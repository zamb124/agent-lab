"""Тесты публичных юридических страниц и данных policy/terms."""

from __future__ import annotations

import pytest

from core.middleware.auth.route_config import RouteMatcher


@pytest.mark.asyncio
async def test_policy_and_terms_pages_are_public(frontend_client) -> None:
    """Страницы /policy и /terms доступны без авторизации."""
    policy_response = await frontend_client.get("/policy")
    terms_response = await frontend_client.get("/terms")

    assert policy_response.status_code == 200
    assert terms_response.status_code == 200
    assert "<!DOCTYPE html>" in policy_response.text
    assert "<!DOCTYPE html>" in terms_response.text


@pytest.mark.asyncio
async def test_policy_and_terms_accept_ru_query(frontend_client) -> None:
    """Юридические страницы корректно открываются с ?lang=ru."""
    policy_response = await frontend_client.get("/policy?lang=ru")
    terms_response = await frontend_client.get("/terms?lang=ru")

    assert policy_response.status_code == 200
    assert terms_response.status_code == 200


@pytest.mark.asyncio
async def test_public_legal_endpoint_is_available_without_auth(frontend_client) -> None:
    """Публичный endpoint legal возвращает реквизиты без JWT."""
    response = await frontend_client.get("/api/public/legal")
    assert response.status_code == 200

    payload = response.json()
    required_fields = {
        "company_name_ru",
        "company_name_en",
        "legal_form_ru",
        "legal_form_en",
        "contact_email",
        "support_email",
        "dpo_email",
        "legal_address_ru",
        "legal_address_en",
        "min_age",
    }
    assert required_fields.issubset(payload.keys())


@pytest.mark.asyncio
async def test_frontend_prefixed_public_legal_endpoint(frontend_client) -> None:
    """Префиксный frontend endpoint legal также доступен публично."""
    response = await frontend_client.get("/frontend/api/public/legal")
    assert response.status_code == 200
    payload = response.json()
    assert payload["company_name_en"]
    assert payload["company_name_ru"]


@pytest.mark.asyncio
async def test_i18n_en_contains_legal_namespaces(frontend_client) -> None:
    """EN переводы содержат актуальные namespaces privacy/terms."""
    response = await frontend_client.get("/api/i18n/en")
    assert response.status_code == 200

    payload = response.json()
    assert "privacy" in payload
    assert "terms" in payload
    assert payload["privacy"]["title"] == "Privacy Policy"
    assert payload["terms"]["title"] == "Terms of Service"
    assert "updated_at" in payload["privacy"]
    assert "updated_at" in payload["terms"]
    assert "section_1" in payload["privacy"]
    assert "section_1" in payload["terms"]


@pytest.mark.asyncio
async def test_i18n_ru_contains_legal_namespaces(frontend_client) -> None:
    """RU переводы содержат актуальные namespaces privacy/terms."""
    response = await frontend_client.get("/api/i18n/ru")
    assert response.status_code == 200

    payload = response.json()
    assert "privacy" in payload
    assert "terms" in payload
    assert payload["privacy"]["title"] == "Политика конфиденциальности"
    assert payload["terms"]["title"] == "Пользовательское соглашение"
    assert "updated_at" in payload["privacy"]
    assert "updated_at" in payload["terms"]
    assert "section_1" in payload["privacy"]
    assert "section_1" in payload["terms"]


def test_route_matcher_marks_legal_pages_as_anonymous() -> None:
    """Auth route config не требует авторизацию для policy/terms."""
    matcher = RouteMatcher()

    for path in ("/policy", "/terms"):
        rule = matcher.match(path)
        assert rule is not None, f"No route rule for {path}"
        assert rule.context_type == "anonymous"
        assert rule.auth_required is False


def test_route_matcher_marks_public_legal_api_as_anonymous() -> None:
    """Auth route config не требует авторизацию для legal API."""
    matcher = RouteMatcher()

    for path in ("/api/public/legal", "/frontend/api/public/legal"):
        rule = matcher.match(path)
        assert rule is not None, f"No route rule for {path}"
        assert rule.context_type == "anonymous"
        assert rule.auth_required is False
