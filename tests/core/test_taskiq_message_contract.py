from __future__ import annotations

import pytest
from taskiq import TaskiqMessage, TaskiqResult
from taskiq.labels import LabelType

from core.tasks.logging_middleware import LoggingMiddleware
from core.tasks.message_contract import (
    set_task_message_string_label,
    set_task_message_string_labels,
    task_message_int_label,
    task_message_string_labels,
)
from core.types import JsonValue

_BOOL_LABEL = int(LabelType.BOOL.value)
_INT_LABEL = int(LabelType.INT.value)
_STR_LABEL = int(LabelType.STR.value)


def test_platform_labels_are_separate_from_taskiq_internal_labels() -> None:
    message = TaskiqMessage(
        task_id="task-1",
        task_name="sample",
        labels={
            "request_id": "req-1",
            "trace_id": "trace-1",
            "retry_on_error": True,
            "max_retries": 3,
        },
        labels_types={
            "request_id": _STR_LABEL,
            "trace_id": _STR_LABEL,
            "retry_on_error": _BOOL_LABEL,
            "max_retries": _INT_LABEL,
        },
        args=[],
        kwargs={},
    )

    labels = task_message_string_labels(message, keys={"request_id", "trace_id"})

    assert labels == {"request_id": "req-1", "trace_id": "trace-1"}
    assert message.labels["retry_on_error"] is True
    assert message.labels["max_retries"] == 3
    assert task_message_int_label(message, "max_retries") == 3


def test_platform_label_reader_rejects_non_string_platform_label() -> None:
    message = TaskiqMessage(
        task_id="task-1",
        task_name="sample",
        labels={"request_id": 123},
        labels_types={"request_id": _INT_LABEL},
        args=[],
        kwargs={},
    )

    with pytest.raises(ValueError, match="Платформенная TaskIQ-метка 'request_id' должна быть строкой"):
        task_message_string_labels(message, keys={"request_id"})


def test_writing_platform_labels_preserves_taskiq_internal_labels() -> None:
    message = TaskiqMessage(
        task_id="task-1",
        task_name="sample",
        labels={
            "retry_on_error": True,
            "max_retries": 3,
        },
        labels_types={
            "retry_on_error": _BOOL_LABEL,
            "max_retries": _INT_LABEL,
        },
        args=[],
        kwargs={},
    )

    set_task_message_string_label(message, "request_id", "req-1")
    set_task_message_string_labels(
        message,
        {
            "trace_id": "trace-1",
            "service_name": "crm",
        },
    )

    assert message.labels == {
        "retry_on_error": True,
        "max_retries": 3,
        "request_id": "req-1",
        "trace_id": "trace-1",
        "service_name": "crm",
    }
    assert message.labels_types == {
        "retry_on_error": _BOOL_LABEL,
        "max_retries": _INT_LABEL,
        "request_id": _STR_LABEL,
        "trace_id": _STR_LABEL,
        "service_name": _STR_LABEL,
    }


@pytest.mark.asyncio
async def test_logging_middleware_keeps_taskiq_retry_labels_typed() -> None:
    message = TaskiqMessage(
        task_id="task-1",
        task_name="sample",
        labels={
            "request_id": "req-1",
            "trace_id": "trace-1",
            "service_name": "crm",
            "retry_on_error": True,
            "max_retries": 3,
        },
        labels_types={
            "request_id": _STR_LABEL,
            "trace_id": _STR_LABEL,
            "service_name": _STR_LABEL,
            "retry_on_error": _BOOL_LABEL,
            "max_retries": _INT_LABEL,
        },
        args=[],
        kwargs={},
    )
    middleware = LoggingMiddleware(queue_name="crm", service_name="crm")

    processed_message = await middleware.pre_execute(message)

    assert processed_message is message
    assert message.labels["retry_on_error"] is True
    assert message.labels["max_retries"] == 3
    assert message.labels_types is not None
    assert message.labels_types["retry_on_error"] == _BOOL_LABEL
    assert message.labels_types["max_retries"] == _INT_LABEL

    await middleware.post_execute(
        message,
        TaskiqResult[JsonValue](
            is_err=False,
            return_value=None,
            execution_time=0.0,
            labels=message.labels,
        ),
    )
