"""
Тесты для полей variables в API flows.
Проверяет что все метаданные (value, title, description, order, public) сохраняются и возвращаются.
"""

import pytest


class TestFlowVariables:
    """Тесты на полную структуру variables в API flows"""

    @pytest.mark.asyncio
    async def test_create_agent_with_full_variables(self, client, app, unique_id):
        """POST создаёт агента с полными метаданными variables"""
        flow_id = f"test_vars_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Variables Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test @var:role", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {
                    "role": {
                        "value": "You are a helpful assistant",
                        "title": "Роль",
                        "description": "Роль агента",
                        "order": 1,
                        "public": True,
                    },
                    "goal": {
                        "value": "Help users",
                        "title": "Цель",
                        "description": "Цель агента",
                        "order": 2,
                        "public": False,
                    },
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "variables" in data
        assert "role" in data["variables"]
        role = data["variables"]["role"]
        assert role["value"] == "You are a helpful assistant"
        assert role["title"] == "Роль"
        assert role["description"] == "Роль агента"
        assert role["order"] == 1
        assert role["public"] is True
        goal = data["variables"]["goal"]
        assert goal["value"] == "Help users"
        assert goal["title"] == "Цель"
        assert goal["order"] == 2
        assert goal["public"] is False
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_get_agent_returns_full_variables(self, client, app, unique_id):
        """GET возвращает все поля variables (value, title, description, order, public)"""
        flow_id = f"test_get_vars_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Get Variables",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {
                    "api_key": {
                        "value": "secret123",
                        "title": "API Key",
                        "description": "Ключ доступа",
                        "order": 5,
                        "public": False,
                    }
                },
            },
        )
        response = await client.get(f"/flows/api/v1/flows/{flow_id}")
        assert response.status_code == 200
        data = response.json()
        api_key = data["variables"]["api_key"]
        assert api_key["value"] == "secret123"
        assert api_key["title"] == "API Key"
        assert api_key["description"] == "Ключ доступа"
        assert api_key["order"] == 5
        assert api_key["public"] is False
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_update_agent_preserves_variables(self, client, app, unique_id):
        """PUT сохраняет все поля variables"""
        flow_id = f"test_upd_vars_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Update Variables",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {"setting": {"value": "initial", "title": "Setting", "order": 1}},
            },
        )
        response = await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": "Updated Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Updated", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {
                    "setting": {
                        "value": "updated",
                        "title": "Updated Setting",
                        "description": "New description",
                        "order": 10,
                        "public": True,
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        setting = data["variables"]["setting"]
        assert setting["value"] == "updated"
        assert setting["title"] == "Updated Setting"
        assert setting["description"] == "New description"
        assert setting["order"] == 10
        assert setting["public"] is True
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_list_agents_returns_full_variables(self, client, app, unique_id):
        """GET /flows/ возвращает полную структуру variables для каждого агента"""
        flow_id = f"test_list_vars_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test List Variables",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {"config": {"value": "test", "title": "Config", "order": 3}},
            },
        )
        response = await client.get("/flows/api/v1/flows/")
        assert response.status_code == 200
        agents = response.json()["items"]
        test_agent = next((a for a in agents if a["flow_id"] == flow_id), None)
        assert test_agent is not None
        config = test_agent["variables"]["config"]
        assert config["value"] == "test"
        assert config["title"] == "Config"
        assert config["order"] == 3
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_branch_variables_full_structure(self, client, app, unique_id):
        """Branches содержат полную структуру variables"""
        flow_id = f"test_branch_vars_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Branch Variables",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "@var:role", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {
                    "role": {
                        "value": "Base role",
                        "title": "Роль",
                        "description": "Роль агента",
                        "order": 1,
                    }
                },
                "branches": {
                    "custom_branch": {
                        "name": "Custom Branch",
                        "description": "Test branch",
                        "variables": {
                            "branch_param": {
                                "value": "branch_value",
                                "title": "Branch Param",
                                "description": "Параметр ветки",
                                "order": 5,
                                "public": True,
                            }
                        },
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        branch = data["branches"]["custom_branch"]
        branch_param = branch["variables"]["branch_param"]
        assert branch_param["value"] == "branch_value"
        assert branch_param["title"] == "Branch Param"
        assert branch_param["description"] == "Параметр ветки"
        assert branch_param["order"] == 5
        assert branch_param["public"] is True
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_branch_variables_simple_value_normalized(self, client, app, unique_id):
        """Простые значения в branch.variables нормализуются в полную структуру"""
        flow_id = f"test_branch_simple_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Simple Branch Variables",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {},
                "branches": {
                    "simple_branch": {
                        "name": "Simple Branch",
                        "variables": {"role": "Custom role value"},
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        branch = data["branches"]["simple_branch"]
        role = branch["variables"]["role"]
        assert role["value"] == "Custom role value"
        assert role.get("public") is False
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_variable_value_can_be_json_object(self, client, app, unique_id):
        """value переменной может быть JSON объектом (dict), а не только строкой"""
        flow_id = f"test_json_value_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test JSON Value",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {
                    "config": {
                        "value": {
                            "api_url": "https://example.com",
                            "timeout": 30,
                            "options": {"retry": True, "max_retries": 3},
                        },
                        "title": "Configuration",
                        "description": "JSON config object",
                        "order": 1,
                        "public": False,
                    },
                    "list_param": {
                        "value": ["item1", "item2", "item3"],
                        "title": "List Parameter",
                        "order": 2,
                    },
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        config = data["variables"]["config"]
        assert config["value"] == {
            "api_url": "https://example.com",
            "timeout": 30,
            "options": {"retry": True, "max_retries": 3},
        }
        assert config["title"] == "Configuration"
        assert config["description"] == "JSON config object"
        assert config["order"] == 1
        list_param = data["variables"]["list_param"]
        assert list_param["value"] == ["item1", "item2", "item3"]
        assert list_param["title"] == "List Parameter"
        assert list_param["order"] == 2
        get_response = await client.get(f"/flows/api/v1/flows/{flow_id}")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["variables"]["config"]["value"]["api_url"] == "https://example.com"
        assert get_data["variables"]["config"]["value"]["options"]["retry"] is True
        await client.delete(f"/flows/api/v1/flows/{flow_id}")


class TestBranchesAPIVariables:
    """Тесты на variables в отдельных ручках branches."""

    @pytest.mark.asyncio
    async def test_get_branch_returns_full_variables(self, client, app, unique_id):
        """GET /flows/{id}/branches/{branch_id} возвращает полную структуру variables"""
        flow_id = f"test_branch_api_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Branch API",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "@var:role", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {},
                "branches": {
                    "my_branch": {
                        "name": "My Branch",
                        "description": "Test branch",
                        "variables": {
                            "role": {
                                "value": "Branch role",
                                "title": "Role Title",
                                "description": "Role description",
                                "order": 10,
                                "public": True,
                            }
                        },
                    }
                },
            },
        )
        response = await client.get(f"/flows/api/v1/{flow_id}/branches/my_branch")
        assert response.status_code == 200
        data = response.json()
        variables = data["variables"]
        assert "role" in variables
        role = variables["role"]
        assert role["value"] == "Branch role"
        assert role["title"] == "Role Title"
        assert role["description"] == "Role description"
        assert role["order"] == 10
        assert role["public"] is True
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_create_branch_with_full_variables(self, client, app, unique_id):
        """POST /flows/{id}/branches создаёт branch с полными variables"""
        flow_id = f"test_create_branch_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Create Branch",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {},
            },
        )
        response = await client.post(
            f"/flows/api/v1/{flow_id}/branches",
            json={
                "branch_id": "new_branch",
                "name": "New Branch",
                "description": "Created via API",
                "variables": {
                    "param": {
                        "value": "param_value",
                        "title": "Param Title",
                        "description": "Param desc",
                        "order": 5,
                        "public": False,
                    }
                },
            },
        )
        assert response.status_code == 201
        get_response = await client.get(f"/flows/api/v1/{flow_id}/branches/new_branch")
        assert get_response.status_code == 200
        data = get_response.json()
        variables = data["variables"]
        assert "param" in variables
        param = variables["param"]
        assert param["value"] == "param_value"
        assert param["title"] == "Param Title"
        assert param["order"] == 5
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_update_branch_preserves_variables(self, client, app, unique_id):
        """PUT /flows/{id}/branches/{branch_id} сохраняет все поля variables"""
        flow_id = f"test_update_branch_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Update Branch",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "variables": {},
                "branches": {
                    "updatable": {
                        "name": "Updatable Branch",
                        "variables": {"config": {"value": "old", "title": "Config", "order": 1}},
                    }
                },
            },
        )
        response = await client.put(
            f"/flows/api/v1/{flow_id}/branches/updatable",
            json={
                "name": "Updated Branch",
                "variables": {
                    "config": {
                        "value": "new_value",
                        "title": "Updated Config",
                        "description": "New description",
                        "order": 99,
                        "public": True,
                    }
                },
            },
        )
        assert response.status_code == 200
        get_response = await client.get(f"/flows/api/v1/{flow_id}/branches/updatable")
        assert get_response.status_code == 200
        data = get_response.json()
        variables = data["variables"]
        config = variables["config"]
        assert config["value"] == "new_value"
        assert config["title"] == "Updated Config"
        assert config["description"] == "New description"
        assert config["order"] == 99
        assert config["public"] is True
        await client.delete(f"/flows/api/v1/flows/{flow_id}")
