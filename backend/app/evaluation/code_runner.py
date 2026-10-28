"""Run model-generated Python against fixed unit tests in a constrained subprocess.

Defence in depth (this executes untrusted model output):
1. Static screen: reject imports/builtins that reach the OS, network or filesystem.
2. Separate interpreter in isolated mode (-I), empty environment, temp cwd.
3. POSIX resource limits: CPU seconds, address space, file size, process count.
4. Wall-clock timeout.
Only benchmark-defined tests are ever run; the playground cannot submit tests.
Deployments can disable this entirely with ECOCOMPUTE_ENABLE_CODE_EXECUTION=false.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "ctypes", "multiprocessing",
    "threading", "asyncio", "http", "urllib", "requests", "httpx", "importlib", "builtins",
    "signal", "resource", "pickle", "marshal", "inspect", "gc", "io", "tempfile", "glob",
}
FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint", "globals", "locals", "vars", "getattr", "setattr", "delattr"}


@dataclass
class CodeRunResult:
    passed: bool
    fraction: float
    detail: str
    failures: list[str] = field(default_factory=list)
    syntax_error: bool = False


def screen_code(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc.msg} (line {exc.lineno})"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                    return f"disallowed import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in FORBIDDEN_MODULES:
                return f"disallowed import: {node.module}"
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            return f"disallowed builtin: {node.id}"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr not in {"__init__", "__name__", "__len__", "__eq__", "__lt__", "__repr__", "__str__", "__iter__", "__next__", "__hash__", "__contains__", "__getitem__"}:
            return f"disallowed dunder access: {node.attr}"
    return None


_HARNESS = r'''
import json
_results = []
_ns = {}
try:
    exec(compile(_CODE, "<model>", "exec"), _ns)
except Exception as e:
    print(json.dumps({"load_error": type(e).__name__ + ": " + str(e)[:200]}))
    raise SystemExit(0)
for _t in _TESTS:
    try:
        _ok = bool(eval(_t, _ns))
        _results.append([_t, _ok, None])
    except Exception as e:
        _results.append([_t, False, type(e).__name__ + ": " + str(e)[:120]])
print(json.dumps({"results": _results}))
'''


def _limits() -> None:  # pragma: no cover - runs in child
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except Exception:
        pass


def run_python_tests(code: str, tests: list[str], entrypoint: str | None = None, timeout_s: float = 6.0) -> CodeRunResult:
    problem = screen_code(code)
    if problem:
        return CodeRunResult(False, 0.0, problem, [problem], syntax_error=problem.startswith("syntax"))
    if entrypoint and f"def {entrypoint}" not in code:
        msg = f"function {entrypoint!r} not defined"
        return CodeRunResult(False, 0.0, msg, [msg], syntax_error=True)

    script = f"_CODE = {json.dumps(code)}\n_TESTS = {json.dumps(tests)}\n" + _HARNESS
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", script],
                capture_output=True, text=True, timeout=timeout_s, cwd=tmp, env={},
                preexec_fn=_limits if sys.platform != "win32" else None,
            )
        except subprocess.TimeoutExpired:
            return CodeRunResult(False, 0.0, "timed out", ["timeout"])
    out = proc.stdout.strip().splitlines()
    if not out:
        return CodeRunResult(False, 0.0, f"no output (exit {proc.returncode}): {proc.stderr[-200:]}", ["crash"])
    try:
        payload = json.loads(out[-1])
    except json.JSONDecodeError:
        return CodeRunResult(False, 0.0, "unparseable harness output", ["harness"])
    if "load_error" in payload:
        return CodeRunResult(False, 0.0, payload["load_error"], [payload["load_error"]], syntax_error=True)
    results = payload["results"]
    failures = [f"{t} -> {err or 'False'}" for t, ok, err in results if not ok]
    passed_n = sum(1 for _, ok, _ in results if ok)
    frac = passed_n / max(1, len(results))
    return CodeRunResult(not failures, frac, f"{passed_n}/{len(results)} tests passed", failures)
