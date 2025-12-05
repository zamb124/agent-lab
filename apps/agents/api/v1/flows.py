"""
Новое API для работы с флоу.
Поддерживает сессии, историю диалогов, файлы и polling задач.
"""

import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

from apps.agents.interfaces.api_interface import get_api_interface
from apps.agents.dependencies import FlowRepositoryDep
from apps.agents.container import get_agents_container
from core.tasks.broker import result_backend

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/flows",
    tags=["Боты и сообщения"],
    responses={
        404: {"description": "Бот или задача не найдены"},
        500: {"description": "Внутренняя ошибка сервера"}
    }
)


class MessageFile(BaseModel):
    """Файл в API сообщении"""

    name: str
    content: str  # base64 encoded
    content_type: Optional[str] = None


class HistoryMessage(BaseModel):
    """Сообщение в истории диалога"""

    role: str  # user, assistant, system
    message: str
    timestamp: Optional[str] = None


class FlowMessageRequest(BaseModel):
    """Запрос на отправку сообщения в флоу"""

    message: str
    role: str = "user"
    user_id: str = "anonymous"
    session_id: Optional[str] = None  # Если не указан, создается новый
    files: List[MessageFile] = Field(default_factory=list)
    history: List[HistoryMessage] = Field(default_factory=list)  # Опциональная история
    wait_timeout: Optional[float] = Field(default=None, description="Если указан - ждём результат синхронно (секунды)")


class FlowMessageResponse(BaseModel):
    """Ответ на отправку сообщения в флоу"""

    task_id: str
    session_id: str
    status: str = "pending"
    message: str = "Сообщение принято в обработку"
    result: Optional[Dict[str, Any]] = None  # Результат если wait_timeout указан


class TaskResponse(BaseModel):
    """Ответ с результатом задачи"""

    task_id: str
    status: str  # pending, processing, completed, failed
    session_id: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


@router.post("/{flow_id}/message", response_model=FlowMessageResponse, summary="Отправить сообщение боту")
async def send_message_to_flow(flow_id: str, request: FlowMessageRequest, flow_repo: FlowRepositoryDep):
    """
    Отправляет текстовое сообщение боту для обработки.
    
    Создает задачу на обработку сообщения. Бот обрабатывает запрос асинхронно.
    Для получения ответа используйте polling endpoint GET /{flow_id}/task/{task_id}.
    
    **Процесс:**
    1. Отправляете сообщение → получаете task_id
    2. Периодически запрашиваете статус задачи
    3. Когда status = "completed" → получаете ответ бота
    
    **Сессии:**
    - Если session_id не указан - создается новая сессия
    - Для продолжения диалога передавайте тот же session_id
    
    **Файлы:**
    - Можно прикрепить файлы (base64 encoded)
    - Бот получит доступ к содержимому файлов

    Args:
        flow_id: ID бота (например: "my_support_bot")
        request: Данные сообщения с текстом, файлами и метаданными

    Returns:
        task_id для polling и session_id для продолжения диалога
    """
    # Проверяем что флоу существует и поддерживает API
    flow_config = await flow_repo.get(flow_id)

    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Флоу {flow_id} не найден")

    # Проверяем что флоу поддерживает API платформу
    if "api" not in flow_config.platforms:
        raise HTTPException(
            status_code=400, detail=f"Флоу {flow_id} не поддерживает API платформу"
        )

    # Подготавливаем данные для API интерфейса
    api_data = {
        "message": request.message,
        "role": request.role,
        "user_id": request.user_id,
        "session_id": request.session_id,
        "files": [file.model_dump() for file in request.files],
        "history": [msg.model_dump() for msg in request.history],
    }

    # Обрабатываем через API интерфейс
    api_interface = get_api_interface()
    message = await api_interface.handle_message(api_data, flow_id)

    if not message:
        raise HTTPException(status_code=400, detail="Не удалось обработать сообщение")

    # Создаем задачу через TaskIQ
    # Если wait_timeout указан - ждём результат синхронно
    task_result = await api_interface.create_task(
        message, 
        flow_id, 
        wait_timeout=request.wait_timeout
    )

    # Синхронный режим - результат уже получен
    if request.wait_timeout is not None:
        logger.info(f"Синхронный запрос к флоу {flow_id} завершён")
        return FlowMessageResponse(
            task_id="sync",
            session_id=message.session_id,
            status="completed",
            message="Выполнено",
            result=task_result if isinstance(task_result, dict) else {"response": str(task_result)},
        )

    # Асинхронный режим - возвращаем task_id для polling
    logger.info(f"Создана API задача {task_result} для флоу {flow_id}")

    return FlowMessageResponse(
        task_id=task_result,
        session_id=message.session_id,
        status="pending",
        message="Сообщение принято в обработку",
    )


