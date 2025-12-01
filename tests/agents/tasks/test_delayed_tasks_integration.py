"""
Интеграционные тесты отложенных задач с реальными агентами.

Полный flow:
1. Агент получает сообщение от пользователя
2. MockLLM заставляет агента вызвать create_delayed_task
3. Задача планируется через TaskIQ schedule_by_time
4. Проверяем что задача была создана
"""

import pytest
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from apps.agents.models import AgentConfig, AgentType, FlowConfig, ToolReference, CodeMode
from apps.agents.container import get_agents_container
from core.context import set_context, clear_context

logger = logging.getLogger(__name__)


class TestAgentCreatesDelayedTask:
    """Тесты где агент создает отложенную задачу через tool."""
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_agent_schedules_delayed_task_with_message(
        self,
        taskiq_environment,
        test_context,
        test_company,
        agent_repo,
        flow_repo,
        mock_llm,
        unique_id
    ):
        """
        Агент получает запрос и создает отложенную задачу с сообщением.
        Проверяем через ToolMessage в результате что тул был вызван.
        """
        agent_id = unique_id("agent")
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="Reminder Agent",
            agent_type=AgentType.REACT,
            prompt="Ты агент-напоминалка. Используй create_delayed_task.",
            tools=[
                ToolReference(
                    tool_id="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                    code_mode=CodeMode.CODE_REFERENCE,
                    function_path="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                )
            ],
        )
        await agent_repo.set(agent_config)
        
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Reminder Flow",
            description="Flow для напоминаний",
            platforms={"api": {}},
            entry_point_agent=agent_id
        )
        await flow_repo.set(flow_config)
        
        test_context.flow_config = flow_config
        test_context.session_id = unique_id("session")
        test_context.platform = "api"
        set_context(test_context)
        
        try:
            mock_llm.configure(response_queue=[
                {
                    "type": "tool_call",
                    "tool": "create_delayed_task",
                    "args": {
                        "delay_seconds": 60,
                        "message": "Напоминание: позвонить маме"
                    }
                },
                {"type": "text", "content": "Готово! Создал напоминание."}
            ])
            
            agent_factory = get_agents_container().agent_factory
            agent = await agent_factory.get_agent(agent_id)
            
            result = await agent.ainvoke({
                "messages": [HumanMessage(content="Напомни позвонить маме через минуту")],
                "session_id": test_context.session_id,
            })
            
            assert result is not None
            messages = result.get("messages", [])
            
            # Проверяем что в ответе есть ToolMessage от create_delayed_task
            tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
            assert len(tool_messages) > 0, "Должен быть хотя бы один ToolMessage"
            
            # Проверяем содержимое ToolMessage - тул должен вернуть сообщение об успехе
            tool_result = tool_messages[0].content
            assert "Создана отложенная задача" in tool_result
            assert "Напоминание: позвонить маме" in tool_result
            assert "task_" in tool_result  # task_id
            
            logger.info(f"Agent created delayed task: {tool_result[:100]}")
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_agent_schedules_tool_call(
        self,
        taskiq_environment,
        test_context,
        test_company,
        agent_repo,
        flow_repo,
        mock_llm,
        unique_id
    ):
        """
        Агент планирует отложенный вызов тула (не просто сообщение).
        """
        agent_id = unique_id("agent")
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="Order Agent",
            agent_type=AgentType.REACT,
            prompt="Ты агент обработки заказов. Создавай отложенные задачи.",
            tools=[
                ToolReference(
                    tool_id="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                    code_mode=CodeMode.CODE_REFERENCE,
                    function_path="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                )
            ],
        )
        await agent_repo.set(agent_config)
        
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Order Flow",
            description="Flow для заказов",
            platforms={"api": {}},
            entry_point_agent=agent_id
        )
        await flow_repo.set(flow_config)
        
        test_context.flow_config = flow_config
        test_context.session_id = unique_id("session")
        test_context.platform = "api"
        set_context(test_context)
        
        try:
            # Создаем отложенный вызов тула (tool_name + tool_args)
            mock_llm.configure(response_queue=[
                {
                    "type": "tool_call",
                    "tool": "create_delayed_task",
                    "args": {
                        "delay_seconds": 60,
                        "tool_name": "check_order_status",
                        "tool_args": {"order_id": "ORD-12345"}
                    }
                },
                {"type": "text", "content": "Создал задачу на проверку заказа."}
            ])
            
            agent_factory = get_agents_container().agent_factory
            agent = await agent_factory.get_agent(agent_id)
            
            result = await agent.ainvoke({
                "messages": [HumanMessage(content="Проверь статус заказа ORD-12345 через минуту")],
                "session_id": test_context.session_id,
            })
            
            messages = result.get("messages", [])
            tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
            assert len(tool_messages) > 0
            
            tool_result = tool_messages[0].content
            # Для tool_call в результате должен быть tool_name
            assert "Создана отложенная задача" in tool_result
            assert "check_order_status" in tool_result
            assert "ORD-12345" in tool_result
            
            logger.info(f"Agent scheduled tool call: {tool_result[:100]}")
            
        finally:
            clear_context()


