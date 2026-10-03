"""Вывод filterable leaf-полей из JSON Schema payload события платформы.

Единственный SSOT для UI-autocomplete и валидации фильтров триггера
`platform_event`: UI не парсит schema сам.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.types import JsonObject, JsonValue, require_json_object

FilterValueKind = Literal["string", "integer", "number", "boolean", "enum"]
FilterOp = Literal["eq", "ne", "contains"]

_MAX_DEPTH = 6
_STRING_OPS: tuple[FilterOp, ...] = ("eq", "ne", "contains")
_SCALAR_OPS: tuple[FilterOp, ...] = ("eq", "ne")
_SCALAR_JSON_TYPES: tuple[Literal["string", "integer", "number", "boolean"], ...] = (
    "string",
    "integer",
    "number",
    "boolean",
)


def _scalar_filter_kind(
    json_type: str | None,
) -> Literal["string", "integer", "number", "boolean"] | None:
    if json_type is None:
        return None
    for kind in _SCALAR_JSON_TYPES:
        if kind == json_type:
            return kind
    return None


class PlatformEventFilterField(BaseModel):
    """Одно фильтруемое leaf-поле payload (dot-path + тип + ops)."""

    path: str
    label: str
    description: str = ""
    value_kind: FilterValueKind
    enum_values: list[str] | None = None
    ops: list[FilterOp] = Field(default_factory=lambda: list(_SCALAR_OPS))


def derive_filter_fields(payload_schema: JsonObject) -> list[PlatformEventFilterField]:
    """Плоский список leaf-путей из JSON Schema Pydantic `model_json_schema()`."""
    root = require_json_object(payload_schema, "payload_schema")
    defs = _schema_defs(root)
    fields: list[PlatformEventFilterField] = []
    _walk(
        node=root,
        path_segments=[],
        label_segments=[],
        defs=defs,
        depth=0,
        fields=fields,
        visiting_refs=set(),
    )
    return fields


def ensure_catalog_filter_fields(
    entry_event_type: str,
    description: str,
    payload_schema: JsonObject,
    filter_fields: list[PlatformEventFilterField] | None,
) -> list[PlatformEventFilterField]:
    """Auto-heal: пустой/отсутствующий filter_fields → derive из payload_schema."""
    _ = entry_event_type
    _ = description
    if filter_fields:
        return filter_fields
    return derive_filter_fields(payload_schema)


def _schema_defs(root: JsonObject) -> dict[str, JsonObject]:
    raw_defs = root.get("$defs")
    if raw_defs is None:
        raw_defs = root.get("definitions")
    if not isinstance(raw_defs, dict):
        return {}
    resolved: dict[str, JsonObject] = {}
    for name, value in raw_defs.items():
        if isinstance(value, dict):
            resolved[name] = require_json_object(value, f"payload_schema.$defs.{name}")
    return resolved


def _walk(
    *,
    node: JsonObject,
    path_segments: list[str],
    label_segments: list[str],
    defs: dict[str, JsonObject],
    depth: int,
    fields: list[PlatformEventFilterField],
    visiting_refs: set[str],
) -> None:
    if depth > _MAX_DEPTH:
        return

    resolved = _resolve_ref(node, defs, visiting_refs)
    if resolved is None:
        return
    resolved = _unwrap_nullable_union(resolved)
    resolved = _resolve_ref(resolved, defs, visiting_refs)
    if resolved is None:
        return

    union_variants = _object_union_variants(resolved)
    if union_variants is not None:
        _walk_union_variants(
            variants=union_variants,
            parent=resolved,
            path_segments=path_segments,
            label_segments=label_segments,
            defs=defs,
            depth=depth,
            fields=fields,
            visiting_refs=visiting_refs,
        )
        return

    enum_values = _enum_string_values(resolved)
    if enum_values is not None and path_segments:
        fields.append(
            _leaf_field(
                path_segments=path_segments,
                label_segments=label_segments,
                node=resolved,
                value_kind="enum",
                enum_values=enum_values,
                ops=list(_SCALAR_OPS),
            )
        )
        return

    json_type = _primary_type(resolved)
    kind = _scalar_filter_kind(json_type)
    if kind is not None and path_segments:
        ops = list(_STRING_OPS) if kind == "string" else list(_SCALAR_OPS)
        fields.append(
            _leaf_field(
                path_segments=path_segments,
                label_segments=label_segments,
                node=resolved,
                value_kind=kind,
                enum_values=None,
                ops=ops,
            )
        )
        return

    if json_type == "array" and path_segments:
        items_raw = resolved.get("items")
        if isinstance(items_raw, dict):
            items = require_json_object(items_raw, "payload_schema.items")
            items_resolved = _resolve_ref(items, defs, visiting_refs)
            if items_resolved is None:
                return
            if _enum_string_values(items_resolved) is not None:
                fields.append(
                    _leaf_field(
                        path_segments=path_segments,
                        label_segments=label_segments,
                        node=resolved,
                        value_kind="enum",
                        enum_values=_enum_string_values(items_resolved),
                        ops=list(_STRING_OPS),
                    )
                )
                return
            item_type = _primary_type(items_resolved)
            kind = _scalar_filter_kind(item_type)
            if kind is not None:
                fields.append(
                    _leaf_field(
                        path_segments=path_segments,
                        label_segments=label_segments,
                        node=resolved,
                        value_kind=kind,
                        enum_values=None,
                        ops=list(_STRING_OPS),
                    )
                )
        return

    if json_type == "object" or "properties" in resolved:
        properties_raw = resolved.get("properties")
        if not isinstance(properties_raw, dict):
            return
        for prop_name, prop_schema_raw in properties_raw.items():
            if not isinstance(prop_schema_raw, dict):
                continue
            prop_schema = require_json_object(
                prop_schema_raw, f"payload_schema.properties.{prop_name}"
            )
            prop_label = _node_title(prop_schema, prop_name)
            _walk(
                node=prop_schema,
                path_segments=[*path_segments, prop_name],
                label_segments=[*label_segments, prop_label],
                defs=defs,
                depth=depth + 1,
                fields=fields,
                visiting_refs=visiting_refs,
            )


def _resolve_ref(
    node: JsonObject,
    defs: dict[str, JsonObject],
    visiting_refs: set[str],
) -> JsonObject | None:
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node
    def_name = _ref_def_name(ref)
    if def_name is None:
        return None
    if def_name in visiting_refs:
        return None
    target = defs.get(def_name)
    if target is None:
        return None
    visiting_refs.add(def_name)
    try:
        return _resolve_ref(target, defs, visiting_refs)
    finally:
        visiting_refs.discard(def_name)


def _ref_def_name(ref: str) -> str | None:
    prefixes = ("#/$defs/", "#/definitions/")
    for prefix in prefixes:
        if ref.startswith(prefix):
            name = ref[len(prefix) :]
            if name and "/" not in name:
                return name
    return None


def _unwrap_nullable_union(node: JsonObject) -> JsonObject:
    """Pydantic Optional[T] → anyOf[T, null]; оставляем единственную не-null ветку."""
    any_of = node.get("anyOf")
    if not isinstance(any_of, list):
        return node
    non_null: list[JsonObject] = []
    for option in any_of:
        if not isinstance(option, dict):
            continue
        option_obj = require_json_object(option, "payload_schema.anyOf[]")
        if option_obj.get("type") == "null":
            continue
        non_null.append(option_obj)
    if len(non_null) == 1:
        return non_null[0]
    return node


def _object_union_variants(node: JsonObject) -> list[JsonObject] | None:
    """Discriminated / multi-branch oneOf|anyOf → список не-null вариантов (≥2)."""
    for key in ("oneOf", "anyOf"):
        raw = node.get(key)
        if not isinstance(raw, list):
            continue
        variants: list[JsonObject] = []
        for option in raw:
            if not isinstance(option, dict):
                continue
            option_obj = require_json_object(option, f"payload_schema.{key}[]")
            if option_obj.get("type") == "null":
                continue
            variants.append(option_obj)
        if len(variants) >= 2:
            return variants
    return None


def _walk_union_variants(
    *,
    variants: list[JsonObject],
    parent: JsonObject,
    path_segments: list[str],
    label_segments: list[str],
    defs: dict[str, JsonObject],
    depth: int,
    fields: list[PlatformEventFilterField],
    visiting_refs: set[str],
) -> None:
    """Обход вариантов union: discriminator enum + leaf-поля всех веток (dedupe path)."""
    discriminator_raw = parent.get("discriminator")
    if isinstance(discriminator_raw, dict) and path_segments:
        property_name = discriminator_raw.get("propertyName")
        mapping_raw = discriminator_raw.get("mapping")
        if isinstance(property_name, str) and isinstance(mapping_raw, dict):
            enum_values = list(mapping_raw.keys())
            if enum_values:
                disc_path = [*path_segments, property_name]
                disc_labels = [*label_segments, property_name.replace("_", " ")]
                _append_field_deduped(
                    fields,
                    _leaf_field(
                        path_segments=disc_path,
                        label_segments=disc_labels,
                        node=parent,
                        value_kind="enum",
                        enum_values=enum_values,
                        ops=list(_SCALAR_OPS),
                    ),
                )

    start_index = len(fields)
    for variant in variants:
        _walk(
            node=variant,
            path_segments=path_segments,
            label_segments=label_segments,
            defs=defs,
            depth=depth,
            fields=fields,
            visiting_refs=visiting_refs,
        )
    _dedupe_fields_from(fields, start_index)


def _append_field_deduped(
    fields: list[PlatformEventFilterField],
    field: PlatformEventFilterField,
) -> None:
    existing = filter_field_by_path(fields, field.path)
    if existing is None:
        fields.append(field)
        return
    if (
        existing.value_kind == "enum"
        and field.value_kind == "enum"
        and existing.enum_values is not None
        and field.enum_values is not None
    ):
        merged = list(dict.fromkeys([*existing.enum_values, *field.enum_values]))
        existing.enum_values = merged


def _dedupe_fields_from(fields: list[PlatformEventFilterField], start_index: int) -> None:
    """Схлопывает дубликаты path, добавленные при обходе union-вариантов."""
    if start_index >= len(fields):
        return
    kept: list[PlatformEventFilterField] = fields[:start_index]
    for field in fields[start_index:]:
        existing = filter_field_by_path(kept, field.path)
        if existing is None:
            kept.append(field)
            continue
        if (
            existing.value_kind == "enum"
            and field.value_kind == "enum"
            and existing.enum_values is not None
            and field.enum_values is not None
        ):
            existing.enum_values = list(
                dict.fromkeys([*existing.enum_values, *field.enum_values])
            )
    fields[:] = kept


def _primary_type(node: JsonObject) -> str | None:
    raw_type = node.get("type")
    if isinstance(raw_type, str):
        return raw_type
    if isinstance(raw_type, list):
        for candidate in raw_type:
            if isinstance(candidate, str) and candidate != "null":
                return candidate
    if "properties" in node:
        return "object"
    if "enum" in node:
        return "string"
    if "items" in node:
        return "array"
    return None


def _enum_string_values(node: JsonObject) -> list[str] | None:
    raw_enum = node.get("enum")
    if isinstance(raw_enum, list) and raw_enum:
        values: list[str] = []
        for item in raw_enum:
            if not isinstance(item, str):
                return None
            values.append(item)
        return values
    any_of = node.get("anyOf")
    if isinstance(any_of, list):
        for option in any_of:
            if not isinstance(option, dict):
                continue
            option_obj = require_json_object(option, "payload_schema.anyOf[]")
            nested = _enum_string_values(option_obj)
            if nested is not None:
                return nested
    return None


def _node_title(node: JsonObject, property_name: str) -> str:
    title = node.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    humanized = property_name.replace("_", " ").replace("  ", " ").strip()
    if humanized:
        return humanized
    return property_name


def _leaf_field(
    *,
    path_segments: list[str],
    label_segments: list[str],
    node: JsonObject,
    value_kind: FilterValueKind,
    enum_values: list[str] | None,
    ops: list[FilterOp],
) -> PlatformEventFilterField:
    path = ".".join(path_segments)
    label = " › ".join(label_segments) if label_segments else path
    description_raw = node.get("description")
    description = description_raw.strip() if isinstance(description_raw, str) else ""
    return PlatformEventFilterField(
        path=path,
        label=label,
        description=description,
        value_kind=value_kind,
        enum_values=enum_values,
        ops=ops,
    )


def filter_field_by_path(
    fields: list[PlatformEventFilterField], path: str
) -> PlatformEventFilterField | None:
    for field in fields:
        if field.path == path:
            return field
    return None


def validate_event_filters_against_fields(
    filters: list[tuple[str, str, JsonValue]],
    fields: list[PlatformEventFilterField],
) -> None:
    """Zero-Guess: каждый filter.path/op/value должен совпадать с filter_fields.

    `filters` — список `(path, op, value)`.
    """
    if not fields:
        if filters:
            raise ValueError(
                "platform event has no filterable fields; filters must be empty"
            )
        return
    by_path = {field.path: field for field in fields}
    for path, op, value in filters:
        field = by_path.get(path)
        if field is None:
            raise ValueError(
                f"unknown filter path {path!r}; allowed: {sorted(by_path)}"
            )
        if op not in field.ops:
            allowed_ops = list(field.ops)
            raise ValueError(
                f"filter op {op!r} is not allowed for path {path!r}; allowed: {allowed_ops}"
            )
        if field.value_kind == "enum":
            if field.enum_values is None:
                raise ValueError(f"filter path {path!r}: enum_values missing in catalog")
            if not isinstance(value, str) or value not in field.enum_values:
                allowed_values = field.enum_values
                raise ValueError(
                    f"filter value {value!r} is not in enum for path {path!r}; allowed: {allowed_values}"
                )
        elif field.value_kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"filter path {path!r} expects boolean value")
        elif field.value_kind == "integer":
            if type(value) is not int or isinstance(value, bool):
                raise ValueError(f"filter path {path!r} expects integer value")
        elif field.value_kind == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"filter path {path!r} expects number value")
        elif field.value_kind == "string":
            if not isinstance(value, str):
                raise ValueError(f"filter path {path!r} expects string value")
