"""Provider abstraction shared by the real Nebius adapter and the offline mock."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ChatResult:
    ok: bool
    model: str
    content: str = ""
    reasoning: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float = 0.0
    finish_reason: str | None = None
    provider: str = "nebius"
    request_id: str | None = None
    attempts: int = 1
    error: str | None = None
    error_type: str | None = None
    raw_usage: dict = field(default_factory=dict)

    @property
    def usage_reported(self) -> bool:
        return self.prompt_tokens is not None and self.completion_tokens is not None


class ProviderError(Exception):
    def __init__(self, message: str, error_type: str = "provider_error", status: int | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.status = status


class Provider(Protocol):
    name: str

    async def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        response_format: dict | None = None,
    ) -> ChatResult: ...

    async def list_models(self) -> list[dict]: ...

    async def aclose(self) -> None: ...


_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


def split_reasoning(content: str) -> tuple[str, str | None]:
    """Separate inline <think>…</think> reasoning (emitted by some reasoning
    models) from the final answer so validators see only the answer."""
    if not content:
        return content, None
    thoughts = _THINK_RE.findall(content)
    cleaned = _THINK_RE.sub("", content)
    # An unterminated <think> block means the answer was cut off mid-reasoning.
    if "<think>" in cleaned.lower():
        idx = cleaned.lower().index("<think>")
        thoughts.append(cleaned[idx + 7 :])
        cleaned = cleaned[:idx]
    return cleaned.strip(), ("\n".join(t.strip() for t in thoughts) or None)
