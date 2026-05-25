"""Typed reflection and critic contracts for agent test-time compute."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from core.models import StrictBaseModel
from core.types import JsonValue

CriticSeverity = Literal["info", "warning", "error", "critical"]
CriticDecision = Literal["approved", "needs_revision", "blocked"]
ReflectionGate = Literal["final_answer", "transaction", "quality"]
ReflectionTargetKind = Literal["response", "result", "validation", "state_path"]


class ReflectionTarget(StrictBaseModel):
    """State projection slice reviewed by a critic."""

    kind: ReflectionTargetKind
    state_path: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def state_path_matches_kind(self) -> "ReflectionTarget":
        if self.kind == "state_path" and self.state_path is None:
            raise ValueError("reflection target state_path is required for kind='state_path'")
        if self.kind != "state_path" and self.state_path is not None:
            raise ValueError("reflection target state_path is only allowed for kind='state_path'")
        return self


class CriticCriterion(StrictBaseModel):
    """One explicit criterion the critic must evaluate."""

    criterion_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    severity: CriticSeverity


class CriticPolicy(StrictBaseModel):
    """Strict policy controlling when reflection approves or blocks a gate."""

    policy_id: str = Field(..., min_length=1)
    gate: ReflectionGate
    target: ReflectionTarget
    instruction: str = Field(..., min_length=1)
    criteria: list[CriticCriterion] = Field(..., min_length=1)
    min_confidence: float = Field(..., ge=0.0, le=1.0)
    block_on_severities: list[CriticSeverity] = Field(..., min_length=1)

    @model_validator(mode="after")
    def ids_and_blockers_must_be_unique(self) -> "CriticPolicy":
        criterion_ids = [criterion.criterion_id for criterion in self.criteria]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise ValueError("critic criteria criterion_id values must be unique")
        if len(set(self.block_on_severities)) != len(self.block_on_severities):
            raise ValueError("critic block_on_severities values must be unique")
        return self


class ReflectionTargetSnapshot(StrictBaseModel):
    """Resolved review target captured in durable activity input."""

    target: ReflectionTarget
    value: JsonValue


class ReflectionCritiqueIssue(StrictBaseModel):
    """One concrete issue found by the critic."""

    criterion_id: str = Field(..., min_length=1)
    severity: CriticSeverity
    finding: str = Field(..., min_length=1)
    evidence: str = Field(..., min_length=1)
    required_action: str = Field(..., min_length=1)


class ReflectionCritiqueResult(StrictBaseModel):
    """Structured critic output returned by the model."""

    decision: CriticDecision
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str = Field(..., min_length=1)
    issues: list[ReflectionCritiqueIssue] = Field(default_factory=list)


class ReflectionGateResult(StrictBaseModel):
    """Deterministic gate result applied to workflow state."""

    policy_id: str = Field(..., min_length=1)
    gate: ReflectionGate
    target: ReflectionTarget
    approved: bool
    blocked_reasons: list[str]
    critique: ReflectionCritiqueResult


class ReflectionRecord(StrictBaseModel):
    """State history record for a completed reflection gate."""

    node_id: str = Field(..., min_length=1)
    execution_branch_id: str = Field(..., min_length=1)
    node_schedule_sequence: int = Field(..., ge=0)
    result: ReflectionGateResult


def evaluate_reflection_gate(
    *,
    policy: CriticPolicy,
    critique: ReflectionCritiqueResult,
) -> ReflectionGateResult:
    """Apply deterministic gate rules to a structured critic result."""
    blocked_reasons: list[str] = []
    if critique.decision != "approved":
        blocked_reasons.append(f"decision:{critique.decision}")
    if critique.confidence < policy.min_confidence:
        blocked_reasons.append("confidence_below_minimum")

    blocked_severities = set(policy.block_on_severities)
    for issue in critique.issues:
        if issue.severity in blocked_severities:
            blocked_reasons.append(f"issue:{issue.severity}:{issue.criterion_id}")

    return ReflectionGateResult(
        policy_id=policy.policy_id,
        gate=policy.gate,
        target=policy.target,
        approved=not blocked_reasons,
        blocked_reasons=blocked_reasons,
        critique=critique,
    )


__all__ = [
    "CriticCriterion",
    "CriticDecision",
    "CriticPolicy",
    "CriticSeverity",
    "ReflectionCritiqueIssue",
    "ReflectionCritiqueResult",
    "ReflectionGate",
    "ReflectionGateResult",
    "ReflectionRecord",
    "ReflectionTarget",
    "ReflectionTargetKind",
    "ReflectionTargetSnapshot",
    "evaluate_reflection_gate",
]
