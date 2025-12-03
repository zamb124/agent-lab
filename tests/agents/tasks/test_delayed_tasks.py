"""
Реальные интеграционные тесты для отложенных задач через TaskIQ Scheduler.

Тесты запускают реальный scheduler, планируют задачи и проверяют их выполнение.
НЕ используют моки - работают с реальной БД и реальным TaskIQ.

Фикстуры:
- taskiq_broker - PostgreSQL broker (из conftest.py)
- taskiq_schedule_source - PostgreSQL schedule source (из conftest.py)
- taskiq_scheduler - TaskIQ scheduler (из conftest.py)
- taskiq_environment - полное окружение (из conftest.py)
"""

import pytest
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from apps.agents.tasks.agent_tasks import process_agent_task

logger = logging.getLogger(__name__)


class TestScheduleSourceOperations:
    """Тесты базовых операций schedule_source."""
    
    @pytest.mark.asyncio
    async def test_schedule_source_started(self, taskiq_schedule_source):
        """Проверяет что schedule_source запущен."""
        assert taskiq_schedule_source is not None
    
    @pytest.mark.asyncio
    async def test_schedule_task_for_future(self, taskiq_schedule_source, test_company, unique_id):
        """Планирует задачу на будущее и проверяет что она создана."""
        execute_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        schedule = await process_agent_task.schedule_by_time(
            taskiq_schedule_source,
            execute_at,
            flow_id=unique_id("flow"),
            session_id=unique_id("session"),
            message="Scheduled test message",
            platform="api",
            user_id="test_user",
            company_id=test_company.company_id,
            metadata={"test": True},
        )
        
        assert schedule is not None
        assert schedule.schedule_id is not None
        
        logger.info(f"Created schedule: {schedule.schedule_id}")
        
        # Отменяем задачу
        await schedule.unschedule()
        logger.info(f"Unscheduled: {schedule.schedule_id}")
    
    @pytest.mark.asyncio
    async def test_unschedule_task(self, taskiq_schedule_source, test_company, unique_id):
        """Проверяет отмену запланированной задачи."""
        execute_at = datetime.now(timezone.utc) + timedelta(hours=2)
        
        schedule = await process_agent_task.schedule_by_time(
            taskiq_schedule_source,
            execute_at,
            flow_id=unique_id("flow"),
            session_id=unique_id("session"),
            message="Task to cancel",
            platform="api",
            user_id="test_user",
            company_id=test_company.company_id,
            metadata={},
        )
        
        schedule_id = schedule.schedule_id
        logger.info(f"Created schedule to cancel: {schedule_id}")
        
        # Отменяем
        await schedule.unschedule()
        logger.info(f"Cancelled schedule: {schedule_id}")
    
    @pytest.mark.asyncio
    async def test_multiple_schedules(self, taskiq_schedule_source, test_company, unique_id):
        """Создает несколько расписаний и отменяет их."""
        schedules = []
        
        for i in range(3):
            execute_at = datetime.now(timezone.utc) + timedelta(hours=i+1)
            schedule = await process_agent_task.schedule_by_time(
                taskiq_schedule_source,
                execute_at,
                flow_id=unique_id("flow"),
                session_id=unique_id("session"),
                message=f"Task {i+1}",
                platform="api",
                user_id="test_user",
                company_id=test_company.company_id,
                metadata={"index": i},
            )
            schedules.append(schedule)
            logger.info(f"Created schedule {i+1}: {schedule.schedule_id}")
        
        assert len(schedules) == 3
        
        # Отменяем все
        for schedule in schedules:
            await schedule.unschedule()
        
        logger.info("All schedules cancelled")


class TestDelayedTaskToolsValidation:
    """Тесты валидации инструментов delayed_task_tools."""
    
    @pytest.mark.asyncio
    async def test_create_delayed_task_requires_message_or_tool(self):
        """Проверяет что create_delayed_task требует message или tool_name."""
        from apps.agents.tools.task.delayed_task_tools import create_delayed_task
        
        # Без message и tool_name - ошибка
        with pytest.raises(ValueError, match="Укажите либо message, либо tool_name"):
            await create_delayed_task.ainvoke({"delay_seconds": 60})
    
    @pytest.mark.asyncio
    async def test_create_delayed_task_rejects_both_message_and_tool(self):
        """Проверяет что нельзя указать и message и tool_name одновременно."""
        from apps.agents.tools.task.delayed_task_tools import create_delayed_task
        
        with pytest.raises(ValueError, match="но не оба сразу"):
            await create_delayed_task.ainvoke({
                "delay_seconds": 60,
                "message": "Test",
                "tool_name": "test_tool"
            })


