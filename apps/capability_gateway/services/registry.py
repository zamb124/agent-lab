"""Capability registry — единственный trusted каталог platform capabilities."""

from __future__ import annotations

import base64
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from a2a.types import Message, Part, Role, TextPart

from apps.capability_gateway.services.context_service import CapabilityContextService
from apps.capability_gateway.services.contracts import CapabilityGatewayContainerProtocol
from apps.voice.services.voice_usage import record_stt_usage, record_tts_usage
from core.capabilities import (
    CAPABILITY_LANGUAGES,
    CapabilityCallRequest,
    CapabilityCallResponse,
    CapabilityDefinition,
    CapabilityDocumentation,
    CapabilityInterruptEnvelope,
    CapabilityLanguage,
    CapabilityManifest,
    CapabilityNamespaceDocumentation,
    CapabilitySchemaFieldDocumentation,
    CapabilitySdkMethodDocumentation,
    JsonObject,
    JsonValue,
    verify_execution_context,
)
from core.clients.speech_override import SpeechOverride, SpeechProviderName, SpeechResponseFormat
from core.clients.speech_provider_catalog import STT_TTS_PROVIDER_IDS, VOICE_RESPONSE_FORMAT_IDS
from core.clients.voice_resolver import get_stt_client, get_tts_client
from core.files.audio_probe import probe_audio_duration_seconds_from_upload
from core.files.models import FileResponse
from core.files.reader import FileReader, FileReadError
from core.files.s3_client import S3ClientFactory
from core.files.writer import ContentMode, FileWriteError, FileWriter
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import Company
from core.text_transforms import TextTransformService
from core.tracing.operation_span import traced_operation

CapabilityHandler = Callable[[CapabilityCallRequest], Awaitable[JsonValue]]
TOOL_RUNTIME_MANIFEST_PATH = "/flows/api/v1/tool-runtime/manifest"
UI_EVENTS_KEY = "ui_events_pending"
MESSAGE_SOURCE_CAPABILITY = "__capability__"
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")
LOG_LEVELS = ("debug", "info", "warning", "error")
logger = get_logger(__name__)


class _CapabilityInterruptFromTool(Exception):
    def __init__(self, interrupt: JsonObject):
        self.interrupt = interrupt
        super().__init__("Tool capability interrupted")


def _schema_object(properties: JsonObject, required: list[str]) -> JsonObject:
    required_json: list[JsonValue] = list(required)
    schema: JsonObject = {
        "type": "object",
        "properties": properties,
        "required": required_json,
        "additionalProperties": False,
    }
    return schema


def _string_schema(description: str) -> JsonObject:
    return {"type": "string", "description": description}


def _integer_schema(description: str) -> JsonObject:
    return {"type": "integer", "description": description}


def _boolean_schema(description: str) -> JsonObject:
    return {"type": "boolean", "description": description}


def _object_schema(description: str) -> JsonObject:
    return {"type": "object", "description": description, "additionalProperties": True}


def _array_schema(description: str) -> JsonObject:
    return {"type": "array", "description": description, "items": {}}


def _json_schema(description: str) -> JsonObject:
    return {"description": description}


_SPEECH_PROVIDERS = STT_TTS_PROVIDER_IDS
_SPEECH_RESPONSE_FORMATS = VOICE_RESPONSE_FORMAT_IDS


def _speech_provider(value: str | None) -> SpeechProviderName | None:
    if value is None:
        return None
    if value not in _SPEECH_PROVIDERS:
        raise ValueError(f"Unknown speech provider: {value}")
    return cast(SpeechProviderName, value)


def _speech_response_format(value: str | None) -> SpeechResponseFormat | None:
    if value is None:
        return None
    if value not in _SPEECH_RESPONSE_FORMATS:
        raise ValueError(f"Unknown speech response format: {value}")
    return cast(SpeechResponseFormat, value)


def _supported_languages() -> list[CapabilityLanguage]:
    return list(CAPABILITY_LANGUAGES)


def _json_schema_block(schema: JsonObject) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)


def _schema_required(schema: JsonObject) -> set[str]:
    raw_required = schema.get("required")
    if not isinstance(raw_required, list):
        return set()
    return {item for item in raw_required if isinstance(item, str)}


def _schema_properties(schema: JsonObject) -> dict[str, dict[str, JsonValue]]:
    raw_properties = schema.get("properties")
    if not isinstance(raw_properties, dict):
        return {}
    properties: dict[str, dict[str, JsonValue]] = {}
    for name, raw_schema in raw_properties.items():
        if isinstance(name, str) and isinstance(raw_schema, dict):
            properties[name] = cast(dict[str, JsonValue], raw_schema)
    return properties


def _schema_enum_values(schema: dict[str, JsonValue]) -> list[JsonValue] | None:
    raw_enum = schema.get("enum")
    if isinstance(raw_enum, list):
        return cast(list[JsonValue], raw_enum)
    return None


def _schema_type(schema: dict[str, JsonValue]) -> str:
    if "$ref" in schema:
        ref = schema.get("$ref")
        if isinstance(ref, str) and "/" in ref:
            return ref.rsplit("/", 1)[-1]
        return "object"
    if "const" in schema:
        return "literal"
    enum_values = _schema_enum_values(schema)
    if enum_values:
        return "enum"
    raw_any_of = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(raw_any_of, list):
        types: list[str] = []
        for item in raw_any_of:
            if isinstance(item, dict):
                item_type = _schema_type(cast(dict[str, JsonValue], item))
                if item_type not in types:
                    types.append(item_type)
        return " | ".join(types) if types else "any"
    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        return " | ".join(str(item) for item in raw_type)
    if raw_type == "array":
        raw_items = schema.get("items")
        if isinstance(raw_items, dict):
            return f"array<{_schema_type(cast(dict[str, JsonValue], raw_items))}>"
        return "array"
    if isinstance(raw_type, str):
        return raw_type
    if schema.get("properties"):
        return "object"
    return "any"


def _schema_description(schema: dict[str, JsonValue]) -> str:
    raw_description = schema.get("description")
    return raw_description.strip() if isinstance(raw_description, str) else ""


def _schema_default(schema: dict[str, JsonValue]) -> tuple[bool, JsonValue]:
    if "default" not in schema:
        return False, None
    return True, schema.get("default")


def _schema_field_docs(schema: JsonObject) -> list[CapabilitySchemaFieldDocumentation]:
    fields: list[CapabilitySchemaFieldDocumentation] = []

    def visit(current_schema: dict[str, JsonValue], *, prefix: str, required_names: set[str]) -> None:
        for name, prop_schema in _schema_properties(cast(JsonObject, current_schema)).items():
            path = f"{prefix}.{name}" if prefix else name
            has_default, default_value = _schema_default(prop_schema)
            fields.append(
                CapabilitySchemaFieldDocumentation(
                    path=path,
                    name=name,
                    type=_schema_type(prop_schema),
                    required=name in required_names,
                    description=_schema_description(prop_schema),
                    has_default=has_default,
                    default_value=default_value,
                    enum_values=_schema_enum_values(prop_schema),
                )
            )
            child_required = _schema_required(cast(JsonObject, prop_schema))
            if _schema_properties(cast(JsonObject, prop_schema)):
                visit(prop_schema, prefix=path, required_names=child_required)
                continue
            raw_items = prop_schema.get("items")
            if isinstance(raw_items, dict) and _schema_properties(cast(JsonObject, raw_items)):
                visit(cast(dict[str, JsonValue], raw_items), prefix=f"{path}[]", required_names=_schema_required(cast(JsonObject, raw_items)))

    visit(cast(dict[str, JsonValue], schema), prefix="", required_names=_schema_required(schema))
    return fields


def _format_json_value(value: JsonValue) -> str:
    if value is None:
        return "`null`"
    return f"`{json.dumps(value, ensure_ascii=False, sort_keys=True)}`"


def _fields_table(fields: list[CapabilitySchemaFieldDocumentation], *, empty_text: str) -> list[str]:
    if not fields:
        return [empty_text]
    lines = [
        "| Field | Required | Type | Default | Description |",
        "|---|---:|---|---|---|",
    ]
    for field in fields:
        default_text = _format_json_value(field.default_value) if field.has_default else "—"
        description = field.description.replace("\n", " ").strip()
        if field.enum_values:
            enum_text = ", ".join(_format_json_value(item) for item in field.enum_values)
            description = f"{description} Enum: {enum_text}.".strip()
        lines.append(
            f"| `{field.path}` | {'yes' if field.required else 'no'} | `{field.type}` | {default_text} | {description or '—'} |"
        )
    return lines


