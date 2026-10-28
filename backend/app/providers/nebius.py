"""Nebius Token Factory adapter (OpenAI-compatible Chat Completions API).

- Authenticates with a bearer key from NEBIUS_API_KEY (never logged).
- Validates model IDs against GET /models.
- Bounded retries with exponential backoff + jitter on 429 / 5xx / timeouts,
  honouring Retry-After when present.
- Measures wall-clock latency and extracts provider-reported token usage,
  including reasoning tokens when the response reports them.
"""
from __future__ import annotations

import asyncio
import random
import time

import httpx

from app.core.logging import get_logger, redact
from app.providers.base import ChatResult, ProviderError, split_reasoning

log = get_logger("ecocompute.nebius")

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class NebiusProvider:
    name = "nebius"

    def __init__(self, api_key: str, base_url: str, timeout_s: float = 90.0, max_retries: int = 3,
                 transport: httpx.AsyncBaseTransport | None = None, backoff_base_s: float = 1.0):
        if not api_key:
            raise ProviderError("NEBIUS_API_KEY is not configured", "configuration")
        self._base_url = base_url
        self._max_retries = max(0, max_retries)
        self._backoff_base = backoff_base_s
        self._client = httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            timeout=httpx.Timeout(timeout_s, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        self._models_cache: tuple[float, list[dict]] | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_models(self) -> list[dict]:
        if self._models_cache and time.time() - self._models_cache[0] < 300:
            return self._models_cache[1]
        try:
            resp = await self._client.get("models", params={"verbose": "true"})
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach Nebius: {type(exc).__name__}", "network") from exc
        if resp.status_code != 200:
            raise ProviderError(
                f"GET /models returned {resp.status_code}: {redact(resp.text[:300])}",
                "auth" if resp.status_code in (401, 403) else "http",
                resp.status_code,
            )
        data = resp.json().get("data", [])
        self._models_cache = (time.time(), data)
        return data

    async def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        response_format: dict | None = None,
    ) -> ChatResult:
        body: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            body["response_format"] = response_format

        attempt = 0
        started = time.perf_counter()
        last_error: ProviderError | None = None
        while attempt <= self._max_retries:
            attempt += 1
            t0 = time.perf_counter()
            try:
                resp = await self._client.post("chat/completions", json=body)
            except httpx.TimeoutException:
                last_error = ProviderError("Request to Nebius timed out", "timeout")
            except httpx.HTTPError as exc:
                last_error = ProviderError(f"Network error: {type(exc).__name__}", "network")
            else:
                latency_ms = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    return self._parse(resp.json(), model, latency_ms, attempt)
                detail = redact(resp.text[:400])
                if resp.status_code in RETRYABLE_STATUS:
                    last_error = ProviderError(f"HTTP {resp.status_code}: {detail}", "rate_limit" if resp.status_code == 429 else "http", resp.status_code)
                    retry_after = resp.headers.get("retry-after")
                    if retry_after and attempt <= self._max_retries:
                        try:
                            await asyncio.sleep(min(float(retry_after), 20.0) * self._backoff_base)
                            continue
                        except ValueError:
                            pass
                else:
                    # 4xx other than throttling: not retryable (bad model id, auth, payload).
                    err_type = "auth" if resp.status_code in (401, 403) else "bad_request"
                    return ChatResult(
                        ok=False, model=model, latency_ms=(time.perf_counter() - started) * 1000,
                        attempts=attempt, error=f"HTTP {resp.status_code}: {detail}", error_type=err_type,
                    )
            if attempt <= self._max_retries:
                backoff = self._backoff_base * (min(2 ** (attempt - 1), 16) + random.uniform(0, 0.5))
                log.warning("nebius retry", extra={"data": {"model": model, "attempt": attempt, "error": str(last_error), "sleep_s": round(backoff, 2)}})
                await asyncio.sleep(backoff)

        assert last_error is not None
        return ChatResult(
            ok=False, model=model, latency_ms=(time.perf_counter() - started) * 1000,
            attempts=attempt, error=str(last_error), error_type=last_error.error_type,
        )

    @staticmethod
    def _parse(payload: dict, requested_model: str, latency_ms: float, attempts: int) -> ChatResult:
        choices = payload.get("choices") or []
        message = (choices[0].get("message") if choices else None) or {}
        raw_content = message.get("content") or ""
        content, inline_reasoning = split_reasoning(raw_content)
        reasoning = message.get("reasoning_content") or message.get("reasoning") or inline_reasoning

        usage = payload.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        return ChatResult(
            ok=True,
            model=payload.get("model") or requested_model,
            content=content,
            reasoning=reasoning,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            reasoning_tokens=details.get("reasoning_tokens"),
            total_tokens=usage.get("total_tokens"),
            latency_ms=latency_ms,
            finish_reason=choices[0].get("finish_reason") if choices else None,
            provider="nebius",
            request_id=payload.get("id"),
            attempts=attempts,
            raw_usage=usage,
        )
