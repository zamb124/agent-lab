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
class TestBranchValidationAndPersistence:
    """Тесты валидации и сохранения веток."""

    async def test_create_branch_saves_variables(self, client, container, unique_id):
        """Создание branch сохраняет переменные."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Test Branch",
            "description": "Branch with variables",
            "variables": {"branch_var": "branch_value", "shared_var": "from_branch"},
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 201, resp.text
        agent = await container.flow_repository.get(flow_id)
        assert agent is not None
        assert branch_id in agent.branches
        branch = agent.branches[branch_id]
        assert branch.variables["branch_var"].value == "branch_value"
        assert branch.variables["shared_var"].value == "from_branch"
        effective = container.flow_factory.apply_branch(agent, branch_id)
        assert effective["variables"]["base_var"] == "base_value"
        assert effective["variables"]["branch_var"] == "branch_value"
        assert effective["variables"]["shared_var"] == "from_branch"

    async def test_create_branch_allows_company_variable_aliases(self, client, container, unique_id):
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
        branch_id = f"test_branch_{unique_id}"
        resp = await client.post(
            f"/flows/api/v1/{flow_id}/branches",
            json={
                "branch_id": branch_id,
                "name": "Test Branch",
                "description": "Payload shape used by the branch create modal",
            },
        )
        assert resp.status_code == 201, resp.text
        agent = await container.flow_repository.get(flow_id)
        assert agent is not None
        assert branch_id in agent.branches

    async def test_create_branch_saves_node_properties(self, client, container, unique_id):
        """Создание branch сохраняет свойства нод."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Test Branch",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Branch prompt",
                    "llm": {"temperature": 0.1, "max_tokens": 1000},
                }
            },
            "nodes_mode": "merge",
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        branch = agent.branches[branch_id]
        assert branch.nodes["main"]["prompt"] == "Branch prompt"
        assert branch.nodes["main"]["llm"]["temperature"] == 0.1
        assert branch.nodes["main"]["llm"]["max_tokens"] == 1000
        effective = container.flow_factory.apply_branch(agent, branch_id)
        assert effective["nodes"]["main"]["prompt"] == "Branch prompt"
        assert effective["nodes"]["main"]["llm"]["temperature"] == 0.1
        assert effective["nodes"]["main"]["llm"]["max_tokens"] == 1000

    async def test_create_branch_saves_nodes(self, client, container, unique_id):
        """Создание branch сохраняет ноды."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Test Branch",
            "entry": "branch_main",
            "nodes": {
                "branch_main": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['path'] = 'branch'\n    return state",
                },
                "branch_helper": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['helper'] = True\n    return state",
                },
            },
            "edges": [
                {"from_node": "branch_main", "to_node": "branch_helper"},
                {"from_node": "branch_helper", "to_node": None},
            ],
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        branch = agent.branches[branch_id]
        assert branch.entry == "branch_main"
        assert "branch_main" in branch.nodes
        assert "branch_helper" in branch.nodes
        assert branch.nodes["branch_main"]["type"] == "code"
        assert "state['path'] = 'branch'" in branch.nodes["branch_main"]["code"]
        effective = container.flow_factory.apply_branch(agent, branch_id)
        assert effective["entry"] == "branch_main"
        assert "branch_main" in effective["nodes"]
        assert "branch_helper" in effective["nodes"]
        assert "main" not in effective["nodes"]

    async def test_create_branch_saves_conditions(self, client, container, unique_id):
        """Создание branch сохраняет условия (conditions) в edges."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Test Branch",
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
            ],
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        branch = agent.branches[branch_id]
        assert len(branch.edges) == 4
        conditional_edges = [e for e in branch.edges if e.condition is not None]
        assert len(conditional_edges) == 2
        edge_to_a = next(
            (e for e in branch.edges if e.from_node == "main" and e.to_node == "branch_a")
        )
        assert edge_to_a.condition is not None
        assert edge_to_a.condition.type == "simple"
        assert edge_to_a.condition.variable == "value"
        assert edge_to_a.condition.operator == ">"
        assert edge_to_a.condition.value == 5
        edge_to_b = next(
            (e for e in branch.edges if e.from_node == "main" and e.to_node == "branch_b")
        )
        assert edge_to_b.condition is not None
        assert edge_to_b.condition.type == "simple"
        assert edge_to_b.condition.variable == "value"
        assert edge_to_b.condition.operator == "<="
        assert edge_to_b.condition.value == 5
        effective = container.flow_factory.apply_branch(agent, branch_id)
        effective_edge_to_a = next(
            (e for e in effective["edges"] if e.from_node == "main" and e.to_node == "branch_a")
        )
        assert effective_edge_to_a.condition is not None
        assert effective_edge_to_a.condition.type == "simple"

    async def test_update_branch_updates_variables(self, client, container, unique_id):
        """Обновление branch обновляет переменные."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Test Branch",
            "variables": {"branch_var": "original"},
        }
        create_branch_resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert create_branch_resp.status_code == 201
        update_data = {
            "name": "Updated Branch",
            "variables": {"branch_var": "updated", "new_var": "new_value"},
        }
        update_resp = await client.put(
            f"/flows/api/v1/{flow_id}/branches/{branch_id}", json=update_data
        )
        assert update_resp.status_code == 200
        agent = await container.flow_repository.get(flow_id)
        branch = agent.branches[branch_id]
        assert branch.name == "Updated Branch"
        assert branch.variables["branch_var"].value == "updated"
        assert branch.variables["new_var"].value == "new_value"

    async def test_create_branch_saves_full_variable_config(self, client, container, unique_id):
        """Создание branch сохраняет полную конфигурацию переменных."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Test Branch",
            "variables": {
                "api_key": {
                    "value": "branch_secret_key",
                    "public": False,
                    "title": "Branch API Key",
                    "description": "Overridden API key for branch",
                },
                "max_retries": {
                    "value": "5",
                    "public": True,
                    "title": "Max Retries",
                    "description": "Maximum number of retry attempts",
                },
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        branch = agent.branches[branch_id]
        api_key = branch.variables["api_key"]
        assert api_key.value == "branch_secret_key"
        assert not api_key.public
        assert api_key.title == "Branch API Key"
        assert api_key.description == "Overridden API key for branch"
        max_retries = branch.variables["max_retries"]
        assert max_retries.value == "5"
        assert max_retries.public
        assert max_retries.title == "Max Retries"
        assert max_retries.description == "Maximum number of retry attempts"
        effective = container.flow_factory.apply_branch(agent, branch_id)
        assert effective["variables"]["api_key"] == "branch_secret_key"
        assert effective["variables"]["timeout"] == "30"
        assert effective["variables"]["max_retries"] == "5"

    async def test_update_branch_updates_full_variable_config(self, client, container, unique_id):
        """Обновление branch обновляет полную конфигурацию переменных."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Test Branch",
            "variables": {
                "branch_var": {
                    "value": "original",
                    "public": False,
                    "title": "Original Title",
                    "description": "Original description",
                }
            },
        }
        create_branch_resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert create_branch_resp.status_code == 201
        update_data = {
            "name": "Updated Branch",
            "variables": {
                "branch_var": {
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
            },
        }
        update_resp = await client.put(
            f"/flows/api/v1/{flow_id}/branches/{branch_id}", json=update_data
        )
        assert update_resp.status_code == 200
        agent = await container.flow_repository.get(flow_id)
        branch = agent.branches[branch_id]
        assert branch.name == "Updated Branch"
        branch_var = branch.variables["branch_var"]
        assert branch_var.value == "updated"
        assert branch_var.public
        assert branch_var.title == "Updated Title"
        assert branch_var.description == "Updated description"
        new_var = branch.variables["new_var"]
        assert new_var.value == "new_value"
        assert new_var.public
        assert new_var.title == "New Variable"
        assert new_var.description == "Newly added variable"

    async def test_create_branch_validates_graph_structure(self, client, unique_id):
        """Создание branch валидирует структуру графа."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Invalid Branch",
            "entry": "nonexistent_node",
            "nodes": {
                "some_node": {
                    "type": "code",
                    "code": "async def run(args, state):\n    return state",
                },
            },
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 400
        assert "валидации ветки" in resp.json()["detail"].lower()

    async def test_create_branch_validates_edge_references(self, client, unique_id):
        """Создание branch валидирует ссылки в edges."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Invalid Branch",
            "nodes": {
                "node_a": {
                    "type": "code",
                    "code": "async def run(args, state):\n    return state",
                }
            },
            "edges": [{"from_node": "node_a", "to_node": "nonexistent_node"}],
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 400
        assert "валидации ветки" in resp.json()["detail"].lower()

    async def test_update_branch_validates_result(self, client, container, unique_id):
        """Обновление branch валидирует результат."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Valid Branch",
            "nodes": {
                "branch_node": {
                    "type": "code",
                    "code": "async def run(args, state):\n    return state",
                }
            },
            "entry": "branch_node",
            "edges": [{"from_node": "branch_node", "to_node": None}],
        }
        create_branch_resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert create_branch_resp.status_code == 201
        update_data = {
            "name": "Invalid Update",
            "entry": "nonexistent_entry",
            "nodes": {
                "branch_node": {
                    "type": "code",
                    "code": "async def run(args, state):\n    return state",
                }
            },
        }
        update_resp = await client.put(
            f"/flows/api/v1/{flow_id}/branches/{branch_id}", json=update_data
        )
        assert update_resp.status_code == 400
        assert "валидации ветки" in update_resp.json()["detail"].lower()
        agent = await container.flow_repository.get(flow_id)
        branch = agent.branches[branch_id]
        assert branch.name == "Valid Branch"
        assert branch.entry == "branch_node"

    async def test_create_branch_with_inline_code(self, client, container, unique_id):
        """Создание branch с inline code в нодах."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "Branch with Code",
            "entry": "code_node",
            "nodes": {
                "code_node": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['result'] = state.get('a', 0) + state.get('b', 0)\n    state['variables']['output'] = state['result']\n    return state",
                }
            },
            "edges": [{"from_node": "code_node", "to_node": None}],
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        branch = agent.branches[branch_id]
        assert "code_node" in branch.nodes
        assert "state['result']" in branch.nodes["code_node"]["code"]
        assert "state.get('a', 0)" in branch.nodes["code_node"]["code"]

    async def test_create_branch_with_llm_node_and_tools(self, client, container, unique_id):
        """Создание branch с llm_node и tools."""
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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "React Branch",
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
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 201
        agent = await container.flow_repository.get(flow_id)
        branch = agent.branches[branch_id]
        assert "react_main" in branch.nodes
        llm_node = branch.nodes["react_main"]
        assert llm_node["type"] == "llm_node"
        assert llm_node["prompt"] == "You are a helpful assistant with calculator"
        assert len(llm_node["tools"]) == 1
        assert llm_node["tools"][0]["tool_id"] == "calc_tool"
        assert "a + b" in llm_node["tools"][0]["code"]
        assert llm_node["llm"]["temperature"] == 0.2

    async def test_create_branch_rejects_unsupported_fields(self, client, unique_id):
        """
        Создание branch отклоняет неподдерживаемые поля.

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
        branch_id = f"test_branch_{unique_id}"
        branch_data = {
            "branch_id": branch_id,
            "name": "новый навык",
            "description": "тут описание",
            "tags": ["eee"],
            "flow": "Some flow",
            "goal": "You need to help the user 1",
            "role": "You are a helpful assistant 1",
            "examples": "Some examples 1",
            "success_criteria": "All done 1",
            "additional_information": "Useful additional information 1",
        }
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json=branch_data)
        assert resp.status_code == 422
        detail = resp.text.lower()
        assert "extra_forbidden" in detail
        assert "flow" in detail
        assert "goal" in detail
