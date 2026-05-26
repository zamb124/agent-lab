"""Repository for first-class evaluation suites, cases, runs and events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import cast

from pydantic import TypeAdapter
from sqlalchemy import text

from apps.flows.src.models.evaluation_lab import (
    EvaluationAnnotation,
    EvaluationAnnotationType,
    EvaluationBaseline,
    EvaluationCase,
    EvaluationCaseRun,
    EvaluationDialogMessage,
    EvaluationEventType,
    EvaluationGatePolicy,
    EvaluationGateResult,
    EvaluationGateState,
    EvaluationMonitor,
    EvaluationMonitorFilter,
    EvaluationMonitorObservation,
    EvaluationMonitorObservationState,
    EvaluationMonitorState,
    EvaluationPairwiseJudgeMode,
    EvaluationPairwiseJudgment,
    EvaluationPairwisePreference,
    EvaluationRubric,
    EvaluationRubricVersion,
    EvaluationRun,
    EvaluationRunEvent,
    EvaluationRunJob,
    EvaluationRunJobState,
    EvaluationRunWithCases,
    EvaluationSuite,
    EvaluationSuiteVersion,
)
from core.context import require_active_company
from core.db import Storage
from core.db.utils import get_rowcount
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    SqlParameterValue,
    parse_json_object,
    require_json_object,
)

EvaluationLabRowValue = str | int | float | bool | datetime | JsonObject | JsonArray | None

_EVALUATION_CASES_ADAPTER: TypeAdapter[list[EvaluationCase]] = TypeAdapter(list[EvaluationCase])
_EVALUATION_DIALOG_ADAPTER: TypeAdapter[list[EvaluationDialogMessage]] = TypeAdapter(
    list[EvaluationDialogMessage]
)
_STRING_LIST_ADAPTER: TypeAdapter[list[str]] = TypeAdapter(list[str])
_EVALUATION_MONITOR_FILTER_ADAPTER: TypeAdapter[EvaluationMonitorFilter] = TypeAdapter(
    EvaluationMonitorFilter
)
_EVALUATION_SCORES_ADAPTER: TypeAdapter[dict[str, float | bool]] = TypeAdapter(
    dict[str, float | bool]
)


def _company_id() -> str:
    return require_active_company().company_id


def _json_payload(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_object(value: EvaluationLabRowValue, field_name: str) -> JsonObject:
    if isinstance(value, str):
        return parse_json_object(value, field_name)
    return require_json_object(value, field_name)


def _int_scalar(value: EvaluationLabRowValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an int")
    return value


class EvaluationLabRepository:
    """SQL repository for the target evaluation domain."""

    def __init__(self, storage: Storage):
        self._storage: Storage = storage

    async def create_suite(self, suite: EvaluationSuite) -> EvaluationSuite:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_suites
                        (suite_id, company_id, flow_id, name, description, tags, archived_at,
                         created_at, updated_at)
                    VALUES
                        (:suite_id, :company_id, :flow_id, :name, :description, :tags, :archived_at,
                         :created_at, :updated_at)
                """),
                {
                    "suite_id": suite.suite_id,
                    "company_id": company_id,
                    "flow_id": suite.flow_id,
                    "name": suite.name,
                    "description": suite.description,
                    "tags": _json_payload(suite.tags),
                    "archived_at": suite.archived_at,
                    "created_at": suite.created_at,
                    "updated_at": suite.updated_at,
                },
            )
            await session.commit()
        return suite

    async def update_suite(self, suite: EvaluationSuite) -> EvaluationSuite:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_suites
                    SET name = :name,
                        description = :description,
                        tags = :tags,
                        archived_at = :archived_at,
                        updated_at = :updated_at
                    WHERE company_id = :company_id AND suite_id = :suite_id
                """),
                {
                    "company_id": company_id,
                    "suite_id": suite.suite_id,
                    "name": suite.name,
                    "description": suite.description,
                    "tags": _json_payload(suite.tags),
                    "archived_at": suite.archived_at,
                    "updated_at": suite.updated_at,
                },
            )
            await session.commit()
        return suite

    async def get_suite(self, suite_id: str) -> EvaluationSuite | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_suites
                    WHERE company_id = :company_id AND suite_id = :suite_id
                """),
                {"company_id": company_id, "suite_id": suite_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._suite_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def list_suites(self, flow_id: str) -> list[EvaluationSuite]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_suites
                    WHERE company_id = :company_id AND flow_id = :flow_id
                    ORDER BY updated_at DESC, suite_id ASC
                """),
                {"company_id": company_id, "flow_id": flow_id},
            )
            rows = result.mappings().all()
        return [self._suite_from_row(cast(Mapping[str, EvaluationLabRowValue], row)) for row in rows]

    async def create_case(self, case: EvaluationCase) -> EvaluationCase:
        company_id = _company_id()
        payload = require_json_object(case.model_dump(mode="json"), "EvaluationCase")
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_cases
                        (case_id, suite_id, company_id, flow_id, name, enabled, sort_order, payload, created_at, updated_at)
                    VALUES
                        (:case_id, :suite_id, :company_id, :flow_id, :name, :enabled, :sort_order, :payload, :created_at, :updated_at)
                """),
                {
                    "case_id": case.case_id,
                    "suite_id": case.suite_id,
                    "company_id": company_id,
                    "flow_id": case.flow_id,
                    "name": case.name,
                    "enabled": case.enabled,
                    "sort_order": case.sort_order,
                    "payload": _json_payload(payload),
                    "created_at": case.created_at,
                    "updated_at": case.updated_at,
                },
            )
            await session.commit()
        return case

    async def update_case(self, case: EvaluationCase) -> EvaluationCase:
        company_id = _company_id()
        payload = require_json_object(case.model_dump(mode="json"), "EvaluationCase")
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_cases
                    SET name = :name,
                        enabled = :enabled,
                        sort_order = :sort_order,
                        payload = :payload,
                        updated_at = :updated_at
                    WHERE company_id = :company_id AND suite_id = :suite_id AND case_id = :case_id
                """),
                {
                    "company_id": company_id,
                    "suite_id": case.suite_id,
                    "case_id": case.case_id,
                    "name": case.name,
                    "enabled": case.enabled,
                    "sort_order": case.sort_order,
                    "payload": _json_payload(payload),
                    "updated_at": case.updated_at,
                },
            )
            await session.commit()
        return case

    async def delete_case(self, suite_id: str, case_id: str) -> bool:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    DELETE FROM evaluation_cases
                    WHERE company_id = :company_id AND suite_id = :suite_id AND case_id = :case_id
                """),
                {"company_id": company_id, "suite_id": suite_id, "case_id": case_id},
            )
            await session.commit()
        return get_rowcount(result) == 1

    async def get_case(self, suite_id: str, case_id: str) -> EvaluationCase | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT payload
                    FROM evaluation_cases
                    WHERE company_id = :company_id AND suite_id = :suite_id AND case_id = :case_id
                """),
                {"company_id": company_id, "suite_id": suite_id, "case_id": case_id},
            )
            row = result.first()
        if row is None:
            return None
        payload = _json_object(cast(EvaluationLabRowValue, row[0]), "evaluation_cases.payload")
        return EvaluationCase.model_validate(payload)

    async def list_cases(self, suite_id: str) -> list[EvaluationCase]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT payload
                    FROM evaluation_cases
                    WHERE company_id = :company_id AND suite_id = :suite_id
                    ORDER BY sort_order ASC, created_at ASC, case_id ASC
                """),
                {"company_id": company_id, "suite_id": suite_id},
            )
            rows = result.all()
        cases: list[EvaluationCase] = []
        for row in rows:
            payload = _json_object(cast(EvaluationLabRowValue, row[0]), "evaluation_cases.payload")
            cases.append(EvaluationCase.model_validate(payload))
        return cases

    async def create_rubric(
        self,
        rubric: EvaluationRubric,
        version: EvaluationRubricVersion,
    ) -> tuple[EvaluationRubric, EvaluationRubricVersion]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_rubrics
                        (rubric_id, company_id, flow_id, name, description, tags, archived_at,
                         created_at, updated_at)
                    VALUES
                        (:rubric_id, :company_id, :flow_id, :name, :description, :tags, :archived_at,
                         :created_at, :updated_at)
                """),
                {
                    "rubric_id": rubric.rubric_id,
                    "company_id": company_id,
                    "flow_id": rubric.flow_id,
                    "name": rubric.name,
                    "description": rubric.description,
                    "tags": _json_payload(rubric.tags),
                    "archived_at": rubric.archived_at,
                    "created_at": rubric.created_at,
                    "updated_at": rubric.updated_at,
                },
            )
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_rubric_versions
                        (rubric_version_id, rubric_id, company_id, flow_id, version, prompt,
                         pass_threshold, created_at)
                    VALUES
                        (:rubric_version_id, :rubric_id, :company_id, :flow_id, :version, :prompt,
                         :pass_threshold, :created_at)
                """),
                self._rubric_version_params(version, company_id),
            )
            await session.commit()
        return rubric, version

    async def update_rubric(self, rubric: EvaluationRubric) -> EvaluationRubric:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_rubrics
                    SET name = :name,
                        description = :description,
                        tags = :tags,
                        archived_at = :archived_at,
                        updated_at = :updated_at
                    WHERE company_id = :company_id AND rubric_id = :rubric_id
                """),
                {
                    "company_id": company_id,
                    "rubric_id": rubric.rubric_id,
                    "name": rubric.name,
                    "description": rubric.description,
                    "tags": _json_payload(rubric.tags),
                    "archived_at": rubric.archived_at,
                    "updated_at": rubric.updated_at,
                },
            )
            await session.commit()
        return rubric

    async def get_rubric(self, rubric_id: str) -> EvaluationRubric | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_rubrics
                    WHERE company_id = :company_id AND rubric_id = :rubric_id
                """),
                {"company_id": company_id, "rubric_id": rubric_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._rubric_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def list_rubrics(self, flow_id: str) -> list[EvaluationRubric]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_rubrics
                    WHERE company_id = :company_id AND flow_id = :flow_id
                    ORDER BY updated_at DESC, rubric_id ASC
                """),
                {"company_id": company_id, "flow_id": flow_id},
            )
            rows = result.mappings().all()
        return [
            self._rubric_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def create_rubric_version(
        self,
        version: EvaluationRubricVersion,
    ) -> EvaluationRubricVersion:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_rubric_versions
                        (rubric_version_id, rubric_id, company_id, flow_id, version, prompt,
                         pass_threshold, created_at)
                    VALUES
                        (:rubric_version_id, :rubric_id, :company_id, :flow_id, :version, :prompt,
                         :pass_threshold, :created_at)
                """),
                self._rubric_version_params(version, company_id),
            )
            await session.commit()
        return version

    async def next_rubric_version(self, rubric_id: str) -> int:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM evaluation_rubric_versions
                    WHERE company_id = :company_id AND rubric_id = :rubric_id
                """),
                {"company_id": company_id, "rubric_id": rubric_id},
            )
        return _int_scalar(
            cast(EvaluationLabRowValue, result.scalar_one()),
            "evaluation_rubric_versions.next_version",
        )

    async def get_rubric_version(
        self,
        rubric_version_id: str,
    ) -> EvaluationRubricVersion | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_rubric_versions
                    WHERE company_id = :company_id AND rubric_version_id = :rubric_version_id
                """),
                {"company_id": company_id, "rubric_version_id": rubric_version_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._rubric_version_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def list_rubric_versions(self, rubric_id: str) -> list[EvaluationRubricVersion]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_rubric_versions
                    WHERE company_id = :company_id AND rubric_id = :rubric_id
                    ORDER BY version DESC
                """),
                {"company_id": company_id, "rubric_id": rubric_id},
            )
            rows = result.mappings().all()
        return [
            self._rubric_version_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def create_suite_version(
        self,
        suite_version: EvaluationSuiteVersion,
    ) -> EvaluationSuiteVersion:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_suite_versions
                        (suite_version_id, suite_id, company_id, flow_id, flow_config_version,
                         version, suite_snapshot, cases_snapshot, created_at)
                    VALUES
                        (:suite_version_id, :suite_id, :company_id, :flow_id, :flow_config_version,
                         :version, :suite_snapshot, :cases_snapshot, :created_at)
                """),
                {
                    "suite_version_id": suite_version.suite_version_id,
                    "suite_id": suite_version.suite_id,
                    "company_id": company_id,
                    "flow_id": suite_version.flow_id,
                    "flow_config_version": suite_version.flow_config_version,
                    "version": suite_version.version,
                    "suite_snapshot": _json_payload(
                        require_json_object(
                            suite_version.suite_snapshot.model_dump(mode="json"),
                            "EvaluationSuiteVersion.suite_snapshot",
                        )
                    ),
                    "cases_snapshot": _json_payload(
                        [
                            require_json_object(
                                case.model_dump(mode="json"),
                                "EvaluationSuiteVersion.cases_snapshot[]",
                            )
                            for case in suite_version.cases_snapshot
                        ]
                    ),
                    "created_at": suite_version.created_at,
                },
            )
            await session.commit()
        return suite_version

    async def next_suite_version(self, suite_id: str) -> int:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM evaluation_suite_versions
                    WHERE company_id = :company_id AND suite_id = :suite_id
                """),
                {"company_id": company_id, "suite_id": suite_id},
            )
        return _int_scalar(
            cast(EvaluationLabRowValue, result.scalar_one()),
            "evaluation_suite_versions.next_version",
        )

    async def get_suite_version(self, suite_version_id: str) -> EvaluationSuiteVersion | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_suite_versions
                    WHERE company_id = :company_id AND suite_version_id = :suite_version_id
                """),
                {"company_id": company_id, "suite_version_id": suite_version_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._suite_version_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def create_run(self, run: EvaluationRun) -> EvaluationRun:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_runs
                        (run_id, suite_id, suite_version_id, company_id, flow_id, branch_id,
                         flow_config_version, trigger, scope, state, idempotency_key,
                         taskiq_task_id, gate_policy_id, gate_state, total_cases, trials,
                         max_concurrency, total_case_runs,
                         passed_case_runs, failed_case_runs, error_case_runs, canceled_case_runs,
                         average_score, average_duration_ms, input_tokens, output_tokens, total_tokens,
                         billing_quantity, started_at, finished_at, created_at, updated_at)
                    VALUES
                        (:run_id, :suite_id, :suite_version_id, :company_id, :flow_id, :branch_id,
                         :flow_config_version, :trigger, :scope, :state, :idempotency_key,
                         :taskiq_task_id, :gate_policy_id, :gate_state, :total_cases, :trials,
                         :max_concurrency, :total_case_runs,
                         :passed_case_runs, :failed_case_runs, :error_case_runs, :canceled_case_runs,
                         :average_score, :average_duration_ms, :input_tokens, :output_tokens, :total_tokens,
                         :billing_quantity, :started_at, :finished_at, :created_at, :updated_at)
                """),
                self._run_params(run, company_id),
            )
            await session.commit()
        return run

    async def update_run(self, run: EvaluationRun) -> EvaluationRun:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_runs
                    SET state = :state,
                        idempotency_key = :idempotency_key,
                        taskiq_task_id = :taskiq_task_id,
                        gate_policy_id = :gate_policy_id,
                        gate_state = :gate_state,
                        total_cases = :total_cases,
                        trials = :trials,
                        max_concurrency = :max_concurrency,
                        total_case_runs = :total_case_runs,
                        passed_case_runs = :passed_case_runs,
                        failed_case_runs = :failed_case_runs,
                        error_case_runs = :error_case_runs,
                        canceled_case_runs = :canceled_case_runs,
                        average_score = :average_score,
                        average_duration_ms = :average_duration_ms,
                        input_tokens = :input_tokens,
                        output_tokens = :output_tokens,
                        total_tokens = :total_tokens,
                        billing_quantity = :billing_quantity,
                        started_at = :started_at,
                        finished_at = :finished_at,
                        updated_at = :updated_at
                    WHERE company_id = :company_id AND run_id = :run_id
                """),
                self._run_params(run, company_id),
            )
            await session.commit()
        return run

    async def get_run(self, run_id: str) -> EvaluationRun | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_runs
                    WHERE company_id = :company_id AND run_id = :run_id
                """),
                {"company_id": company_id, "run_id": run_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._run_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def get_run_by_idempotency_key(
        self,
        *,
        suite_id: str,
        branch_id: str,
        idempotency_key: str,
    ) -> EvaluationRun | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_runs
                    WHERE company_id = :company_id
                      AND suite_id = :suite_id
                      AND branch_id = :branch_id
                      AND idempotency_key = :idempotency_key
                """),
                {
                    "company_id": company_id,
                    "suite_id": suite_id,
                    "branch_id": branch_id,
                    "idempotency_key": idempotency_key,
                },
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._run_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def create_run_job(self, job: EvaluationRunJob) -> EvaluationRunJob:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_run_jobs
                        (run_job_id, run_id, company_id, taskiq_task_id, state, context_data,
                         trace_context, error, enqueued_at, created_at, updated_at)
                    VALUES
                        (:run_job_id, :run_id, :company_id, :taskiq_task_id, :state, :context_data,
                         :trace_context, :error, :enqueued_at, :created_at, :updated_at)
                    ON CONFLICT (company_id, run_id) DO NOTHING
                """),
                self._run_job_params(job, company_id),
            )
            await session.commit()
        stored = await self.get_run_job_by_run_id(job.run_id)
        if stored is None:
            raise ValueError("evaluation run job insert did not persist")
        return stored

    async def update_run_job(self, job: EvaluationRunJob) -> EvaluationRunJob:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_run_jobs
                    SET state = :state,
                        taskiq_task_id = :taskiq_task_id,
                        context_data = :context_data,
                        trace_context = :trace_context,
                        error = :error,
                        enqueued_at = :enqueued_at,
                        updated_at = :updated_at
                    WHERE company_id = :company_id AND run_job_id = :run_job_id
                """),
                self._run_job_params(job, company_id),
            )
            await session.commit()
        return job

    async def get_run_job_by_run_id(self, run_id: str) -> EvaluationRunJob | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_run_jobs
                    WHERE company_id = :company_id AND run_id = :run_id
                """),
                {"company_id": company_id, "run_id": run_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._run_job_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def list_pending_run_jobs(self, limit: int) -> list[EvaluationRunJob]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_run_jobs
                    WHERE company_id = :company_id AND state = :state
                    ORDER BY created_at ASC, run_job_id ASC
                    LIMIT :limit
                """),
                {
                    "company_id": company_id,
                    "state": str(EvaluationRunJobState.PENDING),
                    "limit": limit,
                },
            )
            rows = result.mappings().all()
        return [
            self._run_job_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def list_runs(self, suite_id: str, limit: int) -> list[EvaluationRun]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_runs
                    WHERE company_id = :company_id AND suite_id = :suite_id
                    ORDER BY created_at DESC, run_id DESC
                    LIMIT :limit
                """),
                {"company_id": company_id, "suite_id": suite_id, "limit": limit},
            )
            rows = result.mappings().all()
        return [self._run_from_row(cast(Mapping[str, EvaluationLabRowValue], row)) for row in rows]

    async def create_case_run(self, case_run: EvaluationCaseRun) -> EvaluationCaseRun:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_case_runs
                        (case_run_id, run_id, case_id, suite_id, company_id, flow_id, branch_id,
                         trial_index, state, task_id, context_id, session_id, trace_id, duration_ms,
                         input_tokens, output_tokens, total_tokens, billing_quantity, turns_count,
                         scores, total_score, judge_feedback, dialog, error, started_at, finished_at,
                         created_at, updated_at)
                    VALUES
                        (:case_run_id, :run_id, :case_id, :suite_id, :company_id, :flow_id, :branch_id,
                         :trial_index, :state, :task_id, :context_id, :session_id, :trace_id,
                         :duration_ms, :input_tokens, :output_tokens, :total_tokens,
                         :billing_quantity, :turns_count, :scores, :total_score, :judge_feedback,
                         :dialog, :error, :started_at, :finished_at, :created_at, :updated_at)
                """),
                self._case_run_params(case_run, company_id),
            )
            await session.commit()
        return case_run

    async def update_case_run(self, case_run: EvaluationCaseRun) -> EvaluationCaseRun:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_case_runs
                    SET state = :state,
                        task_id = :task_id,
                        context_id = :context_id,
                        session_id = :session_id,
                        trace_id = :trace_id,
                        duration_ms = :duration_ms,
                        input_tokens = :input_tokens,
                        output_tokens = :output_tokens,
                        total_tokens = :total_tokens,
                        billing_quantity = :billing_quantity,
                        turns_count = :turns_count,
                        scores = :scores,
                        total_score = :total_score,
                        judge_feedback = :judge_feedback,
                        dialog = :dialog,
                        error = :error,
                        started_at = :started_at,
                        finished_at = :finished_at,
                        updated_at = :updated_at
                    WHERE company_id = :company_id AND case_run_id = :case_run_id
                """),
                self._case_run_params(case_run, company_id),
            )
            await session.commit()
        return case_run

    async def list_case_runs(self, run_id: str) -> list[EvaluationCaseRun]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_case_runs
                    WHERE company_id = :company_id AND run_id = :run_id
                    ORDER BY case_id ASC, trial_index ASC, created_at ASC
                """),
                {"company_id": company_id, "run_id": run_id},
            )
            rows = result.mappings().all()
        return [
            self._case_run_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def get_case_run(self, case_run_id: str) -> EvaluationCaseRun | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_case_runs
                    WHERE company_id = :company_id AND case_run_id = :case_run_id
                """),
                {"company_id": company_id, "case_run_id": case_run_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._case_run_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def get_run_with_cases(self, run_id: str) -> EvaluationRunWithCases | None:
        run = await self.get_run(run_id)
        if run is None:
            return None
        case_runs = await self.list_case_runs(run_id)
        gate_result = await self.get_gate_result(run_id)
        return EvaluationRunWithCases(run=run, case_runs=case_runs, gate_result=gate_result)

    async def next_event_sequence(self, run_id: str) -> int:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT COALESCE(MAX(sequence), 0) + 1
                    FROM evaluation_run_events
                    WHERE company_id = :company_id AND run_id = :run_id
                """),
                {"company_id": company_id, "run_id": run_id},
            )
        return _int_scalar(
            cast(EvaluationLabRowValue, result.scalar_one()),
            "evaluation_run_events.next_sequence",
        )

    async def append_event(self, event: EvaluationRunEvent) -> EvaluationRunEvent:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_run_events
                        (event_id, run_id, case_run_id, company_id, sequence, event_type, payload, created_at)
                    VALUES
                        (:event_id, :run_id, :case_run_id, :company_id, :sequence, :event_type, :payload, :created_at)
                """),
                {
                    "event_id": event.event_id,
                    "run_id": event.run_id,
                    "case_run_id": event.case_run_id,
                    "company_id": company_id,
                    "sequence": event.sequence,
                    "event_type": str(event.event_type),
                    "payload": _json_payload(event.payload),
                    "created_at": event.created_at,
                },
            )
            await session.commit()
        return event

    async def list_events(self, run_id: str) -> list[EvaluationRunEvent]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_run_events
                    WHERE company_id = :company_id AND run_id = :run_id
                    ORDER BY sequence ASC
                """),
                {"company_id": company_id, "run_id": run_id},
            )
            rows = result.mappings().all()
        return [
            self._event_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def list_events_after_sequence(
        self,
        run_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> list[EvaluationRunEvent]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_run_events
                    WHERE company_id = :company_id
                      AND run_id = :run_id
                      AND sequence > :after_sequence
                    ORDER BY sequence ASC
                    LIMIT :limit
                """),
                {
                    "company_id": company_id,
                    "run_id": run_id,
                    "after_sequence": after_sequence,
                    "limit": limit,
                },
            )
            rows = result.mappings().all()
        return [
            self._event_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def create_annotation(self, annotation: EvaluationAnnotation) -> EvaluationAnnotation:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_annotations
                        (annotation_id, run_id, case_run_id, company_id, case_id,
                         annotation_type, comment, payload, created_by, created_at, updated_at)
                    VALUES
                        (:annotation_id, :run_id, :case_run_id, :company_id, :case_id,
                         :annotation_type, :comment, :payload, :created_by, :created_at, :updated_at)
                """),
                self._annotation_params(annotation, company_id),
            )
            await session.commit()
        return annotation

    async def update_annotation(self, annotation: EvaluationAnnotation) -> EvaluationAnnotation:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_annotations
                    SET annotation_type = :annotation_type,
                        comment = :comment,
                        payload = :payload,
                        updated_at = :updated_at
                    WHERE company_id = :company_id AND annotation_id = :annotation_id
                """),
                self._annotation_params(annotation, company_id),
            )
            await session.commit()
        return annotation

    async def get_annotation(self, annotation_id: str) -> EvaluationAnnotation | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_annotations
                    WHERE company_id = :company_id AND annotation_id = :annotation_id
                """),
                {"company_id": company_id, "annotation_id": annotation_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._annotation_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def list_annotations(self, run_id: str) -> list[EvaluationAnnotation]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_annotations
                    WHERE company_id = :company_id AND run_id = :run_id
                    ORDER BY created_at ASC, annotation_id ASC
                """),
                {"company_id": company_id, "run_id": run_id},
            )
            rows = result.mappings().all()
        return [
            self._annotation_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def delete_annotation(self, annotation_id: str) -> bool:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    DELETE FROM evaluation_annotations
                    WHERE company_id = :company_id AND annotation_id = :annotation_id
                """),
                {"company_id": company_id, "annotation_id": annotation_id},
            )
            await session.commit()
        return get_rowcount(result) == 1

    async def upsert_baseline(self, baseline: EvaluationBaseline) -> EvaluationBaseline:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_baselines
                        (baseline_id, suite_id, company_id, flow_id, branch_id, run_id,
                         created_by, created_at, updated_at)
                    VALUES
                        (:baseline_id, :suite_id, :company_id, :flow_id, :branch_id, :run_id,
                         :created_by, :created_at, :updated_at)
                    ON CONFLICT (company_id, suite_id, branch_id)
                    DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        created_by = EXCLUDED.created_by,
                        updated_at = EXCLUDED.updated_at
                """),
                self._baseline_params(baseline, company_id),
            )
            await session.commit()
        stored = await self.get_baseline(baseline.suite_id, baseline.branch_id)
        if stored is None:
            raise ValueError("evaluation baseline upsert did not persist")
        return stored

    async def get_baseline(
        self,
        suite_id: str,
        branch_id: str,
    ) -> EvaluationBaseline | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_baselines
                    WHERE company_id = :company_id
                      AND suite_id = :suite_id
                      AND branch_id = :branch_id
                """),
                {"company_id": company_id, "suite_id": suite_id, "branch_id": branch_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._baseline_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def list_baselines(self, suite_id: str) -> list[EvaluationBaseline]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_baselines
                    WHERE company_id = :company_id AND suite_id = :suite_id
                    ORDER BY branch_id ASC
                """),
                {"company_id": company_id, "suite_id": suite_id},
            )
            rows = result.mappings().all()
        return [
            self._baseline_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def create_gate_policy(self, policy: EvaluationGatePolicy) -> EvaluationGatePolicy:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_gate_policies
                        (gate_policy_id, suite_id, company_id, flow_id, branch_id, name,
                         min_pass_rate, min_average_score, max_failed_case_runs,
                         max_error_case_runs, max_average_duration_ms, require_baseline,
                         min_baseline_score_delta, max_baseline_duration_delta_ms,
                         archived_at, created_at, updated_at)
                    VALUES
                        (:gate_policy_id, :suite_id, :company_id, :flow_id, :branch_id, :name,
                         :min_pass_rate, :min_average_score, :max_failed_case_runs,
                         :max_error_case_runs, :max_average_duration_ms, :require_baseline,
                         :min_baseline_score_delta, :max_baseline_duration_delta_ms,
                         :archived_at, :created_at, :updated_at)
                """),
                self._gate_policy_params(policy, company_id),
            )
            await session.commit()
        return policy

    async def update_gate_policy(self, policy: EvaluationGatePolicy) -> EvaluationGatePolicy:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_gate_policies
                    SET branch_id = :branch_id,
                        name = :name,
                        min_pass_rate = :min_pass_rate,
                        min_average_score = :min_average_score,
                        max_failed_case_runs = :max_failed_case_runs,
                        max_error_case_runs = :max_error_case_runs,
                        max_average_duration_ms = :max_average_duration_ms,
                        require_baseline = :require_baseline,
                        min_baseline_score_delta = :min_baseline_score_delta,
                        max_baseline_duration_delta_ms = :max_baseline_duration_delta_ms,
                        archived_at = :archived_at,
                        updated_at = :updated_at
                    WHERE company_id = :company_id AND gate_policy_id = :gate_policy_id
                """),
                self._gate_policy_params(policy, company_id),
            )
            await session.commit()
        return policy

    async def get_gate_policy(self, gate_policy_id: str) -> EvaluationGatePolicy | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_gate_policies
                    WHERE company_id = :company_id AND gate_policy_id = :gate_policy_id
                """),
                {"company_id": company_id, "gate_policy_id": gate_policy_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._gate_policy_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def list_gate_policies(self, suite_id: str) -> list[EvaluationGatePolicy]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_gate_policies
                    WHERE company_id = :company_id AND suite_id = :suite_id
                    ORDER BY branch_id ASC, name ASC
                """),
                {"company_id": company_id, "suite_id": suite_id},
            )
            rows = result.mappings().all()
        return [
            self._gate_policy_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def create_gate_result(self, result: EvaluationGateResult) -> EvaluationGateResult:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_gate_results
                        (gate_result_id, run_id, gate_policy_id, company_id, state,
                         metrics, violations, created_at)
                    VALUES
                        (:gate_result_id, :run_id, :gate_policy_id, :company_id, :state,
                         :metrics, :violations, :created_at)
                """),
                self._gate_result_params(result, company_id),
            )
            await session.commit()
        return result

    async def get_gate_result(self, run_id: str) -> EvaluationGateResult | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_gate_results
                    WHERE company_id = :company_id AND run_id = :run_id
                """),
                {"company_id": company_id, "run_id": run_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._gate_result_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def create_monitor(self, monitor: EvaluationMonitor) -> EvaluationMonitor:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_monitors
                        (monitor_id, suite_id, company_id, flow_id, branch_id, name,
                         description, state, sampling_rate, max_traces_per_sample, filter,
                         gate_policy_id, created_by, created_at, updated_at)
                    VALUES
                        (:monitor_id, :suite_id, :company_id, :flow_id, :branch_id, :name,
                         :description, :state, :sampling_rate, :max_traces_per_sample, :filter,
                         :gate_policy_id, :created_by, :created_at, :updated_at)
                """),
                self._monitor_params(monitor, company_id),
            )
            await session.commit()
        return monitor

    async def update_monitor(self, monitor: EvaluationMonitor) -> EvaluationMonitor:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_monitors
                    SET branch_id = :branch_id,
                        name = :name,
                        description = :description,
                        state = :state,
                        sampling_rate = :sampling_rate,
                        max_traces_per_sample = :max_traces_per_sample,
                        filter = :filter,
                        gate_policy_id = :gate_policy_id,
                        updated_at = :updated_at
                    WHERE company_id = :company_id AND monitor_id = :monitor_id
                """),
                self._monitor_params(monitor, company_id),
            )
            await session.commit()
        return monitor

    async def get_monitor(self, monitor_id: str) -> EvaluationMonitor | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_monitors
                    WHERE company_id = :company_id AND monitor_id = :monitor_id
                """),
                {"company_id": company_id, "monitor_id": monitor_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._monitor_from_row(cast(Mapping[str, EvaluationLabRowValue], row))

    async def list_monitors(self, suite_id: str) -> list[EvaluationMonitor]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_monitors
                    WHERE company_id = :company_id AND suite_id = :suite_id
                    ORDER BY updated_at DESC, monitor_id ASC
                """),
                {"company_id": company_id, "suite_id": suite_id},
            )
            rows = result.mappings().all()
        return [
            self._monitor_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def list_active_monitors(self, limit: int) -> list[EvaluationMonitor]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_monitors
                    WHERE company_id = :company_id AND state = :state
                    ORDER BY updated_at ASC, monitor_id ASC
                    LIMIT :limit
                """),
                {
                    "company_id": company_id,
                    "state": str(EvaluationMonitorState.ACTIVE),
                    "limit": limit,
                },
            )
            rows = result.mappings().all()
        return [
            self._monitor_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def upsert_monitor_observation(
        self,
        observation: EvaluationMonitorObservation,
    ) -> EvaluationMonitorObservation:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_monitor_observations
                        (observation_id, monitor_id, suite_id, company_id, flow_id, branch_id,
                         trace_id, task_id, session_id, state, span_count, payload, sampled_at,
                         curated_case_id)
                    VALUES
                        (:observation_id, :monitor_id, :suite_id, :company_id, :flow_id, :branch_id,
                         :trace_id, :task_id, :session_id, :state, :span_count, :payload, :sampled_at,
                         :curated_case_id)
                    ON CONFLICT (company_id, monitor_id, trace_id)
                    DO UPDATE SET
                        task_id = EXCLUDED.task_id,
                        session_id = EXCLUDED.session_id,
                        state = CASE
                            WHEN evaluation_monitor_observations.curated_case_id IS NULL
                            THEN EXCLUDED.state
                            ELSE evaluation_monitor_observations.state
                        END,
                        span_count = EXCLUDED.span_count,
                        payload = EXCLUDED.payload,
                        sampled_at = EXCLUDED.sampled_at,
                        curated_case_id = evaluation_monitor_observations.curated_case_id
                """),
                self._monitor_observation_params(observation, company_id),
            )
            await session.commit()
        stored = await self.get_monitor_observation(
            observation.monitor_id,
            observation.trace_id,
        )
        if stored is None:
            raise ValueError("evaluation monitor observation upsert did not persist")
        return stored

    async def get_monitor_observation(
        self,
        monitor_id: str,
        trace_id: str,
    ) -> EvaluationMonitorObservation | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_monitor_observations
                    WHERE company_id = :company_id
                      AND monitor_id = :monitor_id
                      AND trace_id = :trace_id
                """),
                {"company_id": company_id, "monitor_id": monitor_id, "trace_id": trace_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._monitor_observation_from_row(
            cast(Mapping[str, EvaluationLabRowValue], row)
        )

    async def update_monitor_observation(
        self,
        observation: EvaluationMonitorObservation,
    ) -> EvaluationMonitorObservation:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    UPDATE evaluation_monitor_observations
                    SET state = :state,
                        curated_case_id = :curated_case_id,
                        payload = :payload
                    WHERE company_id = :company_id
                      AND monitor_id = :monitor_id
                      AND trace_id = :trace_id
                """),
                self._monitor_observation_params(observation, company_id),
            )
            await session.commit()
        stored = await self.get_monitor_observation(
            observation.monitor_id,
            observation.trace_id,
        )
        if stored is None:
            raise ValueError("evaluation monitor observation update did not persist")
        return stored

    async def list_monitor_observations(
        self,
        monitor_id: str,
        limit: int,
    ) -> list[EvaluationMonitorObservation]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_monitor_observations
                    WHERE company_id = :company_id AND monitor_id = :monitor_id
                    ORDER BY sampled_at DESC, observation_id DESC
                    LIMIT :limit
                """),
                {"company_id": company_id, "monitor_id": monitor_id, "limit": limit},
            )
            rows = result.mappings().all()
        return [
            self._monitor_observation_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    async def create_pairwise_judgment(
        self,
        judgment: EvaluationPairwiseJudgment,
    ) -> EvaluationPairwiseJudgment:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            _ = await session.execute(
                text("""
                    INSERT INTO evaluation_pairwise_judgments
                        (pairwise_judgment_id, company_id, suite_id, flow_id, branch_id,
                         left_run_id, right_run_id, left_case_run_id, right_case_run_id,
                         mode, preferred, rubric_version_id, scores, feedback, created_by,
                         created_at)
                    VALUES
                        (:pairwise_judgment_id, :company_id, :suite_id, :flow_id, :branch_id,
                         :left_run_id, :right_run_id, :left_case_run_id, :right_case_run_id,
                         :mode, :preferred, :rubric_version_id, :scores, :feedback, :created_by,
                         :created_at)
                """),
                self._pairwise_judgment_params(judgment, company_id),
            )
            await session.commit()
        return judgment

    async def get_pairwise_judgment(
        self,
        pairwise_judgment_id: str,
    ) -> EvaluationPairwiseJudgment | None:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_pairwise_judgments
                    WHERE company_id = :company_id
                      AND pairwise_judgment_id = :pairwise_judgment_id
                """),
                {
                    "company_id": company_id,
                    "pairwise_judgment_id": pairwise_judgment_id,
                },
            )
            row = result.mappings().first()
        if row is None:
            return None
        return self._pairwise_judgment_from_row(
            cast(Mapping[str, EvaluationLabRowValue], row)
        )

    async def list_pairwise_judgments_for_case_run(
        self,
        case_run_id: str,
    ) -> list[EvaluationPairwiseJudgment]:
        company_id = _company_id()
        async with self._storage.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM evaluation_pairwise_judgments
                    WHERE company_id = :company_id
                      AND (
                        left_case_run_id = :case_run_id
                        OR right_case_run_id = :case_run_id
                      )
                    ORDER BY created_at DESC, pairwise_judgment_id DESC
                """),
                {"company_id": company_id, "case_run_id": case_run_id},
            )
            rows = result.mappings().all()
        return [
            self._pairwise_judgment_from_row(cast(Mapping[str, EvaluationLabRowValue], row))
            for row in rows
        ]

    def _suite_from_row(self, row: Mapping[str, EvaluationLabRowValue]) -> EvaluationSuite:
        return EvaluationSuite(
            suite_id=self._string(row, "suite_id"),
            flow_id=self._string(row, "flow_id"),
            name=self._string(row, "name"),
            description=self._string(row, "description"),
            tags=self._json_list_strings(row["tags"], "evaluation_suites.tags"),
            archived_at=self._optional_datetime(row, "archived_at"),
            created_at=self._datetime(row, "created_at"),
            updated_at=self._datetime(row, "updated_at"),
        )

    def _rubric_from_row(self, row: Mapping[str, EvaluationLabRowValue]) -> EvaluationRubric:
        return EvaluationRubric(
            rubric_id=self._string(row, "rubric_id"),
            flow_id=self._string(row, "flow_id"),
            name=self._string(row, "name"),
            description=self._string(row, "description"),
            tags=self._json_list_strings(row["tags"], "evaluation_rubrics.tags"),
            archived_at=self._optional_datetime(row, "archived_at"),
            created_at=self._datetime(row, "created_at"),
            updated_at=self._datetime(row, "updated_at"),
        )

    def _rubric_version_from_row(
        self,
        row: Mapping[str, EvaluationLabRowValue],
    ) -> EvaluationRubricVersion:
        return EvaluationRubricVersion(
            rubric_version_id=self._string(row, "rubric_version_id"),
            rubric_id=self._string(row, "rubric_id"),
            flow_id=self._string(row, "flow_id"),
            version=self._int(row, "version"),
            prompt=self._string(row, "prompt"),
            pass_threshold=self._float(row, "pass_threshold"),
            created_at=self._datetime(row, "created_at"),
        )

    def _suite_version_from_row(
        self,
        row: Mapping[str, EvaluationLabRowValue],
    ) -> EvaluationSuiteVersion:
        suite_snapshot = EvaluationSuite.model_validate(
            _json_object(row["suite_snapshot"], "evaluation_suite_versions.suite_snapshot")
        )
        cases_payload = row["cases_snapshot"]
        if isinstance(cases_payload, str):
            cases_snapshot = _EVALUATION_CASES_ADAPTER.validate_json(cases_payload)
        else:
            cases_snapshot = _EVALUATION_CASES_ADAPTER.validate_python(cases_payload)
        return EvaluationSuiteVersion(
            suite_version_id=self._string(row, "suite_version_id"),
            suite_id=self._string(row, "suite_id"),
            flow_id=self._string(row, "flow_id"),
            flow_config_version=self._string(row, "flow_config_version"),
            version=self._int(row, "version"),
            suite_snapshot=suite_snapshot,
            cases_snapshot=cases_snapshot,
            created_at=self._datetime(row, "created_at"),
        )

    def _run_from_row(self, row: Mapping[str, EvaluationLabRowValue]) -> EvaluationRun:
        payload = {
            "run_id": self._string(row, "run_id"),
            "suite_id": self._string(row, "suite_id"),
            "suite_version_id": self._string(row, "suite_version_id"),
            "flow_id": self._string(row, "flow_id"),
            "flow_config_version": self._string(row, "flow_config_version"),
            "branch_id": self._string(row, "branch_id"),
            "trigger": self._string(row, "trigger"),
            "scope": _json_object(row["scope"], "evaluation_runs.scope"),
            "state": self._string(row, "state"),
            "idempotency_key": self._optional_string(row, "idempotency_key"),
            "taskiq_task_id": self._optional_string(row, "taskiq_task_id"),
            "gate_policy_id": self._optional_string(row, "gate_policy_id"),
            "gate_state": self._optional_string(row, "gate_state"),
            "total_cases": self._int(row, "total_cases"),
            "trials": self._int(row, "trials"),
            "max_concurrency": self._int(row, "max_concurrency"),
            "total_case_runs": self._int(row, "total_case_runs"),
            "passed_case_runs": self._int(row, "passed_case_runs"),
            "failed_case_runs": self._int(row, "failed_case_runs"),
            "error_case_runs": self._int(row, "error_case_runs"),
            "canceled_case_runs": self._int(row, "canceled_case_runs"),
            "average_score": self._optional_float(row, "average_score"),
            "average_duration_ms": self._optional_float(row, "average_duration_ms"),
            "input_tokens": self._int(row, "input_tokens"),
            "output_tokens": self._int(row, "output_tokens"),
            "total_tokens": self._int(row, "total_tokens"),
            "billing_quantity": self._int(row, "billing_quantity"),
            "started_at": self._optional_datetime(row, "started_at"),
            "finished_at": self._optional_datetime(row, "finished_at"),
            "created_at": self._datetime(row, "created_at"),
            "updated_at": self._datetime(row, "updated_at"),
        }
        return EvaluationRun.model_validate(payload)

    def _run_job_from_row(self, row: Mapping[str, EvaluationLabRowValue]) -> EvaluationRunJob:
        return EvaluationRunJob(
            run_job_id=self._string(row, "run_job_id"),
            run_id=self._string(row, "run_id"),
            taskiq_task_id=self._string(row, "taskiq_task_id"),
            state=EvaluationRunJobState(self._string(row, "state")),
            context_data=_json_object(row["context_data"], "evaluation_run_jobs.context_data"),
            trace_context=(
                None
                if row["trace_context"] is None
                else _json_object(row["trace_context"], "evaluation_run_jobs.trace_context")
            ),
            error=self._optional_string(row, "error"),
            enqueued_at=self._optional_datetime(row, "enqueued_at"),
            created_at=self._datetime(row, "created_at"),
            updated_at=self._datetime(row, "updated_at"),
        )

    def _case_run_from_row(self, row: Mapping[str, EvaluationLabRowValue]) -> EvaluationCaseRun:
        scores = None
        scores_raw = row["scores"]
        if scores_raw is not None:
            scores = _json_object(scores_raw, "evaluation_case_runs.scores")
        dialog_payload = row["dialog"]
        if dialog_payload is None:
            dialog: list[EvaluationDialogMessage] = []
        elif isinstance(dialog_payload, str):
            dialog = _EVALUATION_DIALOG_ADAPTER.validate_json(dialog_payload)
        else:
            dialog = _EVALUATION_DIALOG_ADAPTER.validate_python(dialog_payload)
        payload = {
            "case_run_id": self._string(row, "case_run_id"),
            "run_id": self._string(row, "run_id"),
            "case_id": self._string(row, "case_id"),
            "trial_index": self._int(row, "trial_index"),
            "suite_id": self._string(row, "suite_id"),
            "flow_id": self._string(row, "flow_id"),
            "branch_id": self._string(row, "branch_id"),
            "state": self._string(row, "state"),
            "task_id": self._optional_string(row, "task_id"),
            "context_id": self._optional_string(row, "context_id"),
            "session_id": self._optional_string(row, "session_id"),
            "trace_id": self._optional_string(row, "trace_id"),
            "duration_ms": self._optional_int(row, "duration_ms"),
            "input_tokens": self._int(row, "input_tokens"),
            "output_tokens": self._int(row, "output_tokens"),
            "total_tokens": self._int(row, "total_tokens"),
            "billing_quantity": self._int(row, "billing_quantity"),
            "turns_count": self._int(row, "turns_count"),
            "scores": scores,
            "total_score": self._optional_float(row, "total_score"),
            "judge_feedback": self._optional_string(row, "judge_feedback"),
            "dialog": dialog,
            "error": self._optional_string(row, "error"),
            "started_at": self._optional_datetime(row, "started_at"),
            "finished_at": self._optional_datetime(row, "finished_at"),
            "created_at": self._datetime(row, "created_at"),
            "updated_at": self._datetime(row, "updated_at"),
        }
        return EvaluationCaseRun.model_validate(payload)

    def _baseline_from_row(self, row: Mapping[str, EvaluationLabRowValue]) -> EvaluationBaseline:
        return EvaluationBaseline(
            baseline_id=self._string(row, "baseline_id"),
            suite_id=self._string(row, "suite_id"),
            flow_id=self._string(row, "flow_id"),
            branch_id=self._string(row, "branch_id"),
            run_id=self._string(row, "run_id"),
            created_by=self._string(row, "created_by"),
            created_at=self._datetime(row, "created_at"),
            updated_at=self._datetime(row, "updated_at"),
        )

    def _gate_policy_from_row(
        self,
        row: Mapping[str, EvaluationLabRowValue],
    ) -> EvaluationGatePolicy:
        return EvaluationGatePolicy(
            gate_policy_id=self._string(row, "gate_policy_id"),
            suite_id=self._string(row, "suite_id"),
            flow_id=self._string(row, "flow_id"),
            branch_id=self._string(row, "branch_id"),
            name=self._string(row, "name"),
            min_pass_rate=self._float(row, "min_pass_rate"),
            min_average_score=self._optional_float(row, "min_average_score"),
            max_failed_case_runs=self._int(row, "max_failed_case_runs"),
            max_error_case_runs=self._int(row, "max_error_case_runs"),
            max_average_duration_ms=self._optional_int(row, "max_average_duration_ms"),
            require_baseline=self._bool(row, "require_baseline"),
            min_baseline_score_delta=self._optional_float(row, "min_baseline_score_delta"),
            max_baseline_duration_delta_ms=self._optional_int(
                row,
                "max_baseline_duration_delta_ms",
            ),
            archived_at=self._optional_datetime(row, "archived_at"),
            created_at=self._datetime(row, "created_at"),
            updated_at=self._datetime(row, "updated_at"),
        )

    def _gate_result_from_row(
        self,
        row: Mapping[str, EvaluationLabRowValue],
    ) -> EvaluationGateResult:
        violations_payload = row["violations"]
        if isinstance(violations_payload, str):
            violations = _STRING_LIST_ADAPTER.validate_json(violations_payload)
        else:
            violations = _STRING_LIST_ADAPTER.validate_python(violations_payload)
        return EvaluationGateResult(
            gate_result_id=self._string(row, "gate_result_id"),
            run_id=self._string(row, "run_id"),
            gate_policy_id=self._string(row, "gate_policy_id"),
            state=EvaluationGateState(self._string(row, "state")),
            metrics=_json_object(row["metrics"], "evaluation_gate_results.metrics"),
            violations=violations,
            created_at=self._datetime(row, "created_at"),
        )

    def _monitor_from_row(self, row: Mapping[str, EvaluationLabRowValue]) -> EvaluationMonitor:
        raw_filter = row["filter"]
        if isinstance(raw_filter, str):
            monitor_filter = _EVALUATION_MONITOR_FILTER_ADAPTER.validate_json(raw_filter)
        else:
            monitor_filter = _EVALUATION_MONITOR_FILTER_ADAPTER.validate_python(raw_filter)
        return EvaluationMonitor(
            monitor_id=self._string(row, "monitor_id"),
            suite_id=self._string(row, "suite_id"),
            flow_id=self._string(row, "flow_id"),
            branch_id=self._string(row, "branch_id"),
            name=self._string(row, "name"),
            description=self._string(row, "description"),
            state=EvaluationMonitorState(self._string(row, "state")),
            sampling_rate=self._float(row, "sampling_rate"),
            max_traces_per_sample=self._int(row, "max_traces_per_sample"),
            filter=monitor_filter,
            gate_policy_id=self._optional_string(row, "gate_policy_id"),
            created_by=self._string(row, "created_by"),
            created_at=self._datetime(row, "created_at"),
            updated_at=self._datetime(row, "updated_at"),
        )

    def _monitor_observation_from_row(
        self,
        row: Mapping[str, EvaluationLabRowValue],
    ) -> EvaluationMonitorObservation:
        return EvaluationMonitorObservation(
            observation_id=self._string(row, "observation_id"),
            monitor_id=self._string(row, "monitor_id"),
            suite_id=self._string(row, "suite_id"),
            flow_id=self._string(row, "flow_id"),
            branch_id=self._string(row, "branch_id"),
            trace_id=self._string(row, "trace_id"),
            task_id=self._optional_string(row, "task_id"),
            session_id=self._optional_string(row, "session_id"),
            state=EvaluationMonitorObservationState(self._string(row, "state")),
            span_count=self._int(row, "span_count"),
            payload=_json_object(row["payload"], "evaluation_monitor_observations.payload"),
            sampled_at=self._datetime(row, "sampled_at"),
            curated_case_id=self._optional_string(row, "curated_case_id"),
        )

    def _event_from_row(self, row: Mapping[str, EvaluationLabRowValue]) -> EvaluationRunEvent:
        return EvaluationRunEvent(
            event_id=self._string(row, "event_id"),
            run_id=self._string(row, "run_id"),
            case_run_id=self._optional_string(row, "case_run_id"),
            sequence=self._int(row, "sequence"),
            event_type=EvaluationEventType(self._string(row, "event_type")),
            payload=_json_object(row["payload"], "evaluation_run_events.payload"),
            created_at=self._datetime(row, "created_at"),
        )

    def _pairwise_judgment_from_row(
        self,
        row: Mapping[str, EvaluationLabRowValue],
    ) -> EvaluationPairwiseJudgment:
        raw_scores = row["scores"]
        if isinstance(raw_scores, str):
            scores = _EVALUATION_SCORES_ADAPTER.validate_json(raw_scores)
        else:
            scores = _EVALUATION_SCORES_ADAPTER.validate_python(raw_scores)
        return EvaluationPairwiseJudgment(
            pairwise_judgment_id=self._string(row, "pairwise_judgment_id"),
            suite_id=self._string(row, "suite_id"),
            flow_id=self._string(row, "flow_id"),
            branch_id=self._string(row, "branch_id"),
            left_run_id=self._string(row, "left_run_id"),
            right_run_id=self._string(row, "right_run_id"),
            left_case_run_id=self._string(row, "left_case_run_id"),
            right_case_run_id=self._string(row, "right_case_run_id"),
            mode=EvaluationPairwiseJudgeMode(self._string(row, "mode")),
            preferred=EvaluationPairwisePreference(self._string(row, "preferred")),
            rubric_version_id=self._optional_string(row, "rubric_version_id"),
            scores=scores,
            feedback=self._string(row, "feedback"),
            created_by=self._string(row, "created_by"),
            created_at=self._datetime(row, "created_at"),
        )

    def _annotation_from_row(
        self,
        row: Mapping[str, EvaluationLabRowValue],
    ) -> EvaluationAnnotation:
        return EvaluationAnnotation(
            annotation_id=self._string(row, "annotation_id"),
            run_id=self._string(row, "run_id"),
            case_run_id=self._optional_string(row, "case_run_id"),
            case_id=self._optional_string(row, "case_id"),
            annotation_type=EvaluationAnnotationType(self._string(row, "annotation_type")),
            comment=self._string(row, "comment"),
            payload=_json_object(row["payload"], "evaluation_annotations.payload"),
            created_by=self._string(row, "created_by"),
            created_at=self._datetime(row, "created_at"),
            updated_at=self._datetime(row, "updated_at"),
        )

    def _run_params(self, run: EvaluationRun, company_id: str) -> dict[str, SqlParameterValue]:
        return {
            "run_id": run.run_id,
            "suite_id": run.suite_id,
            "suite_version_id": run.suite_version_id,
            "company_id": company_id,
            "flow_id": run.flow_id,
            "flow_config_version": run.flow_config_version,
            "branch_id": run.branch_id,
            "trigger": str(run.trigger),
            "scope": _json_payload(
                require_json_object(run.scope.model_dump(mode="json"), "EvaluationRun.scope")
            ),
            "state": str(run.state),
            "idempotency_key": run.idempotency_key,
            "taskiq_task_id": run.taskiq_task_id,
            "gate_policy_id": run.gate_policy_id,
            "gate_state": str(run.gate_state) if run.gate_state is not None else None,
            "total_cases": run.total_cases,
            "trials": run.trials,
            "max_concurrency": run.max_concurrency,
            "total_case_runs": run.total_case_runs,
            "passed_case_runs": run.passed_case_runs,
            "failed_case_runs": run.failed_case_runs,
            "error_case_runs": run.error_case_runs,
            "canceled_case_runs": run.canceled_case_runs,
            "average_score": run.average_score,
            "average_duration_ms": run.average_duration_ms,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "total_tokens": run.total_tokens,
            "billing_quantity": run.billing_quantity,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }

    def _run_job_params(
        self,
        job: EvaluationRunJob,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "run_job_id": job.run_job_id,
            "run_id": job.run_id,
            "company_id": company_id,
            "taskiq_task_id": job.taskiq_task_id,
            "state": str(job.state),
            "context_data": _json_payload(job.context_data),
            "trace_context": _json_payload(job.trace_context) if job.trace_context is not None else None,
            "error": job.error,
            "enqueued_at": job.enqueued_at,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    def _rubric_version_params(
        self,
        version: EvaluationRubricVersion,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "rubric_version_id": version.rubric_version_id,
            "rubric_id": version.rubric_id,
            "company_id": company_id,
            "flow_id": version.flow_id,
            "version": version.version,
            "prompt": version.prompt,
            "pass_threshold": version.pass_threshold,
            "created_at": version.created_at,
        }

    def _baseline_params(
        self,
        baseline: EvaluationBaseline,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "baseline_id": baseline.baseline_id,
            "suite_id": baseline.suite_id,
            "company_id": company_id,
            "flow_id": baseline.flow_id,
            "branch_id": baseline.branch_id,
            "run_id": baseline.run_id,
            "created_by": baseline.created_by,
            "created_at": baseline.created_at,
            "updated_at": baseline.updated_at,
        }

    def _gate_policy_params(
        self,
        policy: EvaluationGatePolicy,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "gate_policy_id": policy.gate_policy_id,
            "suite_id": policy.suite_id,
            "company_id": company_id,
            "flow_id": policy.flow_id,
            "branch_id": policy.branch_id,
            "name": policy.name,
            "min_pass_rate": policy.min_pass_rate,
            "min_average_score": policy.min_average_score,
            "max_failed_case_runs": policy.max_failed_case_runs,
            "max_error_case_runs": policy.max_error_case_runs,
            "max_average_duration_ms": policy.max_average_duration_ms,
            "require_baseline": policy.require_baseline,
            "min_baseline_score_delta": policy.min_baseline_score_delta,
            "max_baseline_duration_delta_ms": policy.max_baseline_duration_delta_ms,
            "archived_at": policy.archived_at,
            "created_at": policy.created_at,
            "updated_at": policy.updated_at,
        }

    def _monitor_params(
        self,
        monitor: EvaluationMonitor,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "monitor_id": monitor.monitor_id,
            "suite_id": monitor.suite_id,
            "company_id": company_id,
            "flow_id": monitor.flow_id,
            "branch_id": monitor.branch_id,
            "name": monitor.name,
            "description": monitor.description,
            "state": str(monitor.state),
            "sampling_rate": monitor.sampling_rate,
            "max_traces_per_sample": monitor.max_traces_per_sample,
            "filter": _json_payload(
                require_json_object(
                    monitor.filter.model_dump(mode="json", exclude_none=True),
                    "EvaluationMonitor.filter",
                )
            ),
            "gate_policy_id": monitor.gate_policy_id,
            "created_by": monitor.created_by,
            "created_at": monitor.created_at,
            "updated_at": monitor.updated_at,
        }

    def _monitor_observation_params(
        self,
        observation: EvaluationMonitorObservation,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "observation_id": observation.observation_id,
            "monitor_id": observation.monitor_id,
            "suite_id": observation.suite_id,
            "company_id": company_id,
            "flow_id": observation.flow_id,
            "branch_id": observation.branch_id,
            "trace_id": observation.trace_id,
            "task_id": observation.task_id,
            "session_id": observation.session_id,
            "state": str(observation.state),
            "span_count": observation.span_count,
            "payload": _json_payload(observation.payload),
            "sampled_at": observation.sampled_at,
            "curated_case_id": observation.curated_case_id,
        }

    def _gate_result_params(
        self,
        result: EvaluationGateResult,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "gate_result_id": result.gate_result_id,
            "run_id": result.run_id,
            "gate_policy_id": result.gate_policy_id,
            "company_id": company_id,
            "state": str(result.state),
            "metrics": _json_payload(result.metrics),
            "violations": _json_payload(result.violations),
            "created_at": result.created_at,
        }

    def _annotation_params(
        self,
        annotation: EvaluationAnnotation,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "annotation_id": annotation.annotation_id,
            "run_id": annotation.run_id,
            "case_run_id": annotation.case_run_id,
            "company_id": company_id,
            "case_id": annotation.case_id,
            "annotation_type": str(annotation.annotation_type),
            "comment": annotation.comment,
            "payload": _json_payload(annotation.payload),
            "created_by": annotation.created_by,
            "created_at": annotation.created_at,
            "updated_at": annotation.updated_at,
        }

    def _pairwise_judgment_params(
        self,
        judgment: EvaluationPairwiseJudgment,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "pairwise_judgment_id": judgment.pairwise_judgment_id,
            "company_id": company_id,
            "suite_id": judgment.suite_id,
            "flow_id": judgment.flow_id,
            "branch_id": judgment.branch_id,
            "left_run_id": judgment.left_run_id,
            "right_run_id": judgment.right_run_id,
            "left_case_run_id": judgment.left_case_run_id,
            "right_case_run_id": judgment.right_case_run_id,
            "mode": str(judgment.mode),
            "preferred": str(judgment.preferred),
            "rubric_version_id": judgment.rubric_version_id,
            "scores": _json_payload(judgment.scores),
            "feedback": judgment.feedback,
            "created_by": judgment.created_by,
            "created_at": judgment.created_at,
        }

    def _case_run_params(
        self,
        case_run: EvaluationCaseRun,
        company_id: str,
    ) -> dict[str, SqlParameterValue]:
        return {
            "case_run_id": case_run.case_run_id,
            "run_id": case_run.run_id,
            "case_id": case_run.case_id,
            "trial_index": case_run.trial_index,
            "suite_id": case_run.suite_id,
            "company_id": company_id,
            "flow_id": case_run.flow_id,
            "branch_id": case_run.branch_id,
            "state": str(case_run.state),
            "task_id": case_run.task_id,
            "context_id": case_run.context_id,
            "session_id": case_run.session_id,
            "trace_id": case_run.trace_id,
            "duration_ms": case_run.duration_ms,
            "input_tokens": case_run.input_tokens,
            "output_tokens": case_run.output_tokens,
            "total_tokens": case_run.total_tokens,
            "billing_quantity": case_run.billing_quantity,
            "turns_count": case_run.turns_count,
            "scores": _json_payload(case_run.scores) if case_run.scores is not None else None,
            "total_score": case_run.total_score,
            "judge_feedback": case_run.judge_feedback,
            "dialog": _json_payload(
                [
                    require_json_object(
                        message.model_dump(mode="json"),
                        "EvaluationCaseRun.dialog[]",
                    )
                    for message in case_run.dialog
                ]
            ),
            "error": case_run.error,
            "started_at": case_run.started_at,
            "finished_at": case_run.finished_at,
            "created_at": case_run.created_at,
            "updated_at": case_run.updated_at,
        }

    def _json_list_strings(self, value: EvaluationLabRowValue, field_name: str) -> list[str]:
        if isinstance(value, str):
            return _STRING_LIST_ADAPTER.validate_json(value)
        try:
            return _STRING_LIST_ADAPTER.validate_python(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} must contain only strings") from exc

    def _string(self, row: Mapping[str, EvaluationLabRowValue], key: str) -> str:
        value = row[key]
        if not isinstance(value, str):
            raise ValueError(f"evaluation row field {key} must be a string")
        return value

    def _optional_string(self, row: Mapping[str, EvaluationLabRowValue], key: str) -> str | None:
        value = row[key]
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"evaluation row field {key} must be a string or null")
        return value

    def _int(self, row: Mapping[str, EvaluationLabRowValue], key: str) -> int:
        value = row[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"evaluation row field {key} must be an int")
        return value

    def _optional_int(self, row: Mapping[str, EvaluationLabRowValue], key: str) -> int | None:
        value = row[key]
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"evaluation row field {key} must be an int or null")
        return value

    def _optional_float(self, row: Mapping[str, EvaluationLabRowValue], key: str) -> float | None:
        value = row[key]
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"evaluation row field {key} must be a number or null")
        return float(value)

    def _float(self, row: Mapping[str, EvaluationLabRowValue], key: str) -> float:
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"evaluation row field {key} must be a number")
        return float(value)

    def _bool(self, row: Mapping[str, EvaluationLabRowValue], key: str) -> bool:
        value = row[key]
        if not isinstance(value, bool):
            raise ValueError(f"evaluation row field {key} must be a bool")
        return value

    def _datetime(self, row: Mapping[str, EvaluationLabRowValue], key: str) -> datetime:
        value = row[key]
        if not isinstance(value, datetime):
            raise ValueError(f"evaluation row field {key} must be a datetime")
        return value

    def _optional_datetime(
        self,
        row: Mapping[str, EvaluationLabRowValue],
        key: str,
    ) -> datetime | None:
        value = row[key]
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise ValueError(f"evaluation row field {key} must be a datetime or null")
        return value
