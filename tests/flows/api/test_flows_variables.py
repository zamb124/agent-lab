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
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test @var:role",
                        "tools": [],
                    }
                },
                "edges": [{"from": "main", "to": None}],
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
        
        # Проверяем что все поля variables вернулись
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
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_get_agent_returns_full_variables(self, client, app, unique_id):
        """GET возвращает все поля variables (value, title, description, order, public)"""
        flow_id = f"test_get_vars_{unique_id}"
        
        # Создаём агента с полными variables
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Get Variables",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
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
        
        # GET возвращает полную структуру
        response = await client.get(f"/flows/api/v1/flows/{flow_id}")
        assert response.status_code == 200
        data = response.json()
        
        api_key = data["variables"]["api_key"]
        assert api_key["value"] == "secret123"
        assert api_key["title"] == "API Key"
        assert api_key["description"] == "Ключ доступа"
        assert api_key["order"] == 5
        assert api_key["public"] is False
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_update_agent_preserves_variables(self, client, app, unique_id):
        """PUT сохраняет все поля variables"""
        flow_id = f"test_upd_vars_{unique_id}"
        
        # Создаём
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Update Variables",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
                "variables": {
                    "setting": {
                        "value": "initial",
                        "title": "Setting",
                        "order": 1,
                    }
                },
            },
        )
        
        # Обновляем с новыми variables
        response = await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": "Updated Agent",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Updated", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
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
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_list_agents_returns_full_variables(self, client, app, unique_id):
        """GET /flows/ возвращает полную структуру variables для каждого агента"""
        flow_id = f"test_list_vars_{unique_id}"
        
        # Создаём агента
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test List Variables",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
                "variables": {
                    "config": {
                        "value": "test",
                        "title": "Config",
                        "order": 3,
                    }
                },
            },
        )
        
        # Получаем список
        response = await client.get("/flows/api/v1/flows/")
        assert response.status_code == 200
        agents = response.json()["items"]
        
        # Находим наш агент
        test_agent = next((a for a in agents if a["flow_id"] == flow_id), None)
        assert test_agent is not None
        
        config = test_agent["variables"]["config"]
        assert config["value"] == "test"
        assert config["title"] == "Config"
        assert config["order"] == 3
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_skill_variables_full_structure(self, client, app, unique_id):
        """Skills содержат полную структуру variables"""
        flow_id = f"test_skill_vars_{unique_id}"
        
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Skill Variables",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "@var:role", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
                "variables": {
                    "role": {
                        "value": "Base role",
                        "title": "Роль",
                        "description": "Роль агента",
                        "order": 1,
                    }
                },
                "branches": {
                    "custom_skill": {
                        "name": "Custom Skill",
                        "description": "Test skill",
                        "variables": {
                            "skill_param": {
                                "value": "skill_value",
                                "title": "Skill Param",
                                "description": "Параметр скила",
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
        
        # Проверяем variables в skill
        skill = data["branches"]["custom_skill"]
        skill_param = skill["variables"]["skill_param"]
        assert skill_param["value"] == "skill_value"
        assert skill_param["title"] == "Skill Param"
        assert skill_param["description"] == "Параметр скила"
        assert skill_param["order"] == 5
        assert skill_param["public"] is True
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_skill_variables_simple_value_normalized(self, client, app, unique_id):
        """Простые значения в skill.variables нормализуются в полную структуру"""
        flow_id = f"test_skill_simple_{unique_id}"
        
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Simple Skill Variables",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
                "variables": {},
                "branches": {
                    "simple_skill": {
                        "name": "Simple Skill",
                        "variables": {
                            "role": "Custom role value",
                        },
                    }
                },
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Простое значение должно быть нормализовано
        skill = data["branches"]["simple_skill"]
        role = skill["variables"]["role"]
        assert role["value"] == "Custom role value"
        # Остальные поля должны быть None/False по умолчанию
        assert role.get("public") is False
        
        # Cleanup
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
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
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
        
        # Проверяем что value вернулся как объект
        config = data["variables"]["config"]
        assert config["value"] == {
            "api_url": "https://example.com",
            "timeout": 30,
            "options": {"retry": True, "max_retries": 3},
        }
        assert config["title"] == "Configuration"
        assert config["description"] == "JSON config object"
        assert config["order"] == 1
        
        # Проверяем list
        list_param = data["variables"]["list_param"]
        assert list_param["value"] == ["item1", "item2", "item3"]
        assert list_param["title"] == "List Parameter"
        assert list_param["order"] == 2
        
        # GET тоже должен вернуть объект
        get_response = await client.get(f"/flows/api/v1/flows/{flow_id}")
        assert get_response.status_code == 200
        get_data = get_response.json()
        
        assert get_data["variables"]["config"]["value"]["api_url"] == "https://example.com"
        assert get_data["variables"]["config"]["value"]["options"]["retry"] is True
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")


class TestSkillsAPIVariables:
    """Тесты на variables в отдельных ручках skills (/flows/{id}/skills)"""

    @pytest.mark.asyncio
    async def test_get_skill_returns_full_variables(self, client, app, unique_id):
        """GET /flows/{id}/branches/{branch_id} возвращает полную структуру variables"""
        flow_id = f"test_skill_api_{unique_id}"
        
        # Создаём агента с skill
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Skill API",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "@var:role", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
                "variables": {},
                "branches": {
                    "my_skill": {
                        "name": "My Skill",
                        "description": "Test skill",
                        "variables": {
                            "role": {
                                "value": "Skill role",
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
        
        # Получаем skill через a2a API
        response = await client.get(f"/flows/api/v1/{flow_id}/branches/my_skill")
        assert response.status_code == 200
        data = response.json()
        
        # Проверяем variables в branch_body
        branch_body = data.get("branch_body", {})
        variables = branch_body.get("variables", {})
        
        assert "role" in variables
        role = variables["role"]
        assert role["value"] == "Skill role"
        assert role["title"] == "Role Title"
        assert role["description"] == "Role description"
        assert role["order"] == 10
        assert role["public"] is True
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_create_skill_with_full_variables(self, client, app, unique_id):
        """POST /flows/{id}/skills создаёт skill с полными variables"""
        flow_id = f"test_create_skill_{unique_id}"
        
        # Создаём агента без skills
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Create Skill",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
                "variables": {},
            },
        )
        
        # Создаём skill через API
        response = await client.post(
            f"/flows/api/v1/{flow_id}/branches",
            json={
                "branch_id": "new_skill",
                "name": "New Skill",
                "description": "Created via API",
                "branch_body": {
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
            },
        )
        
        assert response.status_code == 201
        
        # Проверяем что skill создан с variables
        get_response = await client.get(f"/flows/api/v1/{flow_id}/branches/new_skill")
        assert get_response.status_code == 200
        data = get_response.json()
        
        branch_body = data.get("branch_body", {})
        variables = branch_body.get("variables", {})
        
        assert "param" in variables
        param = variables["param"]
        assert param["value"] == "param_value"
        assert param["title"] == "Param Title"
        assert param["order"] == 5
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_update_skill_preserves_variables(self, client, app, unique_id):
        """PUT /flows/{id}/branches/{branch_id} сохраняет все поля variables"""
        flow_id = f"test_update_skill_{unique_id}"
        
        # Создаём агента с skill
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Update Skill",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test", "tools": []}
                },
                "edges": [{"from": "main", "to": None}],
                "variables": {},
                "branches": {
                    "updatable": {
                        "name": "Updatable Skill",
                        "variables": {
                            "config": {"value": "old", "title": "Config", "order": 1}
                        },
                    }
                },
            },
        )
        
        # Обновляем skill
        response = await client.put(
            f"/flows/api/v1/{flow_id}/branches/updatable",
            json={
                "name": "Updated Skill",
                "branch_body": {
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
            },
        )
        
        assert response.status_code == 200
        
        # Проверяем обновлённый skill
        get_response = await client.get(f"/flows/api/v1/{flow_id}/branches/updatable")
        assert get_response.status_code == 200
        data = get_response.json()
        
        branch_body = data.get("branch_body", {})
        variables = branch_body.get("variables", {})
        
        config = variables["config"]
        assert config["value"] == "new_value"
        assert config["title"] == "Updated Config"
        assert config["description"] == "New description"
        assert config["order"] == 99
        assert config["public"] is True
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