class TestDelayedTaskExecution:
    """Тесты реального выполнения отложенных задач."""
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_delayed_task_executes_via_scheduler(
        self,
        taskiq_environment,
        test_context,
        test_company,
        agent_repo,
        flow_repo,
        mock_llm,
        unique_id
    ):
        """
        Полный цикл:
        1. Планируем задачу через schedule_by_time  
        2. Ждем когда время наступит
        3. Выполняем process_agent_task
        4. Агент обрабатывает сообщение
        """
        from apps.agents.tasks.agent_tasks import process_agent_task
        
        agent_id = unique_id("agent")
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="Echo Agent",
            agent_type=AgentType.REACT,
            prompt="Просто подтверди получение сообщения.",
        )
        await agent_repo.set(agent_config)
        
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Echo Flow",
            description="Flow для тестов",
            platforms={"api": {}},
            entry_point_agent=agent_id
        )
        await flow_repo.set(flow_config)
        
        execute_at = datetime.now(timezone.utc) + timedelta(seconds=2)
        session_id = unique_id("session")
        
        schedule_source = taskiq_environment["schedule_source"]
        
        schedule = await process_agent_task.schedule_by_time(
            schedule_source,
            execute_at,
            flow_id=flow_id,
            session_id=session_id,
            message="[DELAYED_TASK:test] Напоминание!",
            platform="api",
            user_id="test_user",
            company_id=test_company.company_id,
            metadata={"test_execution": True},
        )
        
        logger.info(f"Scheduled task for {execute_at}, schedule_id: {schedule.schedule_id}")
        
        mock_llm.configure(response_queue=[
            {"type": "text", "content": "Напоминание получено!"}
        ])
        
        await asyncio.sleep(3)
        
        result = await process_agent_task(
            flow_id=flow_id,
            session_id=session_id,
            message="[DELAYED_TASK:test] Напоминание!",
            platform="api",
            user_id="test_user",
            company_id=test_company.company_id,
            metadata={"test_execution": True},
        )
        
        logger.info(f"Task execution result: {result}")
        
        assert result is not None
        assert result.get("status") in ["completed", "success", "waiting_for_input"]
        
        try:
            await schedule.unschedule()
        except Exception:
            pass


