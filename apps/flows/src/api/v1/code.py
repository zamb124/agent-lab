"""
API endpoints для работы с кодом.

Документация и выполнение идут через единый capability/code-runner контур:
Python, JavaScript, TypeScript, Go и C# получают один manifest возможностей.
"""

import ast
import copy
import importlib
import importlib.util
import inspect
import json
import keyword
import re
import time
import uuid
from pathlib import Path
from types import FrameType, FunctionType, MethodType, ModuleType, TracebackType
from typing import TypedDict, cast

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from apps.flows.src.api.v1.flows import inline_tools_list
from apps.flows.src.container import FlowContainer
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.durable_execution import (
    NodeCompletedPayload,
    NodeScheduledPayload,
    NodeWriteRecordedPayload,
    RunStartedPayload,
    SuperstepStartedPayload,
    WorkflowEventType,
    build_state_delta,
    create_initial_state,
)
from apps.flows.src.models.node_config import NodeConfig
from apps.flows.src.runtime.nodes import create_node
from apps.flows.src.state import collect_flow_node_files
from core.capabilities import (
    CAPABILITY_LANGUAGE_SET,
    CapabilityDocumentation,
    CapabilityLanguage,
    CapabilityNamespaceDocumentation,
    CapabilitySdkMethodDocumentation,
    CodeExecutionKind,
)
from core.clients.service_client import ServiceClient
from core.context import get_context
from core.docs.models import (
    CodeTemplate,
    GlobalVariable,
    ModuleMethod,
    PlatformToolDoc,
    StateField,
)
from core.errors import CodeExecutionRuntimeError, ImanBaseError
from core.files.file_ref import FileRef
from core.logging import get_logger
from core.state import ExecutionState
from core.types import (
    JsonObject,
    JsonValue,
    require_json_array,
    require_json_object,
)

router = APIRouter(tags=["code"])
logger = get_logger(__name__)
type SourceObject = (
    ModuleType | type[object] | MethodType | FunctionType | TracebackType | FrameType
)

CAPABILITY_DOCUMENTATION_PATH = "/capability-gateway/api/v1/capabilities/documentation"
CODE_RUNNER_SERVICE_BY_LANGUAGE = {
    "python": "code_runner_python",
    "javascript": "code_runner_node",
    "typescript": "code_runner_node",
    "go": "code_runner_go",
    "csharp": "code_runner_csharp",
}


class ParsedFunctionParameter(TypedDict):
    type: str
    python_type: str
    required: bool
    has_default: bool
    has_json_default: bool
    default: JsonValue


class ParsedFunctionSignature(TypedDict):
    func_name: str
    parameters: dict[str, ParsedFunctionParameter]
    is_async: bool


def _require_capability_language(language: str) -> CapabilityLanguage:
    if language not in CAPABILITY_LANGUAGE_SET:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    return cast(CapabilityLanguage, language)


async def _capability_documentation(language: CapabilityLanguage) -> CapabilityDocumentation:
    raw = await ServiceClient().get(
        "capability_gateway",
        CAPABILITY_DOCUMENTATION_PATH,
        params={"language": language},
        timeout=30.0,
    )
    if not isinstance(raw, dict):
        raise RuntimeError("capability documentation response must be an object")
    return CapabilityDocumentation.model_validate(raw)


async def _capability_markdown(language: CapabilityLanguage) -> str:
    docs = await _capability_documentation(language)
    return docs.markdown


def _capability_global(language: CapabilityLanguage) -> GlobalVariable:
    namespace_names = "tools/files/http/text/voice/flow_state/log/trace/platform/channel/flow"
    if language == "go":
        return GlobalVariable(
            name=namespace_names,
            type="generated Go SDK namespaces",
            doc="Generated namespaces from CapabilityManifest: tools.Calculator(...), files.Create(...), http.Request(...), flow_state.GetNested(...), channel.Send(...).",
            perspective=["editor", "flow", "tool", "node"],
            tags=["capability", "sandbox"],
        )
    if language == "csharp":
        return GlobalVariable(
            name=namespace_names,
            type="generated C# SDK namespace properties",
            doc="Generated namespaces from CapabilityManifest: await tools.Calculator(...), await files.Create(...), await http.Request(...), await flow_state.GetNested(...), await channel.Send(...).",
            perspective=["editor", "flow", "tool", "node"],
            tags=["capability", "sandbox"],
        )
    if language == "python":
        type_name = "generated async SDK namespaces"
    else:
        type_name = "generated async SDK namespace proxies"
    return GlobalVariable(
        name=namespace_names,
        type=type_name,
        doc="Generated namespaces from CapabilityManifest: tools.calculator(...), files.create(...), http.request(...), flow_state.get_nested(...), channel.send(...).",
        perspective=["editor", "flow", "tool", "node"],
        tags=["capability", "sandbox"],
    )


def _runtime_globals() -> list[GlobalVariable]:
    return [
        GlobalVariable(
            name="args",
            type="runtime entrypoint input",
            doc="Arguments passed into the code entrypoint.",
            perspective=["editor", "flow", "tool", "node"],
            tags=["runtime", "entrypoint"],
        ),
        GlobalVariable(
            name="state",
            type="mutable execution state",
            doc="Flow execution state shared across nodes. User code may write node results here.",
            perspective=["editor", "flow", "tool", "node"],
            tags=["runtime", "state"],
        ),
        GlobalVariable(
            name="variables",
            type="resolved flow variables",
            doc="Resolved flow variables, equivalent to state.variables.",
            perspective=["editor", "flow", "tool", "node"],
            tags=["runtime", "variables"],
        ),
    ]


