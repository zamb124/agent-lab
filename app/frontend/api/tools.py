"""
API для работы с тулами в Builder.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
import inspect
import json
import uuid

from app.models import ToolReference, CodeMode
from app.frontend.dependencies import StorageDep

router = APIRouter(prefix="/tools", tags=["builder-tools"])


@router.get("/")
async def list_tools(
    storage: StorageDep,
    public_only: bool = False
) -> List[Dict[str, Any]]:
    """Получить список всех доступных тулов
    
    Args:
        public_only: Если True, возвращает только публичные тулы (для редактора ботов)
    """
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
        

        # Получаем данные тула из БД (используем полный ключ)
        tool_data_json = await storage.get(key)
        if tool_data_json:
            # Парсим JSON, который уже возвращается методом get
            if isinstance(tool_data_json, str):
                tool_data = json.loads(tool_data_json)
            else:
                tool_data = tool_data_json
            
            # Фильтруем по публичности если нужно
            is_public = tool_data.get("is_public", False)
            if public_only and not is_public:
                continue


            tool_info = {
                "id": tool_id,
                "name": tool_data.get("tool_id", tool_id).split(".")[-1],
                "title": tool_data.get("title") or tool_data.get("tool_id", tool_id).split(".")[-1],
                "description": tool_data.get("description", ""),
                "group": tool_data.get("group"),  # Добавляем поле group
                "type": "tool",
                "category": _get_tool_category_from_path(tool_id),
                "parameters": tool_data.get("params", {}),
                "cost": tool_data.get("cost", 0.0),
                "is_public": is_public,
                "source_path": tool_id
            }
            tools_data.append(tool_info)
    
    return tools_data


@router.post("/", response_model=ToolReference)
async def create_tool(
    name: str = "Новый инструмент",
    description: Optional[str] = None,
    category: str = "general",
    storage: StorageDep = None
) -> ToolReference:
    """Создать новый инструмент и сразу сохранить в БД"""
    tool_id = f"tool_{uuid.uuid4().hex[:8]}"
    
    tool_ref = ToolReference(
        tool_id=tool_id,
        params={},
        code_mode=CodeMode.INLINE_CODE,
        function_path=None,
        inline_code="# Ваш код инструмента здесь\nasync def main():\n    return 'Результат'",
        description=description or "",
        cost=0.0,
        billing_name=None,
        free_for_plans=[],
        source="canvas_created"
    )
    
    # Сразу сохраняем в БД
    await storage.set(f"tool:{tool_id}", tool_ref.model_dump_json())
    
    return tool_ref


@router.get("/{tool_id:path}")
async def get_tool(tool_id: str, storage: StorageDep) -> Dict[str, Any]:
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
                    "title": tool_data.get("title") or tool_data.get("tool_id", tool_id).split(".")[-1],
                    "description": tool_data.get("description", ""),
                    "group": tool_data.get("group"),  # Добавляем поле group
                    "type": "tool",
                    "category": _get_tool_category_from_path(tool_id),
                    "parameters": tool_data.get("params", {}),
                    "cost": tool_data.get("cost", 0.0),
                    "source_path": tool_id
                }
        
    except Exception as e:
        print(f"Ошибка получения тула из БД {tool_id}: {e}")
    
    # Инструмент не найден в текущей компании
    raise HTTPException(status_code=404, detail="Tool not found")


# Вспомогательные функции для работы с инструментами из БД


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
