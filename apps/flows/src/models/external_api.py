"""
Модель ExternalAPIConfig - конфигурация вызова внешнего HTTP API.

Используется и как нода агента, и как tool для react агентов.
"""

import json
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator


class HTTPMethod(str, Enum):
    """HTTP методы"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ResponseType(str, Enum):
    """Тип ответа"""

    JSON = "json"
    TEXT = "text"


class ResponseStatus(str, Enum):
    """Статус ответа от внешнего API"""

    COMPLETED = "completed"
    WAITING_INPUT = "waiting_input"
    ERROR = "error"


class ResponseSchema(BaseModel):
    """Схема ответа"""

    status_field: str = Field(
        default="status", description="Поле со статусом (completed/waiting_input)"
    )
    data_field: str = Field(default="data", description="Поле с данными")
    interrupt_field: str = Field(default="interrupt", description="Поле с данными interrupt")
    error_field: str = Field(default="error", description="Поле с ошибкой")


class ExternalAPIConfig(BaseModel):
    """
    Конфигурация вызова внешнего HTTP API.

    Поддерживает @var: / @state: в url и headers; JSON body_template;
    ключи входа подставляются в {placeholder} URL и мержятся в тело после шаблона.
    """

    api_id: str = Field(..., description="Уникальный идентификатор")
    name: str = Field(..., description="Название API")
    description: Optional[str] = Field(default=None, description="Описание")

    url: str = Field(..., description="URL endpoint (поддерживает @var: и {path_params})")
    method: HTTPMethod = Field(default=HTTPMethod.POST, description="HTTP метод")

    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="HTTP заголовки (строки: @state:path, @var:path, токены @var: в тексте)",
    )

    request_content_type: str = Field(
        default="application/json", description="Content-Type запроса"
    )
    response_type: ResponseType = Field(default=ResponseType.JSON, description="Тип ответа")
    response_schema: ResponseSchema = Field(
        default_factory=ResponseSchema, description="Схема ответа"
    )

    timeout: float = Field(default=30.0, description="Таймаут запроса в секундах")

    body_template: str = Field(
        default="{}",
        description='JSON-тело запроса; в строках допускаются целые @state:path, @var:path и токены @var: в тексте',
    )

    state_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Маппинг полей ответа на state: {response_field: state_field}",
    )

    @model_validator(mode="after")
    def _body_template_is_json_object(self) -> "ExternalAPIConfig":
        raw = self.body_template.strip() if isinstance(self.body_template, str) else ""
        if not raw:
            return self
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError("body_template must be valid JSON") from e
        if not isinstance(parsed, dict):
            raise ValueError("body_template JSON must be an object at the root")
        return self
