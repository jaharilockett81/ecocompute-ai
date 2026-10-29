"""SQLite persistence for workloads, per-call attempts, and benchmark runs.

Every inference call (primary, escalation, judge, router) is an `attempt` row,
so spend, tokens and latency are always reconstructable from raw records.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS workloads (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    source TEXT NOT NULL,              -- playground | benchmark
    run_id TEXT,
    condition TEXT,                    -- adaptive | baseline | small_only (benchmark only)
    case_id TEXT,
    repeat INTEGER DEFAULT 0,
    category TEXT,
    task_text TEXT,
    output_format TEXT,
    status TEXT NOT NULL,              -- running | passed | failed | unverified | error | budget_blocked
    initial_tier TEXT,
    final_tier TEXT,
    final_model TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    usage_complete INTEGER DEFAULT 1,  -- 0 if any call lacked provider-reported usage
    cost_usd REAL,
    overhead_cost_usd REAL DEFAULT 0,
    latency_ms REAL DEFAULT 0,
    escalations INTEGER DEFAULT 0,
    calls INTEGER DEFAULT 0,
    eval_method TEXT,
    provider TEXT,
    final_output TEXT,
    analysis_json TEXT,
    decision_json TEXT,
    trace_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_workloads_run ON workloads(run_id, condition);
CREATE INDEX IF NOT EXISTS idx_workloads_created ON workloads(created_at);

CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    workload_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    role TEXT NOT NULL,                -- primary | judge | router
    tier TEXT,
    model TEXT NOT NULL,
    provider TEXT,
    ok INTEGER NOT NULL,
    passed INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    reasoning_tokens INTEGER,
    latency_ms REAL,
    cost_usd REAL,
    finish_reason TEXT,
    eval_method TEXT,
    eval_detail TEXT,
    error TEXT,
    category TEXT,
    source TEXT,
    case_id TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_workload ON attempts(workload_id);
CREATE INDEX IF NOT EXISTS idx_attempts_created ON attempts(created_at);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    finished_at REAL,
    status TEXT NOT NULL,              -- queued | running | completed | cancelled | failed | budget_stopped
    provider TEXT,
    dataset_version TEXT,
    conditions_json TEXT,
    case_ids_json TEXT,
    max_calls INTEGER,
    calls_made INTEGER DEFAULT 0,
    progress_done INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0,
    error TEXT,
    summary_json TEXT,
    config_json TEXT
);

CREATE TABLE IF NOT EXISTS challenges (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    finished_at REAL,
    status TEXT NOT NULL,              -- running | completed | failed
    scenario_id TEXT NOT NULL,
    provider TEXT,
    ecocompute_workload_id TEXT,
    baseline_workload_id TEXT,
    comparison_json TEXT,
    error TEXT
);
"""


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def _utc_day_start(ts: float | None = None) -> float:
    now = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp()


