"""Deliberate, labelled fault injection for safety drills.

A drill takes a REAL model answer and corrupts it in a deterministic way
before it reaches the quality gate. The point is to prove, on live traffic,
that the gate rejects a bad candidate and the router recovers. It is never
presented as a model failure: the trace, the attempt record and the API all
mark the candidate as injected, and injected attempts are excluded from the
routing evidence.
"""
from __future__ import annotations

import hashlib
import json

from app.evaluation.validators import _get_path, parse_json_output

FAULT_KINDS = ("corrupt_candidate",)
MARKER = "INJECTED_FAULT"


def _wrong(value: object) -> object:
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    return MARKER  # strings, None, anything else


def _set_path(obj: object, path: str, value: object) -> bool:
    parts = path.split(".")
    parent = _get_path(obj, ".".join(parts[:-1])) if len(parts) > 1 else obj
    last = parts[-1]
    if isinstance(parent, dict):
        parent[last] = value
        return True
    if isinstance(parent, list) and last.isdigit() and int(last) < len(parent):
        parent[int(last)] = value
        return True
    return False


def corrupt_candidate(output: str, checks: list[dict]) -> tuple[str, dict]:
    """Return (corrupted_output, description). Deterministic for a given input.

    Preferred mutation: flip the first field the validator checks to a wrong
    value, keeping the JSON well-formed so the failure is semantic, not a
    parse error. Fallback: replace the answer with a marker, which no
    meaningful check accepts.
    """
    digest = hashlib.sha256(output.encode()).hexdigest()[:16]
    fields = next((c.get("expected") for c in checks if c.get("type") == "json_fields" and c.get("expected")), None)
    if fields:
        data, err = parse_json_output(output)
        if not err:
            path, expected = next(iter(fields.items()))
            wrong = _wrong(expected)
            if _set_path(data, path, wrong):
                return json.dumps(data), {
                    "kind": "corrupt_candidate", "mutation": "field_value", "path": path,
                    "expected": expected, "injected_value": wrong, "original_sha256_16": digest,
                }
    return MARKER, {"kind": "corrupt_candidate", "mutation": "replace_output", "original_sha256_16": digest}
