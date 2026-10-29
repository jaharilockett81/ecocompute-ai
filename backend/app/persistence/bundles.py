"""Portable result bundles: export a benchmark run or a Challenge with its full
workload records, and re-import them on startup.

Hosts without a persistent disk lose the SQLite file on restart. Bundles
committed under benchmarks/results/ are loaded back so the recorded results
(and their traces, attempts and request IDs) stay visible. Only bundles from
the real provider are imported; mock bundles are never loaded.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.logging import get_logger
from app.persistence.store import Store, _ser

log = get_logger("ecocompute.bundles")

_RUN_JSON = ("conditions", "case_ids", "summary", "config")
_WL_JSON = ("analysis", "decision", "trace")


def export_bundle(store: Store, kind: str, rid: str) -> dict:
    if kind == "benchmark":
        record = store.get_run(rid)
        wids = [w["id"] for w in store.workloads_for_run(rid)]
    elif kind == "challenge":
        record = store.get_challenge(rid)
        wids = [w for w in (record.get("ecocompute_workload_id"), record.get("baseline_workload_id")) if w] if record else []
    else:
        raise ValueError(kind)
    if not record:
        raise KeyError(rid)
    return {"kind": kind, "bundle_version": 1, "record": record, "workloads": [store.get_workload(w) for w in wids]}


def _insert(store: Store, table: str, row: dict) -> None:
    cols = list(row.keys())
    store._exec(  # noqa: SLF001 - same package
        f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        tuple(_ser(v) for v in row.values()),
    )


def import_bundle(store: Store, bundle: dict, only_provider: str | None = "nebius") -> bool:
    kind, rec = bundle.get("kind"), dict(bundle.get("record") or {})
    if kind not in ("benchmark", "challenge") or not rec.get("id"):
        return False
    if only_provider and rec.get("provider") != only_provider:
        return False
    exists = store.get_run(rec["id"]) if kind == "benchmark" else store.get_challenge(rec["id"])
    if exists:
        return False
    for w in bundle.get("workloads") or []:
        w = dict(w)
        attempts = w.pop("attempts", []) or []
        w.pop("sample_data", None)
        for k in _WL_JSON:
            if k in w:
                w[f"{k}_json"] = w.pop(k)
        _insert(store, "workloads", w)
        for a in attempts:
            _insert(store, "attempts", a)
    if kind == "benchmark":
        for k in _RUN_JSON:
            if k in rec:
                rec[f"{k}_json"] = rec.pop(k)
        _insert(store, "benchmark_runs", rec)
    else:
        rec["comparison_json"] = rec.pop("comparison", None)
        _insert(store, "challenges", rec)
    return True


def import_dir(store: Store, directory: Path, only_provider: str | None = "nebius") -> int:
    n = 0
    for p in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            if import_bundle(store, json.loads(p.read_text()), only_provider):
                n += 1
        except Exception:  # a malformed file must not stop startup
            log.exception("could not import bundle", extra={"data": {"file": p.name}})
    return n
