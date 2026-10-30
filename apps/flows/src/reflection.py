"""Типизированные контракты рефлексии и критика для test-time compute агента."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from core.models import StrictBaseModel
from core.types import JsonValue

CriticSeverity = Literal["info", "warning", "error", "critical"]
CriticDecision = Literal["approved", "needs_revision", "blocked"]
ReflectionGate = Literal["final_answer", "transaction", "quality"]
ReflectionTargetKind = Literal["response", "result", "validation", "state_path"]
ReflectionExitWhenKind = Literal[
    "approved_true",
    "approved_false",
    "decision_eq",
    "blocked_reason_prefix",
    "always",
]


class ReflectionTarget(StrictBaseModel):
    """Срез проекции state, который проверяет критик."""

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
    """Один явный критерий, который критик обязан оценить."""

    criterion_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    severity: CriticSeverity


class CriticExitWhen(StrictBaseModel):
    """Детерминированный предикат выбора выхода по ReflectionGateResult."""

    kind: ReflectionExitWhenKind
    decision: CriticDecision | None = Field(default=None)
    reason_prefix: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def fields_match_kind(self) -> "CriticExitWhen":
        if self.kind == "decision_eq":
            if self.decision is None:
                raise ValueError("CriticExitWhen.decision is required for kind='decision_eq'")
            if self.reason_prefix is not None:
                raise ValueError("CriticExitWhen.reason_prefix is only allowed for kind='blocked_reason_prefix'")
            return self
        if self.kind == "blocked_reason_prefix":
            if self.reason_prefix is None:
                raise ValueError(
                    "CriticExitWhen.reason_prefix is required for kind='blocked_reason_prefix'"
                )
            if self.decision is not None:
                raise ValueError("CriticExitWhen.decision is only allowed for kind='decision_eq'")
            return self
        if self.decision is not None:
            raise ValueError("CriticExitWhen.decision is only allowed for kind='decision_eq'")
        if self.reason_prefix is not None:
            raise ValueError(
                "CriticExitWhen.reason_prefix is only allowed for kind='blocked_reason_prefix'"
            )
        return self


class CriticExit(StrictBaseModel):
    """Именованный выход reflection-ноды (canvas from_port + gate exit_id)."""

    exit_id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    when: CriticExitWhen


def default_pass_fail_exits() -> list[CriticExit]:
    """Два классических выхода: approved / blocked."""
    return [
        CriticExit(
            exit_id="approved",
            label="Approved",
            when=CriticExitWhen(kind="approved_true"),
        ),
        CriticExit(
            exit_id="blocked",
            label="Blocked",
            when=CriticExitWhen(kind="approved_false"),
        ),
    ]


class CriticPolicy(StrictBaseModel):
    """Строгая политика: когда рефлексия одобряет или блокирует gate."""

    policy_id: str = Field(..., min_length=1)
    gate: ReflectionGate
    target: ReflectionTarget
    instruction: str = Field(..., min_length=1)
    criteria: list[CriticCriterion] = Field(..., min_length=1)
    min_confidence: float = Field(..., ge=0.0, le=1.0)
    block_on_severities: list[CriticSeverity] = Field(..., min_length=1)
    exits: list[CriticExit] = Field(default_factory=default_pass_fail_exits, min_length=1)

    @model_validator(mode="after")
    def ids_and_blockers_must_be_unique(self) -> "CriticPolicy":
        criterion_ids = [criterion.criterion_id for criterion in self.criteria]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise ValueError("critic criteria criterion_id values must be unique")
        if len(set(self.block_on_severities)) != len(self.block_on_severities):
            raise ValueError("critic block_on_severities values must be unique")
        exit_ids = [exit_item.exit_id for exit_item in self.exits]
        if len(set(exit_ids)) != len(exit_ids):
            raise ValueError("critic exits exit_id values must be unique")
        always_indexes = [
            index for index, exit_item in enumerate(self.exits) if exit_item.when.kind == "always"
        ]
        if always_indexes:
            if len(always_indexes) > 1:
                raise ValueError("critic exits may contain at most one when.kind='always'")
            if always_indexes[0] != len(self.exits) - 1:
                raise ValueError("critic exit with when.kind='always' must be last")
        return self


class ReflectionTargetSnapshot(StrictBaseModel):
    """Разрешённая цель проверки, зафиксированная во входе durable activity."""

    target: ReflectionTarget
    value: JsonValue


class ReflectionCritiqueIssue(StrictBaseModel):
    """Одна конкретная проблема, найденная критиком."""

    criterion_id: str = Field(..., min_length=1)
    severity: CriticSeverity
    finding: str = Field(..., min_length=1)
    evidence: str = Field(..., min_length=1)
    required_action: str = Field(..., min_length=1)


class ReflectionCritiqueResult(StrictBaseModel):
    """Структурированный ответ критика от модели."""

    decision: CriticDecision
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str = Field(..., min_length=1)
    issues: list[ReflectionCritiqueIssue] = Field(default_factory=list)


class ReflectionGateResult(StrictBaseModel):
    """Детерминированный результат gate, применённый к workflow state."""

    policy_id: str = Field(..., min_length=1)
    gate: ReflectionGate
    target: ReflectionTarget
    approved: bool
    blocked_reasons: list[str]
    critique: ReflectionCritiqueResult
    exit_id: str = Field(..., min_length=1)


class ReflectionRecord(StrictBaseModel):
    """Запись истории state для завершённого reflection gate."""

    node_id: str = Field(..., min_length=1)
    execution_branch_id: str = Field(..., min_length=1)
    node_schedule_sequence: int = Field(..., ge=0)
    result: ReflectionGateResult


def exit_when_matches(
    when: CriticExitWhen,
    *,
    approved: bool,
    decision: CriticDecision,
    blocked_reasons: list[str],
) -> bool:
    """Проверяет предикат выхода против уже посчитанных полей gate."""
    if when.kind == "always":
        return True
    if when.kind == "approved_true":
        return approved is True
    if when.kind == "approved_false":
        return approved is False
    if when.kind == "decision_eq":
        if when.decision is None:
            raise ValueError("decision_eq requires decision")
        return decision == when.decision
    if when.kind == "blocked_reason_prefix":
        if when.reason_prefix is None:
            raise ValueError("blocked_reason_prefix requires reason_prefix")
        prefix = when.reason_prefix
        return any(reason.startswith(prefix) for reason in blocked_reasons)
    raise ValueError(f"unknown CriticExitWhen.kind: {when.kind!r}")


def select_reflection_exit(
    exits: list[CriticExit],
    *,
    approved: bool,
    decision: CriticDecision,
    blocked_reasons: list[str],
) -> str:
    """First-match выбор exit_id. Нет совпадения — raise (Zero-Guess)."""
    if not exits:
        raise ValueError("reflection exits must not be empty")
    for exit_item in exits:
        if exit_when_matches(
            exit_item.when,
            approved=approved,
            decision=decision,
            blocked_reasons=blocked_reasons,
        ):
            return exit_item.exit_id
    raise ValueError(
        "no reflection exit matched gate result "
        + f"(approved={approved!r}, decision={decision!r}, blocked_reasons={blocked_reasons!r})"
    )


def evaluate_reflection_gate(
    *,
    policy: CriticPolicy,
    critique: ReflectionCritiqueResult,
) -> ReflectionGateResult:
    """Применяет детерминированные правила gate к структурированному ответу критика."""
    blocked_reasons: list[str] = []
    if critique.decision != "approved":
        blocked_reasons.append(f"decision:{critique.decision}")
    if critique.confidence < policy.min_confidence:
        blocked_reasons.append("confidence_below_minimum")

    blocked_severities = set(policy.block_on_severities)
    for issue in critique.issues:
        if issue.severity in blocked_severities:
            blocked_reasons.append(f"issue:{issue.severity}:{issue.criterion_id}")

    approved = not blocked_reasons
    exit_id = select_reflection_exit(
        policy.exits,
        approved=approved,
        decision=critique.decision,
        blocked_reasons=blocked_reasons,
    )
    return ReflectionGateResult(
        policy_id=policy.policy_id,
        gate=policy.gate,
        target=policy.target,
        approved=approved,
        blocked_reasons=blocked_reasons,
        critique=critique,
        exit_id=exit_id,
    )


__all__ = [
    "CriticCriterion",
    "CriticDecision",
    "CriticExit",
    "CriticExitWhen",
    "CriticPolicy",
    "CriticSeverity",
    "ReflectionCritiqueIssue",
    "ReflectionCritiqueResult",
    "ReflectionExitWhenKind",
    "ReflectionGate",
    "ReflectionGateResult",
    "ReflectionRecord",
    "ReflectionTarget",
    "ReflectionTargetKind",
    "ReflectionTargetSnapshot",
    "default_pass_fail_exits",
    "evaluate_reflection_gate",
    "exit_when_matches",
    "select_reflection_exit",
]
