"""OpenAI strict parameters compiler for canonical tool JSON Schema."""

from __future__ import annotations

import copy

from core.types import JsonObject, require_json_object


def compile_openai_strict_parameters(canonical: JsonObject) -> JsonObject:
    """
    Ensures object root with additionalProperties=false and all properties required.
    Properties that were not required in canonical become nullable unions.
    """
    schema = require_json_object(copy.deepcopy(canonical), "canonical_input_schema")
    if schema.get("type") != "object":
        raise ValueError("canonical_input_schema root must be type=object")

    raw_properties = schema.get("properties")
    if not isinstance(raw_properties, dict):
        raise ValueError("canonical_input_schema must include properties object")

    raw_required = schema.get("required")
    required_names: set[str] = set()
    if isinstance(raw_required, list):
        for item in raw_required:
            if isinstance(item, str):
                required_names.add(item)

    strict_properties: dict[str, JsonObject] = {}
    for property_name, property_schema in raw_properties.items():
        if not isinstance(property_schema, dict):
            raise ValueError(f"property {property_name!r} must be an object schema")
        property_object = require_json_object(property_schema, f"property.{property_name}")
        if property_name in required_names:
            strict_properties[property_name] = _make_strict_required_property(property_object)
        else:
            strict_properties[property_name] = _make_strict_optional_property(property_object)

    schema["properties"] = strict_properties
    schema["required"] = sorted(strict_properties.keys())
    schema["additionalProperties"] = False
    return schema


def _make_strict_required_property(property_schema: JsonObject) -> JsonObject:
    out = require_json_object(copy.deepcopy(property_schema), "property_schema")
    if "default" in out:
        del out["default"]
    if out.get("type") == "object":
        return _strict_object(out, nullable=False)
    return out


def _make_strict_optional_property(property_schema: JsonObject) -> JsonObject:
    out = require_json_object(copy.deepcopy(property_schema), "property_schema")
    if "default" in out:
        del out["default"]
    if out.get("type") == "object":
        return _strict_object(out, nullable=True)
    if "type" not in out and "$ref" not in out and "anyOf" not in out and "oneOf" not in out:
        out["type"] = "string"
    if out.get("type") == "null":
        return {"type": ["string", "null"]}
    existing_type = out.get("type")
    if isinstance(existing_type, list):
        if "null" not in existing_type:
            out["type"] = [*existing_type, "null"]
        return out
    if isinstance(existing_type, str):
        out["type"] = [existing_type, "null"]
        return out
    if "anyOf" in out or "oneOf" in out:
        return _append_nullable_union(out)
    return out


def _strict_object(property_schema: JsonObject, *, nullable: bool) -> JsonObject:
    out = require_json_object(copy.deepcopy(property_schema), "object_property_schema")
    nested_properties = out.get("properties")
    if isinstance(nested_properties, dict):
        raw_required = out.get("required")
        required_names: set[str] = set()
        if isinstance(raw_required, list):
            for item in raw_required:
                if isinstance(item, str):
                    required_names.add(item)
        strict_nested: dict[str, JsonObject] = {}
        for nested_name, nested_schema in nested_properties.items():
            if not isinstance(nested_schema, dict):
                raise ValueError(f"nested property {nested_name!r} must be an object schema")
            nested_object = require_json_object(nested_schema, f"nested.{nested_name}")
            if nested_name in required_names:
                strict_nested[nested_name] = _make_strict_required_property(nested_object)
            else:
                strict_nested[nested_name] = _make_strict_optional_property(nested_object)
        out["properties"] = strict_nested
        out["required"] = sorted(strict_nested.keys())
    out["additionalProperties"] = False
    if nullable:
        return {"anyOf": [out, {"type": "null"}]}
    return out


def _append_nullable_union(property_schema: JsonObject) -> JsonObject:
    variants_key = "anyOf" if "anyOf" in property_schema else "oneOf"
    raw_variants = property_schema.get(variants_key)
    if not isinstance(raw_variants, list):
        raise ValueError(f"{variants_key} must be a list")
    variants: list[JsonObject] = []
    has_null = False
    for variant in raw_variants:
        if not isinstance(variant, dict):
            raise ValueError(f"{variants_key} entries must be object schemas")
        if variant.get("type") == "null":
            has_null = True
            continue
        variants.append(require_json_object(copy.deepcopy(variant), "union_variant"))
    if not has_null:
        variants.append({"type": "null"})
    return {variants_key: variants}