def _execution_state_fields() -> list[StateField]:
    return [
        StateField(name="content", type="string", description="Input message content."),
        StateField(name="response", type="string", description="Agent response text."),
        StateField(name="result", type="any", description="Last node or tool result."),
        StateField(name="validation", type="object", description="Node validation payload."),
        StateField(name="messages", type="array", description="Conversation message history."),
        StateField(name="variables", type="object", description="Resolved flow variables."),
        StateField(name="files", type="array", description="Attached files available to the flow."),
        StateField(
            name="triggers", type="object", description="Trigger runtime payloads by trigger id."
        ),
        StateField(name="tool_results", type="object", description="Results produced by tools."),
        StateField(name="node_history", type="object", description="Runtime node call history."),
        StateField(
            name="current_nodes", type="array", description="Current graph nodes being executed."
        ),
        StateField(name="branch_id", type="string", description="Current flow branch id."),
        StateField(name="session_id", type="string", description="Runtime session id."),
        StateField(
            name="flow_config_version", type="string", description="Flow config version snapshot."
        ),
    ]


_RESERVED_SDK_METHODS = frozenset({"call", "then"})


def _sdk_method_name(raw: str) -> str:
    name = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw).strip("_")
    if not name:
        name = "tool"
    if name[0].isdigit():
        name = f"tool_{name}"
    if name in _RESERVED_SDK_METHODS:
        name = f"tool_{name}"
    return name


def _exported_method_name(raw: str) -> str:
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


def _schema_properties(parameters_schema: JsonObject | None) -> dict[str, JsonObject]:
    if parameters_schema is None:
        return {}
    raw = parameters_schema.get("properties")
    if raw is None:
        return {}
    properties = require_json_object(raw, "parameters_schema.properties")
    return {
        name: require_json_object(prop, f"parameters_schema.properties.{name}")
        for name, prop in properties.items()
    }


def _tool_arg_entries(parameters_schema: JsonObject | None) -> list[str]:
    return list(_schema_properties(parameters_schema).keys())


def _json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _tool_call_code(
    language: CapabilityLanguage, tool_id: str, parameters_schema: JsonObject | None
) -> str:
    method = _sdk_method_name(tool_id)
    exported = _exported_method_name(method)
    arg_names = _tool_arg_entries(parameters_schema)
    if language == "python":
        if arg_names and all(
            name.isidentifier() and not keyword.iskeyword(name) for name in arg_names
        ):
            kwargs = ",\n".join(f"        {name}=args[{name!r}]" for name in arg_names)
            return (
                "async def run(args, state):\n"
                f"    result = await tools.{method}(\n{kwargs},\n    )\n"
                '    return {"result": result}\n'
            )
        if arg_names:
            entries = ",\n".join(f"        {name!r}: args[{name!r}]," for name in arg_names)
            return (
                "async def run(args, state):\n"
                f"    result = await tools.call({tool_id!r}, **{{\n{entries}\n    }})\n"
                '    return {"result": result}\n'
            )
        return (
            "async def run(args, state):\n"
            f"    result = await tools.{method}()\n"
            '    return {"result": result}\n'
        )
    if language in {"javascript", "typescript"}:
        if arg_names:
            entries = ",\n".join(f"    {name!r}: args[{name!r}]," for name in arg_names)
            payload = f"{{\n{entries}\n  }}"
        else:
            payload = "{}"
        return (
            "async function run(args, state) {\n"
            f"  const result = await tools.{method}({payload});\n"
            "  return {result};\n"
            "}\n"
        )
    if language == "go":
        if arg_names:
            entries = "\n".join(
                f"        {_json_string(name)}: args[{_json_string(name)}]," for name in arg_names
            )
            payload = f"map[string]any{{\n{entries}\n    }}"
        else:
            payload = "map[string]any{}"
        return (
            "package main\n\n"
            "func run(args map[string]any, state map[string]any) (any, error) {\n"
            f"    result, err := tools.{exported}({payload})\n"
            "    if err != nil {\n"
            "        return nil, err\n"
            "    }\n"
            '    return map[string]any{"result": result}, nil\n'
            "}\n"
        )
    if arg_names:
        entries = "\n".join(
            f"        [{_json_string(name)}] = args[{_json_string(name)}]," for name in arg_names
        )
        payload = f"new Dictionary<string, object?> {{\n{entries}\n    }}"
    else:
        payload = "new Dictionary<string, object?>()"
    return (
        "using System.Collections.Generic;\n"
        "using System.Threading.Tasks;\n\n"
        "async Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
        "{\n"
        f"    var result = await tools.{exported}({payload});\n"
        '    return new Dictionary<string, object?> { ["result"] = result };\n'
        "}\n"
    )


def _platform_tool_templates(
    container: FlowContainer, language: CapabilityLanguage
) -> list[CodeTemplate]:
    registry = container.tool_registry
    registry.register_builtin_tools()
    templates: list[CodeTemplate] = []
    for tool_id, tool in sorted(registry.list_all().items(), key=lambda item: item[0]):
        if not type(tool).listed_in_platform_tool_docs:
            continue
        parameters_schema = require_json_object(
            copy.deepcopy(tool.parameters),
            f"tool.{tool_id}.parameters",
        )
        tags = list(tool.get_tags())
        templates.append(
            CodeTemplate(
                id=f"{language}-tool-{tool_id}",
                name=tool.name,
                description=tool.description,
                code=_tool_call_code(language, tool_id, parameters_schema),
                category="platform_tools",
                node_type="code",
                tags=["tool", *tags],
                language=language,
                parameters_schema=parameters_schema,
            )
        )
    return templates


