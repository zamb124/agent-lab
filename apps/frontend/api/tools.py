"""
API для работы с тулами в Builder.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
import inspect
import uuid

from apps.agents.models import CodeMode, ToolReference
from apps.agents.dependencies import ToolRepositoryDep


router = APIRouter(prefix="/tools", tags=["builder-tools"])


@router.get("/")
async def list_tools(
    tool_repo: ToolRepositoryDep,
    public_only: bool = False
) -> List[Dict[str, Any]]:
    """Получить список всех доступных тулов (оптимизировано)
    
    Args:
        public_only: Если True, возвращает только публичные тулы
    """
    all_tools = await tool_repo.list_all(limit=1000)
    
    tools_data = []
    for tool in all_tools:
        is_public = getattr(tool, "is_public", False)
        if public_only and not is_public:
            continue

        tool_info = {
            "id": tool.tool_id,
            "name": tool.tool_id.split(".")[-1],
            "title": tool.title or tool.tool_id.split(".")[-1],
            "description": tool.description or "",
            "group": tool.group,
            "server": tool.server,
            "type": "tool",
            "category": _get_tool_category_from_path(tool.tool_id),
            "code_mode": tool.code_mode.value,
            "parameters": tool.params,
            "cost": tool.cost,
            "is_public": is_public,
            "source_path": tool.tool_id
        }
        tools_data.append(tool_info)
    
    return tools_data


@router.post("/", response_model=ToolReference)
async def create_tool(
    tool_repo: ToolRepositoryDep,
    name: str = "Новый инструмент",
    description: Optional[str] = None,
    category: str = "general",
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
    
    await tool_repo.set(tool_ref)
    
    return tool_ref


@router.get("/{tool_id:path}")
async def get_tool(tool_id: str, tool_repo: ToolRepositoryDep) -> Dict[str, Any]:
    """Получить информацию о конкретном туле"""
    
    tool = await tool_repo.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    return {
        "id": tool.tool_id,
        "name": tool.tool_id.split(".")[-1],
        "title": tool.title or tool.tool_id.split(".")[-1],
        "description": tool.description or "",
        "group": tool.group,
        "server": tool.server,
        "type": "tool",
        "category": _get_tool_category_from_path(tool.tool_id),
        "code_mode": tool.code_mode.value,
        "parameters": tool.params,
        "cost": tool.cost,
        "is_public": getattr(tool, "is_public", False),
        "source_path": tool.tool_id
    }


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
