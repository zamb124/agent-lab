"""
Тесты для ChatOpenAIWithBilling - проверка передачи tools в OpenRouter API.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from apps.agents.services.llm_billing_wrapper import ChatOpenAIWithBilling


@tool
async def calculator_tool(expression: str) -> str:
    """Вычисляет математическое выражение

    Args:
        expression: Математическое выражение для вычисления

    Returns:
        Результат вычисления
    """
    return str(eval(expression))


@tool
async def get_weather(city: str, units: str = "celsius") -> str:
    """Получает погоду в городе

    Args:
        city: Название города
        units: Единицы измерения температуры

    Returns:
        Информация о погоде
    """
    return f"Погода в {city}: солнечно, 25{units}"


@pytest_asyncio.fixture
async def llm_with_billing(migrated_db, billing_service):
    """Создает LLM с биллингом для тестов
    
    Зависит от migrated_db для инициализации контейнера
    """
    llm = ChatOpenAIWithBilling(
        api_key="test-key",
        model="anthropic/claude-sonnet-4.5",
        temperature=0.2,
        max_tokens=8192
    )
    llm._billing_service = billing_service
    
    return llm


class TestToolsInPayload:
    """Тесты передачи tools в OpenRouter API"""

    @pytest.mark.asyncio
    async def test_bind_tools_saves_tools(self, llm_with_billing):
        """Проверяет что bind_tools сохраняет tools в LLM"""
        tools = [calculator_tool, get_weather]

        result = llm_with_billing.bind_tools(tools)

        assert result is llm_with_billing
        assert llm_with_billing._bound_tools == tools
        assert len(llm_with_billing._bound_tools) == 2

    @pytest.mark.asyncio
    async def test_convert_tools_to_openrouter_format(self, llm_with_billing):
        """Проверяет конвертацию LangChain tools в формат OpenRouter"""
        tools = [calculator_tool, get_weather]

        openrouter_tools = llm_with_billing._convert_tools_to_openrouter_format(tools)

        assert len(openrouter_tools) == 2

        # Проверяем первый tool
        calc_tool = openrouter_tools[0]
        assert calc_tool["type"] == "function"
        assert calc_tool["function"]["name"] == "calculator_tool"
        assert "Вычисляет математическое выражение" in calc_tool["function"]["description"]
        assert "expression" in calc_tool["function"]["parameters"]["properties"]
        assert "expression" in calc_tool["function"]["parameters"]["required"]

        # Проверяем второй tool
        weather_tool = openrouter_tools[1]
        assert weather_tool["type"] == "function"
        assert weather_tool["function"]["name"] == "get_weather"
        assert "Получает погоду" in weather_tool["function"]["description"]
        assert "city" in weather_tool["function"]["parameters"]["properties"]
        assert "units" in weather_tool["function"]["parameters"]["properties"]
        assert "city" in weather_tool["function"]["parameters"]["required"]

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_tools_in_request_payload(self, mock_client_class, llm_with_billing, test_context):
        """Проверяет что tools попадают в payload запроса к OpenRouter"""
        captured_payload = {}

        async def capture_post(url, **kwargs):
            if "json" in kwargs:
                captured_payload.update(kwargs["json"])

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Результат: 4"
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 10,
                    "total_tokens": 60
                }
            }
            return mock_response

        # Настраиваем мок для контекстного менеджера
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        # Привязываем tools
        tools = [calculator_tool]
        llm_with_tools = llm_with_billing.bind_tools(tools)

        # Делаем запрос
        messages = [HumanMessage(content="Вычисли 2+2")]
        await llm_with_tools.ainvoke(messages)

        # Проверяем что tools попали в payload
        assert "tools" in captured_payload, "tools должны быть в payload"
        assert len(captured_payload["tools"]) == 1

        tool = captured_payload["tools"][0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "calculator_tool"
        assert "parameters" in tool["function"]
        assert "expression" in tool["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_multiple_tools_in_payload(self, llm_with_billing):
        """Проверяет передачу нескольких tools в payload"""
        # Привязываем несколько tools
        tools = [calculator_tool, get_weather]
        llm_with_tools = llm_with_billing.bind_tools(tools)

        # Конвертируем в OpenRouter формат
        openrouter_tools = llm_with_tools._convert_tools_to_openrouter_format(tools)

        # Проверяем что все tools сконвертировались
        assert len(openrouter_tools) == 2

        tool_names = [t["function"]["name"] for t in openrouter_tools]
        assert "calculator_tool" in tool_names
        assert "get_weather" in tool_names

        # Проверяем структуру каждого tool
        for tool in openrouter_tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]


class TestToolCallsInResponse:
    """Тесты обработки tool_calls в ответе от OpenRouter"""

    @pytest.mark.asyncio
    async def test_parse_tool_call_from_response(self, llm_with_billing):
        """Проверяет парсинг tool_call из ответа OpenRouter"""
        # Симулируем ответ OpenRouter с tool_call
        mock_response_data = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "calculator_tool",
                            "arguments": '{"expression": "2+2"}'
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 20,
                "total_tokens": 70
            }
        }

        # Парсим tool_calls вручную используя внутренний метод
        message_data = mock_response_data["choices"][0]["message"]
        tool_calls = []

        for tc in message_data["tool_calls"]:
            tool_calls.append({
                "name": tc["function"]["name"],
                "args": llm_with_billing._parse_tool_arguments(tc["function"].get("arguments", "{}")),
                "id": tc.get("id", f"call_{tc['function']['name']}"),
                "type": "tool_call"
            })

        # Проверяем что tool_call распарсился
        assert len(tool_calls) == 1

        tool_call = tool_calls[0]
        assert tool_call["name"] == "calculator_tool"
        assert tool_call["args"] == {"expression": "2+2"}
        assert tool_call["id"] == "call_abc123"
        assert tool_call["type"] == "tool_call"

    @pytest.mark.asyncio
    async def test_parse_multiple_tool_calls(self, llm_with_billing):
        """Проверяет парсинг нескольких tool_calls"""
        # Симулируем ответ OpenRouter с несколькими tool_calls
        mock_response_data = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "calculator_tool",
                                "arguments": '{"expression": "2+2"}'
                            }
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city": "Москва", "units": "celsius"}'
                            }
                        }
                    ]
                },
                "finish_reason": "tool_calls"
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            }
        }

        # Парсим tool_calls вручную используя внутренний метод
        message_data = mock_response_data["choices"][0]["message"]
        tool_calls = []

        for tc in message_data["tool_calls"]:
            tool_calls.append({
                "name": tc["function"]["name"],
                "args": llm_with_billing._parse_tool_arguments(tc["function"].get("arguments", "{}")),
                "id": tc.get("id", f"call_{tc['function']['name']}"),
                "type": "tool_call"
            })

        # Проверяем что оба tool_calls распарсились
        assert len(tool_calls) == 2

        calc_call = tool_calls[0]
        assert calc_call["name"] == "calculator_tool"
        assert calc_call["args"]["expression"] == "2+2"
        assert calc_call["id"] == "call_1"

        weather_call = tool_calls[1]
        assert weather_call["name"] == "get_weather"
        assert weather_call["args"]["city"] == "Москва"
        assert weather_call["args"]["units"] == "celsius"
        assert weather_call["id"] == "call_2"

    @pytest.mark.asyncio
    async def test_parse_tool_arguments_valid_json(self, llm_with_billing):
        """Проверяет парсинг валидного JSON аргументов"""
        args = '{"city": "Москва", "units": "celsius"}'

        result = llm_with_billing._parse_tool_arguments(args)

        assert result == {"city": "Москва", "units": "celsius"}

    @pytest.mark.asyncio
    async def test_parse_tool_arguments_dict(self, llm_with_billing):
        """Проверяет что dict передается как есть"""
        args = {"city": "Москва", "units": "celsius"}

        result = llm_with_billing._parse_tool_arguments(args)

        assert result == args

    @pytest.mark.asyncio
    async def test_parse_tool_arguments_empty(self, llm_with_billing):
        """Проверяет обработку пустых аргументов"""
        assert llm_with_billing._parse_tool_arguments("") == {}
        assert llm_with_billing._parse_tool_arguments(None) == {}

    @pytest.mark.asyncio
    async def test_parse_tool_arguments_invalid_json(self, llm_with_billing):
        """Проверяет обработку невалидного JSON"""
        args = '{invalid json}'

        result = llm_with_billing._parse_tool_arguments(args)

        assert result == {}

    @pytest.mark.asyncio
    async def test_no_tool_calls_in_response(self, llm_with_billing):
        """Проверяет обработку ответа без tool_calls"""
        # Симулируем ответ OpenRouter без tool_calls
        mock_response_data = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Привет! Как дела?"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15
            }
        }

        # Проверяем что парсинг не создает tool_calls когда их нет
        message_data = mock_response_data["choices"][0]["message"]
        tool_calls = []

        if "tool_calls" in message_data and message_data["tool_calls"]:
            for tc in message_data["tool_calls"]:
                tool_calls.append({
                    "name": tc["function"]["name"],
                    "args": llm_with_billing._parse_tool_arguments(tc["function"].get("arguments", "{}")),
                    "id": tc.get("id", f"call_{tc['function']['name']}"),
                    "type": "tool_call"
                })

        # Проверяем что нет tool_calls
        assert len(tool_calls) == 0
        assert message_data["content"] == "Привет! Как дела?"

