import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.core.logging import redact
from app.providers.nebius import NebiusProvider


@pytest.fixture
def client(settings, mock_provider):
    main.init_state(settings, mock_provider)
    with TestClient(main.app) as c:
        yield c


def test_health_and_config_have_no_secrets(client, monkeypatch):
    r = client.get("/health").json()
    assert r["status"] == "ok" and r["sample_data"] is True
    cfg = client.get("/api/config").json()
    assert "nebius_api_key" not in json.dumps(cfg) and cfg["api_key_configured"] is False
    assert [t["key"] for t in cfg["tiers"]] == ["small", "medium", "large"]
    assert cfg["tiers"][0]["active_params_b"] == 3.0


def test_stream_emits_ordered_trace(client):
    with client.stream("POST", "/api/workloads/stream", json={
        "task": "Return JSON with key result.", "output_format": "json", "category": "structured_json",
        "forced_tier": "small", "required_fields": ["result"]}) as r:
        body = r.read().decode()
    events = [json.loads(chunk.split("data: ", 1)[1]) for chunk in body.strip().split("\n\n") if chunk.startswith("event: event")]
    steps = [e["step"] for e in events]
    assert steps[:3] == ["start", "analyze", "select"]
    assert "escalate" in steps and steps[-1] == "final"
    done = [c for c in body.split("\n\n") if c.startswith("event: done")]
    final = json.loads(done[0].split("data: ", 1)[1])
    assert final["status"] == "passed" and final["final_tier"] == "medium" and final["sample_data"] is True


def test_access_code_and_rate_limit(settings, mock_provider):
    import dataclasses
    s = dataclasses.replace(settings, demo_access_code="judge-2026", rate_limit_per_minute=2)
    main.init_state(s, mock_provider)
    with TestClient(main.app) as c:
        body = {"task": "Say hi to the judges", "output_format": "text"}
        assert c.post("/api/workloads", json=body).status_code == 401
        h = {"X-Access-Code": "judge-2026"}
        assert c.post("/api/workloads", json=body, headers=h).status_code == 200
        assert c.post("/api/workloads", json=body, headers=h).status_code == 200
        assert c.post("/api/workloads", json=body, headers=h).status_code == 429
        # free, read-only endpoints stay open
        assert c.get("/api/overview").status_code == 200
        assert c.post("/api/router/preview", json={"task": "classify this ticket"}).status_code == 200


def test_input_validation(client):
    assert client.post("/api/workloads", json={"task": "x"}).status_code == 422
    assert client.post("/api/workloads", json={"task": "hello", "forced_tier": "giant"}).status_code == 422
    assert client.post("/api/workloads", json={"task": "a" * 9000}).status_code == 413


def test_overview_impact_and_history(client):
    client.post("/api/workloads", json={"task": "Classify: great. positive or negative?", "category": "classification", "required_terms": ["mock"]})
    ov = client.get("/api/overview").json()
    assert ov["workloads_total"] == 1 and ov["quality_pass_rate"] == 1.0
    imp = client.get("/api/impact").json()
    assert imp["measured"]["category"].startswith("A") and imp["estimated"]["category"].startswith("B")
    assert imp["methodology"]["not_observable"]
    hist = client.get("/api/workloads").json()["items"]
    detail = client.get(f"/api/workloads/{hist[0]['id']}").json()
    assert detail["trace"] and detail["attempts"]
    assert client.get("/api/router/evidence").json()["evidence"]


def test_benchmark_endpoints(client):
    r = client.post("/api/benchmarks", json={"conditions": ["fixed:large", "adaptive"], "categories": ["classification"], "limit": 2})
    assert r.status_code == 200, r.text
    assert client.post("/api/benchmarks", json={"conditions": ["adaptive"], "split": "all", "repeats": 3, "max_calls": 5}).status_code == 422


# --------------------------------------------------------- Nebius adapter (simulated HTTP)
def _chat_payload(content="Answer: 4", usage=None):
    return {"id": "chatcmpl-1", "model": "nvidia/x", "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": usage or {"prompt_tokens": 12, "completion_tokens": 30, "total_tokens": 42, "completion_tokens_details": {"reasoning_tokens": 20}}}


@pytest.mark.asyncio
async def test_nebius_retries_429_then_parses_usage_and_strips_think():
    calls = {"n": 0}

    def handler(req: httpx.Request):
        assert req.headers["authorization"] == "Bearer secret-key-123456"
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "slow down"})
        return httpx.Response(200, json=_chat_payload("<think>2+2 is 4</think>Answer: 4"))

    p = NebiusProvider("secret-key-123456", "https://example.test/v1/", transport=httpx.MockTransport(handler), backoff_base_s=0.0)
    res = await p.chat("nvidia/x", [{"role": "user", "content": "2+2"}], max_tokens=50, temperature=0)
    await p.aclose()
    assert res.ok and res.attempts == 2 and res.content == "Answer: 4" and res.reasoning == "2+2 is 4"
    assert (res.prompt_tokens, res.completion_tokens, res.reasoning_tokens) == (12, 30, 20)


@pytest.mark.asyncio
async def test_nebius_auth_error_not_retried_and_redacted():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, text="invalid key secret-key-123456")

    import os
    os.environ["NEBIUS_API_KEY"] = "secret-key-123456"
    try:
        p = NebiusProvider("secret-key-123456", "https://example.test/v1/", transport=httpx.MockTransport(handler), backoff_base_s=0.0)
        res = await p.chat("nvidia/x", [], max_tokens=5, temperature=0)
        await p.aclose()
    finally:
        os.environ["NEBIUS_API_KEY"] = ""
    assert not res.ok and res.error_type == "auth" and calls["n"] == 1
    assert "secret-key-123456" not in res.error


@pytest.mark.asyncio
async def test_nebius_list_models():
    def handler(req):
        assert req.url.path.endswith("/models")
        return httpx.Response(200, json={"data": [{"id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"}]})

    p = NebiusProvider("k" * 10, "https://example.test/v1/", transport=httpx.MockTransport(handler))
    models = await p.list_models()
    await p.aclose()
    assert models[0]["id"].startswith("nvidia/")


def test_redaction():  # Acceptance test 8 (logs)
    assert "abc123secret" not in redact("Authorization: Bearer abc123secret")
    assert "[REDACTED]" in redact('{"api_key": "sk-1234567890abcdef"}')
