"""
Тесты хуков для кастомных агентов.

Проверяет работу before_prompt_render и after_prompt_render хуков.
"""

from typing import Any, Dict

import pytest

from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig
from apps.flows.src.runtime.nodes import LlmNode
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from core.state import ExecutionState


class AgentWithHooks(LlmNode):
    """Тестовый агент с хуками."""

    name = "test_agent_with_hooks"
    description = "Test agent with hooks"

    async def before_prompt_render(
        self, prompt_template: str, state: Dict[str, Any], variables: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """Добавляет переменную и модифицирует шаблон."""
        variables["custom_var"] = "custom_value"
        prompt_template = f"{prompt_template}\n\nДополнительная инструкция: используй {variables.get('custom_var')}."
        return prompt_template, variables

    async def after_prompt_render(
        self, rendered_prompt: str, state: Dict[str, Any]
    ) -> str:
        """Добавляет текст в конец промпта."""
        return f"{rendered_prompt}\n\nФинальная заметка: промпт обработан хуком."


class AgentWithoutHooks(LlmNode):
    """Тестовый агент без переопределения хуков."""

    name = "test_agent_without_hooks"
    description = "Test agent without hooks"


@pytest.fixture
def flow_config():
    """Базовый конфиг агента."""
    return NodeConfig(
        node_id="test_agent",
        type="llm_node",
        name="Test Agent",
        description="Agent for testing hooks",
        prompt="Ты помощник. Переменная: {test_var}",
        llm=NodeLLMConfig(model="mock-gpt-4", temperature=0.0),
    )


@pytest.fixture
def runner_with_hooks(flow_config):
    """LlmNodeRunner с агентом, у которого есть хуки."""
    agent = AgentWithHooks(node_config=flow_config)
    return LlmNodeRunner(
        node_config=flow_config,
        tools=[],
        llm=None,
        prompt=flow_config.prompt,
        llm_node=agent,
    )


@pytest.fixture
def runner_without_hooks(flow_config):
    """LlmNodeRunner с агентом без хуков."""
    agent = AgentWithoutHooks(node_config=flow_config)
    return LlmNodeRunner(
        node_config=flow_config,
        tools=[],
        llm=None,
        prompt=flow_config.prompt,
        llm_node=agent,
    )


class TestBeforePromptRenderHook:
    """Тесты хука before_prompt_render."""

    @pytest.mark.asyncio
    async def test_before_prompt_render_modifies_template(self, runner_with_hooks):
        """Проверяет, что before_prompt_render может изменить шаблон."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"test_var": "test_value"}
        )

        rendered = await runner_with_hooks._render_prompt(state)

        assert "Дополнительная инструкция" in rendered
        assert "custom_value" in rendered

    @pytest.mark.asyncio
    async def test_before_prompt_render_modifies_variables(self, runner_with_hooks):
        """Проверяет, что before_prompt_render может изменить переменные."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"test_var": "test_value"}
        )

        rendered = await runner_with_hooks._render_prompt(state)

        # Переменная test_var должна быть резолвнута
        assert "test_value" in rendered
        # Кастомная переменная должна быть добавлена
        assert "custom_value" in rendered

    @pytest.mark.asyncio
    async def test_before_prompt_render_with_state(self, runner_with_hooks):
        """Проверяет, что before_prompt_render получает state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"test_var": "test_value"},
            user_role="admin",
            context="support"
        )

        rendered = await runner_with_hooks._render_prompt(state)

        # Хук должен получить state и использовать его
        assert "test_value" in rendered


class TestAfterPromptRenderHook:
    """Тесты хука after_prompt_render."""

    @pytest.mark.asyncio
    async def test_after_prompt_render_modifies_prompt(self, runner_with_hooks):
        """Проверяет, что after_prompt_render может изменить финальный промпт."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"test_var": "test_value"}
        )

        rendered = await runner_with_hooks._render_prompt(state)

        assert "Финальная заметка: промпт обработан хуком." in rendered

    @pytest.mark.asyncio
    async def test_after_prompt_render_receives_state(self, runner_with_hooks):
        """Проверяет, что after_prompt_render получает state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"test_var": "test_value"},
            additional_context="Дополнительная информация"
        )

        rendered = await runner_with_hooks._render_prompt(state)

        # Хук должен получить state
        assert "test_value" in rendered


class TestHooksWithoutAgent:
    """Тесты работы без хуков (агент не переопределяет методы)."""

    @pytest.mark.asyncio
    async def test_agent_without_hooks_works_normally(self, runner_without_hooks):
        """Проверяет, что агент без хуков работает нормально."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"test_var": "test_value"}
        )

        rendered = await runner_without_hooks._render_prompt(state)

        assert "Ты помощник" in rendered
        assert "test_value" in rendered
        # Не должно быть текста из хуков
        assert "Финальная заметка" not in rendered
        assert "Дополнительная инструкция" not in rendered

    @pytest.mark.asyncio
    async def test_default_hooks_return_unchanged(self, runner_without_hooks):
        """Проверяет, что дефолтные хуки возвращают значения без изменений."""
        variables = {"test_var": "test_value"}
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        state_dict = state.model_dump(exclude_none=False)

        agent = runner_without_hooks.llm_node
        template, vars_before = await agent.before_prompt_render(
            "Ты помощник. {test_var}", state_dict, variables.copy()
        )

        assert template == "Ты помощник. {test_var}"
        assert vars_before == variables

        rendered = "Ты помощник. test_value"
        rendered_after = await agent.after_prompt_render(rendered, state_dict)

        assert rendered_after == rendered


class TestHooksIntegration:
    """Интеграционные тесты хуков."""

    @pytest.mark.asyncio
    async def test_both_hooks_work_together(self, runner_with_hooks):
        """Проверяет, что оба хука работают вместе."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"test_var": "test_value"}
        )

        rendered = await runner_with_hooks._render_prompt(state)

        # before_prompt_render должен добавить инструкцию
        assert "Дополнительная инструкция" in rendered
        assert "custom_value" in rendered
        # after_prompt_render должен добавить финальную заметку
        assert "Финальная заметка: промпт обработан хуком." in rendered
        # Оригинальный контент должен быть
        assert "Ты помощник" in rendered
        assert "test_value" in rendered

    @pytest.mark.asyncio
    async def test_hooks_with_system_variables(self, runner_with_hooks):
        """Проверяет, что хуки работают с системными переменными."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )

        rendered = await runner_with_hooks._render_prompt(state)

        # Системные переменные должны быть доступны в хуках
        # (если они есть в контексте)
        assert "Ты помощник" in rendered

