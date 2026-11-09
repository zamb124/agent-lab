"""E2E tool → capability_gateway для мигрированных tools.

Реальная цепочка без моков пайплайна: tool.run → CapabilityGatewayClient →
gateway handler → FilesService/S3 / TextTransformService / code_runner_python.
Единственный мок — MockLLM через Redis-очередь test scope (канон testing.mdc).
"""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from docx import Document

from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.state import ExecutionState
from apps.flows.tools.files.docx_template import fill_docx_template
from apps.flows.tools.files.files import (
    create_file,
    files_materialize_image_regions,
)
from apps.flows.tools.misc.sandbox_codegen import sandbox_codegen
from apps.flows.tools.text.format_text_markdown import format_text_markdown
from apps.flows.tools.text.summarize_text import summarize_text
from core.context import get_context, set_context
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.file_ref import stored_file_ref
from core.files.registry import default_retention_for_source
from core.models.identity_models import User
from core.types import require_json_array, require_json_object
from tests.capabilities.capability_language_helpers import interrupt_capability_code
from tests.core.files.corpus.e2e_helpers import execution_state_for_files
from tests.core.files.corpus.manifest import POSITIVE
from tests.core.files.corpus.read_helpers import store_corpus_in_files_service
from tests.fixtures.s3 import require_s3_configured

_EMBEDDED_PDF = "pdf/embedded-images.pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _bind_persisted_user(user_id: str) -> None:
    """Gateway build_context грузит User из БД; tool conftest ставит ephemeral u1."""
    context = get_context()
    if context is None:
        raise RuntimeError("test context missing")
    user = User(user_id=user_id, name="System")
    _ = set_context(
        context.model_copy(
            update={
                "user": user,
                "metadata": {**context.metadata, "user_id": user_id},
            }
        )
    )


