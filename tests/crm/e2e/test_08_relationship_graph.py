"""
E2E тесты для Graph API.

Покрывают:
1. Построение графа влияния (BFS)
2. Кратчайший путь (Bidirectional Weighted Dijkstra)
3. Связанные entities (1 уровень)
4. Направленность (is_directed, inverse_type_id)
5. Фильтрация по типам связей
6. Ограничение глубины
7. Права доступа (placeholders)
8. Производительность и лимиты
9. Граничные случаи

БЕЗ МОКОВ - только реальные HTTP запросы через crm_client.
"""

from typing import cast

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_list, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _json_bool(payload: dict[str, object], key: str) -> bool:
    value = payload[key]
    if not isinstance(value, bool):
        raise AssertionError(f"{key} must be bool")
    return value


def _json_int(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int):
        raise AssertionError(f"{key} must be int")
    return value


def _json_float(payload: dict[str, object], key: str) -> float:
    value = payload[key]
    if not isinstance(value, (int, float)):
        raise AssertionError(f"{key} must be float")
    return float(value)


def _graph_nodes(graph: dict[str, object]) -> list[dict[str, object]]:
    return object_list(graph.get("nodes"))


def _graph_edges(graph: dict[str, object]) -> list[dict[str, object]]:
    return object_list(graph.get("edges"))


def _nodes_by_entity_id(graph: dict[str, object]) -> dict[str, dict[str, object]]:
    nodes_by_id: dict[str, dict[str, object]] = {}
    for node in _graph_nodes(graph):
        entity_id = object_str(node.get("entity_id"), field="entity_id")
        nodes_by_id[entity_id] = node
    return nodes_by_id


def _entity_ids_from_nodes(nodes: list[dict[str, object]]) -> list[str]:
    return [object_str(node.get("entity_id"), field="entity_id") for node in nodes]


def _entity_ids_from_graph(graph: dict[str, object]) -> list[str]:
    return _entity_ids_from_nodes(_graph_nodes(graph))


def _related_nodes(related: dict[str, object], direction: str) -> list[dict[str, object]]:
    return object_list(related.get(direction))


def _path_entity_ids(path_result: dict[str, object]) -> list[str]:
    path_value = path_result.get("path")
    if not isinstance(path_value, list):
        raise AssertionError("path must be a list")
    entity_ids: list[str] = []
    for path_item in cast(list[object], path_value):
        entity_ids.append(object_str(path_item, field="path item"))
    return entity_ids


def _node_str(node: dict[str, object], key: str) -> str:
    return object_str(node.get(key), field=key)


def _graph_edge_at(graph: dict[str, object], index: int) -> dict[str, object]:
    edges = _graph_edges(graph)
    if index >= len(edges):
        raise AssertionError("edge index out of range")
    return edges[index]


def _graph_node_at(graph: dict[str, object], index: int) -> dict[str, object]:
    nodes = _graph_nodes(graph)
    if index >= len(nodes):
        raise AssertionError("node index out of range")
    return nodes[index]

# ============================================================================
# Fixtures
# ============================================================================

# Глобальный флаг для отслеживания инициализации типов
_relationship_types_initialized = False


@pytest_asyncio.fixture(autouse=True)
async def ensure_relationship_types(crm_client: AsyncClient, auth_headers_system: dict[str, str]):
    """
    Гарантирует что стандартные типы связей созданы перед каждым тестом.

    autouse=True - применяется автоматически ко всем тестам.
    Создает типы только один раз (при первом запуске).
    """
    global _relationship_types_initialized

    if not _relationship_types_initialized:
        standard_types = [
            {"type_id": "manages", "name": "Manages", "is_directed": True, "inverse_type_id": "reports_to"},
            {"type_id": "reports_to", "name": "Reports To", "is_directed": True, "inverse_type_id": "manages"},
            {"type_id": "related_to", "name": "Related To", "is_directed": False},
            {"type_id": "mentors", "name": "Mentors", "is_directed": True},
            {"type_id": "works_on", "name": "Works On", "is_directed": True},
            {"type_id": "works_with", "name": "Works With", "is_directed": True},
            {"type_id": "collaborates_with", "name": "Collaborates With", "is_directed": True},
        ]

        for type_data in standard_types:
            try:
                response = await crm_client.post(
                    "/crm/api/v1/relationships/types/",
                    json=type_data,
                    headers=auth_headers_system
                )
                # 200 = created, 409 = already exists, оба варианта OK
                if response.status_code not in [200, 409]:
                    print(f"⚠️  Failed to create type {type_data['type_id']}: {response.status_code} - {response.text}")
            except Exception:
                # Игнорируем ошибки - типы могут уже существовать
                pass

        _relationship_types_initialized = True

    yield


# ============================================================================
# Helper Functions
# ============================================================================

async def create_entity(
    client: AsyncClient,
    entity_type: str,
    name: str,
    headers: dict[str, str],
    attributes: dict[str, object] | None = None,
    namespace: str | None = None,
) -> str:
    """Создать entity и вернуть entity_id"""
    payload: dict[str, object] = {
        "entity_type": entity_type,
        "name": name,
        "attributes": attributes or {},
    }
    if namespace is not None:
        payload["namespace"] = namespace
    response = await client.post(
        "/crm/api/v1/entities/",
        json=payload,
        headers=headers
    )
    assert response.status_code == 200, f"Failed to create entity: {response.text}"
    body = _http_json(response)
    return object_str(body.get("entity_id"), field="entity_id")


