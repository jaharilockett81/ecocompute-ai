"""EcoCompute AI — FastAPI application."""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections import Counter, defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.presets import PRESETS
from app.benchmark.runner import BenchmarkRunner, load_dataset, results_dir
from app.challenge import SCENARIO_MAP, public_scenarios, run_challenge
from app.optimizer import Optimizer, preset_workloads, validate_upload
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.config import ROOT
from app.persistence.bundles import export_bundle, import_dir
from app.persistence.store import Store
from app.providers.base import ProviderError
from app.providers.factory import build_provider
from app.router.analyzer import analyze
from app.router.engine import EcoComputeRouter, WorkloadSpec
from app.router.policy import plan
from app.schemas.api import BenchmarkRequest, PreviewRequest, WorkloadRequest
from app.sustainability.estimator import EnvironmentalImpactEstimator

VERSION = "1.0.0"
log = get_logger("ecocompute.api")


class AppState:
    settings: Settings
    store: Store
    provider: object
    router: EcoComputeRouter
    bench: BenchmarkRunner
    impact: EnvironmentalImpactEstimator
    optimizer: Optimizer
    hits: dict[str, deque]


state = AppState()


def init_state(settings: Settings, provider=None) -> None:
    state.settings = settings
    state.store = Store(settings.database_path)
    state.store.mark_interrupted_runs()
    # Reload committed real-provider results (hosts without a persistent disk lose the DB on restart).
    if settings.provider == "nebius":
        n = import_dir(state.store, ROOT / "benchmarks" / "results")
        if n:
            log.info("imported result bundles", extra={"data": {"count": n}})
    state.provider = provider or build_provider(settings)
    state.router = EcoComputeRouter(settings, state.provider, state.store)
    state.bench = BenchmarkRunner(settings, state.router, state.store)
    state.impact = EnvironmentalImpactEstimator({t.key: t.active_params_b for t in settings.tiers})
    state.optimizer = Optimizer(settings, state.router, state.store, state.impact)
    state.hits = defaultdict(deque)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    if not getattr(state, "settings", None):
        init_state(get_settings())
    log.info("startup", extra={"data": {"provider": state.settings.provider, "tiers": [t.model_id for t in state.settings.tiers]}})
    yield
    await state.provider.aclose()


app = FastAPI(
    title="EcoCompute AI",
    version=VERSION,
    description="Quality-aware, evidence-driven inference routing across NVIDIA Nemotron models on Nebius Token Factory.",
    lifespan=lifespan,
)


def _cors_origins() -> list[str]:
    try:
        return list(get_settings().cors_origins)
    except Exception:
        return ["http://localhost:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Access-Code"],
)


