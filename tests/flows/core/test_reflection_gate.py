"""Pure matrix for evaluate_reflection_gate — no I/O, no mocks."""

from __future__ import annotations

import pytest

from apps.flows.src.reflection import (
    CriticCriterion,
    CriticExit,
    CriticExitWhen,
    CriticPolicy,
    ReflectionCritiqueIssue,
    ReflectionCritiqueResult,
    ReflectionTarget,
    evaluate_reflection_gate,
)
from tests.flows.fixtures.reflection import (
    critique_issue,
    reflection_critique,
    reflection_policy,
)


def _issue(criterion_id: str, severity: str) -> ReflectionCritiqueIssue:
    return critique_issue(criterion_id=criterion_id, severity=severity)


@pytest.mark.parametrize(
    ("decision", "confidence", "issues", "expected_approved", "expected_reasons"),
    [
        (
            "approved",
            0.95,
            [],
            True,
            [],
        ),
        (
            "approved",
            0.95,
            [_issue("noise", "info")],
            True,
            [],
        ),
        (
            "approved",
            0.95,
            [_issue("noise", "warning")],
            True,
            [],
        ),
        (
            "needs_revision",
            0.99,
            [],
            False,
            ["decision:needs_revision"],
        ),
        (
            "blocked",
            0.99,
            [],
            False,
            ["decision:blocked"],
        ),
        (
            "approved",
            0.5,
            [],
            False,
            ["confidence_below_minimum"],
        ),
        (
            "approved",
            0.95,
            [_issue("evidence", "error")],
            False,
            ["issue:error:evidence"],
        ),
        (
            "approved",
            0.95,
            [_issue("safety", "critical")],
            False,
            ["issue:critical:safety"],
        ),
        (
            "approved",
            0.95,
            [_issue("evidence", "error"), _issue("safety", "critical")],
            False,
            ["issue:error:evidence", "issue:critical:safety"],
        ),
        (
            "approved",
            0.4,
            [_issue("safety", "critical")],
            False,
            ["confidence_below_minimum", "issue:critical:safety"],
        ),
        (
            "needs_revision",
            0.4,
            [_issue("evidence", "error")],
            False,
            [
                "decision:needs_revision",
                "confidence_below_minimum",
                "issue:error:evidence",
            ],
        ),
    ],
)
def test_evaluate_reflection_gate_matrix(
    decision: str,
    confidence: float,
    issues: list[ReflectionCritiqueIssue],
    expected_approved: bool,
    expected_reasons: list[str],
) -> None:
    policy = reflection_policy(min_confidence=0.8, block_on_severities=["error", "critical"])
    critique = reflection_critique(
        decision=decision,
        confidence=confidence,
        summary="matrix case",
        issues=issues,
    )
    result = evaluate_reflection_gate(policy=policy, critique=critique)
    assert result.approved is expected_approved
    assert result.blocked_reasons == expected_reasons
    assert result.exit_id == ("approved" if expected_approved else "blocked")
    assert result.policy_id == policy.policy_id
    assert result.gate == policy.gate
    assert result.target == policy.target
    assert result.critique == critique


@pytest.mark.parametrize("severity", ["info", "warning", "error", "critical"])
def test_evaluate_reflection_gate_blocks_only_listed_severities(severity: str) -> None:
    policy = reflection_policy(block_on_severities=[severity])
    critique = reflection_critique(
        issues=[_issue("c1", severity)],
    )
    result = evaluate_reflection_gate(policy=policy, critique=critique)
    assert result.approved is False
    assert result.blocked_reasons == [f"issue:{severity}:c1"]

    other = "info" if severity != "info" else "warning"
    non_blocking = reflection_critique(issues=[_issue("c2", other)])
    ok = evaluate_reflection_gate(policy=policy, critique=non_blocking)
    assert ok.approved is True
    assert ok.blocked_reasons == []


@pytest.mark.parametrize("gate", ["final_answer", "transaction", "quality"])
def test_evaluate_reflection_gate_copies_gate_label(gate: str) -> None:
    policy = reflection_policy(gate=gate, policy_id=f"policy-{gate}")
    critique = reflection_critique()
    result = evaluate_reflection_gate(policy=policy, critique=critique)
    assert result.gate == gate
    assert result.policy_id == f"policy-{gate}"
    assert result.approved is True


