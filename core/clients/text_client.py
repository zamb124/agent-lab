"""TextClient — summarize / format_markdown over TextTransformService."""

from __future__ import annotations

from core.text_transforms import TextTransformService


class TextClient:
    """Платформенные text transforms для summarize_text / format_text_markdown."""

    _service: TextTransformService

    def __init__(self, service: TextTransformService | None = None) -> None:
        self._service = service if service is not None else TextTransformService()

    async def summarize(
        self,
        text: str,
        *,
        max_output_tokens: int | None = None,
        instruction: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> str:
        return await self._service.summarize(
            text,
            max_output_tokens=max_output_tokens,
            instruction=instruction,
            provider=provider,
            model=model,
        )

    async def format_markdown(self, text: str) -> str:
        return await self._service.format_markdown(text)
