"""Deterministic output validators.

Each check returns an EvalResult. Checks are composable: a workload's
`checks` list is evaluated in order and all must pass. Deterministic checks
are preferred; the optional model judge lives in judge.py and its scores are
labelled as estimates.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import jsonschema

from app.evaluation.code_runner import run_python_tests


@dataclass
class EvalResult:
    passed: bool
    method: str
    detail: str
    score: float | None = None  # 0..1 when meaningful
    failures: list[str] = field(default_factory=list)
    structural_failure: bool = False  # e.g. unparseable JSON — eligible for repair

    def as_dict(self) -> dict:
        return {
            "passed": self.passed, "method": self.method, "detail": self.detail,
            "score": self.score, "failures": self.failures, "structural_failure": self.structural_failure,
        }


_FENCE_RE = re.compile(r"```(?:json|python|py)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_block(text: str) -> str:
    """Return the first fenced block if present, else the stripped text."""
    m = _FENCE_RE.search(text or "")
    return (m.group(1) if m else (text or "")).strip()


def parse_json_output(text: str) -> tuple[object | None, str | None]:
    candidate = extract_block(text)
    try:
        return json.loads(candidate), None
    except json.JSONDecodeError as exc:
        # Tolerate leading/trailing prose around a single JSON object/array.
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = candidate.find(opener), candidate.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(candidate[start : end + 1]), None
                except json.JSONDecodeError:
                    pass
        return None, f"invalid JSON: {exc.msg} at line {exc.lineno} col {exc.colno}"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower()).strip(" .!\"'`")


def _get_path(obj: object, path: str) -> object:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def _values_equal(actual: object, expected: object, tol: float = 1e-6) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual == expected
    if isinstance(expected, (int, float)):
        try:
            return abs(float(actual) - float(expected)) <= max(tol, abs(float(expected)) * 1e-6)
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str):
        return isinstance(actual, (str, int, float)) and _norm(str(actual)) == _norm(expected)
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_values_equal(a, e) for a, e in zip(actual, expected))
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(_values_equal(actual.get(k), v) for k, v in expected.items())
    return actual == expected


_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*(?:e-?\d+)?", re.IGNORECASE)


def _final_number(text: str) -> float | None:
    """Prefer an explicit 'Answer: X' line, else the last number in the text."""
    m = re.search(r"answer\s*[:=]\s*\**\s*(-?\$?[\d,]*\.?\d+)", text, re.IGNORECASE)
    raw = m.group(1) if m else None
    if raw is None:
        nums = _NUM_RE.findall(text)
        raw = nums[-1] if nums else None
    if raw is None:
        return None
    try:
        return float(raw.replace(",", "").replace("$", ""))
    except ValueError:
        return None


def run_check(output: str, check: dict, *, code_execution: bool = True) -> EvalResult:
    kind = check.get("type")

    if kind == "json_schema":
        data, err = parse_json_output(output)
        if err:
            return EvalResult(False, "json_schema", err, 0.0, [err], structural_failure=True)
        try:
            jsonschema.validate(data, check["schema"])
        except jsonschema.ValidationError as exc:
            path = "/".join(str(p) for p in exc.absolute_path) or "(root)"
            msg = f"schema violation at {path}: {exc.message[:160]}"
            return EvalResult(False, "json_schema", msg, 0.0, [msg], structural_failure=True)
        return EvalResult(True, "json_schema", "valid JSON matching schema", 1.0)

    if kind == "json_fields":
        data, err = parse_json_output(output)
        if err:
            return EvalResult(False, "json_fields", err, 0.0, [err], structural_failure=True)
        failures = []
        expected: dict = check.get("expected", {})
        for path, value in expected.items():
            actual = _get_path(data, path)
            if not _values_equal(actual, value, check.get("tolerance", 1e-6)):
                failures.append(f"{path}: expected {value!r}, got {actual!r}")
        ok = not failures
        score = 1 - len(failures) / max(1, len(expected))
        return EvalResult(ok, "json_fields", "all fields match" if ok else "; ".join(failures)[:400], score, failures)

    if kind == "exact":
        candidates = [check["answer"], *check.get("aliases", [])]
        text = extract_block(output)
        last_line = text.strip().splitlines()[-1] if text.strip() else ""
        ok = any(_norm(text) == _norm(c) or _norm(last_line) == _norm(c) for c in candidates)
        return EvalResult(ok, "exact_match", "exact match" if ok else f"expected {check['answer']!r}", 1.0 if ok else 0.0)

    if kind == "label":
        labels = [_norm(l) for l in check["labels"]]
        target = _norm(check["answer"])
        text = _norm(extract_block(output))
        found = [l for l in labels if re.search(rf"\b{re.escape(l)}\b", text)]
        ok = found == [target] or text == target
        detail = "correct label" if ok else f"expected {check['answer']!r}, found {found or 'no label'}"
        return EvalResult(ok, "label_match", detail, 1.0 if ok else 0.0)

    if kind == "numeric":
        value = _final_number(output)
        expected_num = float(check["answer"])
        tol = float(check.get("tolerance", 0.01))
        ok = value is not None and abs(value - expected_num) <= tol
        return EvalResult(ok, "numeric", f"got {value}, expected {expected_num} ±{tol}", 1.0 if ok else 0.0)

    if kind == "contains_all":
        text = _norm(output)
        missing = [t for t in check["terms"] if _norm(t) not in text]
        ok = not missing
        return EvalResult(ok, "contains_all", "all required terms present" if ok else f"missing: {missing}", 1 - len(missing) / len(check["terms"]), missing)

    if kind == "excludes":
        text = _norm(output)
        present = [t for t in check["terms"] if _norm(t) in text]
        ok = not present
        return EvalResult(ok, "excludes", "no forbidden terms" if ok else f"contains forbidden: {present}", 1.0 if ok else 0.0, present)

    if kind == "word_limit":
        words = len(extract_block(output).split())
        lo, hi = check.get("min", 0), check.get("max", 10**9)
        ok = lo <= words <= hi
        return EvalResult(ok, "word_limit", f"{words} words (allowed {lo}-{hi})", 1.0 if ok else 0.0, structural_failure=not ok)

    if kind == "bullet_count":
        lines = [l for l in output.splitlines() if re.match(r"^\s*([-*•]|\d+[.)])\s+", l)]
        ok = len(lines) == check["count"]
        return EvalResult(ok, "bullet_count", f"{len(lines)} bullets (expected {check['count']})", 1.0 if ok else 0.0, structural_failure=not ok)

    if kind == "regex":
        ok = re.search(check["pattern"], output, re.IGNORECASE | re.MULTILINE) is not None
        return EvalResult(ok, "regex", "pattern matched" if ok else f"pattern {check['pattern']!r} not found", 1.0 if ok else 0.0)

    if kind == "python_tests":
        if not code_execution:
            return EvalResult(False, "python_tests", "code execution disabled on this deployment", None, ["disabled"])
        code = extract_block(output)
        res = run_python_tests(code, check["tests"], entrypoint=check.get("entrypoint"))
        return EvalResult(res.passed, "python_tests", res.detail, res.fraction, res.failures, structural_failure=res.syntax_error)

    return EvalResult(False, "unknown", f"unknown check type {kind!r}", 0.0, [f"unknown check {kind}"])


def evaluate(output: str, checks: list[dict], *, code_execution: bool = True) -> EvalResult:
    """Run all checks; overall pass requires every check to pass."""
    if not checks:
        return EvalResult(True, "none", "no objective checks defined — output accepted unverified", None)
    results = [run_check(output, c, code_execution=code_execution) for c in checks]
    passed = all(r.passed for r in results)
    scores = [r.score for r in results if r.score is not None]
    failures = [f"{r.method}: {r.detail}" for r in results if not r.passed]
    return EvalResult(
        passed=passed,
        method="+".join(dict.fromkeys(r.method for r in results)),
        detail="all checks passed" if passed else " | ".join(failures)[:600],
        score=sum(scores) / len(scores) if scores else None,
        failures=failures,
        structural_failure=any(r.structural_failure for r in results if not r.passed),
    )
