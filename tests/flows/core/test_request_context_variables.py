"""Переменные flow из Context (JWT → user / company)."""

from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus
from core.models.i18n_models import Language

from apps.flows.src.channels.request_context_variables import flow_variables_from_request_context


def test_none_context():
    assert flow_variables_from_request_context(None) == {}


def test_flow_variables_from_request_context():
    user = User(
        user_id="u_1",
        name="Alex",
        first_name="Alex",
        last_name="Test",
        status=UserStatus.ACTIVE,
        emails=["a@example.com", "b@example.com"],
        active_company_id="c1",
    )
    company = Company(company_id="c1", name="Acme")
    ctx = Context(
        user=user,
        host="localhost",
        channel="a2a",
        active_company=company,
        active_namespace="sales",
        language=Language.EN,
    )
    v = flow_variables_from_request_context(ctx)
    assert v["user_id"] == "u_1"
    assert v["user_name"] == "Alex"
    assert v["user_email"] == "a@example.com"
    assert v["user_first_name"] == "Alex"
    assert v["user_last_name"] == "Test"
    assert v["company_id"] == "c1"
    assert v["company_name"] == "Acme"
    assert v["active_namespace"] == "sales"
    assert v["user_language"] == "en"
    assert v["interface_language_code"] == "en"
    assert v["interface_language_name"] == "английском"
