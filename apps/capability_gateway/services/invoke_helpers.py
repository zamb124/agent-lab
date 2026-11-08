"""Shared invoke helpers for text capabilities (aligned with flows builtins).

Files: ``files.create`` — ``FileWriter`` (gateway binds ``FilesService``);
``files.read`` — ``read_files_to_envelope`` → ``ReadFileEnvelope`` (тот же контракт,
что tool ``read_file``; tool резолвит ``names`` → ``file_ids`` и зовёт gateway).

Text: ``text.summarize`` / ``text.format_markdown`` call ``TextTransformService``
в gateway; tools ``summarize_text`` / ``format_text_markdown`` — тонкие адаптеры,
которые зовут эти capabilities через ``CapabilityGatewayClient``.
"""

from __future__ import annotations

from core.text_transforms import TextTransformService
from core.types import JsonObject


async def invoke_text_summarize(
    service: TextTransformService,
    *,
    text: str,
    instruction: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> JsonObject:
    summary = await service.summarize(
        text,
        instruction=instruction,
        provider=provider,
        model=model,
        max_output_tokens=max_output_tokens,
    )
    return {"summary": summary}


async def invoke_text_format_markdown(
    service: TextTransformService,
    *,
    text: str,
) -> JsonObject:
    markdown = await service.format_markdown(text)
    return {"markdown": markdown}