@app.middleware("http")
async def limit_body(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > 64_000:
        return JSONResponse({"detail": "payload too large (64 KB max)"}, status_code=413)
    return await call_next(request)


# ------------------------------------------------------------------ guards
def require_access(x_access_code: str | None = Header(default=None)) -> None:
    code = state.settings.demo_access_code
    if code and x_access_code != code:
        raise HTTPException(401, "This action runs paid inference. Enter the demo access code (see the submission's testing instructions).")


def rate_limit(request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")
    window = state.hits[ip]
    now = time.time()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= state.settings.rate_limit_per_minute:
        raise HTTPException(429, f"Rate limit: {state.settings.rate_limit_per_minute} paid requests per minute.")
    window.append(now)


def _spec_from(req: WorkloadRequest) -> WorkloadSpec:
    s = state.settings
    if len(req.task) > s.max_task_chars:
        raise HTTPException(413, f"task exceeds {s.max_task_chars} characters")
    if req.forced_tier and req.forced_tier not in s.tier_map:
        raise HTTPException(422, f"unknown tier {req.forced_tier!r}")
    return WorkloadSpec(
        task=req.task, category=req.category, output_format=req.output_format, checks=req.build_checks(),
        quality_threshold=req.quality_threshold, allow_escalation=req.allow_escalation,
        max_escalations=req.max_escalations, repair_attempts=req.repair_attempts,
        max_cost_usd=req.max_cost_usd, max_latency_ms=req.max_latency_ms, use_judge=req.use_judge,
        forced_tier=req.forced_tier, source="playground",
    )


def _sample_flag() -> dict:
    return {"provider": state.provider.name, "sample_data": state.provider.name != "nebius"}


# ------------------------------------------------------------------ health / config
@app.get("/", include_in_schema=False)
async def root():
    return {"service": "EcoCompute AI API", "provider": state.provider.name, "health": "/health", "docs": "/docs",
            "ui": "Run the Next.js frontend (cd frontend && npm run dev) and open http://localhost:3000/optimize"}


@app.get("/health")
async def health():
    return {"status": "ok", "version": VERSION, **_sample_flag()}


@app.get("/api/config")
async def config():
    s = state.settings
    return {**s.public_dict(), **_sample_flag(),
            "spend_today_usd": round(state.store.spend_today_usd(), 6), "calls_today": state.store.calls_today()}


@app.get("/api/diagnostics/provider", dependencies=[Depends(require_access)])
async def provider_diagnostics(ping: bool = False):
    """Validates that configured model IDs exist in the authenticated catalog; optionally makes one tiny call."""
    out: dict = {**_sample_flag(), "base_url": state.settings.nebius_base_url, "checked_at": time.time()}
    try:
        catalog = await state.provider.list_models()
        ids = {m.get("id") for m in catalog}
        out["catalog_size"] = len(catalog)
        out["nvidia_models_in_catalog"] = sorted(i for i in ids if i and "nvidia" in i.lower())
        out["tiers"] = [{"tier": t.key, "model_id": t.model_id, "in_catalog": t.model_id in ids} for t in state.settings.tiers]
    except ProviderError as exc:
        out["catalog_error"] = str(exc)
    if ping:
        t = state.settings.tiers[0]
        res = await state.provider.chat(t.model_id, [{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=256, temperature=0.0)
        out["ping"] = {"model": res.model, "ok": res.ok, "content": res.content[:80], "latency_ms": round(res.latency_ms, 1),
                       "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens, "error": res.error,
                       "request_id": res.request_id}
    return out


@app.get("/api/models")
async def models():
    s = state.settings
    tiers = s.public_dict()["tiers"]
    catalog_ok, err = None, None
    try:
        ids = {m.get("id") for m in await state.provider.list_models()}
        for t in tiers:
            t["in_catalog"] = t["model_id"] in ids
        catalog_ok = all(t["in_catalog"] for t in tiers)
    except ProviderError as exc:
        err = str(exc)
    return {"tiers": tiers, "catalog_validated": catalog_ok, "catalog_error": err, **_sample_flag()}


@app.get("/api/presets")
async def presets():
    return PRESETS


# ------------------------------------------------------------------ workloads
@app.post("/api/workloads", dependencies=[Depends(require_access), Depends(rate_limit)])
async def run_workload(req: WorkloadRequest):
    outcome = await state.router.run(_spec_from(req))
    return state.store.get_workload(outcome.workload_id) | _sample_flag()


@app.post("/api/workloads/stream", dependencies=[Depends(require_access), Depends(rate_limit)])
async def stream_workload(req: WorkloadRequest):
    spec = _spec_from(req)
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(("event", event))

    async def worker():
        try:
            outcome = await state.router.run(spec, emit)
            await queue.put(("done", state.store.get_workload(outcome.workload_id) | _sample_flag()))
        except Exception as exc:  # surfaced honestly to the client
            log.exception("workload failed")
            await queue.put(("error", {"detail": f"{type(exc).__name__}: {exc}"}))

    task = asyncio.create_task(worker())

    async def gen():
        try:
            while True:
                kind, payload = await queue.get()
                yield f"event: {kind}\ndata: {json.dumps(payload, default=str)}\n\n"
                if kind in ("done", "error"):
                    break
        finally:
            # Client disconnects do not cancel in-flight paid calls; the workload still records honestly.
            if task.done() and task.exception():
                log.warning("stream worker error", extra={"data": {"err": str(task.exception())}})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/workloads")
async def list_workloads(source: str | None = None, limit: int = 50, offset: int = 0):
    return {"items": state.store.list_workloads(source, min(limit, 200), offset), **_sample_flag()}


@app.get("/api/workloads/{wid}")
async def get_workload(wid: str):
    w = state.store.get_workload(wid)
    if not w:
        raise HTTPException(404, "workload not found")
    return w


# ------------------------------------------------------------------ router
@app.post("/api/router/preview")
async def router_preview(req: PreviewRequest):
    """Analyze and plan without calling any model (free)."""
    analysis = analyze(req.task, req.category, req.output_format)
    decision = plan(state.settings.tiers, analysis, state.router.evidence(), quality_threshold=req.quality_threshold,
                    allow_escalation=req.allow_escalation, max_cost_usd=req.max_cost_usd or state.settings.max_workload_cost_usd,
                    min_start_pass=state.settings.min_start_pass)
    return {"analysis": analysis.as_dict(), "decision": decision.as_dict(), **_sample_flag()}


@app.get("/api/router/evidence")
async def router_evidence():
    return {"evidence": state.router.evidence_summary(), **_sample_flag()}


# ------------------------------------------------------------------ benchmarks
@app.get("/api/benchmark/dataset")
async def dataset():
    return load_dataset()


@app.post("/api/benchmarks", dependencies=[Depends(require_access), Depends(rate_limit)])
async def create_benchmark(req: BenchmarkRequest):
    try:
        return state.bench.create(conditions=req.conditions, split=req.split, categories=req.categories,
                                  case_ids=req.case_ids, limit=req.limit, repeats=req.repeats, max_calls=req.max_calls)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/benchmarks")
async def list_benchmarks():
    return {"items": state.store.list_runs(30), **_sample_flag()}


@app.get("/api/benchmarks/{rid}")
async def get_benchmark(rid: str):
    run = state.store.get_run(rid)
    if not run:
        raise HTTPException(404, "run not found")
    if run["status"] in ("queued", "running"):
        run["summary"] = state.bench.summarize(rid)
    return run


@app.post("/api/benchmarks/{rid}/cancel", dependencies=[Depends(require_access)])
async def cancel_benchmark(rid: str):
    if not state.store.get_run(rid):
        raise HTTPException(404, "run not found")
    return {"cancelled": state.bench.cancel(rid)}


@app.get("/api/benchmarks/{rid}/workloads")
async def benchmark_workloads(rid: str):
    return {"items": state.store.workloads_for_run(rid)}


# ------------------------------------------------------------------ challenge
@app.get("/api/challenge/scenarios")
async def challenge_scenarios():
    return {"scenarios": public_scenarios(state.settings), **_sample_flag()}


@app.post("/api/challenge/{scenario_id}/stream", dependencies=[Depends(require_access), Depends(rate_limit)])
async def stream_challenge(scenario_id: str):
    """Run the scenario through EcoCompute and the fixed baseline concurrently; stream both traces."""
    if scenario_id not in SCENARIO_MAP:
        raise HTTPException(404, "unknown scenario")
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(("event", event))

    async def worker():
        try:
            await queue.put(("done", await run_challenge(state.settings, state.router, state.store, scenario_id, emit)))
        except Exception as exc:
            log.exception("challenge failed")
            await queue.put(("error", {"detail": f"{type(exc).__name__}: {exc}"}))

    asyncio.create_task(worker())

    async def gen():
        while True:
            kind, payload = await queue.get()
            yield f"event: {kind}\ndata: {json.dumps(payload, default=str)}\n\n"
            if kind in ("done", "error"):
                break

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ optimizer
def _sse(work) -> StreamingResponse:
    """Run `work(emit)` in the background and stream its events; the final state is sent as `done`."""
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(("event", event))

    async def worker():
        try:
            await queue.put(("done", await work(emit)))
        except ValueError as exc:
            await queue.put(("error", {"detail": str(exc)}))
        except Exception as exc:
            log.exception("optimizer phase failed")
            await queue.put(("error", {"detail": f"{type(exc).__name__}: {exc}"}))

    asyncio.create_task(worker())

    async def gen():
        while True:
            kind, payload = await queue.get()
            yield f"event: {kind}\ndata: {json.dumps(payload, default=str)}\n\n"
            if kind in ("done", "error"):
                break

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _opt_or_404(oid: str) -> dict:
    rec = state.optimizer.get(oid)
    if not rec:
        raise HTTPException(404, "optimization not found")
    return rec


def _export_opt(oid: str) -> None:
    try:
        out = results_dir()
        out.mkdir(parents=True, exist_ok=True)
        (out / f"optimization-{oid}-{state.provider.name}.json").write_text(
            json.dumps(export_bundle(state.store, "optimization", oid), indent=2, default=str))
    except Exception:  # the DB record is authoritative
        log.exception("could not export optimization")


def _locked(oid: str, phase):
    lock = state.optimizer.lock(oid)
    if lock.locked():
        raise HTTPException(409, "another phase of this optimization is running")

    async def work(emit):
        async with lock:
            st = await phase(emit)
            _export_opt(oid)
            return st
    return _sse(work)


@app.get("/api/optimize/workloads")
async def optimize_workloads():
    return {"workloads": preset_workloads(), "analyst_model": state.settings.analyst_model,
            "baseline": {"tier": state.settings.baseline_tier, "model_id": state.settings.tier_map[state.settings.baseline_tier].model_id},
            **_sample_flag()}


@app.post("/api/optimize/sessions", dependencies=[Depends(rate_limit)])
async def optimize_create(body: dict):
    """Create a session from a preset id or an uploaded list of cases. Free: nothing runs yet."""
    if body.get("preset"):
        wl = next((w for w in preset_workloads() if w["id"] == body["preset"]), None)
        if not wl:
            raise HTTPException(404, "unknown preset workload")
    else:
        try:
            cases = validate_upload(body.get("cases"), state.settings)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        wl = {"id": "upload", "title": str(body.get("title") or "Uploaded workload")[:80], "source": "upload",
              "description": "Uploaded by the user.", "cases": cases}
    return state.optimizer.create(wl)["state"]


@app.get("/api/optimize/sessions")
async def optimize_list(limit: int = 20):
    items = [{"id": r["id"], "created_at": r["created_at"], "status": r["status"], "title": r["title"], "provider": r["provider"],
              "summary": _opt_summary(r["state"])} for r in state.store.list_optimizations(min(limit, 100))]
    return {"items": items, **_sample_flag()}


def _opt_summary(st: dict) -> dict:
    rec = st.get("recommendation") or {}
    return {"tasks": len(st.get("workload", {}).get("cases", [])), "rounds": len(st.get("rounds") or []),
            "cost_rel": (rec.get("gate") or {}).get("deltas", {}).get("cost_rel"),
            "drill_rejected": bool(st.get("drill") and st["drill"].get("gate") and not st["drill"]["gate"]["accepted"])}


@app.get("/api/optimize/sessions/{oid}")
async def optimize_get(oid: str):
    return _opt_or_404(oid)["state"]


@app.post("/api/optimize/sessions/{oid}/baseline", dependencies=[Depends(require_access), Depends(rate_limit)])
async def optimize_baseline(oid: str):
    _opt_or_404(oid)
    return _locked(oid, lambda emit: state.optimizer.run_baseline(oid, emit))


@app.post("/api/optimize/sessions/{oid}/analyze", dependencies=[Depends(require_access), Depends(rate_limit)])
async def optimize_analyze(oid: str):
    if not _opt_or_404(oid)["state"].get("baseline"):
        raise HTTPException(409, "run the baseline first")
    return _locked(oid, lambda emit: state.optimizer.analyze(oid, emit))


@app.post("/api/optimize/sessions/{oid}/verify", dependencies=[Depends(require_access), Depends(rate_limit)])
async def optimize_verify(oid: str, body: dict):
    st = _opt_or_404(oid)["state"]
    if not st.get("analysis"):
        raise HTTPException(409, "run the analysis first")
    ids = [str(i) for i in body.get("proposal_ids") or []]
    if not ids:
        raise HTTPException(422, "select at least one proposal to test")
    rounds = int(body.get("max_rounds") or 2)
    drill = bool(body.get("safety_drill", True))
    return _locked(oid, lambda emit: state.optimizer.verify(oid, ids, emit, max_rounds=rounds, safety_drill=drill))


@app.post("/api/optimize/sessions/{oid}/decision", dependencies=[Depends(require_access)])
async def optimize_decision(oid: str, body: dict):
    _opt_or_404(oid)
    try:
        st = state.optimizer.decide(oid, str(body.get("decision")), str(body.get("note") or ""))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    _export_opt(oid)
    return st


@app.get("/api/optimize/sessions/{oid}/export")
async def optimize_export(oid: str):
    _opt_or_404(oid)
    return state.optimizer.export(oid)


@app.get("/api/challenges")
async def list_challenges(limit: int = 20):
    return {"items": state.store.list_challenges(min(limit, 100)), **_sample_flag()}


@app.get("/api/challenges/{cid}")
async def get_challenge(cid: str):
    c = state.store.get_challenge(cid)
    if not c:
        raise HTTPException(404, "challenge not found")
    return c


@app.get("/api/bundles/{kind}/{rid}")
async def get_bundle(kind: str, rid: str):
    """Portable export of a benchmark run or challenge with full workload records (commit to benchmarks/results/)."""
    if kind not in ("benchmark", "challenge", "optimization"):
        raise HTTPException(404, "unknown kind")
    try:
        return export_bundle(state.store, kind, rid)
    except KeyError:
        raise HTTPException(404, f"{kind} not found")


# ------------------------------------------------------------------ analytics
def _measured(attempts: list[dict], workloads: list[dict]) -> dict:
    ok = [a for a in attempts if a["ok"]]
    costs = [a["cost_usd"] for a in ok if a.get("cost_usd") is not None]
    return {
        "category": "A — directly measured (cost = provider-reported tokens × configured price)",
        "calls": len(attempts),
        "failed_calls": len(attempts) - len(ok),
        "prompt_tokens": sum(a.get("prompt_tokens") or 0 for a in ok),
        "completion_tokens": sum(a.get("completion_tokens") or 0 for a in ok),
        "reasoning_tokens": sum(a.get("reasoning_tokens") or 0 for a in ok),
        "calls_missing_usage": sum(1 for a in ok if a.get("prompt_tokens") is None),
        "total_latency_ms": round(sum(a.get("latency_ms") or 0 for a in attempts), 1),
        "total_cost_usd": round(sum(costs), 6) if costs else None,
        "calls_by_tier": dict(Counter(a.get("tier") or "?" for a in attempts)),
        "workloads": len(workloads),
    }


@app.get("/api/impact")
async def impact(run_id: str | None = None):
    provider = state.provider.name
    if run_id:
        wls = state.store.workloads_for_run(run_id)
        by_cond: dict[str, list[dict]] = defaultdict(list)
        atts: dict[str, list[dict]] = defaultdict(list)
        for w in wls:
            by_cond[w["condition"]].append(w)
            atts[w["condition"]].extend(state.store.list_attempts(w["id"]))
        return {
            "run_id": run_id, **_sample_flag(),
            "conditions": {c: {"measured": _measured(atts[c], by_cond[c]), "estimated": state.impact.estimate_attempts(atts[c])} for c in by_cond},
            "methodology": state.impact.methodology(),
        }
    attempts = state.store.attempt_rows(provider)
    workloads = state.store.workload_rows(provider)
    return {**_sample_flag(), "measured": _measured(attempts, workloads),
            "estimated": state.impact.estimate_attempts(attempts), "methodology": state.impact.methodology()}


@app.get("/api/overview")
async def overview():
    provider = state.provider.name
    wls = [w for w in state.store.workload_rows(provider) if w["status"] != "running"]
    graded = [w for w in wls if w["status"] in ("passed", "failed")]
    passed = [w for w in graded if w["status"] == "passed"]
    lat = [w["latency_ms"] for w in wls if w.get("latency_ms")]
    costs = [w["cost_usd"] for w in wls if w.get("cost_usd") is not None]
    runs = [r for r in state.store.list_runs(20) if r["status"] in ("completed", "cancelled", "budget_stopped") and r["provider"] == provider]
    latest = runs[0] if runs else None
    by_cat_tier: dict[str, Counter] = defaultdict(Counter)
    for w in wls:
        by_cat_tier[w.get("category") or "unknown"][w.get("final_tier") or "none"] += 1
    return {
        **_sample_flag(),
        "workloads_total": len(wls),
        "workloads_graded": len(graded),
        "quality_pass_rate": round(len(passed) / len(graded), 4) if graded else None,
        "latency_ms_mean": round(statistics.fmean(lat), 1) if lat else None,
        "latency_ms_median": round(statistics.median(lat), 1) if lat else None,
        "total_cost_usd": round(sum(costs), 6) if costs else None,
        "cost_per_success_usd": round(sum(costs) / len(passed), 6) if costs and passed else None,
        "escalation_rate": round(sum(1 for w in wls if (w.get("escalations") or 0) > 0) / len(wls), 4) if wls else None,
        "final_tier_distribution": dict(Counter(w.get("final_tier") or "none" for w in wls)),
        "tier_by_category": {k: dict(v) for k, v in by_cat_tier.items()},
        "latest_benchmark": {"id": latest["id"], "created_at": latest["created_at"], "status": latest["status"],
                             "summary": latest["summary"]} if latest else None,
        "spend_today_usd": round(state.store.spend_today_usd(), 6),
        "daily_budget_usd": state.settings.daily_budget_usd,
    }
