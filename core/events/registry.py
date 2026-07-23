"""In-process реестр типов событий платформы (без Redis).

`notify/<service>/<kind>_received` — единственное динамическое семейство:
публикуется без предварительной регистрации. Все остальные типы обязаны
пройти `register_platform_event` до `publish_event`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.events.contract import assert_platform_event_type
from core.types import JsonObject

_NOTIFY_PREFIX = "notify/"

_registry_models: dict[str, type[BaseModel]] = {}
_registry_descriptions: dict[str, str] = {}


class PlatformEventCatalogEntry(BaseModel):
    """Запись каталога: тип события + JSON Schema payload."""

    event_type: str
    description: str
    payload_schema: JsonObject = Field(default_factory=dict)


def _model_ref(payload_model: type[BaseModel]) -> str:
    return f"{payload_model.__module__}.{payload_model.__qualname__}"


def is_dynamic_notify_event_type(event_type: str) -> bool:
    """Семейство toast/notification-center вне каталога триггеров."""
    return event_type.startswith(_NOTIFY_PREFIX)


def register_platform_event(
    event_type: str,
    payload_model: type[BaseModel],
    *,
    description: str,
) -> None:
    """Зарегистрировать тип события с контрактом payload."""
    _ = assert_platform_event_type(event_type)
    if is_dynamic_notify_event_type(event_type):
        raise ValueError(
            f"platform event {event_type!r}: notify/* is dynamic and must not be registered"
        )
    if not description:
        raise ValueError(f"platform event {event_type!r}: description is required")
    existing = _registry_models.get(event_type)
    if existing is not None:
        if existing is payload_model:
            return
        message = (
            f"platform event {event_type!r} already registered with model "
            + f"{_model_ref(existing)!r}; conflicting model {_model_ref(payload_model)!r}"
        )
        raise ValueError(message)
    _registry_models[event_type] = payload_model
    _registry_descriptions[event_type] = description


def registered_platform_event_types() -> list[str]:
    """Отсортированный список зарегистрированных типов."""
    return sorted(_registry_models)


def platform_event_payload_model(event_type: str) -> type[BaseModel]:
    """Модель payload зарегистрированного типа; неизвестный тип — ошибка."""
    payload_model = _registry_models.get(event_type)
    if payload_model is None:
        raise KeyError(f"platform event {event_type!r} is not registered in catalog")
    return payload_model


def is_registered_platform_event(event_type: str) -> bool:
    return event_type in _registry_models


def assert_publishable_platform_event_type(event_type: str) -> str:
    """Zero-Guess: publish только зарегистрированных типов или notify/*."""
    _ = assert_platform_event_type(event_type)
    if is_dynamic_notify_event_type(event_type):
        return event_type
    if not is_registered_platform_event(event_type):
        raise ValueError(
            f"platform event {event_type!r} is not registered in catalog; "
            + "call register_platform_event before publish"
        )
    return event_type


def platform_event_catalog() -> list[PlatformEventCatalogEntry]:
    """Каталог типов, зарегистрированных в текущем процессе."""
    entries: list[PlatformEventCatalogEntry] = []
    for event_type in registered_platform_event_types():
        payload_model = _registry_models[event_type]
        entries.append(
            PlatformEventCatalogEntry(
                event_type=event_type,
                description=_registry_descriptions[event_type],
                payload_schema=payload_model.model_json_schema(),
            )
        )
    return entries
