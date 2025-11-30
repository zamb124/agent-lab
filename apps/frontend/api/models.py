"""
API для работы с моделями через HTMX + JSON.

Использует репозитории для работы с данными.
"""

import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from typing import Dict, Any

from apps.frontend.wrappers import ModelListWrapper
from apps.frontend.model_registry import ModelRegistry
from apps.frontend.core.template_loader import render_template, get_templates
from apps.frontend.websockets.notifications import notify_model_updated
from apps.frontend.core.utils import is_htmx_request
from apps.frontend.container import get_frontend_container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/frontend/models", tags=["frontend"])
templates = get_templates()


def _serialize_field_value(field_value: Any) -> str:
    """Сериализовать значение поля в JSON для отображения"""
    if hasattr(field_value, 'model_dump'):
        return json.dumps(field_value.model_dump(), indent=2, ensure_ascii=False)
    
    if isinstance(field_value, list) and field_value and hasattr(field_value[0], 'model_dump'):
        return json.dumps([item.model_dump() for item in field_value], indent=2, ensure_ascii=False)
    
    return json.dumps(field_value, indent=2, ensure_ascii=False)


@router.post("/show-inline-modal")
async def show_inline_modal(request_data: Dict[str, Any]) -> HTMLResponse:
    """Показать вложенную модель в модальном окне"""
    field_name = request_data.get("field_name", "unknown")
    parent_model_type = request_data.get("parent_model_type", "unknown")
    parent_model_id = request_data.get("parent_model_id", "unknown")

    container = get_frontend_container()
    repo = container.get_repository_by_model_type(parent_model_type)
    parent_model = await repo.get(parent_model_id)
    
    if not parent_model:
        raise HTTPException(status_code=404, detail=f"Parent model {parent_model_id} not found")

    field_value = getattr(parent_model, field_name, None)
    formatted_json = _serialize_field_value(field_value)

    content = render_template(
        "modals/inline_edit.html",
        field_name=field_name,
        parent_model_type=parent_model_type,
        parent_model_id=parent_model_id,
        formatted_json=formatted_json,
    )

    html = render_template(
        "modals/modal.html",
        model_type=f"{parent_model_type}.{field_name}",
        model_id="inline",
        content=content,
    )

    return HTMLResponse(content=html)


@router.get("/{model_type}/{model_id:path}")
async def get_model(
    model_type: str, model_id: str, view: str = "table", parent_view_mode: str = None
) -> HTMLResponse:
    """Получить конкретную модель как HTML"""
    
    if model_id == "new":
        ModelClass = ModelRegistry.get_model_class(model_type)
        model = ModelClass()

        if model_type == "create_company_form":
            html = f"""
            <form hx-post="/frontend/admin/create-my-company"
                  hx-ext="json-enc"
                  hx-trigger="submit"
                  class="space-y-6">
                {model.render(view_mode="form")}

                <div class="mt-6">
                    <button type="submit"
                            class="w-full bg-primary-600 hover:bg-primary-700 text-white font-semibold py-3 px-6 rounded-lg
                                   transition-colors duration-200 focus:ring-2 focus:ring-primary-500 focus:ring-offset-2
                                   disabled:opacity-50 disabled:cursor-not-allowed">
                        <span class="htmx-indicator hidden">
                            <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Создание...
                        </span>
                        <span class="htmx-indicator-hidden">
                            Создать компанию
                        </span>
                    </button>
                </div>
            </form>
            """
            return HTMLResponse(content=html)

        kwargs = {"model_type": model_type, "model_id": "new"}
        if parent_view_mode:
            kwargs["parent_view_mode"] = parent_view_mode

        html = model.render(view_mode=view, **kwargs)
        return HTMLResponse(content=html)

    container = get_frontend_container()
    repo = container.get_repository_by_model_type(model_type)
    model = await repo.get(model_id)

    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    kwargs = {"model_type": model_type, "model_id": model_id}
    if parent_view_mode:
        kwargs["parent_view_mode"] = parent_view_mode

    html = model.render(view_mode=view, **kwargs)
    return HTMLResponse(content=html)


