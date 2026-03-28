"""
API endpoints для работы с кодом.
Предоставляет данные для autocomplete в редакторе Python.
Эндпоинты для валидации и выполнения inline кода.
"""

import copy
import importlib
import inspect
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.logging import get_logger
from core.state import ExecutionState
from core.docs import DocumentationQuery
from core.docs.service import get_documentation_service
from core.docs.models import (
    GlobalVariable,
    StateField,
    CodeTemplate,
)
from core.context import get_context
from core.errors import SafeEvalError
from apps.flows.src.runtime.nodes import create_node
from apps.flows.src.api.v1.flows import _inline_tools_list
from apps.flows.src.container import get_container
from apps.flows.src.runners import PythonCodeRunner
from apps.flows.src.state import create_initial_state

router = APIRouter(tags=["code"])
logger = get_logger(__name__)


class CodeCompletionsResponse(BaseModel):
    """Данные для autocomplete в редакторе кода"""
    modules: List[str]
    globals: List[GlobalVariable]
    builtins: List[str]
    module_methods: Dict[str, List[Dict[str, Any]]]
    state_fields: List[StateField] = []
    templates: List[CodeTemplate] = []


@router.get("/completions", response_model=CodeCompletionsResponse)
async def get_code_completions(
    language: str = "python",
    perspective: str = "editor",
) -> CodeCompletionsResponse:
    """
    Возвращает данные для autocomplete в редакторе кода.
    
    Args:
        language: Язык программирования (python, javascript)
        perspective: Ракурс (editor, flow, tool, node)
    
    Returns:
        modules: доступные модули для import
        globals: глобальные переменные (llm, context, etc.)
        builtins: встроенные функции
        module_methods: методы модулей
        state_fields: поля state
        templates: шаблоны кода
    """
    service = get_documentation_service()
    
    query = DocumentationQuery(
        language=language,
        perspective=perspective,
    )
    
    response = service.query(query)
    
    # Конвертируем module_methods в dict формат для API
    module_methods = {
        name: [{"name": m.name, "type": m.type, "doc": m.doc} for m in methods]
        for name, methods in response.module_methods.items()
    }
    
    return CodeCompletionsResponse(
        modules=response.modules,
        globals=response.globals,
        builtins=response.builtins,
        module_methods=module_methods,
        state_fields=response.state_fields,
        templates=response.templates,
    )


class TemplatesResponse(BaseModel):
    """Список шаблонов кода"""
    templates: List[CodeTemplate]


@router.get("/templates", response_model=TemplatesResponse)
async def get_code_templates(
    language: str = "python",
    category: Optional[str] = None,
    node_type: Optional[str] = None,
    tags: Optional[str] = None,
) -> TemplatesResponse:
    """
    Возвращает список шаблонов кода с фильтрацией.
    
    Args:
        language: Язык программирования (python, javascript)
        category: Фильтр по категории (http, llm, interaction, data, files, state, logic, basic)
        node_type: Тип ноды (tool, function)
        tags: Теги через запятую (http,api)
    """
    service = get_documentation_service()
    
    categories = [category] if category else None
    tag_list = tags.split(",") if tags else None
    
    query = DocumentationQuery(
        language=language,
        node_type=node_type,
        categories=categories,
        tags=tag_list,
        include_modules=False,
        include_globals=False,
        include_builtins=False,
        include_state_fields=False,
    )
    
    response = service.query(query)
    return TemplatesResponse(templates=response.templates)


@router.get("/editor-state")
async def get_editor_state(
    flow_id: str,
    skill_id: str = "default",
) -> Dict[str, Any]:
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

    container = get_container()
    runtime_flow = await container.flow_factory.get_flow(flow_id, skill_id)
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
        skill_id=skill_id,
    )
    state.variables = {**state.variables, **runtime_flow.variables}
    cfg_ver = (runtime_flow.config or {}).get("version")
    if cfg_ver:
        state.flow_config_version = str(cfg_ver)
    state.current_nodes = [runtime_flow.entry]

    return state.model_dump(mode="json")


class SourceResponse(BaseModel):
    """Исходный код"""
    path: str
    source: Optional[str]
    error: Optional[str] = None


@router.get("/source")
async def get_function_source(function_path: str) -> SourceResponse:
    """
    Возвращает исходный код функции по её пути.
    
    Пример: apps.flows.bundles.<flow_id>.functions.my_function
    """
    if not function_path:
        raise HTTPException(status_code=400, detail="function_path is required")

    return _get_source_by_path(function_path)


