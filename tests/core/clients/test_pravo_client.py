"""
Тесты core.clients.pravo (без сети: только нормализация и разбор ответов).
"""

import pytest

from core.clients.pravo import PravoCatalogHit, PravoClient, PravoClientError


H64 = "007c57b8a5c11e0eb8e77ae8e75586909c5a0e5fb9ab0d295b8acc3344ac4ccf"


def test_extract_hash_standalone() -> None:
    assert PravoClient.extract_legislation_document_hash(H64.upper()) == H64


def test_extract_hash_from_https_url() -> None:
    u = f"https://ips.pravo.gov.ru/api/ips/legislation/document?baseid=None&hash={H64}"
    assert PravoClient.extract_legislation_document_hash(u) == H64


def test_extract_hash_protocol_relative() -> None:
    u = f"//ips.pravo.gov.ru/api/ips/legislation/document?baseid=None&hash={H64}"
    assert PravoClient.extract_legislation_document_hash(u) == H64


def test_extract_hash_rejects_wrong_host() -> None:
    with pytest.raises(ValueError, match="Ожидается хост"):
        PravoClient.extract_legislation_document_hash(
            f"https://example.com/api/ips/legislation/document?hash={H64}",
        )


def test_legislation_document_api_url() -> None:
    assert PravoClient.legislation_document_api_url(H64) == (
        f"http://ips.pravo.gov.ru/api/ips/legislation/document?baseid=None&hash={H64}"
    )


def test_rag_document_id_stable() -> None:
    a = PravoClient.rag_document_id(H64)
    b = PravoClient.rag_document_id(H64)
    assert a == b
    assert len(a) == 32


def test_format_hybrid_search_query() -> None:
    assert PravoClient._format_hybrid_search_query("гражданский кодекс") == "гражданский&кодекс"


def test_coerce_ips_search_limit() -> None:
    assert PravoClient._coerce_ips_search_limit(20) == 20
    assert PravoClient._coerce_ips_search_limit(7) == 20


def test_hits_from_search_json_docs() -> None:
    body = {
        "page": 1,
        "pageSize": 10,
        "docs": [
            {
                "hash": H64,
                "name": "Тестовое название",
                "adoption": "Федеральный закон …",
            },
        ],
    }
    hits = PravoClient._hits_from_search_json(body)
    assert len(hits) == 1
    assert hits[0].document_hash == H64
    assert hits[0].title == "Тестовое название"
    assert hits[0].url == PravoClient.legislation_document_api_url(H64)


def test_hits_from_search_json_error_status() -> None:
    with pytest.raises(PravoClientError, match="Поиск IPS"):
        PravoClient._hits_from_search_json({"status": 400, "error": "bad"})


def test_pravo_catalog_hit_structure() -> None:
    h = PravoCatalogHit(
        title="t",
        url=f"http://ips.pravo.gov.ru/api/ips/legislation/document?baseid=None&hash={H64}",
        document_hash=H64,
    )
    assert h.title == "t"
