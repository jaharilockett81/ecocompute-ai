"""Environment-driven configuration.

Nothing provider-specific (URLs, model IDs, prices) is hardcoded in logic:
everything comes from environment variables, with `.env.example` documenting
the values to verify against the authenticated Nebius Token Factory catalog.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _float(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw == "":
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ModelTier:
    """One rung of the escalation ladder."""

    key: str  # "small" | "medium" | "large"
    model_id: str
    label: str
    rank: int  # 0 = cheapest
    price_in_per_m: float | None  # USD per 1M input tokens (configured, verify on pricing page)
    price_out_per_m: float | None  # USD per 1M output tokens
    active_params_b: float | None = None  # billions of active params (for impact estimates only)

    @property
    def priced(self) -> bool:
        return self.price_in_per_m is not None and self.price_out_per_m is not None

    def cost(self, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
        if not self.priced or prompt_tokens is None or completion_tokens is None:
            return None
        return (prompt_tokens * self.price_in_per_m + completion_tokens * self.price_out_per_m) / 1_000_000


@dataclass(frozen=True)
class Settings:
    provider: str  # "nebius" | "mock"
    nebius_api_key: str
    nebius_base_url: str
    tiers: tuple[ModelTier, ...]
    router_model: str
    judge_model: str
    baseline_tier: str

    request_timeout_s: float
    max_retries: int
    max_output_tokens: int
    temperature: float
    max_concurrency: int

    daily_budget_usd: float
    max_workload_cost_usd: float
    benchmark_max_calls: int
    max_task_chars: int
    rate_limit_per_minute: int
    demo_access_code: str
    cors_origins: tuple[str, ...]

    enable_code_execution: bool
    exploration_rate: float
    min_start_pass: float
    database_path: str
    data_dir: Path = field(default=Path("."))
    analyst_model: str = ""  # Nemotron model that diagnoses workloads and proposes optimizations

    @property
    def tier_map(self) -> dict[str, ModelTier]:
        return {t.key: t for t in self.tiers}

    def tier_for_model(self, model_id: str) -> ModelTier | None:
        for t in self.tiers:
            if t.model_id == model_id:
                return t
        return None

    def public_dict(self) -> dict:
        """Configuration safe to expose to the frontend (no secrets)."""
        return {
            "provider": self.provider,
            "base_url": self.nebius_base_url,
            "api_key_configured": bool(self.nebius_api_key),
            "tiers": [
                {
                    "key": t.key,
                    "model_id": t.model_id,
                    "label": t.label,
                    "rank": t.rank,
                    "price_in_per_m": t.price_in_per_m,
                    "price_out_per_m": t.price_out_per_m,
                    "active_params_b": t.active_params_b,
                }
                for t in self.tiers
            ],
            "router_model": self.router_model,
            "judge_model": self.judge_model,
            "analyst_model": self.analyst_model,
            "baseline_tier": self.baseline_tier,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "daily_budget_usd": self.daily_budget_usd,
            "max_workload_cost_usd": self.max_workload_cost_usd,
            "benchmark_max_calls": self.benchmark_max_calls,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "access_code_required": bool(self.demo_access_code),
            "code_execution_enabled": self.enable_code_execution,
            "exploration_rate": self.exploration_rate,
            "min_start_pass": self.min_start_pass,
        }


ROOT = Path(__file__).resolve().parents[3]  # repo root


def _active_from_id(model_id: str) -> float | None:
    """MoE model IDs often encode active params, e.g. '...-30B-A3B' -> 3.0."""
    import re

    m = re.search(r"[-_]a(\d+(?:\.\d+)?)b\b", model_id.lower())
    return float(m.group(1)) if m else None


def load_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    _load_dotenv(ROOT / "backend" / ".env")

    small = os.environ.get("NEBIUS_MODEL_SMALL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
    medium = os.environ.get("NEBIUS_MODEL_MEDIUM", "nvidia/nemotron-3-super-120b-a12b")
    large = os.environ.get("NEBIUS_MODEL_LARGE", "nvidia/Nemotron-3-Ultra-550b-a55b")

    tiers: list[ModelTier] = []
    for rank, (key, mid, label) in enumerate(
        [("small", small, "Nemotron Nano"), ("medium", medium, "Nemotron Super"), ("large", large, "Nemotron Ultra")]
    ):
        if not mid:  # a tier can be disabled by setting it empty
            continue
        upper = key.upper()
        tiers.append(
            ModelTier(
                key=key,
                model_id=mid,
                label=os.environ.get(f"NEBIUS_LABEL_{upper}", label),
                rank=rank,
                price_in_per_m=_float(f"NEBIUS_PRICE_IN_{upper}", None),
                price_out_per_m=_float(f"NEBIUS_PRICE_OUT_{upper}", None),
                active_params_b=_float(f"NEBIUS_ACTIVE_PARAMS_B_{upper}", _active_from_id(mid)),
            )
        )
    if not tiers:
        raise RuntimeError("At least one model tier must be configured")

    api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
    provider = os.environ.get("ECOCOMPUTE_PROVIDER", "nebius" if api_key else "mock").strip().lower()

    data_dir = Path(os.environ.get("ECOCOMPUTE_DATA_DIR", str(ROOT / "backend" / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        provider=provider,
        nebius_api_key=api_key,
        nebius_base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/").rstrip("/") + "/",
        tiers=tuple(tiers),
        router_model=os.environ.get("NEBIUS_ROUTER_MODEL", "").strip() or tiers[0].model_id,
        judge_model=os.environ.get("NEBIUS_JUDGE_MODEL", "").strip() or tiers[min(1, len(tiers) - 1)].model_id,
        baseline_tier=os.environ.get("ECOCOMPUTE_BASELINE_TIER", tiers[-1].key),
        request_timeout_s=_float("ECOCOMPUTE_REQUEST_TIMEOUT_S", 90.0) or 90.0,
        max_retries=_int("ECOCOMPUTE_MAX_RETRIES", 3),
        max_output_tokens=_int("ECOCOMPUTE_MAX_OUTPUT_TOKENS", 2048),
        temperature=_float("ECOCOMPUTE_TEMPERATURE", 0.0) or 0.0,
        max_concurrency=_int("ECOCOMPUTE_MAX_CONCURRENCY", 4),
        daily_budget_usd=_float("ECOCOMPUTE_DAILY_BUDGET_USD", 5.0) or 5.0,
        max_workload_cost_usd=_float("ECOCOMPUTE_MAX_WORKLOAD_COST_USD", 0.05) or 0.05,
        benchmark_max_calls=_int("ECOCOMPUTE_BENCHMARK_MAX_CALLS", 400),
        max_task_chars=_int("ECOCOMPUTE_MAX_TASK_CHARS", 8000),
        rate_limit_per_minute=_int("ECOCOMPUTE_RATE_LIMIT_PER_MINUTE", 12),
        demo_access_code=os.environ.get("ECOCOMPUTE_DEMO_ACCESS_CODE", "").strip(),
        cors_origins=tuple(
            o.strip() for o in os.environ.get("ECOCOMPUTE_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        ),
        enable_code_execution=_bool("ECOCOMPUTE_ENABLE_CODE_EXECUTION", True),
        exploration_rate=_float("ECOCOMPUTE_EXPLORATION_RATE", 0.0) or 0.0,
        min_start_pass=_float("ECOCOMPUTE_MIN_START_PASS", 0.5),
        database_path=os.environ.get("ECOCOMPUTE_DB_PATH", str(data_dir / "ecocompute.db")),
        data_dir=data_dir,
        analyst_model=os.environ.get("NEBIUS_ANALYST_MODEL", "").strip() or tiers[min(1, len(tiers) - 1)].model_id,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
