"""
Утилиты для мета-тула codegen: эвристики фидбэка, markdown документации sandbox, один механический
прогон кода через `PythonCodeRunner` (без LLM и без JSON-ответа).

Оркестрация (промпт, цикл попыток) живёт в `apps/flows/tools/sandbox_codegen.py`.
"""

from __future__ import annotations

import re
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Union

from apps.flows.src.services.runtime_namespace_doc import build_runtime_namespace_global_variables
from core.docs import DocumentationQuery
from core.docs.service import get_documentation_service
from core.errors import SafeEvalError
from core.state import ExecutionState


def import_merged_with_async_def_on_same_line(code: str) -> bool:
    """`import re async def run` и аналоги — невалидный Python."""
    for line in code.splitlines():
        if " async def " not in line:
            continue
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            return True
    return False


def import_or_async_glued_without_newlines(code: str) -> bool:
    if re.search(r"import\s+\w+import\b", code):
        return True
    if re.search(r"[A-Za-z0-9_]async def\b", code):
        return True
    return False


def sandbox_feedback_hint(detail: str) -> str:
    d = detail or ""
    if "Access to '" in d and "is not allowed" in d:
        return (
            "\nЗапрещены только перечисленные в политике sandbox атрибуты интроспекции "
            "(например __class__, __bases__). Вызовы super().__init__() и обычные dunder-методы классов допустимы.\n"
        )
    if "Import of '" in d or ("импорт" in d.lower() and "недоступен" in d.lower()):
        return (
            "\nПроверь импорты: только whitelist из документации и имена из глобалов sandbox; "
            "для объектов уже в namespace можно писать `import имя`.\n"
        )
    return ""


def syntax_retry_hint(code: str, detail: str) -> str:
    d = (detail or "").lower()
    if "syntax" not in d and "invalid syntax" not in d:
        return ""
    chunks: List[str] = []
    non_empty_lines = [ln for ln in code.split("\n") if ln.strip()]
    if len(non_empty_lines) <= 1 and len(code) > 120:
        chunks.append(
            "Код должен быть обычным многострочным Python: после `:` — перевод строки, "
            "тело блока с отступом 4 пробела; не помещай всё тело функции в одну строку "
            "(каждый элемент `code_lines` — одна строка файла; не склеивай несколько операторов в один элемент)."
        )
    if import_merged_with_async_def_on_same_line(code):
        chunks.append(
            "Каждый `import` и каждый `from ... import` — отдельной строкой в начале фрагмента, "
            "до объявления `async def`; нельзя писать `import …` и `async def …` в одной строке."
        )
    if import_or_async_glued_without_newlines(code):
        chunks.append(
            "Между операторами обязательны переводы строк: нельзя склеивать токены без `\\n` "
            "(недопустимо `import httpximport re` или `reasync def` — должно быть три отдельные "
            "строки `import httpx`, `import re`, `async def run(state):`)."
        )
    if not chunks:
        return ""
    return "\n\n" + "\n\n".join(chunks)


async def build_sandbox_docs_markdown() -> str:
    runtime_extras = build_runtime_namespace_global_variables()
    query = DocumentationQuery(
        language="python",
        perspective="tool",
        include_templates=False,
        include_platform_tools=False,
        markdown_expand_module_methods=False,
        markdown_expand_builtins=False,
        runtime_namespace_extras=runtime_extras,
    )
    return get_documentation_service().to_markdown(query)


def execution_state_for_codegen(state: Any) -> ExecutionState:
    if state is None:
        raise ValueError("codegen: параметр state обязателен")
    if isinstance(state, ExecutionState):
        return state.model_copy(deep=True)
    if isinstance(state, dict):
        return ExecutionState.model_validate(state).model_copy(deep=True)
    raise ValueError(f"codegen: state должен быть ExecutionState или dict, получено {type(state)!s}")


@dataclass(frozen=True)
class CodegenStagesSuccess:
    result: dict[str, Any]


@dataclass(frozen=True)
class CodegenStagesFailure:
    phase: Literal["validate", "compile", "execute", "result"]
    detail: str
    traceback: str


CodegenStagesResult = Union[CodegenStagesSuccess, CodegenStagesFailure]


async def run_codegen_stages(
    runner: Any,
    code: str,
    exec_state: ExecutionState,
) -> CodegenStagesResult:
    """Ожидается `PythonCodeRunner` из `get_code_runner(\"python\")` (фасад `platform_services`). Код — `async def run(state):` → dict."""
    try:
        runner.compiler.validate(code)
    except Exception as e:
        return CodegenStagesFailure(
            phase="validate",
            detail=str(e),
            traceback=traceback.format_exc(),
        )

    try:
        runner.compiler.compile(code, "run", auto_find=True)
    except SafeEvalError as e:
        return CodegenStagesFailure(
            phase="compile",
            detail=str(e),
            traceback=traceback.format_exc(),
        )

    try:
        raw_result = await runner.execute(code, exec_state, func_name="run")
    except Exception as e:
        return CodegenStagesFailure(
            phase="execute",
            detail=str(e),
            traceback=traceback.format_exc(),
        )

    if not isinstance(raw_result, dict):
        detail = f"Ожидался dict, получено {type(raw_result)!s}"
        return CodegenStagesFailure(phase="result", detail=detail, traceback="")

    return CodegenStagesSuccess(result=raw_result)
