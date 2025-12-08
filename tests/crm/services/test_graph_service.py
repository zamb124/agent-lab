"""
Тесты для GraphService.

GraphService строит Knowledge Graph на основе сущностей и связей.
"""

import pytest
import pytest_asyncio

from apps.crm.models.entity_models import EntityCreate
from apps.crm.models.relationship_models import RelationshipCreate


@pytest_asyncio.fixture
async def graph_service(crm_container, test_context):
    """GraphService для тестов"""
    return crm_container.graph_service


@pytest_asyncio.fixture
async def graph_test_data(crm_container, test_context, unique_id):
    """
    Создает тестовые данные для графа:
    - 3 сущности (person, organization, project)
    - 2 связи между ними
    """
    entity_service = crm_container.entity_service
    relationship_service = crm_container.relationship_service
    
    # Создаем сущности
    person = await entity_service.create_entity(EntityCreate(
        type="person",
        name=f"Graph Test Person {unique_id('graph')}",
        description="Person for graph test",
        attributes={"role": "developer"},
    ))
    
    org = await entity_service.create_entity(EntityCreate(
        type="organization",
        name=f"Graph Test Org {unique_id('graph')}",
        description="Organization for graph test",
        attributes={"industry": "tech"},
    ))
    
    project = await entity_service.create_entity(EntityCreate(
        type="project",
        name=f"Graph Test Project {unique_id('graph')}",
        description="Project for graph test",
        attributes={"status": "active"},
    ))
    
    # Создаем связи
    rel1 = await relationship_service.create_relationship(RelationshipCreate(
        source_entity_id=person.entity_id,
        target_entity_id=org.entity_id,
        relationship_type="works_for",
        weight=1.0,
        attributes={},
    ))
    
    rel2 = await relationship_service.create_relationship(RelationshipCreate(
        source_entity_id=person.entity_id,
        target_entity_id=project.entity_id,
        relationship_type="works_on",
        weight=0.8,
        attributes={},
    ))
    
    yield {
        "person": person,
        "org": org,
        "project": project,
        "relationships": [rel1, rel2],
    }
    
    # Cleanup
    await relationship_service.delete_relationship(rel1.relationship_id)
    await relationship_service.delete_relationship(rel2.relationship_id)
    await entity_service.delete_entity(person.entity_id)
    await entity_service.delete_entity(org.entity_id)
    await entity_service.delete_entity(project.entity_id)


@pytest.mark.asyncio
async def test_get_full_graph(graph_service, graph_test_data, test_context):
    """Тест получения полного графа"""
    result = await graph_service.get_full_graph(limit=100)
    
    assert "nodes" in result
    assert "edges" in result
    assert "stats" in result
    
    assert isinstance(result["nodes"], list)
    assert isinstance(result["edges"], list)
    
    # Должны быть наши тестовые данные
    node_ids = [n["id"] for n in result["nodes"]]
    assert graph_test_data["person"].entity_id in node_ids
    assert graph_test_data["org"].entity_id in node_ids
    assert graph_test_data["project"].entity_id in node_ids
    
    # Проверяем структуру узла
    if result["nodes"]:
        node = result["nodes"][0]
        assert "id" in node
        assert "type" in node
        assert "name" in node
        assert "color" in node


@pytest.mark.asyncio
async def test_get_full_graph_filter_by_type(graph_service, graph_test_data, test_context):
    """Тест фильтрации графа по типу"""
    result = await graph_service.get_full_graph(
        entity_types=["person"],
        limit=100
    )
    
    # Все узлы должны быть person
    for node in result["nodes"]:
        assert node["type"] == "person"


@pytest.mark.asyncio
async def test_get_entity_graph(graph_service, graph_test_data, test_context):
    """Тест получения графа для конкретной сущности"""
    person_id = graph_test_data["person"].entity_id
    
    result = await graph_service.get_entity_graph(person_id, depth=1)
    
    assert "nodes" in result
    assert "edges" in result
    assert "center_entity_id" in result
    assert "depth" in result
    assert "stats" in result
    
    assert result["center_entity_id"] == person_id
    assert result["depth"] == 1
    
    # Центральная сущность должна быть в узлах
    node_ids = [n["id"] for n in result["nodes"]]
    assert person_id in node_ids
    
    # Должен быть хотя бы один is_center=True
    center_nodes = [n for n in result["nodes"] if n.get("is_center")]
    assert len(center_nodes) == 1
    assert center_nodes[0]["id"] == person_id


@pytest.mark.asyncio
async def test_get_entity_graph_with_depth(graph_service, graph_test_data, test_context):
    """Тест глубины обхода графа"""
    person_id = graph_test_data["person"].entity_id
    
    # Глубина 1 - только прямые связи
    result_depth_1 = await graph_service.get_entity_graph(person_id, depth=1)
    
    # Глубина 2 - включая связи связанных
    result_depth_2 = await graph_service.get_entity_graph(person_id, depth=2)
    
    # С большей глубиной должно быть >= узлов
    assert len(result_depth_2["nodes"]) >= len(result_depth_1["nodes"])


@pytest.mark.asyncio
async def test_get_relationship_types(graph_service, graph_test_data, test_context):
    """Тест получения типов связей"""
    result = await graph_service.get_relationship_types()
    
    assert isinstance(result, list)
    
    # Должны быть наши типы связей
    assert "works_for" in result
    assert "works_on" in result


@pytest.mark.asyncio
async def test_get_full_graph_empty(graph_service, test_context):
    """Тест пустого графа"""
    # Получаем граф (может быть пустой или с данными от других тестов)
    result = await graph_service.get_full_graph(limit=1)
    
    assert "nodes" in result
    assert "edges" in result
    assert "stats" in result
    
    assert result["stats"]["total_nodes"] == len(result["nodes"])
    assert result["stats"]["total_edges"] == len(result["edges"])


@pytest.mark.asyncio
async def test_get_entity_graph_nonexistent(graph_service, test_context):
    """Тест графа для несуществующей сущности"""
    result = await graph_service.get_entity_graph("nonexistent_entity_id", depth=1)
    
    # Должен вернуть пустой граф
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["center_entity_id"] == "nonexistent_entity_id"


@pytest.mark.asyncio
async def test_graph_node_structure(graph_service, graph_test_data, test_context):
    """Тест структуры узла графа"""
    result = await graph_service.get_full_graph(limit=10)
    
    if result["nodes"]:
        node = result["nodes"][0]
        
        # Обязательные поля
        assert "id" in node
        assert "type" in node
        assert "name" in node
        assert "color" in node
        assert "attributes" in node


@pytest.mark.asyncio
async def test_graph_edge_structure(graph_service, graph_test_data, test_context):
    """Тест структуры ребра графа"""
    result = await graph_service.get_full_graph(limit=100)
    
    if result["edges"]:
        edge = result["edges"][0]
        
        # Обязательные поля
        assert "source" in edge
        assert "target" in edge
        assert "type" in edge
        assert "weight" in edge

