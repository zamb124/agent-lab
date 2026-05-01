"""
Строгие тесты для Skill overrides.

Проверяем все уровни переопределений через branches:
- variables (merge/replace)
- nodes (merge/replace)
- edges (merge/replace)
- entry
- mock
"""

import pytest
from apps.flows.src.models import FlowConfig, Edge, MergeMode, BranchConfig
from apps.flows.src.container import get_container


class TestSkillVariablesOverride:
    """Тесты переопределения variables через skill."""

    def test_variables_merge_adds_new(self, container):
        """MERGE режим добавляет новые переменные."""
        config = FlowConfig(
            flow_id="test_vars",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
            variables={
                "company_name": "BaseCompany",
                "max_length": 500
            },
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    variables={"new_var": "new_value"},
                    variables_mode=MergeMode.MERGE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert result["variables"]["company_name"] == "BaseCompany"
        assert result["variables"]["max_length"] == 500
        assert result["variables"]["new_var"] == "new_value"

    def test_variables_merge_overrides_existing(self, container):
        """MERGE режим переопределяет существующие переменные."""
        config = FlowConfig(
            flow_id="test_vars",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
            variables={
                "max_length": 500,
                "mode": "default"
            },
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    variables={"max_length": 200, "mode": "custom"},
                    variables_mode=MergeMode.MERGE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert result["variables"]["max_length"] == 200
        assert result["variables"]["mode"] == "custom"

    def test_variables_replace_removes_base(self, container):
        """REPLACE режим удаляет base переменные."""
        config = FlowConfig(
            flow_id="test_vars",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
            variables={
                "base_var1": "value1",
                "base_var2": "value2"
            },
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    variables={"skill_var": "skill_value"},
                    variables_mode=MergeMode.REPLACE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert "base_var1" not in result["variables"]
        assert "base_var2" not in result["variables"]
        assert result["variables"]["skill_var"] == "skill_value"

    def test_variables_with_agent_variable_config(self, container):
        """Переменные в формате FlowVariableConfig мержатся корректно."""
        config = FlowConfig(
            flow_id="test_vars",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
            variables={
                "company_name": {
                    "value": "@var:company_name",
                    "public": True,
                    "title": "Название компании"
                }
            },
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    variables={
                        "company_name": {
                            "value": "CustomCompany",
                            "public": False
                        }
                    },
                    variables_mode=MergeMode.MERGE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        # После apply_skill переменные извлекаются как простые значения
        assert result["variables"]["company_name"] == "CustomCompany"


class TestSkillNodesOverride:
    """Тесты переопределения nodes через skill."""

    def test_nodes_replace_removes_base(self, container):
        """REPLACE режим удаляет base nodes."""
        config = FlowConfig(
            flow_id="test_nodes",
            name="Test",
            entry="main",
            nodes={
                "main": {"type": "llm_node", "prompt": "Base main"},
                "helper": {"type": "code", "code": "def run(s): return s"}
            },
            edges=[Edge(from_node="main", to_node=None)],
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    entry="custom_main",
                    nodes={
                        "custom_main": {"type": "llm_node", "prompt": "Custom"}
                    },
                    nodes_mode=MergeMode.REPLACE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert "main" not in result["nodes"]
        assert "helper" not in result["nodes"]
        assert "custom_main" in result["nodes"]

    def test_nodes_merge_adds_new(self, container):
        """MERGE режим добавляет новые nodes."""
        config = FlowConfig(
            flow_id="test_nodes",
            name="Test",
            entry="main",
            nodes={
                "main": {"type": "llm_node", "prompt": "Base"}
            },
            edges=[Edge(from_node="main", to_node=None)],
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    nodes={
                        "new_node": {"type": "code", "code": "def run(s): return s"}
                    },
                    nodes_mode=MergeMode.MERGE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert "main" in result["nodes"]
        assert "new_node" in result["nodes"]

    def test_nodes_merge_deep_merges_existing(self, container):
        """MERGE режим глубоко мержит существующие nodes."""
        config = FlowConfig(
            flow_id="test_nodes",
            name="Test",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Base prompt",
                    "tools": ["tool1", "tool2"],
                    "llm": {"model": "gpt-4o", "temperature": 0.7}
                }
            },
            edges=[Edge(from_node="main", to_node=None)],
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    nodes={
                        "main": {
                            "prompt": "Custom prompt",
                            "llm": {"temperature": 0.1}
                        }
                    },
                    nodes_mode=MergeMode.MERGE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        node = result["nodes"]["main"]
        assert node["type"] == "llm_node"  # Сохранен
        assert node["prompt"] == "Custom prompt"  # Переопределен
        assert node["tools"] == ["tool1", "tool2"]  # Сохранен
        assert node["llm"]["model"] == "gpt-4o"  # Сохранен
        assert node["llm"]["temperature"] == 0.1  # Переопределен

    def test_nodes_merge_override_tools_list(self, container):
        """MERGE режим заменяет tools list целиком."""
        config = FlowConfig(
            flow_id="test_nodes",
            name="Test",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Prompt",
                    "tools": ["calculator", "ask_user", "finish"]
                }
            },
            edges=[Edge(from_node="main", to_node=None)],
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    nodes={
                        "main": {"tools": ["only_one"]}
                    },
                    nodes_mode=MergeMode.MERGE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert result["nodes"]["main"]["tools"] == ["only_one"]


class TestSkillEdgesOverride:
    """Тесты переопределения edges через skill."""

    def test_edges_replace_removes_base(self, container):
        """REPLACE режим удаляет base edges."""
        config = FlowConfig(
            flow_id="test_edges",
            name="Test",
            entry="main",
            nodes={
                "main": {"type": "code", "code": "def run(s): return s"},
                "step2": {"type": "code", "code": "def run(s): return s"}
            },
            edges=[
                Edge(from_node="main", to_node="step2"),
                Edge(from_node="step2", to_node=None)
            ],
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    edges=[Edge(from_node="main", to_node=None)],
                    edges_mode=MergeMode.REPLACE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert len(result["edges"]) == 1
        assert result["edges"][0].from_node == "main"
        assert result["edges"][0].to_node is None

    def test_edges_merge_overrides_same_pair(self, container):
        """MERGE режим переопределяет edges с той же парой (from_node, to_node)."""
        config = FlowConfig(
            flow_id="test_edges",
            name="Test",
            entry="main",
            nodes={
                "main": {"type": "code", "code": "def run(s): return s"},
                "step2": {"type": "code", "code": "def run(s): return s"},
                "step3": {"type": "code", "code": "def run(s): return s"}
            },
            edges=[
                Edge(from_node="main", to_node="step2"),
                Edge(from_node="step2", to_node=None)
            ],
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    edges=[Edge(from_node="main", to_node="step3")],
                    edges_mode=MergeMode.MERGE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert len(result["edges"]) == 3
        from_nodes = [e.from_node for e in result["edges"]]
        assert from_nodes.count("main") == 2
        assert "step2" in from_nodes

        main_edges = [e for e in result["edges"] if e.from_node == "main"]
        assert len(main_edges) == 2
        main_to_nodes = {e.to_node for e in main_edges}
        assert main_to_nodes == {"step2", "step3"}

    def test_edges_with_conditions(self, container):
        """Переопределение edges с условиями по паре (from, to)."""
        config = FlowConfig(
            flow_id="test_edges",
            name="Test",
            entry="classifier",
            nodes={
                "classifier": {"type": "code", "code": "def run(s): s['route']='a'; return s"},
                "route_a": {"type": "code", "code": "def run(s): return s"},
                "route_b": {"type": "code", "code": "def run(s): return s"}
            },
            edges=[
                Edge(from_node="classifier", to_node="route_a", condition="route == 'a'"),
                Edge(from_node="classifier", to_node="route_b", condition="route == 'b'"),
                Edge(from_node="route_a", to_node=None),
                Edge(from_node="route_b", to_node=None)
            ],
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    edges=[
                        Edge(from_node="classifier", to_node="route_a", condition="route == 'a' and priority == 'high'")
                    ],
                    edges_mode=MergeMode.MERGE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert len(result["edges"]) == 4
        
        classifier_edges = [e for e in result["edges"] if e.from_node == "classifier"]
        assert len(classifier_edges) == 2
        
        classifier_to_route_a = next(e for e in result["edges"] if e.from_node == "classifier" and e.to_node == "route_a")
        assert "priority" in classifier_to_route_a.condition
        
        classifier_to_route_b = next(e for e in result["edges"] if e.from_node == "classifier" and e.to_node == "route_b")
        assert classifier_to_route_b.condition == "route == 'b'"


class TestSkillEntryOverride:
    """Тесты переопределения entry через skill."""

    def test_entry_override(self, container):
        """Skill переопределяет entry point."""
        config = FlowConfig(
            flow_id="test_entry",
            name="Test",
            entry="default_start",
            nodes={
                "default_start": {"type": "code", "code": "def run(s): s['path']='default'; return s"},
                "skill_start": {"type": "code", "code": "def run(s): s['path']='skill'; return s"}
            },
            edges=[
                Edge(from_node="default_start", to_node=None),
                Edge(from_node="skill_start", to_node=None)
            ],
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    entry="skill_start"
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert result["entry"] == "skill_start"

    def test_entry_none_keeps_base(self, container):
        """Если entry не указан в skill - сохраняется base."""
        config = FlowConfig(
            flow_id="test_entry",
            name="Test",
            entry="default_start",
            nodes={
                "default_start": {"type": "code", "code": "def run(s): return s"}
            },
            edges=[Edge(from_node="default_start", to_node=None)],
            branches={
                "custom": BranchConfig(
                    name="Custom",
                    variables={"var": "value"}
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "custom")

        assert result["entry"] == "default_start"


class TestSkillMockOverride:
    """Тесты переопределения mock через skill.
    
    Mock резолвится отдельно через resolve_mock_config, не через _apply_skill.
    """

    def test_mock_enabled_in_skill(self):
        """Skill включает mock."""
        from apps.flows.src.mock.resolver import resolve_mock_config
        
        flow_mock = {"enabled": False}
        skill_mock = {"enabled": True}

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert config.enabled is True

    def test_mock_tools_override(self):
        """Skill переопределяет mock tools."""
        from apps.flows.src.mock.resolver import resolve_mock_config
        
        flow_mock = {
            "enabled": False,
            "tools": {"calculator": 42}
        }
        skill_mock = {
            "enabled": True,
            "tools": {"calculator": 100, "ask_user": "response"}
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert config.enabled is True
        assert config.tools["calculator"] == 100
        assert config.tools["ask_user"] == "response"

    def test_mock_llm_in_skill(self):
        """Skill добавляет mock LLM responses."""
        from apps.flows.src.mock.resolver import resolve_mock_config
        
        flow_mock = {"enabled": False}
        skill_mock = {
            "enabled": True,
            "llm": [
                {"type": "text", "content": "Mock response 1"},
                {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
                {"type": "text", "content": "Final response"}
            ]
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert len(config.llm) == 3
        # llm может быть list[dict] или list[MockLLMResponse]
        first = config.llm[0]
        type0 = first["type"] if isinstance(first, dict) else first.type
        second = config.llm[1]
        type1 = second["type"] if isinstance(second, dict) else second.type
        assert type0 == "text"
        assert type1 == "tool_call"

    def test_mock_nodes_in_skill(self):
        """Skill добавляет mock для nodes."""
        from apps.flows.src.mock.resolver import resolve_mock_config
        
        flow_mock = {"enabled": False}
        skill_mock = {
            "enabled": True,
            "nodes": {
                "main": {"response": "Mocked main response"}
            }
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert config.nodes["main"]["response"] == "Mocked main response"

    def test_mock_agents_in_skill(self):
        """Skill добавляет mock для agents."""
        from apps.flows.src.mock.resolver import resolve_mock_config
        
        flow_mock = {"enabled": False}
        skill_mock = {
            "enabled": True,
            "flows": {
                "subagent": "Mocked subagent response"
            }
        }

        config = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)

        assert config.flows["subagent"] == "Mocked subagent response"


class TestSkillCombinedOverrides:
    """Комбинированные переопределения."""

    def test_full_skill_override(self, container):
        """Skill переопределяет все компоненты (кроме mock - резолвится отдельно)."""
        from apps.flows.src.mock.resolver import resolve_mock_config
        
        config = FlowConfig(
            flow_id="test_full",
            name="Test",
            entry="default_entry",
            nodes={
                "default_entry": {"type": "llm_node", "prompt": "Default", "tools": ["t1"]},
                "helper": {"type": "code", "code": "def run(s): return s"}
            },
            edges=[
                Edge(from_node="default_entry", to_node="helper"),
                Edge(from_node="helper", to_node=None)
            ],
            variables={
                "company": "BaseCompany",
                "mode": "default"
            },
            mock={"enabled": False},
            branches={
                "full": BranchConfig(
                    name="Full Override",
                    entry="custom_entry",
                    nodes={
                        "custom_entry": {"type": "llm_node", "prompt": "Custom", "tools": ["t2"]}
                    },
                    nodes_mode=MergeMode.REPLACE,
                    edges=[Edge(from_node="custom_entry", to_node=None)],
                    edges_mode=MergeMode.REPLACE,
                    variables={"mode": "custom", "skill_var": "value"},
                    variables_mode=MergeMode.MERGE,
                    mock={
                        "enabled": True,
                        "tools": {"t2": "mock"}
                    }
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "full")

        # Entry
        assert result["entry"] == "custom_entry"

        # Nodes (replaced)
        assert "default_entry" not in result["nodes"]
        assert "helper" not in result["nodes"]
        assert "custom_entry" in result["nodes"]

        # Edges (replaced)
        assert len(result["edges"]) == 1
        assert result["edges"][0].from_node == "custom_entry"

        # Variables (merged)
        assert result["variables"]["company"] == "BaseCompany"  # Из base
        assert result["variables"]["mode"] == "custom"  # Override
        assert result["variables"]["skill_var"] == "value"  # Добавлен

        # Mock резолвится отдельно
        skill = config.branches["full"]
        mock_config = resolve_mock_config(
            flow_mock=config.mock,
            skill_mock=skill.mock
        )
        assert mock_config.enabled is True
        assert mock_config.tools["t2"] == "mock"

    def test_example_react_concise_skill(self, container):
        """Реальный пример: skill concise из example_react."""
        config = FlowConfig(
            flow_id="example_react_test",
            name="Example React",
            entry="main",
            nodes={
                "main": {"type": "llm_node", "node_id": "example_main_agent"}
            },
            edges=[Edge(from_node="main", to_node=None)],
            variables={
                "company_name": {"value": "@var:company_name", "public": True},
                "max_response_length": {"value": "500", "public": True}
            },
            branches={
                "concise": BranchConfig(
                    name="Краткие ответы",
                    description="Режим коротких ответов",
                    variables={
                        "max_response_length": {"value": "200", "public": False}
                    },
                    variables_mode=MergeMode.MERGE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "concise")

        # max_response_length переопределен
        assert result["variables"]["max_response_length"] == "200"
        # company_name сохранен
        assert "@var:company_name" in str(result["variables"]["company_name"])

    def test_example_graph_orders_only_skill(self, container):
        """Реальный пример: skill orders_only из example_graph."""
        config = FlowConfig(
            flow_id="example_graph_test",
            name="Example Graph",
            entry="classifier",
            nodes={
                "classifier": {
                    "type": "code",
                    "code": "async def run(state):\n    content = state.get('content', '').lower()\n    if 'заказ' in content:\n        state['route'] = 'order'\n    elif 'жалоб' in content:\n        state['route'] = 'complaint'\n    else:\n        state['route'] = 'general'\n    return state"
                },
                "order_processor": {"type": "llm_node", "prompt": "Order"},
                "complaint_processor": {"type": "llm_node", "prompt": "Complaint"},
                "general_processor": {"type": "llm_node", "prompt": "General"}
            },
            edges=[
                Edge(from_node="classifier", to_node="order_processor", condition="route == 'order'"),
                Edge(from_node="classifier", to_node="complaint_processor", condition="route == 'complaint'"),
                Edge(from_node="classifier", to_node="general_processor", condition="route == 'general'"),
                Edge(from_node="order_processor", to_node=None),
                Edge(from_node="complaint_processor", to_node=None),
                Edge(from_node="general_processor", to_node=None)
            ],
            branches={
                "orders_only": BranchConfig(
                    name="Только заказы",
                    nodes={
                        "classifier": {
                            "type": "code",
                            "code": "async def run(state):\n    content = state.get('content', '').lower()\n    if 'заказ' in content or 'order' in content:\n        state['route'] = 'order'\n    else:\n        state['route'] = 'general'\n    return state"
                        }
                    },
                    nodes_mode=MergeMode.MERGE,
                    edges=[
                        Edge(from_node="classifier", to_node="order_processor", condition="route == 'order'"),
                        Edge(from_node="classifier", to_node="general_processor", condition="route == 'general'"),
                        Edge(from_node="order_processor", to_node=None),
                        Edge(from_node="general_processor", to_node=None)
                    ],
                    edges_mode=MergeMode.REPLACE
                )
            }
        )

        result = container.flow_factory._apply_branch(config, "orders_only")

        # classifier переопределен
        assert "order" in result["nodes"]["classifier"]["code"]
        assert "жалоб" not in result["nodes"]["classifier"]["code"]  # Убрано

        # edges заменены
        edge_conditions = [e.condition for e in result["edges"] if e.condition]
        assert any("order" in c for c in edge_conditions)
        assert not any("complaint" in c for c in edge_conditions)  # Убрано

