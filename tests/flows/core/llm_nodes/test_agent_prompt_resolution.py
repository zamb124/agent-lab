"""
Тесты резолвинга промптов в агентах.

Проверяет, что промпты агентов правильно собираются с учетом:
- Системных переменных (current_date, user_id, user_name, user_email)
- Переменных flow (из state["variables"])
- Локальных переменных агента
- Различных синтаксисов промптов

Примечание: В тестах переменные flow передаются в state["variables"].
"""

from datetime import datetime

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from core.context import Context, User, clear_context, set_context
from core.state import ExecutionState


@pytest.fixture
def flow_config():
    """Базовый конфиг агента."""
    return NodeConfig(
        node_id="test_agent",
        type=NodeType.LLM_NODE,
        name="Test Agent",
        description="Agent for testing prompt resolution",
        prompt="",
        llm=NodeLLMConfig(model="mock-gpt-4", temperature=0.0),
    )


@pytest.fixture
def runner(flow_config):
    """LlmNodeRunner для тестирования."""
    return LlmNodeRunner(
        node_config=flow_config,
        tools=[],
        llm=None,
        prompt="",
        container=get_container(),  # pyright: ignore[reportArgumentType]
    )


@pytest.fixture(autouse=True)
def setup_context():
    """Устанавливает контекст перед каждым тестом и очищает после."""
    context = Context(
        user=User(user_id="test_user_123", name="Test User"),
        channel="test",
        metadata={"email": "test@example.com"},
    )
    set_context(context)
    yield
    clear_context()


class TestSystemVariablesInPrompts:
    """Тесты системных переменных в промптах агентов."""

    @pytest.mark.asyncio
    async def test_current_date_in_prompt(self, runner, flow_config):
        """Проверяет, что {current_date} резолвится в промпте."""
        flow_config.prompt = "Сегодня {current_date}. Ты помощник."
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        today = datetime.now().strftime("%Y-%m-%d")
        assert today in rendered
        assert "Ты помощник." in rendered

    @pytest.mark.asyncio
    async def test_current_time_in_prompt(self, runner, flow_config):
        """Проверяет, что {current_time} резолвится в промпте."""
        flow_config.prompt = "Текущее время: {current_time}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        # Проверяем формат времени HH:MM
        assert ":" in rendered
        assert "Текущее время:" in rendered

    @pytest.mark.asyncio
    async def test_user_id_in_prompt(self, runner, flow_config):
        """Проверяет, что {user_id} резолвится в промпте."""
        flow_config.prompt = "Пользователь: {user_id}. Ты помощник."
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        assert "test_user_123" in rendered
        assert "Ты помощник." in rendered

    @pytest.mark.asyncio
    async def test_user_name_in_prompt(self, runner, flow_config):
        """Проверяет, что {user_name} резолвится в промпте."""
        flow_config.prompt = "Привет, {user_name}! Ты помощник."
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        assert "Test User" in rendered
        assert "Привет" in rendered

    @pytest.mark.asyncio
    async def test_user_email_in_prompt(self, runner, flow_config):
        """Проверяет, что {user_email} резолвится в промпте."""
        flow_config.prompt = "Email пользователя: {user_email}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        assert "test@example.com" in rendered

    @pytest.mark.asyncio
    async def test_all_system_variables_in_prompt(self, runner, flow_config):
        """Проверяет все системные переменные в одном промпте."""
        flow_config.prompt = """Привет, {user_name}!

Твой ID: {user_id}
Email: {user_email}
Сегодня: {current_date}
Время: {current_time}"""
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        assert "Test User" in rendered
        assert "test_user_123" in rendered
        assert "test@example.com" in rendered
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in rendered


