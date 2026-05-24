"""
Сервис оценки агентов/нод.

Оркестрирует запуск тест-кейсов и сохранение результатов.
Поддерживает тестирование агентов и отдельных нод через TestTarget.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date, datetime, timezone

from apps.flows.src.db import EvaluationRepository, FlowRepository, NodeRepository
from apps.flows.src.models import TestCaseConfig
from apps.flows.src.models.enums import NodeType, TestTargetType
from apps.flows.src.models.evaluation_result import (
    EvaluationAllTestsStreamEvent,
    EvaluationDialogMessage,
    EvaluationResult,
    EvaluationResultEvent,
    EvaluationRunSummary,
    EvaluationServiceStreamEvent,
)
from apps.flows.src.models.flow_config import TestTarget
from apps.flows.src.registry.nodes import NodeRegistry
from apps.flows.src.services.flow_factory import FlowFactory
from apps.flows.src.tools.registry import ToolRegistry
from core.logging import get_logger
from core.state import ExecutionState

from .runners import TestRunner

logger = get_logger(__name__)


class EvaluationService:
    """Сервис для запуска и управления оценкой агентов/нод."""

    def __init__(
        self,
        evaluation_repository: EvaluationRepository,
        *,
        flow_repository: FlowRepository,
        flow_factory: FlowFactory,
        node_registry: NodeRegistry,
        node_repository: NodeRepository,
        tool_registry: ToolRegistry,
    ):
        self._repository: EvaluationRepository = evaluation_repository
        self._flow_repository: FlowRepository = flow_repository
        self._flow_factory: FlowFactory = flow_factory
        self._node_registry: NodeRegistry = node_registry
        self._node_repository: NodeRepository = node_repository
        self._tool_registry: ToolRegistry = tool_registry

    async def get_test_cases(
        self,
        flow_id: str,
        branch_id: str,
    ) -> dict[str, TestCaseConfig]:
        """
        Получает тест-кейсы для ветки.

        Фильтрует по branch_ids: включает тесты где branch_id в списке или "*".

        Args:
            flow_id: ID агента
            branch_id: ID ветки

        Returns:
            Словарь {test_case_id: config}
        """
        flow_config = await self._flow_repository.get(flow_id)

        if not flow_config or not flow_config.evaluation:
            return {}

        result: dict[str, TestCaseConfig] = {}
        for test_id, test_case in flow_config.evaluation.items():
            branch_ids = test_case.branch_ids

            if branch_ids == "*":
                result[test_id] = test_case
            elif branch_id in branch_ids:
                result[test_id] = test_case

        return result

    async def run_test(
        self,
        flow_id: str,
        branch_id: str,
        test_case_id: str,
    ) -> EvaluationResult:
        """
        Запускает один тест-кейс.

        Args:
            flow_id: ID агента
            branch_id: ID ветки
            test_case_id: ID тест-кейса

        Returns:
            Результат выполнения
        """
        test_cases = await self.get_test_cases(flow_id, branch_id)

        if test_case_id not in test_cases:
            raise ValueError(f"Test case not found: {test_case_id}")

        test_case = test_cases[test_case_id]

        run_date = date.today()
        iteration = await self._repository.get_next_iteration(flow_id, branch_id, run_date)

        runner = await self._create_runner(flow_id, branch_id, run_date, iteration, test_case)

        # Собираем результат из стриминга
        result_event: EvaluationResultEvent | None = None
        dialog: list[EvaluationDialogMessage] = []
        async for event in runner.run(test_case, test_case_id):
            if event["type"] == "user":
                dialog.append(EvaluationDialogMessage(role="user", content=event["content"]))
            elif event["type"] == "assistant":
                dialog.append(EvaluationDialogMessage(role="assistant", content=event["content"]))
            elif event["type"] == "result":
                result_event = event

        if not result_event:
            raise RuntimeError(f"Test {test_case_id} did not produce a result event")

        saved_dialog = result_event["dialog"] if "dialog" in result_event else dialog
        result = EvaluationResult(
            flow_id=flow_id,
            branch_id=branch_id,
            run_date=run_date,
            iteration=iteration,
            test_case_id=test_case_id,
            task_id=result_event["task_id"],
            status=result_event["status"],
            duration_ms=result_event["duration_ms"],
            turns_count=result_event["turns_count"] if "turns_count" in result_event else len(saved_dialog) // 2,
            dialog=saved_dialog,
            scores=result_event["scores"] if "scores" in result_event else None,
            judge_feedback=result_event["judge_feedback"] if "judge_feedback" in result_event else None,
            error=result_event["error"] if "error" in result_event else None,
        )

        _ = await self._repository.save(result)

        logger.info(
            f"Test {test_case_id} completed: {result.status} (duration={result.duration_ms}ms)"
        )

        return result

    async def run_all_tests(
        self,
        flow_id: str,
        branch_id: str,
    ) -> EvaluationRunSummary:
        """
        Запускает все тест-кейсы для ветки.

        Args:
            flow_id: ID агента
            branch_id: ID ветки

        Returns:
            Сводка по запуску
        """
        test_cases = await self.get_test_cases(flow_id, branch_id)

        if not test_cases:
            raise ValueError(f"No test cases found for {flow_id}/{branch_id}")

        run_date = date.today()
        iteration = await self._repository.get_next_iteration(flow_id, branch_id, run_date)

        summary = EvaluationRunSummary(
            flow_id=flow_id,
            branch_id=branch_id,
            run_date=run_date,
            iteration=iteration,
            started_at=datetime.now(timezone.utc),
            total_tests=len(test_cases),
        )

        total_scores: list[float] = []

        for test_case_id, test_case in test_cases.items():
            runner = await self._create_runner(flow_id, branch_id, run_date, iteration, test_case)

            # Собираем результат из стриминга
            result_event: EvaluationResultEvent | None = None
            dialog: list[EvaluationDialogMessage] = []
            async for event in runner.run(test_case, test_case_id):
                if event["type"] == "user":
                    dialog.append(EvaluationDialogMessage(role="user", content=event["content"]))
                elif event["type"] == "assistant":
                    dialog.append(EvaluationDialogMessage(role="assistant", content=event["content"]))
                elif event["type"] == "result":
                    result_event = event

            if not result_event:
                summary.error_tests += 1
                continue

            saved_dialog = result_event["dialog"] if "dialog" in result_event else dialog
            result = EvaluationResult(
                flow_id=flow_id,
                branch_id=branch_id,
                run_date=run_date,
                iteration=iteration,
                test_case_id=test_case_id,
                task_id=result_event["task_id"],
                status=result_event["status"],
                duration_ms=result_event["duration_ms"],
                turns_count=result_event["turns_count"] if "turns_count" in result_event else len(saved_dialog) // 2,
                dialog=saved_dialog,
                scores=result_event["scores"] if "scores" in result_event else None,
                judge_feedback=result_event["judge_feedback"] if "judge_feedback" in result_event else None,
                error=result_event["error"] if "error" in result_event else None,
            )
            _ = await self._repository.save(result)

            if result.status == "passed":
                summary.passed_tests += 1
            elif result.status == "failed":
                summary.failed_tests += 1
            else:
                summary.error_tests += 1

            total_score = result.get_total_score()
            if total_score is not None:
                total_scores.append(total_score)

        summary.finished_at = datetime.now(timezone.utc)

        if total_scores:
            summary.average_score = sum(total_scores) / len(total_scores)

        if summary.error_tests > 0:
            summary.status = "error"
        elif summary.failed_tests == 0:
            summary.status = "passed"
        elif summary.passed_tests == 0:
            summary.status = "failed"
        else:
            summary.status = "partial"

        logger.info(
            f"Evaluation completed: {summary.passed_tests}/{summary.total_tests} passed, "
            + f"status={summary.status}"
        )

        return summary

    async def run_test_stream(
        self,
        flow_id: str,
        branch_id: str,
        test_case_id: str,
        task_id: str | None = None,
    ) -> AsyncIterator[EvaluationServiceStreamEvent]:
        """
        Запускает один тест со streaming результатов.

        Yields:
            События в реальном времени:
            - {"type": "start", "test_case_id": ...}
            - {"type": "user", "content": ...}
            - {"type": "assistant", "content": ...}
            - {"type": "result", "status": ..., "duration_ms": ..., ...}
            - {"type": "error", "message": ...}
        """
        test_cases = await self.get_test_cases(flow_id, branch_id)

        if test_case_id not in test_cases:
            yield {"type": "error", "message": f"Test case not found: {test_case_id}"}
            return

        test_case = test_cases[test_case_id]

        run_date = date.today()
        iteration = await self._repository.get_next_iteration(flow_id, branch_id, run_date)

        yield {
            "type": "start",
            "test_case_id": test_case_id,
            "name": test_case.name,
        }

        runner = await self._create_runner(flow_id, branch_id, run_date, iteration, test_case)

        dialog: list[EvaluationDialogMessage] = []
        result_event: EvaluationResultEvent | None = None

        async for event in runner.run(test_case, test_case_id, task_id=task_id):
            if event["type"] == "user":
                dialog.append(EvaluationDialogMessage(role="user", content=event["content"]))
                yield event
            elif event["type"] == "assistant":
                dialog.append(EvaluationDialogMessage(role="assistant", content=event["content"]))
                yield event
            elif event["type"] == "result":
                result_event = event
                yield event

        # Сохраняем результат в БД
        if result_event:
            saved_dialog = result_event["dialog"] if "dialog" in result_event else dialog
            result = EvaluationResult(
                flow_id=flow_id,
                branch_id=branch_id,
                run_date=run_date,
                iteration=iteration,
                test_case_id=test_case_id,
                task_id=result_event["task_id"],
                status=result_event["status"],
                duration_ms=result_event["duration_ms"],
                turns_count=result_event["turns_count"] if "turns_count" in result_event else len(saved_dialog) // 2,
                dialog=saved_dialog,
                scores=result_event["scores"] if "scores" in result_event else None,
                judge_feedback=result_event["judge_feedback"] if "judge_feedback" in result_event else None,
                error=result_event["error"] if "error" in result_event else None,
            )
            _ = await self._repository.save(result)

    async def run_all_tests_stream(
        self,
        flow_id: str,
        branch_id: str,
    ) -> AsyncIterator[EvaluationAllTestsStreamEvent]:
        """
        Запускает все тесты со streaming результатов.

        Yields:
            События: run_start, test_start, dialog, test_result, summary
        """
        test_cases = await self.get_test_cases(flow_id, branch_id)

        if not test_cases:
            yield {"type": "error", "message": f"No test cases found for {flow_id}/{branch_id}"}
            return

        run_date = date.today()
        iteration = await self._repository.get_next_iteration(flow_id, branch_id, run_date)

        yield {
            "type": "run_start",
            "flow_id": flow_id,
            "branch_id": branch_id,
            "run_date": run_date.isoformat(),
            "iteration": iteration,
            "total_tests": len(test_cases),
        }

        passed = 0
        failed = 0
        errors = 0
        total_scores: list[float] = []

        for test_case_id, test_case in test_cases.items():
            yield {
                "type": "test_start",
                "test_case_id": test_case_id,
                "name": test_case.name,
            }

            runner = await self._create_runner(flow_id, branch_id, run_date, iteration, test_case)

            result_event: EvaluationResultEvent | None = None
            dialog: list[EvaluationDialogMessage] = []
            async for event in runner.run(test_case, test_case_id):
                if event["type"] == "user":
                    dialog.append(EvaluationDialogMessage(role="user", content=event["content"]))
                elif event["type"] == "assistant":
                    dialog.append(EvaluationDialogMessage(role="assistant", content=event["content"]))
                elif event["type"] == "result":
                    result_event = event

            if not result_event:
                errors += 1
                yield {
                    "type": "test_result",
                    "test_case_id": test_case_id,
                    "status": "error",
                    "error": "No result event produced",
                }
                continue

            saved_dialog = result_event["dialog"] if "dialog" in result_event else dialog
            result = EvaluationResult(
                flow_id=flow_id,
                branch_id=branch_id,
                run_date=run_date,
                iteration=iteration,
                test_case_id=test_case_id,
                task_id=result_event["task_id"],
                status=result_event["status"],
                duration_ms=result_event["duration_ms"],
                turns_count=result_event["turns_count"] if "turns_count" in result_event else len(saved_dialog) // 2,
                dialog=saved_dialog,
                scores=result_event["scores"] if "scores" in result_event else None,
                judge_feedback=result_event["judge_feedback"] if "judge_feedback" in result_event else None,
                error=result_event["error"] if "error" in result_event else None,
            )
            _ = await self._repository.save(result)

            if result.status == "passed":
                passed += 1
            elif result.status == "failed":
                failed += 1
            else:
                errors += 1

            total_score = result.get_total_score()
            if total_score is not None:
                total_scores.append(total_score)

            yield {
                "type": "test_result",
                "test_case_id": test_case_id,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "dialog": result.dialog,
                "scores": result.scores,
                "total_score": total_score,
                "judge_feedback": result.judge_feedback,
                "error": result.error,
            }

        avg_score = sum(total_scores) / len(total_scores) if total_scores else None
        status = "passed" if failed == 0 and errors == 0 else "failed" if passed == 0 else "partial"

        yield {
            "type": "summary",
            "total_tests": len(test_cases),
            "passed_tests": passed,
            "failed_tests": failed,
            "error_tests": errors,
            "average_score": avg_score,
            "status": status,
        }

    async def get_results(
        self,
        flow_id: str,
        branch_id: str,
        run_date: date | None = None,
        iteration: int | None = None,
        limit: int = 10,
    ) -> list[EvaluationResult]:
        """
        Получает результаты оценки.

        Args:
            flow_id: ID агента
            branch_id: ID ветки
            run_date: Дата запуска (если указана с iteration - конкретный запуск)
            iteration: Номер итерации
            limit: Максимум записей

        Returns:
            Список результатов
        """
        if run_date and iteration is not None:
            return await self._repository.get_by_run(flow_id, branch_id, run_date, iteration)

        return await self._repository.get_latest_results(flow_id, branch_id, limit)

    # ========================================================================
    # Создание runner и target callable
    # ========================================================================

    async def _create_runner(
        self,
        flow_id: str,
        branch_id: str,
        run_date: date,
        iteration: int,
        test_case: TestCaseConfig,
    ) -> TestRunner:
        """Создает TestRunner с нужным target callable."""
        target_callable, target_id = await self._create_target_callable(
            test_case, flow_id, branch_id
        )
        return TestRunner(
            target_id,
            target_callable,
            run_date,
            iteration,
            flow_factory=self._flow_factory,
            node_repository=self._node_repository,
            tool_registry=self._tool_registry,
        )

    async def _create_target_callable(
        self,
        test_case: TestCaseConfig,
        flow_id: str,
        branch_id: str,
    ) -> tuple[Callable[[ExecutionState], Awaitable[ExecutionState]], str]:
        """
        Создает callable и target_id на основе target конфигурации.

        Returns:
            (callable, target_id)
        """
        target = test_case.target

        # target не указан — тестируем текущий flow
        if not target:
            callable_ = await self._create_flow_callable(flow_id, branch_id)
            return callable_, f"{flow_id}:{branch_id}"

        if target.type == TestTargetType.FLOW:
            target_flow_id = target.flow_id or flow_id
            target_branch_id = target.branch_id or branch_id
            callable_ = await self._create_flow_callable(target_flow_id, target_branch_id)
            return callable_, f"{target_flow_id}:{target_branch_id}"

        if target.type == TestTargetType.NODE:
            callable_ = self._create_node_callable(target)
            raw_node_id = target.node_config.get("node_id") if target.node_config else None
            node_id = raw_node_id if isinstance(raw_node_id, str) and raw_node_id else "inline_node"
            return callable_, f"node:{node_id}"

        raise ValueError(f"Unknown target type: {target.type}")

    async def _create_flow_callable(
        self, flow_id: str, branch_id: str
    ) -> Callable[[ExecutionState], Awaitable[ExecutionState]]:
        """Callable `run` для собранного flow (FlowFactory)."""
        runtime_flow = await self._flow_factory.get_flow(flow_id, branch_id)

        if not runtime_flow:
            raise ValueError(f"Flow not found: {flow_id}")

        return runtime_flow.run

    def _create_node_callable(
        self, target: TestTarget
    ) -> Callable[[ExecutionState], Awaitable[ExecutionState]]:
        """Создает callable для ноды из inline конфига."""
        if not target.node_config:
            raise ValueError("node_config is required for NODE target type")

        node_type = target.node_config.get("type")
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("node_config must contain 'type' field")

        node_type_enum = NodeType(node_type)

        node_class = self._node_registry.get(node_type_enum)
        raw_node_id = target.node_config.get("node_id")
        node_id = raw_node_id if isinstance(raw_node_id, str) and raw_node_id else "test_node"
        node = node_class.from_config(node_id, target.node_config)

        return node.run
