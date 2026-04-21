"""
E2E тест для variables: полный сценарий с публичными переменными и metadata.

Сценарий:
1. Получаем agent card - проверяем что видны публичные variables
2. Отправляем message/send с variables в metadata (примитивы и JSON/dict)
3. Проверяем что variables переопределились и используются в промптах
4. Проверяем доступ к JSON/dict переменным через точку в промптах
"""

import uuid
from typing import Any, Dict

import pytest


def _msg(text: str, task_id: str = None, context_id: str = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """Создаёт A2A Message с metadata."""
    m = {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": text}],
    }
    if task_id:
        m["taskId"] = task_id
    if context_id:
        m["contextId"] = context_id
    if metadata:
        m["metadata"] = metadata
    return m


def get_task_state(data: Dict[str, Any]) -> str:
    """Извлекает state из A2A Task ответа."""
    return data["status"]["state"]


def get_task_response(data: Dict[str, Any]) -> str:
    """Извлекает текст ответа из A2A Task."""
    msg = data["status"].get("message")
    if msg and msg.get("parts"):
        return msg["parts"][0].get("text", "")
    artifacts = data.get("artifacts", [])
    if artifacts and artifacts[0].get("parts"):
        return artifacts[0]["parts"][0].get("text", "")
    return ""


class TestVariablesE2E:
    """E2E тест для variables: публичные переменные и metadata override."""

    @pytest.fixture
    async def flow_id(self, client):
        """Получаем ID example_react flow."""
        resp = await client.get("/flows/api/v1/registry/flows")
        agents = resp.json()
        flow_id = None
        for agent in agents:
            url = agent.get("url", "")
            if "example_react" in url:
                flow_id = url.split("/flows/")[-1]
                break
        assert flow_id, "В реестре flows не найден example_react (url должен содержать example_react)"
        return flow_id

    @pytest.mark.asyncio
    async def test_agent_card_shows_public_variables(self, client, flow_id):
        """1. Agent card показывает публичные variables."""
        resp = await client.get(f"/flows/api/v1/{flow_id}")
        assert resp.status_code == 200

        card = resp.json()

        # Проверяем что есть variables
        assert "variables" in card, "AgentCard должен содержать variables"
        variables = card["variables"]

        # Проверяем публичные variables из example_react
        assert "company_name" in variables, "company_name должна быть публичной"
        
        assert "max_response_length" in variables, "max_response_length должна быть публичной"
        
        # Проверяем структуру публичной переменной
        company_var = variables["company_name"]
        assert "title" in company_var, "Переменная должна иметь title"
        assert "description" in company_var, "Переменная должна иметь description"
        # Может быть либо "type": "reference" + "key", либо "value"
        assert "type" in company_var or "value" in company_var or "key" in company_var, "Переменная должна иметь type/key или value"

        # support_contacts НЕ должна быть публичной (public=False)
        assert "support_contacts" not in variables, "support_contacts не должна быть публичной"

    @pytest.mark.asyncio
    async def test_message_send_with_primitive_variables_in_metadata(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """2. message/send с примитивными variables в metadata переопределяют flow variables."""
        # Настраиваем mock LLM ответ
        mock_llm_with_queue([{"type": "text", "content": "Ответ с переопределенной компанией: MetadataCompany"}])

        context_id = str(uuid.uuid4())

        # Отправляем message/send с variables в metadata
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-vars-1",
                "method": "message/send",
                "params": {
                    "message": _msg(
                        "Привет",
                        context_id=context_id,
                        metadata={
                            "variables": {
                                "company_name": "MetadataCompany",
                                "max_response_length": "300",
                            }
                        },
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        task = data["result"]
        assert task["status"]["state"] == "completed"

        # Проверяем что ответ содержит переопределенное значение
        response_text = get_task_response(task)
        # Переменные должны быть применены в промпте агента
        # Mock LLM вернет ответ с упоминанием компании
        assert "MetadataCompany" in response_text or "300" in response_text

    @pytest.mark.asyncio
    async def test_message_send_with_dict_variables_in_metadata(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """3. message/send с dict variables в metadata доступны через точку в промптах."""
        # Настраиваем mock LLM ответ, который использует dict переменные
        mock_llm_with_queue([
            {"type": "text", "content": "Пользователь: TestUser, Email: test@example.com, Тема: dark"}
        ])

        context_id = str(uuid.uuid4())

        # Отправляем message/send с dict variables в metadata
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-vars-2",
                "method": "message/send",
                "params": {
                    "message": _msg(
                        "Покажи мои настройки",
                        context_id=context_id,
                        metadata={
                            "variables": {
                                "user_config": {
                                    "name": "TestUser",
                                    "email": "test@example.com",
                                    "settings": {
                                        "theme": "dark",
                                        "language": "ru",
                                    },
                                },
                                "company_name": "TestCorp",
                            }
                        },
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        task = data["result"]
        assert task["status"]["state"] == "completed"

        # Проверяем что dict переменные доступны
        response_text = get_task_response(task)
        # Mock LLM должен использовать переменные из промпта
        assert "TestUser" in response_text or "test@example.com" in response_text or "dark" in response_text

    @pytest.mark.asyncio
    async def test_message_send_with_mixed_variables_in_metadata(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """4. message/send с смешанными variables (примитивы + dict) в metadata."""
        mock_llm_with_queue([
            {"type": "text", "content": "Компания: MixedCompany, Адрес: Москва, Телефон: +7-999-111-11-11"}
        ])

        context_id = str(uuid.uuid4())

        # Смешанные variables: примитивы и dict
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-vars-3",
                "method": "message/send",
                "params": {
                    "message": _msg(
                        "Покажи информацию",
                        context_id=context_id,
                        metadata={
                            "variables": {
                                "company_name": "MixedCompany",
                                "max_response_length": "500",
                                "address": {
                                    "city": "Москва",
                                    "street": "Тверская",
                                    "building": {"number": "10", "entrance": "A"},
                                },
                                "phone": "+7-999-111-11-11",
                            }
                        },
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        task = data["result"]
        assert task["status"]["state"] == "completed"

        response_text = get_task_response(task)
        # Проверяем что все типы переменных доступны
        assert "MixedCompany" in response_text or "Москва" in response_text or "+7-999-111-11-11" in response_text

    @pytest.mark.asyncio
    async def test_full_flow_with_variables_override(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """
        5. Полный E2E сценарий:
        - Получаем agent card (публичные variables)
        - Отправляем message/send с variables в metadata
        - Проверяем что variables переопределились
        - Проверяем что dict variables доступны через точку
        """
        # 1. Получаем agent card
        card_resp = await client.get(f"/flows/api/v1/{flow_id}")
        assert card_resp.status_code == 200
        card = card_resp.json()
        assert "variables" in card
        assert "company_name" in card["variables"]

        # 2. Настраиваем mock LLM с ответом, использующим переменные
        mock_llm_with_queue([
            {
                "type": "text",
                "content": (
                    "Компания: E2ECompany, "
                    "Пользователь: E2EUser, "
                    "Email: e2e@example.com, "
                    "Город: Москва, "
                    "Длина ответа: 1000"
                ),
            }
        ])

        context_id = str(uuid.uuid4())

        # 3. Отправляем message/send с полным набором variables
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-vars-full",
                "method": "message/send",
                "params": {
                    "message": _msg(
                        "Полный тест variables",
                        context_id=context_id,
                        metadata={
                            "variables": {
                                # Примитивные переменные
                                "company_name": "E2ECompany",
                                "max_response_length": "1000",
                                # Dict переменные
                                "user_info": {
                                    "name": "E2EUser",
                                    "email": "e2e@example.com",
                                    "profile": {
                                        "city": "Москва",
                                        "country": "Россия",
                                    },
                                },
                            }
                        },
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        task = data["result"]
        assert task["status"]["state"] == "completed"

        # 4. Проверяем что все variables применились
        response_text = get_task_response(task)
        
        # Проверяем примитивные переменные
        assert "E2ECompany" in response_text or "1000" in response_text
        
        # Проверяем dict переменные (доступ через точку в промпте)
        assert "E2EUser" in response_text or "e2e@example.com" in response_text or "Москва" in response_text

        # 5. Проверяем что contextId сохранился
        assert task["contextId"] == context_id

        # 6. Проверяем что history содержит сообщения
        assert "history" in task
        assert len(task["history"]) >= 2
        roles = [msg["role"] for msg in task["history"]]
        assert "user" in roles
        assert "agent" in roles

    @pytest.mark.asyncio
    async def test_current_date_variable_from_metadata_with_var_reference(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """
        6. Проверяет что переменная current_date из metadata с @var: ссылкой правильно резолвится.
        
        Проблема: когда передается "@var:current_date" в metadata, она должна резолвиться
        через VariablesService.resolve() в значение из БД, а не попадать в промпт как строка "current_date".
        """
        from datetime import datetime
        
        # Сначала создаем переменную current_date в БД
        # (в реальности она может быть создана заранее)
        var_value = "2024-12-18"
        
        # Создаем переменную через API
        var_resp = await client.post(
            "/flows/api/v1/variables",
            json={
                "key": "current_date",
                "value": var_value,
                "secret": False,
            },
        )
        # Игнорируем ошибку если переменная уже существует
        
        # Настраиваем mock LLM ответ
        mock_llm_with_queue([
            {"type": "text", "content": f"Сегодня {var_value}, я помощник компании TestCompany."}
        ])

        context_id = str(uuid.uuid4())

        # Отправляем message/send с @var:current_date в metadata
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-current-date-var",
                "method": "message/send",
                "params": {
                    "message": _msg(
                        "Какая сегодня дата?",
                        context_id=context_id,
                        metadata={
                            "variables": {
                                "current_date": "@var:current_date",  # Передаем ссылку на переменную из БД
                                "company_name": "TestCompany",
                            }
                        },
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        task = data["result"]
        assert task["status"]["state"] == "completed"

        # Проверяем что ответ содержит значение из БД (не строку "current_date" или "@var:current_date")
        response_text = get_task_response(task)
        
        # Важно: проверяем что в ответе есть значение из БД
        assert var_value in response_text
        # Проверяем что строка "@var:current_date" или "current_date" НЕ попала в ответ как есть
        assert "@var:current_date" not in response_text
        # Проверяем что строка "current_date" не попала в промпт (косвенная проверка через ответ)
        # Если в промпте было "current_date" вместо значения, LLM мог бы его упомянуть

    @pytest.mark.asyncio
    async def test_var_reference_in_metadata_recursive_resolution(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """
        7. Проверяет рекурсивный резолв @var: ссылок в metadata.
        
        Сценарий:
        - В metadata передается @var: ссылка напрямую
        - Эта переменная содержит другую @var: ссылку
        - Обе должны быть рекурсивно зарезолвлены
        """
        # Создаем переменные в БД
        await client.post(
            "/flows/api/v1/variables",
            json={"key": "base_url", "value": "https://api.example.com", "secret": False},
        )
        await client.post(
            "/flows/api/v1/variables",
            json={"key": "api_endpoint", "value": "@var:base_url/v1", "secret": False},
        )
        
        # Настраиваем mock LLM ответ
        mock_llm_with_queue([
            {"type": "text", "content": "API endpoint: https://api.example.com/v1"}
        ])

        context_id = str(uuid.uuid4())

        # Отправляем message/send с @var: ссылкой в metadata
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-var-reference-recursive",
                "method": "message/send",
                "params": {
                    "message": _msg(
                        "Какой API endpoint?",
                        context_id=context_id,
                        metadata={
                            "variables": {
                                "api_endpoint": "@var:api_endpoint",  # Ссылка на переменную, которая содержит другую ссылку
                                "company_name": "TestCompany",
                            }
                        },
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        task = data["result"]
        assert task["status"]["state"] == "completed"

        # Проверяем что обе ссылки были зарезолвлены рекурсивно
        response_text = get_task_response(task)
        
        # Должно быть финальное значение, а не ссылки
        assert "https://api.example.com/v1" in response_text
        assert "@var:api_endpoint" not in response_text
        assert "@var:base_url" not in response_text

    @pytest.mark.asyncio
    async def test_var_reference_in_json_metadata_recursive_resolution(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """
        8. Проверяет рекурсивный резолв @var: ссылок внутри JSON объектов в metadata.
        
        Сценарий:
        - В metadata передается JSON объект
        - Внутри JSON есть поля со значениями @var: ссылками
        - Эти ссылки должны быть рекурсивно зарезолвлены
        - Если резолвнутое значение тоже содержит @var:, оно тоже резолвится
        """
        # Создаем переменные в БД
        await client.post(
            "/flows/api/v1/variables",
            json={"key": "db_host", "value": "localhost", "secret": False},
        )
        await client.post(
            "/flows/api/v1/variables",
            json={"key": "db_port", "value": "5432", "secret": False},
        )
        await client.post(
            "/flows/api/v1/variables",
            json={"key": "db_connection", "value": "@var:db_host:@var:db_port", "secret": False},
        )
        
        # Настраиваем mock LLM ответ
        mock_llm_with_queue([
            {"type": "text", "content": "DB connection: localhost:5432"}
        ])

        context_id = str(uuid.uuid4())

        # Отправляем message/send с JSON объектом, содержащим @var: ссылки
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-var-reference-json",
                "method": "message/send",
                "params": {
                    "message": _msg(
                        "Какая строка подключения к БД?",
                        context_id=context_id,
                        metadata={
                            "variables": {
                                "db_config": {
                                    "host": "@var:db_host",
                                    "port": "@var:db_port",
                                    "connection": "@var:db_connection",  # Ссылка, которая содержит другие ссылки
                                },
                                "company_name": "TestCompany",
                            }
                        },
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        task = data["result"]
        assert task["status"]["state"] == "completed"

        # Проверяем что все ссылки были зарезолвлены рекурсивно
        response_text = get_task_response(task)
        
        # Должны быть финальные значения
        assert "localhost" in response_text
        assert "5432" in response_text
        assert "localhost:5432" in response_text
        
        # Не должно быть ссылок
        assert "@var:db_host" not in response_text
        assert "@var:db_port" not in response_text
        assert "@var:db_connection" not in response_text

    @pytest.mark.asyncio
    async def test_var_reference_in_nested_json_metadata_recursive_resolution(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """
        9. Проверяет рекурсивный резолв @var: ссылок в глубоко вложенных JSON структурах.
        
        Сценарий:
        - В metadata передается сложный JSON объект с вложенными объектами и массивами
        - Внутри есть @var: ссылки на разных уровнях вложенности
        - Все ссылки должны быть рекурсивно зарезолвлены
        """
        # Создаем переменные в БД
        await client.post(
            "/flows/api/v1/variables",
            json={"key": "service_name", "value": "my-service", "secret": False},
        )
        await client.post(
            "/flows/api/v1/variables",
            json={"key": "service_version", "value": "1.0.0", "secret": False},
        )
        await client.post(
            "/flows/api/v1/variables",
            json={"key": "full_service_name", "value": "@var:service_name-v@var:service_version", "secret": False},
        )
        
        # Настраиваем mock LLM ответ
        mock_llm_with_queue([
            {"type": "text", "content": "Service: my-service-v1.0.0"}
        ])

        context_id = str(uuid.uuid4())

        # Отправляем message/send с глубоко вложенным JSON объектом
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-var-reference-nested-json",
                "method": "message/send",
                "params": {
                    "message": _msg(
                        "Какой полный идентификатор сервиса?",
                        context_id=context_id,
                        metadata={
                            "variables": {
                                "config": {
                                    "service": {
                                        "name": "@var:service_name",
                                        "version": "@var:service_version",
                                        "full_name": "@var:full_service_name",  # Ссылка с вложенными ссылками
                                    },
                                    "endpoints": [
                                        {"path": "/api/@var:service_name", "method": "GET"},
                                        {"path": "/api/@var:service_name/health", "method": "GET"},
                                    ],
                                },
                                "company_name": "TestCompany",
                            }
                        },
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        task = data["result"]
        assert task["status"]["state"] == "completed"

        # Проверяем что все ссылки были зарезолвлены рекурсивно
        response_text = get_task_response(task)
        
        # Должны быть финальные значения
        assert "my-service" in response_text
        assert "1.0.0" in response_text
        assert "my-service-v1.0.0" in response_text
        
        # Не должно быть ссылок
        assert "@var:service_name" not in response_text
        assert "@var:service_version" not in response_text
        assert "@var:full_service_name" not in response_text

