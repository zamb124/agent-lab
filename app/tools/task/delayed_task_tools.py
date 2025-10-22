"""
Инструменты для работы с отложенными задачами.
Позволяют агентам создавать задачи для выполнения в будущем.

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
    tools = [DELAYED_TASK_TOOLS]  # ❌ НЕТ! Пользователь может написать "напомни..." → цикл!

Декоратор @tool автоматически оборачивает в Command если state изменился.
"""

import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from app.core.tool_decorator import tool
from app.core.context import get_context
from app.core.variables import get_state
from app.models import TaskConfig, TaskStatus
from app.core.container import get_container

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
    
    ВАРИАНТ 1 - Текстовое напоминание:
    create_delayed_task(3600, message="Напоминание: позвонить маме")
    → Через час отправится сообщение напрямую (skip_agent=True)
    
    ВАРИАНТ 2 - Вызов тула:
    create_delayed_task(3600, tool_name="check_order_status", tool_args={"order_id": "123"})
    → Через час выполнится агент с вызовом тула (skip_agent=False)
    
    ВАЖНО для message: указывай ДЕЙСТВИЕ/КОНТЕКСТ, а НЕ текст пользователя!
    ПРАВИЛЬНО: "Напоминание: позвонить маме"
    НЕПРАВИЛЬНО: "напомни позвонить маме" (создаст цикл!)
    
    Args:
        delay_seconds: Задержка в секундах (например, 3600 = 1 час)
        message: Текст напоминания (для skip_agent=True)
        tool_name: Имя тула для вызова (для skip_agent=False)
        tool_args: Аргументы тула (dict)
        metadata: Дополнительные данные
    
    Returns:
        Сообщение об успешном создании
    
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
    # Проверяем что указано либо message, либо tool_name
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
    
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    execute_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    
    # Определяем тип задачи
    if message:
        # Текстовое напоминание - отправляется напрямую
        task_input = {"message": message, "metadata": metadata or {}}
        task_skip_agent = True
        task_description = message
    else:
        # Вызов тула - выполняется через агента
        task_input = {
            "tool_call": {
                "tool_name": tool_name,
                "tool_args": tool_args or {}
            },
            "metadata": metadata or {}
        }
        task_skip_agent = False
        task_description = f"Вызов тула {tool_name}"
    
    task_config = TaskConfig(
        task_id=task_id,
        flow_id=flow_id,
        context=context,
        status=TaskStatus.PENDING,
        input_data=task_input,
        created_at=datetime.now(timezone.utc),
        execute_at=execute_at,
        skip_agent=task_skip_agent,
    )

    storage = get_container().storage
    task_key = f"task:{task_id}"
    
    logger.info(f"📝 Сохраняем задачу: key={task_key}, flow_id={flow_id}")
    success = await storage.set(task_key, task_config.model_dump_json(), force_global=True)
    
    if not success:
        raise ValueError(f"Не удалось сохранить задачу {task_id}")
    
    logger.info(f"✅ Задача {task_id} сохранена в БД")
    
    # Просто добавляем в state - декоратор автоматически обернет в Command!
    state = get_state()
    if not state:
        raise ValueError("State недоступен")
    
    if "store" not in state:
        state["store"] = {}
    if "delayed_tasks" not in state["store"]:
        state["store"]["delayed_tasks"] = {}
    
    state["store"]["delayed_tasks"][task_id] = {
        "task_id": task_id,
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
    
    logger.info(f"📅 Создана отложенная задача {task_id} на {execute_at}")
    
    execute_at_str = execute_at.strftime('%Y-%m-%d %H:%M:%S UTC')
    
    if message:
        return f"✅ Создана отложенная задача {task_id}\n⏰ Выполнится: {execute_at_str}\n📝 Сообщение: {message}"
    else:
        return f"✅ Создана отложенная задача {task_id}\n⏰ Выполнится: {execute_at_str}\n🔧 Тул: {tool_name}({tool_args})"


@tool(is_public=True, group="Планирование задач и напоминаний", title="Список отложенных задач", state_aware=True)
def list_delayed_tasks() -> str:
    """
    Показывает список всех отложенных задач текущей сессии из state.
    
    Задачи персистятся в state["store"]["delayed_tasks"] через checkpointer.
    
    Returns:
        Форматированный список задач или сообщение об отсутствии
    
    Examples:
        list_delayed_tasks()
    """
    logger.info("🔍 list_delayed_tasks: функция вызвана")
    state = get_state()
    logger.info(f"🔍 list_delayed_tasks: state = {state}")
    
    if not state or "store" not in state or "delayed_tasks" not in state["store"]:
        return "📭 У вас нет отложенных задач"
    
    tasks = state["store"]["delayed_tasks"]
    
    if not tasks:
        return "📭 У вас нет отложенных задач"
    
    # Фильтруем только активные и еще не выполненные
    # Автоматически помечаем как executed те, у которых время прошло
    now = datetime.now(timezone.utc)
    
    active_tasks = {}
    for tid, t in tasks.items():
        if t.get("status") != "scheduled":
            continue  # Пропускаем cancelled/executed
        
        # Проверяем что время еще не наступило
        execute_at_str = t.get("execute_at")
        if execute_at_str:
            execute_at = datetime.fromisoformat(execute_at_str)
            if execute_at > now:
                # Задача еще не выполнилась - показываем
                active_tasks[tid] = t
            else:
                # Время прошло - помечаем как executed (автоматическая очистка)
                tasks[tid]["status"] = "executed"
                tasks[tid]["executed_at"] = now.isoformat()
                logger.debug(f"📅 Задача {tid} автоматически помечена как executed (время прошло)")
    
    if not active_tasks:
        return "📭 У вас нет активных отложенных задач"
    
    # Сортируем по времени выполнения
    sorted_tasks = sorted(active_tasks.values(), key=lambda x: x["execute_at"])
    
    result_lines = [f"📅 Отложенные задачи ({len(sorted_tasks)}):"]
    result_lines.append("")
    
    for idx, task in enumerate(sorted_tasks, 1):
        execute_at = datetime.fromisoformat(task["execute_at"])
        execute_at_str = execute_at.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        now = datetime.now(timezone.utc)
        remaining = execute_at - now
        
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_left = f"через {hours}ч {minutes}м" if hours > 0 else f"через {minutes}м"
        else:
            time_left = "выполняется"
        
        task_type = task.get('type', 'message')
        
        result_lines.append(f"{idx}. {task['task_id']} ⏰ {execute_at_str} ({time_left})")
        
        if task_type == 'message':
            result_lines.append(f"   📝 {task['message']}")
        else:
            tool_name = task.get('tool_name', 'unknown')
            tool_args = task.get('tool_args', {})
            result_lines.append(f"   🔧 {tool_name}({', '.join(f'{k}={v}' for k, v in tool_args.items())})")
        
        result_lines.append(f"   🎯 Flow: {task['flow_id']}")
        result_lines.append("")
    
    return "\n".join(result_lines)


@tool(is_public=True, group="Автоматизация", title="Отменить отложенную задачу")
async def cancel_delayed_task(task_id: str) -> str:
    """
    Отменяет отложенную задачу.
    
    Database-First: проверяет задачу в БД, а не только в state.
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
        return "❌ Сессия не определена"
    
    # Проверяем задачу в БД
    task_repo = get_container().task_repository
    task_config = await task_repo.get(task_id)
    
    if not task_config:
        return f"❌ Задача {task_id} не найдена"
    
    # Проверяем что задача принадлежит текущей сессии
    if task_config.session_id != context.session_id:
        return f"❌ Задача {task_id} не найдена в вашей сессии"
    
    # Проверяем статус
    if task_config.status != TaskStatus.PENDING:
        return f"⚠️ Задача {task_id} уже в статусе {task_config.status.value}"
    
    # Удаляем задачу из БД
    success = await task_repo.delete(task_id)
    
    if success:
        # Опционально: помечаем в state если доступен
        state = get_state()
        if state and "store" in state and "delayed_tasks" in state["store"]:
            if task_id in state["store"]["delayed_tasks"]:
                state["store"]["delayed_tasks"][task_id]["status"] = "cancelled"
                state["store"]["delayed_tasks"][task_id]["cancelled_at"] = datetime.now(timezone.utc).isoformat()
                logger.debug(f"📦 Задача помечена cancelled в state (локальный кэш)")
        
        logger.info(f"🗑️ Задача {task_id} отменена")
        
        message = task_config.input_data.get("message", "")
        return f"✅ Задача {task_id} отменена\n📝 Было: {message}"
    else:
        return f"❌ Не удалось отменить задачу {task_id}"


@tool(is_public=False, title="Статус отложенной задачи")
async def get_delayed_task_status(task_id: str) -> str:
    """
    Проверяет статус отложенной задачи.
    
    Показывает подробную информацию о задаче из БД и сессионной памяти.
    
    Args:
        task_id: ID задачи
    
    Returns:
        Подробная информация о статусе задачи
    
    Examples:
        get_delayed_task_status("task_abc123")
    """
    state = get_state()
    
    if state and "store" in state and "delayed_tasks" in state["store"]:
        tasks = state["store"]["delayed_tasks"]
        if task_id in tasks:
            task_info = tasks[task_id]

            storage = get_container().storage
            task_data = await storage.get(f"task:{task_id}", force_global=True)
            
            if task_data:
                task_config = TaskConfig.model_validate_json(task_data)
                
                result = [
                    f"📋 Задача {task_id}",
                    f"",
                    f"🎯 Flow: {task_info['flow_id']}",
                    f"📝 Сообщение: {task_info['message']}",
                    f"⏰ Запланировано: {task_info['execute_at']}",
                    f"🔄 Статус в памяти: {task_info['status']}",
                    f"🔄 Статус в БД: {task_config.status.value}",
                ]
                
                if task_config.execute_at:
                    now = datetime.now(timezone.utc)
                    remaining = task_config.execute_at - now
                    
                    if remaining.total_seconds() > 0:
                        hours = int(remaining.total_seconds() // 3600)
                        minutes = int((remaining.total_seconds() % 3600) // 60)
                        result.append(f"⏳ Осталось: {hours}ч {minutes}м")
                    else:
                        result.append(f"⏳ Время наступило, задача в очереди на выполнение")
                
                return "\n".join(result)
            else:
                return f"⚠️ Задача {task_id} есть в памяти но отсутствует в БД (возможно выполнена)"
    
    return f"❌ Задача {task_id} не найдена в вашей сессии"


DELAYED_TASK_TOOLS = [
    create_delayed_task,
    list_delayed_tasks,
    cancel_delayed_task,
    get_delayed_task_status,
]

