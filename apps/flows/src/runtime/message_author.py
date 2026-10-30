"""Typed author provenance for messages rendered by the shared platform chat."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonObject

if TYPE_CHECKING:
    from apps.flows.src.state import ExecutionState


class FlowMessageAuthorKind(StrEnum):
    AGENT = "agent"
    SUBAGENT = "subagent"


class FlowMessageAuthor(StrictBaseModel):
    kind: FlowMessageAuthorKind
    flow_id: str = Field(..., min_length=1)
    node_id: str | None = Field(default=None, min_length=1)
    name: str = ""


def build_flow_message_author(
    state: "ExecutionState",
    *,
    node_id: str | None = None,
) -> JsonObject:
    """Build the canonical author metadata shared by durable messages and SSE artifacts."""
    author = FlowMessageAuthor(
        kind=(
            FlowMessageAuthorKind.SUBAGENT
            if state.handoff_depth > 0
            else FlowMessageAuthorKind.AGENT
        ),
        flow_id=state.session_flow_id,
        node_id=node_id,
    )
    return author.model_dump(mode="json", exclude_none=True)


__all__ = [
    "FlowMessageAuthor",
    "FlowMessageAuthorKind",
    "build_flow_message_author",
]