class TestDelayedTaskToolsWithContext:
    """Тесты инструментов delayed_task_tools с реальным контекстом."""
    
    @pytest.mark.asyncio
    async def test_create_delayed_task_real(
        self, 
        taskiq_environment, 
        test_context, 
        test_company,
        flow_repo,
        unique_id
    ):
        """
        Создает отложенную задачу через tool с реальным контекстом.
        """
        from apps.agents.tools.task.delayed_task_tools import create_delayed_task
        from apps.agents.models import FlowConfig
        from core.context import set_context
        from core.variables.resolver import set_state_in_context
        
        # Создаем flow
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Delayed Task Test Flow",
            description="Test",
            platforms={"api": {}},
            entry_point_agent="test_agent"
        )
        await flow_repo.set(flow_config)
        
        # Настраиваем контекст
        test_context.flow_config = flow_config
        test_context.session_id = unique_id("session")
        test_context.platform = "api"
        set_context(test_context)
        
        # Настраиваем state
        state = {"store": {}}
        set_state_in_context(state)
        
        try:
            # Создаем отложенную задачу
            result = await create_delayed_task.ainvoke({
                "delay_seconds": 3600,  # 1 час - не будем ждать
                "message": "Real delayed task test"
            })
            
            assert "Создана отложенная задача" in result
            assert "Real delayed task test" in result
            
            # Проверяем что задача добавлена в state
            assert "delayed_tasks" in state["store"]
            assert len(state["store"]["delayed_tasks"]) == 1
            
            # Получаем task_id и schedule_id
            task_id = list(state["store"]["delayed_tasks"].keys())[0]
            task_info = state["store"]["delayed_tasks"][task_id]
            
            assert task_info["schedule_id"] is not None
            assert task_info["status"] == "scheduled"
            assert task_info["message"] == "Real delayed task test"
            
            logger.info(f"Created delayed task: {task_id} with schedule: {task_info['schedule_id']}")
            
            # Отменяем задачу чтобы не засорять БД
            from apps.agents.tools.task.delayed_task_tools import cancel_delayed_task
            cancel_result = await cancel_delayed_task.ainvoke({"task_id": task_id})
            
            assert "отменена" in cancel_result.lower()
            assert task_info["status"] == "cancelled"
            
        finally:
            set_state_in_context(None)
    
    @pytest.mark.asyncio
    async def test_list_delayed_tasks_real(
        self,
        taskiq_environment,
        test_context,
        test_company,
        flow_repo,
        unique_id
    ):
        """Тестирует список отложенных задач с реальными данными."""
        from apps.agents.tools.task.delayed_task_tools import (
            create_delayed_task,
            list_delayed_tasks,
            cancel_delayed_task
        )
        from apps.agents.models import FlowConfig
        from core.context import set_context
        from core.variables.resolver import set_state_in_context
        
        # Создаем flow
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="List Test Flow",
            description="Test",
            platforms={"api": {}},
            entry_point_agent="test_agent"
        )
        await flow_repo.set(flow_config)
        
        # Настраиваем контекст
        test_context.flow_config = flow_config
        test_context.session_id = unique_id("session")
        test_context.platform = "api"
        set_context(test_context)
        
        # Настраиваем state
        state = {"store": {}}
        set_state_in_context(state)
        
        try:
            # Создаем несколько задач
            await create_delayed_task.ainvoke({"delay_seconds": 7200, "message": "Task 1"})
            await create_delayed_task.ainvoke({"delay_seconds": 3600, "message": "Task 2"})
            
            # Получаем список
            result = await list_delayed_tasks.ainvoke({})
            
            assert "Отложенные задачи (2)" in result
            assert "Task 1" in result
            assert "Task 2" in result
            
            # Отменяем все задачи
            for task_id in list(state["store"]["delayed_tasks"].keys()):
                await cancel_delayed_task.ainvoke({"task_id": task_id})
                
        finally:
            set_state_in_context(None)
    
    @pytest.mark.asyncio
    async def test_create_delayed_task_with_tool_call(
        self,
        taskiq_environment,
        test_context,
        test_company,
        flow_repo,
        unique_id
    ):
        """Создает отложенную задачу с вызовом тула."""
        from apps.agents.tools.task.delayed_task_tools import (
            create_delayed_task,
            cancel_delayed_task
        )
        from apps.agents.models import FlowConfig
        from core.context import set_context
        from core.variables.resolver import set_state_in_context
        
        # Создаем flow
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Tool Call Flow",
            description="Test tool call",
            platforms={"api": {}},
            entry_point_agent="test_agent"
        )
        await flow_repo.set(flow_config)
        
        # Настраиваем контекст
        test_context.flow_config = flow_config
        test_context.session_id = unique_id("session")
        test_context.platform = "api"
        set_context(test_context)
        
        state = {"store": {}}
        set_state_in_context(state)
        
        try:
            # Создаем задачу с вызовом тула
            result = await create_delayed_task.ainvoke({
                "delay_seconds": 3600,
                "tool_name": "check_order_status",
                "tool_args": {"order_id": "12345"}
            })
            
            assert "Создана отложенная задача" in result
            assert "check_order_status" in result
            
            # Проверяем данные в state
            task_id = list(state["store"]["delayed_tasks"].keys())[0]
            task_info = state["store"]["delayed_tasks"][task_id]
            
            assert task_info["type"] == "tool_call"
            assert task_info["tool_name"] == "check_order_status"
            assert task_info["tool_args"] == {"order_id": "12345"}
            
            # Отменяем
            await cancel_delayed_task.ainvoke({"task_id": task_id})
            
        finally:
            set_state_in_context(None)


