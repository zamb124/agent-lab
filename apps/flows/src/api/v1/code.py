"""
API endpoints для работы с кодом.

Документация и выполнение идут через единый capability/code-runner контур:
Python, JavaScript, TypeScript, Go и C# получают один manifest возможностей.
"""

import ast
import copy
import importlib
import inspect
import keyword
import re
import time
import uuid
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from apps.flows.src.api.v1.flows import inline_tools_list
from apps.flows.src.container import FlowContainer
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.runtime.nodes import create_node
from apps.flows.src.state import collect_flow_node_files, create_initial_state
from core.capabilities import (
    CAPABILITY_LANGUAGE_SET,
    CapabilityDocumentation,
    CapabilityLanguage,
    CapabilityNamespaceDocumentation,
    CapabilitySdkMethodDocumentation,
)
from core.clients.service_client import ServiceClient
from core.context import get_context
from core.docs.models import (
    CodeTemplate,
    GlobalVariable,
    PlatformToolDoc,
    StateField,
)
from core.errors import CodeExecutionRuntimeError
from core.logging import get_logger
from core.state import ExecutionState

router = APIRouter(tags=["code"])
logger = get_logger(__name__)

CAPABILITY_DOCUMENTATION_PATH = "/capability-gateway/api/v1/capabilities/documentation"


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


