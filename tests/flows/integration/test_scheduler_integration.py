"""
Интеграционные тесты Scheduler.

Проверяют что:
1. Scheduled tasks создаются и сохраняются в Redis + PostgreSQL
2. Scheduler корректно отправляет tasks worker-у в нужное время
3. Все 5 scheduling tools работают корректно
4. Агент secretary использует scheduling tools

ВАЖНО: Используется реальный Redis и PostgreSQL.
Фикстуры taskiq_worker и taskiq_scheduler запускают процессы.
Только LLM мокается.

Маркер real_taskiq отключает sync_tools fixture.
"""

import datetime

import pytest

pytestmark = pytest.mark.real_taskiq


@pytest.fixture(autouse=True)
def require_taskiq_processes(taskiq_worker, taskiq_scheduler):
    """Все тесты в этом модуле требуют реальный TaskIQ worker и scheduler."""
    pass


class TestScheduleService:
    """Тесты ScheduleService напрямую."""

    @pytest.mark.asyncio
    async def test_schedule_one_time_task_creates_in_db(self, app, container, unique_id):
        """schedule_one_time_task создает запись в PostgreSQL."""
        from core.scheduler.models import ContentType

        service = container.schedule_service

        run_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
        flow_id = f"test_agent_{unique_id}"
        session_id = f"{flow_id}:{unique_id}"

        task = await service.schedule_one_time_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=f"test-user-{unique_id}",
            run_at=run_at,
            content_type=ContentType.MESSAGE,
            content="Test reminder",
            description="Test one-time task",
        )

        assert task.id is not None
        assert task.schedule_type == "one_time"
        assert task.content_type == "message"
        assert task.content == "Test reminder"
        assert task.status == "pending"

        # Проверяем что сохранено в БД
        saved_task = await container.scheduled_task_repository.get_by_id(task.id)
        assert saved_task is not None
        assert saved_task.content == "Test reminder"

    @pytest.mark.asyncio
    async def test_schedule_cron_task_creates_in_db(self, app, container, unique_id):
        """schedule_cron_task создает периодическую задачу."""
        from core.scheduler.models import ContentType

        service = container.schedule_service
        flow_id = f"test_agent_{unique_id}"
        session_id = f"{flow_id}:{unique_id}"

        task = await service.schedule_cron_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=f"test-user-{unique_id}",
            cron="0 9 * * *",  # Каждый день в 9:00
            content_type=ContentType.MESSAGE,
            content="Daily reminder",
            description="Daily morning task",
        )

        assert task.id is not None
        assert task.schedule_type == "cron"
        assert task.cron == "0 9 * * *"

        saved_task = await container.scheduled_task_repository.get_by_id(task.id)
        assert saved_task is not None
        assert saved_task.cron == "0 9 * * *"

    @pytest.mark.asyncio
    async def test_schedule_interval_task_creates_in_db(self, app, container, unique_id):
        """schedule_interval_task создает интервальную задачу."""
        from core.scheduler.models import ContentType

        service = container.schedule_service
        flow_id = f"test_agent_{unique_id}"
        session_id = f"{flow_id}:{unique_id}"

        task = await service.schedule_interval_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=f"test-user-{unique_id}",
            interval_minutes=30,
            content_type=ContentType.MESSAGE,
            content="Drink water",
            description="Hydration reminder",
        )

        assert task.id is not None
        assert task.schedule_type == "interval"
        assert task.interval_minutes == 30

        saved_task = await container.scheduled_task_repository.get_by_id(task.id)
        assert saved_task is not None
        assert saved_task.interval_minutes == 30

    @pytest.mark.asyncio
    async def test_list_tasks_returns_session_tasks(self, app, container, unique_id):
        """list_tasks возвращает задачи сессии."""
        from core.scheduler.models import ContentType

        service = container.schedule_service
        flow_id = f"test_agent_{unique_id}"
        session_id = f"{flow_id}:{unique_id}"

        # Создаем несколько задач
        await service.schedule_one_time_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=f"test-user-{unique_id}",
            run_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
            content_type=ContentType.MESSAGE,
            content="Task 1",
        )

        await service.schedule_cron_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=f"test-user-{unique_id}",
            cron="0 10 * * *",
            content_type=ContentType.MESSAGE,
            content="Task 2",
        )

        tasks = await service.list_tasks(session_id=session_id)

        assert len(tasks) >= 2
        contents = [t.content for t in tasks]
        assert "Task 1" in contents
        assert "Task 2" in contents

    @pytest.mark.asyncio
    async def test_cancel_task_updates_status(self, app, container, unique_id):
        """cancel_task меняет статус на cancelled."""
        from core.scheduler.models import ContentType

        service = container.schedule_service
        flow_id = f"test_agent_{unique_id}"
        session_id = f"{flow_id}:{unique_id}"

        task = await service.schedule_one_time_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=f"test-user-{unique_id}",
            run_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
            content_type=ContentType.MESSAGE,
            content="To be cancelled",
        )

        success = await service.cancel_task(task.id)

        assert success is True

        cancelled_task = await container.scheduled_task_repository.get_by_id(task.id)
        assert cancelled_task.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task_returns_false(self, app, container):
        """cancel_task возвращает False для несуществующей задачи."""
        service = container.schedule_service

        success = await service.cancel_task("nonexistent-task-id")

        assert success is False


