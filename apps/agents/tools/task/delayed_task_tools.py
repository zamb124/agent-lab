"""
Инструменты для работы с отложенными задачами через TaskIQ Scheduler.
Позволяют агентам создавать задачи для выполнения в будущем.

АРХИТЕКТУРА:
- Отложенные задачи создаются через TaskIQ schedule_by_time()
- Scheduler хранит расписания в PostgreSQL (AsyncpgScheduleSource)
- При наступлении времени Scheduler вызывает process_agent_task

ИСПОЛЬЗОВАНИЕ:
Эти тулы предназначены для АВТОМАТИЗАЦИИ внутри flow, а не для прямого взаимодействия с пользователями.

ПРАВИЛЬНЫЙ ПРИМЕР:
class OrderProcessingAgent(BaseAgent):
    tools = [DELAYED_TASK_TOOLS]
    
    prompt = '''
    Ты агент обработки заказов.
    
    После создания заказа:
    1. Создай задачу на проверку статуса через 1 час:
       create_delayed_task("Проверить статус заказа #{order_id}", 3600)
    
    2. Создай задачу на follow-up через 24 часа:
       create_delayed_task("Follow-up по заказу #{order_id}: связаться с клиентом", 86400)
    '''

НЕПРАВИЛЬНЫЙ ПРИМЕР:
class FAQAgent(BaseAgent):
    tools = [DELAYED_TASK_TOOLS]  # НЕТ! Пользователь может написать "напомни..." -> цикл!
"""

import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from apps.agents.services.tool_decorator import tool
from core.context import get_context
from core.variables import get_state
from core.tasks.broker import schedule_source
from apps.agents.tasks.agent_tasks import process_agent_task

logger = logging.getLogger(__name__)


