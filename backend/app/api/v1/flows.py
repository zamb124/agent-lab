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

from app.interfaces.api_interface import api_interface
from app.core.storage import Storage
from app.models import TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter()


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


class FlowMessageResponse(BaseModel):
    """Ответ на отправку сообщения в флоу"""

    task_id: str
    session_id: str
    status: str = "pending"
    message: str = "Сообщение принято в обработку"


class TaskResponse(BaseModel):
    """Ответ с результатом задачи"""

    task_id: str
    status: str  # pending, processing, completed, failed
    session_id: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


@router.post("/{flow_id}/message", response_model=FlowMessageResponse)
async def send_message_to_flow(flow_id: str, request: FlowMessageRequest):
    """
    Отправляет сообщение в флоу.

    Args:
        flow_id: ID флоу
        request: Данные сообщения

    Returns:
        Информация о созданной задаче
    """
    # Проверяем что флоу существует и поддерживает API
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)

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
    message = await api_interface.handle_message(api_data, flow_id)

    if not message:
        raise HTTPException(status_code=400, detail="Не удалось обработать сообщение")

    # ПРОВЕРЯЕМ: есть ли прерванная задача для этой сессии
    storage = Storage()
    interrupted_task = await storage.find_interrupted_task(message.session_id, flow_id)

    if interrupted_task:
        # ПРОДОЛЖАЕМ прерванную задачу вместо создания новой
        logger.info(
            f"🔄 Найдена прерванная задача {interrupted_task.task_id} для сессии {message.session_id}"
        )

        # Обновляем прерванную задачу с новым сообщением пользователя
        logger.info(
            f"🔄 Обновляем задачу: старое сообщение='{interrupted_task.input_data.get('message', '')}', новое='{message.content}'"
        )
        interrupted_task.input_data["message"] = message.content
        interrupted_task.input_data["metadata"] = message.metadata or {}
        logger.info(
            f"🔄 Переводим задачу {interrupted_task.task_id} из {interrupted_task.status} в pending"
        )
        interrupted_task.status = (
            TaskStatus.PENDING
        )  # Возвращаем в pending для обработки

        await storage.set_task_config(interrupted_task)
        logger.info(
            f"🔄 Задача {interrupted_task.task_id} обновлена и сохранена в pending"
        )
        task_id = interrupted_task.task_id

        logger.info(f"📋 Продолжаем прерванную задачу {task_id} для флоу {flow_id}")
    else:
        # Создаем новую задачу как обычно
        task_id = await api_interface.create_task(message, flow_id)

    logger.info(f"📋 Создана API задача {task_id} для флоу {flow_id}")

    return FlowMessageResponse(
        task_id=task_id,
        session_id=message.session_id,
        status="pending",
        message="Сообщение принято в обработку",
    )


@router.get("/{flow_id}/task/{task_id}", response_model=TaskResponse)
async def get_task_result(flow_id: str, task_id: str):
    """
    Получает результат выполнения задачи (polling).

    Args:
        flow_id: ID флоу
        task_id: ID задачи

    Returns:
        Результат задачи
    """
    try:
        storage = Storage()

        # Получаем задачу
        task_data = await storage.get(f"task:{task_id}")
        if not task_data:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        task_info = json.loads(task_data)

        # Логируем что читаем из БД
        logger.info(
            f"🔍 API читает задачу {task_id}: статус={task_info.get('status')}, output_data={bool(task_info.get('output_data'))}"
        )
        if task_info.get("output_data"):
            output = task_info["output_data"]
            logger.info(
                f"🔍 Output data: статус={output.get('status')}, вопрос_длина={len(output.get('question', ''))}"
            )

        # Проверяем что задача относится к правильному флоу
        if task_info.get("flow_id") != flow_id:
            raise HTTPException(
                status_code=404, detail="Задача не найдена для этого флоу"
            )

        # Формируем ответ
        response = TaskResponse(
            task_id=task_id,
            status=task_info.get("status", "unknown"),
            session_id=task_info.get("session_id", ""),
            created_at=task_info.get("created_at"),
            completed_at=task_info.get("completed_at"),
            error_message=task_info.get("error_message"),
        )

        # Добавляем результат если задача завершена или ждет ввода
        if task_info.get("output_data"):
            response.result = task_info["output_data"]

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения задачи {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{flow_id}/session/{session_id}/history")
async def get_session_history(flow_id: str, session_id: str, limit: int = 50):
    """
    Получает историю сессии.

    Args:
        flow_id: ID флоу
        session_id: ID сессии
        limit: Максимальное количество сообщений

    Returns:
        История сессии
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


@router.delete("/{flow_id}/session/{session_id}")
async def clear_session(flow_id: str, session_id: str):
    """
    Очищает сессию.

    Args:
        flow_id: ID флоу
        session_id: ID сессии

    Returns:
        Результат операции
    """
    try:
        # Деактивируем сессию
        storage = Storage()

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


@router.get("/{flow_id}/info")
async def get_flow_info(flow_id: str):
    """
    Получает информацию о флоу.

    Args:
        flow_id: ID флоу

    Returns:
        Информация о флоу
    """
    try:
        storage = Storage()
        flow_config = await storage.get_flow_config(flow_id)

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


@router.get("/")
async def list_flows():
    """
    Получает список всех флоу с поддержкой API.

    Returns:
        Список флоу
    """
    try:
        storage = Storage()

        # Получаем все флоу (это может быть медленно для большого количества)
        # В реальности лучше сделать отдельный метод в Storage
        flows = []

        # Пока простая реализация - в будущем можно оптимизировать
        test_flows = ["test_flow", "smart_flow", "weather_flow"]

        for flow_id in test_flows:
            flow_config = await storage.get_flow_config(flow_id)
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
