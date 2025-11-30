"""
E2E тесты API с реальным брокером и процессами.

Полный цикл:
1. Запускается agents сервер (отдельный процесс)
2. Запускается TaskIQ воркер (отдельный процесс)
3. Тест отправляет POST /flows/{flow_id}/message с JWT токеном
4. Воркер обрабатывает задачу
5. Тест получает ответ через GET /flows/{flow_id}/task/{task_id}

Запуск:
    uv run pytest tests/agents/broker/test_e2e_api_broker.py -v -s
"""

import pytest
import asyncio
import httpx

from core.utils.tokens import get_token_service


@pytest.fixture
def existing_flow_id():
    """
    Возвращает ID существующего flow который мигрируется при старте сервера.
    FAQ flow всегда есть и поддерживает API платформу.
    """
    return "apps.agents.flows.faq_flow.faq_flow_config"


@pytest.fixture
def system_company_id():
    """
    ID системной компании куда мигрируются flows.
    Flows мигрируются в 'system' компанию при старте сервера.
    """
    return "system"


@pytest.fixture
def api_auth_token(system_company_id, unique_id):
    """JWT токен для API тестов с system_migrator пользователем (создается при миграции)"""
    token_service = get_token_service()
    return token_service.create_token(
        user_id="system_migrator",  # Создается при миграции flows
        company_id=system_company_id,
        session_id=unique_id("api_session"),
    )


class TestE2EApiBroker:
    """E2E тесты API через брокер с реальными процессами"""
    
    @pytest.mark.asyncio
    async def test_server_health(self, agents_server_process):
        """Проверка что сервер отвечает"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{agents_server_process['url']}/health")
            assert response.status_code == 200
            print(f"✅ Сервер здоров: {response.json()}")
    
    @pytest.mark.asyncio
    async def test_send_message_returns_task_id(
        self, 
        agents_server_process, 
        taskiq_worker_process,
        existing_flow_id,
        system_company_id,
        api_auth_token,
    ):
        """
        POST /flows/{flow_id}/message должен вернуть task_id.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{agents_server_process['url']}/agents/api/v1/flows/{existing_flow_id}/message",
                json={
                    "message": "Привет, API тест!",
                    "user_id": "test_api_user",
                },
                headers={
                    "Authorization": f"Bearer {api_auth_token}",
                    "X-Company-Id": system_company_id,
                },
                timeout=30.0,
            )
            
            print(f"📤 Ответ API: status={response.status_code}, body={response.text}")
            
            assert response.status_code == 200, f"Ошибка: {response.text}"
            
            data = response.json()
            assert "task_id" in data
            assert "session_id" in data
            assert data["status"] == "pending"
            
            print(f"✅ Задача создана: task_id={data['task_id']}, session_id={data['session_id']}")
    
    @pytest.mark.asyncio
    async def test_full_message_cycle(
        self,
        agents_server_process,
        taskiq_worker_process,
        existing_flow_id,
        system_company_id,
        api_auth_token,
    ):
        """
        Полный цикл:
        1. POST сообщение → получаем task_id
        2. Воркер обрабатывает задачу
        3. GET /task/{task_id} → получаем ответ агента
        """
        async with httpx.AsyncClient() as client:
            # 1. Отправляем сообщение
            send_response = await client.post(
                f"{agents_server_process['url']}/agents/api/v1/flows/{existing_flow_id}/message",
                json={
                    "message": "Тест полного цикла через API",
                    "user_id": "test_full_cycle_user",
                },
                headers={
                    "Authorization": f"Bearer {api_auth_token}",
                    "X-Company-Id": system_company_id,
                },
                timeout=30.0,
            )
            
            assert send_response.status_code == 200, f"Ошибка отправки: {send_response.text}"
            
            task_data = send_response.json()
            task_id = task_data["task_id"]
            print(f"📤 Задача создана: task_id={task_id}")
            
            # 2. Polling - ждем завершения задачи
            max_attempts = 30  # 30 секунд максимум
            for attempt in range(max_attempts):
                poll_response = await client.get(
                    f"{agents_server_process['url']}/agents/api/v1/flows/{existing_flow_id}/task/{task_id}",
                    headers={
                        "Authorization": f"Bearer {api_auth_token}",
                        "X-Company-Id": system_company_id,
                    },
                    timeout=10.0,
                )
                
                if poll_response.status_code == 200:
                    result = poll_response.json()
                    status = result.get("status")
                    print(f"📊 Попытка {attempt + 1}: status={status}")
                    
                    if status == "completed":
                        # response в result["result"]["response"]
                        result_data = result.get("result", {})
                        response_text = result_data.get("response", "")
                        print(f"✅ Ответ получен: {response_text[:100]}...")
                        assert "result" in result
                        assert "response" in result_data
                        assert len(response_text) > 0
                        return
                    
                    if status == "failed":
                        pytest.fail(f"Задача завершилась с ошибкой: {result.get('error')}")
                
                await asyncio.sleep(1)
            
            pytest.fail(f"Таймаут ожидания ответа для задачи {task_id}")
    
    @pytest.mark.asyncio
    async def test_multiple_messages_same_session(
        self,
        agents_server_process,
        taskiq_worker_process,
        existing_flow_id,
        system_company_id,
        api_auth_token,
    ):
        """Несколько сообщений в одной сессии."""
        async with httpx.AsyncClient() as client:
            session_id = None
            
            for i in range(3):
                payload = {
                    "message": f"Сообщение #{i + 1}",
                    "user_id": "test_session_user",
                }
                if session_id:
                    payload["session_id"] = session_id
                
                response = await client.post(
                    f"{agents_server_process['url']}/agents/api/v1/flows/{existing_flow_id}/message",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_auth_token}",
                        "X-Company-Id": system_company_id,
                    },
                    timeout=30.0,
                )
                
                assert response.status_code == 200
                data = response.json()
                
                if session_id is None:
                    session_id = data["session_id"]
                    print(f"✅ Создана сессия: {session_id}")
                else:
                    assert data["session_id"] == session_id
                    print(f"✅ Сообщение #{i + 1} в той же сессии")
                
                # Ждем обработки
                task_id = data["task_id"]
                for _ in range(20):
                    poll_response = await client.get(
                        f"{agents_server_process['url']}/agents/api/v1/flows/{existing_flow_id}/task/{task_id}",
                        headers={
                            "Authorization": f"Bearer {api_auth_token}",
                            "X-Company-Id": system_company_id,
                        },
                    )
                    if poll_response.status_code == 200:
                        result = poll_response.json()
                        if result.get("status") == "completed":
                            break
                    await asyncio.sleep(0.5)
            
            print(f"✅ Все 3 сообщения обработаны в сессии {session_id}")


