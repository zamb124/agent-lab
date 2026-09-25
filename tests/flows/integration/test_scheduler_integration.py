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

from apps.flows.src.models import FlowConfig
from apps.flows.src.models.scheduled_task_payload import FlowScheduledTaskPayload
from apps.flows.src.services.schedule_service import ScheduleService
from core.clients.scheduler_client import SchedulerClient
from core.models.identity_models import User
from core.scheduler.models import PlatformScheduledTask

pytestmark = [pytest.mark.integration, pytest.mark.real_taskiq]


@pytest.fixture(autouse=True)
def require_taskiq_processes(taskiq_worker, taskiq_scheduler):
    """Все тесты в этом модуле требуют реальный TaskIQ worker и scheduler."""
    _ = taskiq_worker, taskiq_scheduler


@pytest.fixture
def schedule_service() -> ScheduleService:
    """ScheduleService, как его собирает процесс flows: control-plane scheduler по HTTP."""
    return ScheduleService(scheduler_client=SchedulerClient())


class TestScheduleService:
    """Тесты ScheduleService напрямую."""

    @pytest.mark.asyncio
    async def test_schedule_one_time_task_creates_in_db(self, app, di, unique_id, schedule_service):
        """schedule_one_time_task создает запись в PostgreSQL."""
        from core.scheduler.models import ContentType

        service = schedule_service
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
        assert task.schedule_task_id is not None
        assert task.schedule_type == "one_time"
        assert task.content_type == "message"
        assert task.content == "Test reminder"
        assert task.status == "pending"
        saved_task = await PlatformScheduledTask.get(task.schedule_task_id)
        assert saved_task is not None
        assert (
            FlowScheduledTaskPayload.model_validate(saved_task.payload).content == "Test reminder"
        )

    @pytest.mark.asyncio
    async def test_schedule_cron_task_creates_in_db(self, app, di, unique_id, schedule_service):
        """schedule_cron_task создает периодическую задачу."""
        from core.scheduler.models import ContentType

        service = schedule_service
        flow_id = f"test_agent_{unique_id}"
        session_id = f"{flow_id}:{unique_id}"
        task = await service.schedule_cron_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=f"test-user-{unique_id}",
            cron="0 9 * * *",
            content_type=ContentType.MESSAGE,
            content="Daily reminder",
            description="Daily morning task",
        )
        assert task.schedule_task_id is not None
        assert task.schedule_type == "cron"
        assert task.cron == "0 9 * * *"
        saved_task = await PlatformScheduledTask.get(task.schedule_task_id)
        assert saved_task is not None
        assert saved_task.cron == "0 9 * * *"

    @pytest.mark.asyncio
    async def test_schedule_interval_task_creates_in_db(self, app, di, unique_id, schedule_service):
        """schedule_interval_task создает интервальную задачу."""
        from core.scheduler.models import ContentType

        service = schedule_service
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
        assert task.schedule_task_id is not None
        assert task.schedule_type == "interval"
        assert task.interval_minutes == 30
        saved_task = await PlatformScheduledTask.get(task.schedule_task_id)
        assert saved_task is not None
        assert saved_task.interval_seconds == 30 * 60

    @pytest.mark.asyncio
    async def test_list_tasks_returns_session_tasks(self, app, di, unique_id, schedule_service):
        """list_tasks возвращает задачи сессии."""
        from core.scheduler.models import ContentType

        service = schedule_service
        flow_id = f"test_agent_{unique_id}"
        session_id = f"{flow_id}:{unique_id}"
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
    async def test_cancel_task_updates_status(self, app, di, unique_id, schedule_service):
        """cancel_task меняет статус на cancelled."""
        from core.scheduler.models import ContentType

        service = schedule_service
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
        success = await service.cancel_task(task.schedule_task_id)
        assert success is True
        cancelled_task = await PlatformScheduledTask.get(task.schedule_task_id)
        assert cancelled_task is not None
        assert cancelled_task.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task_returns_false(self, app, di, schedule_service):
        """cancel_task возвращает False для несуществующей задачи."""
        service = schedule_service
        success = await service.cancel_task("nonexistent-task-id")
        assert success is False


