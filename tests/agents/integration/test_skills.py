"""
Интеграционные тесты для Skills.
Тестирует переопределение параметров flow через skills.
"""

import pytest

from apps.agents.src.agent import Agent
from apps.agents.src.models import Edge, AgentConfig, MergeMode, SkillConfig
from apps.agents.src.services.agent_factory import AgentFactory
from core.state import ExecutionState


class TestSkillConfig:
    """Тесты SkillConfig модели."""

    def test_skill_config_defaults(self):
        """Значения по умолчанию."""
        skill = SkillConfig(name="Test Skill")

        assert skill.name == "Test Skill"
        assert skill.description == ""
        assert skill.tags == []
        assert skill.entry is None
        assert skill.nodes is None
        assert skill.edges is None
        assert skill.variables == {}
        assert skill.nodes_mode == MergeMode.REPLACE
        assert skill.edges_mode == MergeMode.REPLACE
        assert skill.variables_mode == MergeMode.MERGE

    def test_skill_config_full(self):
        """Полный конфиг skill."""
        skill = SkillConfig(
            name="Refund",
            description="Обработка возвратов",
            tags=["refund", "support"],
            entry="refund_start",
            nodes={
                "refund_agent": {"type": "react_node", "prompt": "Handle refunds"}
            },
            nodes_mode=MergeMode.MERGE,
            edges=[Edge(from_node="refund_start", to_node="refund_agent")],
            edges_mode=MergeMode.REPLACE,
            variables={"policy": "strict"},
            variables_mode=MergeMode.MERGE,
        )

        assert skill.name == "Refund"
        assert skill.entry == "refund_start"
        assert skill.nodes_mode == MergeMode.MERGE
        assert "refund_agent" in skill.nodes


class TestAgentConfigWithSkills:
    """Тесты AgentConfig со skills."""

    def test_agent_config_without_skills(self):
        """AgentConfig без skills."""
        config = AgentConfig(
            agent_id="test_flow",
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
        )

        assert config.skills == {}

    def test_agent_config_with_skills(self):
        """AgentConfig со skills."""
        config = AgentConfig(
            agent_id="multi_skill_flow",
            name="Multi Skill Agent",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
            skills={
                "default": SkillConfig(name="Default", description="Default skill"),
                "refund": SkillConfig(
                    name="Refund",
                    description="Refund processing",
                    entry="refund_main",
                    variables={"mode": "refund"},
                ),
            },
        )

        assert len(config.skills) == 2
        assert "default" in config.skills
        assert "refund" in config.skills
        assert config.skills["refund"].entry == "refund_main"


