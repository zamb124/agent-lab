"""Prompt-переменные employee-run: `employee_*` из актора, `user_*` из инициатора.

Чистые функции `request_context_variables` + композиция как в `channels/base.py`.
"""

from __future__ import annotations

from apps.flows.src.channels.request_context_variables import (
    flow_employee_variables_from_user,
    flow_user_identity_overrides,
    flow_variables_from_request_context,
)
from core.models.context_models import Context
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company


def _ctx(user: User) -> Context:
    return Context(
        user=user,
        host="test",
        session_id="s",
        channel="a2a",
        active_company=make_test_company(company_id="system", name="System"),
        active_namespace="default",
    )


def _employee_user() -> User:
    return User(
        user_id="flow_employee_f1",
        name="AI Worker",
        emails=["worker@bot.local"],
        first_name="AI",
    )


def _initiator_user() -> User:
    return User(
        user_id="human_42",
        name="Human Person",
        emails=["human@corp.com"],
        first_name="Human",
        last_name="Person",
    )


def test_regular_flow_has_only_initiator_vars():
    human = _initiator_user()
    variables = flow_variables_from_request_context(_ctx(human))
    assert variables["user_id"] == "human_42"
    assert variables["user_name"] == "Human Person"
    assert not any(key.startswith("employee_") for key in variables)


def test_employee_run_has_employee_and_initiator_vars():
    employee = _employee_user()
    initiator = _initiator_user()

    # база берётся от актора (сотрудника) через контекст исполнения
    variables = flow_variables_from_request_context(_ctx(employee))
    # employee_* — из актора
    variables.update(flow_employee_variables_from_user(employee))
    # user_* — из инициатора (собеседника)
    variables.update(flow_user_identity_overrides(initiator))

    assert variables["employee_id"] == "flow_employee_f1"
    assert variables["employee_name"] == "AI Worker"
    assert variables["employee_email"] == "worker@bot.local"

    assert variables["user_id"] == "human_42"
    assert variables["user_name"] == "Human Person"
    assert variables["user_email"] == "human@corp.com"

    # employee_* и user_* различны
    assert variables["employee_id"] != variables["user_id"]
