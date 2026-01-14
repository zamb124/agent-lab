"""
Строгие тесты валидации и сохранения skills через API.

Проверяет что create_skill и update_skill:
- Сохраняют переменные (включая переопределение в skill)
- Сохраняют свойства нод
- Сохраняют ноды
- Сохраняют условия (conditions)
- Валидируют результат применения skill
- Отклоняют невалидные конфигурации
"""

import pytest


@pytest.mark.asyncio
class TestSkillValidationAndPersistence:
    """Тесты валидации и сохранения skills."""

    async def test_create_skill_saves_variables(self, client, container, unique_id):
        """Создание skill сохраняет переменные."""
        agent_id = f"test_agent_vars_{unique_id}"
        
        # Создаём базовый агент с переменными
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}],
            "variables": {
                "base_var": "base_value",
                "shared_var": "from_base"
            }
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём skill с переменными
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Test Skill",
            "description": "Skill with variables",
            "skill_body": {
                "variables": {
                    "skill_var": "skill_value",
                    "shared_var": "from_skill"
                }
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert resp.status_code == 201
        
        # Проверяем что skill сохранён
        agent = await container.agent_repository.get(agent_id)
        assert agent is not None
        assert skill_id in agent.skills
        
        skill = agent.skills[skill_id]
        # Переменные могут быть как простыми значениями, так и AgentVariableConfig
        skill_var = skill.variables["skill_var"]
        shared_var = skill.variables["shared_var"]
        assert (skill_var == "skill_value" or (hasattr(skill_var, "value") and skill_var.value == "skill_value"))
        assert (shared_var == "from_skill" or (hasattr(shared_var, "value") and shared_var.value == "from_skill"))
        
        # Проверяем что при применении skill переменные мержатся правильно
        effective = container.agent_factory._apply_skill(agent, skill_id)
        assert effective["variables"]["base_var"] == "base_value"
        assert effective["variables"]["skill_var"] == "skill_value"
        assert effective["variables"]["shared_var"] == "from_skill"

    async def test_create_skill_saves_node_properties(self, client, container, unique_id):
        """Создание skill сохраняет свойства нод."""
        agent_id = f"test_agent_props_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "react_node",
                    "prompt": "Base prompt",
                    "tools": [],
                    "llm": {"model": "gpt-4o", "temperature": 0.7}
                }
            },
            "edges": [{"from": "main", "to": None}]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём skill с изменёнными свойствами ноды (MERGE mode по умолчанию)
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Test Skill",
            "skill_body": {
                "nodes": {
                    "main": {
                        "type": "react_node",  # Нужен type для валидации
                        "prompt": "Skill prompt",
                        "llm": {"temperature": 0.1, "max_tokens": 1000}
                    }
                },
                "nodes_mode": "merge"  # Явно указываем MERGE mode
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert resp.status_code == 201
        
        # Проверяем что skill сохранён
        agent = await container.agent_repository.get(agent_id)
        skill = agent.skills[skill_id]
        
        assert skill.nodes["main"]["prompt"] == "Skill prompt"
        assert skill.nodes["main"]["llm"]["temperature"] == 0.1
        assert skill.nodes["main"]["llm"]["max_tokens"] == 1000
        
        # Проверяем что при применении skill свойства мержатся
        effective = container.agent_factory._apply_skill(agent, skill_id)
        # По умолчанию nodes_mode = MERGE - deep_merge мержит dict рекурсивно
        assert effective["nodes"]["main"]["prompt"] == "Skill prompt"
        assert effective["nodes"]["main"]["llm"]["temperature"] == 0.1
        assert effective["nodes"]["main"]["llm"]["max_tokens"] == 1000
        # При MERGE mode базовые свойства должны сохраняться если не переопределены в skill
        # Но если в skill.nodes["main"] нет model, он не будет в effective после мержа
        # Это ожидаемое поведение - skill содержит только переопределения

    async def test_create_skill_saves_nodes(self, client, container, unique_id):
        """Создание skill сохраняет ноды."""
        agent_id = f"test_agent_nodes_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    state['path'] = 'base'\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём skill с новыми нодами
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Test Skill",
            "skill_body": {
                "entry": "skill_main",
                "nodes": {
                    "skill_main": {
                        "type": "function",
                        "code": "async def run(state):\n    state['path'] = 'skill'\n    return state"
                    },
                    "skill_helper": {
                        "type": "function",
                        "code": "async def run(state):\n    state['helper'] = True\n    return state"
                    }
                },
                "edges": [
                    {"from": "skill_main", "to": "skill_helper"},
                    {"from": "skill_helper", "to": None}
                ]
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert resp.status_code == 201
        
        # Проверяем что skill сохранён
        agent = await container.agent_repository.get(agent_id)
        skill = agent.skills[skill_id]
        
        assert skill.entry == "skill_main"
        assert "skill_main" in skill.nodes
        assert "skill_helper" in skill.nodes
        assert skill.nodes["skill_main"]["type"] == "function"
        assert "state['path'] = 'skill'" in skill.nodes["skill_main"]["code"]
        
        # Проверяем что при применении skill ноды заменяются (nodes_mode = REPLACE по умолчанию)
        effective = container.agent_factory._apply_skill(agent, skill_id)
        assert effective["entry"] == "skill_main"
        assert "skill_main" in effective["nodes"]
        assert "skill_helper" in effective["nodes"]
        assert "main" not in effective["nodes"]

    async def test_create_skill_saves_conditions(self, client, container, unique_id):
        """Создание skill сохраняет условия (conditions) в edges."""
        agent_id = f"test_agent_cond_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    state['value'] = 10\n    return state"
                },
                "branch_a": {
                    "type": "function",
                    "code": "async def run(state):\n    state['branch'] = 'a'\n    return state"
                },
                "branch_b": {
                    "type": "function",
                    "code": "async def run(state):\n    state['branch'] = 'b'\n    return state"
                }
            },
            "edges": [
                {"from": "main", "to": "branch_a"},
                {"from": "branch_a", "to": None}
            ]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём skill с условными переходами
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Test Skill",
            "skill_body": {
                "edges": [
                    {"from": "main", "to": "branch_a", "condition": "state.get('value', 0) > 5"},
                    {"from": "main", "to": "branch_b", "condition": "state.get('value', 0) <= 5"},
                    {"from": "branch_a", "to": None},
                    {"from": "branch_b", "to": None}
                ]
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert resp.status_code == 201
        
        # Проверяем что skill сохранён с условиями
        agent = await container.agent_repository.get(agent_id)
        skill = agent.skills[skill_id]
        
        assert len(skill.edges) == 4
        
        # Находим edge с условием
        conditional_edges = [e for e in skill.edges if e.condition is not None]
        assert len(conditional_edges) == 2
        
        edge_to_a = next(e for e in skill.edges if e.from_node == "main" and e.to_node == "branch_a")
        assert edge_to_a.condition == "state.get('value', 0) > 5"
        
        edge_to_b = next(e for e in skill.edges if e.from_node == "main" and e.to_node == "branch_b")
        assert edge_to_b.condition == "state.get('value', 0) <= 5"
        
        # Проверяем что при применении skill условия сохраняются
        effective = container.agent_factory._apply_skill(agent, skill_id)
        effective_edge_to_a = next(e for e in effective["edges"] if e.from_node == "main" and e.to_node == "branch_a")
        assert effective_edge_to_a.condition == "state.get('value', 0) > 5"

    async def test_update_skill_updates_variables(self, client, container, unique_id):
        """Обновление skill обновляет переменные."""
        agent_id = f"test_agent_update_vars_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}],
            "variables": {"base_var": "base"}
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём skill
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Test Skill",
            "skill_body": {
                "variables": {"skill_var": "original"}
            }
        }
        
        create_skill_resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert create_skill_resp.status_code == 201
        
        # Обновляем skill с новыми переменными
        update_data = {
            "skill_id": skill_id,
            "name": "Updated Skill",
            "skill_body": {
                "variables": {
                    "skill_var": "updated",
                    "new_var": "new_value"
                }
            }
        }
        
        update_resp = await client.put(f"/agents/api/v1/{agent_id}/skills/{skill_id}", json=update_data)
        assert update_resp.status_code == 200
        
        # Проверяем что переменные обновлены
        agent = await container.agent_repository.get(agent_id)
        skill = agent.skills[skill_id]
        
        assert skill.name == "Updated Skill"
        skill_var = skill.variables["skill_var"]
        new_var = skill.variables["new_var"]
        assert (skill_var == "updated" or (hasattr(skill_var, "value") and skill_var.value == "updated"))
        assert (new_var == "new_value" or (hasattr(new_var, "value") and new_var.value == "new_value"))

    async def test_create_skill_saves_full_variable_config(self, client, container, unique_id):
        """Создание skill сохраняет полную конфигурацию переменных (value, public, title, description)."""
        agent_id = f"test_agent_full_vars_{unique_id}"
        
        # Создаём базовый агент с полной конфигурацией переменных
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}],
            "variables": {
                "api_key": {
                    "value": "base_secret_key",
                    "public": False,
                    "title": "API Key",
                    "description": "Secret API key for external service"
                },
                "timeout": {
                    "value": "30",
                    "public": True,
                    "title": "Timeout",
                    "description": "Request timeout in seconds"
                }
            }
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём skill с полной конфигурацией переменных
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Test Skill",
            "skill_body": {
                "variables": {
                    "api_key": {
                        "value": "skill_secret_key",
                        "public": False,
                        "title": "Skill API Key",
                        "description": "Overridden API key for skill"
                    },
                    "max_retries": {
                        "value": "5",
                        "public": True,
                        "title": "Max Retries",
                        "description": "Maximum number of retry attempts"
                    }
                }
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert resp.status_code == 201
        
        # Проверяем что skill сохранён с полной конфигурацией переменных
        agent = await container.agent_repository.get(agent_id)
        skill = agent.skills[skill_id]
        
        # Проверяем переопределённую переменную
        api_key = skill.variables["api_key"]
        if hasattr(api_key, "value"):
            assert api_key.value == "skill_secret_key"
            assert api_key.public == False
            assert api_key.title == "Skill API Key"
            assert api_key.description == "Overridden API key for skill"
        else:
            # Если это dict (после десериализации)
            assert api_key["value"] == "skill_secret_key"
            assert api_key["public"] == False
            assert api_key["title"] == "Skill API Key"
            assert api_key["description"] == "Overridden API key for skill"
        
        # Проверяем новую переменную
        max_retries = skill.variables["max_retries"]
        if hasattr(max_retries, "value"):
            assert max_retries.value == "5"
            assert max_retries.public == True
            assert max_retries.title == "Max Retries"
            assert max_retries.description == "Maximum number of retry attempts"
        else:
            assert max_retries["value"] == "5"
            assert max_retries["public"] == True
            assert max_retries["title"] == "Max Retries"
            assert max_retries["description"] == "Maximum number of retry attempts"
        
        # Проверяем что при применении skill переменные мержатся с полными метаданными
        effective = container.agent_factory._apply_skill(agent, skill_id)
        # В effective переменные извлекаются как простые значения (только value)
        assert effective["variables"]["api_key"] == "skill_secret_key"
        assert effective["variables"]["timeout"] == "30"
        assert effective["variables"]["max_retries"] == "5"

    async def test_update_skill_updates_full_variable_config(self, client, container, unique_id):
        """Обновление skill обновляет полную конфигурацию переменных."""
        agent_id = f"test_agent_update_full_vars_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}],
            "variables": {
                "base_var": {
                    "value": "base",
                    "public": False,
                    "title": "Base Variable"
                }
            }
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём skill с начальной конфигурацией
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Test Skill",
            "skill_body": {
                "variables": {
                    "skill_var": {
                        "value": "original",
                        "public": False,
                        "title": "Original Title",
                        "description": "Original description"
                    }
                }
            }
        }
        
        create_skill_resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert create_skill_resp.status_code == 201
        
        # Обновляем skill с изменённой конфигурацией переменных
        update_data = {
            "skill_id": skill_id,
            "name": "Updated Skill",
            "skill_body": {
                "variables": {
                    "skill_var": {
                        "value": "updated",
                        "public": True,  # Изменили с False на True
                        "title": "Updated Title",  # Изменили title
                        "description": "Updated description"  # Изменили description
                    },
                    "new_var": {
                        "value": "new_value",
                        "public": True,
                        "title": "New Variable",
                        "description": "Newly added variable"
                    }
                }
            }
        }
        
        update_resp = await client.put(f"/agents/api/v1/{agent_id}/skills/{skill_id}", json=update_data)
        assert update_resp.status_code == 200
        
        # Проверяем что ВСЕ поля переменных обновлены в БД
        agent = await container.agent_repository.get(agent_id)
        skill = agent.skills[skill_id]
        
        assert skill.name == "Updated Skill"
        
        # Проверяем обновлённую переменную
        skill_var = skill.variables["skill_var"]
        if hasattr(skill_var, "value"):
            assert skill_var.value == "updated"
            assert skill_var.public == True  # Должно измениться
            assert skill_var.title == "Updated Title"  # Должно измениться
            assert skill_var.description == "Updated description"  # Должно измениться
        else:
            assert skill_var["value"] == "updated"
            assert skill_var["public"] == True
            assert skill_var["title"] == "Updated Title"
            assert skill_var["description"] == "Updated description"
        
        # Проверяем новую переменную
        new_var = skill.variables["new_var"]
        if hasattr(new_var, "value"):
            assert new_var.value == "new_value"
            assert new_var.public == True
            assert new_var.title == "New Variable"
            assert new_var.description == "Newly added variable"
        else:
            assert new_var["value"] == "new_value"
            assert new_var["public"] == True
            assert new_var["title"] == "New Variable"
            assert new_var["description"] == "Newly added variable"

    async def test_create_skill_validates_graph_structure(self, client, unique_id):
        """Создание skill валидирует структуру графа."""
        agent_id = f"test_agent_invalid_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Пытаемся создать skill с невалидным entry
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Invalid Skill",
            "skill_body": {
                "entry": "nonexistent_node",
                "nodes": {
                    "some_node": {
                        "type": "function",
                        "code": "async def run(state):\n    return state"
                    }
                }
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert resp.status_code == 400
        assert "validation failed" in resp.json()["detail"].lower()

    async def test_create_skill_validates_edge_references(self, client, unique_id):
        """Создание skill валидирует ссылки в edges."""
        agent_id = f"test_agent_invalid_edge_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Пытаемся создать skill с edge на несуществующую ноду
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Invalid Skill",
            "skill_body": {
                "nodes": {
                    "node_a": {
                        "type": "function",
                        "code": "async def run(state):\n    return state"
                    }
                },
                "edges": [
                    {"from": "node_a", "to": "nonexistent_node"}
                ]
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert resp.status_code == 400
        assert "validation failed" in resp.json()["detail"].lower()

    async def test_update_skill_validates_result(self, client, container, unique_id):
        """Обновление skill валидирует результат."""
        agent_id = f"test_agent_update_invalid_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём валидный skill
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Valid Skill",
            "skill_body": {
                "nodes": {
                    "skill_node": {
                        "type": "function",
                        "code": "async def run(state):\n    return state"
                    }
                },
                "entry": "skill_node",
                "edges": [{"from": "skill_node", "to": None}]
            }
        }
        
        create_skill_resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert create_skill_resp.status_code == 201
        
        # Пытаемся обновить skill с невалидным entry
        update_data = {
            "skill_id": skill_id,
            "name": "Invalid Update",
            "skill_body": {
                "entry": "nonexistent_entry",
                "nodes": {
                    "skill_node": {
                        "type": "function",
                        "code": "async def run(state):\n    return state"
                    }
                }
            }
        }
        
        update_resp = await client.put(f"/agents/api/v1/{agent_id}/skills/{skill_id}", json=update_data)
        assert update_resp.status_code == 400
        assert "validation failed" in update_resp.json()["detail"].lower()
        
        # Проверяем что skill не изменился
        agent = await container.agent_repository.get(agent_id)
        skill = agent.skills[skill_id]
        assert skill.name == "Valid Skill"
        assert skill.entry == "skill_node"

    async def test_create_skill_with_inline_code(self, client, container, unique_id):
        """Создание skill с inline code в нодах."""
        agent_id = f"test_agent_inline_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём skill с inline code
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "Skill with Code",
            "skill_body": {
                "entry": "code_node",
                "nodes": {
                    "code_node": {
                        "type": "function",
                        "code": """async def run(state):
    state['result'] = state.get('a', 0) + state.get('b', 0)
    state['variables']['output'] = state['result']
    return state"""
                    }
                },
                "edges": [{"from": "code_node", "to": None}]
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert resp.status_code == 201
        
        # Проверяем что код сохранён корректно
        agent = await container.agent_repository.get(agent_id)
        skill = agent.skills[skill_id]
        
        assert "code_node" in skill.nodes
        assert "state['result']" in skill.nodes["code_node"]["code"]
        assert "state.get('a', 0)" in skill.nodes["code_node"]["code"]

    async def test_create_skill_with_react_node_and_tools(self, client, container, unique_id):
        """Создание skill с react_node и tools."""
        agent_id = f"test_agent_react_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Создаём skill с react_node
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "React Skill",
            "skill_body": {
                "entry": "react_main",
                "nodes": {
                    "react_main": {
                        "type": "react_node",
                        "prompt": "You are a helpful assistant with calculator",
                        "tools": [
                            {
                                "tool_id": "calc_tool",
                                "description": "Calculator tool",
                                "code": """async def execute(args, state):
    a = args.get('a', 0)
    b = args.get('b', 0)
    return {'result': a + b}""",
                                "args_schema": {
                                    "a": {"type": "number", "description": "First number"},
                                    "b": {"type": "number", "description": "Second number"}
                                }
                            }
                        ],
                        "llm": {
                            "model": "gpt-4o",
                            "temperature": 0.2
                        }
                    }
                },
                "edges": [{"from": "react_main", "to": None}]
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        assert resp.status_code == 201
        
        # Проверяем что react_node с tools сохранён
        agent = await container.agent_repository.get(agent_id)
        skill = agent.skills[skill_id]
        
        assert "react_main" in skill.nodes
        react_node = skill.nodes["react_main"]
        assert react_node["type"] == "react_node"
        assert react_node["prompt"] == "You are a helpful assistant with calculator"
        assert len(react_node["tools"]) == 1
        assert react_node["tools"][0]["tool_id"] == "calc_tool"
        assert "a + b" in react_node["tools"][0]["code"]
        assert react_node["llm"]["temperature"] == 0.2

    async def test_create_skill_rejects_unsupported_fields_in_skill_body(self, client, unique_id):
        """
        Создание skill отклоняет неподдерживаемые поля в skill_body.
        
        Поля flow, goal, role, examples, success_criteria, additional_information
        не поддерживаются в SkillConfig.
        """
        agent_id = f"test_agent_unsupported_{unique_id}"
        
        # Создаём базовый агент
        base_agent = {
            "agent_id": agent_id,
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "async def run(state):\n    return state"
                }
            },
            "edges": [{"from": "main", "to": None}]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=base_agent)
        assert create_resp.status_code == 200
        
        # Пытаемся создать skill с неподдерживаемыми полями
        skill_id = f"test_skill_{unique_id}"
        skill_data = {
            "skill_id": skill_id,
            "name": "новый навык",
            "description": "тут описание",
            "tags": ["eee"],
            "skill_body": {
                "flow": "Some flow",
                "goal": "You need to help the user 1",
                "role": "You are a helpful assistant 1",
                "examples": "Some examples 1",
                "success_criteria": "All done 1",
                "additional_information": "Useful additional information 1"
            }
        }
        
        resp = await client.post(f"/agents/api/v1/{agent_id}/skills", json=skill_data)
        # Ожидаем 400 Bad Request с описанием ошибки
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        # Должна быть ошибка о неизвестных полях
        assert "unknown fields" in detail
        assert "flow" in detail
        assert "goal" in detail
        assert "allowed fields" in detail

