"""Helpers for LLM structured output assembly."""


def resolve_structured_output_source_text(
    *,
    content: str,
    last_status_text: str,
    reasoning_text: str,
) -> str:
    if content.strip():
        return content
    if last_status_text.strip():
        return last_status_text
    return reasoning_text
