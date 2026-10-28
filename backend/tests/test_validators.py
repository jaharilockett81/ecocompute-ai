from app.evaluation.code_runner import run_python_tests
from app.evaluation.validators import evaluate, parse_json_output, run_check


def test_invalid_json_fails_structurally():  # Acceptance test 3
    res = run_check('{"a": 1, b: 2', {"type": "json_schema", "schema": {"type": "object"}})
    assert not res.passed and res.structural_failure and "invalid JSON" in res.detail


def test_json_in_fence_and_prose_is_parsed():
    data, err = parse_json_output('Here you go:\n```json\n{"x": [1, 2]}\n```')
    assert err is None and data == {"x": [1, 2]}
    data, err = parse_json_output('Sure! {"y": true} hope that helps')
    assert data == {"y": True}


def test_schema_violation_reports_path():
    res = run_check('{"age": "old"}', {"type": "json_schema", "schema": {"type": "object", "properties": {"age": {"type": "integer"}}}})
    assert not res.passed and "age" in res.detail


def test_json_fields_dotted_paths_and_numbers():
    out = '{"total": "1274.4", "items": [{"sku": "A"}]}'
    res = run_check(out, {"type": "json_fields", "expected": {"total": 1274.40, "items.0.sku": "a"}})
    assert res.passed, res.detail


def test_numeric_prefers_answer_line():
    res = run_check("Step 1: 10 + 5 = 15\nAnswer: 2318", {"type": "numeric", "answer": 2318, "tolerance": 0})
    assert res.passed
    assert not run_check("I think 12", {"type": "numeric", "answer": 13, "tolerance": 0}).passed


def test_label_requires_single_correct_label():
    chk = {"type": "label", "labels": ["positive", "negative", "neutral"], "answer": "neutral"}
    assert run_check("Neutral", chk).passed
    assert not run_check("positive or neutral", chk).passed


def test_word_limit_and_bullets():
    assert run_check("one two three", {"type": "word_limit", "max": 3}).passed
    assert not run_check("one two three four", {"type": "word_limit", "max": 3}).passed
    assert run_check("- a\n- b\n- c", {"type": "bullet_count", "count": 3}).passed


def test_no_checks_is_unverified_not_passed_silently():
    res = evaluate("anything", [])
    assert res.method == "none" and res.score is None


def test_python_tests_pass_and_fail():
    good = "def add(a, b):\n    return a + b\n"
    assert run_python_tests(good, ["add(1, 2) == 3", "add(-1, 1) == 0"], "add").passed
    bad = "def add(a, b):\n    return a - b\n"
    r = run_python_tests(bad, ["add(1, 2) == 3"], "add")
    assert not r.passed and r.fraction == 0


def test_python_sandbox_rejects_dangerous_code():
    r = run_python_tests("import os\ndef f():\n    return os.listdir('/')", ["f() == []"], "f")
    assert not r.passed and "disallowed import" in r.detail
    r = run_python_tests("def f():\n    return open('/etc/passwd').read()", ["f()"], "f")
    assert not r.passed and "disallowed builtin" in r.detail


def test_python_infinite_loop_times_out():
    r = run_python_tests("def f():\n    while True:\n        pass", ["f()"], "f", timeout_s=3)
    assert not r.passed