@router.get("/{model_type}")
async def get_models(request: Request, model_type: str, view: str = "table") -> HTMLResponse:
    """Получить список моделей в указанном виде"""

    if not is_htmx_request(request):
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "preload_url": f"/frontend/models/{model_type}?view={view}",
            }
        )

    container = get_frontend_container()
    repo = container.get_repository_by_model_type(model_type)
    models = await repo.list_all(limit=1000)

    wrapper = ModelListWrapper(models=models, count=len(models), model_type=model_type)
    html = wrapper.render(view_mode=view, model_type=model_type)
    return HTMLResponse(content=html)


@router.post("/{model_type}")
async def create_model(model_type: str, model_data: Dict[str, Any]) -> HTMLResponse:
    """Создать новую модель и вернуть HTML"""
    ModelClass = ModelRegistry.get_model_class(model_type)
    model = ModelClass(**model_data)

    container = get_frontend_container()
    repo = container.get_repository_by_model_type(model_type)
    await repo.set(model)

    html = model.render()
    return HTMLResponse(content=html)


@router.put("/{model_type}/{model_id:path}")
async def update_model(
    model_type: str, model_id: str, model_data: Dict[str, Any], view: str = "form"
) -> Dict[str, Any]:
    """Обновить модель"""
    container = get_frontend_container()
    repo = container.get_repository_by_model_type(model_type)
    
    existing_model = await repo.get(model_id)
    if not existing_model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    existing_data = existing_model.model_dump()
    
    ModelClass = ModelRegistry.get_model_class(model_type)
    
    for field_name, field_value in model_data.items():
        if field_name not in ModelClass.model_fields:
            existing_data[field_name] = field_value
            continue
            
        field_info = ModelClass.model_fields[field_name]
        
        if field_info.frozen:
            continue

        parsed_value = _parse_field_value(field_value, field_info.annotation)
        existing_data[field_name] = parsed_value

    model = ModelClass(**existing_data)
    await repo.set(model)

    await notify_model_updated(model_type, model_id)

    return {"success": True, "message": "Модель обновлена"}


@router.delete("/{model_type}/{model_id:path}")
async def delete_model(model_type: str, model_id: str) -> Dict[str, Any]:
    """Удалить модель"""
    container = get_frontend_container()
    repo = container.get_repository_by_model_type(model_type)
    
    existing_model = await repo.get(model_id)
    if not existing_model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    await repo.delete(model_id)

    return {"deleted": True, "id": model_id}


def _parse_field_value(field_value: Any, annotation: Any) -> Any:
    """Парсинг значения поля с учетом типа аннотации"""
    from typing import get_origin, get_args, Union, Optional
    from datetime import datetime
    from pydantic import BaseModel
    import inspect
    
    if get_origin(annotation) is Union:
        args = get_args(annotation)
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            annotation = non_none_args[0]

    if not isinstance(field_value, str):
        return field_value

    if field_value == "":
        if annotation in [datetime, Optional[datetime], int, Optional[int], float, Optional[float]]:
            return None
        return field_value

    if get_origin(annotation) is dict or annotation is dict:
        return _parse_json_value(field_value, {})
    
    if get_origin(annotation) is list or annotation is list:
        return _parse_json_value(field_value, [])
    
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return _parse_json_value(field_value, field_value)
    
    if hasattr(annotation, '__origin__') and annotation.__origin__ is list:
        args = getattr(annotation, '__args__', ())
        if args and inspect.isclass(args[0]) and issubclass(args[0], BaseModel):
            return _parse_json_value(field_value, field_value)
    
    return field_value


def _parse_json_value(value: str, default: Any) -> Any:
    """Парсинг JSON значения с поддержкой одинарных кавычек"""
    if not value:
        return default
        
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        try:
            fixed_value = value.replace("'", '"')
            return json.loads(fixed_value)
        except json.JSONDecodeError:
            return value
