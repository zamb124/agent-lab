"""Zero-fallback red-tests для каждой операции.

Параметризованный smoke-pack:
  - missing required field → `WsCommandError("ws_invalid_payload", ...)`.
  - no company context → `WsCommandError("forbidden", ...)`.

`not_found` сценарии живут в специализированных `test_op_*.py` (требуют
конкретного payload-наполнения для каждой op).
"""

from __future__ import annotations

import pytest

from apps.sync.realtime.command_router import SYNC_OPERATIONS
from core.context import clear_context
from core.request_scope import require_company
from core.websocket import WsCommandError, validate_ws_payload

# Операции, у которых ВСЕ поля Pydantic-payload — опциональные с дефолтами.
# Контракт «пустой payload → ws_invalid_payload» к ним неприменим: пустой
# dict валиден, ValidationError не поднимается. Исключаем из параметризации,
# а не пропускаем через skip.
_NO_REQUIRED_FIELDS_OPS: frozenset[str] = frozenset(
    {
        "sync/channels/list_requested",
        "sync/calls/turn_credentials_requested",
        "sync/company_members/list_requested",
        "sync/namespaces/list_requested",
    }
)


_OPS_WITH_REQUIRED_FIELDS: list[str] = sorted(
    op for op in SYNC_OPERATIONS.keys() if op not in _NO_REQUIRED_FIELDS_OPS
)


@pytest.mark.parametrize("canonical_type", _OPS_WITH_REQUIRED_FIELDS)
def test_op_missing_required_field_raises_ws_invalid_payload(
    canonical_type: str,
) -> None:
    """Пустой payload {} → ValidationError у Pydantic → WsCommandError("ws_invalid_payload")."""
    op = SYNC_OPERATIONS[canonical_type]
    with pytest.raises(WsCommandError) as exc_info:
        validate_ws_payload(op.payload_model, {})
    assert exc_info.value.code == "ws_invalid_payload", (
        f"{canonical_type}: ожидался ws_invalid_payload, получено {exc_info.value.code}"
    )


def test_require_company_no_context_raises_forbidden() -> None:
    """require_company без active_company → WsCommandError("forbidden")."""
    clear_context()
    with pytest.raises(WsCommandError) as exc_info:
        require_company()
    assert exc_info.value.code == "forbidden"
