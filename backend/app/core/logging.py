"""Structured logging with secret redaction."""
from __future__ import annotations

import json
import logging
import os
import re
import time

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key[\"'=:\s]+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE),
    re.compile(r"(tvly-)[A-Za-z0-9_\-]+"),
]


def redact(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(1) + "[REDACTED]", out)
    for env_name in ("NEBIUS_API_KEY", "TAVILY_API_KEY", "ECOCOMPUTE_DEMO_ACCESS_CODE"):
        secret = os.environ.get(env_name, "")
        if secret and len(secret) >= 6:
            out = out.replace(secret, "[REDACTED]")
    return out


class JsonRedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "data", None)
        if extra:
            payload["data"] = extra
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str))


def configure_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonRedactingFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonRedactingFormatter())
    root.handlers = [handler]
    root.setLevel(os.environ.get("ECOCOMPUTE_LOG_LEVEL", "INFO"))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
