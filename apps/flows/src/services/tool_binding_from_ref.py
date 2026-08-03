"""Generate a ToolBinding from a ToolReference embedded on a flow node."""

from __future__ import annotations

from apps.flows.src.models.tool_contracts import ToolBinding
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.services.tool_definition_backfill import BUILTIN_TOOL_DEFINITION_VERSION
from apps.flows.src.tools.base import sanitize_tool_name
from core.types import JsonObject, JsonValue, require_json_object


def binding_from_tool_reference(
    ref: ToolReference,
    flow_id: str,
    node_id: str,
) -> ToolBinding:
    """Pin a ToolReference to definition version 1.0.0 and map input_mapping."""
    flow_id_clean = flow_id.strip()
    node_id_clean = node_id.strip()
    if not flow_id_clean:
        raise ValueError("flow_id must be non-empty")
    if not node_id_clean:
        raise ValueError("node_id must be non-empty")

    definition_id = _definition_id_from_ref(ref)
    llm_label = (ref.name or "").strip()
    if not llm_label:
        llm_label = definition_id
    llm_name = sanitize_tool_name(llm_label)
    if not llm_name:
        raise ValueError(f"ToolReference '{definition_id}' produced empty llm_name")

    title = (ref.title or "").strip()
    if not title:
        title = llm_label

    description = ref.description if ref.description is not None else ""
    parameter_bindings = _parameter_bindings_from_input_mapping(ref.input_mapping)

    binding_id = f"{flow_id_clean}.{node_id_clean}.{definition_id}"
    return ToolBinding(
        binding_id=binding_id,
        definition_id=definition_id,
        definition_version=BUILTIN_TOOL_DEFINITION_VERSION,
        flow_id=flow_id_clean,
        node_id=node_id_clean,
        llm_name=llm_name,
        title=title,
        description=description,
        parameter_bindings=parameter_bindings,
        model_schema_projection=_model_schema_projection(ref),
        result_projection=_result_projection(ref),
        confirmation_override=None,
        budgets=None,
        enabled=True,
    )


def _definition_id_from_ref(ref: ToolReference) -> str:
    tool_id = ref.tool_id.strip()
    if tool_id:
        return tool_id
    name = (ref.name or "").strip()
    if name:
        return name
    raise ValueError("ToolReference requires non-empty tool_id or name for definition_id")


def _parameter_bindings_from_input_mapping(input_mapping: JsonObject) -> JsonObject:
    bindings: JsonObject = {}
    for target, mapping_value in input_mapping.items():
        bindings[target] = _map_input_mapping_value(mapping_value)
    return bindings


def _map_input_mapping_value(mapping_value: JsonValue) -> JsonValue:
    if isinstance(mapping_value, str) and mapping_value.startswith("@state:"):
        return {
            "source": "state",
            "path": mapping_value.removeprefix("@state:"),
        }
    if isinstance(mapping_value, str) and mapping_value.startswith("@var:"):
        return {
            "source": "state",
            "path": f"variables.{mapping_value.removeprefix('@var:')}",
        }
    return {
        "source": "const",
        "value": mapping_value,
    }


def _model_schema_projection(ref: ToolReference) -> JsonObject:
    if ref.parameters_schema is None:
        return {}
    return require_json_object(ref.parameters_schema, f"tool.{ref.tool_id}.parameters_schema")


def _result_projection(ref: ToolReference) -> list[str]:
    if ref.output_mapping is None:
        return []
    return list(ref.output_mapping.keys())