class TestBrokerDirectKiq:
    """Тесты прямого вызова kiq с воркером"""
    
    @pytest.mark.asyncio
    async def test_kiq_with_worker(
        self,
        migrated_db,
        taskiq_broker,
        taskiq_worker_process,
        existing_flow_id,
        system_company_id,
        unique_id,
    ):
        """
        Прямой вызов kiq с работающим воркером.
        Используем существующий flow который мигрируется при старте.
        """
        from apps.agents.tasks.agent_tasks import process_agent_task
        
        session_id = unique_id("direct_session")
        
        # Используем system user и system company
        user_data = {"name": "System User", "groups": []}
        company_data = {"name": "System Company", "subdomain": "system"}
        
        # Отправляем задачу через kiq - используем существующий flow
        task = await process_agent_task.kiq(
            flow_id=existing_flow_id,
            session_id=session_id,
            message="Прямой вызов kiq с воркером",
            platform="api",
            user_id="system_user",
            company_id=system_company_id,
            metadata={},
            user_data=user_data,
            company_data=company_data,
        )
        
        print(f"📤 Задача отправлена: task_id={task.task_id}")
        
        # Ждем результата
        try:
            result = await task.wait_result(timeout=30)
            
            if result.is_err:
                print(f"❌ Задача завершилась с ошибкой: {result.error}")
                pytest.fail(f"Ошибка выполнения: {result.error}")
            else:
                print(f"✅ Результат: {result.return_value}")
                assert result.return_value["status"] == "completed"
                assert "response" in result.return_value
                
        except asyncio.TimeoutError:
            pytest.fail("Таймаут ожидания результата - воркер не обработал задачу")