class TestDelayedToolCallExecution:
    """Тесты выполнения отложенного вызова функции."""
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_delayed_tool_call_result_in_messages(
        self,
        taskiq_environment,
        test_context,
        test_company,
        agent_repo,
        flow_repo,
        tool_repo,
        mock_llm,
        unique_id
    ):
        """
        ВАЖНЫЙ ТЕСТ: Проверяем что результат отложенного вызова функции
        реально попадает в messages агента.
        
        Flow:
        1. Создаем агента с inline tool (check_order_status)
        2. Агент получает сообщение "Выполни инструмент check_order_status(order_id=ORD-99999)"
        3. MockLLM заставляет агента вызвать check_order_status
        4. Проверяем что в messages агента есть ToolMessage с результатом функции
        """
        # Создаем inline tool который вернет конкретный результат
        tool_ref = ToolReference(
            tool_id=unique_id("check_order_tool"),
            code_mode=CodeMode.INLINE_CODE,
            inline_code='''
async def check_order_status(order_id: str) -> str:
    """Проверяет статус заказа"""
    return f"[TOOL_RESULT] Заказ {order_id} успешно доставлен клиенту!"
''',
            description="Проверка статуса заказа"
        )
        await tool_repo.set(tool_ref)
        
        agent_id = unique_id("agent")
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="Order Check Agent",
            agent_type=AgentType.REACT,
            prompt="Вызывай check_order_status когда нужно проверить статус.",
            tools=[tool_ref],
        )
        await agent_repo.set(agent_config)
        
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Order Check Flow",
            description="Flow для проверки заказов",
            platforms={"api": {}},
            entry_point_agent=agent_id
        )
        await flow_repo.set(flow_config)
        
        test_context.flow_config = flow_config
        test_context.session_id = unique_id("session")
        test_context.platform = "api"
        set_context(test_context)
        
        try:
            # MockLLM: агент вызовет check_order_status и даст финальный ответ
            mock_llm.configure(response_queue=[
                {
                    "type": "tool_call",
                    "tool": "check_order_status",
                    "args": {"order_id": "ORD-99999"}
                },
                {"type": "text", "content": "Заказ ORD-99999 доставлен."}
            ])
            
            agent_factory = get_agents_container().agent_factory
            agent = await agent_factory.get_agent(agent_id)
            
            # Симулируем отложенное сообщение
            task_message = "[DELAYED_TASK:test] Выполни инструмент check_order_status(order_id=ORD-99999)"
            
            result = await agent.ainvoke({
                "messages": [HumanMessage(content=task_message)],
                "session_id": test_context.session_id,
            })
            
            assert result is not None
            messages = result.get("messages", [])
            
            # Проверяем что есть ToolMessage с результатом check_order_status
            tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
            assert len(tool_messages) > 0, "Должен быть хотя бы один ToolMessage"
            
            # Проверяем что результат функции в ToolMessage
            tool_results = [m.content for m in tool_messages]
            assert any("[TOOL_RESULT]" in str(content) and "ORD-99999" in str(content) for content in tool_results), \
                f"ToolMessage должен содержать результат check_order_status, получили: {tool_results}"
            
            # Проверяем финальный ответ агента
            ai_messages = [m for m in messages if isinstance(m, AIMessage)]
            assert len(ai_messages) > 0
            final_response = ai_messages[-1].content
            assert "ORD-99999" in final_response or "доставлен" in final_response.lower()
            
            logger.info(f"Tool result in messages: {tool_results}")
            logger.info(f"Final agent response: {final_response}")
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_delayed_task_via_process_agent_task(
        self,
        taskiq_environment,
        test_context,
        test_company,
        agent_repo,
        flow_repo,
        tool_repo,
        mock_llm,
        unique_id
    ):
        """
        Тест выполнения через process_agent_task (как это делает scheduler).
        """
        from apps.agents.tasks.agent_tasks import process_agent_task
        
        tool_ref = ToolReference(
            tool_id=unique_id("check_tool"),
            code_mode=CodeMode.INLINE_CODE,
            inline_code='''
async def check_order_status(order_id: str) -> str:
    """Проверяет статус заказа"""
    return f"Статус заказа {order_id}: Доставлен"
''',
            description="Проверка статуса"
        )
        await tool_repo.set(tool_ref)
        
        agent_id = unique_id("agent")
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="Order Agent",
            agent_type=AgentType.REACT,
            prompt="Вызывай check_order_status когда нужно.",
            tools=[tool_ref],
        )
        await agent_repo.set(agent_config)
        
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Order Flow",
            description="Flow",
            platforms={"api": {}},
            entry_point_agent=agent_id
        )
        await flow_repo.set(flow_config)
        
        mock_llm.configure(response_queue=[
            {
                "type": "tool_call",
                "tool": "check_order_status",
                "args": {"order_id": "ORD-12345"}
            },
            {"type": "text", "content": "Заказ ORD-12345 доставлен!"}
        ])
        
        # Выполняем через process_agent_task как это делает scheduler
        result = await process_agent_task(
            flow_id=flow_id,
            session_id=unique_id("session"),
            message="[DELAYED_TASK:test] Проверь статус заказа ORD-12345",
            platform="api",
            user_id="test_user",
            company_id=test_company.company_id,
            metadata={},
        )
        
        assert result is not None
        assert result.get("status") == "completed"
        
        # Проверяем response
        response = result.get("response", "")
        assert "ORD-12345" in response or "доставлен" in response.lower(), \
            f"Response должен содержать результат, получили: {response}"
        
        logger.info(f"process_agent_task completed with response: {response}")