def _capability_templates(language: CapabilityLanguage) -> list[CodeTemplate]:
    snippets = {
        "python": (
            "async def run(args, state):\n"
            '    calc = await tools.calculator(expression=args["expression"])\n'
            '    state["calculation"] = calc\n'
            '    return {"calculation": calc}\n'
        ),
        "javascript": (
            "async function run(args, state) {\n"
            "  const calc = await tools.calculator({expression: args.expression});\n"
            "  state.calculation = calc;\n"
            "  return {calculation: calc};\n"
            "}\n"
        ),
        "typescript": (
            "async function run(args: {expression: string}, state: Record<string, unknown>) {\n"
            "  const calc = await tools.calculator({expression: args.expression});\n"
            "  state.calculation = calc;\n"
            "  return {calculation: calc};\n"
            "}\n"
        ),
        "go": (
            "package main\n\n"
            "func run(args map[string]any, state map[string]any) (any, error) {\n"
            '    calc, err := tools.Calculator(map[string]any{"expression": args["expression"]})\n'
            "    if err != nil {\n"
            "        return nil, err\n"
            "    }\n"
            '    state["calculation"] = calc\n'
            '    return map[string]any{"calculation": calc}, nil\n'
            "}\n"
        ),
        "csharp": (
            "using System.Collections.Generic;\n"
            "using System.Threading.Tasks;\n\n"
            "async Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
            "{\n"
            '    var calc = await tools.Calculator(new Dictionary<string, object?> { ["expression"] = args["expression"] });\n'
            '    state["calculation"] = calc;\n'
            '    return new Dictionary<string, object?> { ["calculation"] = calc };\n'
            "}\n"
        ),
    }
    return [
        CodeTemplate(
            id=f"{language}-capability-call",
            name="Capability call",
            description="Вызов platform capability из isolated code runner.",
            code=snippets[language],
            category="capabilities",
            node_type="code",
            tags=["capability", "sandbox"],
            language=language,
        )
    ]


def _valid_entrypoint_name(language: CapabilityLanguage, entrypoint: str) -> bool:
    if language == "python":
        return entrypoint.isidentifier() and not keyword.iskeyword(entrypoint)
    if language in {"javascript", "typescript"}:
        return re.fullmatch(r"[$A-Za-z_][$\w]*", entrypoint) is not None
    if language == "go":
        return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entrypoint) is not None
    if language == "csharp":
        return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entrypoint) is not None
    return False


_CSHARP_METHOD_RE = re.compile(
    "".join(
        (
            r"(?m)^\s*",
            r"(?:(?:public|private|protected|internal|static|async|virtual|override|sealed|new|partial)\s+)*",
            r"(?:[A-Za-z_][A-Za-z0-9_<>,\[\]\.?]*\s+)+",
            r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        )
    )
)


def _infer_entrypoint(language: CapabilityLanguage, code: str) -> str | None:
    if language == "python":
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node.name
        return None
    if language in {"javascript", "typescript"}:
        candidates: list[tuple[int, str]] = []
        for pattern in (
            r"(?:export\s+)?(?:async\s+)?function\s+([$A-Za-z_][$\w]*)\s*\(",
            r"(?:export\s+)?(?:const|let|var)\s+([$A-Za-z_][$\w]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[$A-Za-z_][$\w]*)\s*=>",
        ):
            for match in re.finditer(pattern, code):
                candidates.append((match.start(), match.group(1)))
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[0])[0][1]
    if language == "go":
        match = re.search(r"func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code)
        return match.group(1) if match else None
    if language == "csharp":
        match = _CSHARP_METHOD_RE.search(code)
        return match.group(1) if match else None
    return None


class CodeCompletionsResponse(BaseModel):
    """Данные для autocomplete в редакторе кода"""

    modules: list[str]
    globals: list[GlobalVariable]
    builtins: list[str]
    module_methods: dict[str, list[ModuleMethod]]
    state_fields: list[StateField] = []
    templates: list[CodeTemplate] = []
    platform_tools: list[PlatformToolDoc] = []
    capability_namespaces: list[CapabilityNamespaceDocumentation] = []
    capabilities: list[CapabilitySdkMethodDocumentation] = []
    runtime_namespace_extras: list[GlobalVariable] | None = None


@router.get("/completions", response_model=CodeCompletionsResponse)
async def get_code_completions(
    container: ContainerDep,
    language: str = "python",
    perspective: str = "editor",
    include_runtime_namespace_extras: bool = False,
) -> CodeCompletionsResponse:
    """
    Возвращает данные для autocomplete в редакторе кода.

    Args:
        language: Язык программирования (`python`, `javascript`, `typescript`, `go`, `csharp`)
        perspective: Ракурс (editor, flow, tool, node)

    Returns:
        modules: доступные модули для import
        globals: глобальные переменные SDK capability
        builtins: встроенные функции
        module_methods: методы модулей
        state_fields: поля state
        templates: шаблоны кода
    """
    capability_language = _require_capability_language(language)
    capability_docs = await _capability_documentation(capability_language)
    _ = container, perspective, include_runtime_namespace_extras
    return CodeCompletionsResponse(
        modules=[],
        globals=[*_runtime_globals(), _capability_global(capability_language)],
        builtins=[],
        module_methods={},
        state_fields=_execution_state_fields(),
        templates=_capability_templates(capability_language),
        platform_tools=[],
        capability_namespaces=capability_docs.namespaces,
        capabilities=capability_docs.capabilities,
        runtime_namespace_extras=None,
    )


@router.get("/documentation")
async def get_code_documentation(
    container: ContainerDep,
    language: str = "python",
    perspective: str = "editor",
    include_runtime_namespace_extras: bool = False,
) -> Response:
    """
    Полная документация для редактора inline-кода в формате Markdown
    (тот же состав данных, что у /completions).
    """
    capability_language = _require_capability_language(language)
    _ = container, perspective, include_runtime_namespace_extras
    body = await _capability_markdown(capability_language)
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
    )


