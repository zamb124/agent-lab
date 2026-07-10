"""Property-based fuzz tests for prompt template scanner."""

from hypothesis import given, settings
from hypothesis import strategies as st

from core.variables import scan_prompt_template
from core.variables.template_scan import _SYSTEM_TEMPLATE_VARIABLES

_SYSTEM_SAMPLE = st.sampled_from(sorted(_SYSTEM_TEMPLATE_VARIABLES))
_IDENT = st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,12}", fullmatch=True)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=500))
def test_scan_never_crashes(template: str) -> None:
    result = scan_prompt_template(template)
    assert isinstance(result.refs, list)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=300))
def test_required_roots_subset_of_all_roots(template: str) -> None:
    result = scan_prompt_template(template)
    optional = set(result.optional_roots)
    for root in result.required_roots:
        assert root not in _SYSTEM_TEMPLATE_VARIABLES
        assert root not in optional


@settings(max_examples=100, deadline=None)
@given(
    st.lists(_IDENT, min_size=1, max_size=5, unique=True),
    st.lists(_IDENT, min_size=0, max_size=3, unique=True),
    _SYSTEM_SAMPLE,
)
def test_scan_for_loop_excludes_bound_var(required_vars: list[str], optional_vars: list[str], system_var: str) -> None:
    loop_var = "item"
    list_name = "items"
    body = " ".join(f"{{{name}}}" for name in required_vars)
    template = f"{{for {loop_var} in {list_name}}}{body}{{endfor}} {{{system_var}}}"
    result = scan_prompt_template(template)
    assert loop_var not in result.required_roots
    assert loop_var not in result.optional_roots
    assert system_var not in result.required_roots