class TestMultipleDelayedTasks:
    """Тесты с несколькими отложенными задачами - message и tool_call."""
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_agent_creates_message_task(
        self,
        taskiq_environment,
        test_context,
        test_company,
        agent_repo,
        flow_repo,
        mock_llm,
        unique_id
    ):
        """Агент создает отложенную задачу с текстовым сообщением."""
        agent_id = unique_id("agent")
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="Message Task Agent",
            agent_type=AgentType.REACT,
            prompt="Создавай отложенные задачи.",
            tools=[
                ToolReference(
                    tool_id="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                    code_mode=CodeMode.CODE_REFERENCE,
                    function_path="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                ),
            ],
        )
        await agent_repo.set(agent_config)
        
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Message Task Flow",
            description="Flow для тестов",
            platforms={"api": {}},
            entry_point_agent=agent_id
        )
        await flow_repo.set(flow_config)
        
        test_context.flow_config = flow_config
        test_context.session_id = unique_id("session")
        test_context.platform = "api"
        set_context(test_context)
        
        try:
            agent_factory = get_agents_container().agent_factory
            agent = await agent_factory.get_agent(agent_id)
            
            # Задача с текстовым сообщением
            mock_llm.configure(response_queue=[
                {
                    "type": "tool_call",
                    "tool": "create_delayed_task",
                    "args": {"delay_seconds": 60, "message": "Напоминание: проверить почту"}
                },
                {"type": "text", "content": "Создал напоминание"}
            ])
            
            result = await agent.ainvoke({
                "messages": [HumanMessage(content="Напомни проверить почту через минуту")],
                "session_id": test_context.session_id,
            })
            
            tool_messages = [m for m in result.get("messages", []) if isinstance(m, ToolMessage)]
            assert len(tool_messages) > 0
            
            tool_result = tool_messages[0].content
            assert "Создана отложенная задача" in tool_result
            assert "Напоминание: проверить почту" in tool_result
            
            logger.info(f"Created message task: {tool_result[:80]}")
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_agent_creates_tool_call_task(
        self,
        taskiq_environment,
        test_context,
        test_company,
        agent_repo,
        flow_repo,
        mock_llm,
        unique_id
    ):
        """Агент создает отложенную задачу с вызовом тула."""
        agent_id = unique_id("agent")
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="Tool Task Agent",
            agent_type=AgentType.REACT,
            prompt="Создавай отложенные задачи с вызовом тулов.",
            tools=[
                ToolReference(
                    tool_id="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                    code_mode=CodeMode.CODE_REFERENCE,
                    function_path="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                ),
            ],
        )
        await agent_repo.set(agent_config)
        
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Tool Task Flow",
            description="Flow для тестов",
            platforms={"api": {}},
            entry_point_agent=agent_id
        )
        await flow_repo.set(flow_config)
        
        test_context.flow_config = flow_config
        test_context.session_id = unique_id("session")
        test_context.platform = "api"
        set_context(test_context)
        
        try:
            agent_factory = get_agents_container().agent_factory
            agent = await agent_factory.get_agent(agent_id)
            
            # Задача с вызовом тула
            mock_llm.configure(response_queue=[
                {
                    "type": "tool_call",
                    "tool": "create_delayed_task",
                    "args": {
                        "delay_seconds": 120, 
                        "tool_name": "send_email",
                        "tool_args": {"to": "user@test.com", "subject": "Follow-up"}
                    }
                },
                {"type": "text", "content": "Создал задачу на отправку email"}
            ])
            
            result = await agent.ainvoke({
                "messages": [HumanMessage(content="Отправь email через 2 минуты")],
                "session_id": test_context.session_id,
            })
            
            tool_messages = [m for m in result.get("messages", []) if isinstance(m, ToolMessage)]
            assert len(tool_messages) > 0
            
            tool_result = tool_messages[0].content
            assert "Создана отложенная задача" in tool_result
            assert "send_email" in tool_result
            assert "user@test.com" in tool_result or "Follow-up" in tool_result
            
            logger.info(f"Created tool_call task: {tool_result[:80]}")
            
        finally:
            clear_context()


