from __future__ import annotations

from app.core.config import Settings
from app.providers.mock import MockProvider
from app.providers.nebius import NebiusProvider


def build_provider(settings: Settings):
    if settings.provider == "nebius":
        return NebiusProvider(
            api_key=settings.nebius_api_key,
            base_url=settings.nebius_base_url,
            timeout_s=settings.request_timeout_s,
            max_retries=settings.max_retries,
        )
    if settings.provider == "mock":
        mock = MockProvider({t.model_id: t.rank for t in settings.tiers})
        try:  # let the offline UI show plausible passes on EcoBench tasks (still labelled sample data)
            from app.benchmark.runner import load_dataset
            from app.providers.mock import reference_answer
            for case in load_dataset()["cases"]:
                ans = reference_answer(case)
                if ans is not None:
                    mock.register_answer(case["task"][:160], ans)
        except Exception:  # pragma: no cover - dataset missing in a stripped image
            pass
        return mock
    raise ValueError(f"Unknown provider {settings.provider!r}")
