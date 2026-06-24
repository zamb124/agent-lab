"""
Mock Control System: детерминированные ответы для tools / nodes / flows / LLM,
управляемые через `metadata.__mock__` A2A-запроса.

Единый контракт: для любой сущности (tool, node, flow, llm) ответы задаются
СПИСКОМ (FIFO-очередь). Каждый вызов забирает следующий элемент списка.
Очереди и манифест живут в Redis со scope по `session_id`, поэтому работают
и на async-исполнении в worker, и переживают межпроцессную границу.

Источник правды о том, какие сущности замоканы — манифест в ключе
`mock_control:{session_id}:manifest`. Очереди ответов — отдельные ключи
`mock_control:{session_id}:{kind}:{entity_id}` (атомарный pop через Lua).
"""

from __future__ import annotations

import json
from typing import Final, final

from pydantic import Field, field_validator

from core.clients.llm.mock import (
    MockLLM,
    MockLLMQueuedResponse,
    pop_mock_array_response,
)
from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue

logger = get_logger(__name__)

MOCK_CONTROL_METADATA_KEY: Final[str] = "__mock__"
MOCK_GLOBAL_LLM_ID: Final[str] = "__global__"
_MOCK_CONTROL_TTL_SECONDS: Final[int] = 3600
_KEY_PREFIX: Final[str] = "mock_control"


class MockControlError(RuntimeError):
    """Mock Control включён, но запрошенная очередь пуста или недоступна."""


class MockControlPermissionError(RuntimeError):
    """Пользователь не входит ни в одну из permission_groups для mock."""


class MockControlConfig(StrictBaseModel):
    """
    Конфигурация mock из `metadata.__mock__`.

    Значение для каждой сущности — всегда список ответов (FIFO). Скаляр
    (`"calculator": "42"`) запрещён: Pydantic поднимет ошибку валидации.
    """

    enabled: bool = Field(default=False, description="Включает mock для всего run")
    permission_groups: list[str] = Field(
        default_factory=list,
        description="Группы, которым разрешён mock; пользователь должен входить хотя бы в одну",
    )
    tools: dict[str, list[MockLLMQueuedResponse]] = Field(
        default_factory=dict,
        description="Очередь ответов на каждый tool_id",
    )
    nodes: dict[str, list[MockLLMQueuedResponse]] = Field(
        default_factory=dict,
        description="Очередь ответов на каждую ноду графа (node_id); для llm_node — LLM-ответы",
    )
    flows: dict[str, list[MockLLMQueuedResponse]] = Field(
        default_factory=dict,
        description="Очередь результатов вложенного flow по flow_id",
    )
    llm: list[MockLLMQueuedResponse] = Field(
        default_factory=list,
        description="Общая очередь LLM-ответов для single-llm-node (react), если у ноды нет своей",
    )

    @field_validator("tools", "nodes", "flows")
    @classmethod
    def _reject_empty_entity_queues(
        cls, value: dict[str, list[MockLLMQueuedResponse]]
    ) -> dict[str, list[MockLLMQueuedResponse]]:
        for entity_id, queue in value.items():
            if not queue:
                raise ValueError(
                    f"mock entity {entity_id!r}: очередь ответов не может быть пустой"
                )
        return value


class MockControlManifest(StrictBaseModel):
    """Манифест активного mock: какие сущности замоканы и кому это разрешено."""

    permission_groups: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    flows: list[str] = Field(default_factory=list)
    has_global_llm: bool = Field(default=False)


def parse_mock_control_metadata(metadata: JsonObject) -> MockControlConfig | None:
    """Извлекает и валидирует `metadata.__mock__`. None — секции нет."""
    raw = metadata.get(MOCK_CONTROL_METADATA_KEY)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"metadata.{MOCK_CONTROL_METADATA_KEY} must be an object")
    return MockControlConfig.model_validate(raw)


def assert_mock_permission(user_groups: list[str], permission_groups: list[str]) -> None:
    """Проверяет право на mock. Без явных permission_groups mock запрещён."""
    if not permission_groups:
        raise MockControlPermissionError(
            "mock.permission_groups обязателен: mock доступен только привилегированным группам"
        )
    if not set(user_groups) & set(permission_groups):
        raise MockControlPermissionError(
            "Пользователь не входит ни в одну из mock.permission_groups: "
            + ", ".join(sorted(permission_groups))
        )


def _manifest_key(session_id: str) -> str:
    return f"{_KEY_PREFIX}:{session_id}:manifest"


def _queue_key(session_id: str, kind: str, entity_id: str) -> str:
    return f"{_KEY_PREFIX}:{session_id}:{kind}:{entity_id}"


async def setup_mock_control(
    redis_client: RedisClient,
    session_id: str,
    config: MockControlConfig,
    *,
    user_groups: list[str],
) -> None:
    """
    Записывает манифест и очереди ответов в Redis для текущего session_id.

    Вызывается из `process_task` до старта flow. Проверяет права. Если mock
    выключен — снимает ранее выставленный манифест (resume без mock).
    """
    if not config.enabled:
        _ = await redis_client.delete(_manifest_key(session_id))
        return

    assert_mock_permission(user_groups, config.permission_groups)

    for kind, entity_map in (
        ("tool", config.tools),
        ("node", config.nodes),
        ("flow", config.flows),
    ):
        for entity_id, queue in entity_map.items():
            _ = await redis_client.set(
                _queue_key(session_id, kind, entity_id),
                json.dumps(queue, ensure_ascii=False),
                ttl=_MOCK_CONTROL_TTL_SECONDS,
            )
    if config.llm:
        _ = await redis_client.set(
            _queue_key(session_id, "llm", MOCK_GLOBAL_LLM_ID),
            json.dumps(config.llm, ensure_ascii=False),
            ttl=_MOCK_CONTROL_TTL_SECONDS,
        )

    manifest = MockControlManifest(
        permission_groups=config.permission_groups,
        tools=list(config.tools.keys()),
        nodes=list(config.nodes.keys()),
        flows=list(config.flows.keys()),
        has_global_llm=bool(config.llm),
    )
    _ = await redis_client.set(
        _manifest_key(session_id),
        manifest.model_dump_json(),
        ttl=_MOCK_CONTROL_TTL_SECONDS,
    )
    logger.info(
        "mock_control.configured",
        session_id=session_id,
        tools=len(manifest.tools),
        nodes=len(manifest.nodes),
        flows=len(manifest.flows),
        has_global_llm=manifest.has_global_llm,
    )