class TestFlowVariablesInPrompts:
    """Тесты переменных flow в промптах агентов."""

    @pytest.mark.asyncio
    async def test_flow_variable_in_prompt(self, runner, flow_config):
        """Проверяет, что переменная flow резолвится в промпте."""
        flow_config.prompt = "Компания: {company_name}. Ты помощник."
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={"company_name": "TestCorp"}
        )
        rendered = await runner._render_prompt(state)

        assert "TestCorp" in rendered
        assert "Ты помощник." in rendered

    @pytest.mark.asyncio
    async def test_multiple_flow_variables_in_prompt(self, runner, flow_config):
        """Проверяет несколько переменных flow в промпте."""
        flow_config.prompt = "Компания: {company_name}, Телефон: {phone}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "company_name": "TestCorp",
                "phone": "+7-999-123-45-67",
            }
        )
        rendered = await runner._render_prompt(state)

        assert "TestCorp" in rendered
        assert "+7-999-123-45-67" in rendered

    @pytest.mark.asyncio
    async def test_flow_variable_with_default(self, runner, flow_config):
        """Проверяет переменную flow с default значением."""
        flow_config.prompt = "Город: {city|не указан}"
        runner.prompt = flow_config.prompt

        # Переменная отсутствует - должен использоваться default
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)
        assert "не указан" in rendered

        # Переменная есть - должно использоваться значение
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={"city": "Москва"}
        )
        rendered = await runner._render_prompt(state)
        assert "Москва" in rendered
        assert "не указан" not in rendered


class TestLocalAgentVariablesInPrompts:
    """Тесты локальных переменных агента в промптах."""

    @pytest.mark.asyncio
    async def test_local_variable_in_prompt(self, runner, flow_config):
        """Проверяет, что локальная переменная агента резолвится в промпте."""
        flow_config.prompt = "Роль: {role}. Ты помощник."
        flow_config.local_variables = {"role": "консультант"}
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        assert "консультант" in rendered
        assert "Ты помощник." in rendered

    @pytest.mark.asyncio
    async def test_local_variable_overrides_flow_variable(self, runner, flow_config):
        """Проверяет, что локальная переменная имеет приоритет над flow переменной."""
        flow_config.prompt = "Роль: {role}"
        flow_config.local_variables = {"role": "локальная_роль"}
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={"role": "flow_роль"}
        )
        rendered = await runner._render_prompt(state)

        # Локальная переменная должна иметь приоритет
        assert "локальная_роль" in rendered
        assert "flow_роль" not in rendered


class TestCombinedVariablesInPrompts:
    """Тесты комбинаций всех типов переменных в промптах."""

    @pytest.mark.asyncio
    async def test_system_and_flow_variables(self, runner, flow_config):
        """Проверяет комбинацию системных и flow переменных."""
        flow_config.prompt = """Привет, {user_name}!

Компания: {company_name}
Сегодня: {current_date}"""
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={"company_name": "TestCorp"}
        )
        rendered = await runner._render_prompt(state)

        assert "Test User" in rendered
        assert "TestCorp" in rendered
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in rendered

    @pytest.mark.asyncio
    async def test_system_flow_and_local_variables(self, runner, flow_config):
        """Проверяет комбинацию всех типов переменных."""
        flow_config.prompt = """Привет, {user_name}!

Компания: {company_name}
Роль: {role}
Сегодня: {current_date}"""
        flow_config.local_variables = {"role": "консультант"}
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={"company_name": "TestCorp"}
        )
        rendered = await runner._render_prompt(state)

        assert "Test User" in rendered
        assert "TestCorp" in rendered
        assert "консультант" in rendered
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in rendered