class TestCancelDelayedTask:
    """Тесты отмены отложенных задач."""
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_cancel_delayed_task_from_state(
        self,
        taskiq_environment,
        test_context,
        test_company,
        agent_repo,
        flow_repo,
        mock_llm,
        unique_id
    ):
        """
        Тест отмены задачи.
        Сначала создаем задачу, потом отменяем её.
        """
        agent_id = unique_id("agent")
        agent_config = AgentConfig(
            agent_id=agent_id,
            name="Cancel Task Agent",
            agent_type=AgentType.REACT,
            prompt="Создавай и отменяй задачи.",
            tools=[
                ToolReference(
                    tool_id="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                    code_mode=CodeMode.CODE_REFERENCE,
                    function_path="apps.agents.tools.task.delayed_task_tools.create_delayed_task",
                ),
                ToolReference(
                    tool_id="apps.agents.tools.task.delayed_task_tools.cancel_delayed_task",
                    code_mode=CodeMode.CODE_REFERENCE,
                    function_path="apps.agents.tools.task.delayed_task_tools.cancel_delayed_task",
                ),
            ],
        )
        await agent_repo.set(agent_config)
        
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Cancel Task Flow",
            description="Flow для отмены задач",
            platforms={"api": {}},
            entry_point_agent=agent_id
        )
        await flow_repo.set(flow_config)
        
        test_context.flow_config = flow_config
        test_context.session_id = unique_id("session")
        test_context.platform = "api"
        set_context(test_context)
        
        try:
            agent_factory = get_agents_container().agent_factory
            agent = await agent_factory.get_agent(agent_id)
            
            # Создаем задачу
            mock_llm.configure(response_queue=[
                {
                    "type": "tool_call",
                    "tool": "create_delayed_task",
                    "args": {"delay_seconds": 3600, "message": "Задача для отмены"}
                },
                {"type": "text", "content": "Создал задачу"}
            ])
            
            result = await agent.ainvoke({
                "messages": [HumanMessage(content="Создай задачу на час")],
                "session_id": test_context.session_id,
            })
            
            # Извлекаем task_id из результата
            tool_messages = [m for m in result.get("messages", []) if isinstance(m, ToolMessage)]
            assert len(tool_messages) > 0
            
            tool_result = tool_messages[0].content
            # Парсим task_id из "Создана отложенная задача task_abc123"
            import re
            match = re.search(r'task_[a-f0-9]+', tool_result)
            assert match, f"task_id не найден в: {tool_result}"
            task_id = match.group()
            
            logger.info(f"Created task {task_id}, now cancelling...")
            
            # Отменяем задачу
            mock_llm.configure(response_queue=[
                {
                    "type": "tool_call",
                    "tool": "cancel_delayed_task",
                    "args": {"task_id": task_id}
                },
                {"type": "text", "content": "Задача отменена"}
            ])
            
            result2 = await agent.ainvoke({
                "messages": [HumanMessage(content=f"Отмени задачу {task_id}")],
                "session_id": test_context.session_id,
            })
            
            tool_messages2 = [m for m in result2.get("messages", []) if isinstance(m, ToolMessage)]
            assert len(tool_messages2) > 0
            
            cancel_result = tool_messages2[0].content
            assert "отменена" in cancel_result.lower() or task_id in cancel_result
            
            logger.info(f"Successfully cancelled task {task_id}")
            
        finally:
            clear_context()