@router.get("/{flow_id}/task/{task_id}", response_model=TaskResponse, summary="Получить результат задачи")
async def get_task_result(flow_id: str, task_id: str):
    """
    Получает статус и результат обработки сообщения (polling).
    
    **Статусы задачи:**
    - `pending` - ожидает обработки
    - `completed` - выполнена, результат в поле result
    - `waiting_for_input` - бот ожидает ответа пользователя (вопрос в result.question)
    - `failed` - ошибка, детали в error_message
    
    **Polling:**
    Рекомендуем запрашивать статус каждые 1-2 секунды до получения completed или failed.
    
    **Когда бот задает вопрос:**
    Если status = "waiting_for_input", в result.question будет вопрос бота.
    Отправьте ответ через POST /{flow_id}/message с тем же session_id.

    Args:
        flow_id: ID бота
        task_id: ID задачи полученный при отправке сообщения

    Returns:
        Статус задачи и результат (если completed)
    """
    # Получаем результат из TaskIQ result backend
    task_result = await result_backend.get_result(task_id)
    
    if task_result is None:
        # Задача еще не завершена или не найдена
        return TaskResponse(
            task_id=task_id,
            status="pending",
            session_id="",
        )
    
    logger.info(f"🔍 API читает результат задачи {task_id}: is_err={task_result.is_err}")
    
    if task_result.is_err:
        return TaskResponse(
            task_id=task_id,
            status="failed",
            session_id="",
            error_message=str(task_result.error) if task_result.error else "Unknown error",
        )
    
    # Успешный результат
    result_data = task_result.return_value or {}
    status = result_data.get("status", "completed")
    session_id = result_data.get("session_id", "")
    
    return TaskResponse(
        task_id=task_id,
        status=status,
        session_id=session_id,
        result=result_data,
    )


@router.get("/{flow_id}/session/{session_id}/history", summary="История диалога")
async def get_session_history(flow_id: str, session_id: str, limit: int = 50):
    """
    Получает историю сообщений в сессии (диалоге).
    
    Возвращает все сообщения пользователя и бота в хронологическом порядке.
    
    Полезно для:
    - Отображения истории диалога в UI
    - Анализа взаимодействий
    - Восстановления контекста

    Args:
        flow_id: ID бота
        session_id: ID сессии (диалога)
        limit: Максимальное количество сообщений (по умолчанию 50)

    Returns:
        Массив сообщений с ролями, текстом и временными метками
    """
    try:
        # Здесь можно реализовать получение истории из checkpointer
        # Пока возвращаем заглушку
        return {
            "session_id": session_id,
            "flow_id": flow_id,
            "messages": [],
            "message": "История сессий будет реализована позже",
        }

    except Exception as e:
        logger.error(f"Ошибка получения истории сессии {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{flow_id}/session/{session_id}", summary="Очистить сессию")
async def clear_session(flow_id: str, session_id: str):
    """
    Деактивирует сессию (завершает диалог).
    
    После очистки сессии:
    - История сохраняется
    - Новое сообщение с тем же session_id создаст новый диалог
    - Контекст сбрасывается
    
    Используйте когда пользователь завершил диалог или начинает новую тему.

    Args:
        flow_id: ID бота
        session_id: ID сессии для деактивации

    Returns:
        Подтверждение успешной операции
    """
    try:
        # Деактивируем сессию
        storage = get_agents_container().storage

        # Ищем сессию по разным возможным ключам
        session_keys = [f"session:api:{session_id}", session_id]

        session_found = False
        for session_key in session_keys:
            session_data = await storage.get(session_key)
            if session_data:
                session_info = json.loads(session_data)
                session_info["status"] = "inactive"
                session_info["last_activity"] = datetime.now(timezone.utc).isoformat()
                await storage.set(session_key, json.dumps(session_info))
                session_found = True
                logger.info(f"🧹 Сессия деактивирована: {session_key}")
                break

        if session_found:
            return {"success": True, "message": f"Сессия {session_id} очищена"}
        else:
            raise HTTPException(status_code=404, detail="Сессия не найдена")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка очистки сессии {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{flow_id}/info", summary="Информация о боте")
async def get_flow_info(flow_id: str, flow_repo: FlowRepositoryDep):
    """
    Получает информацию о боте: название, описание, поддерживаемые платформы.
    
    Используйте этот endpoint чтобы проверить доступность бота перед отправкой сообщений.

    Args:
        flow_id: ID бота

    Returns:
        Название, описание, список платформ, entry point агент
    """
    try:
        flow_config = await flow_repo.get(flow_id)

        if not flow_config:
            raise HTTPException(status_code=404, detail=f"Флоу {flow_id} не найден")

        # Проверяем поддержку API
        api_supported = "api" in flow_config.platforms

        return {
            "flow_id": flow_config.flow_id,
            "name": flow_config.name,
            "description": flow_config.description,
            "api_supported": api_supported,
            "platforms": list(flow_config.platforms.keys()),
            "entry_point": flow_config.entry_point_agent,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения информации о флоу {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", summary="Список доступных ботов")
async def list_flows(flow_repo: FlowRepositoryDep):
    """
    Получает список всех ботов доступных через API.
    
    Возвращает только ботов с включенной платформой API.

    Returns:
        Массив ботов с их ID, названиями и описаниями
    """
    try:
        # Получаем все флоу (это может быть медленно для большого количества)
        # В реальности лучше сделать отдельный метод в Storage
        flows = []

        # Пока простая реализация - в будущем можно оптимизировать
        test_flows = ["test_flow", "smart_flow", "weather_flow"]

        for flow_id in test_flows:
            flow_config = await flow_repo.get(flow_id)
            if flow_config and "api" in flow_config.platforms:
                flows.append(
                    {
                        "flow_id": flow_config.flow_id,
                        "name": flow_config.name,
                        "description": flow_config.description,
                    }
                )

        return {"flows": flows, "total": len(flows)}

    except Exception as e:
        logger.error(f"Ошибка получения списка флоу: {e}")
        raise HTTPException(status_code=500, detail=str(e))