class TemplatesResponse(BaseModel):
    """Список шаблонов кода"""

    templates: list[CodeTemplate]


@router.get("/templates", response_model=TemplatesResponse)
async def get_code_templates(
    container: ContainerDep,
    language: str = "python",
    category: str | None = None,
    node_type: str | None = None,
    tags: str | None = None,
) -> TemplatesResponse:
    """
    Возвращает список шаблонов кода с фильтрацией.

    Args:
        language: Язык программирования (`python`, `javascript`, `typescript`, `go`, `csharp`)
        category: Фильтр по категории (http, llm, interaction, data, files, state, logic, basic)
        node_type: Тип ноды (code, llm_node и др., см. документацию)
        tags: Теги через запятую (http,api)
    """
    capability_language = _require_capability_language(language)
    _ = category, node_type, tags
    templates = [
        *_capability_templates(capability_language),
        *_platform_tool_templates(container, capability_language),
    ]
    return TemplatesResponse(templates=templates)


@router.get("/editor-state")
async def get_editor_state(
    container: ContainerDep,
    flow_id: str,
    branch_id: str = "default",
) -> JsonObject:
    """
    Стартовый ExecutionState как при реальном запуске flow: резолвнутые variables,
    flow_config_version и формат session_id. Для редактора нод и TestPanel.
    """
    context = get_context()
    if not context or not context.user:
        raise HTTPException(
            status_code=401,
            detail="Требуется контекст пользователя",
        )
    user_id = context.user.user_id
    runtime_flow = await container.flow_factory.get_flow(flow_id, branch_id)
    if runtime_flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    task_id = str(uuid.uuid4())
    context_id = str(uuid.uuid4())
    session_id = f"{flow_id}:{context_id}"

    state = create_initial_state(
        task_id=task_id,
        context_id=context_id,
        user_id=user_id,
        session_id=session_id,
        content="",
        branch_id=branch_id,
    )
    state.variables = {**state.variables, **runtime_flow.variables}
    cfg_ver = runtime_flow.config.get("version")
    if cfg_ver:
        state.flow_config_version = str(cfg_ver)
    state.current_nodes = [runtime_flow.entry]
    raw_cfg_nodes = runtime_flow.config.get("nodes")
    cfg_nodes_raw = (
        require_json_object(raw_cfg_nodes, "runtime_flow.config.nodes")
        if raw_cfg_nodes is not None
        else {}
    )
    cfg_nodes = {
        node_id: require_json_object(node_config, f"runtime_flow.config.nodes.{node_id}")
        for node_id, node_config in cfg_nodes_raw.items()
    }
    state.files = collect_flow_node_files(cfg_nodes)

    return require_json_object(state.model_dump(mode="json"), "editor_state")


class SourceResponse(BaseModel):
    """Исходный код"""

    path: str
    source: str | None
    error: str | None = None


@router.get("/source")
async def get_function_source(container: ContainerDep, function_path: str) -> SourceResponse:
    """
    Возвращает исходный код функции по её пути.

    Пример: apps.flows.bundles.<flow_id>.functions.my_function
    """
    _ = container
    if not function_path:
        raise HTTPException(status_code=400, detail="function_path is required")

    return _get_source_by_path(function_path)


class FlowFunctionInfo(BaseModel):
    """Функция из модуля ``bundles.<flow_id>.functions``."""

    name: str
    path: str
    doc: str | None = None


class FlowFunctionsResponse(BaseModel):
    """Список функций из bundle flow (``functions.py``)."""

    flow_id: str
    functions: list[FlowFunctionInfo]
    error: str | None = None


@router.get("/flow-functions")
async def get_flow_functions(container: ContainerDep, flow_id: str) -> FlowFunctionsResponse:
    """
    Возвращает список функций из ``apps/flows/bundles/<flow_id>/functions.py``.
    """
    _ = container
    if not flow_id:
        return FlowFunctionsResponse(flow_id=flow_id, functions=[], error="flow_id is required")

    try:
        module_path = f"apps.flows.bundles.{flow_id}.functions"
        spec = importlib.util.find_spec(module_path)
        if spec is None or spec.origin is None:
            return FlowFunctionsResponse(
                flow_id=flow_id,
                functions=[],
                error=f"Module apps.flows.bundles.{flow_id}.functions not found",
            )
        source = Path(spec.origin).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=spec.origin)

        functions: list[FlowFunctionInfo] = []
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            functions.append(
                FlowFunctionInfo(
                    name=node.name,
                    path=f"{module_path}.{node.name}",
                    doc=ast.get_docstring(node),
                )
            )

        return FlowFunctionsResponse(
            flow_id=flow_id, functions=sorted(functions, key=lambda f: f.name)
        )
    except ModuleNotFoundError:
        return FlowFunctionsResponse(
            flow_id=flow_id,
            functions=[],
            error=f"Module apps.flows.bundles.{flow_id}.functions not found",
        )
    except (OSError, SyntaxError) as e:
        return FlowFunctionsResponse(
            flow_id=flow_id,
            functions=[],
            error=str(e),
        )


@router.get("/tool-source")
async def get_tool_source(container: ContainerDep, tool_path: str) -> SourceResponse:
    """
    Возвращает исходный код tool класса по его пути.

    Пример: apps.flows.tools.math_tools.calculator
    """
    _ = container
    if not tool_path:
        raise HTTPException(status_code=400, detail="tool_path is required")

    return _get_source_by_path(tool_path)


