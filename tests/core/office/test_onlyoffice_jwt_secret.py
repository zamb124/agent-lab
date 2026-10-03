"""Секрет OnlyOffice JWT читается через Settings, не через os.environ."""

import pytest

from core.office.jwt_secret import resolve_onlyoffice_jwt_secret


def test_onlyoffice_jwt_secret_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFICE__JWT_SECRET", "from-env-onlyoffice-secret")
    assert resolve_onlyoffice_jwt_secret() == "from-env-onlyoffice-secret"


def test_onlyoffice_jwt_secret_falls_back_to_office_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OFFICE__JWT_SECRET", raising=False)
    secret = resolve_onlyoffice_jwt_secret()
    assert secret.strip() != ""