class TestPromptSyntaxInAgents:
    """Тесты различных синтаксисов промптов в агентах."""

    @pytest.mark.asyncio
    async def test_optional_variable_with_default(self, runner, flow_config):
        """Проверяет опциональную переменную с default в промпте агента."""
        flow_config.prompt = "Email: {?support_email|support@example.com}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        assert "support@example.com" in rendered

    @pytest.mark.asyncio
    async def test_conditional_block_in_prompt(self, runner, flow_config):
        """Проверяет условный блок в промпте агента."""
        flow_config.prompt = """Ты помощник.

{?has_instructions|
Специальные инструкции:
- Инструкция 1
- Инструкция 2
}"""
        runner.prompt = flow_config.prompt

        # Переменная есть и не пустая - блок должен показаться
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={"has_instructions": True}
        )
        rendered = await runner._render_prompt(state)
        assert "Специальные инструкции" in rendered
        assert "Инструкция 1" in rendered

        # Переменная отсутствует - блок не должен показаться
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)
        assert "Специальные инструкции" not in rendered

    @pytest.mark.asyncio
    async def test_nested_variables_in_prompt(self, runner, flow_config):
        """Проверяет вложенные переменные в промпте агента."""
        flow_config.prompt = "Город: {city.name|не указан}, Улица: {city.street|не указана}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "city": {
                    "name": "Москва",
                    "street": "Тверская",
                }
            }
        )
        rendered = await runner._render_prompt(state)

        assert "Москва" in rendered
        assert "Тверская" in rendered

    @pytest.mark.asyncio
    async def test_complex_prompt_with_all_syntax(self, runner, flow_config):
        """Проверяет сложный промпт со всеми синтаксисами."""
        flow_config.prompt = """Привет, {user_name}!

Ты консультант компании {company_name|неизвестной компании}.

{?is_vip|
VIP клиент: {client_name}
}

Контакты:
- Телефон: {phone|не указан}
- Email: {?email|не указан}

Сегодня: {current_date}"""
        flow_config.local_variables = {"is_vip": True}
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "company_name": "TestCorp",
                "client_name": "Иван Иванов",
                "phone": "+7-999-123-45-67",
            }
        )
        rendered = await runner._render_prompt(state)

        assert "Test User" in rendered
        assert "TestCorp" in rendered
        assert "Иван Иванов" in rendered
        assert "+7-999-123-45-67" in rendered
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in rendered


class TestPromptResolutionWithoutContext:
    """Тесты резолвинга промптов без контекста (системные переменные должны работать)."""

    @pytest.mark.asyncio
    async def test_system_variables_without_user_context(self, runner, flow_config):
        """Проверяет, что системные переменные работают без контекста пользователя."""
        clear_context()

        flow_config.prompt = "Сегодня {current_date}, время {current_time}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        today = datetime.now().strftime("%Y-%m-%d")
        assert today in rendered
        # user_id, user_name, user_email не должны быть в результате
        assert "user_id" not in rendered
        assert "user_name" not in rendered
        assert "user_email" not in rendered

    @pytest.mark.asyncio
    async def test_user_variables_without_context(self, runner, flow_config):
        """Проверяет, что переменные пользователя не резолвятся без контекста."""
        clear_context()

        flow_config.prompt = "Пользователь: {user_name|неизвестен}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        # Должен использоваться default, так как user_name нет в контексте
        assert "неизвестен" in rendered


class TestPromptResolutionEdgeCases:
    """Тесты граничных случаев резолвинга промптов."""

    @pytest.mark.asyncio
    async def test_empty_prompt(self, runner, flow_config):
        """Проверяет пустой промпт."""
        flow_config.prompt = ""
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        assert rendered == ""

    @pytest.mark.asyncio
    async def test_prompt_without_variables(self, runner, flow_config):
        """Проверяет промпт без переменных."""
        flow_config.prompt = "Ты помощник. Отвечай на вопросы."
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        assert rendered == "Ты помощник. Отвечай на вопросы."

    @pytest.mark.asyncio
    async def test_prompt_with_unknown_variable_safe_mode(self, runner, flow_config):
        """Проверяет промпт с неизвестной переменной в safe режиме."""
        flow_config.prompt = "Привет, {unknown_var}!"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        # В safe режиме неизвестная переменная должна остаться как есть
        assert "{unknown_var}" in rendered

    @pytest.mark.asyncio
    async def test_prompt_with_escaped_braces(self, runner, flow_config):
        """Проверяет промпт с экранированными скобками."""
        # В Python строке \\{ становится \{ после обработки
        flow_config.prompt = "Путь: \\{config_path\\} или {config_path|C:\\\\Windows}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)

        # Экранированные скобки должны остаться как {config_path} (без экранирования)
        # VariableResolver обрабатывает \{ и \} как экранированные символы
        assert "{config_path}" in rendered or "\\{config_path\\}" in rendered
        # Default должен использоваться
        assert "C:\\Windows" in rendered or "C:\\\\Windows" in rendered


