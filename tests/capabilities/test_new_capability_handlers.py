"""Новые capabilities: files.materialize_image_regions, files.fill_docx_template, sandbox.codegen.

Manifest parity + валидация handler'ов + e2e через реальный FilesService/S3.
"""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from docx import Document
from pydantic import ValidationError

from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.types import JsonObject, JsonValue, require_json_array, require_json_object
from tests.core.files.corpus.manifest import POSITIVE
from tests.core.files.corpus.read_helpers import store_corpus_in_files_service
from tests.fixtures.s3 import require_s3_configured

_EMBEDDED_PDF = "pdf/embedded-images.pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _signed_context(
    *,
    user_id: str,
    allowed_capabilities: list[str] | None = None,
) -> CapabilityExecutionContext:
    allowed = allowed_capabilities if allowed_capabilities is not None else []
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id=user_id,
        flow_id="capability_handlers_flow",
        branch_id="main",
        session_id="capability_handlers_flow:ctx",
        task_id="capability-handlers-task",
        context_id="ctx",
        channel="a2a",
        allowed_capabilities=allowed,
        exp=execution_token_exp(300),
    )
    return CapabilityExecutionContext(
        execution_token=issue_execution_token(claims),
        company_id=claims.company_id,
        user_id=claims.user_id,
        flow_id=claims.flow_id,
        branch_id=claims.branch_id,
        session_id=claims.session_id,
        task_id=claims.task_id,
        context_id=claims.context_id,
        channel=claims.channel,
    )


def _request(
    name: str,
    kwargs: JsonObject,
    *,
    user_id: str,
    allowed_capabilities: list[str] | None = None,
    args: list[JsonValue] | None = None,
) -> CapabilityCallRequest:
    return CapabilityCallRequest(
        context=_signed_context(
            user_id=user_id, allowed_capabilities=allowed_capabilities
        ),
        name=name,
        kwargs=kwargs,
        args=args or [],
    )


@pytest.mark.asyncio
async def test_manifest_exposes_new_capabilities(
    capability_gateway_di,
) -> None:
    manifest = await capability_gateway_di.capability_registry.manifest()
    by_name = {capability.name: capability for capability in manifest.capabilities}
    for name, namespace, method in (
        ("files.materialize_image_regions", "files", "materialize_image_regions"),
        ("files.fill_docx_template", "files", "fill_docx_template"),
        ("images.generate", "images", "generate"),
        ("images.edit", "images", "edit"),
        ("sandbox.codegen", "sandbox", "codegen"),
    ):
        assert name in by_name, name
        assert by_name[name].sdk_namespace == namespace
        assert by_name[name].sdk_method == method


@pytest.mark.asyncio
async def test_files_materialize_image_regions_rejects_non_array_sections(
    capability_gateway_di,
    system_user_id: str,
) -> None:
    with pytest.raises(TypeError, match="sections"):
        _ = await capability_gateway_di.capability_registry.call(
            _request(
                "files.materialize_image_regions",
                {"sections": "oops"},
                user_id=system_user_id,
            )
        )


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_files_materialize_image_regions_crops_pdf_page(
    capability_gateway_di,
    frontend_di,
    system_user_id: str,
    unique_id: str,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == _EMBEDDED_PDF)
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    assert file_ref.file_id is not None

    response = await capability_gateway_di.capability_registry.call(
        _request(
            "files.materialize_image_regions",
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
                                    "x1": 0.8,
                                    "y1": 0.6,
                                },
                            }
                        ],
                    }
                ],
                "attachment_file_ids": [file_ref.file_id],
            },
            user_id=system_user_id,
        )
    )
    assert response.status == "ok"
    body = require_json_object(response.result, "materialize.result")
    sections = require_json_array(body["sections"], "sections")
    items = require_json_array(
        require_json_object(sections[0], "sections[0]")["items"], "items"
    )
    photo = require_json_object(
        require_json_object(items[0], "items[0]")["photo"], "photo"
    )
    crop_file_id = photo.get("file_id")
    assert isinstance(crop_file_id, str) and crop_file_id.strip()


@pytest.mark.asyncio
async def test_images_generate_rejects_missing_prompt(
    capability_gateway_di,
    system_user_id: str,
) -> None:
    with pytest.raises(Exception, match="prompt"):
        _ = await capability_gateway_di.capability_registry.call(
            _request("images.generate", {}, user_id=system_user_id)
        )


