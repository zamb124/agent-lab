"""
CodeTool - runnable tool backed by inline code from flow config.

The abstract BaseTool stays independent from the code runner stack. This keeps
the tool decorator importable without pulling any language runner back into the
tools package during module initialization.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import TYPE_CHECKING, ClassVar, override

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.models.tool_reference import CallParameter
from apps.flows.src.tools.base import (
    BaseTool,
    Permission,
    ToolArguments,
    ToolParametersSchema,
    ToolResult,
)
from apps.flows.src.tools.json_schema_parameters import validate_tool_args_against_parameters_schema
from core.config.testing import is_testing
from core.types import JsonObject, JsonValue, require_json_object, require_json_value

if TYPE_CHECKING:
    from core.state import ExecutionState


def _builtin_delegate_tool_id(code: str) -> str | None:
    first_line = code.lstrip().splitlines()[0] if code.strip() else ""
    marker = "# platform:builtin:"
    if not first_line.startswith(marker):
        return None
    tool_id = first_line.removeprefix(marker).strip()
    return tool_id or None


class CodeTool(BaseTool):
    """
    Тул из inline-кода в конфиге (поле code).
    Выполнение через isolated remote code runner.

    Не кладётся в процессный ToolRegistry.register и не показывается в platform tools документации:
    экземпляры живут только в списке tools конкретной llm_node (materialize).
    """

    listed_in_platform_tool_docs: ClassVar[bool] = False

    def __init__(
        self,
        tool_id: str,
        code: str,
        title: str | None = None,
        description: str | None = None,
        parameters: Mapping[str, CallParameter | JsonObject] | None = None,
        parameters_schema: JsonObject | None = None,
        permission: Permission = None,
        tags: list[str] | None = None,
        react_role: ReactToolRole = ReactToolRole.STANDARD,
        language: str = "python",
        entrypoint: str | None = None,
        resources: JsonObject | None = None,
        container: FlowRuntimeContainer | None = None,
    ):
        self.name: str = tool_id
        self.description: str = description or f"Code tool: {tool_id}"
        self.permission: Permission = permission
        self.tags: list[str] = tags or ["misc"]
        self.react_role: ReactToolRole = react_role
        self.language: str = language
        self.entrypoint: str | None = entrypoint.strip() if entrypoint and entrypoint.strip() else None
        self._code: str = code
        self._resources_config: JsonObject = resources or {}
        self.container: FlowRuntimeContainer | None = container
        self._parameters: ToolParametersSchema | None = None

        if parameters_schema is not None:
            schema_obj = require_json_object(parameters_schema, f"CodeTool.{tool_id}.parameters_schema")
            if schema_obj.get("type") != "object":
                raise ValueError(f"CodeTool '{tool_id}': parameters_schema must have type: object")
            raw_properties = schema_obj.get("properties")
            if not isinstance(raw_properties, dict):
                raise ValueError(
                    f"CodeTool '{tool_id}': parameters_schema must contain object properties"
                )
            self._parameters = require_json_object(
                copy.deepcopy(schema_obj),
                f"CodeTool.{tool_id}.parameters_schema",
            )
        elif parameters:
            props: JsonObject = {}
            required: list[JsonValue] = []
            for param_name, param_info in parameters.items():
                if isinstance(param_info, CallParameter):
                    param_type = param_info.type
                    param_description = param_info.description
                    is_req = param_info.required
                else:
                    param_obj = require_json_object(
                        param_info,
                        f"CodeTool.{tool_id}.parameters.{param_name}",
                    )
                    raw_type = param_obj.get("type", "string")
                    if not isinstance(raw_type, str):
                        raise ValueError(
                            f"CodeTool '{tool_id}': parameter '{param_name}' type must be a string"
                        )
                    raw_description = param_obj.get("description", "")
                    if not isinstance(raw_description, str):
                        raise ValueError(
                            f"CodeTool '{tool_id}': parameter '{param_name}' description must be a string"
                        )
                    raw_required = param_obj.get("required", True)
                    if not isinstance(raw_required, bool):
                        raise ValueError(
                            f"CodeTool '{tool_id}': parameter '{param_name}' required must be a boolean"
                        )
                    param_type = raw_type
                    param_description = raw_description
                    is_req = raw_required

                props[param_name] = {
                    "type": param_type,
                    "description": param_description,
                }
                if is_req:
                    required.append(param_name)
            self._parameters = {"type": "object", "properties": props, "required": required}
    @property
    @override
    def parameters(self) -> ToolParametersSchema:
        """Возвращает параметры."""
        if self._parameters:
            return self._parameters
        return {"type": "object", "properties": {}, "required": []}

    @override
    async def _run_impl(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """Выполняет inline код через isolated remote code runner."""
        if self._resources_config:
            message = (
                f"CodeTool '{self.name}': resources are not injected into sandbox code. "
                + "Use capability('tools.call', ...) / Capability('tools.call', ...) or a dedicated platform capability."
            )
            raise ValueError(message)
        full_args = self._apply_defaults(args)
        schema = self._parameters
        if schema is not None and schema.get("type") == "object":
            validate_tool_args_against_parameters_schema(schema=schema, arguments=dict(full_args))

        container = self.container
        delegated_tool_id = _builtin_delegate_tool_id(self._code)
        if delegated_tool_id and is_testing() and container is not None:
            container.tool_registry.register_builtin_tools()
            builtin_tool = container.tool_registry.get(delegated_tool_id)
            if builtin_tool is None:
                raise RuntimeError(f"Builtin tool not found: {delegated_tool_id}")
            return await builtin_tool.run(full_args, state)

        if container is None:
            raise RuntimeError(f"CodeTool '{self.name}' requires FlowContainer to execute remote code")
        runner = container.get_code_runner(language=self.language)
        return require_json_value(
            await runner.execute_tool(self._code, full_args, state, entrypoint=self.entrypoint),
            f"CodeTool.{self.name}.result",
        )

    def _apply_defaults(self, args: ToolArguments) -> ToolArguments:
        """Применяет default значения из args_schema к args."""
        if not self._parameters:
            return args

        result: JsonObject = dict(args)
        properties = self._parameters.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError(f"CodeTool '{self.name}': parameters_schema.properties must be an object")

        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                raise ValueError(
                    f"CodeTool '{self.name}': schema for parameter '{prop_name}' must be an object"
                )
            if prop_name not in result and "default" in prop_schema:
                result[prop_name] = prop_schema["default"]

        return result
