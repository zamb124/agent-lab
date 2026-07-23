"""Property-based fuzz tests for code contract scanner."""

from hypothesis import given, settings
from hypothesis import strategies as st

import core.code_contract.scanner as scanner_module
from core.code_contract import scan_code_contract

_LANGUAGES = st.sampled_from(
    ["python", "py", "javascript", "typescript", "js", "ts", "go", "golang", "csharp", "cs", "unknown"]
)


@settings(max_examples=200, deadline=None)
@given(_LANGUAGES, st.text(max_size=2000))
def test_scan_never_crashes(language: str, code: str) -> None:
    contract = scan_code_contract(language, code)
    assert contract.reads == sorted(set(contract.reads))
    assert contract.optional_reads == sorted(set(contract.optional_reads))
    assert contract.writes == sorted(set(contract.writes))
    assert contract.variable_writes == sorted(set(contract.variable_writes))
    assert contract.return_keys == sorted(set(contract.return_keys))


@settings(max_examples=100, deadline=None)
@given(_LANGUAGES, st.text(max_size=2000))
def test_empty_or_whitespace_code_is_empty_contract(language: str, whitespace: str) -> None:
    if whitespace.strip():
        return
    contract = scan_code_contract(language, whitespace)
    assert contract.reads == []
    assert contract.optional_reads == []
    assert contract.writes == []
    assert contract.variable_writes == []
    assert contract.return_keys == []


@settings(max_examples=50, deadline=None)
@given(st.text(min_size=1, max_size=200))
def test_cache_is_idempotent(code: str) -> None:
    scanner_module._CACHE.clear()
    first = scan_code_contract("python", code)
    second = scan_code_contract("python", code)
    assert first == second
