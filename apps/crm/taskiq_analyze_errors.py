"""Wire-контракт Pydantic ValidationError для TaskIQ exceptions."""

from __future__ import annotations

from pydantic import ValidationError

PREFIX = "TASKIQ_ANALYZE_VALIDATION_ERROR:"


def format_validation_for_taskiq(exc: ValidationError) -> str:
    return PREFIX + exc.json(
        include_context=False,
        include_input=False,
        include_url=False,
    )