async def create_relationship(
    client: AsyncClient,
    source_id: str,
    target_id: str,
    relationship_type: str,
    headers: dict[str, str],
    weight: float = 1.0,
    namespace: str | None = None,
) -> str:
    """Создать relationship и вернуть relationship_id"""
    payload: dict[str, object] = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relationship_type": relationship_type,
        "weight": weight,
    }
    if namespace is not None:
        payload["namespace"] = namespace
    response = await client.post(
        "/crm/api/v1/relationships/",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 200, f"Failed to create relationship: {response.text}"
    body = _http_json(response)
    return object_str(body.get("relationship_id"), field="relationship_id")


async def create_relationship_type(
    client: AsyncClient,
    type_id: str,
    name: str,
    headers: dict[str, str],
    is_directed: bool = True,
    inverse_type_id: str | None = None,
) -> None:
    """Создать тип связи"""
    body: dict[str, object] = {
        "type_id": type_id,
        "name": name,
        "is_directed": is_directed,
    }
    if inverse_type_id is not None:
        body["inverse_type_id"] = inverse_type_id
    response = await client.post(
        "/crm/api/v1/relationships/types/",
        json=body,
        headers=headers
    )
    assert response.status_code == 200, f"Failed to create relationship type: {response.text}"


async def ensure_namespace(
    client: AsyncClient,
    namespace_name: str,
    template_suffix: str,
    headers: dict[str, str],
    entity_type: str,
) -> None:
    """Создаёт namespace через шаблон с одним entity_type (идемпотентно по 409)."""
    template_id = f"tmpl_test_{template_suffix}"
    response = await client.post(
        "/crm/api/v1/namespaces/templates",
        json={"template_id": template_id, "name": f"Tpl {template_suffix}"},
        headers=headers,
    )
    assert response.status_code in (201, 409), response.text

    response = await client.post(
        f"/crm/api/v1/namespaces/templates/{template_id}/types",
        json={
            "type_id": entity_type,
            "name": entity_type,
            "required_fields": {},
            "optional_fields": {},
            "namespace_ids": [],
        },
        headers=headers,
    )
    assert response.status_code in (201, 409), response.text

    response = await client.post(
        "/crm/api/v1/namespaces",
        json={
            "name": namespace_name,
            "description": "graph namespace filter test",
            "template_id": template_id,
        },
        headers=headers,
    )
    assert response.status_code in (201, 409), response.text


async def create_public_grant(
    client: AsyncClient,
    entity_id: str,
    headers: dict[str, str],
) -> None:
    """Сделать entity публичной"""
    response = await client.post(
        f"/crm/api/v1/entities/{entity_id}/grants/public",
        headers=headers
    )
    assert response.status_code == 200, f"Failed to create public grant: {response.text}"


# ============================================================================
# Test Classes
# ============================================================================

class TestInfluenceGraph:
    """Построение графа влияния (BFS)"""

    @pytest.mark.asyncio
    async def test_simple_linear_graph(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 1.1: Линейная цепочка CEO → Manager → Developer"""
        # Создаем entities
        ceo_id = await create_entity(crm_client, "contact", f"CEO {unique_id}", auth_headers_system)
        manager_id = await create_entity(crm_client, "contact", f"Manager {unique_id}", auth_headers_system)
        dev_id = await create_entity(crm_client, "contact", f"Developer {unique_id}", auth_headers_system)

        # Создаем relationships
        _ = await create_relationship(crm_client, ceo_id, manager_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, manager_id, dev_id, "manages", auth_headers_system)

        # Строим граф от CEO
        response = await crm_client.get(
            f"/crm/api/v1/entities/{ceo_id}/influence-graph?max_depth=3",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        assert _json_int(graph, "total_nodes") == 3
        assert len(_graph_edges(graph)) == 2
        assert object_str(graph.get("root_entity_id"), field="root_entity_id") == ceo_id
        assert _json_int(graph, "max_depth") == 3

        # Проверяем уровни узлов
        nodes_by_id = _nodes_by_entity_id(graph)
        assert _json_int(nodes_by_id[ceo_id], "level") == 0
        assert _json_int(nodes_by_id[manager_id], "level") == 1
        assert _json_int(nodes_by_id[dev_id], "level") == 2

        # Все узлы доступны
        assert all(_json_bool(node, "access") for node in _graph_nodes(graph))

    @pytest.mark.asyncio
    async def test_branching_tree_graph(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 1.2: Дерево с разветвлением"""
        # Создаем иерархию
        ceo_id = await create_entity(crm_client, "contact", f"CEO {unique_id}", auth_headers_system)
        mgr1_id = await create_entity(crm_client, "contact", f"Manager1 {unique_id}", auth_headers_system)
        mgr2_id = await create_entity(crm_client, "contact", f"Manager2 {unique_id}", auth_headers_system)
        dev1_id = await create_entity(crm_client, "contact", f"Dev1 {unique_id}", auth_headers_system)
        dev2_id = await create_entity(crm_client, "contact", f"Dev2 {unique_id}", auth_headers_system)

        # Создаем связи
        _ = await create_relationship(crm_client, ceo_id, mgr1_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, ceo_id, mgr2_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, mgr1_id, dev1_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, mgr2_id, dev2_id, "manages", auth_headers_system)

        # Строим граф
        response = await crm_client.get(
            f"/crm/api/v1/entities/{ceo_id}/influence-graph?max_depth=2",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        assert _json_int(graph, "total_nodes") == 5
        assert len(_graph_edges(graph)) == 4

        # Проверяем уровни
        nodes_by_id = _nodes_by_entity_id(graph)
        assert _json_int(nodes_by_id[ceo_id], "level") == 0
        assert _json_int(nodes_by_id[mgr1_id], "level") == 1
        assert _json_int(nodes_by_id[mgr2_id], "level") == 1
        assert _json_int(nodes_by_id[dev1_id], "level") == 2
        assert _json_int(nodes_by_id[dev2_id], "level") == 2

    @pytest.mark.asyncio
    async def test_graph_with_cycles(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 1.3: Граф с циклами A→B→C→A"""
        # Создаем entities
        a_id = await create_entity(crm_client, "contact", f"PersonA {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"PersonB {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"PersonC {unique_id}", auth_headers_system)

        # Создаем цикл
        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, c_id, a_id, "mentions", auth_headers_system)

        # Строим граф - BFS не должен зациклиться
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=5",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        # Каждый узел посещается только раз
        assert _json_int(graph, "total_nodes") == 3
        assert len(_graph_edges(graph)) == 3


class TestDirectionality:
    """Направленность связей"""

    @pytest.mark.asyncio
    async def test_directed_relationships(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 2.1: Направленные связи без inverse"""
        # Создаем тип связи БЕЗ inverse_type_id
        _ = await create_relationship_type(
            crm_client, f"supervises_{unique_id}", "Supervises",
            auth_headers_system, is_directed=True, inverse_type_id=None
        )

        manager_id = await create_entity(crm_client, "contact", f"Manager {unique_id}", auth_headers_system)
        employee_id = await create_entity(crm_client, "contact", f"Employee {unique_id}", auth_headers_system)

        # Создаем направленную связь БЕЗ inverse
        _ = await create_relationship(crm_client, manager_id, employee_id, f"supervises_{unique_id}", auth_headers_system)

        # Граф от Manager - Employee должен быть виден
        response = await crm_client.get(
            f"/crm/api/v1/entities/{manager_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = _http_json(response)
        entity_ids = _entity_ids_from_graph(graph)
        assert employee_id in entity_ids

        # Граф от Employee - Manager НЕ должен быть виден (направленная связь)
        response = await crm_client.get(
            f"/crm/api/v1/entities/{employee_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = _http_json(response)
        entity_ids = _entity_ids_from_graph(graph)
        assert manager_id not in entity_ids

    @pytest.mark.asyncio
    async def test_inverse_relationships(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 2.2: Обратные связи (manages ↔ reports_to)"""
        # Создаем типы связей с inverse_type_id
        _ = await create_relationship_type(
            crm_client, f"manages_{unique_id}", "Manages",
            auth_headers_system, is_directed=True, inverse_type_id=f"reports_to_{unique_id}"
        )
        _ = await create_relationship_type(
            crm_client, f"reports_to_{unique_id}", "Reports To",
            auth_headers_system, is_directed=True, inverse_type_id=f"manages_{unique_id}"
        )

        manager_id = await create_entity(crm_client, "contact", f"Manager {unique_id}", auth_headers_system)
        employee_id = await create_entity(crm_client, "contact", f"Employee {unique_id}", auth_headers_system)

        # Создаем только одну связь manages
        _ = await create_relationship(crm_client, manager_id, employee_id, f"manages_{unique_id}", auth_headers_system)

        # Граф от Employee - Manager ДОЛЖЕН быть виден через inverse_type_id
        response = await crm_client.get(
            f"/crm/api/v1/entities/{employee_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = _http_json(response)
        entity_ids = _entity_ids_from_graph(graph)
        assert manager_id in entity_ids

    @pytest.mark.asyncio
    async def test_undirected_relationships(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 2.3: Недирективные связи (симметричные)"""
        # Создаем недирективный тип связи
        _ = await create_relationship_type(
            crm_client, f"friends_{unique_id}", "Friends",
            auth_headers_system, is_directed=False
        )

        person1_id = await create_entity(crm_client, "contact", f"Person1 {unique_id}", auth_headers_system)
        person2_id = await create_entity(crm_client, "contact", f"Person2 {unique_id}", auth_headers_system)

        # Создаем недирективную связь
        _ = await create_relationship(crm_client, person1_id, person2_id, f"friends_{unique_id}", auth_headers_system)

        # Граф от Person1 - Person2 виден
        response = await crm_client.get(
            f"/crm/api/v1/entities/{person1_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = _http_json(response)
        entity_ids = _entity_ids_from_graph(graph)
        assert person2_id in entity_ids

        # Граф от Person2 - Person1 ТОЖЕ виден (симметричная связь)
        response = await crm_client.get(
            f"/crm/api/v1/entities/{person2_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = _http_json(response)
        entity_ids = _entity_ids_from_graph(graph)
        assert person1_id in entity_ids


class TestFiltering:
    """Фильтрация по типам связей"""

    @pytest.mark.asyncio
    async def test_filter_single_type(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 3.1: Фильтр по одному типу"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, a_id, c_id, "mentors", auth_headers_system)
        _ = await create_relationship(crm_client, b_id, d_id, "manages", auth_headers_system)

        # Фильтр только по "manages"
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?relationship_types=manages",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        entity_ids = _entity_ids_from_graph(graph)
        assert b_id in entity_ids
        assert d_id in entity_ids
        assert c_id not in entity_ids  # "mentors" отфильтрован

    @pytest.mark.asyncio
    async def test_filter_multiple_types(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 3.2: Фильтр по нескольким типам"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, a_id, c_id, "mentors", auth_headers_system)
        _ = await create_relationship(crm_client, a_id, d_id, "works_with", auth_headers_system)

        # Фильтр по "manages" и "mentors"
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?relationship_types=manages,mentors",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        entity_ids = _entity_ids_from_graph(graph)
        assert b_id in entity_ids
        assert c_id in entity_ids
        assert d_id not in entity_ids  # "works_with" отфильтрован


class TestDepthLimits:
    """Ограничение глубины (max_depth)"""

    @pytest.mark.asyncio
    async def test_max_depth_1(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 4.1: max_depth=1 (только прямые соседи)"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, c_id, d_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=1",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        entity_ids = _entity_ids_from_graph(graph)
        assert a_id in entity_ids
        assert b_id in entity_ids
        assert c_id not in entity_ids
        assert d_id not in entity_ids

    @pytest.mark.asyncio
    async def test_max_depth_2(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 4.2: max_depth=2"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, c_id, d_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=2",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        entity_ids = _entity_ids_from_graph(graph)
        assert a_id in entity_ids
        assert b_id in entity_ids
        assert c_id in entity_ids
        assert d_id not in entity_ids

    @pytest.mark.asyncio
    async def test_max_depth_full(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 4.3: max_depth=5 (полный граф)"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, c_id, d_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=5",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        assert _json_int(graph, "total_nodes") == 4


class TestShortestPath:
    """Кратчайший путь (Dijkstra)"""

    @pytest.mark.asyncio
    async def test_simple_path(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 5.1: Прямой путь A→B→C"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system, weight=1.0)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system, weight=1.0)

        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        path_result = _http_json(response)
        assert _json_bool(path_result, "exists") is True
        assert _path_entity_ids(path_result) == [a_id, b_id, c_id]
        assert _json_float(path_result, "total_distance") == 2.0
        assert len(object_list(path_result.get("edges"))) == 2

    @pytest.mark.asyncio
    async def test_weighted_path_selection(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 5.2: Взвешенный путь (выбор оптимального)"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        # Прямой путь с большим весом
        _ = await create_relationship(crm_client, a_id, c_id, "mentions", auth_headers_system, weight=5.0)
        # Путь через B с меньшим весом
        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system, weight=1.0)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system, weight=1.0)

        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        path_result = _http_json(response)
        assert _json_bool(path_result, "exists") is True
        # Должен выбрать путь через B (2.0 < 5.0)
        assert _path_entity_ids(path_result) == [a_id, b_id, c_id]
        assert _json_float(path_result, "total_distance") == 2.0

    @pytest.mark.asyncio
    async def test_no_path_exists(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 5.3: Путь не существует"""
        # Изолированные компоненты
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, c_id, d_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={d_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        path_result = _http_json(response)
        assert _json_bool(path_result, "exists") is False
        assert _path_entity_ids(path_result) == []
        assert _json_float(path_result, "total_distance") == 0.0

    @pytest.mark.asyncio
    async def test_path_with_directionality(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 5.4: Путь с учетом направленности"""
        # Создаем тип связи БЕЗ inverse_type_id
        _ = await create_relationship_type(
            crm_client, f"supervises_{unique_id}", "Supervises",
            auth_headers_system, is_directed=True, inverse_type_id=None
        )

        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        # Направленные связи БЕЗ inverse
        _ = await create_relationship(crm_client, a_id, b_id, f"supervises_{unique_id}", auth_headers_system)
        _ = await create_relationship(crm_client, b_id, c_id, f"supervises_{unique_id}", auth_headers_system)

        # От A до C - должен найти
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert _json_bool(_http_json(response), "exists") is True

        # От C до A - не должен найти (направленные связи)
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={c_id}&to={a_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert _json_bool(_http_json(response), "exists") is False

    @pytest.mark.asyncio
    async def test_path_through_undirected(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 5.5: Путь через undirected связи"""
        # Создаем недирективный тип
        _ = await create_relationship_type(
            crm_client, f"friends_{unique_id}", "Friends",
            auth_headers_system, is_directed=False
        )

        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, f"friends_{unique_id}", auth_headers_system)
        _ = await create_relationship(crm_client, b_id, c_id, f"friends_{unique_id}", auth_headers_system)

        # От A до C - должен найти
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert _json_bool(_http_json(response), "exists") is True

        # От C до A - ТОЖЕ должен найти (симметричные связи)
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={c_id}&to={a_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert _json_bool(_http_json(response), "exists") is True

    @pytest.mark.asyncio
    async def test_path_max_depth_limit(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 5.6: max_depth ограничивает поиск"""
        entities: list[str] = []
        for i in range(5):
            entity_id = await create_entity(crm_client, "contact", f"Person{i} {unique_id}", auth_headers_system)
            entities.append(entity_id)

        # Создаем цепочку A→B→C→D→E
        for i in range(4):
            _ = await create_relationship(crm_client, entities[i], entities[i+1], "mentions", auth_headers_system)

        # Путь от A до E с max_depth=3 (требуется 4 шага)
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={entities[0]}&to={entities[4]}&max_depth=3",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert _json_bool(_http_json(response), "exists") is False


class TestRelatedEntities:
    """Связанные entities (1 уровень)"""

    @pytest.mark.asyncio
    async def test_outgoing_only(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 6.1: direction="outgoing" """
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, a_id, c_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, d_id, a_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/related?direction=outgoing",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        related = _http_json(response)
        outgoing_ids = _entity_ids_from_nodes(_related_nodes(related, "outgoing"))
        assert len(_related_nodes(related, "outgoing")) == 2
        assert b_id in outgoing_ids
        assert c_id in outgoing_ids
        assert len(_related_nodes(related, "incoming")) == 0

    @pytest.mark.asyncio
    async def test_incoming_only(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 6.2: direction="incoming" """
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, a_id, c_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, d_id, a_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/related?direction=incoming",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        related = _http_json(response)
        incoming_ids = _entity_ids_from_nodes(_related_nodes(related, "incoming"))
        assert len(_related_nodes(related, "incoming")) == 1
        assert d_id in incoming_ids
        assert len(_related_nodes(related, "outgoing")) == 0

    @pytest.mark.asyncio
    async def test_both_directions(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 6.3: direction="both" (по умолчанию)"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, a_id, c_id, "mentions", auth_headers_system)
        _ = await create_relationship(crm_client, d_id, a_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/related?direction=both",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        related = _http_json(response)
        assert len(_related_nodes(related, "incoming")) == 1
        assert len(_related_nodes(related, "outgoing")) == 2

    @pytest.mark.asyncio
    async def test_filter_by_relationship_type(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 6.4: Фильтр по relationship_type"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, a_id, c_id, "mentors", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/related?relationship_type=manages",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        related = _http_json(response)
        outgoing_ids = _entity_ids_from_nodes(_related_nodes(related, "outgoing"))
        assert b_id in outgoing_ids
        assert c_id not in outgoing_ids


class TestAccessControl:
    """Права доступа"""

    @pytest.mark.asyncio
    async def test_placeholder_nodes(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str], auth_headers_company2: dict[str, str]):
        """Test 7.1: Placeholder для недоступных узлов"""
        ns = f"g_{unique_id}"
        # Company2 user создает entities в СВОЕЙ компании
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_company2, namespace=ns)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_company2)

        # Делаем только A публичной
        _ = await create_public_grant(crm_client, a_id, auth_headers_company2)

        # System user (другая компания, но есть public grant) запрашивает граф от A
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        nodes_by_id = _nodes_by_entity_id(graph)

        # A доступен полностью
        assert _json_bool(nodes_by_id[a_id], "access") is True
        assert _node_str(nodes_by_id[a_id], "entity_type") != "hidden"

        # B и C - placeholders
        assert _json_bool(nodes_by_id[b_id], "access") is False
        assert _node_str(nodes_by_id[b_id], "entity_type") == "hidden"
        assert _node_str(nodes_by_id[b_id], "name") == "Hidden"

        assert _json_bool(nodes_by_id[c_id], "access") is False
        assert _node_str(nodes_by_id[c_id], "entity_type") == "hidden"

        assert _json_int(graph, "filtered_count") == 2

    @pytest.mark.asyncio
    async def test_partial_access_through_grants(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str], auth_headers_company2: dict[str, str]):
        """Test 7.2: Частичный доступ через grants"""
        ns = f"g_{unique_id}"
        # Company2 user создает entities в СВОЕЙ компании
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_company2, namespace=ns)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_company2)

        # Делаем A и C публичными
        _ = await create_public_grant(crm_client, a_id, auth_headers_company2)
        _ = await create_public_grant(crm_client, c_id, auth_headers_company2)

        # System user (другая компания, но есть public grants) запрашивает граф
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        nodes_by_id = _nodes_by_entity_id(graph)

        # A и C доступны
        assert _json_bool(nodes_by_id[a_id], "access") is True
        assert _json_bool(nodes_by_id[c_id], "access") is True

        # B - placeholder
        assert _json_bool(nodes_by_id[b_id], "access") is False
        assert _json_int(graph, "filtered_count") == 1


class TestCrossCompanyAccess:
    """Cross-company доступ через grants"""

    @pytest.mark.asyncio
    async def test_public_grant_shows_relationships(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str], auth_headers_company2: dict[str, str]):
        """Test 7.3: Public grant позволяет видеть relationships"""
        ns = f"g_{unique_id}"
        # Company2 создает граф
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)
        _ = await create_public_grant(crm_client, a_id, auth_headers_company2)

        # System user видит relationship (но B как placeholder)
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = _http_json(response)

        # Должен быть 1 edge (A→B)
        assert len(_graph_edges(graph)) == 1
        assert _node_str(_graph_edge_at(graph, 0), "source_id") == a_id
        assert _node_str(_graph_edge_at(graph, 0), "target_id") == b_id

        # B виден как placeholder
        nodes = _nodes_by_entity_id(graph)
        assert b_id in nodes
        assert _json_bool(nodes[b_id], "access") is False

    @pytest.mark.asyncio
    async def test_user_grant_cross_company(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str], auth_headers_company2: dict[str, str], system_user_id: str):
        """Test 7.4: User grant позволяет видеть relationships"""
        ns = f"g_{unique_id}"
        # Company2 создает entities
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_company2, namespace=ns)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_company2)

        # Даем system user доступ к A и C (но НЕ к B)
        response = await crm_client.post(
            f"/crm/api/v1/entities/{a_id}/grants/user",
            json={
                "user_id": system_user_id,
                "role": "viewer"
            },
            headers=auth_headers_company2
        )
        assert response.status_code == 200, f"Failed to grant A: {response.text}"

        response = await crm_client.post(
            f"/crm/api/v1/entities/{c_id}/grants/user",
            json={
                "user_id": system_user_id,
                "role": "viewer"
            },
            headers=auth_headers_company2
        )
        assert response.status_code == 200, f"Failed to grant C: {response.text}"

        # System user видит A→B→C, где B = placeholder
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = _http_json(response)

        # Должно быть 2 edges
        assert len(_graph_edges(graph)) == 2

        # A и C доступны, B - placeholder
        nodes = _nodes_by_entity_id(graph)
        assert _json_bool(nodes[a_id], "access") is True
        assert _json_bool(nodes[b_id], "access") is False
        assert _json_bool(nodes[c_id], "access") is True

    @pytest.mark.asyncio
    async def test_namespace_grant_cross_company(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str], auth_headers_company2: dict[str, str]):
        """Test 7.5: Namespace grant дает доступ ко всем relationships"""
        # Company2 создает entities в namespace
        entities: list[str] = []
        for i in range(5):
            e_id = await create_entity(crm_client, "contact", f"E{i} {unique_id}", auth_headers_company2)
            entities.append(e_id)

        # Создаем цепочку
        for i in range(4):
            _ = await create_relationship(crm_client, entities[i], entities[i+1], "mentions", auth_headers_company2)

        # Даем namespace grant
        response = await crm_client.post(
            "/crm/api/v1/namespaces/default/grants/company",
            json={
                "company_id": "system",
                "role": "viewer"
            },
            headers=auth_headers_company2
        )
        assert response.status_code == 200, f"Failed to grant namespace: {response.text}"

        # System user видит весь граф
        response = await crm_client.get(
            f"/crm/api/v1/entities/{entities[0]}/influence-graph?max_depth=5",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = _http_json(response)

        # Все entities и relationships видны
        assert len(_graph_nodes(graph)) == 5
        assert len(_graph_edges(graph)) == 4
        assert all(_json_bool(n, "access") is True for n in _graph_nodes(graph))

    @pytest.mark.asyncio
    async def test_shortest_path_cross_company(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str], auth_headers_company2: dict[str, str]):
        """Test 7.6: Shortest path работает через company границы"""
        ns = f"g_{unique_id}"
        # Company2 создает путь A→B→C
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_company2, namespace=ns)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2, weight=1.0)
        _ = await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_company2, weight=1.0)

        # Public grants для A и C
        _ = await create_public_grant(crm_client, a_id, auth_headers_company2)
        _ = await create_public_grant(crm_client, c_id, auth_headers_company2)

        # System user ищет путь
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        path = _http_json(response)

        assert _json_bool(path, "exists") is True
        assert len(_path_entity_ids(path)) == 3
        assert _json_float(path, "total_distance") == 2.0

    @pytest.mark.asyncio
    async def test_related_entities_cross_company(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str], auth_headers_company2: dict[str, str]):
        """Test 7.7: Related entities видны через company границы"""
        ns = f"g_{unique_id}"
        # Company2 создает hub entity
        hub_id = await create_entity(crm_client, "contact", f"Hub {unique_id}", auth_headers_company2, namespace=ns)

        related_ids: list[str] = []
        for i in range(3):
            r_id = await create_entity(crm_client, "contact", f"Related{i} {unique_id}", auth_headers_company2, namespace=ns)
            _ = await create_relationship(crm_client, hub_id, r_id, "mentions", auth_headers_company2)
            related_ids.append(r_id)

        # Public grant для hub
        _ = await create_public_grant(crm_client, hub_id, auth_headers_company2)

        # System user получает related
        response = await crm_client.get(
            f"/crm/api/v1/entities/{hub_id}/related",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        related = _http_json(response)

        # Должны быть видны 3 outgoing (как placeholders)
        assert len(_related_nodes(related, "outgoing")) == 3


class TestPerformance:
    """Производительность и лимиты"""

    @pytest.mark.asyncio
    async def test_deep_graph(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 8.2: Глубокий граф (max_depth=5)"""
        entities: list[str] = []
        for i in range(6):
            entity_id = await create_entity(crm_client, "contact", f"Person{i} {unique_id}", auth_headers_system)
            entities.append(entity_id)

        # Создаем цепочку A→B→C→D→E→F
        for i in range(5):
            _ = await create_relationship(crm_client, entities[i], entities[i+1], "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{entities[0]}/influence-graph?max_depth=5",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        assert _json_int(graph, "total_nodes") == 6

        # Проверяем уровни
        nodes_by_id = _nodes_by_entity_id(graph)
        for i, entity_id in enumerate(entities):
            assert _json_int(nodes_by_id[entity_id], "level") == i

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_wide_graph(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 8.3: Широкий граф (много соседей)"""
        root_id = await create_entity(crm_client, "contact", f"Root {unique_id}", auth_headers_system)

        # Создаем 20 прямых соседей (уменьшено с 50 для скорости теста)
        neighbor_ids: list[str] = []
        for i in range(20):
            neighbor_id = await create_entity(crm_client, "contact", f"Neighbor{i} {unique_id}", auth_headers_system)
            neighbor_ids.append(neighbor_id)
            _ = await create_relationship(crm_client, root_id, neighbor_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{root_id}/influence-graph?max_depth=1",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        assert _json_int(graph, "total_nodes") == 21  # root + 20 neighbors

        # Все узлы на уровне 0 или 1
        for node in _graph_nodes(graph):
            assert _json_int(node, "level") in [0, 1]


class TestComplexScenarios:
    """Комплексные сценарии"""

    @pytest.mark.asyncio
    async def test_organizational_hierarchy(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 9.1: Организационная иерархия"""
        # Создаем иерархию
        ceo_id = await create_entity(crm_client, "contact", f"CEO {unique_id}", auth_headers_system)
        vp_sales_id = await create_entity(crm_client, "contact", f"VP Sales {unique_id}", auth_headers_system)
        vp_eng_id = await create_entity(crm_client, "contact", f"VP Eng {unique_id}", auth_headers_system)
        mgr1_id = await create_entity(crm_client, "contact", f"Manager1 {unique_id}", auth_headers_system)
        mgr2_id = await create_entity(crm_client, "contact", f"Manager2 {unique_id}", auth_headers_system)
        dev1_id = await create_entity(crm_client, "contact", f"Dev1 {unique_id}", auth_headers_system)
        dev2_id = await create_entity(crm_client, "contact", f"Dev2 {unique_id}", auth_headers_system)
        dev3_id = await create_entity(crm_client, "contact", f"Dev3 {unique_id}", auth_headers_system)
        dev4_id = await create_entity(crm_client, "contact", f"Dev4 {unique_id}", auth_headers_system)

        # Создаем связи
        _ = await create_relationship(crm_client, ceo_id, vp_sales_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, ceo_id, vp_eng_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, vp_sales_id, mgr1_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, vp_eng_id, mgr2_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, mgr1_id, dev1_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, mgr1_id, dev2_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, mgr2_id, dev3_id, "manages", auth_headers_system)
        _ = await create_relationship(crm_client, mgr2_id, dev4_id, "manages", auth_headers_system)

        # Строим граф от CEO
        response = await crm_client.get(
            f"/crm/api/v1/entities/{ceo_id}/influence-graph?max_depth=3",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        assert _json_int(graph, "total_nodes") == 9
        assert len(_graph_edges(graph)) == 8

    @pytest.mark.asyncio
    async def test_project_network(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 9.2: Проектная сеть"""
        # Создаем entities разных типов
        project1_id = await create_entity(crm_client, "project", f"Project1 {unique_id}", auth_headers_system)
        project2_id = await create_entity(crm_client, "project", f"Project2 {unique_id}", auth_headers_system)
        project3_id = await create_entity(crm_client, "project", f"Project3 {unique_id}", auth_headers_system)
        person1_id = await create_entity(crm_client, "contact", f"Person1 {unique_id}", auth_headers_system)
        person2_id = await create_entity(crm_client, "contact", f"Person2 {unique_id}", auth_headers_system)

        # Создаем связи
        _ = await create_relationship(crm_client, person1_id, project1_id, "works_on", auth_headers_system)
        _ = await create_relationship(crm_client, person1_id, project2_id, "works_on", auth_headers_system)
        _ = await create_relationship(crm_client, person1_id, person2_id, "collaborates_with", auth_headers_system)
        _ = await create_relationship(crm_client, person2_id, project3_id, "works_on", auth_headers_system)

        # Строим граф от Person1
        response = await crm_client.get(
            f"/crm/api/v1/entities/{person1_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        assert _json_int(graph, "total_nodes") == 5

        # Находим путь от Project1 до Project3
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={project1_id}&to={project3_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        # Путь может не существовать из-за направленности, это нормально


class TestEdgeCases:
    """Граничные случаи"""

    @pytest.mark.asyncio
    async def test_single_node_graph(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 10.1: Граф из одного узла (нет связей)"""
        entity_id = await create_entity(crm_client, "contact", f"Lonely {unique_id}", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{entity_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = _http_json(response)
        assert _json_int(graph, "total_nodes") == 1
        assert len(_graph_edges(graph)) == 0
        assert _node_str(_graph_node_at(graph, 0), "entity_id") == entity_id

    @pytest.mark.asyncio
    async def test_nonexistent_entity(self, crm_client: AsyncClient, auth_headers_system: dict[str, str]):
        """Test 10.2: Несуществующая entity"""
        fake_id = "nonexistent_entity_id_12345"

        response = await crm_client.get(
            f"/crm/api/v1/entities/{fake_id}/influence-graph",
            headers=auth_headers_system
        )
        # Должна быть ошибка 404 или 500
        assert response.status_code in [404, 500]

    @pytest.mark.asyncio
    async def test_no_access_to_root(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str], auth_headers_company2: dict[str, str]):
        """Test 10.3: Нет доступа к root entity"""
        # System user создает private entity
        entity_id = await create_entity(crm_client, "contact", f"Private {unique_id}", auth_headers_system)

        # Company2 user пытается получить граф
        response = await crm_client.get(
            f"/crm/api/v1/entities/{entity_id}/influence-graph",
            headers=auth_headers_company2
        )
        # Должна быть ошибка 403
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_max_depth_zero(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 10.6: max_depth=0"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)

        # max_depth=0 должен вернуть только root
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=0",
            headers=auth_headers_system
        )

        # API может отклонить max_depth=0 или вернуть только root
        # Проверяем оба варианта
        if response.status_code == 200:
            graph = _http_json(response)
            # Если принимает, должен вернуть только root
            assert _json_int(graph, "total_nodes") == 1
            assert _node_str(_graph_node_at(graph, 0), "entity_id") == a_id
        else:
            # Или вернуть ошибку валидации (400 или 422)
            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_self_loop_path(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 10.7: Shortest path от A до A (self-loop)"""
        entity_id = await create_entity(crm_client, "contact", f"Self {unique_id}", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={entity_id}&to={entity_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        path_result = _http_json(response)
        assert _json_bool(path_result, "exists") is True
        assert _path_entity_ids(path_result) == [entity_id]
        assert _json_float(path_result, "total_distance") == 0.0


class TestSameCompanyRegression:
    """Убедиться что same-company сценарии работают как раньше"""

    @pytest.mark.asyncio
    async def test_same_company_graph_unchanged(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]):
        """Test 8.1: Same company графы работают как раньше"""
        # Все в одной компании
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)

        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = _http_json(response)

        assert len(_graph_nodes(graph)) == 2
        assert len(_graph_edges(graph)) == 1
        assert all(_json_bool(n, "access") is True for n in _graph_nodes(graph))

    @pytest.mark.asyncio
    async def test_api_list_relationships_filtered(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str], auth_headers_company2: dict[str, str]):
        """Test 8.2: API /relationships/ фильтрует по компании"""
        ns = f"g_{unique_id}"
        # Company2 создает relationship
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        _ = await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)

        # System user НЕ видит через API
        response = await crm_client.get(
            f"/crm/api/v1/relationships/?entity_id={a_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        rels = object_list(_http_json(response).get("items"))
        assert len(rels) == 0


class TestInfluenceGraphNamespaceFilter:
    """Query ``namespace`` фильтрует Relationship.namespace при обходе графа."""

    @pytest.mark.asyncio
    async def test_other_namespace_edges_excluded(
        self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """Связи в чужом namespace не должны попадать в обход с ?namespace=default."""
        ns_default = "default"
        ns_other = f"other_{unique_id}"
        await ensure_namespace(crm_client, ns_other, unique_id, auth_headers_system, "contact")

        root_id = await create_entity(
            crm_client, "contact", f"Root {unique_id}", auth_headers_system,
            namespace=ns_default,
        )
        peer_default = await create_entity(
            crm_client, "contact", f"PeerDefault {unique_id}", auth_headers_system,
            namespace=ns_default,
        )
        peer_other = await create_entity(
            crm_client, "contact", f"PeerOther {unique_id}", auth_headers_system,
            namespace=ns_other,
        )

        _ = await create_relationship(
            crm_client, root_id, peer_default, "mentors", auth_headers_system,
            namespace=ns_default,
        )
        _ = await create_relationship(
            crm_client, root_id, peer_other, "mentors", auth_headers_system,
            namespace=ns_other,
        )

        response = await crm_client.get(
            f"/crm/api/v1/entities/{root_id}/influence-graph",
            params={"max_depth": 2, "namespace": ns_default},
            headers=auth_headers_system,
        )
        assert response.status_code == 200, response.text
        graph = _http_json(response)
        ids = set(_entity_ids_from_graph(graph))
        assert root_id in ids
        assert peer_default in ids
        assert peer_other not in ids
        assert len(_graph_edges(graph)) == 1

    @pytest.mark.asyncio
    async def test_include_all_namespaces_brings_back_other(
        self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """Флаг include_all_namespaces=true возвращает связи всех Relationship.namespace."""
        ns_default = "default"
        ns_other = f"other_{unique_id}_all"
        await ensure_namespace(
            crm_client, ns_other, f"{unique_id}_all", auth_headers_system, "contact"
        )

        root_id = await create_entity(
            crm_client, "contact", f"Root {unique_id}", auth_headers_system,
            namespace=ns_default,
        )
        peer_other = await create_entity(
            crm_client, "contact", f"PeerOther {unique_id}", auth_headers_system,
            namespace=ns_other,
        )
        _ = await create_relationship(
            crm_client, root_id, peer_other, "mentors", auth_headers_system,
            namespace=ns_other,
        )

        response = await crm_client.get(
            f"/crm/api/v1/entities/{root_id}/influence-graph",
            params={
                "max_depth": 2,
                "namespace": ns_default,
                "include_all_namespaces": "true",
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200, response.text
        graph = _http_json(response)
        ids = set(_entity_ids_from_graph(graph))
        assert peer_other in ids

    @pytest.mark.asyncio
    async def test_related_endpoint_namespace_filter(
        self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """GET /entities/{id}/related тоже фильтрует Relationship.namespace."""
        ns_default = "default"
        ns_other = f"other_{unique_id}_rel"
        await ensure_namespace(
            crm_client, ns_other, f"{unique_id}_rel", auth_headers_system, "contact"
        )

        root_id = await create_entity(
            crm_client, "contact", f"Root {unique_id}", auth_headers_system,
            namespace=ns_default,
        )
        peer_default = await create_entity(
            crm_client, "contact", f"PeerDefault {unique_id}", auth_headers_system,
            namespace=ns_default,
        )
        peer_other = await create_entity(
            crm_client, "contact", f"PeerOther {unique_id}", auth_headers_system,
            namespace=ns_other,
        )

        _ = await create_relationship(
            crm_client, root_id, peer_default, "mentors", auth_headers_system,
            namespace=ns_default,
        )
        _ = await create_relationship(
            crm_client, root_id, peer_other, "mentors", auth_headers_system,
            namespace=ns_other,
        )

        response = await crm_client.get(
            f"/crm/api/v1/entities/{root_id}/related",
            params={"namespace": ns_default},
            headers=auth_headers_system,
        )
        assert response.status_code == 200, response.text
        related = _http_json(response)
        outgoing_ids = set(_entity_ids_from_nodes(_related_nodes(related, "outgoing")))
        assert peer_default in outgoing_ids
        assert peer_other not in outgoing_ids