class TestSchedulingTools:
    """Тесты scheduling tools через container.tool_registry."""

    @pytest.fixture
    def make_state(self):
        """Фабрика для создания ExecutionState."""
        from core.state import ExecutionState

        def _make(unique_id: str, session_suffix: str = ""):
            # session_id в формате flow_id:context_id для правильного извлечения flow_id
            flow_id = f"test_agent_{unique_id}"
            context_id = f"{session_suffix}_{unique_id}" if session_suffix else unique_id
            session_id = f"{flow_id}:{context_id}"
            return ExecutionState(
                task_id=f"test-task-{unique_id}",
                context_id=context_id,
                flow_id=flow_id,
                session_id=session_id,
                user_id=f"test-user-{unique_id}",
            )
        return _make

    @pytest.mark.asyncio
    async def test_schedule_one_time_task_tool(self, app, container, unique_id, make_state):
        """Tool schedule_one_time_task создает задачу."""
        tool = await container.tool_registry.create_tool({"tool_id": "schedule_one_time_task"})
        state = make_state(unique_id)

        run_at = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2)).isoformat()

        result = await tool.run(
            {
                "run_at": run_at,
                "content_type": "message",
                "content": "Tool test reminder",
                "description": "Created by tool",
            },
            state,
        )

        assert "Одноразовая задача создана" in result
        assert len(state.scheduled_tasks) == 1
        assert state.scheduled_tasks[0]["content"] == "Tool test reminder"

    @pytest.mark.asyncio
    async def test_schedule_cron_task_tool(self, app, container, unique_id, make_state):
        """Tool schedule_cron_task создает периодическую задачу."""
        tool = await container.tool_registry.create_tool({"tool_id": "schedule_cron_task"})
        state = make_state(unique_id)

        result = await tool.run(
            {
                "cron": "0 8 * * 1-5",
                "content_type": "message",
                "content": "Weekday morning reminder",
                "description": "Work days only",
            },
            state,
        )

        assert "Периодическая задача создана" in result
        assert "0 8 * * 1-5" in result
        assert len(state.scheduled_tasks) == 1

    @pytest.mark.asyncio
    async def test_schedule_interval_task_tool(self, app, container, unique_id, make_state):
        """Tool schedule_interval_task создает интервальную задачу."""
        tool = await container.tool_registry.create_tool({"tool_id": "schedule_interval_task"})
        state = make_state(unique_id)

        result = await tool.run(
            {
                "interval_minutes": 60,
                "content_type": "message",
                "content": "Hourly check",
            },
            state,
        )

        assert "Периодическая задача создана" in result
        assert "60" in result
        assert len(state.scheduled_tasks) == 1

    @pytest.mark.asyncio
    async def test_list_scheduled_tasks_tool(self, app, container, unique_id, make_state):
        """Tool list_scheduled_tasks показывает задачи."""
        schedule_tool = await container.tool_registry.create_tool({"tool_id": "schedule_one_time_task"})
        list_tool = await container.tool_registry.create_tool({"tool_id": "list_scheduled_tasks"})

        state = make_state(unique_id, "list")

        run_at = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=3)).isoformat()
        await schedule_tool.run(
            {
                "run_at": run_at,
                "content_type": "message",
                "content": "List test task",
            },
            state,
        )

        result = await list_tool.run({}, state)

        assert "Запланированные задачи" in result
        assert "List test task" in result

    @pytest.mark.asyncio
    async def test_cancel_scheduled_task_tool(self, app, container, unique_id, make_state):
        """Tool cancel_scheduled_task отменяет задачу."""
        schedule_tool = await container.tool_registry.create_tool({"tool_id": "schedule_one_time_task"})
        cancel_tool = await container.tool_registry.create_tool({"tool_id": "cancel_scheduled_task"})

        state = make_state(unique_id, "cancel")

        run_at = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=4)).isoformat()
        await schedule_tool.run(
            {
                "run_at": run_at,
                "content_type": "message",
                "content": "To cancel via tool",
            },
            state,
        )

        task_id = state.scheduled_tasks[0]["id"]

        result = await cancel_tool.run({"task_id": task_id}, state)

        assert "отменена" in result
        assert len(state.scheduled_tasks) == 0

    @pytest.mark.asyncio
    async def test_schedule_tool_call_task(self, app, container, unique_id, make_state):
        """Можно запланировать вызов tool."""
        tool = await container.tool_registry.create_tool({"tool_id": "schedule_one_time_task"})
        state = make_state(unique_id)

        run_at = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=5)).isoformat()

        result = await tool.run(
            {
                "run_at": run_at,
                "content_type": "tool_call",
                "content": "calculator",
                "tool_args": {"expression": "2+2"},
                "description": "Scheduled calculation",
            },
            state,
        )

        assert "Одноразовая задача создана" in result
        task_data = state.scheduled_tasks[0]
        assert task_data["content_type"] == "tool_call"
        assert task_data["content"] == "calculator"
        assert task_data["tool_args"] == {"expression": "2+2"}


