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
        return MockProvider({t.model_id: t.rank for t in settings.tiers})
    raise ValueError(f"Unknown provider {settings.provider!r}")
