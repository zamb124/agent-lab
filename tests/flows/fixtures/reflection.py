"""Shared builders for reflection CriticPolicy / critique payloads in tests."""

from __future__ import annotations

from core.reflection import (
    CriticCriterion,
    CriticDecision,
    CriticPolicy,
    CriticSeverity,
    ReflectionCritiqueIssue,
    ReflectionCritiqueResult,
    ReflectionGate,
    ReflectionTarget,
    ReflectionTargetKind,
)
from core.types import JsonObject


def reflection_policy(
    *,
    policy_id: str = "final-answer-safety",
    gate: ReflectionGate = "final_answer",
    target_kind: ReflectionTargetKind = "response",
    state_path: str | None = None,
    instruction: str = "Block unsafe or unsupported outputs.",
    min_confidence: float = 0.8,
    block_on_severities: list[CriticSeverity] | None = None,
    criteria: list[CriticCriterion] | None = None,
) -> CriticPolicy:
    if target_kind == "state_path":
        if state_path is None:
            raise ValueError("state_path required for target_kind=state_path")
        target = ReflectionTarget(kind="state_path", state_path=state_path)
    else:
        target = ReflectionTarget(kind=target_kind)
    return CriticPolicy(
        policy_id=policy_id,
        gate=gate,
        target=target,
        instruction=instruction,
        criteria=criteria
        or [
            CriticCriterion(
                criterion_id="safety",
                description="Must not instruct destructive actions.",
                severity="critical",
            ),
            CriticCriterion(
                criterion_id="evidence",
                description="Must be supported by visible facts.",
                severity="error",
            ),
        ],
        min_confidence=min_confidence,
        block_on_severities=block_on_severities or ["error", "critical"],
    )


def reflection_critique(
    *,
    decision: CriticDecision = "approved",
    confidence: float = 0.95,
    summary: str = "Looks safe and complete.",
    issues: list[ReflectionCritiqueIssue] | None = None,
) -> ReflectionCritiqueResult:
    return ReflectionCritiqueResult(
        decision=decision,
        confidence=confidence,
        summary=summary,
        issues=issues or [],
    )


def critique_issue(
    *,
    criterion_id: str = "safety",
    severity: CriticSeverity = "critical",
    finding: str = "Unsafe action proposed.",
    evidence: str = "Response mentions destructive production change.",
    required_action: str = "Require explicit approval.",
) -> ReflectionCritiqueIssue:
    return ReflectionCritiqueIssue(
        criterion_id=criterion_id,
        severity=severity,
        finding=finding,
        evidence=evidence,
        required_action=required_action,
    )


def reflection_node_config(
    *,
    policy: CriticPolicy | None = None,
    model: str = "mock-gpt-4",
) -> JsonObject:
    return {
        "type": "reflection",
        "llm": {"model": model, "temperature": 0.0},
        "critic_policy": (policy or reflection_policy()).model_dump(mode="json"),
    }


def mock_critique_queue_item(critique: ReflectionCritiqueResult) -> JsonObject:
    return {
        "type": "structured_output",
        "data": critique.model_dump(mode="json"),
    }