@pytest.mark.parametrize(
    "target",
    [
        ReflectionTarget(kind="response"),
        ReflectionTarget(kind="result"),
        ReflectionTarget(kind="validation"),
        ReflectionTarget(kind="state_path", state_path="variables.draft"),
    ],
)
def test_evaluate_reflection_gate_copies_target(target: ReflectionTarget) -> None:
    policy = CriticPolicy(
        policy_id="p1",
        gate="quality",
        target=target,
        instruction="Review.",
        criteria=[
            CriticCriterion(
                criterion_id="ok",
                description="ok",
                severity="error",
            )
        ],
        min_confidence=0.5,
        block_on_severities=["error"],
    )
    result = evaluate_reflection_gate(
        policy=policy,
        critique=ReflectionCritiqueResult(
            decision="approved",
            confidence=0.9,
            summary="ok",
            issues=[],
        ),
    )
    assert result.target == target
    assert result.exit_id == "approved"


def test_select_reflection_exit_first_match_decision() -> None:
    policy = CriticPolicy(
        policy_id="p1",
        gate="quality",
        target=ReflectionTarget(kind="response"),
        instruction="Review.",
        criteria=[
            CriticCriterion(criterion_id="ok", description="ok", severity="error"),
        ],
        min_confidence=0.5,
        block_on_severities=["error"],
        exits=[
            CriticExit(
                exit_id="pass",
                label="Pass",
                when=CriticExitWhen(kind="approved_true"),
            ),
            CriticExit(
                exit_id="revise",
                label="Revise",
                when=CriticExitWhen(kind="decision_eq", decision="needs_revision"),
            ),
            CriticExit(
                exit_id="reject",
                label="Reject",
                when=CriticExitWhen(kind="always"),
            ),
        ],
    )
    revise = evaluate_reflection_gate(
        policy=policy,
        critique=ReflectionCritiqueResult(
            decision="needs_revision",
            confidence=0.9,
            summary="needs work",
            issues=[],
        ),
    )
    assert revise.approved is False
    assert revise.exit_id == "revise"

    blocked = evaluate_reflection_gate(
        policy=policy,
        critique=ReflectionCritiqueResult(
            decision="blocked",
            confidence=0.9,
            summary="hard block",
            issues=[],
        ),
    )
    assert blocked.exit_id == "reject"


def test_select_reflection_exit_reason_prefix() -> None:
    policy = CriticPolicy(
        policy_id="p1",
        gate="quality",
        target=ReflectionTarget(kind="response"),
        instruction="Review.",
        criteria=[
            CriticCriterion(criterion_id="ok", description="ok", severity="error"),
        ],
        min_confidence=0.8,
        block_on_severities=["error"],
        exits=[
            CriticExit(
                exit_id="low_conf",
                label="Low confidence",
                when=CriticExitWhen(
                    kind="blocked_reason_prefix",
                    reason_prefix="confidence_below_minimum",
                ),
            ),
            CriticExit(
                exit_id="other",
                label="Other",
                when=CriticExitWhen(kind="always"),
            ),
        ],
    )
    result = evaluate_reflection_gate(
        policy=policy,
        critique=ReflectionCritiqueResult(
            decision="approved",
            confidence=0.2,
            summary="unsure",
            issues=[],
        ),
    )
    assert result.exit_id == "low_conf"


def test_select_reflection_exit_no_match_raises() -> None:
    policy = CriticPolicy(
        policy_id="p1",
        gate="quality",
        target=ReflectionTarget(kind="response"),
        instruction="Review.",
        criteria=[
            CriticCriterion(criterion_id="ok", description="ok", severity="error"),
        ],
        min_confidence=0.5,
        block_on_severities=["error"],
        exits=[
            CriticExit(
                exit_id="pass",
                label="Pass",
                when=CriticExitWhen(kind="approved_true"),
            ),
        ],
    )
    with pytest.raises(ValueError, match="no reflection exit matched"):
        evaluate_reflection_gate(
            policy=policy,
            critique=ReflectionCritiqueResult(
                decision="blocked",
                confidence=0.9,
                summary="blocked",
                issues=[],
            ),
        )
