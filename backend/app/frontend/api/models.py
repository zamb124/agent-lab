"""
Простое API для работы с моделями через HTMX + JSON
"""
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from typing import Dict, Any
from pydantic import BaseModel
from app.core.storage import Storage
from app.frontend.wrappers import ModelListWrapper
from app.frontend.model_registry import ModelRegistry
import uuid
import json

router = APIRouter(prefix="/frontend/models", tags=["frontend"])


@router.post("/show-inline-modal")
async def show_inline_modal(request_data: Dict[str, Any]) -> HTMLResponse:
    """Показать вложенную модель в модальном окне"""
    # Получаем данные
    model_data_str = request_data.get("model_data", "{}")
    field_name = request_data.get("field_name", "unknown")
    parent_model_type = request_data.get("parent_model_type", "unknown")
    parent_model_id = request_data.get("parent_model_id", "unknown")
    
    # Парсим JSON строку в объект
    import json
    try:
        field_data = json.loads(model_data_str)
    except json.JSONDecodeError:
        field_data = {}
    
    # Передаем объект для форматирования в шаблоне
    formatted_json = field_data
    
    # Рендерим форму через шаблон
    from app.frontend.environment import render_template
    content = render_template("modals/inline_edit.html", 
                            field_name=field_name,
                            parent_model_type=parent_model_type,
                            parent_model_id=parent_model_id,
                            formatted_json=formatted_json)
    
    # Оборачиваем в модальное окно
    from app.frontend.environment import render_template
    html = render_template("modals/modal.html", 
                         model_type=f"{parent_model_type}.{field_name}",
                         model_id="inline",
                         content=content)
    
    return HTMLResponse(content=html)




@router.get("/{model_type}")
async def get_models(model_type: str, view: str = "table") -> HTMLResponse:
    """Получить список моделей в указанном виде"""
    storage = Storage()
    
    # Получаем все модели данного типа
    keys = await storage.list_by_prefix(f"{model_type}:")
    models_data = []
    
    for key in keys:
        data = await storage.get(key)
        if data:
            # Парсим JSON если это строка
            if isinstance(data, str):
                model_data = json.loads(data)
            else:
                model_data = data
            models_data.append(model_data)
    
    # Создаем конкретные модели из данных
    models = []
    ModelClass = ModelRegistry.get_model_class(model_type)
    
    for model_data in models_data:
        try:
            model = ModelClass(**model_data)
            models.append(model)
        except Exception:
            # Пропускаем невалидные модели
            continue
    
    # Создаем wrapper с конкретными моделями
    wrapper = ModelListWrapper(
        models=models,
        count=len(models),
        model_type=model_type
    )
    
    html = wrapper.render(view_mode=view, model_type=model_type)
    return HTMLResponse(content=html)


@router.get("/{model_type}/{model_id}")
async def get_model(model_type: str, model_id: str, view: str = "table", parent_view_mode: str = None) -> HTMLResponse:
    """Получить конкретную модель как HTML"""
    storage = Storage()
    key = f"{model_type}:{model_id}"
    data = await storage.get(key)
    
    if not data:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    # Получаем класс модели из registry
    ModelClass = ModelRegistry.get_model_class(model_type)
    
    # Парсим данные
    if isinstance(data, str):
        model_data = json.loads(data)
    else:
        model_data = data
    
    # Создаем модель и рендерим
    model = ModelClass(**model_data)
    
    # Передаем parent_view_mode если указан
    kwargs = {'model_type': model_type, 'model_id': model_id}
    if parent_view_mode:
        kwargs['parent_view_mode'] = parent_view_mode
        
    html = model.render(view_mode=view, **kwargs)
    
    return HTMLResponse(content=html)


@router.post("/{model_type}")
async def create_model(model_type: str, model_data: Dict[str, Any]) -> HTMLResponse:
    """Создать новую модель и вернуть HTML"""
    storage = Storage()
    
    # Генерируем ID если его нет
    model_id = model_data.get(f"{model_type}_id")
    if not model_id:
        model_id = f"{model_type}_{uuid.uuid4().hex[:8]}"
        model_data[f"{model_type}_id"] = model_id
    
    key = f"{model_type}:{model_id}"
    await storage.set(key, json.dumps(model_data))
    
    # Создаем модель и рендерим
    ModelClass = ModelRegistry.get_model_class(model_type)
    model = ModelClass(**model_data)
    html = model.render()
    
    return HTMLResponse(content=html)


@router.put("/{model_type}/{model_id}")
async def update_model(model_type: str, model_id: str, model_data: Dict[str, Any], view: str = "form") -> HTMLResponse:
    """Обновить модель и вернуть обновленную строку таблицы"""
    storage = Storage()
    key = f"{model_type}:{model_id}"
    
    # Получаем существующие данные
    existing_data = await storage.get(key)
    if not existing_data:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    # Парсим существующие данные
    if isinstance(existing_data, str):
        import json
        existing_model_data = json.loads(existing_data)
    else:
        existing_model_data = existing_data
    
    # Получаем класс модели для проверки типов полей
    ModelClass = ModelRegistry.get_model_class(model_type)
    
    # Обновляем поля с учетом их типов
    for field_name, field_value in model_data.items():
        # Если поле BaseModel и пришла строка - парсим
        if field_name in ModelClass.model_fields:
            field_info = ModelClass.model_fields[field_name]
            annotation = field_info.annotation
            
            # Убираем Optional
            from typing import get_origin, get_args, Union
            if get_origin(annotation) is Union:
                args = get_args(annotation)
                non_none_args = [arg for arg in args if arg is not type(None)]
                if len(non_none_args) == 1:
                    annotation = non_none_args[0]
            
            # Если BaseModel поле и строка - парсим
            try:
                from pydantic import BaseModel
                if issubclass(annotation, BaseModel) and isinstance(field_value, str):
                    import ast
                    parsed_value = ast.literal_eval(field_value)
                    existing_model_data[field_name] = parsed_value
                else:
                    existing_model_data[field_name] = field_value
            except (TypeError, ValueError, SyntaxError):
                existing_model_data[field_name] = field_value
        else:
            existing_model_data[field_name] = field_value
    
    # Валидируем через модель
    model = ModelClass(**existing_model_data)
    
    # Сохраняем валидированные данные как JSON
    await storage.set(key, model.model_dump_json())
    
    # Отправляем WebSocket уведомление об обновлении модели
    from .websocket import notify_model_updated
    await notify_model_updated(model_type, model_id)
    
    # Возвращаем просто 200 OK
    return {"success": True, "message": "Модель обновлена"}


@router.delete("/{model_type}/{model_id}")
async def delete_model(model_type: str, model_id: str) -> Dict[str, Any]:
    """Удалить модель"""
    storage = Storage()
    key = f"{model_type}:{model_id}"
    
    # Проверяем что модель существует
    existing_data = await storage.get(key)
    if not existing_data:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    # Удаляем
    await storage.delete(key)
    
    return {"deleted": True, "id": model_id}




