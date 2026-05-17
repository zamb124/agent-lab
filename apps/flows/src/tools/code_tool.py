"""
CodeTool - runnable tool backed by inline code from flow config.

The abstract BaseTool stays independent from the code runner stack. This keeps
the tool decorator importable without pulling any language runner back into the
tools package during module initialization.
"""

from __future__ import annotations

import ast
import builtins
import copy
import inspect
import json
import math
import operator
import typing
import __future__
from typing import TYPE_CHECKING, Any, ClassVar

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.tools.base import BaseTool, Permission
from apps.flows.src.tools.json_schema_parameters import validate_tool_args_against_parameters_schema
from core.config.testing import is_testing
from core.state.mutation_policy import user_code_state_mutation_guard

if TYPE_CHECKING:
    from core.state import ExecutionState


_LOCAL_TEST_IMPORT_ROOTS = {
    "__future__",
    "asyncio",
    "ast",
    "base64",
    "collections",
    "datetime",
    "decimal",
    "functools",
    "hashlib",
    "html",
    "itertools",
    "json",
    "math",
    "operator",
    "random",
    "re",
    "statistics",
    "string",
    "time",
    "typing",
    "uuid",
}


class _ExecutionStateProxy:
    """Mapping-like facade used only by local test execution."""

    def __init__(self, state: "ExecutionState"):
        object.__setattr__(self, "_state", state)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self._state, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self._state, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self._state, key, value)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and hasattr(self._state, key)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_state":
            object.__setattr__(self, name, value)
            return
        setattr(self._state, name, value)


def _local_test_infer_entrypoint(source: str) -> str | None:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name
    return None


def _local_test_safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level != 0:
        raise ImportError("relative imports are not allowed in code runner")
    root = name.split(".", 1)[0]
    if root not in _LOCAL_TEST_IMPORT_ROOTS:
        raise ImportError(f"import is not allowed in code runner: {name}")
    return builtins.__import__(name, globals, locals, fromlist, level)


def _local_test_namespace() -> dict[str, Any]:
    safe_builtins = {
        "BaseException": BaseException,
        "Exception": Exception,
        "AssertionError": AssertionError,
        "AttributeError": AttributeError,
        "ImportError": ImportError,
        "IndexError": IndexError,
        "KeyError": KeyError,
        "NameError": NameError,
        "NotImplementedError": NotImplementedError,
        "RuntimeError": RuntimeError,
        "TypeError": TypeError,
        "ValueError": ValueError,
        "ZeroDivisionError": ZeroDivisionError,
        "__build_class__": __build_class__,
        "abs": abs,
        "all": all,
        "any": any,
        "bin": bin,
        "bool": bool,
        "bytearray": bytearray,
        "bytes": bytes,
        "callable": callable,
        "chr": chr,
        "classmethod": classmethod,
        "compile": compile,
        "dict": dict,
        "divmod": divmod,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "format": format,
        "getattr": getattr,
        "hasattr": hasattr,
        "hex": hex,
        "int": int,
        "isinstance": isinstance,
        "iter": iter,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "object": object,
        "oct": oct,
        "ord": ord,
        "pow": pow,
        "print": print,
        "property": property,
        "range": range,
        "repr": repr,
        "reversed": reversed,
        "round": round,
        "set": set,
        "setattr": setattr,
        "sorted": sorted,
        "staticmethod": staticmethod,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "type": type,
        "zip": zip,
        "__import__": _local_test_safe_import,
    }
    return {
        "__builtins__": safe_builtins,
        "__name__": "__sandbox__",
        "Any": typing.Any,
        "Callable": typing.Callable,
        "Dict": typing.Dict,
        "List": typing.List,
        "Literal": typing.Literal,
        "Number": int | float,
        "Optional": typing.Optional,
        "Sequence": typing.Sequence,
        "Set": typing.Set,
        "Tuple": typing.Tuple,
        "Union": typing.Union,
        "ast": ast,
        "json": json,
        "math": math,
        "operator": operator,
        "typing": typing,
    }


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
        parameters: dict[str, Any] | None = None,
        parameters_schema: dict[str, Any] | None = None,
        permission: Permission = None,
        tags: list[str] | None = None,
        react_role: ReactToolRole = ReactToolRole.STANDARD,
        language: str = "python",
        entrypoint: str | None = None,
        resources: dict[str, Any] | None = None,
        container: FlowRuntimeContainer | None = None,
    ):
        self.name = tool_id
        self.description = description or f"Code tool: {tool_id}"
        self.permission = permission
        self.tags = tags or ["misc"]
        self.react_role = react_role
        self.language = language
        self.entrypoint = entrypoint.strip() if isinstance(entrypoint, str) and entrypoint.strip() else None
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
        """Выполняет inline код через isolated remote code runner."""
        if self._resources_config:
            raise ValueError(
                f"CodeTool '{self.name}': resources are not injected into sandbox code. "
                "Use capability('tools.call', ...) / Capability('tools.call', ...) or a dedicated platform capability."
            )
        full_args = self._apply_defaults(args)
        schema = self._parameters
        if isinstance(schema, dict) and schema.get("type") == "object":
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
            if not is_testing():
                raise RuntimeError(f"CodeTool '{self.name}' requires FlowContainer to execute remote code")
            return await self._execute_local_test(full_args, state)
        else:
            runner = container.get_code_runner(language=self.language)
        return await runner.execute_tool(self._code, full_args, state, entrypoint=self.entrypoint)

    async def _execute_local_test(self, args: dict[str, Any], state: "ExecutionState") -> Any:
        if self.language != "python":
            raise RuntimeError(
                f"CodeTool '{self.name}' requires FlowContainer to execute {self.language} code"
            )

        entrypoint_name = self.entrypoint or _local_test_infer_entrypoint(self._code)
        if not entrypoint_name:
            raise RuntimeError("Entrypoint function not found: declare at least one function")

        namespace = _local_test_namespace()
        state_proxy = _ExecutionStateProxy(state)
        namespace["variables"] = state.variables
        namespace["files"] = state.files

        compiled = compile(
            self._code,
            f"<test-code-tool:{self.name}>",
            "exec",
            flags=__future__.annotations.compiler_flag,
            dont_inherit=True,
        )
        exec(compiled, namespace)
        entrypoint = namespace.get(entrypoint_name)
        if not callable(entrypoint):
            raise RuntimeError(f"Entrypoint not found: {entrypoint_name}")

        signature = inspect.signature(entrypoint)
        parameters = [
            param
            for param in signature.parameters.values()
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]
        with user_code_state_mutation_guard():
            if (
                len(parameters) >= 2
                and parameters[0].name in ("args", "arguments")
                and parameters[1].name == "state"
            ):
                result = entrypoint(args, state_proxy)
            else:
                kwargs = dict(args)
                if "state" in signature.parameters:
                    kwargs["state"] = state_proxy
                result = entrypoint(**kwargs)
            if inspect.isawaitable(result):
                result = await result
        return None if result is state_proxy else result

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
