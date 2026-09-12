"""Flow UI as a block document over plain A2A.

`FlowConfig.interface` and `BranchConfig.interface` become `FlowUIDocument`
block documents; the durable ledger, A2A projections and share grants lose the
A2UI representation layer. The Redis head-projection cache is derived from the
ledger and is purged, because it still holds `ExecutionState` of the previous shape.

Revision ID: 20260910_0035
Revises: 20260818_0034
Create Date: 2026-09-10
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence

import redis
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from apps.flows.src.durable_execution.hashing import hash_state_json
from apps.flows.src.durable_execution.models import ExecutionStateDelta
from apps.flows.src.durable_execution.state_delta import apply_state_delta
from apps.flows.src.models.flow_config import FlowConfig
from core.config import get_settings
from core.flow_ui.document import FlowUIDocument
from core.flow_ui.problems import FlowUILimits, flow_ui_problems
from core.flow_ui.templates import default_chat_document
from core.state import ExecutionState
from core.types import JsonArray, JsonObject, JsonValue, require_json_object

revision: str = "20260910_0035"
down_revision: str | None = "20260818_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_STATE_KEYS: frozenset[str] = frozenset(
    {
        "a2a_representation",
        "ui_document",
        "ui_interaction",
        "ui_effect_cursor",
        "ui_applied_effect_ids",
        "ui_template_version",
        "ui_last_synced_at",
        "ui_last_accepted_client_mutation_id",
        "ui_last_accepted_client_mutation_hash",
        "ui_conflict",
        "ui_values",
    }
)
_REMOVED_EVENT_TYPES: tuple[str, ...] = (
    "UIInteractionAccepted",
    "UIDocumentPatched",
    "UIRepresentationSelected",
)
_A2UI_MEDIA_TYPES: frozenset[str] = frozenset(
    {"application/a2ui+json", "application/vnd.a2ui+json;version=0.9.1"}
)
_A2UI_METADATA_KEYS: tuple[str, ...] = ("platformUi", "a2ui")
_LEGACY_DOCUMENT_ARTIFACT_NAME = "ui.document"
_LEGACY_DOCUMENT_DATA_KEY = "flowUi"
_LEGACY_ACTION_PREFIX = "platform.ui."
_LEGACY_CHAT_TEMPLATE_ID = "linnex.default-chat"
_TRANSPARENT_CONTAINERS: frozenset[str] = frozenset(
    {"PageShell", "Stack", "Column", "List", "Form", "FieldGroup"}
)
_ABSORBED_BY_CONVERSATION: frozenset[str] = frozenset(
    {"ConversationFeed", "ArtifactFeed", "TaskControls", "SuggestedPrompts"}
)
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_STATE_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$")
_JSONB = postgresql.JSONB()


# --- helpers over legacy JSON ------------------------------------------------


def _object(value: JsonValue, label: str) -> JsonObject:
    return require_json_object(value, label)


def _string(value: JsonValue, label: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        default = value.get("default")
        if isinstance(default, str):
            return default
    raise ValueError(f"{label} must be a string")


def _text(value: JsonValue, label: str) -> str:
    """Текстовое свойство: legacy допускал числа там, где новая грамматика ждёт шаблон."""
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a string")
    if isinstance(value, (int, float)):
        return str(value)
    return _string(value, label)


def _optional_string(value: JsonValue, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _pointer_to_state_path(pointer: str) -> str:
    """Legacy `values` были отдельным namespace с ключами-идентификаторами компонентов;
    в state путь обязан быть идентификатором, поэтому дефисы и прочее становятся `_`."""
    segments = [segment for segment in pointer.split("/") if segment]
    if len(segments) < 2 or segments[0] not in {"values", "content"}:
        raise ValueError(f"binding {pointer!r} cannot be expressed as a state path")
    normalized: list[str] = []
    for position, segment in enumerate(segments[1:]):
        cleaned = re.sub(r"[^A-Za-z0-9_]", "_", segment)
        if position == 0 and cleaned and not (cleaned[0].isalpha() or cleaned[0] == "_"):
            cleaned = f"field_{cleaned}"
        normalized.append(cleaned)
    path = ".".join(normalized)
    if _STATE_PATH_RE.match(path) is None:
        raise ValueError(f"binding {pointer!r} is not a valid state path")
    return path


def _block_id(component_id: str, used: set[str]) -> str:
    candidate = re.sub(r"[^a-z0-9_-]", "-", component_id.lower())
    if not candidate or not candidate[0].isalpha():
        candidate = f"b-{candidate}"
    unique = candidate
    suffix = 2
    while unique in used:
        unique = f"{candidate}-{suffix}"
        suffix += 1
    used.add(unique)
    return unique


# Alembic исполняет файл ревизии вне sys.modules — dataclass здесь недоступен.
class _ConversationCapture:
    __slots__ = ("greeting", "placeholder", "present", "submit_label", "suggested_prompts")

    def __init__(self) -> None:
        self.present: bool = False
        self.greeting: str = ""
        self.suggested_prompts: list[str] = []
        self.placeholder: str = ""
        self.submit_label: str = ""


class _SurfaceContext:
    __slots__ = (
        "components",
        "composer_ids",
        "content",
        "conversation",
        "conversation_emitted",
        "flow_id",
        "policy",
        "used_ids",
    )

    def __init__(
        self,
        *,
        flow_id: str,
        components: JsonObject,
        content: JsonObject,
        policy: JsonObject,
        used_ids: set[str],
    ) -> None:
        self.flow_id: str = flow_id
        self.components: JsonObject = components
        self.content: JsonObject = content
        self.policy: JsonObject = policy
        self.used_ids: set[str] = used_ids
        self.conversation: _ConversationCapture = _ConversationCapture()
        self.conversation_emitted: bool = False
        self.composer_ids: set[str] = _composer_component_ids(components)


_COMPOSER_LEAF_TYPES: frozenset[str] = frozenset(
    {"TextArea", "TextField", "FileUpload", "VoiceInput"}
)
_COMPOSER_MESSAGE_POINTER = "/values/message"
_LEGACY_SUBMIT_ACTION = "platform.ui.submit"


def _is_legacy_submit_button(component: JsonObject) -> bool:
    if _string(component.get("type"), "component.type") != "Button":
        return False
    raw_actions = component.get("actions")
    if raw_actions is None:
        return False
    press = _object(raw_actions, "component.actions").get("press")
    if press is None:
        return False
    return _object(press, "action press").get("name") == _LEGACY_SUBMIT_ACTION


def _composer_component_ids(components: JsonObject) -> set[str]:
    """Composer чата legacy-шаблона — Form с текстовым полем `/values/message` рядом с
    ConversationFeed; его поле, вложения, голос и кнопка submit в новой грамматике живут
    внутри блока `conversation`. Остальные дети такой формы остаются обычными блоками."""
    typed = {
        component_id: _object(raw, f"component {component_id}")
        for component_id, raw in components.items()
    }
    if not any(
        _string(component.get("type"), "component.type") == "ConversationFeed"
        for component in typed.values()
    ):
        return set()
    composer_ids: set[str] = set()
    for component in typed.values():
        if _string(component.get("type"), "component.type") != "Form":
            continue
        raw_children = component.get("children")
        child_ids = (
            [_string(item, "child id") for item in raw_children]
            if isinstance(raw_children, list)
            else []
        )
        children = {child_id: _component_of(typed, child_id) for child_id in child_ids}
        has_message_field = any(
            _string(child.get("type"), "component.type") in {"TextArea", "TextField"}
            and _bindings(child).get("value") == _COMPOSER_MESSAGE_POINTER
            for child in children.values()
        )
        if not has_message_field:
            continue
        for child_id, child in children.items():
            child_type = _string(child.get("type"), "component.type")
            if child_type in _COMPOSER_LEAF_TYPES or _is_legacy_submit_button(child):
                composer_ids.add(child_id)
    return composer_ids


def _component_of(components: dict[str, JsonObject], component_id: str) -> JsonObject:
    component = components.get(component_id)
    if component is None:
        raise ValueError(f"component {component_id!r} is missing")
    return component


def _component(context: _SurfaceContext, component_id: str) -> JsonObject:
    raw = context.components.get(component_id)
    if raw is None:
        raise ValueError(f"flow {context.flow_id}: component {component_id!r} is missing")
    return _object(raw, f"component {component_id}")


def _properties(component: JsonObject) -> JsonObject:
    raw = component.get("properties")
    return {} if raw is None else _object(raw, "component.properties")


def _bindings(component: JsonObject) -> dict[str, str]:
    raw = component.get("bindings")
    if raw is None:
        return {}
    bindings = _object(raw, "component.bindings")
    return {name: _string(pointer, f"binding {name}") for name, pointer in bindings.items()}


def _text_property(context: _SurfaceContext, component: JsonObject, *names: str) -> str:
    bindings = _bindings(component)
    properties = _properties(component)
    for name in names:
        pointer = bindings.get(name)
        if pointer is None:
            continue
        if pointer.startswith("/content/"):
            key = pointer.removeprefix("/content/")
            literal = context.content.get(key)
            if isinstance(literal, str):
                return literal
            return "{" + _pointer_to_state_path(pointer) + "}"
        if pointer.startswith("/values/"):
            return "{" + _pointer_to_state_path(pointer) + "}"
        raise ValueError(f"flow {context.flow_id}: binding {name}={pointer!r} is not convertible")
    for name in names:
        value = properties.get(name)
        if value is not None:
            return _text(value, f"property {name}")
    return ""


def _field_path(context: _SurfaceContext, component: JsonObject, component_id: str) -> str:
    pointer = _bindings(component).get("value")
    if pointer is not None:
        return _pointer_to_state_path(pointer)
    path = re.sub(r"[^A-Za-z0-9_]", "_", component_id)
    if not path or not (path[0].isalpha() or path[0] == "_"):
        path = f"field_{path}"
    if _STATE_PATH_RE.match(path) is None:
        raise ValueError(f"flow {context.flow_id}: cannot derive field path for {component_id!r}")
    return path


def _validation(component: JsonObject) -> tuple[bool, str | None, str]:
    raw_checks = component.get("checks")
    if raw_checks is None:
        return False, None, ""
    if not isinstance(raw_checks, list):
        raise ValueError("component.checks must be a list")
    required = False
    patterns: list[str] = []
    message = ""
    for raw_check in raw_checks:
        check = _object(raw_check, "check")
        function = _string(check.get("function"), "check.function")
        check_message = _optional_string(check.get("message"), "check.message")
        if check_message and not message:
            message = check_message
        if function == "required":
            required = True
        elif function == "regex":
            patterns.append(_string(check.get("pattern"), "check.pattern"))
        elif function == "email":
            patterns.append(_EMAIL_PATTERN)
        elif function == "minLength":
            patterns.append(r"^[\s\S]{%d,}$" % int(_number(check.get("value"), "check.value")))
        elif function == "maxLength":
            patterns.append(r"^[\s\S]{0,%d}$" % int(_number(check.get("value"), "check.value")))
        else:
            raise ValueError(f"unknown check function {function!r}")
    if not patterns:
        return required, None, message
    if len(patterns) == 1:
        return required, patterns[0], message
    lookaheads = "".join(f"(?={pattern})" for pattern in patterns)
    return required, f"^{lookaheads}[\\s\\S]*$", message


def _number(value: JsonValue, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    return float(value)


def _optional_number(value: JsonValue, label: str) -> float | None:
    if value is None:
        return None
    return _number(value, label)


def _placement(component: JsonObject) -> tuple[int | None, int | None, int]:
    raw = component.get("placement")
    if raw is None:
        return None, None, 0
    base = _object(_object(raw, "placement").get("base") or {}, "placement.base")
    row_start = base.get("row_start")
    column_span = base.get("column_span")
    order = base.get("order")
    return (
        int(row_start) if isinstance(row_start, int) and not isinstance(row_start, bool) else None,
        int(column_span)
        if isinstance(column_span, int) and not isinstance(column_span, bool)
        else None,
        int(order) if isinstance(order, int) and not isinstance(order, bool) else 0,
    )


def _grid_columns(component: JsonObject) -> int:
    raw = component.get("container_layout")
    if raw is None:
        return 12
    layout = _object(raw, "container_layout")
    grid = layout.get("grid")
    if grid is None:
        return 12
    bands = _object(_object(grid, "grid").get("columns_by_band") or {}, "columns_by_band")
    wide = bands.get("wide")
    if isinstance(wide, int) and not isinstance(wide, bool) and wide > 0:
        return wide
    return 12


def _action(component: JsonObject, slot: str) -> JsonObject | None:
    raw_actions = component.get("actions")
    if raw_actions is None:
        return None
    action = _object(raw_actions, "component.actions").get(slot)
    if action is None:
        return None
    spec = _object(action, f"action {slot}")
    if spec.get("kind") == "local":
        return None
    name = _string(spec.get("name"), "action.name")
    if name == "platform.ui.submit":
        name = "submit"
    else:
        name = re.sub(r"[^a-z0-9_]", "_", name.lower())
        if not name[0].isalpha():
            name = f"a_{name}"
    context = spec.get("context")
    payload = {} if context is None else _object(context, "action.context")
    return {"name": name, "payload": payload}


def _options(context: _SurfaceContext, component: JsonObject) -> JsonArray:
    raw = _properties(component).get("options")
    if raw is None:
        pointer = _bindings(component).get("options")
        if pointer is not None and pointer.startswith("/content/"):
            raw = context.content.get(pointer.removeprefix("/content/"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"flow {context.flow_id}: select options are required")
    options: JsonArray = []
    for item in raw:
        if isinstance(item, dict):
            value = _string(item.get("value"), "option.value")
            label = _optional_string(item.get("label"), "option.label")
            options.append({"value": value, "label": label if label is not None else value})
        else:
            value = _string(item, "option")
            options.append({"value": value, "label": value})
    return options


# --- component conversion ----------------------------------------------------


def _input_block(
    context: _SurfaceContext,
    component_id: str,
    component: JsonObject,
    block_type: str,
    extra: JsonObject,
) -> JsonObject:
    required, pattern, message = _validation(component)
    block: JsonObject = {
        "type": block_type,
        "block_id": _block_id(component_id, context.used_ids),
        "field": _field_path(context, component, component_id),
        "label": _text_property(context, component, "label", "title"),
        "required": required,
    }
    if message:
        block["error_message"] = message
    if pattern is not None and block_type == "text_input":
        block["pattern"] = pattern
    block.update(extra)
    return block


def _leaf(context: _SurfaceContext, component_id: str, component: JsonObject) -> JsonObject | None:
    component_type = _string(component.get("type"), "component.type")
    properties = _properties(component)
    bindings = _bindings(component)

    def new_id() -> str:
        return _block_id(component_id, context.used_ids)

    if component_type == "Text":
        return {
            "type": "text",
            "block_id": new_id(),
            "markdown": _text_property(context, component, "text"),
        }
    if component_type == "Markdown":
        return {
            "type": "text",
            "block_id": new_id(),
            "markdown": _text_property(context, component, "content", "text"),
        }
    if component_type == "Heading":
        level = properties.get("level")
        level_value = int(level) if isinstance(level, int) and not isinstance(level, bool) else 2
        return {
            "type": "heading",
            "block_id": new_id(),
            "text": _text_property(context, component, "text", "title"),
            "level": min(max(level_value, 1), 3),
        }
    if component_type == "CodeBlock":
        return {
            "type": "code",
            "block_id": new_id(),
            "code": _text_property(context, component, "code"),
            "language": _optional_string(properties.get("language"), "language") or "text",
        }
    if component_type == "Image":
        return {
            "type": "image",
            "block_id": new_id(),
            "url": _text_property(context, component, "src", "url"),
            "alt": _text_property(context, component, "alt"),
        }
    if component_type == "Video":
        return {
            "type": "video",
            "block_id": new_id(),
            "url": _text_property(context, component, "src", "url"),
        }
    if component_type == "AudioPlayer":
        return {
            "type": "audio",
            "block_id": new_id(),
            "url": _text_property(context, component, "src", "url"),
        }
    if component_type == "Divider":
        return {"type": "divider", "block_id": new_id()}
    if component_type == "Badge":
        return {
            "type": "badge",
            "block_id": new_id(),
            "label": _text_property(context, component, "label", "text"),
        }
    if component_type == "Alert":
        return {
            "type": "alert",
            "block_id": new_id(),
            "title": _text_property(context, component, "title"),
            "message": _text_property(context, component, "message", "text"),
        }
    if component_type == "Metric":
        return {
            "type": "metric",
            "block_id": new_id(),
            "label": _text_property(context, component, "label"),
            "value": _text_property(context, component, "value"),
            "hint": _text_property(context, component, "hint"),
        }
    if component_type == "Status":
        return {
            "type": "status",
            "block_id": new_id(),
            "label": _text_property(context, component, "label", "text"),
        }
    if component_type == "Progress":
        maximum = _optional_number(properties.get("max"), "max")
        return {
            "type": "progress",
            "block_id": new_id(),
            "label": _text_property(context, component, "label"),
            "value": _text_property(context, component, "value"),
            "max": maximum if maximum is not None else 100,
        }
    if component_type == "EmptyState":
        if bindings.get("message") == "/content/greeting":
            return None
        return {
            "type": "empty_state",
            "block_id": new_id(),
            "title": _text_property(context, component, "title"),
            "message": _text_property(context, component, "message", "text"),
        }
    if component_type in {"Link", "PageLink"}:
        page_id = None
        for name in ("page_id", "pageId", "targetPageId"):
            page_id = _optional_string(properties.get(name), name)
            if page_id is not None:
                break
        block: JsonObject = {
            "type": "link",
            "block_id": new_id(),
            "label": _text_property(context, component, "label", "text"),
        }
        if page_id is not None:
            block["page_id"] = page_id
        else:
            block["url"] = _text_property(context, component, "href", "url")
        return block
    if component_type == "Button":
        action = _action(component, "press")
        if action is None:
            raise ValueError(f"flow {context.flow_id}: button {component_id!r} has no event action")
        variant = _optional_string(properties.get("variant"), "variant")
        return {
            "type": "button",
            "block_id": new_id(),
            "label": _text_property(context, component, "label", "text"),
            "action": action,
            "variant": variant
            if variant in {"primary", "secondary", "ghost", "danger"}
            else "primary",
        }
    if component_type in {"TextField", "TextArea"}:
        return _input_block(
            context,
            component_id,
            component,
            "text_input",
            {
                "placeholder": _text_property(context, component, "placeholder"),
                "multiline": component_type == "TextArea",
            },
        )
    if component_type == "NumberField":
        return _input_block(
            context,
            component_id,
            component,
            "number_input",
            {
                "placeholder": _text_property(context, component, "placeholder"),
                "min": _optional_number(properties.get("min"), "min"),
                "max": _optional_number(properties.get("max"), "max"),
                "step": _optional_number(properties.get("step"), "step"),
            },
        )
    if component_type in {"Select", "ChoicePicker"}:
        return _input_block(
            context,
            component_id,
            component,
            "select",
            {
                "placeholder": _text_property(context, component, "placeholder"),
                "options": _options(context, component),
                "multiple": properties.get("multiple") is True,
            },
        )
    if component_type == "CheckBox":
        return _input_block(context, component_id, component, "checkbox", {})
    if component_type == "Switch":
        return _input_block(context, component_id, component, "switch", {})
    if component_type == "Slider":
        minimum = _optional_number(properties.get("min"), "min")
        maximum = _optional_number(properties.get("max"), "max")
        step = _optional_number(properties.get("step"), "step")
        return _input_block(
            context,
            component_id,
            component,
            "slider",
            {
                "min": minimum if minimum is not None else 0,
                "max": maximum if maximum is not None else 100,
                "step": step if step is not None else 1,
            },
        )
    if component_type == "DatePicker":
        return _input_block(context, component_id, component, "date_input", {})
    if component_type == "DateTimeInput":
        return _input_block(context, component_id, component, "datetime_input", {})
    if component_type == "FileUpload":
        return _input_block(
            context,
            component_id,
            component,
            "file_upload",
            {"multiple": properties.get("multiple") is not False},
        )
    if component_type == "VoiceInput":
        return _input_block(
            context,
            component_id,
            component,
            "voice_input",
            {"placeholder": _text_property(context, component, "placeholder")},
        )
    if component_type in {"Table", "DataTable"}:
        rows_pointer = bindings.get("rows")
        columns_raw = properties.get("columns")
        columns: JsonArray = []
        if isinstance(columns_raw, list):
            for item in columns_raw:
                column = _object(item, "table column")
                key = _string(column.get("key"), "column.key")
                label = _optional_string(column.get("label"), "column.label")
                columns.append({"key": key, "label": label if label is not None else key})
        block = {"type": "data_table", "block_id": new_id(), "columns": columns}
        if rows_pointer is not None:
            block["rows"] = _pointer_to_state_path(rows_pointer)
            return block
        file_id = _text_property(context, component, "file_id")
        if file_id != "":
            block["file_id"] = file_id
            return block
        block["rows"] = "rows"
        return block
    if component_type == "JsonInspector":
        pointer = bindings.get("data")
        if pointer is None:
            raise ValueError(
                f"flow {context.flow_id}: JsonInspector {component_id!r} has no data binding"
            )
        return {
            "type": "json_view",
            "block_id": new_id(),
            "path": _pointer_to_state_path(pointer),
            "title": _text_property(context, component, "title"),
        }
    if component_type == "FileCollection":
        pointer = bindings.get("files", "/values/files")
        return {"type": "file_list", "block_id": new_id(), "files": _pointer_to_state_path(pointer)}
    if component_type == "AgentIdentity":
        image_url = _optional_string(properties.get("image_url"), "image_url")
        return {
            "type": "agent_identity",
            "block_id": new_id(),
            "title": _text_property(context, component, "title", "name"),
            "image_url": image_url or "",
        }
    raise ValueError(
        f"flow {context.flow_id}: component {component_id!r} of type {component_type!r} "
        "cannot be expressed as a Flow UI block"
    )


def _capture_conversation(context: _SurfaceContext) -> None:
    """Collect conversation settings from every chat-machinery component of the surface."""
    capture = context.conversation
    for component_id, raw_component in context.components.items():
        component = _object(raw_component, f"component {component_id}")
        component_type = _string(component.get("type"), "component.type")
        properties = _properties(component)
        bindings = _bindings(component)
        if component_type == "EmptyState" and bindings.get("message") == "/content/greeting":
            greeting = context.content.get("greeting")
            capture.greeting = greeting if isinstance(greeting, str) else ""
            capture.present = True
            continue
        if not _is_conversation_part(context, component_id, component):
            continue
        capture.present = True
        if component_type == "SuggestedPrompts":
            pointer = bindings.get("items", "/content/suggestedPrompts")
            prompts = context.content.get(pointer.removeprefix("/content/"))
            if isinstance(prompts, list):
                capture.suggested_prompts = [_string(item, "suggested prompt") for item in prompts]
        if component_type == "TextArea":
            placeholder = _optional_string(properties.get("placeholder"), "placeholder")
            if placeholder:
                capture.placeholder = placeholder
        if _is_legacy_submit_button(component):
            capture.submit_label = _text_property(context, component, "label", "text")


def _is_conversation_part(
    context: _SurfaceContext, component_id: str, component: JsonObject
) -> bool:
    component_type = _string(component.get("type"), "component.type")
    if component_type in _ABSORBED_BY_CONVERSATION or component_id in context.composer_ids:
        return True
    return _properties(component).get("presentation") == "composer"


def _conversation_block(context: _SurfaceContext) -> JsonObject:
    policy = context.policy
    capture = context.conversation
    settings: JsonObject = {
        "greeting": capture.greeting,
        "suggested_prompts": capture.suggested_prompts[:12],
        "placeholder": capture.placeholder,
    }
    for source_name, target_name in (
        ("show_reasoning", "show_reasoning"),
        ("tool_calls_display", "tool_calls"),
        ("show_activity", "show_activity"),
        ("show_skill_loads", "show_skill_loads"),
        ("show_reflection", "show_reflection"),
        ("errors_display", "errors"),
        ("show_run_trace", "show_run_trace"),
        ("show_trace_actions", "show_trace_actions"),
        ("show_browser_previews", "show_browser_previews"),
        ("show_files_panel", "show_files_panel"),
        ("allow_cancel", "allow_cancel"),
        ("allow_voice", "allow_voice"),
    ):
        if source_name in policy:
            settings[target_name] = policy[source_name]
    context.conversation_emitted = True
    return {
        "type": "conversation",
        "block_id": _block_id("conversation", context.used_ids),
        "settings": settings,
    }


def _convert_children(context: _SurfaceContext, parent: JsonObject) -> JsonArray:
    raw_children = parent.get("children")
    if raw_children is None:
        return []
    if not isinstance(raw_children, list):
        raise ValueError("component.children must be a list")
    ordered: list[tuple[int, int, int, str]] = []
    for index, raw_child_id in enumerate(raw_children):
        child_id = _string(raw_child_id, "child id")
        row_start, _, order = _placement(_component(context, child_id))
        ordered.append((row_start if row_start is not None else 10**9, order, index, child_id))
    ordered.sort()
    grid_columns = _grid_columns(parent)

    blocks: JsonArray = []
    index = 0
    while index < len(ordered):
        row_start, _, _, child_id = ordered[index]
        row_members = [child_id]
        while (
            row_start < 10**9
            and index + len(row_members) < len(ordered)
            and ordered[index + len(row_members)][0] == row_start
        ):
            row_members.append(ordered[index + len(row_members)][3])
        index += len(row_members)
        if len(row_members) == 1:
            blocks.extend(_convert_component(context, child_id))
            continue
        blocks.extend(_columns_from_row(context, row_members, grid_columns))
    return blocks


def _columns_from_row(
    context: _SurfaceContext, member_ids: list[str], grid_columns: int
) -> JsonArray:
    widths: list[int] = []
    converted: list[JsonArray] = []
    for member_id in member_ids:
        blocks = _convert_component(context, member_id)
        if not blocks:
            continue
        _, span, _ = _placement(_component(context, member_id))
        widths.append(round(span * 12 / grid_columns) if span is not None else 0)
        converted.append(blocks)
    if not converted:
        return []
    if len(converted) == 1:
        return converted[0]
    if sum(widths) <= 0 or sum(widths) > 12 or 0 in widths:
        widths = [max(12 // len(converted), 1)] * len(converted)
    columns: JsonArray = [
        {"width": width, "blocks": blocks} for width, blocks in zip(widths, converted, strict=True)
    ]
    result: JsonArray = []
    for start in range(0, len(columns), 6):
        result.append(
            {
                "type": "columns",
                "block_id": _block_id("row", context.used_ids),
                "columns": columns[start : start + 6],
            }
        )
    return result


def _convert_component(context: _SurfaceContext, component_id: str) -> JsonArray:
    component = _component(context, component_id)
    component_type = _string(component.get("type"), "component.type")
    visibility = component.get("visibility")
    if isinstance(visibility, dict) and visibility:
        raise ValueError(
            f"flow {context.flow_id}: visibility rules of {component_id!r} are not convertible"
        )
    if _is_conversation_part(context, component_id, component):
        if component_type == "ConversationFeed" and not context.conversation_emitted:
            return [_conversation_block(context)]
        return []
    if component_type in _TRANSPARENT_CONTAINERS:
        return _convert_children(context, component)
    if component_type in {"Section", "Card"}:
        return [
            {
                "type": "section",
                "block_id": _block_id(component_id, context.used_ids),
                "title": _text_property(context, component, "title", "label"),
                "blocks": _convert_children(context, component),
            }
        ]
    if component_type in {"Row", "Grid"}:
        raw_children = component.get("children")
        member_ids = (
            [_string(item, "child id") for item in raw_children]
            if isinstance(raw_children, list)
            else []
        )
        if not member_ids:
            return []
        if len(member_ids) == 1:
            return _convert_component(context, member_ids[0])
        return _columns_from_row(context, member_ids, _grid_columns(component))
    if component_type == "Tabs":
        raw_children = component.get("children")
        member_ids = (
            [_string(item, "child id") for item in raw_children]
            if isinstance(raw_children, list)
            else []
        )
        raw_tabs = _properties(component).get("tabs")
        titles: list[str] = []
        if isinstance(raw_tabs, list):
            for item in raw_tabs:
                if isinstance(item, dict):
                    label = _optional_string(item.get("label"), "tab.label")
                    titles.append(label if label is not None else _string(item.get("id"), "tab.id"))
                else:
                    titles.append(_string(item, "tab"))
        tabs: JsonArray = []
        for position, member_id in enumerate(member_ids):
            member = _component(context, member_id)
            title = (
                titles[position]
                if position < len(titles)
                else _text_property(context, member, "title", "label") or member_id
            )
            tabs.append({"title": title, "blocks": _convert_component(context, member_id)})
        if not tabs:
            raise ValueError(f"flow {context.flow_id}: Tabs {component_id!r} has no tabs")
        return [
            {"type": "tabs", "block_id": _block_id(component_id, context.used_ids), "tabs": tabs}
        ]
    if component_type == "Icon":
        # Декоративная иконка без данных: в грамматике блоков аналога нет.
        return []
    if component_type in {"Modal", "ErrorBoundary", "Navigation", "Citations", "Chart"}:
        raise ValueError(
            f"flow {context.flow_id}: component {component_id!r} of type {component_type!r} "
            "cannot be expressed as a Flow UI block"
        )
    leaf = _leaf(context, component_id, component)
    return [leaf] if leaf is not None else []


def _convert_page(flow_id: str, document: JsonObject, page: JsonObject) -> JsonObject:
    page_id = _string(page.get("page_id"), "page.page_id")
    surfaces = _object(document.get("surfaces"), "document.surfaces")
    surface = _object(
        surfaces.get(_string(page.get("root_surface_id"), "page.root_surface_id")), "surface"
    )
    data_model = _object(surface.get("data_model") or {}, "surface.data_model")
    context = _SurfaceContext(
        flow_id=flow_id,
        components=_object(surface.get("components"), "surface.components"),
        content=_object(data_model.get("content") or {}, "data_model.content"),
        policy=_object(document.get("policy") or {}, "document.policy"),
        used_ids=set(),
    )
    root_id = _string(surface.get("root_component_id", "root"), "surface.root_component_id")
    _capture_conversation(context)
    blocks = _convert_component(context, root_id)
    if context.conversation.present and not context.conversation_emitted:
        blocks.append(_conversation_block(context))
    if context.conversation.submit_label and _has_inputs_without_action(blocks):
        # Кнопка composer'а legacy отправляла все values страницы; поля вне composer'а
        # сохраняют её как действие страницы.
        blocks.append(
            {
                "type": "button",
                "block_id": _block_id("submit", context.used_ids),
                "label": context.conversation.submit_label,
                "action": {"name": "submit", "payload": {}},
            }
        )
    title_raw = page.get("title")
    title = _string(title_raw, "page.title") if title_raw is not None else ""
    return {"page_id": page_id, "title": title, "blocks": blocks}


def _is_plain_chat(converted_pages: JsonArray) -> bool:
    """Одна страница только из chat-машинерии: пользователь не достраивал документ поверх шаблона."""
    if len(converted_pages) != 1:
        return False
    blocks = _object(converted_pages[0], "page").get("blocks")
    if not isinstance(blocks, list):
        return False
    types: set[str] = set()
    for block in blocks:
        for nested in _flatten(block):
            block_type = nested.get("type")
            if not isinstance(block_type, str):
                raise ValueError("block.type must be a string")
            types.add(block_type)
    return "conversation" in types and types <= {"conversation", "agent_identity", "section"}


_INPUT_BLOCK_TYPES: frozenset[str] = frozenset(
    {
        "text_input",
        "number_input",
        "select",
        "checkbox",
        "switch",
        "slider",
        "date_input",
        "datetime_input",
        "file_upload",
        "voice_input",
    }
)


def _has_inputs_without_action(blocks: JsonArray) -> bool:
    has_inputs = False
    for block in blocks:
        for nested in _flatten(block):
            block_type = nested.get("type")
            if block_type in _INPUT_BLOCK_TYPES:
                has_inputs = True
            if block_type in {"button", "html"} or nested.get("action") is not None:
                return False
            if nested.get("row_action") is not None:
                return False
    return has_inputs


def _chat_template_document(converted_pages: JsonArray) -> JsonObject:
    """Нетронутый chat-шаблон получает стоковые block_id; переносятся только settings и аватар."""
    page = _object(converted_pages[0], "page")
    blocks = page.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("chat template page has no blocks")
    conversation: JsonObject | None = None
    image_url = ""
    identity_title = ""
    for block in blocks:
        for nested in _flatten(block):
            if nested.get("type") == "conversation":
                conversation = nested
            if nested.get("type") == "agent_identity":
                image_url = _string(nested.get("image_url"), "agent_identity.image_url")
                identity_title = _string(nested.get("title"), "agent_identity.title")
    if conversation is None:
        raise ValueError("chat template has no conversation block")
    document = require_json_object(default_chat_document().model_dump(mode="json"), "chat document")
    stock_pages = document.get("pages")
    if not isinstance(stock_pages, list) or not isinstance(stock_pages[0], dict):
        raise ValueError("default chat document has no pages")
    stock_blocks = stock_pages[0].get("blocks")
    if not isinstance(stock_blocks, list):
        raise ValueError("default chat document has no blocks")
    for block in stock_blocks:
        if not isinstance(block, dict):
            raise ValueError("default chat document block must be an object")
        if block.get("type") == "conversation":
            block["settings"] = conversation.get("settings")
        if block.get("type") == "agent_identity":
            block["image_url"] = image_url
            block["title"] = identity_title
    return document


def _flatten(block: JsonValue) -> list[JsonObject]:
    block_object = _object(block, "block")
    found = [block_object]
    for key in ("blocks",):
        nested = block_object.get(key)
        if isinstance(nested, list):
            for child in nested:
                found.extend(_flatten(child))
    for key in ("columns", "tabs"):
        groups = block_object.get(key)
        if isinstance(groups, list):
            for group in groups:
                group_blocks = _object(group, key).get("blocks")
                if isinstance(group_blocks, list):
                    for child in group_blocks:
                        found.extend(_flatten(child))
    return found


def _convert_interface(flow_id: str, legacy: JsonObject) -> JsonObject:
    template = _object(legacy.get("template"), "interface.template")
    document = _object(template.get("document"), "interface.template.document")
    pages_raw = _object(document.get("pages"), "document.pages")
    pages: JsonArray = [
        _convert_page(flow_id, document, _object(page, f"page {page_id}"))
        for page_id, page in pages_raw.items()
    ]
    converted: JsonObject
    if template.get("template_id") == _LEGACY_CHAT_TEMPLATE_ID and _is_plain_chat(pages):
        converted = _chat_template_document(pages)
    else:
        converted = {
            "pages": pages,
            "start_page_id": _string(document.get("active_page_id"), "document.active_page_id"),
        }
    validated = FlowUIDocument.model_validate(converted)
    problems = flow_ui_problems(validated, FlowUILimits())
    if problems:
        details = "; ".join(f"{problem.code}: {problem.message}" for problem in problems)
        raise ValueError(f"flow {flow_id}: converted interface is not publishable ({details})")
    return require_json_object(validated.model_dump(mode="json"), "FlowUIDocument")


def _convert_flow_config(key: str, payload: JsonObject) -> JsonObject:
    flow_id = _string(payload.get("flow_id"), f"{key}.flow_id")
    legacy_interface = payload.get("interface")
    if isinstance(legacy_interface, dict) and "template" in legacy_interface:
        payload["interface"] = _convert_interface(flow_id, legacy_interface)
    branches = payload.get("branches")
    if isinstance(branches, dict):
        for branch_id, raw_branch in branches.items():
            branch = _object(raw_branch, f"{key}.branches.{branch_id}")
            override = branch.pop("interface_override", None)
            if override is None:
                branch.setdefault("interface", None)
            else:
                override_object = _object(override, f"{key}.interface_override")
                replacement = override_object.get("replacement")
                branch["interface"] = (
                    _convert_interface(
                        flow_id, _object(replacement, "interface_override.replacement")
                    )
                    if override_object.get("mode") == "replace" and replacement is not None
                    else None
                )
            branches[branch_id] = branch
    _ = FlowConfig.model_validate(payload)
    return payload


def _rewrite_flow_configs() -> None:
    connection = op.get_bind()
    update_statement_by_table = {
        table: sa.text(
            f"UPDATE {table} SET value = :value, updated_at = now() WHERE key = :key"
        ).bindparams(sa.bindparam("value", type_=_JSONB))
        for table in ("flows", "flows_versions")
    }
    for table, update_statement in update_statement_by_table.items():
        rows = connection.execute(
            sa.text(
                f"SELECT key, value FROM {table} WHERE value->'interface' ? 'template' "
                "OR EXISTS (SELECT 1 FROM jsonb_each(COALESCE(value->'branches', '{}'::jsonb)) b "
                "WHERE b.value ? 'interface_override')"
            )
        ).mappings()
        for row in rows:
            key = row["key"]
            if not isinstance(key, str):
                raise RuntimeError(f"Flow UI migration found an invalid key in {table}")
            payload = require_json_object(row["value"], f"{table}.{key}")
            try:
                migrated = _convert_flow_config(key, payload)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Flow UI migration failed for {table}.{key}: {exc}") from exc
            _ = connection.execute(update_statement, {"key": key, "value": migrated})


# --- durable ledger ----------------------------------------------------------


def _strip_state_keys(state: JsonObject) -> JsonObject:
    return {key: value for key, value in state.items() if key not in _LEGACY_STATE_KEYS}


def _strip_delta(raw_delta: JsonObject) -> ExecutionStateDelta:
    allowed = set(ExecutionStateDelta.model_fields)
    delta: JsonObject = {key: value for key, value in raw_delta.items() if key in allowed}
    fields_set = delta.get("fields_set")
    if isinstance(fields_set, dict):
        delta["fields_set"] = _strip_state_keys(fields_set)
    fields_unset = delta.get("fields_unset")
    if isinstance(fields_unset, list):
        delta["fields_unset"] = [key for key in fields_unset if key not in _LEGACY_STATE_KEYS]
    messages_append = delta.get("messages_append")
    if isinstance(messages_append, list):
        delta["messages_append"] = [
            message
            for message in messages_append
            if not isinstance(message, dict) or _strip_parts(message)
        ]
    return ExecutionStateDelta.model_validate(delta)


def _rewrite_activity_attempts() -> None:
    """Кэш завершённых activities воспроизводится через строгую ExecutionStateDelta."""

    def keep_attempt(result_json: JsonObject) -> bool:
        raw_delta = result_json.get("state_delta")
        if isinstance(raw_delta, dict):
            result_json["state_delta"] = _strip_delta(raw_delta).model_dump(
                mode="json", exclude_none=False
            )
        return True

    _rewrite_json_rows(
        "activity_attempts",
        "activity_attempt_id",
        "result_json",
        keep_attempt,
        where=" WHERE result_json ? 'state_delta'",
    )


def _state_json(state: ExecutionState) -> JsonObject:
    data = require_json_object(state.model_dump(mode="json", exclude_none=False), "ExecutionState")
    _ = data.pop("flow_config", None)
    return data


class _BranchRow:
    __slots__ = ("base_sequence", "execution_branch_id", "parent_execution_branch_id")

    def __init__(
        self,
        *,
        execution_branch_id: str,
        parent_execution_branch_id: str | None,
        base_sequence: int,
    ) -> None:
        self.execution_branch_id: str = execution_branch_id
        self.parent_execution_branch_id: str | None = parent_execution_branch_id
        self.base_sequence: int = base_sequence


def _session_branches(
    connection: sa.Connection, company_id: str, session_id: str, event_branch_ids: set[str]
) -> list[_BranchRow]:
    """Ветки сессии в порядке «родитель раньше ребёнка»; ветка без строки — корневая."""
    rows = (
        connection.execute(
            sa.text(
                "SELECT execution_branch_id, parent_execution_branch_id, base_sequence "
                "FROM execution_branches WHERE company_id = :company_id AND session_id = :session_id"
            ),
            {"company_id": company_id, "session_id": session_id},
        )
        .mappings()
        .all()
    )
    by_id: dict[str, _BranchRow] = {}
    for row in rows:
        branch_id = row["execution_branch_id"]
        if not isinstance(branch_id, str):
            raise RuntimeError(f"execution_branches has a non-string id in session {session_id}")
        parent_raw = row["parent_execution_branch_id"]
        if parent_raw is not None and not isinstance(parent_raw, str):
            raise RuntimeError(
                f"execution_branches has a non-string parent in session {session_id}"
            )
        by_id[branch_id] = _BranchRow(
            execution_branch_id=branch_id,
            parent_execution_branch_id=parent_raw,
            base_sequence=int(row["base_sequence"]),
        )
    for branch_id in event_branch_ids:
        if branch_id not in by_id:
            by_id[branch_id] = _BranchRow(
                execution_branch_id=branch_id, parent_execution_branch_id=None, base_sequence=0
            )
    ordered: list[_BranchRow] = []
    placed: set[str] = set()
    pending = list(by_id.values())
    while pending:
        progressed = False
        for branch in list(pending):
            parent_id = branch.parent_execution_branch_id
            if parent_id is None or parent_id in placed:
                ordered.append(branch)
                placed.add(branch.execution_branch_id)
                pending.remove(branch)
                progressed = True
        if not progressed:
            raise RuntimeError(
                f"execution_branches of session {session_id} reference an unknown parent branch"
            )
    return ordered


def _rebuild_ledger() -> None:
    connection = op.get_bind()
    _ = connection.execute(
        sa.text("DELETE FROM workflow_events WHERE event_type IN :types").bindparams(
            sa.bindparam("types", value=_REMOVED_EVENT_TYPES, expanding=True)
        )
    )
    sessions = (
        connection.execute(
            sa.text(
                "SELECT company_id, session_id, array_agg(DISTINCT execution_branch_id) AS branch_ids "
                "FROM workflow_events GROUP BY company_id, session_id ORDER BY company_id, session_id"
            )
        )
        .mappings()
        .all()
    )
    update_event = sa.text(
        "UPDATE workflow_events SET state_delta = :state_delta, payload = :payload, "
        "prev_state_hash = :prev_hash, next_state_hash = :next_hash WHERE event_id = :event_id"
    ).bindparams(sa.bindparam("state_delta", type_=_JSONB), sa.bindparam("payload", type_=_JSONB))
    update_snapshot = sa.text(
        "UPDATE workflow_snapshots SET state_json = :state_json, state_hash = :state_hash "
        "WHERE snapshot_id = :snapshot_id"
    ).bindparams(sa.bindparam("state_json", type_=_JSONB))
    update_branch_base = sa.text(
        "UPDATE execution_branches SET base_state_hash = :base_hash "
        "WHERE execution_branch_id = :branch_id"
    )
    update_instance_head = sa.text(
        "UPDATE workflow_instances SET head_state_hash = :head_hash, head_sequence = :head_sequence, "
        "latest_snapshot_id = :latest_snapshot_id "
        "WHERE company_id = :company_id AND session_id = :session_id "
        "AND active_execution_branch_id = :branch_id"
    )
    for session_row in sessions:
        company_id = session_row["company_id"]
        session_id = session_row["session_id"]
        event_branch_ids = {str(branch_id) for branch_id in session_row["branch_ids"]}
        branches = _session_branches(connection, company_id, session_id, event_branch_ids)
        # Состояние родителя в точке fork нужно детям: собираем требуемые sequence заранее.
        fork_points: dict[str, set[int]] = {}
        for branch in branches:
            if branch.parent_execution_branch_id is not None:
                fork_points.setdefault(branch.parent_execution_branch_id, set()).add(
                    branch.base_sequence
                )
        base_states: dict[tuple[str, int], tuple[JsonObject, str]] = {}
        for branch in branches:
            branch_id = branch.execution_branch_id
            events = (
                connection.execute(
                    sa.text(
                        "SELECT event_id, sequence, state_delta, payload FROM workflow_events "
                        "WHERE company_id = :company_id AND session_id = :session_id "
                        "AND execution_branch_id = :branch_id ORDER BY sequence"
                    ),
                    {"company_id": company_id, "session_id": session_id, "branch_id": branch_id},
                )
                .mappings()
                .all()
            )
            snapshots = (
                connection.execute(
                    sa.text(
                        "SELECT snapshot_id, sequence FROM workflow_snapshots "
                        "WHERE company_id = :company_id AND session_id = :session_id "
                        "AND execution_branch_id = :branch_id ORDER BY sequence"
                    ),
                    {"company_id": company_id, "session_id": session_id, "branch_id": branch_id},
                )
                .mappings()
                .all()
            )
            snapshot_by_sequence = {int(row["sequence"]): row["snapshot_id"] for row in snapshots}

            state: ExecutionState | None = None
            previous_hash: str | None = None
            kept_sequences: set[int] = set()
            parent_id = branch.parent_execution_branch_id
            if parent_id is not None:
                base = base_states.get((parent_id, branch.base_sequence))
                if base is None:
                    raise RuntimeError(
                        f"Flow UI ledger migration: branch {branch_id} of session {session_id} "
                        f"forks from unknown state {parent_id}@{branch.base_sequence}"
                    )
                base_json, previous_hash = base
                state = ExecutionState.model_validate(base_json)
                kept_sequences.add(branch.base_sequence)
                base_snapshot_id = snapshot_by_sequence.get(branch.base_sequence)
                if base_snapshot_id is not None:
                    _ = connection.execute(
                        update_snapshot,
                        {
                            "state_json": base_json,
                            "state_hash": previous_hash,
                            "snapshot_id": base_snapshot_id,
                        },
                    )
                _ = connection.execute(
                    update_branch_base, {"base_hash": previous_hash, "branch_id": branch_id}
                )
            wanted_forks = sorted(fork_points.get(branch_id, set()))

            def remember_forks(upto_sequence: int | None) -> None:
                while wanted_forks and (upto_sequence is None or wanted_forks[0] < upto_sequence):
                    fork_sequence = wanted_forks.pop(0)
                    if state is None:
                        raise RuntimeError(
                            f"Flow UI ledger migration: fork of {branch_id}@{fork_sequence} "
                            f"in session {session_id} precedes the first event"
                        )
                    fork_json = _state_json(state)
                    base_states[(branch_id, fork_sequence)] = (
                        fork_json,
                        hash_state_json(fork_json),
                    )

            for event in events:
                sequence = int(event["sequence"])
                remember_forks(sequence)
                kept_sequences.add(sequence)
                delta = _strip_delta(
                    require_json_object(event["state_delta"], "workflow_events.state_delta")
                )
                try:
                    state = apply_state_delta(state, delta)
                except ValueError as exc:
                    raise RuntimeError(
                        f"Flow UI ledger migration failed for session {session_id} "
                        f"branch {branch_id} at sequence {sequence}: {exc}"
                    ) from exc
                state_json = _state_json(state)
                state_hash = hash_state_json(state_json)
                payload = require_json_object(event["payload"], "workflow_events.payload")
                payload_delta = payload.get("state_delta")
                if isinstance(payload_delta, dict):
                    # NodeWriteRecorded дублирует delta в payload.
                    payload["state_delta"] = _strip_delta(payload_delta).model_dump(mode="json")
                _ = connection.execute(
                    update_event,
                    {
                        "state_delta": delta.model_dump(mode="json"),
                        "payload": payload,
                        "prev_hash": previous_hash,
                        "next_hash": state_hash,
                        "event_id": event["event_id"],
                    },
                )
                snapshot_id = snapshot_by_sequence.get(sequence)
                if snapshot_id is not None:
                    _ = connection.execute(
                        update_snapshot,
                        {
                            "state_json": state_json,
                            "state_hash": state_hash,
                            "snapshot_id": snapshot_id,
                        },
                    )
                previous_hash = state_hash
            remember_forks(None)

            orphan_snapshots = [
                snapshot_id
                for sequence, snapshot_id in snapshot_by_sequence.items()
                if sequence not in kept_sequences
            ]
            if orphan_snapshots:
                _ = connection.execute(
                    sa.text("DELETE FROM workflow_snapshots WHERE snapshot_id IN :ids").bindparams(
                        sa.bindparam("ids", value=orphan_snapshots, expanding=True)
                    )
                )
            if events:
                latest_snapshot_id = None
                for sequence in sorted(snapshot_by_sequence, reverse=True):
                    if sequence in kept_sequences:
                        latest_snapshot_id = snapshot_by_sequence[sequence]
                        break
                _ = connection.execute(
                    update_instance_head,
                    {
                        "head_hash": previous_hash,
                        "head_sequence": int(events[-1]["sequence"]),
                        "latest_snapshot_id": latest_snapshot_id,
                        "company_id": company_id,
                        "session_id": session_id,
                        "branch_id": branch_id,
                    },
                )


# --- A2A projections ---------------------------------------------------------


def _strip_metadata(container: JsonObject) -> None:
    metadata = container.get("metadata")
    if isinstance(metadata, dict):
        for key in _A2UI_METADATA_KEYS:
            _ = metadata.pop(key, None)
        if not metadata:
            _ = container.pop("metadata")


def _is_legacy_ui_part(part: JsonObject) -> bool:
    """A2UI parts, документ `flowUi` предыдущего поколения и текстовые кадры
    `platform.ui.*` — протокольные кадры интерфейса, а не содержимое разговора."""
    media_type = part.get("mediaType", part.get("media_type"))
    if isinstance(media_type, str) and media_type in _A2UI_MEDIA_TYPES:
        return True
    data = part.get("data")
    if isinstance(data, dict) and _LEGACY_DOCUMENT_DATA_KEY in data:
        return True
    text = part.get("text")
    if isinstance(text, str) and text.startswith("{") and _LEGACY_ACTION_PREFIX in text:
        frame = json.loads(text)
        action = frame.get("action") if isinstance(frame, dict) else None
        return isinstance(action, str) and action.startswith(_LEGACY_ACTION_PREFIX)
    return False


def _strip_state_diff(part: JsonObject) -> None:
    """Артефакты node_complete несут diff state; записи по удалённым полям исчезают вместе с полями."""
    data = part.get("data")
    if not isinstance(data, dict):
        return
    diff = data.get("diff")
    if not isinstance(diff, list):
        return
    data["diff"] = [
        entry
        for entry in diff
        if not (
            isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and str(entry["path"]).split(".", 1)[0] in _LEGACY_STATE_KEYS
        )
    ]


def _strip_parts(container: JsonObject) -> bool:
    """Drop legacy UI parts in place; returns True when parts remain."""
    if container.get("name") == _LEGACY_DOCUMENT_ARTIFACT_NAME:
        return False
    parts = container.get("parts")
    if not isinstance(parts, list):
        return True
    kept: JsonArray = []
    for raw_part in parts:
        if not isinstance(raw_part, dict):
            kept.append(raw_part)
            continue
        if _is_legacy_ui_part(raw_part):
            continue
        _strip_metadata(raw_part)
        _strip_state_diff(raw_part)
        kept.append(raw_part)
    container["parts"] = kept
    _strip_metadata(container)
    return bool(kept)


def _strip_task(task: JsonObject) -> None:
    _strip_metadata(task)
    history = task.get("history")
    if isinstance(history, list):
        task["history"] = [
            message for message in history if isinstance(message, dict) and _strip_parts(message)
        ]
    artifacts = task.get("artifacts")
    if isinstance(artifacts, list):
        task["artifacts"] = [
            artifact
            for artifact in artifacts
            if isinstance(artifact, dict) and _strip_parts(artifact)
        ]
    status = task.get("status")
    if isinstance(status, dict):
        status_message = status.get("message")
        if isinstance(status_message, dict) and not _strip_parts(status_message):
            _ = status.pop("message")


def _rewrite_json_rows(
    table: str,
    id_column: str,
    json_column: str,
    keep: Callable[[JsonObject], bool],
    extra_set: str = "",
    where: str = "",
) -> None:
    connection = op.get_bind()
    rows = (
        connection.execute(sa.text(f"SELECT {id_column}, {json_column} FROM {table}{where}"))
        .mappings()
        .all()
    )
    update_statement = sa.text(
        f"UPDATE {table} SET {json_column} = :value{extra_set} WHERE {id_column} = :row_id"
    ).bindparams(sa.bindparam("value", type_=_JSONB))
    delete_statement = sa.text(f"DELETE FROM {table} WHERE {id_column} = :row_id")
    for row in rows:
        row_id = row[id_column]
        payload = require_json_object(row[json_column], f"{table}.{json_column}")
        if keep(payload):
            _ = connection.execute(update_statement, {"value": payload, "row_id": row_id})
        else:
            _ = connection.execute(delete_statement, {"row_id": row_id})


def _keep_event(event_json: JsonObject) -> bool:
    if isinstance(event_json.get("history"), list) or isinstance(event_json.get("artifacts"), list):
        _strip_task(event_json)
        return True
    for key in ("artifact", "message", "status"):
        nested = event_json.get(key)
        if isinstance(nested, dict):
            if key == "status":
                status_message = nested.get("message")
                if isinstance(status_message, dict) and not _strip_parts(status_message):
                    _ = nested.pop("message")
            elif not _strip_parts(nested):
                return False
    _strip_metadata(event_json)
    return True


def _rewrite_a2a_projections() -> None:
    _rewrite_json_rows("a2a_task_messages", "task_message_id", "message_json", _strip_parts)
    _rewrite_json_rows(
        "a2a_artifact_projections",
        "artifact_projection_id",
        "artifact_json",
        _strip_parts,
        extra_set=", updated_at = now()",
    )
    _rewrite_json_rows("a2a_task_event_dedup", "task_event_id", "event_json", _keep_event)

    def keep_task(task_json: JsonObject) -> bool:
        _strip_task(task_json)
        return True

    _rewrite_json_rows(
        "a2a_task_projections",
        "task_id",
        "task_json",
        keep_task,
        extra_set=", updated_at = now()",
    )
    connection = op.get_bind()
    for key in _A2UI_METADATA_KEYS:
        _ = connection.execute(
            sa.text(
                f"UPDATE a2a_task_projections SET task_metadata = task_metadata - '{key}' WHERE task_metadata ? '{key}'"
            )
        )
    op.drop_column("a2a_task_projections", "negotiated_extensions")
    op.drop_column("a2a_task_projections", "representation")
    op.drop_column("a2a_task_projections", "ui_template_version")


# --- share grants ------------------------------------------------------------


def _rewrite_share_grants() -> None:
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text("SELECT grant_id, redacted_value_paths FROM flow_ui_share_grants")
        )
        .mappings()
        .all()
    )
    update_statement = sa.text(
        "UPDATE flow_ui_share_grants SET redacted_value_paths = :paths WHERE grant_id = :grant_id"
    ).bindparams(sa.bindparam("paths", type_=_JSONB))
    for row in rows:
        raw_paths = row["redacted_value_paths"]
        if not isinstance(raw_paths, list):
            raise RuntimeError(f"flow_ui_share_grants.{row['grant_id']} has invalid redacted paths")
        converted: list[str] = []
        for pointer in raw_paths:
            pointer_text = _string(pointer, "redacted path")
            if pointer_text.startswith("/values/"):
                pointer_text = "/" + pointer_text.removeprefix("/values/")
            converted.append(pointer_text)
        _ = connection.execute(update_statement, {"paths": converted, "grant_id": row["grant_id"]})
    op.alter_column(
        "flow_ui_share_grants", "redacted_value_paths", new_column_name="redacted_paths"
    )
    op.drop_column("flow_ui_share_grants", "document_id")
    op.drop_column("flow_ui_share_grants", "minimum_revision")


_PROJECTION_CACHE_PATTERN = "flows:workflow_projection:*"


def _purge_projection_cache() -> None:
    """Head-проекции в Redis хранят ExecutionState прежней формы и hash до переписи ledger."""
    client = redis.Redis.from_url(get_settings().database.redis_url)
    try:
        keys: list[bytes] = [
            key
            for key in client.scan_iter(match=_PROJECTION_CACHE_PATTERN, count=1000)
            if isinstance(key, bytes)
        ]
        if keys:
            _ = client.delete(*keys)
    finally:
        client.close()


def upgrade() -> None:
    _rewrite_flow_configs()
    _rebuild_ledger()
    _rewrite_activity_attempts()
    _rewrite_a2a_projections()
    _rewrite_share_grants()
    _purge_projection_cache()


def downgrade() -> None:
    raise RuntimeError(
        "Flow UI block documents cannot be converted back to A2UI templates; "
        "restore the flows database from a backup taken before 20260910_0035"
    )
