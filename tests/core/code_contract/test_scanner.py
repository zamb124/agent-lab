import core.code_contract.scanner as scanner_module
from core.code_contract import scan_code_contract


def test_scan_python_detects_state_writes_and_return_keys():
    code = """
async def run(args, state):
    state.result_value = 1
    state["nested_key"] = args["x"]
    return {"answer": 42, "ok": True}
"""
    contract = scan_code_contract("python", code)

    assert "result_value" in contract.writes
    assert "nested_key" in contract.writes
    assert contract.return_keys == ["answer", "ok"]


def test_scan_python_detects_state_reads():
    code = """
async def run(args, state):
    x = state.count
    y = state["label"]
    return {"ok": x + y}
"""
    contract = scan_code_contract("python", code)

    assert "count" in contract.reads
    assert "label" in contract.reads


def test_scan_python_state_update_writes():
    code = "async def run(a, state):\n    state.update({'merged': 1})\n    return {}"
    contract = scan_code_contract("python", code)

    assert "merged" in contract.writes


def test_scan_python_falls_back_to_regex_on_syntax_error():
    code = "state.broken = ( this is not valid python"
    contract = scan_code_contract("python", code)

    assert "broken" in contract.writes


def test_scan_javascript_detects_state_writes_and_return_keys():
    code = """
async function run(args, state) {
    state.count = 5;
    state["label"] = args.label;
    return { answer: 42, ok: true };
}
"""
    contract = scan_code_contract("javascript", code)

    assert "count" in contract.writes
    assert "label" in contract.writes
    assert "answer" in contract.return_keys
    assert "ok" in contract.return_keys


def test_scan_typescript_alias():
    code = 'state.total += 1;\nreturn { done: true };'
    contract = scan_code_contract("typescript", code)

    assert "total" in contract.writes
    assert "done" in contract.return_keys


def test_scan_go_detects_state_writes():
    code = """
func Run(args map[string]any, state map[string]any) map[string]any {
    state["total"] = 10
    return map[string]any{}
}
"""
    contract = scan_code_contract("go", code)

    assert "total" in contract.writes


def test_scan_go_alias_golang():
    contract = scan_code_contract("golang", 'state["x"] = 1')

    assert "x" in contract.writes


def test_scan_csharp_detects_state_writes():
    code = """
public object Run(dynamic args, dynamic state) {
    state.Score = 7;
    return new { answer = 1 };
}
"""
    contract = scan_code_contract("csharp", code)

    assert "Score" in contract.writes
    assert "answer" in contract.return_keys


def test_scan_csharp_alias_cs():
    contract = scan_code_contract("cs", "state.Value = 3;\nreturn new { ok = true };")

    assert "Value" in contract.writes
    assert "ok" in contract.return_keys


def test_scan_unknown_language_uses_c_like():
    contract = scan_code_contract("brainfuck", 'state.foo = 1')

    assert "foo" in contract.writes


def test_scan_empty_code_returns_empty_contract():
    contract = scan_code_contract("python", "")

    assert contract.reads == []
    assert contract.writes == []
    assert contract.return_keys == []


def test_scan_whitespace_code_returns_empty_contract():
    contract = scan_code_contract("python", "   \n  ")

    assert contract.reads == []
    assert contract.writes == []
    assert contract.return_keys == []


def test_scan_cache_returns_same_contract():
    code = "state.cached = 1"
    first = scan_code_contract("python", code)
    second = scan_code_contract("python", code)

    assert first == second


def test_scan_cache_eviction_does_not_break_scanner():
    scanner_module._CACHE.clear()
    for idx in range(scanner_module._CACHE_MAX + 5):
        contract = scan_code_contract("python", f"state.field_{idx} = {idx}")
        assert f"field_{idx}" in contract.writes
