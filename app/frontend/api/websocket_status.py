"""
API для мониторинга статуса WebSocket соединений
"""

from fastapi import APIRouter
from typing import Dict, Any

from app.frontend.core.websocket_manager import websocket_manager

router = APIRouter(prefix="/api/websocket", tags=["WebSocket Status"])


@router.get("/status")
async def get_websocket_status() -> Dict[str, Any]:
    """Получить общий статус всех WebSocket соединений"""
    
    status = {
        "connections": {},
        "polling_tasks": {},
        "summary": {
            "total_connections": 0,
            "total_polling_tasks": 0,
            "active_polling_tasks": 0,
            "failed_polling_tasks": 0
        }
    }
    
    for conn_type, connections in websocket_manager.connections.items():
        status["connections"][conn_type] = {
            "count": len(connections),
            "session_ids": list(connections.keys())
        }
        status["summary"]["total_connections"] += len(connections)
    
    for polling_key, task in websocket_manager.polling_tasks.items():
        task_status = "running"
        error = None
        
        if task.done():
            if task.cancelled():
                task_status = "cancelled"
            elif task.exception():
                task_status = "error"
                error = str(task.exception())
            else:
                task_status = "completed"
        else:
            status["summary"]["active_polling_tasks"] += 1
        
        if task_status == "error":
            status["summary"]["failed_polling_tasks"] += 1
        
        status["polling_tasks"][polling_key] = {
            "status": task_status,
            "error": error
        }
        status["summary"]["total_polling_tasks"] += 1
    
    return status


@router.get("/status/{session_id}")
async def get_session_status(session_id: str, connection_type: str = "chat") -> Dict[str, Any]:
    """Получить статус конкретной сессии"""
    
    return websocket_manager.get_polling_status(session_id, connection_type)