class TestApplySkill:
    """Тесты применения skill к конфигу."""

    def test_apply_skill_entry(self, container):
        """Применение entry из skill."""
        config = AgentConfig(
            agent_id="test",
            name="Test",
            entry="default_entry",
            nodes={
                "default_entry": {"type": "code", "code": "def run(s): return s"},
                "skill_entry": {"type": "code", "code": "def run(s): return s"},
            },
            edges=[
                Edge(from_node="default_entry", to_node=None),
                Edge(from_node="skill_entry", to_node=None),
            ],
            skills={
                "custom": SkillConfig(name="Custom", entry="skill_entry"),
            },
        )

        effective = container.agent_factory._apply_skill(config, "custom")

        assert effective["entry"] == "skill_entry"

    def test_apply_skill_variables_merge(self, container):
        """Мерж variables (по умолчанию)."""
        config = AgentConfig(
            agent_id="test",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
            variables={"base_var": "base_value", "shared": "from_flow"},
            skills={
                "custom": SkillConfig(
                    name="Custom",
                    variables={"skill_var": "skill_value", "shared": "from_skill"},
                ),
            },
        )

        effective = container.agent_factory._apply_skill(config, "custom")

        assert effective["variables"]["base_var"] == "base_value"
        assert effective["variables"]["skill_var"] == "skill_value"
        assert effective["variables"]["shared"] == "from_skill"

    def test_apply_skill_variables_replace(self, container):
        """Замена variables."""
        config = AgentConfig(
            agent_id="test",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
            variables={"base_var": "base_value"},
            skills={
                "custom": SkillConfig(
                    name="Custom",
                    variables={"skill_var": "skill_value"},
                    variables_mode=MergeMode.REPLACE,
                ),
            },
        )

        effective = container.agent_factory._apply_skill(config, "custom")

        # effective["variables"] содержит простые значения (после извлечения из AgentVariableConfig)
        assert "base_var" not in effective["variables"]
        assert effective["variables"]["skill_var"] == "skill_value"

    def test_apply_skill_nodes_replace(self, container):
        """Замена nodes (по умолчанию)."""
        config = AgentConfig(
            agent_id="test",
            name="Test",
            entry="main",
            nodes={
                "main": {"type": "code", "code": "def run(s): return s"},
                "helper": {"type": "code", "code": "def run(s): return s"},
            },
            edges=[Edge(from_node="main", to_node=None)],
            skills={
                "custom": SkillConfig(
                    name="Custom",
                    entry="custom_main",
                    nodes={
                        "custom_main": {"type": "code", "code": "def run(s): return s"},
                    },
                ),
            },
        )

        effective = container.agent_factory._apply_skill(config, "custom")

        assert "main" not in effective["nodes"]
        assert "helper" not in effective["nodes"]
        assert "custom_main" in effective["nodes"]

    def test_apply_skill_nodes_merge(self, container):
        """Мерж nodes."""
        config = AgentConfig(
            agent_id="test",
            name="Test",
            entry="main",
            nodes={
                "main": {"type": "react_node", "prompt": "Default prompt", "tools": ["tool1"]},
            },
            edges=[Edge(from_node="main", to_node=None)],
            skills={
                "custom": SkillConfig(
                    name="Custom",
                    nodes={
                        "main": {"prompt": "Custom prompt", "llm": {"temperature": 0.1}},
                        "new_node": {"type": "code", "code": "def run(s): return s"},
                    },
                    nodes_mode=MergeMode.MERGE,
                ),
            },
        )

        effective = container.agent_factory._apply_skill(config, "custom")

        assert effective["nodes"]["main"]["prompt"] == "Custom prompt"
        assert effective["nodes"]["main"]["tools"] == ["tool1"]
        assert effective["nodes"]["main"]["llm"]["temperature"] == 0.1
        assert "new_node" in effective["nodes"]

    def test_apply_skill_edges_replace(self, container):
        """Замена edges (по умолчанию)."""
        config = AgentConfig(
            agent_id="test",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[
                Edge(from_node="main", to_node="step2"),
                Edge(from_node="step2", to_node=None),
            ],
            skills={
                "custom": SkillConfig(
                    name="Custom",
                    edges=[Edge(from_node="main", to_node=None)],
                ),
            },
        )

        effective = container.agent_factory._apply_skill(config, "custom")

        assert len(effective["edges"]) == 1
        assert effective["edges"][0].from_node == "main"
        assert effective["edges"][0].to_node is None

    def test_apply_skill_edges_merge(self, container):
        """Мерж edges по паре (from_node, to_node)."""
        config = AgentConfig(
            agent_id="test",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[
                Edge(from_node="main", to_node="step2"),
                Edge(from_node="step2", to_node=None),
            ],
            skills={
                "custom": SkillConfig(
                    name="Custom",
                    edges=[Edge(from_node="main", to_node="step3")],
                    edges_mode=MergeMode.MERGE,
                ),
            },
        )

        effective = container.agent_factory._apply_skill(config, "custom")

        assert len(effective["edges"]) == 3
        from_nodes = [e.from_node for e in effective["edges"]]
        assert from_nodes.count("main") == 2
        assert "step2" in from_nodes
        
        main_edges = [e for e in effective["edges"] if e.from_node == "main"]
        assert len(main_edges) == 2
        main_to_nodes = {e.to_node for e in main_edges}
        assert main_to_nodes == {"step2", "step3"}

    def test_apply_skill_unknown_skill(self, container):
        """Неизвестный skill возвращает базовый конфиг."""
        config = AgentConfig(
            agent_id="test",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
            skills={
                "known": SkillConfig(name="Known", entry="other"),
            },
        )

        effective = container.agent_factory._apply_skill(config, "unknown")

        assert effective["entry"] == "main"

    def test_apply_skill_default_without_skills(self, container):
        """default skill при пустых skills."""
        config = AgentConfig(
            agent_id="test",
            name="Test",
            entry="main",
            nodes={"main": {"type": "code", "code": "def run(s): return s"}},
            edges=[Edge(from_node="main", to_node=None)],
        )

        effective = container.agent_factory._apply_skill(config, "default")

        assert effective["entry"] == "main"


class TestFlowWithSkills:
    """Интеграционные тесты Agent со skills."""

    @pytest.mark.asyncio
    async def test_flow_execution_with_skill_entry(self):
        """Выполнение flow с skill entry."""
        config = AgentConfig(
            agent_id="skill_flow",
            name="Skill Agent",
            entry="default_start",
            nodes={
                "default_start": {
                    "type": "code",
                    "code": "def run(s): s['path'] = 'default'; return s",
                },
                "skill_start": {
                    "type": "code",
                    "code": "def run(s): s['path'] = 'skill'; return s",
                },
            },
            edges=[
                Edge(from_node="default_start", to_node=None),
                Edge(from_node="skill_start", to_node=None),
            ],
            skills={
                "custom": SkillConfig(name="Custom", entry="skill_start"),
            },
        )

        flow_default = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": [
                    {"from": e.from_node, "to": e.to_node, "condition": e.condition}
                    for e in config.edges
                ],
            },
            variables={},
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await flow_default.run(state)
        assert result["path"] == "default"

        flow_skill = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": "skill_start",
                "nodes": config.nodes,
                "edges": [
                    {"from": e.from_node, "to": e.to_node, "condition": e.condition}
                    for e in config.edges
                ],
            },
            variables={},
        )
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await flow_skill.run(state)
        assert result["path"] == "skill"

    @pytest.mark.asyncio
    async def test_flow_execution_with_skill_variables(self):
        """Выполнение flow с skill variables."""
        flow = await Agent.from_config(
            config={
                "id": "var_flow",
                "name": "Var Agent",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "code",
                        "code": """
def run(state):
    vars = state.get('variables', {})
    state['mode'] = vars.get('mode', 'unknown')
    return state
""",
                    }
                },
                "edges": [{"from": "main", "to": None}],
            },
            variables={"mode": "refund", "extra": "skill_var"},
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await flow.run(state)

        assert result["mode"] == "refund"
        assert result.variables["extra"] == "skill_var"

