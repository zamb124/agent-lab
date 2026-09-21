"""Roundtrip tests for tool contract models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.flows.src.models.tool_contracts import (
    ToolDefinition,
    ToolErrorBody,
    ToolGrantClaims,
    ToolResultEnvelope,
    ToolRevision,
)
from core.types import JsonObject


def _sample_definition() -> ToolDefinition:
    input_schema: JsonObject = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"entity_id": {"type": "string"}},
        "required": ["entity_id"],
    }
    output_schema: JsonObject = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"entity_id": {"type": "string"}},
        "required": ["entity_id"],
    }
    return ToolDefinition(
        definition_id="crm.note.create",
        version=1,
        machine_name="crm_create_note",
        title="Create CRM note",
        description="Creates one note on an entity.",
        canonical_input_schema=input_schema,
        canonical_output_schema=output_schema,
        argument_sources={"entity_id": "model", "text": "model"},
        effects=["create"],
        required_scopes=["crm.notes:create"],
        confirmation_floor="preview",
        idempotency="required",
        executor_kind="trusted_builtin",
        limits={"wall_time_ms": 5000},
        provenance={"owner": "platform"},
    )


def test_tool_definition_roundtrip() -> None:
    definition = _sample_definition()
    restored = ToolDefinition.model_validate(definition.model_dump(mode="json"))
    assert restored == definition


def test_tool_revision_roundtrip() -> None:
    revision = ToolRevision(
        revision_id="rev-1",
        definition_id="crm.note.create",
        definition_version=1,
        executor_kind="sandbox_code",
        source_hash="abc123",
        metadata={"language": "python"},
    )
    restored = ToolRevision.model_validate(revision.model_dump(mode="json"))
    assert restored == revision


def test_tool_grant_claims_roundtrip() -> None:
    claims = ToolGrantClaims(
        iss="platform",
        aud="capability-gateway",
        jti="grant-1",
        iat=1,
        nbf=1,
        exp=100,
        actor_id="user-1",
        company_id="company-1",
        flow_id="support",
        branch_id="main",
        source_node_id="support_agent",
        tool_call_id="call-1",
        definition_id="crm.note.create",
        definition_version=1,
        binding_id="support.add_note",
        allowed_capabilities=[{"operation": "crm.notes:create"}],
        max_calls=1,
        approval_id="approval-1",
        approved_argument_hash="hash-1",
    )
    restored = ToolGrantClaims.model_validate(claims.model_dump(mode="json"))
    assert restored == claims


def test_tool_result_envelope_ok_and_error() -> None:
    ok = ToolResultEnvelope(ok=True, data={"note_id": "n-1"})
    assert ok.error is None

    error = ToolErrorBody(code="not_found", message="missing", retryable=False)
    failed = ToolResultEnvelope(ok=False, error=error)
    assert failed.data is None


def test_tool_result_envelope_rejects_invalid_shape() -> None:
    with pytest.raises(ValidationError):
        _ = ToolResultEnvelope(ok=True, error=ToolErrorBody(code="x", message="y", retryable=False))
    with pytest.raises(ValidationError):
        _ = ToolResultEnvelope(ok=False)
