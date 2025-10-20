"""
Простое API для работы с моделями через HTMX + JSON
"""

import json
import uuid
import logging
import inspect
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from typing import Dict, Any, get_origin, get_args, Union, Optional
from pydantic import BaseModel
from app.db.repositories import Storage
from app.frontend.wrappers import ModelListWrapper
from app.frontend.model_registry import ModelRegistry
from app.frontend.core.template_loader import render_template, get_templates
from app.frontend.websockets.notifications import notify_model_updated
from app.frontend.core.utils import is_htmx_request

# ПРИНУДИТЕЛЬНЫЙ импорт field_extensions для применения monkey patches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/frontend/models", tags=["frontend"])
templates = get_templates()


@router.post("/show-inline-modal")
async def show_inline_modal(request_data: Dict[str, Any]) -> HTMLResponse:
    """Показать вложенную модель в модальном окне"""
    # Получаем данные
    field_name = request_data.get("field_name", "unknown")
    parent_model_type = request_data.get("parent_model_type", "unknown")
    parent_model_id = request_data.get("parent_model_id", "unknown")

    # Загружаем родительскую модель из storage
    storage = Storage()
    key = f"{parent_model_type}:{parent_model_id}"
    data = await storage.get(key)

    if not data:
        raise HTTPException(status_code=404, detail=f"Parent model {parent_model_id} not found")

    # Получаем класс модели из registry
    ModelClass = ModelRegistry.get_model_class(parent_model_type)

    # Парсим данные
    if isinstance(data, str):
        model_data = json.loads(data)
    else:
        model_data = data

    # Создаем модель
    model = ModelClass(**model_data)

    # Получаем значение поля
    field_value = getattr(model, field_name, None)

    # Сериализуем значение поля в JSON
    try:
        if hasattr(field_value, 'model_dump'):
            # Для BaseModel объектов используем model_dump
            formatted_json = json.dumps(field_value.model_dump(), indent=2, ensure_ascii=False)
        elif isinstance(field_value, list) and field_value and hasattr(field_value[0], 'model_dump'):
            # Для списков BaseModel объектов
            formatted_json = json.dumps([item.model_dump() for item in field_value], indent=2, ensure_ascii=False)
        else:
            # Для обычных значений
            formatted_json = json.dumps(field_value, indent=2, ensure_ascii=False)
    except (TypeError, AttributeError):
        # Если не удается сериализовать, показываем строковое представление
        formatted_json = str(field_value)

    # Рендерим форму через шаблон
    content = render_template(
        "modals/inline_edit.html",
        field_name=field_name,
        parent_model_type=parent_model_type,
        parent_model_id=parent_model_id,
        formatted_json=formatted_json,
    )

    # Оборачиваем в модальное окно
    html = render_template(
        "modals/modal.html",
        model_type=f"{parent_model_type}.{field_name}",
        model_id="inline",
        content=content,
    )

    return HTMLResponse(content=html)


@router.get("/{model_type}")
async def get_models(request: Request, model_type: str, view: str = "table") -> HTMLResponse:
    """Получить список моделей в указанном виде"""

    # При прямом переходе (не HTMX) возвращаем dashboard с preload_url
    if not is_htmx_request(request):
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "preload_url": f"/frontend/models/{model_type}?view={view}",
            }
        )

    # При HTMX запросе возвращаем фрагмент
    storage = Storage()

    # Получаем все модели данного типа (Storage автоматически добавит префикс компании)
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
        model = ModelClass(**model_data)
        models.append(model)

    # Создаем wrapper с конкретными моделями
    wrapper = ModelListWrapper(models=models, count=len(models), model_type=model_type)

    html = wrapper.render(view_mode=view, model_type=model_type)
    return HTMLResponse(content=html)


