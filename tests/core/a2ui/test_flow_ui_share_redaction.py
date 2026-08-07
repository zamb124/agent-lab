"""Server-side Flow UI share redaction (pure domain, no I/O)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.models.flow_interface import default_flow_interface_config
from core.models.flow_ui_share import FlowUIShareGrant
from core.state.flow_ui_share_redaction import (
    apply_share_redaction,
    assert_share_mutation_allowed,
    validate_share_redacted_paths,
)


def _grant(*, paths: list[str]) -> FlowUIShareGrant:
    now = datetime.now(UTC)
    return FlowUIShareGrant.model_validate(
        {
            "grant_id": "g" + ("x" * 31),
            "company_id": "system",
            "flow_id": "flow",
            "branch_id": "default",
            "context_id": "ctx",
            "document_id": "flow-ui:ctx",
            "minimum_revision": 1,
            "permission": "view",
            "redacted_value_paths": paths,
            "created_by_user_id": "owner",
            "expires_at": now,
            "created_at": now,
        }
    )


def test_validate_share_redacted_paths_rejects_foreign_namespaces() -> None:
    with pytest.raises(ValueError, match="JSON Pointer"):
        validate_share_redacted_paths(["values/secret"])
    with pytest.raises(ValueError, match="/values or /content"):
        validate_share_redacted_paths(["/system/secret"])


def test_apply_share_redaction_removes_forbidden_values_only() -> None:
    document = default_flow_interface_config().template.materialize(
        document_id="flow-ui:ctx"
    )
    document.surfaces["main"].data_model.values = {
        "message": "top-secret",
        "files": ["keep"],
    }
    redacted = apply_share_redaction(document, _grant(paths=["/values/message"]))
    assert redacted.surfaces["main"].data_model.values == {"files": ["keep"]}
    assert document.surfaces["main"].data_model.values["message"] == "top-secret"


def test_assert_share_mutation_allowed_rejects_redacted_writes() -> None:
    grant = _grant(paths=["/values/message"])
    assert_share_mutation_allowed(grant, {"main": {"files": []}})
    with pytest.raises(PermissionError, match="forbids client writes"):
        assert_share_mutation_allowed(
            grant,
            {"main": {"message": "leak", "files": []}},
        )