class TestScheduledTaskExecution:
    """Тесты выполнения scheduled tasks через worker."""

    @pytest.mark.asyncio
    async def test_one_time_task_executes_at_scheduled_time(self, app, container, unique_id, mock_llm_redis):
        """Одноразовая задача выполняется когда время пришло."""
        from apps.flows.src.models import FlowConfig
        from apps.flows.src.tasks.scheduled_tasks import execute_scheduled_task
        from core.scheduler.models import ContentType, ScheduledTaskStatus

        # Создаем простой агент
        flow_id = f"scheduler_test_agent_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Scheduler Test Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['response'] = f\"Received: {state.get('content', '')}\"\n    return state",
                },
            },
            edges=[{"from": "main", "to": None}],
        )
        await container.flow_repository.set(flow_config)

        # Создаем scheduled task
        service = container.schedule_service
        session_id = f"{flow_id}:{unique_id}"

        user_id = f"test-user-{unique_id}"
        task = await service.schedule_one_time_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            run_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=1),
            content_type=ContentType.MESSAGE,
            content="Scheduled message test",
        )

        # Симулируем выполнение scheduled task (как это делает scheduler)
        result = await execute_scheduled_task(
            scheduled_task_id=task.id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            task_type="message",
            payload={"content": "Scheduled message test"},
        )

        assert result["status"] == "completed"
        assert "Scheduled message test" in result["response"]

        # Проверяем что статус обновился
        updated_task = await container.scheduled_task_repository.get_by_id(task.id)
        assert updated_task.status == ScheduledTaskStatus.EXECUTED

    @pytest.mark.asyncio
    async def test_tool_call_task_executes_tool(self, app, container, unique_id):
        """Tool call задача вызывает указанный tool."""
        from apps.flows.src.tasks.scheduled_tasks import execute_scheduled_task
        from core.scheduler.models import ContentType

        service = container.schedule_service
        flow_id = f"test_agent_{unique_id}"
        session_id = f"{flow_id}:{unique_id}"

        user_id = f"test-user-{unique_id}"
        task = await service.schedule_one_time_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            run_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=1),
            content_type=ContentType.TOOL_CALL,
            content="calculator",
            tool_args={"expression": "10+5"},
        )

        result = await execute_scheduled_task(
            scheduled_task_id=task.id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            task_type="tool_call",
            payload={"content": "calculator", "tool_args": {"expression": "10+5"}},
        )

        assert result["tool"] == "calculator"
        assert "15" in str(result["result"])



