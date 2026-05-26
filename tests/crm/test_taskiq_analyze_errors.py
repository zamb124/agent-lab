from __future__ import annotations

from pydantic import ValidationError

from apps.crm.taskiq_analyze_errors import PREFIX, format_validation_for_taskiq
from core.models.base import StrictBaseModel
from core.types import parse_json_array, require_json_object


class _TaskiqValidationPayload(StrictBaseModel):
    count: int


def _validation_error() -> ValidationError:
    try:
        _ = _TaskiqValidationPayload.model_validate({"count": "not-int"})
    except ValidationError as exc:
        return exc
    raise AssertionError("TaskIQ validation payload must fail")


def test_format_validation_for_taskiq_emits_strict_pydantic_error_json() -> None:
    formatted = format_validation_for_taskiq(_validation_error())

    assert formatted.startswith(PREFIX)
    errors = parse_json_array(formatted[len(PREFIX) :], "taskiq.validation_errors")
    assert len(errors) == 1

    error = require_json_object(errors[0], "taskiq.validation_errors[0]")
    assert error["type"] == "int_parsing"
    assert error["loc"] == ["count"]
    assert error["msg"] == "Input should be a valid integer, unable to parse string as an integer"
    assert "input" not in error
    assert "ctx" not in error
    assert "url" not in error
