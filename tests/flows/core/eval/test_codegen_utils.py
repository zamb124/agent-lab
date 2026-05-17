"""Unit-тесты `run_codegen_stages` и границ codegen_utils без MockLLM."""

from __future__ import annotations

import pytest

from apps.flows.src.eval.codegen_utils import (
    CodegenStagesFailure,
    CodegenStagesSuccess,
    run_codegen_stages,
)
from apps.flows.src.eval.platform_services import get_code_runner
from core.state import ExecutionState


@pytest.mark.asyncio
async def test_run_codegen_stages_run_success(unique_id):
    runner = get_code_runner(language="python")
    state = ExecutionState.create(
        task_id=f"t_codegen_ok_{unique_id}",
        context_id=f"c_codegen_{unique_id}",
        user_id=f"u_codegen_{unique_id}",
        session_id=f"flow_codegen:{unique_id}",
    )
    code = "async def run(state):\n    return {'ok': True}\n"
    out = await run_codegen_stages(runner, code, state)
    assert isinstance(out, CodegenStagesSuccess)
    assert out.result == {"ok": True}


@pytest.mark.asyncio
async def test_run_codegen_stages_validate_failure(unique_id):
    runner = get_code_runner(language="python")
    state = ExecutionState.create(
        task_id=f"t_codegen_val_{unique_id}",
        context_id=f"c_codegen_v_{unique_id}",
        user_id=f"u_codegen_v_{unique_id}",
        session_id=f"flow_codegen_v:{unique_id}",
    )
    out = await run_codegen_stages(runner, "not a python {", state)
    assert isinstance(out, CodegenStagesFailure)
    assert out.phase == "validate"
    assert out.detail


@pytest.mark.asyncio
async def test_run_codegen_stages_requires_run_entrypoint(unique_id):
    runner = get_code_runner(language="python")
    state = ExecutionState.create(
        task_id=f"t_codegen_entry_{unique_id}",
        context_id=f"c_codegen_entry_{unique_id}",
        user_id=f"u_codegen_entry_{unique_id}",
        session_id=f"flow_codegen_entry:{unique_id}",
    )
    code = "async def execute(state):\n    return {'ok': True}\n"
    out = await run_codegen_stages(runner, code, state)
    assert isinstance(out, CodegenStagesFailure)
    assert out.phase == "compile"
    assert "Function 'run' not found" in out.detail