class TestSchedulingTools:
    """Тесты scheduling tools через di.tool_registry."""

    @pytest.fixture
    def make_state(self):
        """Фабрика для создания ExecutionState."""
        from core.state import ExecutionState

        def _make(unique_id: str, session_suffix: str = ""):
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
    async def test_schedule_one_time_task_tool(self, app, di, unique_id, make_state):
        """Tool schedule_one_time_task создает задачу."""
        tool = await di.tool_registry.create_tool({"tool_id": "schedule_one_time_task"})
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
        assert isinstance(result, dict)
        assert result["content"] == "Tool test reminder"
        assert result["schedule_type"] == "one_time"
        assert len(state.scheduled_tasks) == 1
        assert state.scheduled_tasks[0]["content"] == "Tool test reminder"

    @pytest.mark.asyncio
    async def test_schedule_cron_task_tool(self, app, di, unique_id, make_state):
        """Tool schedule_cron_task создает периодическую задачу."""
        tool = await di.tool_registry.create_tool({"tool_id": "schedule_cron_task"})
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
        assert isinstance(result, dict)
        assert result["schedule_type"] == "cron"
        assert result["cron"] == "0 8 * * 1-5"
        assert len(state.scheduled_tasks) == 1

    @pytest.mark.asyncio
    async def test_schedule_interval_task_tool(self, app, di, unique_id, make_state):
        """Tool schedule_interval_task создает интервальную задачу."""
        tool = await di.tool_registry.create_tool({"tool_id": "schedule_interval_task"})
        state = make_state(unique_id)
        result = await tool.run(
            {"interval_minutes": 60, "content_type": "message", "content": "Hourly check"}, state
        )
        assert isinstance(result, dict)
        assert result["schedule_type"] == "interval"
        assert result["interval_minutes"] == 60
        assert len(state.scheduled_tasks) == 1

    @pytest.mark.asyncio
    async def test_list_scheduled_tasks_tool(self, app, di, unique_id, make_state):
        """Tool list_scheduled_tasks показывает задачи."""
        schedule_tool = await di.tool_registry.create_tool(
            {"tool_id": "schedule_one_time_task"}
        )
        list_tool = await di.tool_registry.create_tool({"tool_id": "list_scheduled_tasks"})
        state = make_state(unique_id, "list")
        run_at = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=3)).isoformat()
        await schedule_tool.run(
            {"run_at": run_at, "content_type": "message", "content": "List test task"}, state
        )
        result = await list_tool.run({}, state)
        assert isinstance(result, dict)
        items = result["items"]
        assert isinstance(items, list)
        assert any(
            isinstance(item, dict) and item.get("content") == "List test task" for item in items
        )

    @pytest.mark.asyncio
    async def test_cancel_scheduled_task_tool(self, app, di, unique_id, make_state):
        """Tool cancel_scheduled_task отменяет задачу."""
        schedule_tool = await di.tool_registry.create_tool(
            {"tool_id": "schedule_one_time_task"}
        )
        cancel_tool = await di.tool_registry.create_tool(
            {"tool_id": "cancel_scheduled_task"}
        )
        state = make_state(unique_id, "cancel")
        run_at = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=4)).isoformat()
        await schedule_tool.run(
            {"run_at": run_at, "content_type": "message", "content": "To cancel via tool"}, state
        )
        schedule_task_id = state.scheduled_tasks[0]["schedule_task_id"]
        result = await cancel_tool.run({"schedule_task_id": schedule_task_id}, state)
        assert isinstance(result, dict)
        assert result["cancelled"] is True
        assert result["schedule_task_id"] == schedule_task_id
        assert len(state.scheduled_tasks) == 0

    @pytest.mark.asyncio
    async def test_schedule_tool_call_task(self, app, di, unique_id, make_state):
        """Можно запланировать вызов tool."""
        tool = await di.tool_registry.create_tool({"tool_id": "schedule_one_time_task"})
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
        assert isinstance(result, dict)
        assert result["content_type"] == "tool_call"
        assert result["content"] == "calculator"
        task_data = state.scheduled_tasks[0]
        assert task_data["content_type"] == "tool_call"
        assert task_data["content"] == "calculator"
        assert task_data["tool_args"] == {"expression": "2+2"}


class TestScheduledTaskExecution:
    """Тесты выполнения scheduled tasks через worker."""

    @pytest.mark.asyncio
    async def test_one_time_task_executes_at_scheduled_time(
        self, app, di, unique_id, mock_llm_redis
    ):
        """Одноразовая задача выполняется когда время пришло."""
        from apps.flows.src.tasks.scheduled_tasks import execute_scheduled_task
        from core.scheduler.models import ContentType, ScheduledTaskStatus

        flow_id = f"scheduler_test_agent_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Scheduler Test Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['response'] = f\"Received: {state.get('content', '')}\"\n    return state",
                }
            },
            edges=[{"from_node": "main", "to_node": None}],
        )
        await FlowConfig.create_version(flow_config)
        service = schedule_service
        session_id = f"{flow_id}:{unique_id}"
        user_id = f"test-user-{unique_id}"
        await User.set(
            User(
                user_id=user_id,
                name="Scheduler Test User",
                companies={"system": ["member"]},
                active_company_id="system",
            )
        )
        task = await service.schedule_one_time_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            run_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=1),
            content_type=ContentType.MESSAGE,
            content="Scheduled message test",
        )
        result = await execute_scheduled_task(
            schedule_task_id=task.schedule_task_id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            content_type=ContentType.MESSAGE.value,
            content="Scheduled message test",
            company_id="system",
            di=di,
        )
        assert result["task_state"] == "completed"
        assert "Scheduled message test" in result["response"]
        updated_task = await PlatformScheduledTask.get(task.schedule_task_id)
        assert updated_task is not None
        assert updated_task.status == ScheduledTaskStatus.EXECUTED

    @pytest.mark.asyncio
    async def test_tool_call_task_executes_tool(self, app, di, unique_id):
        """Tool call задача вызывает указанный tool."""
        from apps.flows.src.tasks.scheduled_tasks import execute_scheduled_task
        from core.scheduler.models import ContentType

        flow_id = f"test_agent_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Scheduler Tool Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "code",
                    "code": "async def run(args, state):\n    return state",
                }
            },
            edges=[{"from_node": "main", "to_node": None}],
        )
        await FlowConfig.create_version(flow_config)
        service = schedule_service
        session_id = f"{flow_id}:{unique_id}"
        user_id = f"test-user-{unique_id}"
        await User.set(
            User(
                user_id=user_id,
                name="Scheduler Tool User",
                companies={"system": ["member"]},
                active_company_id="system",
            )
        )
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
            schedule_task_id=task.schedule_task_id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            content_type=ContentType.TOOL_CALL.value,
            content="calculator",
            tool_args={"expression": "10+5"},
            company_id="system",
            di=di,
        )
        assert result["tool"] == "calculator"
        assert "15" in str(result["result"])