@pytest.mark.asyncio
async def test_images_edit_rejects_empty_references(
    capability_gateway_di,
    system_user_id: str,
) -> None:
    with pytest.raises(TypeError, match="references"):
        _ = await capability_gateway_di.capability_registry.call(
            _request(
                "images.edit",
                {"prompt": "crop it", "references": []},
                user_id=system_user_id,
            )
        )


@pytest.mark.asyncio
async def test_images_edit_rejects_reference_without_file_id(
    capability_gateway_di,
    system_user_id: str,
) -> None:
    with pytest.raises(ValidationError, match="file_id"):
        _ = await capability_gateway_di.capability_registry.call(
            _request(
                "images.edit",
                {"prompt": "crop it", "references": [{"page": 0}]},
                user_id=system_user_id,
            )
        )


@pytest.mark.asyncio
async def test_files_fill_docx_template_rejects_missing_file_id(
    capability_gateway_di,
    system_user_id: str,
) -> None:
    with pytest.raises(Exception, match="file_id"):
        _ = await capability_gateway_di.capability_registry.call(
            _request(
                "files.fill_docx_template",
                {"variables": {}, "output_original_name": "out.docx"},
                user_id=system_user_id,
            )
        )


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_files_fill_docx_template_e2e(
    capability_gateway_di,
    frontend_di,
    system_user_id: str,
    unique_id: str,
) -> None:
    require_s3_configured()
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

    response = await capability_gateway_di.capability_registry.call(
        _request(
            "files.fill_docx_template",
            {
                "file_id": record.file_id,
                "variables": {"name": "World"},
                "output_original_name": f"filled_{unique_id}.docx",
                "strict": False,
            },
            user_id=system_user_id,
        )
    )
    assert response.status == "ok"
    file_item = require_json_object(response.result, "fill_docx.result")
    assert file_item["file_id"]
    assert file_item["original_name"] == f"filled_{unique_id}.docx"
    assert file_item["content_type"] == _DOCX_MIME


@pytest.mark.asyncio
async def test_sandbox_codegen_rejects_positional_args(
    capability_gateway_di,
    system_user_id: str,
) -> None:
    with pytest.raises(ValueError, match="keyword arguments only"):
        _ = await capability_gateway_di.capability_registry.call(
            _request(
                "sandbox.codegen",
                {},
                user_id=system_user_id,
                args=["task"],
            )
        )


@pytest.mark.asyncio
async def test_sandbox_codegen_validates_kwargs(
    capability_gateway_di,
    system_user_id: str,
) -> None:
    with pytest.raises(ValidationError):
        _ = await capability_gateway_di.capability_registry.call(
            _request(
                "sandbox.codegen",
                {
                    "task": "print hi",
                    "language": "python",
                    "state": {},
                    "wall_time_limit_seconds": 30,
                    "max_iterations": 0,
                },
                user_id=system_user_id,
            )
        )


