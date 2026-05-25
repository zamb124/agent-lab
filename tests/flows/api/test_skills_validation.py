"""
Строгие тесты валидации и сохранения веток (branches) через API.

Проверяет что create_branch и update_branch:
- Сохраняют переменные (включая переопределение во ветке)
- Сохраняют свойства нод
- Сохраняют ноды
- Сохраняют условия (conditions)
- Валидируют результат применения ветки
- Отклоняют невалидные конфигурации
"""

import pytest


@pytest.mark.asyncio
class TestSkillValidationAndPersistence:
    """Тесты валидации и сохранения веток."""

    async def test_create_skill_saves_variables(self, client, container, unique_id):
        """Создание skill сохраняет переменные."""
        flow_id = f"test_agent_vars_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
            "variables": {"base_var": "base_value", "shared_var": "from_base"},
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Test Skill",
            "description": "Skill with variables",
            "branch_body": {"variables": {"skill_var": "skill_value", "shared_var": "from_skill"}},
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        assert agent is not None
        assert branch_id in agent.branches
        skill = agent.branches[branch_id]
        skill_var = skill.variables["skill_var"]
        shared_var = skill.variables["shared_var"]
        assert skill_var == "skill_value" or (
            hasattr(skill_var, "value") and skill_var.value == "skill_value"
        )
        assert shared_var == "from_skill" or (
            hasattr(shared_var, "value") and shared_var.value == "from_skill"
        )
        effective = container.flow_factory.apply_branch(agent, branch_id)
        assert effective["variables"]["base_var"] == "base_value"
        assert effective["variables"]["skill_var"] == "skill_value"
        assert effective["variables"]["shared_var"] == "from_skill"

    async def test_create_skill_allows_company_variable_aliases(self, client, container, unique_id):
        """Создание ветки не падает на variables.*.value = @var:company_secret."""
        flow_id = f"test_agent_company_alias_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent With Company Alias",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "code",
                    "code": "async def run(args, state):\n    return state",
                    "input_mapping": {"bot_token": "@var:telegram_mirror_bot_token"},
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
            "variables": {
                "telegram_mirror_bot_token": {
                    "value": "@var:telegram_notify_bot_token",
                    "secret": True,
                }
            },
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        resp = await client.post(
            f"/flows/api/v1/{flow_id}/branches",
            json={
                "branch_id": branch_id,
                "name": "Test Skill",
                "description": "Payload shape used by the branch create modal",
                "nodes": {},
                "edges": [],
            },
        )
        assert resp.status_code == 201, resp.text
        agent = await container.flow_repository.get(flow_id)
        assert agent is not None
        assert branch_id in agent.branches

    async def test_create_skill_saves_node_properties(self, client, container, unique_id):
        """Создание skill сохраняет свойства нод."""
        flow_id = f"test_agent_props_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Base prompt",
                    "tools": [],
                    "llm": {"model": "gpt-4o", "temperature": 0.7},
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Test Skill",
            "branch_body": {
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Skill prompt",
                        "llm": {"temperature": 0.1, "max_tokens": 1000},
                    }
                },
                "nodes_mode": "merge",
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        skill = agent.branches[branch_id]
        assert skill.nodes["main"]["prompt"] == "Skill prompt"
        assert skill.nodes["main"]["llm"]["temperature"] == 0.1
        assert skill.nodes["main"]["llm"]["max_tokens"] == 1000
        effective = container.flow_factory.apply_branch(agent, branch_id)
        assert effective["nodes"]["main"]["prompt"] == "Skill prompt"
        assert effective["nodes"]["main"]["llm"]["temperature"] == 0.1
        assert effective["nodes"]["main"]["llm"]["max_tokens"] == 1000

    async def test_create_skill_saves_nodes(self, client, container, unique_id):
        """Создание skill сохраняет ноды."""
        flow_id = f"test_agent_nodes_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['path'] = 'base'\n    return state",
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Test Skill",
            "branch_body": {
                "entry": "skill_main",
                "nodes": {
                    "skill_main": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['path'] = 'skill'\n    return state",
                    },
                    "skill_helper": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['helper'] = True\n    return state",
                    },
                },
                "edges": [
                    {"from_node": "skill_main", "to_node": "skill_helper"},
                    {"from_node": "skill_helper", "to_node": None},
                ],
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        skill = agent.branches[branch_id]
        assert skill.entry == "skill_main"
        assert "skill_main" in skill.nodes
        assert "skill_helper" in skill.nodes
        assert skill.nodes["skill_main"]["type"] == "code"
        assert "state['path'] = 'skill'" in skill.nodes["skill_main"]["code"]
        effective = container.flow_factory.apply_branch(agent, branch_id)
        assert effective["entry"] == "skill_main"
        assert "skill_main" in effective["nodes"]
        assert "skill_helper" in effective["nodes"]
        assert "main" not in effective["nodes"]

    async def test_create_skill_saves_conditions(self, client, container, unique_id):
        """Создание skill сохраняет условия (conditions) в edges."""
        flow_id = f"test_agent_cond_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['value'] = 10\n    return state",
                },
                "branch_a": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['branch'] = 'a'\n    return state",
                },
                "branch_b": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['branch'] = 'b'\n    return state",
                },
            },
            "edges": [
                {"from_node": "main", "to_node": "branch_a"},
                {"from_node": "branch_a", "to_node": None},
            ],
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Test Skill",
            "branch_body": {
                "edges": [
                    {
                        "from_node": "main",
                        "to_node": "branch_a",
                        "condition": {
                            "type": "simple",
                            "variable": "value",
                            "operator": ">",
                            "value": 5,
                        },
                    },
                    {
                        "from_node": "main",
                        "to_node": "branch_b",
                        "condition": {
                            "type": "simple",
                            "variable": "value",
                            "operator": "<=",
                            "value": 5,
                        },
                    },
                    {"from_node": "branch_a", "to_node": None},
                    {"from_node": "branch_b", "to_node": None},
                ]
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        skill = agent.branches[branch_id]
        assert len(skill.edges) == 4
        conditional_edges = [e for e in skill.edges if e.condition is not None]
        assert len(conditional_edges) == 2
        edge_to_a = next(
            (e for e in skill.edges if e.from_node == "main" and e.to_node == "branch_a")
        )
        assert edge_to_a.condition == "state.get('value', 0) > 5"
        edge_to_b = next(
            (e for e in skill.edges if e.from_node == "main" and e.to_node == "branch_b")
        )
        assert edge_to_b.condition == "state.get('value', 0) <= 5"
        effective = container.flow_factory.apply_branch(agent, branch_id)
        effective_edge_to_a = next(
            (e for e in effective["edges"] if e.from_node == "main" and e.to_node == "branch_a")
        )
        assert effective_edge_to_a.condition == "state.get('value', 0) > 5"

    async def test_update_skill_updates_variables(self, client, container, unique_id):
        """Обновление skill обновляет переменные."""
        flow_id = f"test_agent_update_vars_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
            "variables": {"base_var": "base"},
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Test Skill",
            "branch_body": {"variables": {"skill_var": "original"}},
        }
        create_skill_resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert create_skill_resp.status_code == 201
        update_data = {
            "branch_id": branch_id,
            "name": "Updated Skill",
            "branch_body": {"variables": {"skill_var": "updated", "new_var": "new_value"}},
        }
        update_resp = await client.put(
            f"/flows/api/v1/{flow_id}/branches/{branch_id}", json=update_data
        )
        assert update_resp.status_code == 200
        agent = await container.flow_repository.get(flow_id)
        skill = agent.branches[branch_id]
        assert skill.name == "Updated Skill"
        skill_var = skill.variables["skill_var"]
        new_var = skill.variables["new_var"]
        assert skill_var == "updated" or (
            hasattr(skill_var, "value") and skill_var.value == "updated"
        )
        assert new_var == "new_value" or (
            hasattr(new_var, "value") and new_var.value == "new_value"
        )

    async def test_create_skill_saves_full_variable_config(self, client, container, unique_id):
        """Создание skill сохраняет полную конфигурацию переменных (value, public, title, description)."""
        flow_id = f"test_agent_full_vars_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
            "variables": {
                "api_key": {
                    "value": "base_secret_key",
                    "public": False,
                    "title": "API Key",
                    "description": "Secret API key for external service",
                },
                "timeout": {
                    "value": "30",
                    "public": True,
                    "title": "Timeout",
                    "description": "Request timeout in seconds",
                },
            },
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Test Skill",
            "branch_body": {
                "variables": {
                    "api_key": {
                        "value": "skill_secret_key",
                        "public": False,
                        "title": "Skill API Key",
                        "description": "Overridden API key for skill",
                    },
                    "max_retries": {
                        "value": "5",
                        "public": True,
                        "title": "Max Retries",
                        "description": "Maximum number of retry attempts",
                    },
                }
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        skill = agent.branches[branch_id]
        api_key = skill.variables["api_key"]
        if hasattr(api_key, "value"):
            assert api_key.value == "skill_secret_key"
            assert not api_key.public
            assert api_key.title == "Skill API Key"
            assert api_key.description == "Overridden API key for skill"
        else:
            assert api_key["value"] == "skill_secret_key"
            assert not api_key["public"]
            assert api_key["title"] == "Skill API Key"
            assert api_key["description"] == "Overridden API key for skill"
        max_retries = skill.variables["max_retries"]
        if hasattr(max_retries, "value"):
            assert max_retries.value == "5"
            assert max_retries.public
            assert max_retries.title == "Max Retries"
            assert max_retries.description == "Maximum number of retry attempts"
        else:
            assert max_retries["value"] == "5"
            assert max_retries["public"]
            assert max_retries["title"] == "Max Retries"
            assert max_retries["description"] == "Maximum number of retry attempts"
        effective = container.flow_factory.apply_branch(agent, branch_id)
        assert effective["variables"]["api_key"] == "skill_secret_key"
        assert effective["variables"]["timeout"] == "30"
        assert effective["variables"]["max_retries"] == "5"

    async def test_update_skill_updates_full_variable_config(self, client, container, unique_id):
        """Обновление skill обновляет полную конфигурацию переменных."""
        flow_id = f"test_agent_update_full_vars_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
            "variables": {"base_var": {"value": "base", "public": False, "title": "Base Variable"}},
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Test Skill",
            "branch_body": {
                "variables": {
                    "skill_var": {
                        "value": "original",
                        "public": False,
                        "title": "Original Title",
                        "description": "Original description",
                    }
                }
            },
        }
        create_skill_resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert create_skill_resp.status_code == 201
        update_data = {
            "branch_id": branch_id,
            "name": "Updated Skill",
            "branch_body": {
                "variables": {
                    "skill_var": {
                        "value": "updated",
                        "public": True,
                        "title": "Updated Title",
                        "description": "Updated description",
                    },
                    "new_var": {
                        "value": "new_value",
                        "public": True,
                        "title": "New Variable",
                        "description": "Newly added variable",
                    },
                }
            },
        }
        update_resp = await client.put(
            f"/flows/api/v1/{flow_id}/branches/{branch_id}", json=update_data
        )
        assert update_resp.status_code == 200
        agent = await container.flow_repository.get(flow_id)
        skill = agent.branches[branch_id]
        assert skill.name == "Updated Skill"
        skill_var = skill.variables["skill_var"]
        if hasattr(skill_var, "value"):
            assert skill_var.value == "updated"
            assert skill_var.public
            assert skill_var.title == "Updated Title"
            assert skill_var.description == "Updated description"
        else:
            assert skill_var["value"] == "updated"
            assert skill_var["public"]
            assert skill_var["title"] == "Updated Title"
            assert skill_var["description"] == "Updated description"
        new_var = skill.variables["new_var"]
        if hasattr(new_var, "value"):
            assert new_var.value == "new_value"
            assert new_var.public
            assert new_var.title == "New Variable"
            assert new_var.description == "Newly added variable"
        else:
            assert new_var["value"] == "new_value"
            assert new_var["public"]
            assert new_var["title"] == "New Variable"
            assert new_var["description"] == "Newly added variable"

    async def test_create_skill_validates_graph_structure(self, client, unique_id):
        """Создание skill валидирует структуру графа."""
        flow_id = f"test_agent_invalid_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Invalid Skill",
            "branch_body": {
                "entry": "nonexistent_node",
                "nodes": {
                    "some_node": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return state",
                    }
                },
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 400
        assert "валидации ветки" in resp.json()["detail"].lower()

    async def test_create_skill_validates_edge_references(self, client, unique_id):
        """Создание skill валидирует ссылки в edges."""
        flow_id = f"test_agent_invalid_edge_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Invalid Skill",
            "branch_body": {
                "nodes": {
                    "node_a": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return state",
                    }
                },
                "edges": [{"from_node": "node_a", "to_node": "nonexistent_node"}],
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 400
        assert "валидации ветки" in resp.json()["detail"].lower()

    async def test_update_skill_validates_result(self, client, container, unique_id):
        """Обновление skill валидирует результат."""
        flow_id = f"test_agent_update_invalid_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Valid Skill",
            "branch_body": {
                "nodes": {
                    "skill_node": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return state",
                    }
                },
                "entry": "skill_node",
                "edges": [{"from_node": "skill_node", "to_node": None}],
            },
        }
        create_skill_resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert create_skill_resp.status_code == 201
        update_data = {
            "branch_id": branch_id,
            "name": "Invalid Update",
            "branch_body": {
                "entry": "nonexistent_entry",
                "nodes": {
                    "skill_node": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return state",
                    }
                },
            },
        }
        update_resp = await client.put(
            f"/flows/api/v1/{flow_id}/branches/{branch_id}", json=update_data
        )
        assert update_resp.status_code == 400
        assert "валидации ветки" in update_resp.json()["detail"].lower()
        agent = await container.flow_repository.get(flow_id)
        skill = agent.branches[branch_id]
        assert skill.name == "Valid Skill"
        assert skill.entry == "skill_node"

    async def test_create_skill_with_inline_code(self, client, container, unique_id):
        """Создание skill с inline code в нодах."""
        flow_id = f"test_agent_inline_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "Skill with Code",
            "branch_body": {
                "entry": "code_node",
                "nodes": {
                    "code_node": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['result'] = state.get('a', 0) + state.get('b', 0)\n    state['variables']['output'] = state['result']\n    return state",
                    }
                },
                "edges": [{"from_node": "code_node", "to_node": None}],
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        skill = agent.branches[branch_id]
        assert "code_node" in skill.nodes
        assert "state['result']" in skill.nodes["code_node"]["code"]
        assert "state.get('a', 0)" in skill.nodes["code_node"]["code"]

    async def test_create_skill_with_llm_node_and_tools(self, client, container, unique_id):
        """Создание skill с llm_node и tools."""
        flow_id = f"test_agent_react_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "React Skill",
            "branch_body": {
                "entry": "react_main",
                "nodes": {
                    "react_main": {
                        "type": "llm_node",
                        "prompt": "You are a helpful assistant with calculator",
                        "tools": [
                            {
                                "tool_id": "calc_tool",
                                "description": "Calculator tool",
                                "code": "async def run(args, state):\n    a = args.get('a', 0)\n    b = args.get('b', 0)\n    return {'result': a + b}",
                                "parameters_schema": {
                                    "type": "object",
                                    "properties": {
                                        "a": {"type": "number", "description": "First number"},
                                        "b": {"type": "number", "description": "Second number"},
                                    },
                                    "required": ["a", "b"],
                                },
                            }
                        ],
                        "llm": {"model": "gpt-4o", "temperature": 0.2},
                    }
                },
                "edges": [{"from_node": "react_main", "to_node": None}],
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        skill = agent.branches[branch_id]
        assert "react_main" in skill.nodes
        llm_node = skill.nodes["react_main"]
        assert llm_node["type"] == "llm_node"
        assert llm_node["prompt"] == "You are a helpful assistant with calculator"
        assert len(llm_node["tools"]) == 1
        assert llm_node["tools"][0]["tool_id"] == "calc_tool"
        assert "a + b" in llm_node["tools"][0]["code"]
        assert llm_node["llm"]["temperature"] == 0.2

    async def test_create_skill_rejects_unsupported_fields_in_branch_body(self, client, unique_id):
        """
        Создание skill отклоняет неподдерживаемые поля в branch_body.

        Поля flow, goal, role, examples, success_criteria, additional_information
        не поддерживаются в BranchConfig.
        """
        flow_id = f"test_agent_unsupported_{unique_id}"
        base_agent = {
            "flow_id": flow_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {"type": "code", "code": "async def run(args, state):\n    return state"}
            },
            "edges": [{"from_node": "main", "to_node": None}],
        }
        create_resp = await client.post("/flows/api/v1/flows/", json=base_agent)
        assert create_resp.status_code == 200
        branch_id = f"test_skill_{unique_id}"
        skill_data = {
            "branch_id": branch_id,
            "name": "новый навык",
            "description": "тут описание",
            "tags": ["eee"],
            "branch_body": {
                "flow": "Some flow",
                "goal": "You need to help the user 1",
                "role": "You are a helpful assistant 1",
                "examples": "Some examples 1",
                "success_criteria": "All done 1",
                "additional_information": "Useful additional information 1",
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=skill_data)
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "unknown fields" in detail
        assert "flow" in detail
        assert "goal" in detail
        assert "allowed fields" in detail