@tool(is_public=True, group="Планирование задач и напоминаний", title="Создать отложенную задачу", state_aware=True)
async def create_delayed_task(
    delay_seconds: int,
    message: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Создает отложенную задачу для текущего flow через указанное время.
    
    Задача выполняется через TaskIQ Scheduler - когда наступает время,
    scheduler вызывает process_agent_task с указанным сообщением.
    
    ВАРИАНТ 1 - Текстовое напоминание:
    create_delayed_task(3600, message="Напоминание: позвонить маме")
    -> Через час агент получит сообщение и обработает его
    
    ВАРИАНТ 2 - Вызов тула:
    create_delayed_task(3600, tool_name="check_order_status", tool_args={"order_id": "123"})
    -> Через час агент выполнит вызов указанного тула
    
    ВАЖНО для message: указывай ДЕЙСТВИЕ/КОНТЕКСТ, а НЕ текст пользователя!
    ПРАВИЛЬНО: "Напоминание: позвонить маме"
    НЕПРАВИЛЬНО: "напомни позвонить маме" (создаст цикл!)
    
    Args:
        delay_seconds: Задержка в секундах (например, 3600 = 1 час)
        message: Текст напоминания
        tool_name: Имя тула для вызова
        tool_args: Аргументы тула (dict)
        metadata: Дополнительные данные
    
    Returns:
        Сообщение об успешном создании с schedule_id
    
    Examples:
        # Напоминание
        create_delayed_task(3600, message="Напоминание: позвонить маме")
        
        # Вызов тула
        create_delayed_task(
            delay_seconds=86400,
            tool_name="send_followup_email",
            tool_args={"client_id": "456", "subject": "Проверка заявки"}
        )
    """
    if not message and not tool_name:
        raise ValueError("Укажите либо message, либо tool_name")
    
    if message and tool_name:
        raise ValueError("Укажите либо message, либо tool_name, но не оба сразу")
    
    context = get_context()
    
    if not context:
        raise ValueError("Context недоступен")
    
    if not context.flow_config:
        raise ValueError("flow_config не найден в контексте")
    
    flow_id = context.flow_config.flow_id
    session_id = context.session_id
    platform = context.platform or "api"
    user_id = context.user.user_id if context.user else "system"
    company_id = context.active_company.company_id if context.active_company else "default"
    
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    execute_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    
    # Формируем сообщение для агента
    if message:
        task_message = f"[DELAYED_TASK:{task_id}] {message}"
    else:
        # Для вызова тула формируем специальное сообщение
        tool_args_str = ", ".join(f'{k}={v}' for k, v in (tool_args or {}).items())
        task_message = f"[DELAYED_TASK:{task_id}] Выполни инструмент {tool_name}({tool_args_str})"
    
    # Планируем задачу через TaskIQ
    schedule = await process_agent_task.schedule_by_time(
        schedule_source,
        execute_at,
        flow_id=flow_id,
        session_id=session_id,
        message=task_message,
        platform=platform,
        user_id=user_id,
        company_id=company_id,
        metadata={
            **(metadata or {}),
            "delayed_task_id": task_id,
            "original_message": message,
            "tool_name": tool_name,
            "tool_args": tool_args,
        },
    )
    
    schedule_id = schedule.schedule_id
    
    logger.info(f"Scheduled delayed task {task_id} (schedule_id={schedule_id}) for {execute_at}")
    
    # Сохраняем в state для отслеживания
    state = get_state()
    if not state:
        raise ValueError("State недоступен")
    
    if "store" not in state:
        state["store"] = {}
    if "delayed_tasks" not in state["store"]:
        state["store"]["delayed_tasks"] = {}
    
    state["store"]["delayed_tasks"][task_id] = {
        "task_id": task_id,
        "schedule_id": schedule_id,
        "flow_id": flow_id,
        "session_id": session_id,
        "type": "message" if message else "tool_call",
        "message": message if message else None,
        "tool_name": tool_name if tool_name else None,
        "tool_args": tool_args if tool_args else None,
        "execute_at": execute_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "scheduled",
        "metadata": metadata or {},
        "delay_seconds": delay_seconds,
    }
    
    execute_at_str = execute_at.strftime('%Y-%m-%d %H:%M:%S UTC')
    
    if message:
        return f"Создана отложенная задача {task_id}\nВыполнится: {execute_at_str}\nСообщение: {message}"
    else:
        return f"Создана отложенная задача {task_id}\nВыполнится: {execute_at_str}\nТул: {tool_name}({tool_args})"


@tool(is_public=True, group="Планирование задач и напоминаний", title="Список отложенных задач", state_aware=True)
async def list_delayed_tasks() -> str:
    """Показывает список отложенных задач текущей сессии."""
    state = get_state()
    
    if not state or "store" not in state or "delayed_tasks" not in state["store"]:
        return "У вас нет отложенных задач"
    
    tasks = state["store"]["delayed_tasks"]
    
    if not tasks:
        return "У вас нет отложенных задач"
    
    now = datetime.now(timezone.utc)
    
    active_tasks = {}
    for tid, t in tasks.items():
        if t.get("status") != "scheduled":
            continue
        
        execute_at_str = t.get("execute_at")
        if execute_at_str:
            execute_at = datetime.fromisoformat(execute_at_str)
            if execute_at > now:
                active_tasks[tid] = t
            else:
                tasks[tid]["status"] = "executed"
                tasks[tid]["executed_at"] = now.isoformat()
    
    if not active_tasks:
        return "У вас нет активных отложенных задач"
    
    sorted_tasks = sorted(active_tasks.values(), key=lambda x: x["execute_at"])
    
    result_lines = [f"Отложенные задачи ({len(sorted_tasks)}):"]
    result_lines.append("")
    
    for idx, task in enumerate(sorted_tasks, 1):
        execute_at = datetime.fromisoformat(task["execute_at"])
        execute_at_str = execute_at.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        remaining = execute_at - now
        
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_left = f"через {hours}ч {minutes}м" if hours > 0 else f"через {minutes}м"
        else:
            time_left = "выполняется"
        
        task_type = task.get('type', 'message')
        
        result_lines.append(f"{idx}. {task['task_id']} - {execute_at_str} ({time_left})")
        
        if task_type == 'message':
            result_lines.append(f"   Сообщение: {task['message']}")
        else:
            tool_name = task.get('tool_name', 'unknown')
            tool_args = task.get('tool_args', {})
            result_lines.append(f"   Тул: {tool_name}({', '.join(f'{k}={v}' for k, v in tool_args.items())})")
        
        result_lines.append(f"   Flow: {task['flow_id']}")
        result_lines.append("")
    
    return "\n".join(result_lines)


@tool(is_public=True, group="Автоматизация", title="Отменить отложенную задачу")
async def cancel_delayed_task(task_id: str) -> str:
    """
    Отменяет отложенную задачу.
    
    Удаляет задачу из TaskIQ Scheduler и помечает её как cancelled в state.
    Можно отменить только свои задачи (из текущей сессии).
    
    Args:
        task_id: ID задачи для отмены (например, "task_abc123")
    
    Returns:
        Сообщение об успешной отмене или ошибке
    
    Examples:
        cancel_delayed_task("task_abc123")
    """
    context = get_context()
    
    if not context or not context.session_id:
        return "Сессия не определена"
    
    state = get_state()
    
    if not state or "store" not in state or "delayed_tasks" not in state["store"]:
        return f"Задача {task_id} не найдена"
    
    tasks = state["store"]["delayed_tasks"]
    
    if task_id not in tasks:
        return f"Задача {task_id} не найдена в вашей сессии"
    
    task_info = tasks[task_id]
    
    if task_info.get("status") != "scheduled":
        return f"Задача {task_id} уже в статусе {task_info.get('status')}"
    
    schedule_id = task_info.get("schedule_id")
    
    if schedule_id:
        try:
            await schedule_source.delete_schedule(schedule_id)
            logger.info(f"Deleted schedule {schedule_id} for task {task_id}")
        except Exception as e:
            logger.warning(f"Failed to delete schedule {schedule_id}: {e}")
    
    tasks[task_id]["status"] = "cancelled"
    tasks[task_id]["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    
    message = task_info.get("message", task_info.get("tool_name", ""))
    return f"Задача {task_id} отменена\nБыло: {message}"


@tool(is_public=False, title="Статус отложенной задачи")
async def get_delayed_task_status(task_id: str) -> str:
    """
    Проверяет статус отложенной задачи.
    
    Показывает информацию о задаче из сессионной памяти.
    
    Args:
        task_id: ID задачи
    
    Returns:
        Подробная информация о статусе задачи
    
    Examples:
        get_delayed_task_status("task_abc123")
    """
    state = get_state()
    
    if not state or "store" not in state or "delayed_tasks" not in state["store"]:
        return f"Задача {task_id} не найдена"
    
    tasks = state["store"]["delayed_tasks"]
    
    if task_id not in tasks:
        return f"Задача {task_id} не найдена в вашей сессии"
    
    task_info = tasks[task_id]
    
    result = [
        f"Задача {task_id}",
        "",
        f"Flow: {task_info['flow_id']}",
        f"Статус: {task_info['status']}",
        f"Запланировано: {task_info['execute_at']}",
        f"Schedule ID: {task_info.get('schedule_id', 'N/A')}",
    ]
    
    if task_info.get("type") == "message":
        result.append(f"Сообщение: {task_info['message']}")
    else:
        result.append(f"Тул: {task_info.get('tool_name')}")
        result.append(f"Аргументы: {task_info.get('tool_args')}")
    
    execute_at_str = task_info.get("execute_at")
    if execute_at_str and task_info["status"] == "scheduled":
        execute_at = datetime.fromisoformat(execute_at_str)
        now = datetime.now(timezone.utc)
        remaining = execute_at - now
        
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            result.append(f"Осталось: {hours}ч {minutes}м")
        else:
            result.append("Время наступило, задача в очереди на выполнение")
    
    return "\n".join(result)


DELAYED_TASK_TOOLS = [
    create_delayed_task,
    list_delayed_tasks,
    cancel_delayed_task,
    get_delayed_task_status,
]
