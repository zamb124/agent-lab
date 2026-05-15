"""
Регистрация символов codegen в eval-namespace (путь B: exec строки = те же глобалы, что ожидает исходник `sandbox_codegen`).

Единая точка: менять состав здесь, не копипастой в `namespace.py`.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

from apps.flows.src.eval.codegen_utils import (
    CodegenStagesFailure,
    CodegenStagesSuccess,
    build_sandbox_docs_markdown,
    execution_state_for_codegen,
    run_codegen_stages,
    sandbox_feedback_hint,
    syntax_retry_hint,
)
from core.clients.llm import get_llm


def register_sandbox_codegen_namespace(namespace: Dict[str, Any]) -> None:
    platform_services = importlib.import_module("apps.flows.src.eval.platform_services")
    sandbox_codegen = importlib.import_module("apps.flows.tools.sandbox_codegen")

    namespace["execution_state_for_codegen"] = execution_state_for_codegen
    namespace["build_sandbox_docs_markdown"] = build_sandbox_docs_markdown
    namespace["get_code_runner"] = platform_services.get_code_runner
    namespace["get_llm"] = get_llm
    namespace["get_text_transform_service"] = platform_services.get_text_transform_service
    namespace["LLMGeneratedCode"] = sandbox_codegen.LLMGeneratedCode
    namespace["run_codegen_stages"] = run_codegen_stages
    namespace["CodegenStagesSuccess"] = CodegenStagesSuccess
    namespace["CodegenStagesFailure"] = CodegenStagesFailure
    namespace["sandbox_feedback_hint"] = sandbox_feedback_hint
    namespace["syntax_retry_hint"] = syntax_retry_hint
    namespace["_system_rules_block"] = sandbox_codegen._system_rules_block
