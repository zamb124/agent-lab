"""
Сервис оценки агентов/skills.

Оркестрирует запуск тест-кейсов и сохранение результатов.
"""

from datetime import date, datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from apps.agents.src.container import get_container
from apps.agents.src.db import EvaluationRepository
from core.logging import get_logger
from apps.agents.src.models import (
    EvaluationResult,
    EvaluationRunSummary,
    TestCaseConfig,
)

from .runners import DialogTestRunner

logger = get_logger(__name__)


class EvaluationService:
    """Сервис для запуска и управления оценкой агентов/skills."""

    def __init__(self, evaluation_repository: EvaluationRepository):
        self._repository = evaluation_repository

    async def get_test_cases(
        self,
        agent_id: str,
        skill_id: str,
    ) -> Dict[str, TestCaseConfig]:
        """
        Получает тест-кейсы для skill.

        Фильтрует по skill_ids: включает тесты где skill_id в списке или "*".

        Args:
            agent_id: ID агента
            skill_id: ID skill

        Returns:
            Словарь {test_case_id: config}
        """
        container = get_container()
        agent_config = await container.agent_repository.get(agent_id)

        if not agent_config or not agent_config.evaluation:
            return {}

        result = {}
        for test_id, test_case in agent_config.evaluation.items():
            skill_ids = test_case.skill_ids

            # "*" - для всех skills
            if skill_ids == "*":
                result[test_id] = test_case
            # Список - проверяем вхождение
            elif isinstance(skill_ids, list) and skill_id in skill_ids:
                result[test_id] = test_case

        return result

    async def run_test(
        self,
        agent_id: str,
        skill_id: str,
        test_case_id: str,
    ) -> EvaluationResult:
        """
        Запускает один тест-кейс.

        Args:
            agent_id: ID агента
            skill_id: ID skill
            test_case_id: ID тест-кейса

        Returns:
            Результат выполнения
        """
        test_cases = await self.get_test_cases(agent_id, skill_id)

        if test_case_id not in test_cases:
            raise ValueError(f"Test case not found: {test_case_id}")

        test_case = test_cases[test_case_id]

        run_date = date.today()
        iteration = await self._repository.get_next_iteration(agent_id, skill_id, run_date)

        runner = self._create_runner(agent_id, skill_id, run_date, iteration, test_case)
        result = await runner.run(test_case, test_case_id)

        await self._repository.save(result)

        logger.info(
            f"Test {test_case_id} completed: {result.status} (duration={result.duration_ms}ms)"
        )

        return result

    async def run_all_tests(
        self,
        agent_id: str,
        skill_id: str,
    ) -> EvaluationRunSummary:
        """
        Запускает все тест-кейсы для skill.

        Args:
            agent_id: ID агента
            skill_id: ID skill

        Returns:
            Сводка по запуску
        """

        test_cases = await self.get_test_cases(agent_id, skill_id)

        if not test_cases:
            raise ValueError(f"No test cases found for {agent_id}/{skill_id}")

        run_date = date.today()
        iteration = await self._repository.get_next_iteration(agent_id, skill_id, run_date)

        summary = EvaluationRunSummary(
            agent_id=agent_id,
            skill_id=skill_id,
            run_date=run_date,
            iteration=iteration,
            started_at=datetime.now(timezone.utc),
            total_tests=len(test_cases),
        )

        total_scores: List[float] = []

        for test_case_id, test_case in test_cases.items():
            runner = self._create_runner(agent_id, skill_id, run_date, iteration, test_case)

            result = await runner.run(test_case, test_case_id)
            await self._repository.save(result)

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
            f"status={summary.status}"
        )

        return summary

    async def run_test_stream(
        self,
        agent_id: str,
        skill_id: str,
        test_case_id: str,
        task_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Запускает один тест со streaming результатов.

        Args:
            task_id: ID задачи для трейсинга (если не указан, генерируется автоматически)

        Yields:
            События в реальном времени:
            - {"type": "start", "test_case_id": ...}
            - {"type": "user", "content": ...} - сразу при отправке
            - {"type": "assistant", "content": ...} - когда получен ответ
            - {"type": "result", "status": ..., "duration_ms": ..., ...}
            - {"type": "error", "message": ...}
        """
        test_cases = await self.get_test_cases(agent_id, skill_id)

        if test_case_id not in test_cases:
            yield {"type": "error", "message": f"Test case not found: {test_case_id}"}
            return

        test_case = test_cases[test_case_id]

        run_date = date.today()
        iteration = await self._repository.get_next_iteration(agent_id, skill_id, run_date)

        yield {
            "type": "start",
            "test_case_id": test_case_id,
            "name": test_case.name,
        }

        runner = self._create_runner(agent_id, skill_id, run_date, iteration, test_case)

        # Собираем диалог для сохранения
        dialog = []
        result_event = None

        async for event in runner.run(test_case, test_case_id, task_id=task_id):
            if event["type"] == "user":
                dialog.append({"role": "user", "content": event["content"]})
                yield event
            elif event["type"] == "assistant":
                dialog.append({"role": "assistant", "content": event["content"]})
                yield event
            elif event["type"] == "result":
                result_event = event
                yield event

        # Сохраняем результат в БД
        if result_event:
            # Для agent тестов диалог передается в событии result
            saved_dialog = result_event.get("dialog", dialog)
            result = EvaluationResult(
                agent_id=agent_id,
                skill_id=skill_id,
                run_date=run_date,
                iteration=iteration,
                test_case_id=test_case_id,
                task_id=result_event.get("task_id"),
                status=result_event.get("status", "error"),
                duration_ms=result_event.get("duration_ms", 0),
                turns_count=result_event.get("turns_count", len(saved_dialog) // 2),
                dialog=saved_dialog,
                scores=result_event.get("scores"),
                judge_feedback=result_event.get("judge_feedback"),
                error=result_event.get("error"),
            )
            await self._repository.save(result)

    async def run_all_tests_stream(
        self,
        agent_id: str,
        skill_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Запускает все тесты со streaming результатов.

        Yields:
            События: run_start, test_start, dialog, test_result, summary
        """
        test_cases = await self.get_test_cases(agent_id, skill_id)

        if not test_cases:
            yield {"type": "error", "message": f"No test cases found for {agent_id}/{skill_id}"}
            return

        run_date = date.today()
        iteration = await self._repository.get_next_iteration(agent_id, skill_id, run_date)

        yield {
            "type": "run_start",
            "agent_id": agent_id,
            "skill_id": skill_id,
            "run_date": run_date.isoformat(),
            "iteration": iteration,
            "total_tests": len(test_cases),
        }

        passed = 0
        failed = 0
        errors = 0
        total_scores: List[float] = []

        for test_case_id, test_case in test_cases.items():
            yield {
                "type": "test_start",
                "test_case_id": test_case_id,
                "name": test_case.name,
            }

            runner = self._create_runner(agent_id, skill_id, run_date, iteration, test_case)

            result = await runner.run(test_case, test_case_id)
            await self._repository.save(result)

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
        agent_id: str,
        skill_id: str,
        run_date: Optional[date] = None,
        iteration: Optional[int] = None,
        limit: int = 10,
    ) -> List[EvaluationResult]:
        """
        Получает результаты оценки.

        Args:
            agent_id: ID агента
            skill_id: ID skill
            run_date: Дата запуска (если указана с iteration - конкретный запуск)
            iteration: Номер итерации
            limit: Максимум записей

        Returns:
            Список результатов
        """
        if run_date and iteration is not None:
            return await self._repository.get_by_run(agent_id, skill_id, run_date, iteration)

        return await self._repository.get_latest_results(agent_id, skill_id, limit)

    def _create_runner(
        self,
        agent_id: str,
        skill_id: str,
        run_date: date,
        iteration: int,
        test_case: TestCaseConfig,
    ):
        """Создаёт runner для теста."""
        return DialogTestRunner(agent_id, skill_id, run_date, iteration)