class Store:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    # ---------------------------------------------------------------- helpers
    def _exec(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _all(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _one(self, sql: str, params: tuple | dict = ()) -> dict | None:
        rows = self._all(sql, params)
        return rows[0] if rows else None

    # -------------------------------------------------------------- workloads
    def create_workload(self, **fields: Any) -> str:
        wid = fields.pop("id", None) or new_id()
        fields.setdefault("created_at", time.time())
        fields.setdefault("status", "running")
        cols = ["id", *fields.keys()]
        self._exec(
            f"INSERT INTO workloads ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            (wid, *[_ser(v) for v in fields.values()]),
        )
        return wid

    def update_workload(self, wid: str, **fields: Any) -> None:
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE workloads SET {sets} WHERE id=?", (*[_ser(v) for v in fields.values()], wid))

    def get_workload(self, wid: str) -> dict | None:
        row = self._one("SELECT * FROM workloads WHERE id=?", (wid,))
        if row:
            row = _deser_workload(row)
            row["attempts"] = self.list_attempts(wid)
        return row

    def list_workloads(self, source: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        sql = "SELECT * FROM workloads"
        params: tuple = ()
        if source:
            sql += " WHERE source=?"
            params = (source,)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        return [_deser_workload(r, light=True) for r in self._all(sql, (*params, limit, offset))]

    def workloads_for_run(self, run_id: str) -> list[dict]:
        return [_deser_workload(r, light=True) for r in self._all("SELECT * FROM workloads WHERE run_id=? ORDER BY created_at", (run_id,))]

    # --------------------------------------------------------------- attempts
    def add_attempt(self, **fields: Any) -> str:
        aid = new_id()
        fields.setdefault("created_at", time.time())
        cols = ["id", *fields.keys()]
        self._exec(
            f"INSERT INTO attempts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            (aid, *[_ser(v) for v in fields.values()]),
        )
        return aid

    def list_attempts(self, workload_id: str) -> list[dict]:
        return self._all("SELECT * FROM attempts WHERE workload_id=? ORDER BY idx", (workload_id,))

    def spend_today_usd(self) -> float:
        row = self._one(
            "SELECT COALESCE(SUM(cost_usd),0) AS s FROM attempts WHERE created_at>=? AND provider='nebius'",
            (_utc_day_start(),),
        )
        return float(row["s"]) if row else 0.0

    def calls_today(self) -> int:
        row = self._one("SELECT COUNT(*) AS c FROM attempts WHERE created_at>=? AND provider='nebius'", (_utc_day_start(),))
        return int(row["c"]) if row else 0

    def tier_outcomes(self, provider: str) -> list[dict]:
        """Aggregate primary-call validation outcomes per (category, tier).
        Only calls with a deterministic or judge verdict count as evidence."""
        return self._all(
            """
            SELECT category, tier, COUNT(*) AS n,
                   SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END) AS passes,
                   AVG(prompt_tokens) AS avg_prompt, AVG(completion_tokens) AS avg_completion,
                   AVG(latency_ms) AS avg_latency, AVG(cost_usd) AS avg_cost
            FROM attempts
            WHERE role='primary' AND ok=1 AND passed IS NOT NULL AND provider=? AND category IS NOT NULL
            GROUP BY category, tier
            """,
            (provider,),
        )

    def calibration_evidence(self, provider: str, case_ids: list[str]) -> dict[tuple[str, str], dict]:
        """Evidence restricted to calibration-split cases (no test-set leakage)."""
        if not case_ids:
            return {}
        marks = ",".join("?" * len(case_ids))
        rows = self._all(
            f"""
            SELECT category, tier, COUNT(*) AS n,
                   SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END) AS passes,
                   AVG(prompt_tokens) AS avg_prompt, AVG(completion_tokens) AS avg_completion,
                   AVG(latency_ms) AS avg_latency, AVG(cost_usd) AS avg_cost
            FROM attempts
            WHERE role='primary' AND ok=1 AND passed IS NOT NULL AND provider=? AND source='benchmark'
              AND case_id IN ({marks})
            GROUP BY category, tier
            """,
            (provider, *case_ids),
        )
        return {(r["category"], r["tier"]): r for r in rows}

    def attempt_rows(self, provider: str | None = None, limit: int = 5000) -> list[dict]:
        if provider:
            return self._all("SELECT * FROM attempts WHERE provider=? ORDER BY created_at DESC LIMIT ?", (provider, limit))
        return self._all("SELECT * FROM attempts ORDER BY created_at DESC LIMIT ?", (limit,))

    def workload_rows(self, provider: str | None = None, limit: int = 5000) -> list[dict]:
        if provider:
            rows = self._all("SELECT * FROM workloads WHERE provider=? ORDER BY created_at DESC LIMIT ?", (provider, limit))
        else:
            rows = self._all("SELECT * FROM workloads ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_deser_workload(r, light=True) for r in rows]

    # ----------------------------------------------------------- benchmarks
    def create_run(self, **fields: Any) -> str:
        rid = new_id()
        fields.setdefault("created_at", time.time())
        cols = ["id", *fields.keys()]
        self._exec(
            f"INSERT INTO benchmark_runs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            (rid, *[_ser(v) for v in fields.values()]),
        )
        return rid

    def update_run(self, rid: str, **fields: Any) -> None:
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            self._exec(f"UPDATE benchmark_runs SET {sets} WHERE id=?", (*[_ser(v) for v in fields.values()], rid))

    def get_run(self, rid: str) -> dict | None:
        row = self._one("SELECT * FROM benchmark_runs WHERE id=?", (rid,))
        return _deser_run(row) if row else None

    def list_runs(self, limit: int = 20) -> list[dict]:
        return [_deser_run(r) for r in self._all("SELECT * FROM benchmark_runs ORDER BY created_at DESC LIMIT ?", (limit,))]

    # -------------------------------------------------------------- challenges
    def create_challenge(self, **fields: Any) -> str:
        cid = new_id()
        fields.setdefault("created_at", time.time())
        fields.setdefault("status", "running")
        cols = ["id", *fields.keys()]
        self._exec(
            f"INSERT INTO challenges ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            (cid, *[_ser(v) for v in fields.values()]),
        )
        return cid

    def update_challenge(self, cid: str, **fields: Any) -> None:
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            self._exec(f"UPDATE challenges SET {sets} WHERE id=?", (*[_ser(v) for v in fields.values()], cid))

    def get_challenge(self, cid: str) -> dict | None:
        row = self._one("SELECT * FROM challenges WHERE id=?", (cid,))
        return _deser_challenge(row) if row else None

    def list_challenges(self, limit: int = 20) -> list[dict]:
        return [_deser_challenge(r) for r in self._all("SELECT * FROM challenges ORDER BY created_at DESC LIMIT ?", (limit,))]

    def mark_interrupted_runs(self) -> None:
        self._exec("UPDATE benchmark_runs SET status='failed', error='Server restarted during run' WHERE status IN ('queued','running')")
        self._exec("UPDATE challenges SET status='failed', error='Server restarted during run' WHERE status='running'")
        self._exec("UPDATE workloads SET status='error' WHERE status='running'")


def _ser(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    if isinstance(v, bool):
        return int(v)
    return v


def _deser_workload(row: dict, light: bool = False) -> dict:
    for key in ("analysis_json", "decision_json", "trace_json"):
        raw = row.pop(key, None)
        name = key.removesuffix("_json")
        if light and key == "trace_json":
            continue
        row[name] = json.loads(raw) if raw else None
    row["usage_complete"] = bool(row.get("usage_complete"))
    return row


def _deser_run(row: dict) -> dict:
    for key in ("conditions_json", "case_ids_json", "summary_json", "config_json"):
        raw = row.pop(key, None)
        row[key.removesuffix("_json")] = json.loads(raw) if raw else None
    return row


def _deser_challenge(row: dict) -> dict:
    raw = row.pop("comparison_json", None)
    row["comparison"] = json.loads(raw) if raw else None
    return row