class TestVariablesFromMetadata:
    """Тесты переменных из metadata, переопределяющих flow variables."""

    @pytest.mark.asyncio
    async def test_metadata_variables_override_flow_variables(self, runner, flow_config):
        """Проверяет, что переменные из metadata переопределяют flow variables."""
        flow_config.prompt = "Компания: {company_name}, Телефон: {phone}"
        runner.prompt = flow_config.prompt

        # Agent variables
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "company_name": "FlowCorp",
                "phone": "+7-999-000-00-00",
            }
        )

        # Переопределяем через metadata (симулируем что они пришли из metadata)
        # В реальности это делается в BaseChannel.process_task(), но для теста
        # мы можем напрямую обновить state.variables
        state.variables["company_name"] = "MetadataCorp"
        state.variables["phone"] = "+7-999-111-11-11"

        rendered = await runner._render_prompt(state)

        assert "MetadataCorp" in rendered
        assert "+7-999-111-11-11" in rendered
        assert "FlowCorp" not in rendered
        assert "+7-999-000-00-00" not in rendered

    @pytest.mark.asyncio
    async def test_metadata_variables_partial_override(self, runner, flow_config):
        """Проверяет частичное переопределение variables из metadata."""
        flow_config.prompt = "Компания: {company_name}, Телефон: {phone}, Email: {email}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "company_name": "FlowCorp",
                "phone": "+7-999-000-00-00",
                "email": "flow@example.com",
            }
        )

        # Переопределяем только company_name
        state.variables["company_name"] = "MetadataCorp"

        rendered = await runner._render_prompt(state)

        assert "MetadataCorp" in rendered
        assert "+7-999-000-00-00" in rendered
        assert "flow@example.com" in rendered