@pytest.mark.asyncio
async def test_sandbox_codegen_denied_by_allowed_capabilities(
    capability_gateway_di,
    system_user_id: str,
) -> None:
    with pytest.raises(Exception, match="sandbox.codegen|not allowed|capabilit"):
        _ = await capability_gateway_di.capability_registry.call(
            _request(
                "sandbox.codegen",
                {
                    "task": "print hi",
                    "language": "python",
                    "state": {},
                    "wall_time_limit_seconds": 30,
                },
                user_id=system_user_id,
                allowed_capabilities=["files.read"],
            )
        )


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_sandbox_codegen_executes_generated_python_in_runner(
    capability_gateway_di,
    code_runner_python_service,
    mock_llm_redis,
    system_user_id: str,
) -> None:
    """Полный цикл: LLM генерирует код → реальный code_runner_python исполняет."""
    _ = code_runner_python_service
    code = 'async def run(args, state):\n    return {"echo": args["x"]}'
    await mock_llm_redis(
        [{"type": "text", "content": json.dumps({"code": code})}]
    )
    response = await capability_gateway_di.capability_registry.call(
        _request(
            "sandbox.codegen",
            {
                "task": "echo x back",
                "language": "python",
                "entrypoint": "run",
                "run_args": {"x": 41},
                "max_iterations": 2,
                "state": {},
                "wall_time_limit_seconds": 30,
            },
            user_id=system_user_id,
        )
    )
    assert response.status == "ok"
    body = require_json_object(response.result, "codegen.result")
    assert body["success"] is True
    assert body["result"] == {"echo": 41}
    assert body["attempts"] == 1
    assert "async def run" in str(body["final_code"])


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_sandbox_codegen_retries_on_runner_failure(
    capability_gateway_di,
    code_runner_python_service,
    mock_llm_redis,
    system_user_id: str,
) -> None:
    """Первая генерация падает в runner'е → feedback → вторая генерация успешна."""
    _ = code_runner_python_service
    bad_code = 'async def run(args, state):\n    raise RuntimeError("boom")'
    good_code = 'async def run(args, state):\n    return {"ok": True}'
    await mock_llm_redis(
        [
            {"type": "text", "content": json.dumps({"code": bad_code})},
            {"type": "text", "content": json.dumps({"code": good_code})},
        ]
    )
    response = await capability_gateway_di.capability_registry.call(
        _request(
            "sandbox.codegen",
            {
                "task": "return ok flag",
                "language": "python",
                "entrypoint": "run",
                "run_args": {},
                "max_iterations": 3,
                "state": {},
                "wall_time_limit_seconds": 30,
            },
            user_id=system_user_id,
        )
    )
    assert response.status == "ok"
    body = require_json_object(response.result, "codegen.result")
    assert body["success"] is True
    assert body["result"] == {"ok": True}
    assert body["attempts"] == 2
    trace = require_json_array(body["trace"], "codegen.trace")
    assert len(trace) == 2
    first = require_json_object(trace[0], "trace[0]")
    assert first["phase"] == "execute"
    assert "boom" in str(first["error"])


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    "language,entrypoint,code",
    [
        (
            "javascript",
            "run",
            "async function run(args, state) {\n  return {echo: args.x};\n}",
        ),
        (
            "typescript",
            "run",
            "async function run(args: any, state: any): Promise<any> {\n  return {echo: args.x};\n}",
        ),
        (
            "go",
            "Run",
            "package main\n\nfunc Run(args map[string]any, state map[string]any) (any, error) {\n    return map[string]any{\"echo\": args[\"x\"]}, nil\n}",
        ),
        (
            "csharp",
            "Run",
            "using System.Collections.Generic;\nusing System.Threading.Tasks;\n\nasync Task<object?> Run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n{\n    return new Dictionary<string, object?> { [\"echo\"] = args[\"x\"] };\n}",
        ),
    ],
)
async def test_sandbox_codegen_executes_generated_code_per_language(
    capability_gateway_di,
    sandbox_services,
    mock_llm_redis,
    system_user_id: str,
    language: str,
    entrypoint: str,
    code: str,
) -> None:
    """sandbox.codegen по каждому языку: LLM → реальный code-runner-<lang>."""
    _ = sandbox_services
    await mock_llm_redis(
        [{"type": "text", "content": json.dumps({"code": code})}]
    )
    response = await capability_gateway_di.capability_registry.call(
        _request(
            "sandbox.codegen",
            {
                "task": "echo x back",
                "language": language,
                "entrypoint": entrypoint,
                "run_args": {"x": 5},
                "max_iterations": 1,
                "state": {},
                "wall_time_limit_seconds": 60,
            },
            user_id=system_user_id,
        )
    )
    assert response.status == "ok"
    body = require_json_object(response.result, "codegen.result")
    assert body["success"] is True
    assert body["attempts"] == 1
    result_obj = require_json_object(body["result"], "codegen.result.result")
    assert result_obj["echo"] == 5


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_sandbox_codegen_fails_after_max_iterations(
    capability_gateway_di,
    code_runner_python_service,
    mock_llm_redis,
    system_user_id: str,
) -> None:
    """Все итерации неуспешны → capability завершается ошибкой."""
    _ = code_runner_python_service
    bad_code = 'async def run(args, state):\n    raise RuntimeError("always fails")'
    await mock_llm_redis(
        [{"type": "text", "content": json.dumps({"code": bad_code})}]
    )
    with pytest.raises(Exception, match="max_iterations|sandbox.codegen|failed"):
        _ = await capability_gateway_di.capability_registry.call(
            _request(
                "sandbox.codegen",
                {
                    "task": "never succeed",
                    "language": "python",
                    "entrypoint": "run",
                    "max_iterations": 1,
                    "state": {},
                    "wall_time_limit_seconds": 30,
                },
                user_id=system_user_id,
            )
        )
