import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings  # noqa: E402
from app.persistence.store import Store  # noqa: E402
from app.providers.mock import MockProvider  # noqa: E402
from app.router.engine import EcoComputeRouter  # noqa: E402

PRICED_ENV = {
    "ECOCOMPUTE_PROVIDER": "mock",
    "NEBIUS_API_KEY": "",
    "NEBIUS_MODEL_SMALL": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "NEBIUS_MODEL_MEDIUM": "nvidia/nemotron-3-super-120b-a12b",
    "NEBIUS_MODEL_LARGE": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "NEBIUS_PRICE_IN_SMALL": "0.06", "NEBIUS_PRICE_OUT_SMALL": "0.24",
    "NEBIUS_PRICE_IN_MEDIUM": "0.30", "NEBIUS_PRICE_OUT_MEDIUM": "0.90",
    "NEBIUS_PRICE_IN_LARGE": "1.00", "NEBIUS_PRICE_OUT_LARGE": "3.00",
    "ECOCOMPUTE_DEMO_ACCESS_CODE": "",
    "ECOCOMPUTE_RATE_LIMIT_PER_MINUTE": "1000",
    "ECOCOMPUTE_EXPLORATION_RATE": "0",
}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for k, v in PRICED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ECOCOMPUTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ECOCOMPUTE_DB_PATH", str(tmp_path / "test.db"))
    return load_settings()


@pytest.fixture
def mock_provider(settings):
    return MockProvider({t.model_id: t.rank for t in settings.tiers})


@pytest.fixture
def store(settings):
    return Store(settings.database_path)


@pytest.fixture
def router(settings, mock_provider, store):
    return EcoComputeRouter(settings, mock_provider, store)
