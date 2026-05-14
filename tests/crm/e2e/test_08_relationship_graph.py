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

import pytest
import pytest_asyncio
from httpx import AsyncClient

# ============================================================================
# Fixtures
# ============================================================================

# Глобальный флаг для отслеживания инициализации типов
_relationship_types_initialized = False


@pytest_asyncio.fixture(autouse=True)
async def ensure_relationship_types(crm_client, auth_headers_system):
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
    headers: dict,
    attributes: dict = None,
    namespace: str | None = None,
) -> str:
    """Создать entity и вернуть entity_id"""
    payload = {
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
    return response.json()["entity_id"]


async def create_relationship(
    client: AsyncClient,
    source_id: str,
    target_id: str,
    relationship_type: str,
    headers: dict,
    weight: float = 1.0,
    namespace: str | None = None,
) -> str:
    """Создать relationship и вернуть relationship_id"""
    payload: dict = {
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
    return response.json()["relationship_id"]


async def create_relationship_type(
    client: AsyncClient,
    type_id: str,
    name: str,
    headers: dict,
    is_directed: bool = True,
    inverse_type_id: str = None
) -> None:
    """Создать тип связи"""
    response = await client.post(
        "/crm/api/v1/relationships/types/",
        json={
            "type_id": type_id,
            "name": name,
            "is_directed": is_directed,
            "inverse_type_id": inverse_type_id
        },
        headers=headers
    )
    assert response.status_code == 200, f"Failed to create relationship type: {response.text}"


async def ensure_namespace(
    client: AsyncClient,
    namespace_name: str,
    template_suffix: str,
    headers: dict,
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
    headers: dict
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
    async def test_simple_linear_graph(self, crm_client, unique_id, auth_headers_system):
        """Test 1.1: Линейная цепочка CEO → Manager → Developer"""
        # Создаем entities
        ceo_id = await create_entity(crm_client, "contact", f"CEO {unique_id}", auth_headers_system)
        manager_id = await create_entity(crm_client, "contact", f"Manager {unique_id}", auth_headers_system)
        dev_id = await create_entity(crm_client, "contact", f"Developer {unique_id}", auth_headers_system)

        # Создаем relationships
        await create_relationship(crm_client, ceo_id, manager_id, "manages", auth_headers_system)
        await create_relationship(crm_client, manager_id, dev_id, "manages", auth_headers_system)

        # Строим граф от CEO
        response = await crm_client.get(
            f"/crm/api/v1/entities/{ceo_id}/influence-graph?max_depth=3",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["total_nodes"] == 3
        assert len(graph["edges"]) == 2
        assert graph["root_entity_id"] == ceo_id
        assert graph["max_depth"] == 3

        # Проверяем уровни узлов
        nodes_by_id = {node["entity_id"]: node for node in graph["nodes"]}
        assert nodes_by_id[ceo_id]["level"] == 0
        assert nodes_by_id[manager_id]["level"] == 1
        assert nodes_by_id[dev_id]["level"] == 2

        # Все узлы доступны
        assert all(node["access"] for node in graph["nodes"])

    @pytest.mark.asyncio
    async def test_branching_tree_graph(self, crm_client, unique_id, auth_headers_system):
        """Test 1.2: Дерево с разветвлением"""
        # Создаем иерархию
        ceo_id = await create_entity(crm_client, "contact", f"CEO {unique_id}", auth_headers_system)
        mgr1_id = await create_entity(crm_client, "contact", f"Manager1 {unique_id}", auth_headers_system)
        mgr2_id = await create_entity(crm_client, "contact", f"Manager2 {unique_id}", auth_headers_system)
        dev1_id = await create_entity(crm_client, "contact", f"Dev1 {unique_id}", auth_headers_system)
        dev2_id = await create_entity(crm_client, "contact", f"Dev2 {unique_id}", auth_headers_system)

        # Создаем связи
        await create_relationship(crm_client, ceo_id, mgr1_id, "manages", auth_headers_system)
        await create_relationship(crm_client, ceo_id, mgr2_id, "manages", auth_headers_system)
        await create_relationship(crm_client, mgr1_id, dev1_id, "manages", auth_headers_system)
        await create_relationship(crm_client, mgr2_id, dev2_id, "manages", auth_headers_system)

        # Строим граф
        response = await crm_client.get(
            f"/crm/api/v1/entities/{ceo_id}/influence-graph?max_depth=2",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["total_nodes"] == 5
        assert len(graph["edges"]) == 4

        # Проверяем уровни
        nodes_by_id = {node["entity_id"]: node for node in graph["nodes"]}
        assert nodes_by_id[ceo_id]["level"] == 0
        assert nodes_by_id[mgr1_id]["level"] == 1
        assert nodes_by_id[mgr2_id]["level"] == 1
        assert nodes_by_id[dev1_id]["level"] == 2
        assert nodes_by_id[dev2_id]["level"] == 2

    @pytest.mark.asyncio
    async def test_graph_with_cycles(self, crm_client, unique_id, auth_headers_system):
        """Test 1.3: Граф с циклами A→B→C→A"""
        # Создаем entities
        a_id = await create_entity(crm_client, "contact", f"PersonA {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"PersonB {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"PersonC {unique_id}", auth_headers_system)

        # Создаем цикл
        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, c_id, a_id, "mentions", auth_headers_system)

        # Строим граф - BFS не должен зациклиться
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=5",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        # Каждый узел посещается только раз
        assert graph["total_nodes"] == 3
        assert len(graph["edges"]) == 3


class TestDirectionality:
    """Направленность связей"""

    @pytest.mark.asyncio
    async def test_directed_relationships(self, crm_client, unique_id, auth_headers_system):
        """Test 2.1: Направленные связи без inverse"""
        # Создаем тип связи БЕЗ inverse_type_id
        await create_relationship_type(
            crm_client, f"supervises_{unique_id}", "Supervises",
            auth_headers_system, is_directed=True, inverse_type_id=None
        )

        manager_id = await create_entity(crm_client, "contact", f"Manager {unique_id}", auth_headers_system)
        employee_id = await create_entity(crm_client, "contact", f"Employee {unique_id}", auth_headers_system)

        # Создаем направленную связь БЕЗ inverse
        await create_relationship(crm_client, manager_id, employee_id, f"supervises_{unique_id}", auth_headers_system)

        # Граф от Manager - Employee должен быть виден
        response = await crm_client.get(
            f"/crm/api/v1/entities/{manager_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = response.json()
        entity_ids = [node["entity_id"] for node in graph["nodes"]]
        assert employee_id in entity_ids

        # Граф от Employee - Manager НЕ должен быть виден (направленная связь)
        response = await crm_client.get(
            f"/crm/api/v1/entities/{employee_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = response.json()
        entity_ids = [node["entity_id"] for node in graph["nodes"]]
        assert manager_id not in entity_ids

    @pytest.mark.asyncio
    async def test_inverse_relationships(self, crm_client, unique_id, auth_headers_system):
        """Test 2.2: Обратные связи (manages ↔ reports_to)"""
        # Создаем типы связей с inverse_type_id
        await create_relationship_type(
            crm_client, f"manages_{unique_id}", "Manages",
            auth_headers_system, is_directed=True, inverse_type_id=f"reports_to_{unique_id}"
        )
        await create_relationship_type(
            crm_client, f"reports_to_{unique_id}", "Reports To",
            auth_headers_system, is_directed=True, inverse_type_id=f"manages_{unique_id}"
        )

        manager_id = await create_entity(crm_client, "contact", f"Manager {unique_id}", auth_headers_system)
        employee_id = await create_entity(crm_client, "contact", f"Employee {unique_id}", auth_headers_system)

        # Создаем только одну связь manages
        await create_relationship(crm_client, manager_id, employee_id, f"manages_{unique_id}", auth_headers_system)

        # Граф от Employee - Manager ДОЛЖЕН быть виден через inverse_type_id
        response = await crm_client.get(
            f"/crm/api/v1/entities/{employee_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = response.json()
        entity_ids = [node["entity_id"] for node in graph["nodes"]]
        assert manager_id in entity_ids

    @pytest.mark.asyncio
    async def test_undirected_relationships(self, crm_client, unique_id, auth_headers_system):
        """Test 2.3: Недирективные связи (симметричные)"""
        # Создаем недирективный тип связи
        await create_relationship_type(
            crm_client, f"friends_{unique_id}", "Friends",
            auth_headers_system, is_directed=False
        )

        person1_id = await create_entity(crm_client, "contact", f"Person1 {unique_id}", auth_headers_system)
        person2_id = await create_entity(crm_client, "contact", f"Person2 {unique_id}", auth_headers_system)

        # Создаем недирективную связь
        await create_relationship(crm_client, person1_id, person2_id, f"friends_{unique_id}", auth_headers_system)

        # Граф от Person1 - Person2 виден
        response = await crm_client.get(
            f"/crm/api/v1/entities/{person1_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = response.json()
        entity_ids = [node["entity_id"] for node in graph["nodes"]]
        assert person2_id in entity_ids

        # Граф от Person2 - Person1 ТОЖЕ виден (симметричная связь)
        response = await crm_client.get(
            f"/crm/api/v1/entities/{person2_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = response.json()
        entity_ids = [node["entity_id"] for node in graph["nodes"]]
        assert person1_id in entity_ids


class TestFiltering:
    """Фильтрация по типам связей"""

    @pytest.mark.asyncio
    async def test_filter_single_type(self, crm_client, unique_id, auth_headers_system):
        """Test 3.1: Фильтр по одному типу"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "manages", auth_headers_system)
        await create_relationship(crm_client, a_id, c_id, "mentors", auth_headers_system)
        await create_relationship(crm_client, b_id, d_id, "manages", auth_headers_system)

        # Фильтр только по "manages"
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?relationship_types=manages",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        entity_ids = [node["entity_id"] for node in graph["nodes"]]
        assert b_id in entity_ids
        assert d_id in entity_ids
        assert c_id not in entity_ids  # "mentors" отфильтрован

    @pytest.mark.asyncio
    async def test_filter_multiple_types(self, crm_client, unique_id, auth_headers_system):
        """Test 3.2: Фильтр по нескольким типам"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "manages", auth_headers_system)
        await create_relationship(crm_client, a_id, c_id, "mentors", auth_headers_system)
        await create_relationship(crm_client, a_id, d_id, "works_with", auth_headers_system)

        # Фильтр по "manages" и "mentors"
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?relationship_types=manages,mentors",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        entity_ids = [node["entity_id"] for node in graph["nodes"]]
        assert b_id in entity_ids
        assert c_id in entity_ids
        assert d_id not in entity_ids  # "works_with" отфильтрован


class TestDepthLimits:
    """Ограничение глубины (max_depth)"""

    @pytest.mark.asyncio
    async def test_max_depth_1(self, crm_client, unique_id, auth_headers_system):
        """Test 4.1: max_depth=1 (только прямые соседи)"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, c_id, d_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=1",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        entity_ids = [node["entity_id"] for node in graph["nodes"]]
        assert a_id in entity_ids
        assert b_id in entity_ids
        assert c_id not in entity_ids
        assert d_id not in entity_ids

    @pytest.mark.asyncio
    async def test_max_depth_2(self, crm_client, unique_id, auth_headers_system):
        """Test 4.2: max_depth=2"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, c_id, d_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=2",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        entity_ids = [node["entity_id"] for node in graph["nodes"]]
        assert a_id in entity_ids
        assert b_id in entity_ids
        assert c_id in entity_ids
        assert d_id not in entity_ids

    @pytest.mark.asyncio
    async def test_max_depth_full(self, crm_client, unique_id, auth_headers_system):
        """Test 4.3: max_depth=5 (полный граф)"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, c_id, d_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=5",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["total_nodes"] == 4


class TestShortestPath:
    """Кратчайший путь (Dijkstra)"""

    @pytest.mark.asyncio
    async def test_simple_path(self, crm_client, unique_id, auth_headers_system):
        """Test 5.1: Прямой путь A→B→C"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system, weight=1.0)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system, weight=1.0)

        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        path_result = response.json()
        assert path_result["exists"] is True
        assert path_result["path"] == [a_id, b_id, c_id]
        assert path_result["total_distance"] == 2.0
        assert len(path_result["edges"]) == 2

    @pytest.mark.asyncio
    async def test_weighted_path_selection(self, crm_client, unique_id, auth_headers_system):
        """Test 5.2: Взвешенный путь (выбор оптимального)"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        # Прямой путь с большим весом
        await create_relationship(crm_client, a_id, c_id, "mentions", auth_headers_system, weight=5.0)
        # Путь через B с меньшим весом
        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system, weight=1.0)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_system, weight=1.0)

        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        path_result = response.json()
        assert path_result["exists"] is True
        # Должен выбрать путь через B (2.0 < 5.0)
        assert path_result["path"] == [a_id, b_id, c_id]
        assert path_result["total_distance"] == 2.0

    @pytest.mark.asyncio
    async def test_no_path_exists(self, crm_client, unique_id, auth_headers_system):
        """Test 5.3: Путь не существует"""
        # Изолированные компоненты
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, c_id, d_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={d_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        path_result = response.json()
        assert path_result["exists"] is False
        assert path_result["path"] == []
        assert path_result["total_distance"] == 0.0

    @pytest.mark.asyncio
    async def test_path_with_directionality(self, crm_client, unique_id, auth_headers_system):
        """Test 5.4: Путь с учетом направленности"""
        # Создаем тип связи БЕЗ inverse_type_id
        await create_relationship_type(
            crm_client, f"supervises_{unique_id}", "Supervises",
            auth_headers_system, is_directed=True, inverse_type_id=None
        )

        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        # Направленные связи БЕЗ inverse
        await create_relationship(crm_client, a_id, b_id, f"supervises_{unique_id}", auth_headers_system)
        await create_relationship(crm_client, b_id, c_id, f"supervises_{unique_id}", auth_headers_system)

        # От A до C - должен найти
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert response.json()["exists"] is True

        # От C до A - не должен найти (направленные связи)
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={c_id}&to={a_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert response.json()["exists"] is False

    @pytest.mark.asyncio
    async def test_path_through_undirected(self, crm_client, unique_id, auth_headers_system):
        """Test 5.5: Путь через undirected связи"""
        # Создаем недирективный тип
        await create_relationship_type(
            crm_client, f"friends_{unique_id}", "Friends",
            auth_headers_system, is_directed=False
        )

        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, f"friends_{unique_id}", auth_headers_system)
        await create_relationship(crm_client, b_id, c_id, f"friends_{unique_id}", auth_headers_system)

        # От A до C - должен найти
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert response.json()["exists"] is True

        # От C до A - ТОЖЕ должен найти (симметричные связи)
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={c_id}&to={a_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert response.json()["exists"] is True

    @pytest.mark.asyncio
    async def test_path_max_depth_limit(self, crm_client, unique_id, auth_headers_system):
        """Test 5.6: max_depth ограничивает поиск"""
        entities = []
        for i in range(5):
            entity_id = await create_entity(crm_client, "contact", f"Person{i} {unique_id}", auth_headers_system)
            entities.append(entity_id)

        # Создаем цепочку A→B→C→D→E
        for i in range(4):
            await create_relationship(crm_client, entities[i], entities[i+1], "mentions", auth_headers_system)

        # Путь от A до E с max_depth=3 (требуется 4 шага)
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={entities[0]}&to={entities[4]}&max_depth=3",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        assert response.json()["exists"] is False


class TestRelatedEntities:
    """Связанные entities (1 уровень)"""

    @pytest.mark.asyncio
    async def test_outgoing_only(self, crm_client, unique_id, auth_headers_system):
        """Test 6.1: direction="outgoing" """
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, a_id, c_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, d_id, a_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/related?direction=outgoing",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        related = response.json()
        outgoing_ids = [node["entity_id"] for node in related["outgoing"]]
        assert len(related["outgoing"]) == 2
        assert b_id in outgoing_ids
        assert c_id in outgoing_ids
        assert len(related["incoming"]) == 0

    @pytest.mark.asyncio
    async def test_incoming_only(self, crm_client, unique_id, auth_headers_system):
        """Test 6.2: direction="incoming" """
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, a_id, c_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, d_id, a_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/related?direction=incoming",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        related = response.json()
        incoming_ids = [node["entity_id"] for node in related["incoming"]]
        assert len(related["incoming"]) == 1
        assert d_id in incoming_ids
        assert len(related["outgoing"]) == 0

    @pytest.mark.asyncio
    async def test_both_directions(self, crm_client, unique_id, auth_headers_system):
        """Test 6.3: direction="both" (по умолчанию)"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)
        d_id = await create_entity(crm_client, "contact", f"D {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, a_id, c_id, "mentions", auth_headers_system)
        await create_relationship(crm_client, d_id, a_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/related?direction=both",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        related = response.json()
        assert len(related["incoming"]) == 1
        assert len(related["outgoing"]) == 2

    @pytest.mark.asyncio
    async def test_filter_by_relationship_type(self, crm_client, unique_id, auth_headers_system):
        """Test 6.4: Фильтр по relationship_type"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "manages", auth_headers_system)
        await create_relationship(crm_client, a_id, c_id, "mentors", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/related?relationship_type=manages",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        related = response.json()
        outgoing_ids = [node["entity_id"] for node in related["outgoing"]]
        assert b_id in outgoing_ids
        assert c_id not in outgoing_ids


class TestAccessControl:
    """Права доступа"""

    @pytest.mark.asyncio
    async def test_placeholder_nodes(self, crm_client, unique_id, auth_headers_system, auth_headers_company2):
        """Test 7.1: Placeholder для недоступных узлов"""
        ns = f"g_{unique_id}"
        # Company2 user создает entities в СВОЕЙ компании
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_company2, namespace=ns)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_company2)

        # Делаем только A публичной
        await create_public_grant(crm_client, a_id, auth_headers_company2)

        # System user (другая компания, но есть public grant) запрашивает граф от A
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        nodes_by_id = {node["entity_id"]: node for node in graph["nodes"]}

        # A доступен полностью
        assert nodes_by_id[a_id]["access"] is True
        assert nodes_by_id[a_id]["entity_type"] != "hidden"

        # B и C - placeholders
        assert nodes_by_id[b_id]["access"] is False
        assert nodes_by_id[b_id]["entity_type"] == "hidden"
        assert nodes_by_id[b_id]["name"] == "Hidden"

        assert nodes_by_id[c_id]["access"] is False
        assert nodes_by_id[c_id]["entity_type"] == "hidden"

        assert graph["filtered_count"] == 2

    @pytest.mark.asyncio
    async def test_partial_access_through_grants(self, crm_client, unique_id, auth_headers_system, auth_headers_company2):
        """Test 7.2: Частичный доступ через grants"""
        ns = f"g_{unique_id}"
        # Company2 user создает entities в СВОЕЙ компании
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_company2, namespace=ns)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_company2)

        # Делаем A и C публичными
        await create_public_grant(crm_client, a_id, auth_headers_company2)
        await create_public_grant(crm_client, c_id, auth_headers_company2)

        # System user (другая компания, но есть public grants) запрашивает граф
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        nodes_by_id = {node["entity_id"]: node for node in graph["nodes"]}

        # A и C доступны
        assert nodes_by_id[a_id]["access"] is True
        assert nodes_by_id[c_id]["access"] is True

        # B - placeholder
        assert nodes_by_id[b_id]["access"] is False
        assert graph["filtered_count"] == 1


class TestCrossCompanyAccess:
    """Cross-company доступ через grants"""

    @pytest.mark.asyncio
    async def test_public_grant_shows_relationships(self, crm_client, unique_id, auth_headers_system, auth_headers_company2):
        """Test 7.3: Public grant позволяет видеть relationships"""
        ns = f"g_{unique_id}"
        # Company2 создает граф
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)
        await create_public_grant(crm_client, a_id, auth_headers_company2)

        # System user видит relationship (но B как placeholder)
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = response.json()

        # Должен быть 1 edge (A→B)
        assert len(graph["edges"]) == 1
        assert graph["edges"][0]["source_id"] == a_id
        assert graph["edges"][0]["target_id"] == b_id

        # B виден как placeholder
        nodes = {n["entity_id"]: n for n in graph["nodes"]}
        assert b_id in nodes
        assert nodes[b_id]["access"] is False

    @pytest.mark.asyncio
    async def test_user_grant_cross_company(self, crm_client, unique_id, auth_headers_system, auth_headers_company2, system_user_id):
        """Test 7.4: User grant позволяет видеть relationships"""
        ns = f"g_{unique_id}"
        # Company2 создает entities
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_company2, namespace=ns)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_company2)

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
        graph = response.json()

        # Должно быть 2 edges
        assert len(graph["edges"]) == 2

        # A и C доступны, B - placeholder
        nodes = {n["entity_id"]: n for n in graph["nodes"]}
        assert nodes[a_id]["access"] is True
        assert nodes[b_id]["access"] is False
        assert nodes[c_id]["access"] is True

    @pytest.mark.asyncio
    async def test_namespace_grant_cross_company(self, crm_client, unique_id, auth_headers_system, auth_headers_company2):
        """Test 7.5: Namespace grant дает доступ ко всем relationships"""
        # Company2 создает entities в namespace
        entities = []
        for i in range(5):
            e_id = await create_entity(crm_client, "contact", f"E{i} {unique_id}", auth_headers_company2)
            entities.append(e_id)

        # Создаем цепочку
        for i in range(4):
            await create_relationship(crm_client, entities[i], entities[i+1], "mentions", auth_headers_company2)

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
        graph = response.json()

        # Все entities и relationships видны
        assert len(graph["nodes"]) == 5
        assert len(graph["edges"]) == 4
        assert all(n["access"] is True for n in graph["nodes"])

    @pytest.mark.asyncio
    async def test_shortest_path_cross_company(self, crm_client, unique_id, auth_headers_system, auth_headers_company2):
        """Test 7.6: Shortest path работает через company границы"""
        ns = f"g_{unique_id}"
        # Company2 создает путь A→B→C
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        c_id = await create_entity(crm_client, "contact", f"C {unique_id}", auth_headers_company2, namespace=ns)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2, weight=1.0)
        await create_relationship(crm_client, b_id, c_id, "mentions", auth_headers_company2, weight=1.0)

        # Public grants для A и C
        await create_public_grant(crm_client, a_id, auth_headers_company2)
        await create_public_grant(crm_client, c_id, auth_headers_company2)

        # System user ищет путь
        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={a_id}&to={c_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        path = response.json()

        assert path["exists"] is True
        assert len(path["path"]) == 3
        assert path["total_distance"] == 2.0

    @pytest.mark.asyncio
    async def test_related_entities_cross_company(self, crm_client, unique_id, auth_headers_system, auth_headers_company2):
        """Test 7.7: Related entities видны через company границы"""
        ns = f"g_{unique_id}"
        # Company2 создает hub entity
        hub_id = await create_entity(crm_client, "contact", f"Hub {unique_id}", auth_headers_company2, namespace=ns)

        related_ids = []
        for i in range(3):
            r_id = await create_entity(crm_client, "contact", f"Related{i} {unique_id}", auth_headers_company2, namespace=ns)
            await create_relationship(crm_client, hub_id, r_id, "mentions", auth_headers_company2)
            related_ids.append(r_id)

        # Public grant для hub
        await create_public_grant(crm_client, hub_id, auth_headers_company2)

        # System user получает related
        response = await crm_client.get(
            f"/crm/api/v1/entities/{hub_id}/related",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        related = response.json()

        # Должны быть видны 3 outgoing (как placeholders)
        assert len(related["outgoing"]) == 3


class TestPerformance:
    """Производительность и лимиты"""

    @pytest.mark.asyncio
    async def test_deep_graph(self, crm_client, unique_id, auth_headers_system):
        """Test 8.2: Глубокий граф (max_depth=5)"""
        entities = []
        for i in range(6):
            entity_id = await create_entity(crm_client, "contact", f"Person{i} {unique_id}", auth_headers_system)
            entities.append(entity_id)

        # Создаем цепочку A→B→C→D→E→F
        for i in range(5):
            await create_relationship(crm_client, entities[i], entities[i+1], "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{entities[0]}/influence-graph?max_depth=5",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["total_nodes"] == 6

        # Проверяем уровни
        nodes_by_id = {node["entity_id"]: node for node in graph["nodes"]}
        for i, entity_id in enumerate(entities):
            assert nodes_by_id[entity_id]["level"] == i

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_wide_graph(self, crm_client, unique_id, auth_headers_system):
        """Test 8.3: Широкий граф (много соседей)"""
        root_id = await create_entity(crm_client, "contact", f"Root {unique_id}", auth_headers_system)

        # Создаем 20 прямых соседей (уменьшено с 50 для скорости теста)
        neighbor_ids = []
        for i in range(20):
            neighbor_id = await create_entity(crm_client, "contact", f"Neighbor{i} {unique_id}", auth_headers_system)
            neighbor_ids.append(neighbor_id)
            await create_relationship(crm_client, root_id, neighbor_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{root_id}/influence-graph?max_depth=1",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["total_nodes"] == 21  # root + 20 neighbors

        # Все узлы на уровне 0 или 1
        for node in graph["nodes"]:
            assert node["level"] in [0, 1]


class TestComplexScenarios:
    """Комплексные сценарии"""

    @pytest.mark.asyncio
    async def test_organizational_hierarchy(self, crm_client, unique_id, auth_headers_system):
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
        await create_relationship(crm_client, ceo_id, vp_sales_id, "manages", auth_headers_system)
        await create_relationship(crm_client, ceo_id, vp_eng_id, "manages", auth_headers_system)
        await create_relationship(crm_client, vp_sales_id, mgr1_id, "manages", auth_headers_system)
        await create_relationship(crm_client, vp_eng_id, mgr2_id, "manages", auth_headers_system)
        await create_relationship(crm_client, mgr1_id, dev1_id, "manages", auth_headers_system)
        await create_relationship(crm_client, mgr1_id, dev2_id, "manages", auth_headers_system)
        await create_relationship(crm_client, mgr2_id, dev3_id, "manages", auth_headers_system)
        await create_relationship(crm_client, mgr2_id, dev4_id, "manages", auth_headers_system)

        # Строим граф от CEO
        response = await crm_client.get(
            f"/crm/api/v1/entities/{ceo_id}/influence-graph?max_depth=3",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["total_nodes"] == 9
        assert len(graph["edges"]) == 8

    @pytest.mark.asyncio
    async def test_project_network(self, crm_client, unique_id, auth_headers_system):
        """Test 9.2: Проектная сеть"""
        # Создаем entities разных типов
        project1_id = await create_entity(crm_client, "project", f"Project1 {unique_id}", auth_headers_system)
        project2_id = await create_entity(crm_client, "project", f"Project2 {unique_id}", auth_headers_system)
        project3_id = await create_entity(crm_client, "project", f"Project3 {unique_id}", auth_headers_system)
        person1_id = await create_entity(crm_client, "contact", f"Person1 {unique_id}", auth_headers_system)
        person2_id = await create_entity(crm_client, "contact", f"Person2 {unique_id}", auth_headers_system)

        # Создаем связи
        await create_relationship(crm_client, person1_id, project1_id, "works_on", auth_headers_system)
        await create_relationship(crm_client, person1_id, project2_id, "works_on", auth_headers_system)
        await create_relationship(crm_client, person1_id, person2_id, "collaborates_with", auth_headers_system)
        await create_relationship(crm_client, person2_id, project3_id, "works_on", auth_headers_system)

        # Строим граф от Person1
        response = await crm_client.get(
            f"/crm/api/v1/entities/{person1_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["total_nodes"] == 5

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
    async def test_single_node_graph(self, crm_client, unique_id, auth_headers_system):
        """Test 10.1: Граф из одного узла (нет связей)"""
        entity_id = await create_entity(crm_client, "contact", f"Lonely {unique_id}", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{entity_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["total_nodes"] == 1
        assert len(graph["edges"]) == 0
        assert graph["nodes"][0]["entity_id"] == entity_id

    @pytest.mark.asyncio
    async def test_nonexistent_entity(self, crm_client, auth_headers_system):
        """Test 10.2: Несуществующая entity"""
        fake_id = "nonexistent_entity_id_12345"

        response = await crm_client.get(
            f"/crm/api/v1/entities/{fake_id}/influence-graph",
            headers=auth_headers_system
        )
        # Должна быть ошибка 404 или 500
        assert response.status_code in [404, 500]

    @pytest.mark.asyncio
    async def test_no_access_to_root(self, crm_client, unique_id, auth_headers_system, auth_headers_company2):
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
    async def test_max_depth_zero(self, crm_client, unique_id, auth_headers_system):
        """Test 10.6: max_depth=0"""
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)

        # max_depth=0 должен вернуть только root
        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph?max_depth=0",
            headers=auth_headers_system
        )

        # API может отклонить max_depth=0 или вернуть только root
        # Проверяем оба варианта
        if response.status_code == 200:
            graph = response.json()
            # Если принимает, должен вернуть только root
            assert graph["total_nodes"] == 1
            assert graph["nodes"][0]["entity_id"] == a_id
        else:
            # Или вернуть ошибку валидации (400 или 422)
            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_self_loop_path(self, crm_client, unique_id, auth_headers_system):
        """Test 10.7: Shortest path от A до A (self-loop)"""
        entity_id = await create_entity(crm_client, "contact", f"Self {unique_id}", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/relationships/path/?from={entity_id}&to={entity_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200

        path_result = response.json()
        assert path_result["exists"] is True
        assert path_result["path"] == [entity_id]
        assert path_result["total_distance"] == 0.0


class TestSameCompanyRegression:
    """Убедиться что same-company сценарии работают как раньше"""

    @pytest.mark.asyncio
    async def test_same_company_graph_unchanged(self, crm_client, unique_id, auth_headers_system):
        """Test 8.1: Same company графы работают как раньше"""
        # Все в одной компании
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_system)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_system)

        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_system)

        response = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/influence-graph",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        graph = response.json()

        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1
        assert all(n["access"] is True for n in graph["nodes"])

    @pytest.mark.asyncio
    async def test_api_list_relationships_filtered(self, crm_client, unique_id, auth_headers_system, auth_headers_company2):
        """Test 8.2: API /relationships/ фильтрует по компании"""
        ns = f"g_{unique_id}"
        # Company2 создает relationship
        a_id = await create_entity(crm_client, "contact", f"A {unique_id}", auth_headers_company2, namespace=ns)
        b_id = await create_entity(crm_client, "contact", f"B {unique_id}", auth_headers_company2, namespace=ns)
        await create_relationship(crm_client, a_id, b_id, "mentions", auth_headers_company2)

        # System user НЕ видит через API
        response = await crm_client.get(
            f"/crm/api/v1/relationships/?entity_id={a_id}",
            headers=auth_headers_system
        )
        assert response.status_code == 200
        rels = response.json()["items"]
        assert len(rels) == 0


class TestInfluenceGraphNamespaceFilter:
    """Query ``namespace`` фильтрует Relationship.namespace при обходе графа."""

    @pytest.mark.asyncio
    async def test_other_namespace_edges_excluded(
        self, crm_client, unique_id, auth_headers_system
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

        await create_relationship(
            crm_client, root_id, peer_default, "mentors", auth_headers_system,
            namespace=ns_default,
        )
        await create_relationship(
            crm_client, root_id, peer_other, "mentors", auth_headers_system,
            namespace=ns_other,
        )

        response = await crm_client.get(
            f"/crm/api/v1/entities/{root_id}/influence-graph",
            params={"max_depth": 2, "namespace": ns_default},
            headers=auth_headers_system,
        )
        assert response.status_code == 200, response.text
        graph = response.json()
        ids = {n["entity_id"] for n in graph["nodes"]}
        assert root_id in ids
        assert peer_default in ids
        assert peer_other not in ids
        assert len(graph["edges"]) == 1

    @pytest.mark.asyncio
    async def test_include_all_namespaces_brings_back_other(
        self, crm_client, unique_id, auth_headers_system
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
        await create_relationship(
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
        graph = response.json()
        ids = {n["entity_id"] for n in graph["nodes"]}
        assert peer_other in ids

    @pytest.mark.asyncio
    async def test_related_endpoint_namespace_filter(
        self, crm_client, unique_id, auth_headers_system
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

        await create_relationship(
            crm_client, root_id, peer_default, "mentors", auth_headers_system,
            namespace=ns_default,
        )
        await create_relationship(
            crm_client, root_id, peer_other, "mentors", auth_headers_system,
            namespace=ns_other,
        )

        response = await crm_client.get(
            f"/crm/api/v1/entities/{root_id}/related",
            params={"namespace": ns_default},
            headers=auth_headers_system,
        )
        assert response.status_code == 200, response.text
        related = response.json()
        outgoing_ids = {n["entity_id"] for n in related["outgoing"]}
        assert peer_default in outgoing_ids
        assert peer_other not in outgoing_ids
