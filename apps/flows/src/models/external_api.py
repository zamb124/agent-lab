"""
Модель ExternalAPIConfig - конфигурация вызова внешнего HTTP API.

Используется и как нода агента, и как tool для react агентов.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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


class ParameterLocation(str, Enum):
    """Расположение параметра в запросе"""

    QUERY = "query"
    PATH = "path"
    HEADER = "header"
    BODY = "body"


class ParameterSchema(BaseModel):
    """Схема параметра (OpenAPI-like)"""

    name: str = Field(..., description="Имя параметра")
    source: Optional[str] = Field(
        default=None,
        description="Источник значения (@state:user.profile.name). Если указан - берёт из state по пути",
    )
    location: ParameterLocation = Field(default=ParameterLocation.BODY, description="Расположение")
    type: str = Field(
        default="string", description="Тип: string, integer, number, boolean, object, array"
    )
    description: Optional[str] = Field(default=None, description="Описание параметра")
    required: bool = Field(default=False, description="Обязательный параметр")
    default: Optional[Any] = Field(
        default=None, description="Значение по умолчанию (поддерживает @var:)"
    )


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

    Поддерживает @var: переменные в url, headers, auth_headers и default значениях параметров.
    """

    api_id: str = Field(..., description="Уникальный идентификатор")
    name: str = Field(..., description="Название API")
    description: Optional[str] = Field(default=None, description="Описание")

    url: str = Field(..., description="URL endpoint (поддерживает @var: и {path_params})")
    method: HTTPMethod = Field(default=HTTPMethod.POST, description="HTTP метод")

    headers: Dict[str, str] = Field(
        default_factory=dict, description="HTTP заголовки (поддерживают @var:)"
    )
    auth_headers: Dict[str, str] = Field(
        default_factory=dict, description="Заголовки авторизации (поддерживают @var:)"
    )

    parameters: List[ParameterSchema] = Field(
        default_factory=list, description="Параметры запроса (OpenAPI-like)"
    )

    request_content_type: str = Field(
        default="application/json", description="Content-Type запроса"
    )
    response_type: ResponseType = Field(default=ResponseType.JSON, description="Тип ответа")
    response_schema: ResponseSchema = Field(
        default_factory=ResponseSchema, description="Схема ответа"
    )

    timeout: float = Field(default=30.0, description="Таймаут запроса в секундах")

    state_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Маппинг полей ответа на state: {response_field: state_field}",
    )

    def get_openapi_parameters(self) -> Dict[str, Any]:
        """Возвращает параметры в формате для LLM tools."""
        properties = {}
        required = []

        for param in self.parameters:
            prop = {
                "type": param.type,
            }
            if param.description:
                prop["description"] = param.description

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