def _get_source_by_path(path: str) -> SourceResponse:
    """
    Получает исходный код по пути к модулю/классу/функции/методу.

    Поддерживает:
    - module.function
    - module.ClassName
    - module.ClassName.method
    """
    try:
        parts = path.split(".")
        if len(parts) < 2:
            return SourceResponse(path=path, source=None, error="Invalid path format")

        obj: SourceObject | None = None
        for i in range(len(parts) - 1, 0, -1):
            module_path = ".".join(parts[:i])
            try:
                module = importlib.import_module(module_path)
                obj = module
                for attr_name in parts[i:]:
                    obj = _source_object_child(obj, attr_name)
                    if obj is None:
                        break
                if obj is not None:
                    break
            except ModuleNotFoundError:
                continue

        if obj is None:
            return SourceResponse(path=path, source=None, error=f"Object not found: {path}")

        source = inspect.getsource(obj)
        return SourceResponse(path=path, source=source)
    except ModuleNotFoundError:
        return SourceResponse(path=path, source=None, error="Module not found")
    except OSError:
        return SourceResponse(path=path, source=None, error="Source code not available")
    except TypeError:
        return SourceResponse(path=path, source=None, error="Cannot get source for built-in")


def _source_object_child(obj: SourceObject, attr_name: str) -> SourceObject | None:
    namespace = cast(dict[str, object], vars(obj))
    raw_attr = namespace.get(attr_name)
    if isinstance(raw_attr, (ModuleType, FunctionType, MethodType, TracebackType, FrameType)):
        return raw_attr
    if isinstance(raw_attr, type):
        return raw_attr
    return None


# ============================================================================
# Валидация и выполнение кода
# ============================================================================


class ValidateRequest(BaseModel):
    """Запрос на валидацию кода"""

    code: str
    node_type: str | None = "code"
    kind: str | None = None
    language: str = "python"
    entrypoint: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None


class ValidateResponse(BaseModel):
    """Результат валидации"""

    valid: bool
    error: str | None = None
    warnings: list[str] = []
    stage: str | None = None
    service: str | None = None
    exception_type: str | None = None


class ParseSignatureRequest(BaseModel):
    """Запрос на парсинг сигнатуры функции"""

    code: str
    func_name: str | None = None


class ParameterInfo(BaseModel):
    """Информация о параметре функции"""

    type: str
    description: str = ""
    default: JsonValue = None
    required: bool = True


class ParseSignatureResponse(BaseModel):
    """Результат парсинга сигнатуры"""

    success: bool
    func_name: str | None = None
    parameters: dict[str, ParameterInfo] = {}
    parameters_schema: JsonObject | None = None
    error: str | None = None


def _python_type_to_json_type(type_str: str) -> str:
    """Конвертирует Python тип в JSON Schema тип."""
    type_mapping = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "List": "array",
        "dict": "object",
        "Dict": "object",
        "Any": "string",
        "Optional": "string",
    }
    base_type = type_str.split("[")[0].strip()
    return type_mapping.get(base_type, "string")