def _capability_templates(language: CapabilityLanguage) -> list[CodeTemplate]:
    snippets = {
        "python": (
            "async def run(args, state):\n"
            "    calc = await tools.calculator(expression=args[\"expression\"])\n"
            "    state[\"calculation\"] = calc\n"
            "    return {\"calculation\": calc}\n"
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
            "    calc, err := tools.Calculator(map[string]any{\"expression\": args[\"expression\"]})\n"
            "    if err != nil {\n"
            "        return nil, err\n"
            "    }\n"
            "    state[\"calculation\"] = calc\n"
            "    return map[string]any{\"calculation\": calc}, nil\n"
            "}\n"
        ),
        "csharp": (
            "using System.Collections.Generic;\n"
            "using System.Threading.Tasks;\n\n"
            "async Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
            "{\n"
            "    var calc = await tools.Calculator(new Dictionary<string, object?> { [\"expression\"] = args[\"expression\"] });\n"
            "    state[\"calculation\"] = calc;\n"
            "    return new Dictionary<string, object?> { [\"calculation\"] = calc };\n"
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
    r"(?m)^\s*"
    r"(?:(?:public|private|protected|internal|static|async|virtual|override|sealed|new|partial)\s+)*"
    r"(?:[A-Za-z_][A-Za-z0-9_<>,\[\]\.?]*\s+)+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\("
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


def _has_entrypoint(language: CapabilityLanguage, code: str, entrypoint: str) -> bool:
    if language == "python":
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False
        return any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == entrypoint
            for node in tree.body
        )
    if language in {"javascript", "typescript"}:
        name = re.escape(entrypoint)
        ident = rf"(?<![$\w]){name}(?![$\w])"
        return any(
            re.search(pattern, code) is not None
            for pattern in (
                rf"(?:export\s+)?(?:async\s+)?function\s+{name}\s*\(",
                rf"(?:export\s+)?(?:const|let|var)\s+{name}\s*=",
                rf"export\s+(?:async\s+)?function\s+{name}\s*\(",
                rf"export\s+(?:const|let|var)\s+{name}\s*=",
                rf"export\s*\{{[^}}]*{ident}[^}}]*\}}",
            )
        )
    if language == "go":
        return re.search(rf"func\s+{re.escape(entrypoint)}\s*\(", code) is not None
    if language == "csharp":
        return re.search(
            rf"(?m)^\s*"
            rf"(?:(?:public|private|protected|internal|static|async|virtual|override|sealed|new|partial)\s+)*"
            rf"(?:[A-Za-z_][A-Za-z0-9_<>,\[\]\.?]*\s+)+"
            rf"{re.escape(entrypoint)}\s*\(",
            code,
        ) is not None
    return False


def _entrypoint_error(language: CapabilityLanguage, entrypoint: str) -> str:
    if language == "python":
        return f"Entrypoint function not found: async def {entrypoint}(args, state)"
    if language in {"javascript", "typescript"}:
        return f"Entrypoint function not found: async function {entrypoint}(args, state)"
    if language == "csharp":
        return f"Entrypoint function not found: Task<object?> {entrypoint}(Dictionary<string, object?> args, Dictionary<string, object?> state)"
    return f"Entrypoint function not found: func {entrypoint}(args map[string]any, state map[string]any) (any, error)"


class CodeCompletionsResponse(BaseModel):
    """Данные для autocomplete в редакторе кода"""
    modules: list[str]
    globals: list[GlobalVariable]
    builtins: list[str]
    module_methods: dict[str, list[dict[str, Any]]]
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
        globals=[_capability_global(capability_language)],
        builtins=[],
        module_methods={},
        state_fields=[],
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
    _ = container, category, node_type, tags
    return TemplatesResponse(templates=_capability_templates(capability_language))


@router.get("/editor-state")
async def get_editor_state(
    container: ContainerDep,
    flow_id: str,
    branch_id: str = "default",
) -> dict[str, Any]:
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
    cfg_ver = (runtime_flow.config or {}).get("version")
    if cfg_ver:
        state.flow_config_version = str(cfg_ver)
    state.current_nodes = [runtime_flow.entry]
    cfg_nodes = (runtime_flow.config or {}).get("nodes") or {}
    state.files = collect_flow_node_files(cfg_nodes)

    return state.model_dump(mode="json")


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
        return FlowFunctionsResponse(
            flow_id=flow_id,
            functions=[],
            error="flow_id is required"
        )

    try:
        module_path = f"apps.flows.bundles.{flow_id}.functions"
        module = importlib.import_module(module_path)

        functions = []
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if inspect.isfunction(obj):
                functions.append(FlowFunctionInfo(
                    name=name,
                    path=f"{module_path}.{name}",
                    doc=inspect.getdoc(obj)
                ))

        return FlowFunctionsResponse(
            flow_id=flow_id,
            functions=sorted(functions, key=lambda f: f.name)
        )
    except ModuleNotFoundError:
        return FlowFunctionsResponse(
            flow_id=flow_id,
            functions=[],
            error=f"Module apps.flows.bundles.{flow_id}.functions not found"
        )
    except Exception as e:
        return FlowFunctionsResponse(
            flow_id=flow_id,
            functions=[],
            error=str(e)
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
            return SourceResponse(
                path=path,
                source=None,
                error="Invalid path format"
            )

        obj = None
        for i in range(len(parts) - 1, 0, -1):
            module_path = ".".join(parts[:i])
            try:
                module = importlib.import_module(module_path)
                obj = module
                for attr_name in parts[i:]:
                    obj = getattr(obj, attr_name, None)
                    if obj is None:
                        break
                if obj is not None:
                    break
            except ModuleNotFoundError:
                continue

        if obj is None:
            return SourceResponse(
                path=path,
                source=None,
                error=f"Object not found: {path}"
            )

        source = inspect.getsource(obj)
        return SourceResponse(
            path=path,
            source=source
        )
    except ModuleNotFoundError:
        return SourceResponse(
            path=path,
            source=None,
            error="Module not found"
        )
    except OSError:
        return SourceResponse(
            path=path,
            source=None,
            error="Source code not available"
        )
    except TypeError:
        return SourceResponse(
            path=path,
            source=None,
            error="Cannot get source for built-in"
        )


# ============================================================================
# Валидация и выполнение кода
# ============================================================================

class ValidateRequest(BaseModel):
    """Запрос на валидацию кода"""
    code: str
    node_type: str | None = "code"
    language: str = "python"
    entrypoint: str | None = None


class ValidateResponse(BaseModel):
    """Результат валидации"""
    valid: bool
    error: str | None = None
    warnings: list[str] = []


class ParseSignatureRequest(BaseModel):
    """Запрос на парсинг сигнатуры функции"""
    code: str
    func_name: str | None = None


class ParameterInfo(BaseModel):
    """Информация о параметре функции"""
    type: str
    description: str = ""
    default: Any | None = None
    required: bool = True


class ParseSignatureResponse(BaseModel):
    """Результат парсинга сигнатуры"""
    success: bool
    func_name: str | None = None
    parameters: dict[str, ParameterInfo] = {}
    args_schema: dict[str, Any] | None = None
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


def _parse_function_signature(code: str, func_name: str | None = None) -> dict[str, Any]:
    """
    Парсит сигнатуру функции из Python кода.
    """
    tree = ast.parse(code)
    top_level_funcs = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if func_name:
        candidates = [node for node in top_level_funcs if node.name == func_name]
    else:
        by_name = {node.name: node for node in top_level_funcs}
        candidates = []
        node = by_name.get("run")
        if node is not None:
            candidates.append(node)
        if not candidates and top_level_funcs:
            candidates.append(top_level_funcs[0])

    for node in candidates:
        params = {}
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
            default_value = None
            if has_default:
                default_idx = i - first_default_idx
                default_node = args.defaults[default_idx]
                try:
                    default_value = ast.literal_eval(default_node)
                except (ValueError, TypeError):
                    default_value = ast.unparse(default_node)

            json_type = _python_type_to_json_type(type_str)

            params[param_name] = {
                "type": json_type,
                "python_type": type_str,
                "required": not has_default,
                "has_default": has_default,
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
async def parse_signature(container: ContainerDep, request: ParseSignatureRequest) -> ParseSignatureResponse:
    """
    Парсит сигнатуру функции и генерирует args_schema.
    """
    _ = container
    if not request.code or not request.code.strip():
        return ParseSignatureResponse(success=False, error="Код пустой")

    try:
        result = _parse_function_signature(request.code, request.func_name)

        args_schema = {}
        for param_name, param_info in result["parameters"].items():
            schema_item = {
                "type": param_info["type"],
                "description": f"Параметр {param_name}",
                "required": bool(param_info["required"]),
            }
            if param_info.get("has_default"):
                schema_item["default"] = param_info["default"]
            args_schema[param_name] = schema_item

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
            args_schema=args_schema,
        )

    except SyntaxError as e:
        return ParseSignatureResponse(success=False, error=f"Синтаксическая ошибка: {e}")
    except ValueError as e:
        return ParseSignatureResponse(success=False, error=str(e))
    except Exception as e:
        return ParseSignatureResponse(success=False, error=f"Ошибка парсинга: {e}")


def _require_execute_node_type(node_type: str) -> str:
    if node_type in ("tool", "function"):
        raise ValueError("Node type must be 'code'; tool/function is not a code runner contract")
    return node_type


class ExecuteRequest(BaseModel):
    """Запрос на выполнение ноды."""
    node_type: str = "code"
    node_config: dict[str, Any] = {}
    state: dict[str, Any]
    entrypoint: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None


class DiffItem(BaseModel):
    """Элемент diff"""
    path: str
    old_value: Any
    new_value: Any
    change_type: str


class ExecuteResponse(BaseModel):
    """Результат выполнения"""
    success: bool
    input_state: dict[str, Any] | None = None
    output_state: dict[str, Any] | None = None
    diff: list[DiffItem] = []
    error: str | None = None
    error_payload: dict[str, Any] | None = None
    duration_ms: int = 0


def _compute_diff(old: dict[str, Any], new: dict[str, Any], path: str = "") -> list[DiffItem]:
    """Вычисляет diff между двумя state."""
    diff_items = []
    SKIP_KEYS = {
        "task_id", "context_id", "user_id", "session_id",
        "messages", "prompt_history", "node_history", "nested_states",
        "current_nodes", "branch_id", "flow_config_version", "user_groups",
        "interrupt_path", "tool_results", "triggers", "files",
        "breakpoints", "scheduled_tasks", "reasoning_history",
        "pending_reasoning", "breakpoint_hit", "breakpoint_state", "interrupt",
        "join_arrived_preds", "hitl_handoff_correlation_id",
        "flow_deadline_monotonic", "flow_timeout_effective_seconds",
    }
    all_keys = set(old.keys()) | set(new.keys())

    for key in all_keys:
        current_path = f"{path}.{key}" if path else key
        if key in SKIP_KEYS:
            continue

        old_val = old.get(key)
        new_val = new.get(key)

        if key not in old:
            diff_items.append(DiffItem(
                path=current_path,
                old_value=None,
                new_value=new_val,
                change_type="added"
            ))
        elif key not in new:
            diff_items.append(DiffItem(
                path=current_path,
                old_value=old_val,
                new_value=None,
                change_type="removed"
            ))
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            diff_items.extend(_compute_diff(old_val, new_val, current_path))
        elif old_val != new_val:
            diff_items.append(DiffItem(
                path=current_path,
                old_value=old_val,
                new_value=new_val,
                change_type="changed"
            ))

    return diff_items


async def _merge_execute_state_with_flow(
    input_state: dict[str, Any],
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

    from_graph = collect_flow_node_files(runtime_flow.config.get("nodes") or {})
    req_files = input_state.get("files") or []
    seen = {(f.get("name"), f.get("path")) for f in from_graph}
    extra = [f for f in req_files if (f.get("name"), f.get("path")) not in seen]
    input_state["files"] = list(from_graph) + extra
    input_state["variables"] = {
        **runtime_flow.variables,
        **(input_state.get("variables") or {}),
    }
    cfg_ver = (runtime_flow.config or {}).get("version")
    if cfg_ver:
        input_state["flow_config_version"] = str(cfg_ver)


@router.post("/validate", response_model=ValidateResponse)
async def validate_code(container: ContainerDep, request: ValidateRequest) -> ValidateResponse:
    """
    Валидирует код без выполнения.
    """
    code = request.code
    _require_execute_node_type(request.node_type or "code")
    capability_language = _require_capability_language(request.language)
    entrypoint = request.entrypoint.strip() if isinstance(request.entrypoint, str) and request.entrypoint.strip() else None
    warnings = []

    if not code or not code.strip():
        return ValidateResponse(valid=False, error="Код пустой")
    if entrypoint is None:
        entrypoint = _infer_entrypoint(capability_language, code)
        if entrypoint is None:
            return ValidateResponse(valid=False, error="Entrypoint function not found: declare at least one function")
    if not _valid_entrypoint_name(capability_language, entrypoint):
        return ValidateResponse(valid=False, error=f"Invalid {capability_language} entrypoint name: {entrypoint!r}")

    runner = container.get_code_runner(capability_language)
    valid, error = runner.validate(code)

    if not valid:
        return ValidateResponse(valid=False, error=error)

    if not _has_entrypoint(capability_language, code, entrypoint):
        return ValidateResponse(valid=False, error=_entrypoint_error(capability_language, entrypoint))

    return ValidateResponse(valid=True, warnings=warnings)


@router.post("/execute", response_model=ExecuteResponse)
async def execute_code(container: ContainerDep, request: ExecuteRequest) -> ExecuteResponse:
    """
    Выполняет ноду с переданным state.
    """
    input_state_raw = copy.deepcopy(request.state)
    start_time = time.time()

    try:
        input_state_normalized = copy.deepcopy(input_state_raw)
        input_state_normalized.setdefault("task_id", str(uuid.uuid4()))
        context_id = input_state_normalized.setdefault("context_id", str(uuid.uuid4()))
        input_state_normalized.setdefault("user_id", "test_user")
        flow_id = request.flow_id or request.node_config.get("flow_id") or "test-flow"
        if "session_id" not in input_state_normalized:
            input_state_normalized["session_id"] = f"{flow_id}:{context_id}"

        input_state_normalized.setdefault("current_nodes", [])
        input_state_normalized.setdefault("branch_id", "default")
        input_state_normalized.setdefault("messages", [])
        input_state_normalized.setdefault("user_groups", [])
        input_state_normalized.setdefault("variables", {})
        input_state_normalized.setdefault("files", [])
        input_state_normalized.setdefault("interrupt_path", [])
        input_state_normalized.setdefault("node_history", {})
        input_state_normalized.setdefault("tool_results", {})
        input_state_normalized.setdefault("execution_exceptions", [])
        input_state_normalized.setdefault("nested_states", {})
        input_state_normalized.setdefault("reasoning_history", [])
        input_state_normalized.setdefault("breakpoints", {})
        input_state_normalized.setdefault("scheduled_tasks", [])
        input_state_normalized.setdefault("prompt_history", [])
        input_state_normalized.setdefault("content", None)
        input_state_normalized.setdefault("response", None)
        input_state_normalized.setdefault("mock", None)
        input_state_normalized.setdefault("pending_reasoning", None)
        input_state_normalized.setdefault("breakpoint_hit", None)
        input_state_normalized.setdefault("breakpoint_state", None)
        input_state_normalized.setdefault("interrupt", None)
        input_state_normalized.setdefault("flow_config_version", None)
        input_state_normalized.setdefault("result", None)
        input_state_normalized.setdefault("validation", None)
        input_state_normalized.setdefault("join_arrived_preds", {})

        resolved_flow_id = flow_id
        resolved_skill_id = (
            request.branch_id
            or input_state_normalized.get("branch_id")
            or "default"
        )
        if resolved_flow_id and resolved_flow_id not in ("", "test-flow"):
            await _merge_execute_state_with_flow(
                input_state_normalized,
                flow_id=resolved_flow_id,
                branch_id=resolved_skill_id,
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
            duration_ms=duration_ms
        )

    except CodeExecutionRuntimeError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return ExecuteResponse(
            success=False,
            input_state=input_state_raw,
            error=str(e),
            error_payload=e.payload,
            duration_ms=duration_ms,
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Ошибка выполнения: {e}", exc_info=True)
        return ExecuteResponse(
            success=False,
            input_state=input_state_raw,
            error=f"Ошибка выполнения: {e}",
            error_payload=getattr(e, "payload", None) if isinstance(getattr(e, "payload", None), dict) else None,
            duration_ms=duration_ms
        )


def _validate_node_config(config: dict[str, Any]) -> None:
    """Валидация обязательных полей для каждого типа ноды."""
    node_type = config.get("type")

    if node_type == "code":
        if not config.get("code"):
            raise ValueError("code is required for code node execution")

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


async def _build_node_config(request: ExecuteRequest) -> dict[str, Any]:
    """Строит node_config из ExecuteRequest."""
    config = request.node_config.copy()
    config["type"] = _require_execute_node_type(str(request.node_type))
    if request.entrypoint is not None:
        config["entrypoint"] = request.entrypoint

    _validate_node_config(config)

    return config


async def _execute_node(
    node_config: dict[str, Any],
    input_state: dict[str, Any],
    container: FlowContainer,
    flow_id: str = "test-flow",
) -> dict[str, Any]:
    """Выполняет ноду используя унифицированную фабрику."""
    state_data = copy.deepcopy(input_state)
    state_data.setdefault("task_id", str(uuid.uuid4()))
    state_data.setdefault("context_id", str(uuid.uuid4()))
    state_data.setdefault("user_id", "test_user")
    if "session_id" not in state_data:
        context_id = state_data.get("context_id", str(uuid.uuid4()))
        state_data["session_id"] = f"{flow_id}:{context_id}"

    if node_config.get("type") == "llm_node" and "tools" in node_config:
        tools = node_config["tools"]
        if tools:
            node_config = {**node_config, "tools": await inline_tools_list(tools, container)}

    node = await create_node("test_node", node_config, container=container)
    state = ExecutionState.model_validate(state_data)
    result_state = await node.run(state)
    return result_state.model_dump(exclude_none=False)
