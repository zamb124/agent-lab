"""
Тесты мета-тула sandbox_codegen (MockLLM, реальный PythonCodeRunner).

Путь агента: await tool.run(args, state) — см. test_sandbox_codegen_tool_run_real_eval_pipeline (без monkeypatch).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from apps.flows.tools.sandbox_codegen import (
    SandboxCodegenArgs,
    _build_sandbox_docs_markdown,
    _import_merged_with_async_def_on_same_line,
    _import_or_async_glued_without_newlines,
    _LLMGeneratedCode,
    _syntax_retry_hint,
    sandbox_codegen,
)
from core.clients.llm.factory import setup_mock_responses
from core.docs import DocumentationQuery
from core.docs.service import get_documentation_service
from core.state import ExecutionState


def _mock_structured_code(code: str) -> dict:
    """Как ожидает MockLLM structured_output под sandbox_codegen: массив строк файла."""
    return {"code_lines": code.splitlines()}


def test_llm_generated_code_rejects_embedded_newline_in_line():
    with pytest.raises(ValidationError):
        _LLMGeneratedCode.model_validate({"code_lines": ["import os", "a\nb"]})


def test_llm_generated_code_joins_lines():
    m = _LLMGeneratedCode.model_validate(
        {"code_lines": ["import os", "", "async def run(state):", "    return {}"]},
    )
    assert m.code_lines[1] == ""
    assert "\n".join(m.code_lines) == "import os\n\nasync def run(state):\n    return {}"


def test_sandbox_codegen_args_run_variables_json_string():
    m = SandboxCodegenArgs.model_validate(
        {
            "task": "сложи числа",
            "run_variables": '{"a": 3, "b": 5}',
        },
    )
    assert m.run_variables == {"a": 3, "b": 5}


def test_syntax_retry_hint_collapsed_one_line():
    code = "async def run(state):    import httpx    return {}    " * 8
    hint = _syntax_retry_hint(code, "Syntax error: invalid syntax (<unknown>, line 1)")
    assert "многострочным" in hint
    assert hint != ""


def test_syntax_retry_hint_skips_for_multiline():
    code = "async def run(state):\n    return {'ok': True}\n"
    assert _syntax_retry_hint(code, "Syntax error: invalid syntax") == ""


def test_import_or_async_glued_detects_collapsed_structured_output():
    collapsed = (
        "import httpximport reasync def run(state):\n    return {}\n"
    )
    assert _import_or_async_glued_without_newlines(collapsed)
    assert "httpximport" in _syntax_retry_hint(collapsed, "SyntaxError: invalid syntax")


def test_import_merged_with_async_def_detected():
    assert _import_merged_with_async_def_on_same_line(
        "import re async def run(state):\n    return {}\n",
    )
    assert _import_merged_with_async_def_on_same_line(
        "from html import unescape async def run(state):\n    return {}\n",
    )
    assert not _import_merged_with_async_def_on_same_line(
        "import re\n\nasync def run(state):\n    return {}\n",
    )


def test_syntax_retry_hint_when_import_merged_with_async_def():
    code = "import re async def run(state):\n    return {}\n"
    hint = _syntax_retry_hint(code, "Syntax error: invalid syntax (<unknown>, line 1)")
    assert "отдельной строкой" in hint
    assert "async def" in hint


def test_sandbox_codegen_args_run_variables_preserved_with_task():
    m = SandboxCodegenArgs.model_validate(
        {
            "task": "run",
            "run_variables": {"a": 1},
        },
    )
    assert m.run_variables == {"a": 1}


@pytest.mark.asyncio
async def test_sandbox_codegen_retries_after_syntax_error():
    bad = "async def run(state):\n    return {"
    good = "async def run(state):\n    return {'ok': True}"
    setup_mock_responses(
        response_queue=[
            {"type": "structured_output", "data": _mock_structured_code(bad)},
            {"type": "structured_output", "data": _mock_structured_code(good)},
        ]
    )
    state = ExecutionState.create(
        task_id="t_eval_syn_1",
        context_id="c_eval_syn_1",
        user_id="u_eval_syn_1",
        session_id="flow_eval_syn:c_eval_syn_1",
    )
    raw = await sandbox_codegen._func(
        task="Верни dict с ключом ok True",
        max_iterations=5,
        state=state,
    )
    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["result"] == {"ok": True}
    assert payload["attempts"] == 2
    validate_entries = [x for x in payload["trace"] if x.get("phase") == "validate"]
    assert validate_entries
    assert "traceback" in validate_entries[0]
    assert "\n" in validate_entries[0]["traceback"]
    assert payload["trace"][-1]["phase"] == "success"


@pytest.mark.asyncio
async def test_sandbox_codegen_ignores_extra_keys_in_llm_structured_output():
    """Провайдер может вернуть в JSON лишние поля (mode, notes) — используется только code_lines."""
    code = "async def run(state):\n    return {'ok': True}"
    setup_mock_responses(
        response_queue=[
            {
                "type": "structured_output",
                "data": {**_mock_structured_code(code), "mode": "node", "notes": "ignored"},
            },
        ],
    )
    state = ExecutionState.create(
        task_id="t_eval_syn_extra",
        context_id="c_eval_syn_extra",
        user_id="u_eval_syn_extra",
        session_id="flow_eval_syn:c_eval_syn_extra",
    )
    raw = await sandbox_codegen._func(
        task="Верни dict с ключом ok True",
        max_iterations=2,
        state=state,
    )
    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["result"] == {"ok": True}


@pytest.mark.asyncio
async def test_sandbox_codegen_run_variables_merged_into_state():
    code = (
        "async def run(state):\n"
        "    a = state.variables.get('a')\n"
        "    b = state.variables.get('b')\n"
        "    return {'sum': a + b}\n"
    )
    setup_mock_responses(
        response_queue=[
            {"type": "structured_output", "data": _mock_structured_code(code)},
        ]
    )
    state = ExecutionState.create(
        task_id="t_eval_syn_2",
        context_id="c_eval_syn_2",
        user_id="u_eval_syn_2",
        session_id="flow_eval_syn:c_eval_syn_2",
    )
    raw = await sandbox_codegen._func(
        task="Сложи a и b из state.variables",
        run_variables={"a": 3, "b": 5},
        max_iterations=3,
        state=state,
    )
    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["result"] == {"sum": 8}


@pytest.mark.asyncio
async def test_sandbox_codegen_run_variables_json_string_for_llm_caller():
    code = (
        "async def run(state):\n"
        "    a = state.variables.get('a')\n"
        "    b = state.variables.get('b')\n"
        "    return {'sum': a + b}\n"
    )
    setup_mock_responses(
        response_queue=[
            {"type": "structured_output", "data": _mock_structured_code(code)},
        ]
    )
    state = ExecutionState.create(
        task_id="t_eval_syn_str",
        context_id="c_eval_syn_str",
        user_id="u_eval_syn_str",
        session_id="flow_eval_syn:c_eval_syn_str",
    )
    raw = await sandbox_codegen.run(
        {
            "task": "Сложи a и b",
            "run_variables": '{"a": 3, "b": 5}',
            "max_iterations": 3,
        },
        state,
    )
    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["result"] == {"sum": 8}


@pytest.mark.asyncio
async def test_sandbox_codegen_tool_run_real_eval_pipeline(unique_id):
    """
    Путь LlmNodeRunner: tool.run(args, state).

    Мок только MockLLM; validate / compile / execute — реальный PythonCodeRunner.
    """
    code = (
        "async def run(state):\n"
        "    return {'ok': True, 'variables_len': len(state.variables)}\n"
    )
    setup_mock_responses(
        response_queue=[
            {"type": "structured_output", "data": _mock_structured_code(code)},
        ]
    )
    state = ExecutionState.create(
        task_id=f"t_eval_syn_run_{unique_id}",
        context_id=f"c_eval_syn_run_{unique_id}",
        user_id=f"u_eval_syn_run_{unique_id}",
        session_id=f"flow_eval_syn_run:{unique_id}",
    )
    args = {
        "task": "Верни dict ok True и число ключей variables",
        "max_iterations": 3,
    }
    raw = await sandbox_codegen.run(args, state)
    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["result"] == {"ok": True, "variables_len": 0}
    assert payload["attempts"] == 1
    assert payload["trace"][-1]["phase"] == "success"


@pytest.mark.asyncio
async def test_sandbox_codegen_sandbox_docs_omit_platform_tool_catalog():
    md = await _build_sandbox_docs_markdown()
    assert "doc-platform-tools" not in md
    assert 'docs-platform-tool-title' not in md


def test_documentation_markdown_respects_include_platform_tools_false():
    q = DocumentationQuery(
        language="python",
        perspective="tool",
        include_platform_tools=False,
        include_templates=False,
    )
    md = get_documentation_service().to_markdown(q)
    assert "doc-platform-tools" not in md
    assert 'docs-platform-tool-title' not in md


def test_sandbox_documentation_markdown_skips_module_methods_and_builtin_list():
    q = DocumentationQuery(
        language="python",
        perspective="tool",
        include_templates=False,
        markdown_expand_module_methods=False,
        markdown_expand_builtins=False,
    )
    md = get_documentation_service().to_markdown(q)
    assert "В sandbox разрешено подмножество API" in md
    assert "ограниченный whitelist встроенных имён" in md
    assert "### `json`" not in md


def test_documentation_query_includes_runtime_namespace_extras_in_markdown():
    from apps.flows.src.services.runtime_namespace_doc import (
        build_runtime_namespace_global_variables,
    )

    extras = build_runtime_namespace_global_variables()
    assert isinstance(extras, list)
    q = DocumentationQuery(
        language="python",
        perspective="tool",
        include_templates=False,
        runtime_namespace_extras=extras,
    )
    md = get_documentation_service().to_markdown(q)
    assert "Дополнительные символы sandbox" in md
    assert len(extras) == 0 or any(
        name in md for name in (extras[0].name,)
    )
