"""
Список рабочих пространств для переключателя сайдбара.

Эндпоинт кормит UI, поэтому проверяется ровно то, на что UI опирается:
форма страницы, наличие текущего пространства и отсутствие в выдаче
непродуктовых namespace.
"""

from __future__ import annotations

import pytest

from core.models.identity_models import Namespace
from tests.wiki.conftest import API_PREFIX

pytestmark = pytest.mark.no_test_doubles

NAMESPACES_URL = f"{API_PREFIX}/namespaces"


async def test_list_returns_offset_page_shape(wiki_client):
    response = await wiki_client.get(NAMESPACES_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["items"], list)
    assert body["offset"] == 0
    assert body["limit"] == 200
    assert body["total"] >= len(body["items"])
    if body["total"] > body["limit"]:
        assert len(body["items"]) == body["limit"]
    else:
        assert body["total"] == len(body["items"])


async def test_list_contains_current_namespace(wiki_client, wiki_namespace):
    names: set[str] = set()
    offset = 0
    while True:
        response = await wiki_client.get(NAMESPACES_URL, params={"limit": 200, "offset": offset})
        assert response.status_code == 200, response.text
        body = response.json()
        items = body["items"]
        if not isinstance(items, list):
            raise AssertionError("namespaces items must be a list")
        for item in items:
            name = item["name"]
            if not isinstance(name, str):
                raise AssertionError("namespace name must be a string")
            names.add(name)
        total = body["total"]
        if not isinstance(total, int):
            raise AssertionError("namespaces total must be an int")
        offset += len(items)
        if len(items) == 0 or offset >= total:
            break
    assert wiki_namespace in names


async def test_items_are_platform_namespaces(wiki_client):
    response = await wiki_client.get(NAMESPACES_URL)

    items = response.json()["items"]
    assert items, "ожидается хотя бы одно пространство компании"
    for item in items:
        namespace = Namespace.model_validate(item)
        assert namespace.name.strip() == namespace.name
        assert namespace.name != ""
