"""
API для работы с тулами в Builder.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
import inspect
import json

from app.tools import ALL_TOOLS
from app.core.storage import Storage
from app.core.container import get_container

router = APIRouter(prefix="/tools", tags=["builder-tools"])


async def get_storage() -> Storage:
    """Получить Storage из контейнера"""
    container = get_container()
    return container.get_storage()


@router.get("/")
async def list_tools(storage: Storage = Depends(get_storage)) -> List[Dict[str, Any]]:
    """Получить список всех доступных тулов"""
    tools_data = []
    
    # Получаем тулы из БД
    tool_keys = await storage.list_by_prefix("tool:")
    
    for key in tool_keys:
        # Извлекаем tool_id из ключа (убираем префикс компании и "tool:")
        # Формат ключа: company:system:tool:app.tools.voice_tools.get_audio_transcript
        tool_prefix_index = key.find(":tool:")
        if tool_prefix_index != -1:
            tool_id = key[tool_prefix_index + 6:]  # +6 для ":tool:"
        else:
            print(f"Неожиданный формат ключа тула: {key}")
            continue
        
        try:
            # Получаем данные тула из БД (используем полный ключ)
            tool_data_json = await storage.get(key)
            if tool_data_json:
                # Парсим JSON, который уже возвращается методом get
                if isinstance(tool_data_json, str):
                    tool_data = json.loads(tool_data_json)
                else:
                    tool_data = tool_data_json
                
                tool_info = {
                    "id": tool_id,
                    "name": tool_data.get("tool_id", tool_id).split(".")[-1],  # Берем имя функции
                    "description": tool_data.get("description", ""),
                    "type": "tool",
                    "category": _get_tool_category_from_path(tool_id),
                    "parameters": tool_data.get("params", {}),
                    "cost": tool_data.get("cost", 0.0),
                    "source_path": tool_id
                }
                tools_data.append(tool_info)
                
        except Exception as e:
            print(f"Ошибка обработки тула {tool_id}: {e}")
            continue
    
    # Также добавляем тулы из кода (для совместимости)
    for tool in ALL_TOOLS:
        # Проверяем, что тул еще не добавлен из БД
        if not any(t["name"] == tool.name for t in tools_data):
            tool_info = {
                "id": tool.name,
                "name": tool.name,
                "description": tool.description,
                "type": "tool",
                "category": _get_tool_category(tool),
                "parameters": _get_tool_parameters(tool),
                "cost": 0.0,
                "source_path": f"code.{tool.name}"
            }
            tools_data.append(tool_info)
    
    return tools_data


@router.get("/{tool_id:path}")
async def get_tool(tool_id: str, storage: Storage = Depends(get_storage)) -> Dict[str, Any]:
    """Получить информацию о конкретном туле"""
    
    # Сначала пытаемся найти в БД по полному пути
    try:
        # Ищем среди всех ключей тулов
        tool_keys = await storage.list_by_prefix("tool:")
        matching_key = None
        
        for key in tool_keys:
            if key.endswith(f":{tool_id}"):
                matching_key = key
                break
        
        if matching_key:
            tool_data_json = await storage.get(matching_key)
            if tool_data_json:
                # Парсим JSON, который уже возвращается методом get
                if isinstance(tool_data_json, str):
                    tool_data = json.loads(tool_data_json)
                else:
                    tool_data = tool_data_json
            
                return {
                    "id": tool_id,
                    "name": tool_data.get("tool_id", tool_id).split(".")[-1],
                    "description": tool_data.get("description", ""),
                    "type": "tool",
                    "category": _get_tool_category_from_path(tool_id),
                    "parameters": tool_data.get("params", {}),
                    "cost": tool_data.get("cost", 0.0),
                    "source_path": tool_id
                }
        
    except Exception as e:
        print(f"Ошибка получения тула из БД {tool_id}: {e}")
    
    # Если не найден в БД, ищем в коде
    tool = _find_tool_by_id(tool_id)
    if tool:
        return {
            "id": tool.name,
            "name": tool.name,
            "description": tool.description,
            "type": "tool",
            "category": _get_tool_category(tool),
            "parameters": _get_tool_parameters(tool),
            "cost": 0.0,
            "source_path": f"code.{tool.name}"
        }
    
    raise HTTPException(status_code=404, detail="Tool not found")


def _find_tool_by_id(tool_id: str):
    """Найти тул по ID"""
    for tool in ALL_TOOLS:
        if tool.name == tool_id:
            return tool
    return None


def _get_tool_category(tool) -> str:
    """Определить категорию тула по модулю"""
    if hasattr(tool, 'func') and hasattr(tool.func, '__module__'):
        module = tool.func.__module__
        return _get_category_from_module_path(module)
    return "other"


def _get_tool_category_from_path(tool_path: str) -> str:
    """Определить категорию тула по пути"""
    return _get_category_from_module_path(tool_path)


def _get_category_from_module_path(module_path: str) -> str:
    """Определить категорию по пути модуля"""
    if 'calc_tools' in module_path:
        return "calculator"
    elif 'weather_tools' in module_path:
        return "weather"
    elif 'file_tools' in module_path:
        return "files"
    elif 'fashn_tools' in module_path:
        return "fashn"
    elif 'nano_banana_tools' in module_path:
        return "image_generation"
    elif 'voice_tools' in module_path:
        return "voice"
    elif 'standard' in module_path:
        return "standard"
    return "other"


def _get_tool_parameters(tool) -> Dict[str, Any]:
    """Получить параметры тула"""
    if hasattr(tool, 'args_schema') and tool.args_schema:
        schema = tool.args_schema.schema()
        return {
            "properties": schema.get("properties", {}),
            "required": schema.get("required", [])
        }
    
    # Если нет схемы, пытаемся получить из сигнатуры функции
    if hasattr(tool, 'func'):
        try:
            sig = inspect.signature(tool.func)
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param_name in ['self', 'cls']:
                    continue
                    
                param_info = {
                    "type": "string"  # По умолчанию строка
                }
                
                if param.annotation != inspect.Parameter.empty:
                    if param.annotation == int:
                        param_info["type"] = "integer"
                    elif param.annotation == float:
                        param_info["type"] = "number"
                    elif param.annotation == bool:
                        param_info["type"] = "boolean"
                    elif hasattr(param.annotation, '__origin__') and param.annotation.__origin__ == list:
                        param_info["type"] = "array"
                
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
                else:
                    param_info["default"] = param.default
                
                properties[param_name] = param_info
            
            return {
                "properties": properties,
                "required": required
            }
        except Exception:
            pass
    
    return {"properties": {}, "required": []}
