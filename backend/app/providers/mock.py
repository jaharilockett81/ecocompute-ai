"""Deterministic offline provider for tests and UI development.

Every result it returns is tagged provider="mock" and the API/UI label it as
SAMPLE DATA. It never pretends to be Nebius. Behaviour is scripted so tests
can exercise validation failures and escalation deterministically:

- Small-tier models emit malformed JSON for prompts asking for JSON, and a
  wrong answer for prompts containing "[hard]".
- Larger tiers answer from the `expected` hint embedded by the benchmark
  harness (see MockProvider.register_answer) or a generic response.
"""
from __future__ import annotations

import asyncio
import hashlib
import json

from app.providers.base import ChatResult


class MockProvider:
    name = "mock"

    def __init__(self, tier_rank: dict[str, int] | None = None, latency_scale: float = 0.0):
        self._rank = tier_rank or {}
        self._answers: dict[str, str] = {}
        self._latency_scale = latency_scale
        self.calls: list[dict] = []

    def register_answer(self, prompt_fragment: str, answer: str) -> None:
        self._answers[prompt_fragment] = answer

    async def aclose(self) -> None:
        return None

    async def list_models(self) -> list[dict]:
        return [{"id": m, "object": "model", "owned_by": "mock"} for m in self._rank]

    async def chat(self, model, messages, *, max_tokens, temperature, response_format=None) -> ChatResult:
        prompt = "\n".join(str(m.get("content", "")) for m in messages)
        self.calls.append({"model": model, "prompt": prompt})
        rank = self._rank.get(model, 1)
        if self._latency_scale:
            await asyncio.sleep(self._latency_scale * (1 + rank))

        content = self._respond(prompt, rank)
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(content) // 4) + 40 * rank  # larger models "think" more
        digest = hashlib.sha1(f"{model}{prompt}".encode()).hexdigest()
        latency = 300.0 + 450.0 * rank + int(digest[:3], 16) % 200
        return ChatResult(
            ok=True, model=model, content=content, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens,
            latency_ms=float(latency), finish_reason="stop", provider="mock",
            request_id=f"mock-{digest[:12]}",
        )

    def _respond(self, prompt: str, rank: int) -> str:
        if "You are an impartial grader" in prompt:
            return json.dumps({"score": 4, "rationale": "mock judge"})
        answer = next((a for frag, a in self._answers.items() if frag in prompt), None)
        wants_json = "json" in prompt.lower()
        if rank == 0 and wants_json:
            return '{"result": "partial", missing_quote: true'  # deliberately invalid JSON
        if rank == 0 and "[hard]" in prompt:
            return "I am not sure."
        if answer is not None:
            return answer
        if wants_json:
            return json.dumps({"result": "ok"})
        return "Mock response: this is sample output from the offline provider."
