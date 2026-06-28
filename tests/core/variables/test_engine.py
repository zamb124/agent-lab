"""Контракт ResolutionEngine: scoped overrides, expression, @var/@ctx, цикл, missing.

Чистый движок без хранилища: на вход — определения PlatformVariable + ResolutionContext,
на выход — плоский map значений. Проверяем сам алгоритм резолва (Zero-Guess: цикл/missing → raise).
"""

from __future__ import annotations

import pytest

from core.variables.engine import ResolutionEngine, VariableCycleError
from core.variables.models import (
    PlatformVariable,
    ResolutionContext,
    ScopeCondition,
    ScopeField,
    ScopeOp,
    VariableScopeOverride,
    VariableValueKind,
    VariableValuePayload,
    VariableValueSpec,
)
from core.variables.resolver import VariableResolutionError


def _static(key: str, value: object, *, scopes: list[VariableScopeOverride] | None = None) -> PlatformVariable:
    return PlatformVariable(
        variable_key=key,
        company_id="acme",
        payload=VariableValuePayload(
            base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value=value),
            scopes=scopes or [],
        ),
    )


def test_static_value_resolves_unchanged() -> None:
    ctx = ResolutionContext(company_id="acme")
    result = ResolutionEngine.resolve([_static("greeting", "hello")], ctx)
    assert result["greeting"] == "hello"


def test_scope_override_by_user_id_wins_over_base() -> None:
    # Один flow — разное значение в зависимости от user_id исполнителя.
    var = _static(
        "tier",
        "free",
        scopes=[
            VariableScopeOverride(
                value_kind=VariableValueKind.STATIC,
                value="pro",
                priority=10,
                match=[ScopeCondition(field=ScopeField.USER_ID, op=ScopeOp.EQ, value="u-pro")],
            )
        ],
    )
    pro = ResolutionEngine.resolve([var], ResolutionContext(company_id="acme", user_id="u-pro"))
    free = ResolutionEngine.resolve([var], ResolutionContext(company_id="acme", user_id="u-other"))
    assert pro["tier"] == "pro"
    assert free["tier"] == "free"


def test_scope_override_by_namespace_eq() -> None:
    var = _static(
        "region",
        "global",
        scopes=[
            VariableScopeOverride(
                value="eu",
                priority=5,
                match=[ScopeCondition(field=ScopeField.NAMESPACE, op=ScopeOp.EQ, value="eu-team")],
            )
        ],
    )
    eu = ResolutionEngine.resolve([var], ResolutionContext(company_id="acme", namespace="eu-team"))
    other = ResolutionEngine.resolve([var], ResolutionContext(company_id="acme", namespace="us-team"))
    assert eu["region"] == "eu"
    assert other["region"] == "global"


def test_highest_priority_matching_override_wins() -> None:
    var = _static(
        "plan",
        "base",
        scopes=[
            VariableScopeOverride(
                value="low",
                priority=1,
                match=[ScopeCondition(field=ScopeField.COMPANY_ID, op=ScopeOp.EQ, value="acme")],
            ),
            VariableScopeOverride(
                value="high",
                priority=100,
                match=[ScopeCondition(field=ScopeField.COMPANY_ID, op=ScopeOp.EQ, value="acme")],
            ),
        ],
    )
    result = ResolutionEngine.resolve([var], ResolutionContext(company_id="acme"))
    assert result["plan"] == "high"


def test_var_dependency_resolves_in_topological_order() -> None:
    # base_url зависит от host через @var: — порядок определяется топосортом.
    host = _static("host", "api.example.com")
    base_url = _static("base_url", "https://@var:host/v1")
    result = ResolutionEngine.resolve([base_url, host], ResolutionContext(company_id="acme"))
    assert result["base_url"] == "https://api.example.com/v1"


def test_ctx_token_substitutes_context_field() -> None:
    var = _static("who", "user-@ctx:user_id")
    result = ResolutionEngine.resolve([var], ResolutionContext(company_id="acme", user_id="u-7"))
    assert result["who"] == "user-u-7"


def test_expression_kind_renders_refs() -> None:
    token = _static("token", "secret-abc")
    header = PlatformVariable(
        variable_key="auth_header",
        company_id="acme",
        payload=VariableValuePayload(
            base=VariableValueSpec(
                value_kind=VariableValueKind.EXPRESSION,
                expression="Bearer @var:token",
            )
        ),
    )
    result = ResolutionEngine.resolve([header, token], ResolutionContext(company_id="acme"))
    assert result["auth_header"] == "Bearer secret-abc"


def test_scope_condition_by_other_var_value() -> None:
    # Значение переменной зависит от значения другой переменной (field=var).
    mode = _static("mode", "premium")
    var = _static(
        "limit",
        "100",
        scopes=[
            VariableScopeOverride(
                value="unlimited",
                priority=10,
                match=[ScopeCondition(field=ScopeField.VAR, op=ScopeOp.EQ, ref_key="mode", value="premium")],
            )
        ],
    )
    result = ResolutionEngine.resolve([var, mode], ResolutionContext(company_id="acme"))
    assert result["limit"] == "unlimited"


def test_cycle_raises() -> None:
    a = _static("a", "@var:b")
    b = _static("b", "@var:a")
    with pytest.raises(VariableCycleError):
        ResolutionEngine.resolve([a, b], ResolutionContext(company_id="acme"))


def test_missing_reference_raises() -> None:
    var = _static("x", "@var:nonexistent")
    with pytest.raises(VariableResolutionError):
        ResolutionEngine.resolve([var], ResolutionContext(company_id="acme"))


def test_seed_visible_as_var_dependency() -> None:
    # identity/system переменные приходят как seed и видны зависимостям.
    var = _static("welcome", "Hi @var:user_name")
    result = ResolutionEngine.resolve(
        [var],
        ResolutionContext(company_id="acme"),
        seed={"user_name": "Alice"},
    )
    assert result["welcome"] == "Hi Alice"
