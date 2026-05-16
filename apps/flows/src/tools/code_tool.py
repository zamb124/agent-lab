"""
CodeTool - runnable tool backed by inline Python code from flow config.

The abstract BaseTool stays independent from the code runner stack. This keeps
the tool decorator and sandbox namespace importable without pulling PythonCompiler
back into the tools package during module initialization.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, ClassVar

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.runners.python import PythonCodeRunner
from apps.flows.src.tools.base import BaseTool, Permission
from apps.flows.src.tools.json_schema_parameters import validate_tool_args_against_parameters_schema

if TYPE_CHECKING:
    from core.state import ExecutionState


class CodeTool(BaseTool):
    """
    Тул из Python-кода в конфиге (поле code).
    Выполнение через SafeEval.execute_tool.

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
        parameters: dict[str, Any] | None = None,
        parameters_schema: dict[str, Any] | None = None,
        permission: Permission = None,
        tags: list[str] | None = None,
        react_role: ReactToolRole = ReactToolRole.STANDARD,
        resources: dict[str, Any] | None = None,
        container: FlowRuntimeContainer | None = None,
    ):
        self.name = tool_id
        self.description = description or f"Code tool: {tool_id}"
        self.permission = permission
        self.tags = tags or ["misc"]
        self.react_role = react_role
        self._code = code
        self._resources_config = resources or {}
        self.container = container

        if parameters_schema is not None:
            if not isinstance(parameters_schema, dict):
                raise ValueError(f"CodeTool '{tool_id}': parameters_schema must be a dict")
            if parameters_schema.get("type") != "object":
                raise ValueError(f"CodeTool '{tool_id}': parameters_schema must have type: object")
            props = parameters_schema.get("properties")
            if not isinstance(props, dict):
                raise ValueError(
                    f"CodeTool '{tool_id}': parameters_schema must contain object properties"
                )
            self._parameters = copy.deepcopy(parameters_schema)
        elif parameters:
            props = {}
            required = []
            for param_name, param_info in parameters.items():
                props[param_name] = {
                    "type": param_info.type
                    if hasattr(param_info, "type")
                    else param_info.get("type", "string"),
                    "description": param_info.description
                    if hasattr(param_info, "description")
                    else param_info.get("description", ""),
                }
                is_req = (
                    param_info.required
                    if hasattr(param_info, "required")
                    else param_info.get("required", True)
                )
                if is_req:
                    required.append(param_name)
            self._parameters = {"type": "object", "properties": props, "required": required}
        else:
            self._parameters = None

    @property
    def parameters(self) -> dict[str, Any]:
        """Возвращает параметры."""
        if self._parameters:
            return self._parameters
        return {"type": "object", "properties": {}, "required": []}

    async def _run_impl(self, args: dict[str, Any], state: "ExecutionState") -> Any:
        """Выполняет inline код через SafeEval."""
        full_args = self._apply_defaults(args)
        schema = self._parameters
        if isinstance(schema, dict) and schema.get("type") == "object":
            validate_tool_args_against_parameters_schema(schema=schema, arguments=dict(full_args))

        variables = state.variables
        resources = await self._resolve_resources(state)

        container = self.container
        if container is None:
            if resources:
                raise RuntimeError(f"CodeTool '{self.name}' requires FlowContainer to execute inline code")
            runner = PythonCodeRunner(variables=variables)
        else:
            runner = container.get_code_runner(
                language="python",
                resources=resources,
                variables=variables,
            )
        return await runner.execute_tool(self._code, full_args, state)

    def _apply_defaults(self, args: dict[str, Any]) -> dict[str, Any]:
        """Применяет default значения из args_schema к args."""
        if not self._parameters:
            return args

        result = dict(args)
        properties = self._parameters.get("properties", {})
        if not isinstance(properties, dict):
            return result

        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            if prop_name not in result and "default" in prop_schema:
                result[prop_name] = prop_schema["default"]

        return result

    async def _resolve_resources(self, state: "ExecutionState") -> dict[str, Any]:
        """
        Резолвит resources для tool.

        Единообразно с нодами — иерархия flow > skill > tool.
        """
        tool_resources = self._resources_config
        container = self.container
        if container is None:
            if tool_resources:
                raise RuntimeError(f"CodeTool '{self.name}' requires FlowContainer to resolve resources")
            return {}

        flow_resources, skill_resources = await container.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )

        if not flow_resources and not skill_resources and not tool_resources:
            return {}

        return await container.resource_resolver.resolve_for_node(
            flow_resources=flow_resources,
            skill_resources=skill_resources,
            node_resources=tool_resources,
            variables=state.variables,
        )