async def get_mock_control_manifest(
    redis_client: RedisClient, session_id: str
) -> MockControlManifest | None:
    """Читает манифест активного mock. None — mock не активирован для session."""
    raw = await redis_client.get(_manifest_key(session_id))
    if raw is None:
        return None
    return MockControlManifest.model_validate_json(raw)


def build_node_mock_llm(
    redis_client: RedisClient, session_id: str, queue_kind: str, entity_id: str
) -> MockLLM:
    """MockLLM, читающий ответы строго из конкретной Redis-очереди (strict)."""
    mock_llm = MockLLM()
    _ = mock_llm.bind_redis_queue(
        redis_client,
        _queue_key(session_id, queue_kind, entity_id),
        strict=True,
    )
    return mock_llm


async def resolve_llm_node_mock(
    redis_client: RedisClient,
    session_id: str,
    node_id: str,
    *,
    manifest: MockControlManifest | None = None,
) -> MockLLM | None:
    """
    MockLLM для llm-ноды: своя очередь `nodes[node_id]`, иначе общая `llm[]`.

    Mock активен, но для ноды нет ни своей очереди, ни общей — fail-closed
    (`MockControlError`): иначе реальный LLM-вызов обошёл бы mock.
    """
    if manifest is None:
        manifest = await get_mock_control_manifest(redis_client, session_id)
    if manifest is None:
        return None
    if node_id in manifest.nodes:
        return build_node_mock_llm(redis_client, session_id, "node", node_id)
    if manifest.has_global_llm:
        return build_node_mock_llm(redis_client, session_id, "llm", MOCK_GLOBAL_LLM_ID)
    raise MockControlError(
        f"mock включён, но для llm-ноды {node_id!r} нет ни nodes[{node_id!r}], ни общей llm-очереди"
    )


async def resolve_tool_mock_result(
    redis_client: RedisClient,
    session_id: str,
    tool_name: str,
    *,
    manifest: MockControlManifest | None = None,
) -> str | None:
    """
    Текст результата tool из очереди `tools[tool_name]` или None (tool не замокан).

    Очередь сконфигурирована, но исчерпана — fail-closed (`MockControlError`).
    """
    if manifest is None:
        manifest = await get_mock_control_manifest(redis_client, session_id)
    if manifest is None or tool_name not in manifest.tools:
        return None
    item = await pop_mock_array_response(
        redis_client, _queue_key(session_id, "tool", tool_name)
    )
    if item is None:
        raise MockControlError(f"mock очередь tool {tool_name!r} исчерпана")
    return mock_item_to_text(item)


async def resolve_entity_node_mock_result(
    redis_client: RedisClient,
    session_id: str,
    queue_kind: str,
    entity_id: str,
) -> JsonValue | MockMiss:
    """
    Результат для не-LLM ноды (`node`) или вложенного flow (`flow`).

    Возвращает `MOCK_MISS`, если сущность не замокана (нужен реальный запуск);
    иначе — результат из очереди (dict мержится в state, скаляр → state.result).
    """
    manifest = await get_mock_control_manifest(redis_client, session_id)
    if manifest is None:
        return MOCK_MISS
    configured_ids = manifest.flows if queue_kind == "flow" else manifest.nodes
    if entity_id not in configured_ids:
        return MOCK_MISS
    item = await pop_mock_array_response(
        redis_client, _queue_key(session_id, queue_kind, entity_id)
    )
    if item is None:
        raise MockControlError(f"mock очередь {queue_kind} {entity_id!r} исчерпана")
    return mock_item_to_node_result(item)


def mock_item_to_text(item: MockLLMQueuedResponse) -> str:
    """Сводит элемент очереди к тексту (результат tool)."""
    if isinstance(item, str):
        return item
    item_type = item.get("type")
    if item_type in ("text", "result"):
        content = item.get("content")
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)
    return json.dumps(item, ensure_ascii=False)


def mock_item_to_node_result(item: MockLLMQueuedResponse) -> JsonValue:
    """
    Сводит элемент очереди к результату ноды/flow.

    `state` → patch (dict, мержится в state); `text`/`result` → content;
    строка → как есть (попадёт в state.result).
    """
    if isinstance(item, str):
        return item
    item_type = item.get("type")
    if item_type == "state":
        patch = item.get("patch")
        if not isinstance(patch, dict):
            raise ValueError("mock state item: 'patch' must be an object")
        return patch
    if item_type in ("text", "result"):
        return item.get("content")
    return item


@final
class MockMiss:
    """Сентинел-тип: сущность не замокана (нужен реальный запуск)."""

    __slots__ = ()


MOCK_MISS: Final[MockMiss] = MockMiss()
