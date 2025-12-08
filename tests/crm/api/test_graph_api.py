"""
Тесты для API Knowledge Graph CRM.

Тестируются endpoints:
- GET /crm/api/v1/graph
- GET /crm/api/v1/graph/entity/{entity_id}
- GET /crm/api/v1/graph/relationship-types
"""

import pytest


@pytest.fixture
async def graph_api_data(crm_client, unique_id):
    """
    Создает тестовые данные для графа через API.
    """
    # Создаем сущности
    person_payload = {
        "type": "person",
        "name": f"Graph API Person {unique_id('graph_api')}",
        "description": "Person for graph API test",
        "attributes": {"role": "developer"},
    }
    person_response = await crm_client.post("/crm/api/v1/entities", json=person_payload)
    person = person_response.json()
    
    org_payload = {
        "type": "organization",
        "name": f"Graph API Org {unique_id('graph_api')}",
        "description": "Organization for graph API test",
        "attributes": {},
    }
    org_response = await crm_client.post("/crm/api/v1/entities", json=org_payload)
    org = org_response.json()
    
    # Создаем связь
    rel_payload = {
        "source_entity_id": person["entity_id"],
        "target_entity_id": org["entity_id"],
        "relationship_type": "works_at",
        "weight": 1.0,
        "attributes": {},
    }
    rel_response = await crm_client.post("/crm/api/v1/relationships", json=rel_payload)
    relationship = rel_response.json()
    
    yield {
        "person": person,
        "org": org,
        "relationship": relationship,
    }
    
    # Cleanup
    if relationship.get("relationship_id"):
        await crm_client.delete(f"/crm/api/v1/relationships/{relationship['relationship_id']}")
    await crm_client.delete(f"/crm/api/v1/entities/{person['entity_id']}")
    await crm_client.delete(f"/crm/api/v1/entities/{org['entity_id']}")


@pytest.mark.asyncio
async def test_get_full_graph(crm_client, graph_api_data):
    """Тест получения полного графа"""
    response = await crm_client.get("/crm/api/v1/graph")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "nodes" in data
    assert "edges" in data
    assert "stats" in data
    
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)


@pytest.mark.asyncio
async def test_get_full_graph_with_limit(crm_client):
    """Тест графа с лимитом"""
    response = await crm_client.get("/crm/api/v1/graph?limit=10")
    
    assert response.status_code == 200
    data = response.json()
    assert data["stats"]["total_nodes"] <= 10


@pytest.mark.asyncio
async def test_get_full_graph_filter_by_types(crm_client, graph_api_data):
    """Тест фильтрации графа по типам"""
    response = await crm_client.get("/crm/api/v1/graph?entity_types=person,organization")
    
    assert response.status_code == 200
    data = response.json()
    
    for node in data["nodes"]:
        assert node["type"] in ["person", "organization"]


@pytest.mark.asyncio
async def test_get_entity_graph(crm_client, graph_api_data):
    """Тест получения графа для сущности"""
    person_id = graph_api_data["person"]["entity_id"]
    
    response = await crm_client.get(f"/crm/api/v1/graph/entity/{person_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "nodes" in data
    assert "edges" in data
    assert "center_entity_id" in data
    assert "depth" in data
    assert "stats" in data
    
    assert data["center_entity_id"] == person_id


@pytest.mark.asyncio
async def test_get_entity_graph_with_depth(crm_client, graph_api_data):
    """Тест графа с указанием глубины"""
    person_id = graph_api_data["person"]["entity_id"]
    
    response = await crm_client.get(f"/crm/api/v1/graph/entity/{person_id}?depth=3")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["depth"] == 3


@pytest.mark.asyncio
async def test_get_entity_graph_nonexistent(crm_client):
    """Тест графа для несуществующей сущности"""
    response = await crm_client.get("/crm/api/v1/graph/entity/nonexistent_entity_id")
    
    assert response.status_code == 200
    data = response.json()
    
    # Должен вернуть пустой граф
    assert data["nodes"] == []
    assert data["edges"] == []


@pytest.mark.asyncio
async def test_get_relationship_types(crm_client, graph_api_data):
    """Тест получения типов связей"""
    response = await crm_client.get("/crm/api/v1/graph/relationship-types")
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert "works_at" in data


@pytest.mark.asyncio
async def test_graph_node_structure(crm_client, graph_api_data):
    """Тест структуры узла"""
    response = await crm_client.get("/crm/api/v1/graph?limit=5")
    
    assert response.status_code == 200
    data = response.json()
    
    if data["nodes"]:
        node = data["nodes"][0]
        assert "id" in node
        assert "type" in node
        assert "name" in node
        assert "color" in node


@pytest.mark.asyncio
async def test_graph_edge_structure(crm_client, graph_api_data):
    """Тест структуры ребра"""
    response = await crm_client.get("/crm/api/v1/graph?limit=100")
    
    assert response.status_code == 200
    data = response.json()
    
    if data["edges"]:
        edge = data["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "type" in edge
        assert "weight" in edge


@pytest.mark.asyncio
async def test_graph_stats(crm_client, graph_api_data):
    """Тест статистики графа"""
    response = await crm_client.get("/crm/api/v1/graph")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "stats" in data
    assert "total_nodes" in data["stats"]
    assert "total_edges" in data["stats"]
    
    assert data["stats"]["total_nodes"] == len(data["nodes"])
    assert data["stats"]["total_edges"] == len(data["edges"])


@pytest.mark.asyncio
async def test_entity_graph_center_marker(crm_client, graph_api_data):
    """Тест маркера центральной сущности"""
    person_id = graph_api_data["person"]["entity_id"]
    
    response = await crm_client.get(f"/crm/api/v1/graph/entity/{person_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    # Должен быть узел с is_center=True
    center_nodes = [n for n in data["nodes"] if n.get("is_center")]
    
    if center_nodes:
        assert len(center_nodes) == 1
        assert center_nodes[0]["id"] == person_id

