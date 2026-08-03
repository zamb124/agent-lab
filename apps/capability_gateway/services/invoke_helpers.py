"""Shared invoke helpers for files/text capabilities (aligned with flows builtins).

Files: ``files.create`` / ``files.read`` and tools ``create_file`` / ``read_file``
both use ``FileWriter`` / ``FileReader`` (process-configured upload for tools;
gateway binds FilesService for sandbox). No separate typed client — the writer/reader
stack is the shared surface.

Text: ``text.summarize`` / ``text.format_markdown`` and tools ``summarize_text`` /
``format_text_markdown`` both call ``TextTransformService`` (tools via
``TextClient``).
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