def _empty_state(user_id: str) -> ExecutionState:
    return ExecutionState.create(
        task_id="capability_routed_task",
        context_id="ctx",
        user_id=user_id,
        session_id="capability_routed_flow:ctx",
    )


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_create_file_persists_via_gateway(
    frontend_di,
    unique_id: str,
    system_user_id: str,
) -> None:
    require_s3_configured()
    _bind_persisted_user(system_user_id)
    state = execution_state_for_files(files=[], user_id=system_user_id)
    result = require_json_object(
        await create_file.run(
            {
                "content": "hello capability",
                "original_name": f"note_{unique_id}.md",
                "content_mode": "raw",
            },
            state,
        ),
        "create_file.result",
    )
    file_id = result.get("file_id")
    assert isinstance(file_id, str) and file_id.strip()
    persisted = await frontend_di.files_service.get(file_id)
    assert persisted is not None
    assert any(
        file_ref.file_id == file_id for file_ref in state.files
    ), "state.files must gain the created FileRef"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_fill_docx_template_via_gateway(
    frontend_di,
    unique_id: str,
    system_user_id: str,
) -> None:
    require_s3_configured()
    _bind_persisted_user(system_user_id)
    buf = BytesIO()
    doc = Document()
    doc.add_paragraph("Hello {{ name }}")
    doc.save(buf)
    spec = FileCreateSpec.model_validate(
        {
            "source_kind": FileSourceKind.PLATFORM_AUXILIARY.value,
            "source_ref": FileSourceRef.model_validate({}).model_dump(),
            "retention": default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
        }
    )
    record = await frontend_di.files_service.create(
        spec,
        buf.getvalue(),
        original_name=f"tpl_{unique_id}.docx",
        content_type=_DOCX_MIME,
    )
    state = execution_state_for_files(files=[stored_file_ref(record)], user_id=system_user_id)
    result = require_json_object(
        await fill_docx_template.run(
            {
                "variables": {"name": "World"},
                "output_original_name": f"filled_{unique_id}.docx",
                "strict": False,
            },
            state,
        ),
        "fill_docx_template.result",
    )
    assert result["success"] is True
    file_id = result.get("file_id")
    assert isinstance(file_id, str) and file_id.strip()
    persisted = await frontend_di.files_service.get(file_id)
    assert persisted is not None
    assert persisted.content_type == _DOCX_MIME
    # Корректность заполнения шаблона покрыта capability-level e2e
    # (tests/capabilities/test_new_capability_handlers.py) — здесь проверяем маршрут.


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_files_materialize_image_regions_via_gateway(
    frontend_di,
    unique_id: str,
    system_user_id: str,
) -> None:
    require_s3_configured()
    _bind_persisted_user(system_user_id)
    entry = next(e for e in POSITIVE if e.relative_path == _EMBEDDED_PDF)
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    assert file_ref.file_id is not None
    state = execution_state_for_files(files=[file_ref], user_id=system_user_id)
    result = require_json_object(
        await files_materialize_image_regions.run(
            {
                "sections": [
                    {
                        "title": "menu",
                        "items": [
                            {
                                "name": "dish",
                                "photo": {
                                    "file_id": file_ref.file_id,
                                    "page": 0,
                                    "x0": 0.1,
                                    "y0": 0.1,
                                    "x1": 0.6,
                                    "y1": 0.6,
                                },
                            }
                        ],
                    }
                ],
                "attachment_file_ids": [file_ref.file_id],
            },
            state,
        ),
        "files_materialize_image_regions.result",
    )
    sections = require_json_array(result["sections"], "sections")
    items = require_json_array(
        require_json_object(sections[0], "sections[0]")["items"], "items"
    )
    photo = require_json_object(
        require_json_object(items[0], "items[0]")["photo"], "photo"
    )
    crop_file_id = photo.get("file_id")
    assert isinstance(crop_file_id, str) and crop_file_id.strip()
    assert await frontend_di.files_service.get(crop_file_id) is not None


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_summarize_text_via_gateway(
    capability_gateway_service,
    mock_llm_redis,
    system_user_id: str,
) -> None:
    _ = capability_gateway_service
    _bind_persisted_user(system_user_id)
    await mock_llm_redis([{"type": "text", "content": "Коротко о главном."}])
    state = _empty_state(system_user_id)
    result = require_json_object(
        await summarize_text.run({"text": "Длинный текст " * 50}, state),
        "summarize_text.result",
    )
    assert result["summary"] == "Коротко о главном."


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_format_text_markdown_via_gateway(
    capability_gateway_service,
    mock_llm_redis,
    system_user_id: str,
) -> None:
    _ = capability_gateway_service
    _bind_persisted_user(system_user_id)
    await mock_llm_redis([{"type": "text", "content": "# Заголовок\n\nТекст."}])
    state = _empty_state(system_user_id)
    result = require_json_object(
        await format_text_markdown.run({"text": "заголовок текст"}, state),
        "format_text_markdown.result",
    )
    assert result["markdown"] == "# Заголовок\n\nТекст."


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_sandbox_codegen_tool_via_gateway(
    capability_gateway_service,
    code_runner_python_service,
    mock_llm_redis,
    system_user_id: str,
) -> None:
    """Tool → capability sandbox.codegen → LLM → реальный code_runner_python."""
    _ = capability_gateway_service, code_runner_python_service
    _bind_persisted_user(system_user_id)
    code = 'async def run(args, state):\n    return {"echo": args["x"]}'
    await mock_llm_redis(
        [{"type": "text", "content": json.dumps({"code": code})}]
    )
    state = _empty_state(system_user_id)
    result = require_json_object(
        await sandbox_codegen.run(
            {
                "task": "echo x back",
                "language": "python",
                "entrypoint": "run",
                "run_args": {"x": 7},
                "max_iterations": 2,
            },
            state,
        ),
        "sandbox_codegen.result",
    )
    assert result["success"] is True
    assert result["result"] == {"echo": 7}
    assert result["attempts"] == 1
    assert "async def run" in str(result["final_code"])


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_sandbox_codegen_tool_merges_returned_state(
    capability_gateway_service,
    code_runner_python_service,
    mock_llm_redis,
    system_user_id: str,
) -> None:
    """state-мутации сгенерированного кода возвращаются в result.state (scratch-контракт)."""
    _ = capability_gateway_service, code_runner_python_service
    _bind_persisted_user(system_user_id)
    code = (
        'async def run(args, state):\n'
        '    state["variables"]["from_code"] = "yes"\n'
        '    return {"done": True}'
    )
    await mock_llm_redis(
        [{"type": "text", "content": json.dumps({"code": code})}]
    )
    state = _empty_state(system_user_id)
    result = require_json_object(
        await sandbox_codegen.run(
            {
                "task": "write marker into state.variables",
                "language": "python",
                "entrypoint": "run",
                "max_iterations": 2,
            },
            state,
        ),
        "sandbox_codegen.result",
    )
    assert result["success"] is True
    returned_state = require_json_object(result["state"], "sandbox_codegen.state")
    returned_variables = require_json_object(
        returned_state["variables"], "sandbox_codegen.state.variables"
    )
    assert returned_variables["from_code"] == "yes"


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_sandbox_codegen_tool_raises_flow_interrupt(
    capability_gateway_service,
    code_runner_python_service,
    mock_llm_redis,
    system_user_id: str,
) -> None:
    """Код зовёт flow.ask_user в sandbox → interrupt конверт → FlowInterrupt в туле."""
    _ = capability_gateway_service, code_runner_python_service
    _bind_persisted_user(system_user_id)
    code = interrupt_capability_code("python")
    await mock_llm_redis(
        [{"type": "text", "content": json.dumps({"code": code})}]
    )
    state = _empty_state(system_user_id)
    with pytest.raises(FlowInterrupt):
        _ = await sandbox_codegen.run(
            {
                "task": "ask the user a question",
                "language": "python",
                "entrypoint": "run",
                "max_iterations": 1,
            },
            state,
        )