def _json_default_from_ast(node: ast.expr) -> JsonValue:
    """Парсит только JSON-совместимые литералы из default-значения сигнатуры."""
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ValueError("default literal is not JSON-compatible")
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_json_default_from_ast(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        result: JsonObject = {}
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            if key_node is None:
                raise ValueError("dict unpacking is not a JSON default")
            key = _json_default_from_ast(key_node)
            if not isinstance(key, str):
                raise ValueError("JSON default object keys must be strings")
            result[key] = _json_default_from_ast(value_node)
        return result
    raise ValueError("default expression is not a JSON literal")


def _parse_function_signature(code: str, func_name: str | None = None) -> ParsedFunctionSignature:
    """
    Парсит сигнатуру функции из Python кода.
    """
    tree = ast.parse(code)
    top_level_funcs: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
        node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if func_name:
        candidates = [node for node in top_level_funcs if node.name == func_name]
    else:
        by_name = {node.name: node for node in top_level_funcs}
        candidates: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        node = by_name.get("run")
        if node is not None:
            candidates.append(node)
        if not candidates and top_level_funcs:
            candidates.append(top_level_funcs[0])

    for node in candidates:
        params: dict[str, ParsedFunctionParameter] = {}
        args = node.args

        num_args = len(args.args)
        num_defaults = len(args.defaults)
        first_default_idx = num_args - num_defaults

        for i, arg in enumerate(args.args):
            param_name = arg.arg

            if param_name in ("self", "cls", "state", "args"):
                continue

            type_str = "string"
            if arg.annotation:
                type_str = ast.unparse(arg.annotation)

            has_default = i >= first_default_idx
            default_value: JsonValue = None
            has_json_default = False
            if has_default:
                default_idx = i - first_default_idx
                default_node = args.defaults[default_idx]
                try:
                    default_value = _json_default_from_ast(default_node)
                    has_json_default = True
                except ValueError:
                    has_json_default = False

            json_type = _python_type_to_json_type(type_str)

            params[param_name] = {
                "type": json_type,
                "python_type": type_str,
                "required": not has_default,
                "has_default": has_default,
                "has_json_default": has_json_default,
                "default": default_value,
            }

        return {
            "func_name": node.name,
            "parameters": params,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
        }

    target = func_name or "run/first top-level function"
    raise ValueError(f"Функция не найдена: {target}")


@router.post("/parse-signature", response_model=ParseSignatureResponse)
async def parse_signature(
    container: ContainerDep, request: ParseSignatureRequest
) -> ParseSignatureResponse:
    """
    Парсит сигнатуру функции и генерирует parameters_schema.
    """
    _ = container
    if not request.code or not request.code.strip():
        return ParseSignatureResponse(success=False, error="Код пустой")

    try:
        result = _parse_function_signature(request.code, request.func_name)

        properties: JsonObject = {}
        required: list[JsonValue] = []
        for param_name, param_info in result["parameters"].items():
            schema_item: JsonObject = {
                "type": param_info["type"],
                "description": f"Параметр {param_name}",
            }
            if param_info["has_json_default"]:
                schema_item["default"] = param_info["default"]
            if bool(param_info["required"]):
                required.append(param_name)
            properties[param_name] = schema_item

        parameters = {
            name: ParameterInfo(
                type=info["type"],
                description=f"Параметр {name} ({info['python_type']})",
                default=info["default"],
                required=info["required"],
            )
            for name, info in result["parameters"].items()
        }

        return ParseSignatureResponse(
            success=True,
            func_name=result["func_name"],
            parameters=parameters,
            parameters_schema={
                "type": "object",
                "properties": properties,
                "required": required,
            },
        )

    except SyntaxError as e:
        return ParseSignatureResponse(success=False, error=f"Синтаксическая ошибка: {e}")
    except ValueError as e:
        return ParseSignatureResponse(success=False, error=str(e))


def _require_execute_node_type(node_type: str) -> str:
    if node_type in ("tool", "function"):
        raise ValueError("Node type must be 'code'; tool/function is not a code runner contract")
    return node_type


def _require_validation_kind(request: ValidateRequest) -> CodeExecutionKind:
    raw = (
        request.kind
        if isinstance(request.kind, str) and request.kind.strip()
        else request.node_type
    )
    raw_kind = raw.strip() if isinstance(raw, str) and raw.strip() else "code"
    if raw_kind in ("tool", "function", "resource"):
        return "tool"
    if raw_kind in ("code", "node"):
        return "node"
    raise HTTPException(status_code=400, detail=f"Unsupported code validation kind: {raw_kind}")


class ExecuteRequest(BaseModel):
    """Запрос на выполнение ноды."""

    node_type: str = "code"
    node_config: JsonObject = Field(default_factory=dict)
    code: str | None = None
    state: JsonObject
    entrypoint: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None


class DiffItem(BaseModel):
    """Элемент diff"""

    path: str
    old_value: JsonValue
    new_value: JsonValue
    change_type: str


class ExecuteResponse(BaseModel):
    """Результат выполнения"""

    success: bool
    input_state: JsonObject | None = None
    output_state: JsonObject | None = None
    diff: list[DiffItem] = []
    error: str | None = None
    error_payload: JsonObject | None = None
    duration_ms: int = 0


def _compute_diff(old: JsonObject, new: JsonObject, path: str = "") -> list[DiffItem]:
    """Вычисляет diff между двумя state."""
    diff_items: list[DiffItem] = []
    SKIP_KEYS = {
        "task_id",
        "context_id",
        "user_id",
        "session_id",
        "messages",
        "prompt_history",
        "node_history",
        "nested_states",
        "current_nodes",
        "branch_id",
        "flow_config_version",
        "user_groups",
        "interrupt_path",
        "tool_results",
        "triggers",
        "files",
        "breakpoints",
        "scheduled_tasks",
        "reasoning_history",
        "reflection_history",
        "pending_reasoning",
        "breakpoint_hit",
        "breakpoint_state",
        "interrupt",
        "join_arrived_preds",
        "hitl_handoff_correlation_id",
        "flow_deadline_monotonic",
        "flow_timeout_effective_seconds",
        "terminal_task_state",
        "terminal_task_error",
        "llm_context_memory_cursor",
    }
    all_keys = set(old.keys()) | set(new.keys())

    for key in all_keys:
        current_path = f"{path}.{key}" if path else key
        if key in SKIP_KEYS:
            continue

        old_val = old.get(key)
        new_val = new.get(key)

        if key not in old:
            diff_items.append(
                DiffItem(path=current_path, old_value=None, new_value=new_val, change_type="added")
            )
        elif key not in new:
            diff_items.append(
                DiffItem(
                    path=current_path, old_value=old_val, new_value=None, change_type="removed"
                )
            )
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            diff_items.extend(
                _compute_diff(
                    require_json_object(old_val, f"diff.old.{current_path}"),
                    require_json_object(new_val, f"diff.new.{current_path}"),
                    current_path,
                )
            )
        elif old_val != new_val:
            diff_items.append(
                DiffItem(
                    path=current_path, old_value=old_val, new_value=new_val, change_type="changed"
                )
            )

    return diff_items


async def _merge_execute_state_with_flow(
    input_state: JsonObject,
    *,
    flow_id: str,
    branch_id: str,
    container: "FlowContainer",
) -> None:
    """
    Приближает state к реальному старту flow: файлы из всех нод графа + резолвнутые variables flow.
    Записи state.files из запроса, которых нет среди файлов графа, дописываются в конец.
    """
    runtime_flow = await container.flow_factory.get_flow(flow_id, branch_id)
    if runtime_flow is None:
        raise ValueError(f"Flow не найден: {flow_id}")

    raw_cfg_nodes = runtime_flow.config.get("nodes")
    cfg_nodes_raw = (
        require_json_object(raw_cfg_nodes, "runtime_flow.config.nodes")
        if raw_cfg_nodes is not None
        else {}
    )
    cfg_nodes = {
        node_id: require_json_object(node_config, f"runtime_flow.config.nodes.{node_id}")
        for node_id, node_config in cfg_nodes_raw.items()
    }
    from_graph = collect_flow_node_files(cfg_nodes)
    raw_files = input_state.get("files")
    req_files: list[FileRef] = []
    if raw_files is not None:
        req_files = [
            FileRef.model_validate(require_json_object(item, f"execute.state.files[{index}]"))
            for index, item in enumerate(require_json_array(raw_files, "execute.state.files"))
        ]
    seen: set[tuple[str | None, str | None, str]] = set()
    for file_item in from_graph:
        seen.add((file_item.file_id, file_item.url, file_item.original_name))
    extra: list[FileRef] = []
    for file_item in req_files:
        file_key = (file_item.file_id, file_item.url, file_item.original_name)
        if file_key not in seen:
            extra.append(file_item)
    input_state["files"] = [file_item.to_json_object() for file_item in [*from_graph, *extra]]
    request_variables_raw = input_state.get("variables")
    request_variables = (
        require_json_object(request_variables_raw, "execute.state.variables")
        if request_variables_raw is not None
        else {}
    )
    input_state["variables"] = {
        **runtime_flow.variables,
        **request_variables,
    }
    cfg_ver = runtime_flow.config.get("version")
    if cfg_ver:
        input_state["flow_config_version"] = str(cfg_ver)


@router.post("/validate", response_model=ValidateResponse)
async def validate_code(container: ContainerDep, request: ValidateRequest) -> ValidateResponse:
    """
    Валидирует код без выполнения.
    """
    code = request.code
    validation_kind = _require_validation_kind(request)
    capability_language = _require_capability_language(request.language)
    entrypoint = (
        request.entrypoint.strip()
        if isinstance(request.entrypoint, str) and request.entrypoint.strip()
        else None
    )
    entrypoint_for_validation = entrypoint
    warnings: list[str] = []

    if not code or not code.strip():
        return ValidateResponse(valid=False, error="Код пустой")
    if entrypoint_for_validation is None:
        entrypoint_for_validation = _infer_entrypoint(capability_language, code)
    if entrypoint_for_validation is not None and not _valid_entrypoint_name(
        capability_language, entrypoint_for_validation
    ):
        return ValidateResponse(
            valid=False,
            error=f"Invalid {capability_language} entrypoint name: {entrypoint_for_validation!r}",
        )

    runner = container.get_code_runner(capability_language)
    try:
        validation = await runner.validate_remote(
            code=code,
            entrypoint=entrypoint_for_validation,
            kind=validation_kind,
            flow_id=request.flow_id,
            branch_id=request.branch_id,
        )
    except Exception as exc:
        logger.warning(
            "code.validation_remote_failed",
            language=capability_language,
            kind=validation_kind,
            exception_type=type(exc).__name__,
        )
        return ValidateResponse(
            valid=False,
            error=str(exc),
            stage="service",
            service=CODE_RUNNER_SERVICE_BY_LANGUAGE[capability_language],
            exception_type=type(exc).__name__,
            warnings=warnings,
        )
    if not validation.valid:
        validation_error = validation.error
        if validation_error is None:
            return ValidateResponse(
                valid=False,
                error="Code runner validation failed",
                warnings=validation.warnings,
            )
        return ValidateResponse(
            valid=False,
            error=validation_error.message,
            warnings=validation.warnings,
            stage=validation_error.stage,
            service=validation_error.service,
            exception_type=validation_error.exception_type,
        )
    warnings.extend(validation.warnings)

    return ValidateResponse(valid=True, warnings=warnings)


@router.post("/execute", response_model=ExecuteResponse)
async def execute_code(container: ContainerDep, request: ExecuteRequest) -> ExecuteResponse:
    """
    Выполняет ноду с переданным state.
    """
    input_state_raw = require_json_object(copy.deepcopy(request.state), "execute.state")
    start_time = time.time()

    try:
        input_state_normalized = require_json_object(
            copy.deepcopy(input_state_raw),
            "execute.state",
        )
        _ = input_state_normalized.setdefault("task_id", str(uuid.uuid4()))
        context_id = input_state_normalized.setdefault("context_id", str(uuid.uuid4()))
        if not isinstance(context_id, str) or not context_id.strip():
            raise ValueError("execute.state.context_id must be a non-empty string")
        _ = input_state_normalized.setdefault("user_id", "test_user")
        raw_node_flow_id = request.node_config.get("flow_id")
        if raw_node_flow_id is not None and not isinstance(raw_node_flow_id, str):
            raise ValueError("execute.node_config.flow_id must be a string")
        flow_id = request.flow_id or raw_node_flow_id or "test-flow"
        if "session_id" not in input_state_normalized:
            input_state_normalized["session_id"] = f"{flow_id}:{context_id}"

        state_defaults: JsonObject = {
            "current_nodes": [],
            "branch_id": "default",
            "messages": [],
            "user_groups": [],
            "variables": {},
            "files": [],
            "interrupt_path": [],
            "node_history": {},
            "tool_results": {},
            "execution_exceptions": [],
            "nested_states": {},
            "child_workflows": {},
            "reasoning_history": [],
            "breakpoints": {},
            "scheduled_tasks": [],
            "prompt_history": [],
            "ui_events_pending": [],
            "llm_context_memory_cursor": {},
            "content": None,
            "response": None,
            "pending_reasoning": None,
            "breakpoint_hit": None,
            "breakpoint_state": None,
            "interrupt": None,
            "flow_config_version": None,
            "result": None,
            "validation": None,
            "join_arrived_preds": {},
        }
        for key, value in state_defaults.items():
            _ = input_state_normalized.setdefault(key, value)

        resolved_flow_id = flow_id
        raw_branch_id = input_state_normalized.get("branch_id")
        if raw_branch_id is not None and not isinstance(raw_branch_id, str):
            raise ValueError("execute.state.branch_id must be a string")
        resolved_branch_id = request.branch_id or raw_branch_id or "default"
        if resolved_flow_id and resolved_flow_id not in ("", "test-flow"):
            await _merge_execute_state_with_flow(
                input_state_normalized,
                flow_id=resolved_flow_id,
                branch_id=resolved_branch_id,
                container=container,
            )

        node_config = await _build_node_config(request)
        output_state = await _execute_node(
            node_config, input_state_normalized, container, flow_id=resolved_flow_id
        )

        duration_ms = int((time.time() - start_time) * 1000)
        diff = _compute_diff(input_state_normalized, output_state)

        return ExecuteResponse(
            success=True,
            input_state=input_state_raw,
            output_state=output_state,
            diff=diff,
            duration_ms=duration_ms,
        )

    except CodeExecutionRuntimeError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_text = str(e)
        exception_type = e.payload.get("exception_type")
        if isinstance(exception_type, str) and exception_type and exception_type not in error_text:
            error_text = f"{exception_type}: {error_text}"
        return ExecuteResponse(
            success=False,
            input_state=input_state_raw,
            error=error_text,
            error_payload=e.payload,
            duration_ms=duration_ms,
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Ошибка выполнения: {e}", exc_info=True)
        error_payload = e.payload if isinstance(e, ImanBaseError) else None
        return ExecuteResponse(
            success=False,
            input_state=input_state_raw,
            error=f"Ошибка выполнения: {e}",
            error_payload=error_payload,
            duration_ms=duration_ms,
        )


def _validate_node_config(config: JsonObject) -> None:
    """Валидация обязательных полей для каждого типа ноды."""
    node_type = config.get("type")

    if node_type == "code":
        code = config.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code, tool_id или function обязателен")

    elif node_type == "external_api":
        if not config.get("url"):
            raise ValueError("url обязателен для external_api")

    elif node_type == "remote_flow":
        if not config.get("url") and not config.get("flow_id"):
            raise ValueError("url или flow_id обязателен для remote_flow")

    elif node_type == "flow":
        if not config.get("flow_id"):
            raise ValueError("flow_id обязателен для flow")

    elif node_type == "llm_node":
        if not config.get("prompt"):
            raise ValueError("prompt обязателен для llm_node")

    elif node_type == "mcp":
        if not config.get("server_id"):
            raise ValueError("server_id обязателен для mcp")
        if not config.get("tool_name"):
            raise ValueError("tool_name обязателен для mcp")


async def _build_node_config(request: ExecuteRequest) -> JsonObject:
    """Строит node_config из ExecuteRequest."""
    config = require_json_object(copy.deepcopy(request.node_config), "execute.node_config")
    if request.code is not None and "code" not in config:
        config["code"] = request.code
    config["type"] = _require_execute_node_type(str(request.node_type))
    if request.entrypoint is not None:
        config["entrypoint"] = request.entrypoint

    _validate_node_config(config)
    validation_config: JsonObject = {**config, "node_id": "test_node"}
    _ = NodeConfig.model_validate(validation_config)

    return config


async def _execute_node(
    node_config: JsonObject,
    input_state: JsonObject,
    container: FlowContainer,
    flow_id: str = "test-flow",
) -> JsonObject:
    """Выполняет ноду используя унифицированную фабрику."""
    state_data = require_json_object(copy.deepcopy(input_state), "execute.state")
    _ = state_data.setdefault("task_id", str(uuid.uuid4()))
    _ = state_data.setdefault("context_id", str(uuid.uuid4()))
    _ = state_data.setdefault("user_id", "test_user")
    if "session_id" not in state_data:
        context_id = state_data.get("context_id", str(uuid.uuid4()))
        if not isinstance(context_id, str) or not context_id.strip():
            raise ValueError("execute.state.context_id must be a non-empty string")
        state_data["session_id"] = f"{flow_id}:{context_id}"

    if node_config.get("type") == "llm_node" and "tools" in node_config:
        tools = node_config.get("tools")
        if isinstance(tools, list) and tools:
            node_config = {
                **node_config,
                "tools": await inline_tools_list(tools, container),
            }

    node = await create_node(
        "test_node",
        node_config,
        container=as_flow_runtime_container(container),
    )
    state = ExecutionState.model_validate(state_data)
    node_type = node_config.get("type")
    if not isinstance(node_type, str) or not node_type:
        raise ValueError("execute.node_config.type must be a non-empty string")
    state.current_nodes = ["test_node"]

    runtime = container.workflow_runtime
    base_event = await runtime.record_state_event(
        state.session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(
            flow_id=flow_id,
            branch_id=state.branch_id,
            task_id=state.task_id,
            flow_config_version=state.flow_config_version,
        ),
    )
    superstep_event = await runtime.record_state_event(
        state.session_id,
        state,
        event_type=WorkflowEventType.superstep_started,
        payload=SuperstepStartedPayload(current_nodes=["test_node"]),
    )
    scheduled_event = await runtime.record_state_event(
        state.session_id,
        state,
        event_type=WorkflowEventType.node_scheduled,
        payload=NodeScheduledPayload(
            node_id="test_node",
            node_type=node_type,
            current_nodes=["test_node"],
        ),
    )
    state.attach_durable_node_context(
        execution_branch_id=scheduled_event.execution_branch_id or base_event.execution_branch_id,
        node_schedule_sequence=scheduled_event.sequence,
        superstep_sequence=superstep_event.sequence,
    )
    result_state = await node.run(state)
    _ = await runtime.record_state_event(
        result_state.session_id,
        result_state,
        event_type=WorkflowEventType.node_write_recorded,
        payload=NodeWriteRecordedPayload(
            node_id="test_node",
            node_type=node_type,
            state_delta=build_state_delta(state, result_state),
        ),
    )
    _ = await runtime.record_state_event(
        result_state.session_id,
        result_state,
        event_type=WorkflowEventType.node_completed,
        payload=NodeCompletedPayload(node_id="test_node", node_type=node_type),
    )
    return require_json_object(
        result_state.model_dump(mode="json", exclude_none=False),
        "execute.output_state",
    )