class FlowFunctionInfo(BaseModel):
    """Функция из модуля ``bundles.<flow_id>.functions``."""
    name: str
    path: str
    doc: Optional[str] = None


class FlowFunctionsResponse(BaseModel):
    """Список функций из bundle flow (``functions.py``)."""
    flow_id: str
    functions: List[FlowFunctionInfo]
    error: Optional[str] = None


@router.get("/flow-functions")
async def get_flow_functions(flow_id: str) -> FlowFunctionsResponse:
    """
    Возвращает список функций из ``apps/flows/bundles/<flow_id>/functions.py``.
    """
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
async def get_tool_source(tool_path: str) -> SourceResponse:
    """
    Возвращает исходный код tool класса по его пути.
    
    Пример: tools.calculator.Calculator
    """
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
    node_type: Optional[str] = "function"


class ValidateResponse(BaseModel):
    """Результат валидации"""
    valid: bool
    error: Optional[str] = None
    warnings: List[str] = []


class ParseSignatureRequest(BaseModel):
    """Запрос на парсинг сигнатуры функции"""
    code: str
    func_name: Optional[str] = None


class ParameterInfo(BaseModel):
    """Информация о параметре функции"""
    type: str
    description: str = ""
    default: Optional[Any] = None
    required: bool = True


class ParseSignatureResponse(BaseModel):
    """Результат парсинга сигнатуры"""
    success: bool
    func_name: Optional[str] = None
    parameters: Dict[str, ParameterInfo] = {}
    args_schema: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


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


