"""
Мета-тул sandbox_codegen: генерация Python в песочнице по задаче (LLM + validate/compile/execute).

Механика прогона — `apps.flows.src.eval.codegen_utils` (`run_codegen_stages`).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.flows.src.eval.codegen_utils import (
    CodegenStagesFailure,
    CodegenStagesSuccess,
    build_sandbox_docs_markdown,
    execution_state_for_codegen,
    import_merged_with_async_def_on_same_line,
    import_or_async_glued_without_newlines,
    run_codegen_stages,
    sandbox_feedback_hint,
    syntax_retry_hint,
)
from apps.flows.src.eval.platform_services import get_code_runner
from apps.flows.src.tools import tool
from core.clients.llm import get_llm

SANDBOX_CODEGEN_DEFAULT_MODEL = "qwen/qwen3.5-397b-a17b"


class LLMGeneratedCode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code_lines: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "Исходник Python как массив строк: каждый элемент — ровно одна физическая строка файла .py "
            "по порядку сверху вниз; пустая строка в файле — элемент ''. Отступы тел блоков — пробелы "
            "в начале элемента. Запрещено вставлять \\n внутрь одного элемента и склеивать несколько "
            "операторов в одном элементе (отдельные элементы для import httpx, import re, async def …)."
        ),
    )

    @field_validator("code_lines", mode="before")
    @classmethod
    def _coerce_code_lines(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError(
                "code_lines должен быть JSON-массивом строк; каждая строка .py — отдельный элемент",
            )
        return [str(item) for item in value]

    @field_validator("code_lines", mode="after")
    @classmethod
    def _no_embedded_newlines_in_code_lines(cls, value: List[str]) -> List[str]:
        for i, line in enumerate(value):
            if "\n" in line or "\r" in line:
                raise ValueError(
                    f"code_lines[{i}]: один элемент — одна строка без символов перевода внутри; "
                    "разбей на несколько элементов массива",
                )
        return value


class SandboxCodegenArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task: str = Field(..., min_length=1, description="Что должен сделать код во время выполнения.")
    run_variables: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Опционально: словарь, сливаемый в state.variables перед run (числа, входы; в коде — state.variables).",
    )
    output_json_schema: Optional[str] = Field(
        default=None,
        description="Опционально: текст JSON Schema ожидаемого dict в результате.",
    )
    max_iterations: int = Field(default=5, ge=1, le=20)
    max_doc_chars: int = Field(default=120_000, ge=5000, le=500_000)
    model: str = Field(
        default=SANDBOX_CODEGEN_DEFAULT_MODEL,
        min_length=1,
        description="Имя модели LLM для codegen (OpenRouter id).",
    )

    @field_validator("model", mode="before")
    @classmethod
    def _model_non_empty(cls, value: Any) -> Any:
        if value is None:
            return SANDBOX_CODEGEN_DEFAULT_MODEL
        if isinstance(value, str) and value.strip() == "":
            return SANDBOX_CODEGEN_DEFAULT_MODEL
        return value

    @field_validator("run_variables", mode="before")
    @classmethod
    def _coerce_run_variables(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                return None
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "run_variables: нужен объект или JSON-объект в строке",
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError("run_variables: после JSON.parse ожидается объект с парами ключ-значение")
            return parsed
        raise ValueError(
            f"run_variables: ожидался dict или строка с JSON-объектом, получено {type(value).__name__}",
        )


def _system_rules_block() -> str:
    return (
        "Ты генерируешь только Python для sandbox Humanitec (inline code flows).\n"
        "Запрещены импорты apps.* и core.* и любой доступ к закрытым модулям платформы.\n"
        "Используй только API из приложенной документации.\n"
        "Ровно одна функция `async def run(state):`, возвращает `dict` (сериализуемый JSON-объект). "
        "Входные данные вызова — в `state.variables` (поле вызова `run_variables` сливается туда перед run).\n"
        "Формат ответа модели: поле `code_lines` — JSON-массив строк; каждый элемент — одна строка будущего .py "
        "(первая строка файла — первый элемент). Несколько операторов подряд — несколько элементов. "
        "Пустая строка в файле — элемент \"\". Нельзя класть перевод строки внутрь одного элемента.\n"
        "После `:` следующая логическая строка — следующий элемент с отступом 4 пробела в начале.\n"
        "Импорты: отдельный элемент на каждый `import` / `from`; перед `async def` — отдельный элемент; "
        "запрещено в одном элементе писать `import re async def` или `import httpximport`.\n"
        "Regex в строках: для пробелов в шаблоне нужен один "
        "обратный слэш перед `s` (как в обычном .py), не цепочка из лишних слэшей — иначе матчится "
        "литерал, а не класс whitespace.\n"
    )


# Обратная совместимость тестов (префикс _).
_LLMGeneratedCode = LLMGeneratedCode
_build_sandbox_docs_markdown = build_sandbox_docs_markdown
_import_merged_with_async_def_on_same_line = import_merged_with_async_def_on_same_line
_import_or_async_glued_without_newlines = import_or_async_glued_without_newlines
_syntax_retry_hint = syntax_retry_hint
_sandbox_feedback_hint = sandbox_feedback_hint


@tool(
    name="sandbox_codegen",
    description=(
        "Сгенерировать и выполнить Python в песочнице Humanitec по полю task (codegen). "
        "Ожидается async def run(state): → dict. Опционально run_variables сливается в state.variables. "
        "Ответ — JSON-строка: success, result, final_code, attempts, trace."
    ),
    tags=["eval", "codegen", "inline", "sandbox"],
    args_schema=SandboxCodegenArgs,
    listed_in_platform_tool_docs=False,
)
async def sandbox_codegen(
    task: str,
    run_variables: Optional[Any] = None,
    output_json_schema: Optional[str] = None,
    max_iterations: int = 5,
    max_doc_chars: int = 120_000,
    model: str = "qwen/qwen3.5-397b-a17b",
    state: Optional[Any] = None,
) -> str:
    # FunctionTool._run_impl уже валидирует args через SandboxCodegenArgs и передаёт сюда keyword-аргументы.
    # Логика копии state — внутри тела: при code/execute весь туль исполняется как отдельная строка (<string>);
    # воркер не подмешивает в namespace функции с уровня модуля (например бывший _exec_state_for_sandbox_run).
    base = execution_state_for_codegen(state)
    if run_variables:
        exec_state = base.model_copy(
            update={"variables": {**base.variables, **run_variables}},
        )
    else:
        exec_state = base
    doc_md = await build_sandbox_docs_markdown()
    if len(doc_md) > max_doc_chars:
        doc_md = (
            doc_md[:max_doc_chars]
            + "\n\n# ... [documentation truncated by max_doc_chars]\n"
        )

    system_rules = _system_rules_block()
    schema_hint = ""
    if output_json_schema and output_json_schema.strip():
        schema_hint = f"\nОриентир формы ответа (JSON Schema):\n{output_json_schema.strip()}\n"

    doc_block = "## Документация sandbox\n\n" + doc_md
    system_content = system_rules + schema_hint + doc_block

    exec_runner = get_code_runner(language="python")
    llm = get_llm(model_name=model, state=exec_state)

    trace: List[Dict[str, Any]] = []
    last_code = ""
    feedback: Optional[str] = None

    for attempt in range(1, max_iterations + 1):
        user_parts: List[str] = [f"Задача:\n{task}"]
        if last_code:
            user_parts.append(f"Текущий код:\n```python\n{last_code}\n```")
        if feedback:
            user_parts.append(feedback)
        user_content = "\n\n".join(user_parts)

        gen = await llm.chat(
            [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            response_model=LLMGeneratedCode,
            model=model,
        )
        code = "\n".join(gen.code_lines).strip()
        last_code = code
        feedback = None

        out = await run_codegen_stages(exec_runner, code, exec_state)
        if isinstance(out, CodegenStagesSuccess):
            trace.append({"attempt": attempt, "phase": "success", "detail": "ok"})
            return json.dumps(
                {
                    "success": True,
                    "result": out.result,
                    "final_code": last_code,
                    "attempts": attempt,
                    "trace": trace,
                },
                ensure_ascii=False,
            )

        fail: CodegenStagesFailure = out
        trace.append(
            {
                "attempt": attempt,
                "phase": fail.phase,
                "detail": fail.detail,
                "traceback": fail.traceback,
            }
        )
        if fail.phase == "validate":
            feedback = (
                f"Ошибка проверки кода (sandbox, фаза validate): {fail.detail}\n"
                "Полный traceback есть только в trace ответа тула для отладки; для исправления кода "
                "достаточно сообщения выше и правил из system.\nИсправь код."
                + sandbox_feedback_hint(fail.detail)
                + syntax_retry_hint(code, fail.detail)
            )
        elif fail.phase == "compile":
            feedback = (
                f"Ошибка компиляции (фаза compile): {fail.detail}\n"
                "Traceback — в trace ответа тула.\nИсправь код."
                + sandbox_feedback_hint(fail.detail)
                + syntax_retry_hint(code, fail.detail)
            )
        elif fail.phase == "execute":
            feedback = (
                f"Ошибка выполнения (фаза execute): {fail.detail}\n"
                "Traceback — в trace ответа тула.\nИсправь код."
            )
        else:
            feedback = (
                f"Ошибка: код должен вернуть dict (JSON-объект). {fail.detail}\nИсправь код."
            )

    return json.dumps(
        {
            "success": False,
            "result": None,
            "final_code": last_code,
            "attempts": max_iterations,
            "trace": trace,
            "error": "max_iterations_exhausted",
        },
        ensure_ascii=False,
    )