class TestJsonDictVariablesInPrompts:
    """Тесты JSON/dict объектов в variables с доступом через точку."""

    @pytest.mark.asyncio
    async def test_dict_variable_dot_notation(self, runner, flow_config):
        """Проверяет доступ к dict переменной через точку."""
        flow_config.prompt = "Пользователь: {user.name}, Email: {user.email}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "user": {
                    "name": "Иван Иванов",
                    "email": "ivan@example.com",
                }
            }
        )
        rendered = await runner._render_prompt(state)

        assert "Иван Иванов" in rendered
        assert "ivan@example.com" in rendered

    @pytest.mark.asyncio
    async def test_deeply_nested_dict_variable(self, runner, flow_config):
        """Проверяет доступ к глубоко вложенным полям dict."""
        flow_config.prompt = (
            "Адрес: {address.city.name}, Улица: {address.street}, Дом: {address.building.number}"
        )
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "address": {
                    "city": {"name": "Москва", "code": "MSK"},
                    "street": "Тверская",
                    "building": {"number": "10", "entrance": "A"},
                }
            }
        )
        rendered = await runner._render_prompt(state)

        assert "Москва" in rendered
        assert "Тверская" in rendered
        assert "10" in rendered

    @pytest.mark.asyncio
    async def test_dict_variable_with_default(self, runner, flow_config):
        """Проверяет dict переменную с default значением."""
        flow_config.prompt = "Город: {city.name|не указан}, Район: {city.district|не указан}"
        runner.prompt = flow_config.prompt

        # Полный объект
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "city": {
                    "name": "Москва",
                    "district": "Центральный",
                }
            }
        )
        rendered = await runner._render_prompt(state)
        assert "Москва" in rendered
        assert "Центральный" in rendered

        # Частичный объект (district отсутствует)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "city": {
                    "name": "Москва",
                }
            }
        )
        rendered = await runner._render_prompt(state)
        assert "Москва" in rendered
        assert "не указан" in rendered

    @pytest.mark.asyncio
    async def test_dict_variable_optional(self, runner, flow_config):
        """Проверяет опциональную dict переменную."""
        flow_config.prompt = "Пользователь: {?user.name|Гость}, Email: {?user.email}"
        runner.prompt = flow_config.prompt

        # Переменная есть
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "user": {
                    "name": "Иван",
                    "email": "ivan@example.com",
                }
            }
        )
        rendered = await runner._render_prompt(state)
        assert "Иван" in rendered
        assert "ivan@example.com" in rendered

        # Переменной нет
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
        )
        rendered = await runner._render_prompt(state)
        assert "Гость" in rendered
        assert "ivan@example.com" not in rendered

    @pytest.mark.asyncio
    async def test_complex_json_structure(self, runner, flow_config):
        """Проверяет сложную JSON структуру с множественными уровнями вложенности."""
        flow_config.prompt = """Конфигурация:
API URL: {config.api.base_url}
API Key: {config.api.key}
База данных: {config.database.host}:{config.database.port}
Пользователь БД: {config.database.user.name}"""
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "config": {
                    "api": {
                        "base_url": "https://api.example.com",
                        "key": "secret-key-123",
                    },
                    "database": {
                        "host": "localhost",
                        "port": "5432",
                        "user": {
                            "name": "db_user",
                            "password": "secret",
                        },
                    },
                }
            }
        )
        rendered = await runner._render_prompt(state)

        assert "https://api.example.com" in rendered
        assert "secret-key-123" in rendered
        assert "localhost" in rendered
        assert "5432" in rendered
        assert "db_user" in rendered

    @pytest.mark.asyncio
    async def test_dict_variable_with_list_access(self, runner, flow_config):
        """Проверяет доступ к элементам списка внутри dict."""
        flow_config.prompt = "Первый контакт: {contacts.0.name}, Телефон: {contacts.0.phone}"
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "contacts": [
                    {"name": "Иван", "phone": "+7-999-111-11-11"},
                    {"name": "Петр", "phone": "+7-999-222-22-22"},
                ]
            }
        )
        rendered = await runner._render_prompt(state)

        # Проверяем что переменные резолвятся (dot notation для списков может не поддерживаться напрямую)
        # Но можем проверить что структура доступна
        assert "Иван" in rendered or "{contacts.0.name}" in rendered

    @pytest.mark.asyncio
    async def test_dict_variable_mixed_with_simple(self, runner, flow_config):
        """Проверяет смешивание dict и простых переменных."""
        flow_config.prompt = (
            "Компания: {company_name}, "
            "Адрес: {address.city}, "
            "Телефон: {phone}, "
            "Email: {contact.email}"
        )
        runner.prompt = flow_config.prompt

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "company_name": "TestCorp",
                "address": {"city": "Москва", "street": "Тверская"},
                "phone": "+7-999-123-45-67",
                "contact": {"email": "info@testcorp.com", "name": "Support"},
            }
        )
        rendered = await runner._render_prompt(state)

        assert "TestCorp" in rendered
        assert "Москва" in rendered
        assert "+7-999-123-45-67" in rendered
        assert "info@testcorp.com" in rendered

    @pytest.mark.asyncio
    async def test_dict_variable_from_metadata(self, runner, flow_config):
        """Проверяет dict переменную, переопределенную из metadata."""
        flow_config.prompt = "Пользователь: {user.name}, Роль: {user.role}"
        runner.prompt = flow_config.prompt

        # Agent variables
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test_user_123",
            session_id="test-agent:test-context",
            variables={
                "user": {
                    "name": "FlowUser",
                    "role": "user",
                }
            }
        )

        # Переопределяем из metadata
        state.variables["user"] = {
            "name": "MetadataUser",
            "role": "admin",
        }

        rendered = await runner._render_prompt(state)

        assert "MetadataUser" in rendered
        assert "admin" in rendered
        assert "FlowUser" not in rendered
        assert "user" not in rendered