def _parse_function_signature(code: str, func_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Парсит сигнатуру функции из Python кода.
    """
    import ast
    
    tree = ast.parse(code)
    target_names = [func_name] if func_name else ["execute", "run"]
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in target_names or (func_name is None and not node.name.startswith("_")):
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
                        "default": default_value,
                    }
                
                return {
                    "func_name": node.name,
                    "parameters": params,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                }
    
    raise ValueError(f"Функция не найдена: {target_names}")


@router.post("/parse-signature", response_model=ParseSignatureResponse)
async def parse_signature(request: ParseSignatureRequest) -> ParseSignatureResponse:
    """
    Парсит сигнатуру функции и генерирует args_schema.
    """
    if not request.code or not request.code.strip():
        return ParseSignatureResponse(success=False, error="Код пустой")
    
    try:
        result = _parse_function_signature(request.code, request.func_name)
        
        args_schema = {}
        for param_name, param_info in result["parameters"].items():
            schema_item = {
                "type": param_info["type"],
                "description": f"Параметр {param_name}",
            }
            if param_info["default"] is not None:
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


class ExecuteRequest(BaseModel):
    """Запрос на выполнение ноды."""
    node_type: str = "code"
    node_config: Dict[str, Any] = {}
    state: Dict[str, Any]


class DiffItem(BaseModel):
    """Элемент diff"""
    path: str
    old_value: Any
    new_value: Any
    change_type: str


class ExecuteResponse(BaseModel):
    """Результат выполнения"""
    success: bool
    input_state: Optional[Dict[str, Any]] = None
    output_state: Optional[Dict[str, Any]] = None
    diff: List[DiffItem] = []
    error: Optional[str] = None
    duration_ms: int = 0


def _compute_diff(old: Dict[str, Any], new: Dict[str, Any], path: str = "") -> List[DiffItem]:
    """Вычисляет diff между двумя state."""
    diff_items = []
    SKIP_KEYS = {
        "task_id", "context_id", "user_id", "session_id",
        "messages", "prompt_history", "node_history", "nested_states",
        "current_nodes", "skill_id", "flow_config_version", "user_groups",
        "interrupt_path", "tool_results", "triggers", "files",
        "breakpoints", "scheduled_tasks", "reasoning_history",
        "pending_reasoning", "breakpoint_hit", "breakpoint_state", "interrupt"
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


@router.post("/validate", response_model=ValidateResponse)
async def validate_code(request: ValidateRequest) -> ValidateResponse:
    """
    Валидирует код без выполнения.
    """
    code = request.code
    node_type = request.node_type or "code"
    warnings = []

    if not code or not code.strip():
        return ValidateResponse(valid=False, error="Код пустой")

    runner = PythonCodeRunner()
    valid, error = runner.validate(code)
    
    if not valid:
        return ValidateResponse(valid=False, error=error)

    # Проверяем что код содержит хотя бы одну функцию
    import re
    if not re.search(r"(?:async\s+)?def\s+\w+\s*\(", code):
        return ValidateResponse(valid=False, error="Функция не найдена в коде")
    
    return ValidateResponse(valid=True, warnings=warnings)


@router.post("/execute", response_model=ExecuteResponse)
async def execute_code(request: ExecuteRequest) -> ExecuteResponse:
    """
    Выполняет ноду с переданным state.
    """
    input_state_raw = copy.deepcopy(request.state)
    start_time = time.time()

    try:
        input_state_normalized = copy.deepcopy(input_state_raw)
        task_id = input_state_normalized.setdefault("task_id", str(uuid.uuid4()))
        context_id = input_state_normalized.setdefault("context_id", str(uuid.uuid4()))
        input_state_normalized.setdefault("user_id", "test_user")
        flow_id = request.node_config.get("flow_id", "test-flow")
        if "session_id" not in input_state_normalized:
            input_state_normalized["session_id"] = f"{flow_id}:{context_id}"
        
        input_state_normalized.setdefault("current_nodes", [])
        input_state_normalized.setdefault("skill_id", "default")
        input_state_normalized.setdefault("messages", [])
        input_state_normalized.setdefault("user_groups", [])
        input_state_normalized.setdefault("variables", {})
        input_state_normalized.setdefault("files", [])
        input_state_normalized.setdefault("interrupt_path", [])
        input_state_normalized.setdefault("node_history", {})
        input_state_normalized.setdefault("tool_results", {})
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
        
        node_config = await _build_node_config(request)
        output_state = await _execute_node(node_config, input_state_normalized, flow_id=flow_id)

        duration_ms = int((time.time() - start_time) * 1000)
        diff = _compute_diff(input_state_normalized, output_state)

        return ExecuteResponse(
            success=True,
            input_state=input_state_raw,
            output_state=output_state,
            diff=diff,
            duration_ms=duration_ms
        )

    except SafeEvalError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return ExecuteResponse(
            success=False,
            input_state=input_state_raw,
            error=str(e),
            duration_ms=duration_ms
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Ошибка выполнения: {e}", exc_info=True)
        return ExecuteResponse(
            success=False,
            input_state=input_state_raw,
            error=f"Ошибка выполнения: {e}",
            duration_ms=duration_ms
        )


def _validate_node_config(config: Dict[str, Any]) -> None:
    """Валидация обязательных полей для каждого типа ноды."""
    node_type = config.get("type")
    
    if node_type == "code":
        if not config.get("code") and not config.get("tool_id") and not config.get("function"):
            raise SafeEvalError("code, tool_id или function обязателен для code")
    
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


async def _build_node_config(request: ExecuteRequest) -> Dict[str, Any]:
    """Строит node_config из ExecuteRequest."""
    config = request.node_config.copy()
    config["type"] = request.node_type
    
    # Обратная совместимость: если node_config пустой, но есть поля напрямую в request
    # (старый формат API)
    if not config and hasattr(request, '__dict__'):
        request_dict = request.__dict__
        # Переносим поля из request в config (кроме node_type и state)
        for key, value in request_dict.items():
            if key not in ("node_type", "state", "node_config") and value is not None:
                config[key] = value
    
    _validate_node_config(config)
    
    return config


async def _execute_node(node_config: Dict[str, Any], input_state: Dict[str, Any], flow_id: str = "test-flow") -> Dict[str, Any]:
    """Выполняет ноду используя унифицированную фабрику."""
    state_data = copy.deepcopy(input_state)
    state_data.setdefault("task_id", str(uuid.uuid4()))
    state_data.setdefault("context_id", str(uuid.uuid4()))
    state_data.setdefault("user_id", "test_user")
    if "session_id" not in state_data:
        context_id = state_data.get("context_id", str(uuid.uuid4()))
        state_data["session_id"] = f"{flow_id}:{context_id}"
    
    # Инлайним tools для llm_node если они переданы как строки
    if node_config.get("type") == "llm_node" and "tools" in node_config:
        tools = node_config["tools"]
        if tools:
            container = get_container()
            node_config = {**node_config, "tools": await _inline_tools_list(tools, container)}
    
    node = await create_node("test_node", node_config)
    state = ExecutionState.model_validate(state_data)
    result_state = await node.run(state)
    return result_state.model_dump(exclude_none=False)
