"""Zero-fallback red-tests для каждой операции.

Параметризованный smoke-pack:
  - missing required field → `WsCommandError("ws_invalid_payload", ...)`.
  - no company context → `WsCommandError("ws_no_company", ...)`.

`not_found` сценарии живут в специализированных `test_op_*.py` (требуют
конкретного payload-наполнения для каждой op).
"""

from __future__ import annotations

import pytest

from apps.sync.container import SyncContainer
from apps.sync.realtime.command_router import SYNC_OPERATIONS
from apps.sync.realtime.operations import parse_payload, resolve_company_id
from core.models.identity_models import User
from core.websocket import WsCommandError

# Операции, у которых ВСЕ поля Pydantic-payload — опциональные с дефолтами.
# Они не могут «упасть» на `ws_invalid_payload` при пустом dict.
_NO_REQUIRED_FIELDS_OPS: set[str] = {
    "sync/spaces/list_requested",
    "sync/channels/list_requested",
    "sync/calls/turn_credentials_requested",
    "sync/company_members/list_requested",
    "sync/platform_namespaces/list_requested",
}


@pytest.mark.parametrize("canonical_type", sorted(SYNC_OPERATIONS.keys()))
def test_op_missing_required_field_raises_ws_invalid_payload(
    canonical_type: str,
) -> None:
    """Пустой payload {} → ValidationError у Pydantic → WsCommandError("ws_invalid_payload")."""
    if canonical_type in _NO_REQUIRED_FIELDS_OPS:
        pytest.skip(
            f"{canonical_type}: все поля Pydantic-payload опциональны (list-операция)."
        )
    op = SYNC_OPERATIONS[canonical_type]
    with pytest.raises(WsCommandError) as exc_info:
        parse_payload(op.payload_model, {})
    assert exc_info.value.code == "ws_invalid_payload", (
        f"{canonical_type}: ожидался ws_invalid_payload, получено {exc_info.value.code}"
    )


def test_resolve_company_id_no_context_raises_ws_no_company() -> None:
    """resolve_company_id без active_company → WsCommandError("ws_no_company")."""
    user = User(user_id="u_test", name="U", active_company_id="")
    # set_context не вызывается → context = None.
    from core.context import clear_context

    clear_context()
    with pytest.raises(WsCommandError) as exc_info:
        resolve_company_id(user)
    assert exc_info.value.code == "ws_no_company"