def _go_exported_name(raw: str) -> str:
    parts: list[str] = []
    current: list[str] = []
    for ch in raw:
        if ch.isalnum():
            current.append(ch)
        elif current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    if not parts:
        return "Call"
    name = "".join(part[:1].upper() + part[1:] for part in parts)
    if name[:1].isdigit():
        name = f"Call{name}"
    return name


def _capability_sdk(capability: CapabilityDefinition) -> tuple[str, str]:
    if capability.sdk_namespace and capability.sdk_method:
        return capability.sdk_namespace, capability.sdk_method
    if "." not in capability.name:
        return "capabilities", capability.name
    namespace, method = capability.name.split(".", 1)
    return namespace, method


def _optional_string(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be string")
    stripped = value.strip()
    return stripped if stripped else None


def _required_string(value: JsonValue, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be non-empty string")
    return value.strip()


def _optional_int(value: JsonValue, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise TypeError(f"{name} must be integer")
    return value


def _optional_object(value: JsonValue, name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be object")
    return dict(value)


def _optional_array(value: JsonValue, name: str) -> list[Any] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise TypeError(f"{name} must be array")
    return list(value)


def _optional_bool(value: JsonValue, name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be boolean")
    return value


def _content_mode(value: str) -> ContentMode:
    if value not in {"auto", "markdown", "base64", "raw"}:
        raise ValueError("content_mode must be one of: auto, markdown, base64, raw")
    return cast(ContentMode, value)


def _active_company(context: Context) -> Company:
    if context.active_company is None:
        raise ValueError("Capability requires Context with active_company")
    return context.active_company


def _get_nested(data: dict[str, Any], path: str, default: JsonValue = None) -> JsonValue:
    current: Any = data
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
        if current is None:
            return default
    return cast(JsonValue, current)


def _set_nested(data: dict[str, Any], path: str, value: JsonValue) -> None:
    keys = [key for key in path.split(".") if key]
    if not keys:
        raise ValueError("path must be non-empty")
    current = data
    for key in keys[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value
    current[keys[-1]] = value


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _find_file(files: list[Any], name: str | None) -> JsonValue:
    candidates = [item for item in files if isinstance(item, dict)]
    if not candidates:
        return None
    if name is None:
        return cast(JsonValue, candidates[-1])
    for item in candidates:
        if item.get("name") == name or item.get("original_name") == name:
            return cast(JsonValue, item)
    name_lower = name.lower()
    for item in candidates:
        candidate_name = str(item.get("name") or item.get("original_name") or "").lower()
        if name_lower in candidate_name:
            return cast(JsonValue, item)
    return None


def _message_dict(*, role: Role, content: str, task_id: str | None) -> JsonObject:
    message = Message(
        message_id=str(uuid.uuid4()),
        role=role,
        parts=[Part(root=TextPart(text=content))],
        task_id=task_id,
        metadata={"node_id": MESSAGE_SOURCE_CAPABILITY},
    )
    return cast(JsonObject, message.model_dump(mode="json"))


def _append_ui_event(
    state: dict[str, JsonValue],
    *,
    event_type: str,
    payload: JsonObject,
    event_id: str | None = None,
    version: str = "1.0.0",
    source: str = "assistant",
    correlation_id: str | None = None,
) -> JsonObject:
    event: JsonObject = {
        "id": event_id or str(uuid.uuid4()),
        "type": event_type,
        "payload": payload,
        "version": version,
        "timestamp": datetime.now(UTC).isoformat(),
        "source": source,
        "correlation_id": correlation_id,
    }
    existing = state.get(UI_EVENTS_KEY)
    if not isinstance(existing, list):
        existing = []
        state[UI_EVENTS_KEY] = existing
    existing.append(event)
    return event


class CapabilityRegistry:
    """Регистрирует и исполняет platform capabilities."""

    def __init__(
        self,
        *,
        container: CapabilityGatewayContainerProtocol,
        context_service: CapabilityContextService,
        text_transform_service: TextTransformService,
    ):
        self._container: CapabilityGatewayContainerProtocol = container
        self._context_service: CapabilityContextService = context_service
        self._text_transform_service: TextTransformService = text_transform_service
        self._static_definitions: dict[str, CapabilityDefinition] = self._build_static_definitions()
        self._handlers: dict[str, CapabilityHandler] = {
            "files.create": self._files_create,
            "files.get_bytes": self._files_get_bytes,
            "files.get_metadata": self._files_get_metadata,
            "files.read": self._files_read,
            "http.request": self._http_request,
            "text.summarize": self._text_summarize,
            "text.format_markdown": self._text_format_markdown,
            "voice.transcribe_audio": self._voice_transcribe_audio,
            "voice.synthesize_speech": self._voice_synthesize_speech,
            "platform.request": self._platform_request,
            "trace.event": self._trace_event,
            "state.get_nested": self._state_get_nested,
            "state.set_nested": self._state_set_nested,
            "state.merge": self._state_merge,
            "state.get_files": self._state_get_files,
            "state.find_file": self._state_find_file,
            "state.get_user": self._state_get_user,
            "state.get_tool_result": self._state_get_tool_result,
            "state.get_messages": self._state_get_messages,
            "state.add_user_message": self._state_add_user_message,
            "state.add_agent_message": self._state_add_agent_message,
            "state.push_ui_event": self._state_push_ui_event,
            "state.push_ui_events": self._state_push_ui_events,
            "state.pop_ui_events": self._state_pop_ui_events,
            "state.extract_json": self._state_extract_json,
            "channel.send": self._channel_send,
            "channel.send_with_buttons": self._channel_send_with_buttons,
            "flow.ask_user": self._flow_ask_user,
            "tools.call": self._tools_call,
            "tools.call_builtin": self._tools_call_builtin,
        }
        for method in HTTP_METHODS:
            self._handlers[f"http.{method.lower()}"] = self._make_http_method_handler(method)
        for level in LOG_LEVELS:
            self._handlers[f"log.{level}"] = self._make_log_handler(level)
        definition_names = set(self._static_definitions)
        handler_names = set(self._handlers)
        if not definition_names.issubset(handler_names):
            missing_handlers = sorted(definition_names - handler_names)
            message = (
                "Capability registry mismatch: "
                f"missing_handlers={missing_handlers}"
            )
            raise ValueError(message)

    async def manifest(self) -> CapabilityManifest:
        definitions = dict(self._static_definitions)
        definitions.update(await self._load_tool_definitions())
        return CapabilityManifest(
            version="capabilities.v1",
            capabilities=[definitions[name] for name in sorted(definitions)],
        )

    async def documentation(self, *, language: CapabilityLanguage | None = None) -> CapabilityDocumentation:
        manifest = await self.manifest()
        language_note = (
            "all languages"
            if language is None
            else language
        )
        method_docs = self._sdk_method_docs(manifest, language=language)
        namespace_docs = self._namespace_docs(method_docs, language=language)
        lines = [
            "# Capability API",
            "",
            f"Version: `{manifest.version}`",
            f"Language: `{language_note}`",
            "",
            "User code calls platform SDK namespaces generated from the same manifest: "
            "`tools`, `files`, `http`, `text`, `voice`, `flow_state`, `log`, `trace`, `platform`, `channel`, `flow`.",
            "The structured `capabilities` and `namespaces` fields in this response are the backend source for editor autocomplete.",
            "If `entrypoint` is omitted, the runner executes the first function declared in the source. "
            "Node/tool configs may set any valid language function name via `entrypoint`.",
        ]
        if language is not None:
            lines.extend(["", "Entry point:", "", *self._entrypoint_block(language)])
        if namespace_docs:
            lines.extend(["", "## SDK namespaces", ""])
            for namespace in namespace_docs:
                methods = ", ".join(f"`{method}`" for method in namespace.methods)
                lines.append(f"- `{namespace.name}` ({namespace.type}): {methods}")
        for method_doc in method_docs:
            capability = next(item for item in manifest.capabilities if item.name == method_doc.capability_name)
            lines.extend(self._capability_markdown_section(capability, method_doc, language=language))
        return CapabilityDocumentation(
            version=manifest.version,
            markdown="\n".join(lines),
            language=language,
            namespaces=namespace_docs,
            capabilities=method_docs,
        )

    def _sdk_method_docs(
        self,
        manifest: CapabilityManifest,
        *,
        language: CapabilityLanguage | None,
    ) -> list[CapabilitySdkMethodDocumentation]:
        docs: list[CapabilitySdkMethodDocumentation] = []
        for capability in manifest.capabilities:
            if language is not None and language not in capability.languages:
                continue
            effective_language = language or "python"
            docs.append(self._sdk_method_doc(capability, language=effective_language))
        return docs

    def _namespace_docs(
        self,
        method_docs: list[CapabilitySdkMethodDocumentation],
        *,
        language: CapabilityLanguage | None,
    ) -> list[CapabilityNamespaceDocumentation]:
        grouped: dict[str, list[CapabilitySdkMethodDocumentation]] = {}
        for doc in method_docs:
            grouped.setdefault(doc.namespace, []).append(doc)
        namespace_type = self._namespace_type(language or "python")
        namespaces: list[CapabilityNamespaceDocumentation] = []
        for namespace, docs in sorted(grouped.items()):
            docs_sorted = sorted(docs, key=lambda item: item.method)
            namespaces.append(
                CapabilityNamespaceDocumentation(
                    name=namespace,
                    type=namespace_type,
                    methods=[item.method for item in docs_sorted],
                    capability_names=[item.capability_name for item in docs_sorted],
                )
            )
        return namespaces

    def _namespace_type(self, language: CapabilityLanguage) -> str:
        if language == "go":
            return "generated Go package-level namespace value"
        if language == "csharp":
            return "generated C# static namespace property"
        if language == "python":
            return "generated async namespace object"
        return "generated async namespace proxy"

    def _sdk_method_doc(
        self,
        capability: CapabilityDefinition,
        *,
        language: CapabilityLanguage,
    ) -> CapabilitySdkMethodDocumentation:
        namespace, method = _capability_sdk(capability)
        input_fields = _schema_field_docs(capability.input_schema)
        output_fields = _schema_field_docs(capability.output_schema)
        label = f"{namespace}.{self._language_method_name(language, method)}"
        signature = self._signature(language, namespace, method, input_fields)
        insert_text = self._insert_text(language, namespace, method, capability)
        documentation = "\n".join(
            [
                f"### `{label}`",
                "",
                capability.description,
                "",
                f"Capability: `{capability.name}`",
                "",
                "Parameters:",
                "",
                *_fields_table(input_fields, empty_text="No named parameters."),
                "",
                "Returns:",
                "",
                *_fields_table(output_fields, empty_text="Free-form JSON result. See output_schema."),
            ]
        )
        return CapabilitySdkMethodDocumentation(
            capability_name=capability.name,
            namespace=namespace,
            method=self._language_method_name(language, method),
            label=label,
            title=capability.title,
            description=capability.description,
            signature=signature,
            insert_text=insert_text,
            documentation=documentation,
            tags=capability.tags,
            input_schema=capability.input_schema,
            output_schema=capability.output_schema,
            input_fields=input_fields,
            output_fields=output_fields,
        )

    def _language_method_name(self, language: CapabilityLanguage, method: str) -> str:
        if language in {"go", "csharp"}:
            return _go_exported_name(method)
        return method

    def _top_level_fields(
        self,
        fields: list[CapabilitySchemaFieldDocumentation],
    ) -> list[CapabilitySchemaFieldDocumentation]:
        return [field for field in fields if "." not in field.path and "[]" not in field.path]

    def _signature(
        self,
        language: CapabilityLanguage,
        namespace: str,
        method: str,
        fields: list[CapabilitySchemaFieldDocumentation],
    ) -> str:
        method_name = self._language_method_name(language, method)
        top_fields = self._top_level_fields(fields)
        args = ", ".join(
            f"{field.name}{'' if field.required else '?'}: {field.type}"
            for field in top_fields
        )
        if language == "python":
            return f"await {namespace}.{method_name}({args})"
        if language in {"javascript", "typescript"}:
            return f"await {namespace}.{method_name}({{{args}}})"
        if language == "go":
            return f"{namespace}.{method_name}(map[string]any{{...}}) (any, error)"
        return f"await {namespace}.{method_name}(new Dictionary<string, object?> {{ ... }})"

    def _insert_text(
        self,
        language: CapabilityLanguage,
        namespace: str,
        method: str,
        capability: CapabilityDefinition,
    ) -> str:
        kwargs = self._sample_kwargs(capability, language)
        method_name = self._language_method_name(language, method)
        if language == "python":
            python_kwargs = ", ".join(f"{key}={value}" for key, value in kwargs.items())
            return f"await {namespace}.{method_name}({python_kwargs})"
        if language in {"javascript", "typescript"}:
            js_kwargs = ", ".join(f"{key}: {value}" for key, value in kwargs.items())
            return f"await {namespace}.{method_name}({{{js_kwargs}}})"
        if language == "go":
            go_kwargs = ", ".join(f"\"{key}\": {value}" for key, value in kwargs.items())
            return f"{namespace}.{method_name}(map[string]any{{{go_kwargs}}})"
        csharp_kwargs = ", ".join(f"[\"{key}\"] = {value}" for key, value in kwargs.items())
        return f"await {namespace}.{method_name}(new Dictionary<string, object?> {{ {csharp_kwargs} }})"

    def _capability_markdown_section(
        self,
        capability: CapabilityDefinition,
        method_doc: CapabilitySdkMethodDocumentation,
        *,
        language: CapabilityLanguage | None,
    ) -> list[str]:
        lines = [
            "",
            f"## `{capability.name}`",
            "",
            capability.description,
            "",
            f"SDK: `{method_doc.label}`",
            "",
            f"Signature: `{method_doc.signature}`",
            "",
            f"Languages: {', '.join(capability.languages)}",
        ]
        if language is not None:
            lines.extend(["", "Usage:", "", *self._usage_block(language, capability)])
        lines.extend(
            [
                "",
                "### Parameters",
                "",
                *_fields_table(method_doc.input_fields, empty_text="No named parameters."),
                "",
                "### Returns",
                "",
                *_fields_table(method_doc.output_fields, empty_text="Free-form JSON result. See output schema."),
                "",
                "<details>",
                "<summary>Input JSON Schema</summary>",
                "",
                "```json",
                _json_schema_block(capability.input_schema),
                "```",
                "",
                "</details>",
                "",
                "<details>",
                "<summary>Output JSON Schema</summary>",
                "",
                "```json",
                _json_schema_block(capability.output_schema),
                "```",
                "",
                "</details>",
            ]
        )
        return lines

    async def _load_tool_definitions(self) -> dict[str, CapabilityDefinition]:
        raw_manifest = await self._container.service_client.get(
            "flows",
            TOOL_RUNTIME_MANIFEST_PATH,
            timeout=30.0,
        )
        manifest = CapabilityManifest.model_validate(raw_manifest)
        return {capability.name: capability for capability in manifest.capabilities}

    def _entrypoint_block(self, language: CapabilityLanguage) -> list[str]:
        if language == "python":
            return [
                "```python",
                "async def run(args, state):",
                "    result = await tools.calculator(expression=\"2+2\")",
                "    return {\"result\": result}",
                "```",
            ]
        if language == "go":
            return [
                "```go",
                "package main",
                "",
                "func run(args map[string]any, state map[string]any) (any, error) {",
                "    result, err := tools.Calculator(map[string]any{\"expression\": \"2+2\"})",
                "    if err != nil {",
                "        return nil, err",
                "    }",
                "    return map[string]any{\"result\": result}, nil",
                "}",
                "```",
            ]
        if language == "csharp":
            return [
                "```csharp",
                "using System.Collections.Generic;",
                "using System.Threading.Tasks;",
                "",
                "async Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)",
                "{",
                "    var result = await tools.Calculator(new Dictionary<string, object?> { [\"expression\"] = \"2+2\" });",
                "    return new Dictionary<string, object?> { [\"result\"] = result };",
                "}",
                "```",
            ]
        fence = "typescript" if language == "typescript" else "javascript"
        return [
            f"```{fence}",
            "async function run(args, state) {",
            "  const result = await tools.calculator({expression: \"2+2\"});",
            "  return {result};",
            "}",
            "```",
        ]

    def _usage_block(self, language: CapabilityLanguage, capability: CapabilityDefinition) -> list[str]:
        kwargs = self._sample_kwargs(capability, language)
        namespace, method = _capability_sdk(capability)
        if language == "python":
            python_kwargs = ", ".join(f"{key}={value}" for key, value in kwargs.items())
            return [
                "```python",
                f"result = await {namespace}.{method}({python_kwargs})",
                "```",
            ]
        if language == "go":
            go_kwargs = ", ".join(f"\"{key}\": {value}" for key, value in kwargs.items())
            return [
                "```go",
                f"result, err := {namespace}.{_go_exported_name(method)}(map[string]any{{{go_kwargs}}})",
                "```",
            ]
        if language == "csharp":
            csharp_kwargs = ", ".join(f"[\"{key}\"] = {value}" for key, value in kwargs.items())
            return [
                "```csharp",
                f"var result = await {namespace}.{_go_exported_name(method)}(new Dictionary<string, object?> {{ {csharp_kwargs} }});",
                "```",
            ]
        js_kwargs = ", ".join(f"{key}: {value}" for key, value in kwargs.items())
        fence = "typescript" if language == "typescript" else "javascript"
        return [
            f"```{fence}",
            f"const result = await {namespace}.{method}({{{js_kwargs}}});",
            "```",
        ]

    def _sample_kwargs(
        self,
        capability: CapabilityDefinition,
        language: CapabilityLanguage,
    ) -> dict[str, str]:
        properties = capability.input_schema.get("properties")
        required = capability.input_schema.get("required")
        if not isinstance(properties, dict) or not isinstance(required, list):
            return {}
        kwargs: dict[str, str] = {}
        for raw_name in required:
            if not isinstance(raw_name, str):
                continue
            raw_schema = properties.get(raw_name)
            schema = raw_schema if isinstance(raw_schema, dict) else {}
            kwargs[raw_name] = self._sample_literal(schema, language)
        return kwargs

    def _sample_literal(self, schema: dict[str, JsonValue], language: CapabilityLanguage) -> str:
        schema_type = schema.get("type")
        if schema_type == "integer":
            return "1"
        if schema_type == "number":
            return "1.0"
        if schema_type == "boolean":
            return "True" if language == "python" else "true"
        if schema_type == "object":
            if language == "go":
                return "map[string]any{}"
            if language == "csharp":
                return "new Dictionary<string, object?>()"
            return "{}"
        if schema_type == "array":
            if language == "go":
                return "[]any{}"
            if language == "csharp":
                return "new List<object?>()"
            return "[]"
        return "\"value\""

    async def call(self, request: CapabilityCallRequest) -> CapabilityCallResponse:
        verify_execution_context(request.context)
        handler = self._handlers.get(request.name)
        if handler is None and request.name.startswith("tools."):
            handler = self._tool_capability_call
        if handler is None:
            raise ValueError(f"Unknown capability: {request.name}")
        async with traced_operation(
            "capability_gateway.capability.call",
            event_type="capability.call",
            operation_category="capability",
            resource_type="flow",
            resource_id=request.context.flow_id,
            extra_attributes={
                "platform.capability.name": request.name,
                "platform.flow.branch_id": request.context.branch_id,
                "platform.flow.session_id": request.context.session_id,
                "platform.flow.task_id": request.context.task_id,
                "platform.flow.context_id": request.context.context_id,
            },
        ):
            try:
                capability_result = await handler(request)
            except _CapabilityInterruptFromTool as exc:
                return CapabilityCallResponse(
                    status="interrupt",
                    state=request.state,
                    interrupt=CapabilityInterruptEnvelope.model_validate(exc.interrupt),
                )
        return CapabilityCallResponse(status="ok", result=capability_result, state=request.state)

    async def _tool_capability_call(self, request: CapabilityCallRequest) -> JsonValue:
        tool_id = request.name.removeprefix("tools.")
        if not tool_id:
            raise ValueError("Tool capability name must be tools.<tool_id>")
        forwarded = request.model_copy(
            update={
                "name": "tools.call",
                "kwargs": {
                    "tool_id": tool_id,
                    "arguments": dict(request.kwargs),
                },
            }
        )
        return await self._tools_call(forwarded)

    def _build_static_definitions(self) -> dict[str, CapabilityDefinition]:
        definitions = {
            "files.create": CapabilityDefinition(
                name="files.create",
                title="Create persisted platform file",
                description=(
                    "Создаёт файл в платформенном S3/FileRepository и возвращает file_id/url. "
                    "Поддерживает raw, markdown, base64 и auto content modes как platform tool create_file."
                ),
                input_schema=_schema_object(
                    properties={
                        "content": _string_schema("Текст, Markdown или base64 содержимое файла"),
                        "original_name": _string_schema("Имя файла с расширением"),
                        "content_mode": _string_schema("auto, markdown, base64 или raw"),
                    },
                    required=["content", "original_name"],
                ),
                output_schema=_schema_object(
                    properties={
                        "file_id": _string_schema("ID файла в FileRepository"),
                        "url": _string_schema("Относительный URL скачивания"),
                        "original_name": _string_schema("Оригинальное имя"),
                        "content_type": _string_schema("MIME type"),
                        "file_size": _integer_schema("Размер в байтах"),
                    },
                    required=["file_id", "url", "original_name", "content_type", "file_size"],
                ),
                languages=_supported_languages(),
                tags=["files", "s3", "storage"],
                sdk_namespace="files",
                sdk_method="create",
            ),
            "files.get_bytes": CapabilityDefinition(
                name="files.get_bytes",
                title="Read persisted file bytes",
                description="Возвращает содержимое persisted-файла как base64 и метаданные FileRepository.",
                input_schema=_schema_object(
                    properties={
                        "file_id": _string_schema("ID файла в FileRepository"),
                    },
                    required=["file_id"],
                ),
                output_schema=_schema_object(
                    properties={
                        "content_base64": _string_schema("Base64 содержимого файла"),
                        "content_type": _string_schema("MIME type файла"),
                        "file_name": _string_schema("Оригинальное имя файла"),
                    },
                    required=["content_base64", "content_type", "file_name"],
                ),
                languages=_supported_languages(),
                tags=["files"],
                sdk_namespace="files",
                sdk_method="get_bytes",
            ),
            "files.get_metadata": CapabilityDefinition(
                name="files.get_metadata",
                title="Get persisted file metadata",
                description="Возвращает metadata persisted-файла из FileRepository без скачивания содержимого.",
                input_schema=_schema_object(
                    properties={
                        "file_id": _string_schema("ID файла в FileRepository"),
                    },
                    required=["file_id"],
                ),
                output_schema=_schema_object(
                    properties={
                        "file_id": _string_schema("ID файла"),
                        "url": _string_schema("Относительный URL скачивания"),
                        "original_name": _string_schema("Оригинальное имя"),
                        "content_type": _string_schema("MIME type"),
                        "file_size": _integer_schema("Размер в байтах"),
                    },
                    required=["file_id", "url", "original_name", "content_type", "file_size"],
                ),
                languages=_supported_languages(),
                tags=["files", "metadata"],
                sdk_namespace="files",
                sdk_method="get_metadata",
            ),
            "files.read": CapabilityDefinition(
                name="files.read",
                title="Read persisted file as structured document",
                description=(
                    "Читает persisted-файл через core.files.reader.FileReader и возвращает FileReadResult: "
                    "pages, page_count, detected_kind, mime_type, warnings, source checksum/file_id."
                ),
                input_schema=_schema_object(
                    properties={
                        "file_id": _string_schema("ID файла в FileRepository"),
                        "file_name": _string_schema("Опциональное имя с расширением"),
                        "include_asset_bytes": _boolean_schema("Включать base64 ассетов PDF/Office"),
                        "vision_prompt": _string_schema("Опциональная инструкция для image/vision чтения"),
                        "vision_model": _string_schema("Опциональная vision-модель"),
                    },
                    required=["file_id"],
                ),
                output_schema=_object_schema("FileReadResult JSON"),
                languages=_supported_languages(),
                tags=["files", "reader", "documents"],
                sdk_namespace="files",
                sdk_method="read",
            ),
            "http.request": CapabilityDefinition(
                name="http.request",
                title="HTTP request",
                description=(
                    "Выполняет внешний HTTP/HTTPS запрос из capability-gateway. "
                    "Для platform services используй tools.<tool_id>/ServiceClient-backed tools, не raw HTTP."
                ),
                input_schema=_schema_object(
                    properties={
                        "method": _string_schema("HTTP method: GET, POST, PUT, PATCH, DELETE, HEAD"),
                        "url": _string_schema("Абсолютный http/https URL"),
                        "headers": _object_schema("Опциональные HTTP headers"),
                        "params": _object_schema("Опциональные query parameters"),
                        "json": _object_schema("Опциональное JSON body"),
                        "body": _string_schema("Опциональное string body"),
                        "timeout_seconds": _integer_schema("Timeout in seconds"),
                    },
                    required=["method", "url"],
                ),
                output_schema=_schema_object(
                    properties={
                        "status_code": _integer_schema("HTTP status code"),
                        "headers": _object_schema("Response headers"),
                        "body_text": _string_schema("Response body decoded as text"),
                    },
                    required=["status_code", "headers", "body_text"],
                ),
                languages=_supported_languages(),
                tags=["http", "web"],
                sdk_namespace="http",
                sdk_method="request",
            ),
            "text.summarize": CapabilityDefinition(
                name="text.summarize",
                title="Summarize text",
                description="Суммаризирует текст через платформенный LLM routing с billing.",
                input_schema=_schema_object(
                    properties={
                        "text": _string_schema("Текст для суммаризации"),
                        "instruction": _string_schema("Опциональная инструкция"),
                        "provider": _string_schema("Опциональный LLM provider"),
                        "model": _string_schema("Опциональная модель"),
                        "max_output_tokens": _integer_schema("Лимит выходных токенов"),
                    },
                    required=["text"],
                ),
                output_schema=_schema_object(
                    properties={
                        "summary": _string_schema("Суммаризация"),
                    },
                    required=["summary"],
                ),
                languages=_supported_languages(),
                tags=["text", "llm", "billing"],
                sdk_namespace="text",
                sdk_method="summarize",
            ),
            "text.format_markdown": CapabilityDefinition(
                name="text.format_markdown",
                title="Format text as Markdown",
                description="Форматирует plain text в Markdown через платформенный LLM/LitServe routing с billing.",
                input_schema=_schema_object(
                    properties={
                        "text": _string_schema("Исходный текст"),
                        "provider": _string_schema("Опциональный LLM provider"),
                        "model": _string_schema("Опциональная модель"),
                        "max_chunk_chars": _integer_schema("Размер чанка"),
                    },
                    required=["text"],
                ),
                output_schema=_schema_object(
                    properties={
                        "markdown": _string_schema("Markdown результат"),
                    },
                    required=["markdown"],
                ),
                languages=_supported_languages(),
                tags=["text", "markdown", "llm", "billing"],
                sdk_namespace="text",
                sdk_method="format_markdown",
            ),
            "voice.transcribe_audio": CapabilityDefinition(
                name="voice.transcribe_audio",
                title="Transcribe persisted audio",
                description=(
                    "Распознаёт persisted-аудио из FileRepository/S3 через voice_resolver "
                    "и записывает STT usage/billing."
                ),
                input_schema=_schema_object(
                    properties={
                        "file_id": _string_schema("ID аудио-файла в FileRepository"),
                        "language": _string_schema("Опциональный BCP-47 язык распознавания"),
                        "provider": _string_schema("Опциональный STT provider"),
                        "model": _string_schema("Опциональная STT модель"),
                    },
                    required=["file_id"],
                ),
                output_schema=_schema_object(
                    properties={
                        "text": _string_schema("Распознанный текст"),
                    },
                    required=["text"],
                ),
                languages=_supported_languages(),
                tags=["voice", "stt", "billing"],
                sdk_namespace="voice",
                sdk_method="transcribe_audio",
            ),
            "voice.synthesize_speech": CapabilityDefinition(
                name="voice.synthesize_speech",
                title="Synthesize speech",
                description=(
                    "Синтезирует речь через voice_resolver, сохраняет аудио в FileRepository/S3 "
                    "и записывает TTS usage/billing."
                ),
                input_schema=_schema_object(
                    properties={
                        "text": _string_schema("Текст для озвучивания"),
                        "voice": _string_schema("Опциональный голос"),
                        "language": _string_schema("Опциональный BCP-47 язык"),
                        "provider": _string_schema("Опциональный TTS provider"),
                        "model": _string_schema("Опциональная TTS модель"),
                        "response_format": _string_schema("wav, mp3, ogg, pcm или lpcm"),
                        "file_name": _string_schema("Опциональное имя сохраняемого файла"),
                    },
                    required=["text"],
                ),
                output_schema=_schema_object(
                    properties={
                        "file_id": _string_schema("ID созданного аудио-файла"),
                    },
                    required=["file_id"],
                ),
                languages=_supported_languages(),
                tags=["voice", "tts", "billing", "files"],
                sdk_namespace="voice",
                sdk_method="synthesize_speech",
            ),
        }
        for method in HTTP_METHODS:
            name = f"http.{method.lower()}"
            definitions[name] = CapabilityDefinition(
                name=name,
                title=f"HTTP {method}",
                description=f"Удобная обёртка над http.request с method={method}.",
                input_schema=_schema_object(
                    properties={
                        "url": _string_schema("Абсолютный http/https URL"),
                        "headers": _object_schema("Опциональные HTTP headers"),
                        "params": _object_schema("Опциональные query parameters"),
                        "json": _object_schema("Опциональное JSON body"),
                        "body": _string_schema("Опциональное string body"),
                        "timeout_seconds": _integer_schema("Timeout in seconds"),
                    },
                    required=["url"],
                ),
                output_schema=definitions["http.request"].output_schema,
                languages=_supported_languages(),
                tags=["http", "web"],
                sdk_namespace="http",
                sdk_method=method.lower(),
            )
        definitions.update(
            {
                "platform.request": CapabilityDefinition(
                    name="platform.request",
                    title="ServiceClient platform request",
                    description=(
                        "Выполняет HTTP-запрос к внутреннему platform service через ServiceClient "
                        "с context headers (trace/request/company/user/auth)."
                    ),
                    input_schema=_schema_object(
                        properties={
                            "service": _string_schema("Имя сервиса из конфигурации, например flows или capability_gateway"),
                            "method": _string_schema("HTTP method"),
                            "path": _string_schema("Путь с ведущим /"),
                            "headers": _object_schema("Опциональные headers"),
                            "params": _object_schema("Опциональные query parameters"),
                            "json": _object_schema("Опциональное JSON body"),
                            "body": _string_schema("Опциональное string body"),
                            "timeout_seconds": _integer_schema("Timeout in seconds"),
                        },
                        required=["service", "method", "path"],
                    ),
                    output_schema=_json_schema("JSON-ответ platform service или null"),
                    languages=_supported_languages(),
                    tags=["platform", "http", "service-client"],
                    sdk_namespace="platform",
                    sdk_method="request",
                ),
                "trace.event": CapabilityDefinition(
                    name="trace.event",
                    title="Record custom trace event span",
                    description="Создаёт короткий traced span с developer-defined event_type и attributes.",
                    input_schema=_schema_object(
                        properties={
                            "event_type": _string_schema("Тип события trace"),
                            "attributes": _object_schema("Дополнительные JSON attributes"),
                        },
                        required=["event_type"],
                    ),
                    output_schema=_schema_object(
                        properties={"recorded": _boolean_schema("True если span создан")},
                        required=["recorded"],
                    ),
                    languages=_supported_languages(),
                    tags=["trace", "observability"],
                    sdk_namespace="trace",
                    sdk_method="event",
                ),
                "flow.ask_user": CapabilityDefinition(
                    name="flow.ask_user",
                    title="Interrupt flow and ask user",
                    description="Останавливает выполнение и возвращает FlowInterrupt envelope с вопросом пользователю.",
                    input_schema=_schema_object(
                        properties={"question": _string_schema("Вопрос пользователю")},
                        required=["question"],
                    ),
                    output_schema=_schema_object(
                        properties={"interrupt": _object_schema("Capability interrupt envelope")},
                        required=[],
                    ),
                    languages=_supported_languages(),
                    tags=["flow", "interrupt", "user"],
                    sdk_namespace="flow",
                    sdk_method="ask_user",
                ),
            }
        )
        for level in LOG_LEVELS:
            name = f"log.{level}"
            definitions[name] = CapabilityDefinition(
                name=name,
                title=f"Log {level}",
                description=f"Пишет structured log уровня {level} из sandbox-кода с request_id/trace_id.",
                input_schema=_schema_object(
                    properties={
                        "message": _string_schema("Сообщение"),
                        "fields": _object_schema("Дополнительные JSON-поля"),
                    },
                    required=["message"],
                ),
                output_schema=_schema_object(
                    properties={"logged": _boolean_schema("True если log записан")},
                    required=["logged"],
                ),
                languages=_supported_languages(),
                tags=["logging", "observability"],
                sdk_namespace="log",
                sdk_method=level,
            )
        definitions.update(self._state_definitions())
        definitions.update(
            {
                "channel.send": CapabilityDefinition(
                    name="channel.send",
                    title="Queue user-visible channel message",
                    description=(
                        "Добавляет agent message в state.messages и ставит ui_event channel.message. "
                        "Flow runtime опубликует pending UI events после завершения ноды."
                    ),
                    input_schema=_schema_object(
                        properties={"content": _string_schema("Текст сообщения")},
                        required=["content"],
                    ),
                    output_schema=_schema_object(
                        properties={"queued": _boolean_schema("True если сообщение поставлено в state")},
                        required=["queued"],
                    ),
                    languages=_supported_languages(),
                    tags=["channel", "messages", "streaming"],
                    sdk_namespace="channel",
                    sdk_method="send",
                ),
                "channel.send_with_buttons": CapabilityDefinition(
                    name="channel.send_with_buttons",
                    title="Queue user-visible channel message with buttons",
                    description="То же что channel.send, но payload ui_event содержит quick-reply buttons.",
                    input_schema=_schema_object(
                        properties={
                            "content": _string_schema("Текст сообщения"),
                            "buttons": _array_schema("Список строк-кнопок"),
                        },
                        required=["content", "buttons"],
                    ),
                    output_schema=_schema_object(
                        properties={"queued": _boolean_schema("True если сообщение поставлено в state")},
                        required=["queued"],
                    ),
                    languages=_supported_languages(),
                    tags=["channel", "messages", "streaming"],
                    sdk_namespace="channel",
                    sdk_method="send_with_buttons",
                ),
            }
        )
        return definitions

    def _state_definitions(self) -> dict[str, CapabilityDefinition]:
        specs: list[tuple[str, str, str, JsonObject, JsonObject]] = [
            (
                "get_nested",
                "Get nested state value",
                "Возвращает значение из state по dot-path.",
                _schema_object(
                    properties={
                        "path": _string_schema("Dot-path, например user.profile.name"),
                        "default": _json_schema("Значение по умолчанию"),
                    },
                    required=["path"],
                ),
                _json_schema("Найденное значение или default"),
            ),
            (
                "set_nested",
                "Set nested state value",
                "Мутирует state по dot-path и возвращает установленное значение.",
                _schema_object(
                    properties={
                        "path": _string_schema("Dot-path"),
                        "value": _json_schema("JSON-значение"),
                    },
                    required=["path", "value"],
                ),
                _schema_object(
                    properties={"value": _json_schema("Установленное значение")},
                    required=["value"],
                ),
            ),
            (
                "merge",
                "Deep merge state",
                "Глубоко мержит JSON object в state.",
                _schema_object(
                    properties={"updates": _object_schema("Обновления state")},
                    required=["updates"],
                ),
                _schema_object(
                    properties={"state": _object_schema("Обновленный state")},
                    required=["state"],
                ),
            ),
            (
                "get_files",
                "Get state files",
                "Возвращает state.files как список JSON объектов.",
                _schema_object(properties={}, required=[]),
                _array_schema("Список файлов"),
            ),
            (
                "find_file",
                "Find state file",
                "Ищет файл в state.files по имени; без имени возвращает последний файл.",
                _schema_object(
                    properties={"name": _string_schema("Опциональное имя файла")},
                    required=[],
                ),
                _json_schema("Найденный file object или null"),
            ),
            (
                "get_user",
                "Get state user summary",
                "Возвращает user_id и user_groups из state.",
                _schema_object(properties={}, required=[]),
                _object_schema("User summary"),
            ),
            (
                "get_tool_result",
                "Get tool result from state",
                "Возвращает state.tool_results[tool_name].",
                _schema_object(
                    properties={"tool_name": _string_schema("Имя tool")},
                    required=["tool_name"],
                ),
                _json_schema("Результат tool или null"),
            ),
            (
                "get_messages",
                "Get state messages",
                "Возвращает state.messages.",
                _schema_object(properties={}, required=[]),
                _array_schema("A2A messages"),
            ),
            (
                "add_user_message",
                "Append user message",
                "Добавляет A2A user message в state.messages.",
                _schema_object(
                    properties={"content": _string_schema("Текст сообщения")},
                    required=["content"],
                ),
                _object_schema("Созданное сообщение"),
            ),
            (
                "add_agent_message",
                "Append agent message",
                "Добавляет A2A agent message в state.messages.",
                _schema_object(
                    properties={"content": _string_schema("Текст сообщения")},
                    required=["content"],
                ),
                _object_schema("Созданное сообщение"),
            ),
            (
                "push_ui_event",
                "Push one UI event",
                "Добавляет одно pending UI event в state.ui_events_pending.",
                _schema_object(
                    properties={
                        "event_type": _string_schema("Тип события"),
                        "payload": _object_schema("Payload события"),
                        "event_id": _string_schema("Опциональный id"),
                        "version": _string_schema("Версия события"),
                        "source": _string_schema("Источник"),
                        "correlation_id": _string_schema("Опциональный correlation id"),
                    },
                    required=["event_type", "payload"],
                ),
                _object_schema("Созданное событие"),
            ),
            (
                "push_ui_events",
                "Push many UI events",
                "Добавляет несколько pending UI events в state.ui_events_pending.",
                _schema_object(
                    properties={"events": _array_schema("Список UI event objects")},
                    required=["events"],
                ),
                _array_schema("Созданные события"),
            ),
            (
                "pop_ui_events",
                "Pop pending UI events",
                "Возвращает и очищает state.ui_events_pending.",
                _schema_object(properties={}, required=[]),
                _array_schema("Извлеченные события"),
            ),
            (
                "extract_json",
                "Extract JSON from text",
                "Извлекает JSON object/array из текста или fenced markdown блока.",
                _schema_object(
                    properties={"text": _string_schema("Текст с JSON")},
                    required=["text"],
                ),
                _json_schema("JSON object/array или null"),
            ),
        ]
        return {
            f"state.{method}": CapabilityDefinition(
                name=f"state.{method}",
                title=title,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
                languages=_supported_languages(),
                tags=["state", "utility"],
                sdk_namespace="flow_state",
                sdk_method=method,
            )
            for method, title, description, input_schema, output_schema in specs
        }

    async def _files_create(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        content = _required_string(request.kwargs.get("content"), "content")
        original_name = _required_string(request.kwargs.get("original_name"), "original_name")
        content_mode = _content_mode(
            _optional_string(request.kwargs.get("content_mode"), "content_mode") or "auto"
        )

        context = await self._context_service.build_context(request.context)
        writer = FileWriter.bind_for_upload(
            file_processor=self._container.file_processor,
            download_url_prefix="/flows/api/v1/files/download",
        )
        with self._context_service.activate(context):
            try:
                record = await writer.write(
                    content=content,
                    original_name=original_name,
                    content_mode=content_mode,
                    public=True,
                )
            except FileWriteError as exc:
                raise ValueError(str(exc)) from exc

        response = FileResponse.from_record(record)
        return response.model_dump(mode="json")

    async def _files_get_bytes(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        file_id = _required_string(request.kwargs.get("file_id"), "file_id")
        record = await self._container.file_repository.get(file_id)
        if record is None:
            raise ValueError(f"File not found: {file_id}")

        s3_client = S3ClientFactory.create_client_for_bucket(record.s3_bucket)
        try:
            content = await s3_client.download_bytes(record.s3_key, bucket=record.s3_bucket)
        finally:
            await s3_client.close()

        return {
            "content_base64": base64.b64encode(content).decode("ascii"),
            "content_type": record.content_type,
            "file_name": record.original_name,
        }

    async def _files_get_metadata(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        file_id = _required_string(request.kwargs.get("file_id"), "file_id")
        record = await self._container.file_repository.get(file_id)
        if record is None:
            raise ValueError(f"File not found: {file_id}")
        return FileResponse.from_record(record).model_dump(mode="json")

    async def _files_read(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        file_id = _required_string(request.kwargs.get("file_id"), "file_id")
        file_name = _optional_string(request.kwargs.get("file_name"), "file_name")
        include_asset_bytes = _optional_bool(
            request.kwargs.get("include_asset_bytes"),
            "include_asset_bytes",
        ) or False
        vision_prompt = _optional_string(request.kwargs.get("vision_prompt"), "vision_prompt")
        vision_model = _optional_string(request.kwargs.get("vision_model"), "vision_model")
        context = await self._context_service.build_context(request.context)
        with self._context_service.activate(context):
            try:
                result = await FileReader().read(
                    file_id,
                    file_name=file_name,
                    include_asset_bytes=include_asset_bytes,
                    source_file_id=file_id,
                    vision_prompt=vision_prompt,
                    vision_model=vision_model or "google/gemini-2.5-flash-preview",
                )
            except FileReadError as exc:
                raise ValueError(str(exc)) from exc
        return result.model_dump(mode="json")

    def _make_http_method_handler(self, method: str) -> CapabilityHandler:
        async def _handler(request: CapabilityCallRequest) -> JsonValue:
            forwarded = request.model_copy(
                update={"kwargs": {"method": method, **dict(request.kwargs)}}
            )
            return await self._http_request(forwarded)

        return _handler

    async def _http_request(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        method = _required_string(request.kwargs.get("method"), "method").upper()
        url = _required_string(request.kwargs.get("url"), "url")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute http/https URL")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
            raise ValueError(f"Unsupported HTTP method: {method}")
        headers = _optional_object(request.kwargs.get("headers"), "headers") or {}
        params = _optional_object(request.kwargs.get("params"), "params") or {}
        json_body = _optional_object(request.kwargs.get("json"), "json")
        body = _optional_string(request.kwargs.get("body"), "body")
        timeout_seconds = _optional_int(request.kwargs.get("timeout_seconds"), "timeout_seconds") or 30
        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise ValueError("timeout_seconds must be between 1 and 120")
        if json_body is not None and body is not None:
            raise ValueError("Pass either json or body, not both")
        async with httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=True) as client:
            response = await client.request(
                method,
                url,
                headers={str(k): str(v) for k, v in headers.items()},
                params=params,
                json=json_body,
                content=body,
            )
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body_text": response.text,
        }

    async def _platform_request(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        service = _required_string(request.kwargs.get("service"), "service")
        method = _required_string(request.kwargs.get("method"), "method").upper()
        path = _required_string(request.kwargs.get("path"), "path")
        if not path.startswith("/"):
            raise ValueError("path must start with /")
        if method not in HTTP_METHODS:
            raise ValueError(f"Unsupported HTTP method: {method}")
        headers = _optional_object(request.kwargs.get("headers"), "headers")
        params = _optional_object(request.kwargs.get("params"), "params")
        json_body = _optional_object(request.kwargs.get("json"), "json")
        body = _optional_string(request.kwargs.get("body"), "body")
        timeout_seconds = _optional_int(request.kwargs.get("timeout_seconds"), "timeout_seconds") or 30
        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise ValueError("timeout_seconds must be between 1 and 120")
        kwargs: dict[str, Any] = {}
        if headers is not None:
            kwargs["headers"] = {str(key): str(value) for key, value in headers.items()}
        if params is not None:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body
        if body is not None:
            kwargs["content"] = body
        context = await self._context_service.build_context(request.context)
        with self._context_service.activate(context):
            result = await self._container.service_client.request(
                service,
                method,
                path,
                timeout=float(timeout_seconds),
                **kwargs,
            )
        return cast(JsonValue, result)

    def _make_log_handler(self, level: str) -> CapabilityHandler:
        async def _handler(request: CapabilityCallRequest) -> JsonValue:
            self._reject_positional_args(request)
            message = _required_string(request.kwargs.get("message"), "message")
            fields = _optional_object(request.kwargs.get("fields"), "fields") or {}
            log_fields = {
                **fields,
                "capability_request_id": request.context.request_id,
                "capability_trace_id": request.context.trace_id,
                "capability_flow_id": request.context.flow_id,
                "capability_task_id": request.context.task_id,
            }
            getattr(logger, level)("capability_gateway.sandbox_log", message=message, **log_fields)
            return {"logged": True}

        return _handler

    async def _trace_event(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        event_type = _required_string(request.kwargs.get("event_type"), "event_type")
        attributes = _optional_object(request.kwargs.get("attributes"), "attributes") or {}
        async with traced_operation(
            "capability_gateway.trace.event",
            event_type=event_type,
            operation_category="developer",
            resource_type="flow",
            resource_id=request.context.flow_id,
            extra_attributes={
                "platform.capability.trace.event_type": event_type,
                **{f"platform.capability.attr.{key}": value for key, value in attributes.items()},
            },
        ):
            return {"recorded": True}

    async def _state_get_nested(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        path = _required_string(request.kwargs.get("path"), "path")
        default = request.kwargs.get("default")
        return _get_nested(request.state, path, default)

    async def _state_set_nested(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        path = _required_string(request.kwargs.get("path"), "path")
        value = request.kwargs.get("value")
        _set_nested(request.state, path, value)
        return {"value": value}

    async def _state_merge(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        updates = _optional_object(request.kwargs.get("updates"), "updates")
        if updates is None:
            raise TypeError("updates must be object")
        merged = _deep_merge(dict(request.state), updates)
        request.state.clear()
        request.state.update(cast(dict[str, JsonValue], merged))
        return {"state": request.state}

    async def _state_get_files(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        files = request.state.get("files")
        return files if isinstance(files, list) else []

    async def _state_find_file(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        name = _optional_string(request.kwargs.get("name"), "name")
        files = request.state.get("files")
        return _find_file(files if isinstance(files, list) else [], name)

    async def _state_get_user(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        groups = request.state.get("user_groups")
        return {
            "id": request.state.get("user_id") or request.context.user_id or "",
            "groups": groups if isinstance(groups, list) else [],
        }

    async def _state_get_tool_result(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        tool_name = _required_string(request.kwargs.get("tool_name"), "tool_name")
        results = request.state.get("tool_results")
        if not isinstance(results, dict):
            return None
        return cast(JsonValue, results.get(tool_name))

    async def _state_get_messages(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        messages = request.state.get("messages")
        return messages if isinstance(messages, list) else []

    async def _state_add_user_message(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        content = _required_string(request.kwargs.get("content"), "content")
        message = _message_dict(
            role=Role.user,
            content=content,
            task_id=request.context.task_id,
        )
        messages = request.state.get("messages")
        if not isinstance(messages, list):
            messages = []
            request.state["messages"] = messages
        messages.append(message)
        return message

    async def _state_add_agent_message(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        content = _required_string(request.kwargs.get("content"), "content")
        message = _message_dict(
            role=Role.agent,
            content=content,
            task_id=request.context.task_id,
        )
        messages = request.state.get("messages")
        if not isinstance(messages, list):
            messages = []
            request.state["messages"] = messages
        messages.append(message)
        return message

    async def _state_push_ui_event(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        event_type = _required_string(request.kwargs.get("event_type"), "event_type")
        payload = _optional_object(request.kwargs.get("payload"), "payload")
        if payload is None:
            raise TypeError("payload must be object")
        event = _append_ui_event(
            request.state,
            event_type=event_type,
            payload=cast(JsonObject, payload),
            event_id=_optional_string(request.kwargs.get("event_id"), "event_id"),
            version=_optional_string(request.kwargs.get("version"), "version") or "1.0.0",
            source=_optional_string(request.kwargs.get("source"), "source") or "assistant",
            correlation_id=_optional_string(
                request.kwargs.get("correlation_id"),
                "correlation_id",
            ),
        )
        return event

    async def _state_push_ui_events(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        raw_events = _optional_array(request.kwargs.get("events"), "events")
        if raw_events is None:
            raise TypeError("events must be array")
        queued: list[JsonObject] = []
        for raw_event in raw_events:
            if not isinstance(raw_event, dict):
                raise TypeError("each event must be object")
            forwarded = request.model_copy(
                update={
                    "kwargs": {
                        "event_type": raw_event.get("type"),
                        "payload": raw_event.get("payload"),
                        "event_id": raw_event.get("id"),
                        "version": raw_event.get("version"),
                        "source": raw_event.get("source"),
                        "correlation_id": raw_event.get("correlation_id"),
                    }
                }
            )
            queued.append(await self._state_push_ui_event(forwarded))
        return cast(JsonValue, queued)

    async def _state_pop_ui_events(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        events = request.state.get(UI_EVENTS_KEY)
        if not isinstance(events, list):
            return []
        request.state[UI_EVENTS_KEY] = []
        return events

    async def _state_extract_json(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        text = _required_string(request.kwargs.get("text"), "text")
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        candidates = [fenced.group(1)] if fenced else []
        candidates.append(text)
        for candidate in candidates:
            stripped = candidate.strip()
            if not stripped:
                continue
            try:
                return cast(JsonValue, json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return None

    async def _channel_send(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        content = _required_string(request.kwargs.get("content"), "content")
        message = await self._state_add_agent_message(
            request.model_copy(update={"kwargs": {"content": content}})
        )
        event = _append_ui_event(
            request.state,
            event_type="channel.message",
            payload={"content": content},
            source="assistant",
        )
        return {"queued": True, "message": message, "event": event}

    async def _channel_send_with_buttons(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        content = _required_string(request.kwargs.get("content"), "content")
        buttons = _optional_array(request.kwargs.get("buttons"), "buttons")
        if buttons is None or not all(isinstance(button, str) for button in buttons):
            raise TypeError("buttons must be array of strings")
        message = await self._state_add_agent_message(
            request.model_copy(update={"kwargs": {"content": content}})
        )
        event = _append_ui_event(
            request.state,
            event_type="channel.message",
            payload={"content": content, "buttons": buttons},
            source="assistant",
        )
        return {"queued": True, "message": message, "event": event}

    async def _flow_ask_user(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        question = _required_string(request.kwargs.get("question"), "question")
        raise _CapabilityInterruptFromTool(
            {
                "kind": "user_message",
                "body": {
                    "kind": "user_message",
                    "question": question,
                },
            }
        )

    async def _text_summarize(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        text = _required_string(request.kwargs.get("text"), "text")
        instruction = _optional_string(request.kwargs.get("instruction"), "instruction")
        provider = _optional_string(request.kwargs.get("provider"), "provider")
        model = _optional_string(request.kwargs.get("model"), "model")
        max_output_tokens = _optional_int(
            request.kwargs.get("max_output_tokens"),
            "max_output_tokens",
        )
        context = await self._context_service.build_context(request.context)
        with self._context_service.activate(context):
            summary = await self._text_transform_service.summarize(
                text,
                instruction=instruction,
                provider=provider,
                model=model,
                max_output_tokens=max_output_tokens,
            )
        return {"summary": summary}

    async def _text_format_markdown(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        text = _required_string(request.kwargs.get("text"), "text")
        provider = _optional_string(request.kwargs.get("provider"), "provider")
        model = _optional_string(request.kwargs.get("model"), "model")
        max_chunk_chars = _optional_int(request.kwargs.get("max_chunk_chars"), "max_chunk_chars")
        context = await self._context_service.build_context(request.context)
        with self._context_service.activate(context):
            markdown = await self._text_transform_service.format_markdown(
                text,
                provider=provider,
                model=model,
                max_chunk_chars=max_chunk_chars,
            )
        return {"markdown": markdown}

    async def _voice_transcribe_audio(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        file_id = _required_string(request.kwargs.get("file_id"), "file_id")
        language = _optional_string(request.kwargs.get("language"), "language")
        provider = _optional_string(request.kwargs.get("provider"), "provider")
        model = _optional_string(request.kwargs.get("model"), "model")

        context = await self._context_service.build_context(request.context)
        company = _active_company(context)
        with self._context_service.activate(context):
            record = await self._container.file_processor.get_file_record(file_id)
            if record is None:
                raise ValueError(f"voice.transcribe_audio: file not found: {file_id}")

            s3 = await self._container.file_processor.get_s3_client()
            audio_bytes = await s3.download_bytes(record.s3_key, bucket=record.s3_bucket)

            stt = await get_stt_client(
                company_id=company.company_id,
                override=SpeechOverride(
                    provider=_speech_provider(provider),
                    model=model,
                    language=language,
                ),
            )
            result = await stt.transcribe_audio(
                audio_bytes=audio_bytes,
                file_name=record.original_name,
                mime_type=record.content_type,
                language=language,
            )

            try:
                audio_seconds = await probe_audio_duration_seconds_from_upload(
                    data=audio_bytes,
                    file_name=record.original_name,
                )
            except ValueError:
                audio_seconds = 0.0
            if audio_seconds > 0:
                await record_stt_usage(
                    user=context.user,
                    company=company,
                    provider=result.provider,
                    audio_seconds=audio_seconds,
                    metadata={"endpoint": "capability_gateway.voice.transcribe_audio", "file_id": file_id},
                )

        return {"text": result.text or ""}

    async def _voice_synthesize_speech(self, request: CapabilityCallRequest) -> JsonObject:
        self._reject_positional_args(request)
        text = _required_string(request.kwargs.get("text"), "text")
        voice = _optional_string(request.kwargs.get("voice"), "voice")
        language = _optional_string(request.kwargs.get("language"), "language")
        provider = _optional_string(request.kwargs.get("provider"), "provider")
        model = _optional_string(request.kwargs.get("model"), "model")
        response_format = _optional_string(request.kwargs.get("response_format"), "response_format")
        file_name = _optional_string(request.kwargs.get("file_name"), "file_name")

        context = await self._context_service.build_context(request.context)
        company = _active_company(context)
        with self._context_service.activate(context):
            tts = await get_tts_client(
                company_id=company.company_id,
                override=SpeechOverride(
                    provider=_speech_provider(provider),
                    model=model,
                    voice=voice,
                    language=language,
                    response_format=_speech_response_format(response_format),
                ),
            )
            result = await tts.synthesize(text=text)

            ext = result.response_format or "wav"
            original_name = file_name if file_name else f"tts_{uuid.uuid4().hex[:12]}.{ext}"
            record = await self._container.file_processor.persist_uploaded_file(
                data=result.audio_bytes,
                original_name=original_name,
                content_type=result.mime_type,
                uploaded_by=context.user.user_id,
                company_id=company.company_id,
                public=False,
                download_url_prefix="/flows/api/v1/files/download",
            )
            await record_tts_usage(
                user=context.user,
                company=company,
                provider=result.provider,
                char_count=len(text),
                metadata={"endpoint": "capability_gateway.voice.synthesize_speech", "file_id": record.file_id},
            )

        return {"file_id": record.file_id}

    async def _tools_call(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        tool_id = _required_string(request.kwargs.get("tool_id"), "tool_id")
        arguments_raw = request.kwargs.get("arguments")
        if not isinstance(arguments_raw, dict):
            raise TypeError("arguments must be object")

        context = await self._context_service.build_context(request.context)
        payload = {
            "context": request.context.model_dump(mode="json"),
            "tool_id": tool_id,
            "arguments": arguments_raw,
            "state": request.state,
        }
        with self._context_service.activate(context):
            raw_response = await self._container.service_client.post(
                "flows",
                "/flows/api/v1/tool-runtime/call",
                json=payload,
                timeout=120.0,
            )

        if not isinstance(raw_response, dict):
            raise RuntimeError("flows tool-runtime response must be an object")

        returned_state = raw_response.get("state")
        if isinstance(returned_state, dict):
            request.state.clear()
            request.state.update(returned_state)

        status = raw_response.get("status")
        if status == "interrupt":
            interrupt = raw_response.get("interrupt")
            if not isinstance(interrupt, dict):
                raise RuntimeError("flows tool-runtime interrupt response lacks interrupt envelope")
            raise _CapabilityInterruptFromTool(interrupt)
        if status != "ok":
            raise RuntimeError(f"flows tool-runtime returned invalid status: {status!r}")
        return raw_response.get("result")

    async def _tools_call_builtin(self, request: CapabilityCallRequest) -> JsonValue:
        self._reject_positional_args(request)
        tool_id = _required_string(request.kwargs.get("tool_id"), "tool_id")
        arguments_raw = request.kwargs.get("arguments")
        if not isinstance(arguments_raw, dict):
            raise TypeError("arguments must be object")

        context = await self._context_service.build_context(request.context)
        payload = {
            "context": request.context.model_dump(mode="json"),
            "tool_id": tool_id,
            "arguments": arguments_raw,
            "state": request.state,
        }
        with self._context_service.activate(context):
            raw_response = await self._container.service_client.post(
                "flows",
                "/flows/api/v1/tool-runtime/call-builtin",
                json=payload,
                timeout=120.0,
            )

        if not isinstance(raw_response, dict):
            raise RuntimeError("flows builtin tool-runtime response must be an object")

        returned_state = raw_response.get("state")
        if isinstance(returned_state, dict):
            request.state.clear()
            request.state.update(returned_state)

        status = raw_response.get("status")
        if status == "interrupt":
            interrupt = raw_response.get("interrupt")
            if not isinstance(interrupt, dict):
                raise RuntimeError("flows builtin tool-runtime interrupt response lacks interrupt envelope")
            raise _CapabilityInterruptFromTool(interrupt)
        if status != "ok":
            raise RuntimeError(f"flows builtin tool-runtime returned invalid status: {status!r}")
        return raw_response.get("result")

    def _reject_positional_args(self, request: CapabilityCallRequest) -> None:
        if request.args:
            raise ValueError(f"Capability {request.name} accepts keyword arguments only")
