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
        finish = "stop"
        if completion_tokens > max_tokens:  # honour the output cap like a real endpoint
            content, completion_tokens, finish = content[: max(0, (max_tokens - 40 * rank) * 4)], max_tokens, "length"
        digest = hashlib.sha1(f"{model}{prompt}".encode()).hexdigest()
        latency = 300.0 + 450.0 * rank + int(digest[:3], 16) % 200
        return ChatResult(
            ok=True, model=model, content=content, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens,
            latency_ms=float(latency), finish_reason=finish, provider="mock",
            request_id=f"mock-{digest[:12]}",
        )

    def _respond(self, prompt: str, rank: int) -> str:
        if "You are an impartial grader" in prompt:
            return json.dumps({"score": 4, "rationale": "mock judge"})
        if "You are EcoCompute's optimization analyst" in prompt:
            return self._analyst(prompt)
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

    @staticmethod
    def _analyst(prompt: str) -> str:
        """Scripted analyst: route every category to the small tier with escalation, one refusal-worthy item."""
        line = next((l for l in prompt.splitlines() if l.startswith("CATEGORIES: ")), "CATEGORIES: ")
        cats = [c for c in line.removeprefix("CATEGORIES: ").split(",") if c]
        props = []
        for i, c in enumerate(cats):
            props.append({"id": f"p{2 * i + 1}", "type": "route_category", "category": c, "tier": "small",
                          "rationale": "mock analyst (sample data)", "evidence": "mock", "expected_effect": "lower cost", "risk": "quality"})
            props.append({"id": f"p{2 * i + 2}", "type": "enable_escalation", "category": c, "enabled": True,
                          "rationale": "mock analyst (sample data)", "evidence": "mock", "expected_effect": "recover failures", "risk": "extra calls"})
        return json.dumps({"diagnosis": [{"finding": "Mock diagnosis (sample data): every task runs on the largest tier.",
                                          "evidence": "mock", "categories": cats}],
                           "proposals": props, "next_action": "Test the proposals against the baseline."})


def reference_answer(case: dict) -> str | None:
    """Correct answer derivable from a case's checks (mock provider only, for UI development)."""
    for ch in case.get("checks", []):
        if ch.get("type") == "json_fields":
            out: dict = {}
            for path, v in ch["expected"].items():
                cur = out
                parts = path.split(".")
                if any(p.isdigit() for p in parts):
                    return None
                for p in parts[:-1]:
                    cur = cur.setdefault(p, {})
                cur[parts[-1]] = v
            return json.dumps(out)
        if ch.get("type") in ("label", "exact"):
            return str(ch["answer"])
        if ch.get("type") == "numeric":
            return str(ch["answer"])
    return None
