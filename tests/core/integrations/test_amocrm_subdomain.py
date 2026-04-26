"""Нормализация query subdomain для AmoCRM."""

import pytest

from core.integrations.providers.amocrm import normalize_amocrm_subdomain_query


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("suharevarendadacom", "suharevarendadacom"),
        ("  foo  ", "foo"),
        ("https://suharevarendadacom.amocrm.ru/", "suharevarendadacom"),
        ("https://suharevarendadacom.amocrm.ru", "suharevarendadacom"),
        ("suharevarendadacom.amocrm.ru", "suharevarendadacom"),
        ("https://bar.kommo.com/path", "bar"),
    ],
)
def test_normalize_amocrm_subdomain_query_ok(raw: str, expected: str) -> None:
    assert normalize_amocrm_subdomain_query(raw) == expected


def test_normalize_amocrm_subdomain_query_empty_raises() -> None:
    with pytest.raises(ValueError, match="пустой"):
        normalize_amocrm_subdomain_query("   ")