@router.get("/{model_type}/{model_id}")
async def get_model(
    model_type: str, model_id: str, view: str = "table", parent_view_mode: str = None
) -> HTMLResponse:
    """Получить конкретную модель как HTML"""

    # Специальный случай: создание новой модели
    if model_id == "new":
        ModelClass = ModelRegistry.get_model_class(model_type)

        # Создаем пустую модель с дефолтными значениями
        model = ModelClass()

        # Для формы создания компании добавляем HTMX атрибуты
        if model_type == "create_company_form":
            # Рендерим только форму с HTMX атрибутами
            html = f"""
            <form hx-post="/api/v1/admin/create-my-company"
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

        # Для остальных моделей - обычный рендер
        kwargs = {"model_type": model_type, "model_id": "new"}
        if parent_view_mode:
            kwargs["parent_view_mode"] = parent_view_mode

        html = model.render(view_mode=view, **kwargs)
        return HTMLResponse(content=html)

    # Обычный случай: загрузка существующей модели
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
    kwargs = {"model_type": model_type, "model_id": model_id}
    if parent_view_mode:
        kwargs["parent_view_mode"] = parent_view_mode

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
async def update_model(
    model_type: str, model_id: str, model_data: Dict[str, Any], view: str = "form"
) -> HTMLResponse:
    """Обновить модель и вернуть обновленную строку таблицы"""
    storage = Storage()
    key = f"{model_type}:{model_id}"

    # Получаем существующие данные
    existing_data = await storage.get(key)
    if not existing_data:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    # Парсим существующие данные
    if isinstance(existing_data, str):
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

            # Пропускаем frozen поля (они неизменяемы)
            if field_info.frozen:
                continue

            annotation = field_info.annotation

            # Убираем Optional
            if get_origin(annotation) is Union:
                args = get_args(annotation)
                non_none_args = [arg for arg in args if arg is not type(None)]
                if len(non_none_args) == 1:
                    annotation = non_none_args[0]

            # Если BaseModel поле и строка - парсим JSON
            try:
                if isinstance(field_value, str):
                    # Пустая строка = None для Optional полей
                    if field_value == "":
                        # Для datetime, int, float полей пустая строка = None
                        if annotation in [datetime, Optional[datetime], int, Optional[int], float, Optional[float]]:
                            existing_model_data[field_name] = None
                            continue
                    # Пустая строка или JSON для dict
                    elif field_value == "{}" or (get_origin(annotation) is dict or annotation is dict):
                        if field_value:
                            # Обрабатываем как одинарные, так и двойные кавычки
                            try:
                                # Сначала пробуем стандартный JSON
                                parsed_value = json.loads(field_value)
                            except json.JSONDecodeError:
                                # Если не получилось, пробуем заменить одинарные кавычки на двойные
                                try:
                                    fixed_value = field_value.replace("'", '"')
                                    parsed_value = json.loads(fixed_value)
                                except json.JSONDecodeError:
                                    # Если совсем не JSON, оставляем как есть
                                    parsed_value = field_value
                            existing_model_data[field_name] = parsed_value
                        else:
                            existing_model_data[field_name] = {}
                    # Пустая строка или JSON для list
                    elif field_value == "[]" or (get_origin(annotation) is list or annotation is list):
                        if field_value:
                            try:
                                # Сначала пробуем стандартный JSON
                                parsed_value = json.loads(field_value)
                            except json.JSONDecodeError:
                                # Если не получилось, пробуем заменить одинарные кавычки на двойные
                                try:
                                    fixed_value = field_value.replace("'", '"')
                                    parsed_value = json.loads(fixed_value)
                                except json.JSONDecodeError:
                                    # Если совсем не JSON, оставляем как есть
                                    parsed_value = field_value
                            existing_model_data[field_name] = parsed_value
                        else:
                            existing_model_data[field_name] = []
                    # Проверяем, является ли это BaseModel
                    elif inspect.isclass(annotation) and issubclass(annotation, BaseModel):
                        try:
                            parsed_value = json.loads(field_value)
                        except json.JSONDecodeError:
                            # Если не получилось, пробуем заменить одинарные кавычки на двойные
                            fixed_value = field_value.replace("'", '"')
                            parsed_value = json.loads(fixed_value)
                        existing_model_data[field_name] = parsed_value
                    # Проверяем, является ли это List[BaseModel]
                    elif (hasattr(annotation, '__origin__') and
                          annotation.__origin__ is list and
                          len(annotation.__args__) > 0 and
                          issubclass(annotation.__args__[0], BaseModel)):
                        try:
                            parsed_value = json.loads(field_value)
                        except json.JSONDecodeError:
                            # Если не получилось, пробуем заменить одинарные кавычки на двойные
                            fixed_value = field_value.replace("'", '"')
                            parsed_value = json.loads(fixed_value)
                        existing_model_data[field_name] = parsed_value
                    else:
                        existing_model_data[field_name] = field_value
                else:
                    existing_model_data[field_name] = field_value
            except (TypeError, ValueError, json.JSONDecodeError):
                existing_model_data[field_name] = field_value
        else:
            existing_model_data[field_name] = field_value

    # Валидируем через модель
    model = ModelClass(**existing_model_data)

    # Сохраняем валидированные данные как JSON
    await storage.set(key, model.model_dump_json())

    # Отправляем WebSocket уведомление об обновлении модели
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
