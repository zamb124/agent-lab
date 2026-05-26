"""
CodeTool - runnable tool backed by inline code from flow config.

The abstract BaseTool stays independent from the code runner stack. This keeps
the tool decorator importable without pulling any language runner back into the
tools package during module initialization.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, ClassVar, cast, override

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.tools.base import (
    BaseTool,
    Permission,
    ToolArguments,
    ToolContainerRef,
    ToolParametersSchema,
    ToolResult,
)
from apps.flows.src.tools.json_schema_parameters import validate_tool_args_against_parameters_schema
from core.types import JsonObject, require_json_object, require_json_value

if TYPE_CHECKING:
    from core.state import ExecutionState


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
        *,
        parameters_schema: JsonObject,
        title: str | None = None,
        description: str | None = None,
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
        self.entrypoint: str | None = (
            entrypoint.strip() if entrypoint and entrypoint.strip() else None
        )
        self._code: str = code
        self._resources_config: JsonObject = resources or {}
        self.container: ToolContainerRef | None = container
        self._parameters: ToolParametersSchema

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

    @property
    @override
    def parameters(self) -> ToolParametersSchema:
        """Возвращает параметры."""
        return self._parameters

    @override
    async def _run_impl(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """Выполняет inline код через isolated remote code runner."""
        if self._resources_config:
            message = (
                f"CodeTool '{self.name}': resources are not injected into sandbox code. "
                + "Use tools.<tool_id>(...) / tools.call('<tool_id>', ...) from the sandbox SDK or a dedicated platform capability."
            )
            raise ValueError(message)
        full_args = self._apply_defaults(args)
        validate_tool_args_against_parameters_schema(
            schema=self._parameters, arguments=dict(full_args)
        )

        container = cast(FlowRuntimeContainer | None, self.container)
        if container is None:
            raise RuntimeError(
                f"CodeTool '{self.name}' requires FlowContainer to execute remote code"
            )
        runner = container.get_code_runner(language=self.language)
        return require_json_value(
            await runner.execute_tool(self._code, full_args, state, entrypoint=self.entrypoint),
            f"CodeTool.{self.name}.result",
        )

    def _apply_defaults(self, args: ToolArguments) -> ToolArguments:
        """Применяет default значения из parameters_schema к args."""
        result: JsonObject = dict(args)
        properties = self._parameters.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError(
                f"CodeTool '{self.name}': parameters_schema.properties must be an object"
            )

        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                raise ValueError(
                    f"CodeTool '{self.name}': schema for parameter '{prop_name}' must be an object"
                )
            if prop_name not in result and "default" in prop_schema:
                result[prop_name] = prop_schema["default"]

        return result