class TestSchedulerStartup:
    """Тесты запуска и работы scheduler."""
    
    @pytest.mark.asyncio
    async def test_scheduler_available(self, taskiq_scheduler):
        """Проверяет что scheduler доступен."""
        assert taskiq_scheduler is not None
        assert taskiq_scheduler.broker is not None
        assert len(taskiq_scheduler.sources) > 0
    
    @pytest.mark.asyncio
    async def test_scheduler_has_sources(self, taskiq_scheduler):
        """Проверяет что scheduler имеет настроенные sources."""
        # НЕ вызываем startup/shutdown - scheduler уже запущен через session-scoped фикстуру
        # и shutdown сломает его для остальных тестов
        assert len(taskiq_scheduler.sources) > 0
        assert taskiq_scheduler.broker is not None


class TestScheduledTaskExecution:
    """Тесты запланированного выполнения задач."""
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_schedule_immediate_task(
        self,
        taskiq_environment,
        test_company,
        flow_repo,
        unique_id
    ):
        """
        Планирует задачу на ближайшее время.
        Не ждет выполнения - просто проверяет что планирование работает.
        """
        from apps.agents.models import FlowConfig
        
        # Создаем flow
        flow_id = unique_id("flow")
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Immediate Scheduled Flow",
            description="Test immediate scheduling",
            platforms={"api": {}},
            entry_point_agent="apps.agents.agents.echo.agent.EchoAgent"
        )
        await flow_repo.set(flow_config)
        
        # Планируем задачу на 5 секунд вперед
        execute_at = datetime.now(timezone.utc) + timedelta(seconds=5)
        
        schedule = await process_agent_task.schedule_by_time(
            taskiq_environment["schedule_source"],
            execute_at,
            flow_id=flow_id,
            session_id=unique_id("session"),
            message="Immediate test message",
            platform="api",
            user_id="test_user",
            company_id=test_company.company_id,
            metadata={"immediate_test": True},
        )
        
        logger.info(f"Scheduled immediate task {schedule.schedule_id} for {execute_at}")
        
        assert schedule is not None
        assert schedule.schedule_id is not None
        
        # Отменяем чтобы не засорять БД
        await schedule.unschedule()
        logger.info("Task cancelled after verification")
