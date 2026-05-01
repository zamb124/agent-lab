"""
Тесты core.clients.pravo (без сети: только нормализация и разбор HTML).
"""

import pytest

from core.clients.pravo import PravoClient


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
        f"https://ips.pravo.gov.ru/api/ips/legislation/document?baseid=None&hash={H64}"
    )


def test_rag_document_id_stable() -> None:
    a = PravoClient.rag_document_id(H64)
    b = PravoClient.rag_document_id(H64)
    assert a == b
    assert len(a) == 32


def test_build_catalog_search_url_encodes_keyword() -> None:
    u = PravoClient._build_catalog_search_url(keyword="гражданский кодекс", page=2)
    assert "page=2" in u
    assert "search%5Boneof_lexemes%5D=" in u


def test_parse_catalog_search_html_links() -> None:
    h = f'''
    <html><body>
    <a href="/api/ips/legislation/document?baseid=None&hash={H64}">Постановление № 1</a>
    <a href="https://ips.pravo.gov.ru/api/ips/legislation/document?baseid=None&hash={H64}">Дубль</a>
    </body></html>
    '''
    hits = PravoClient._parse_catalog_search_html(h, page_base_url="https://ips.pravo.gov.ru/")
    assert len(hits) == 1
    assert hits[0].document_hash == H64
    assert hits[0].title == "Постановление № 1"
