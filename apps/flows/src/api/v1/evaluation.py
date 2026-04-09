"""
API для получения результатов evaluation.

Запуск тестов - через A2A с metadata.evaluation.test_case_id.
Получение результатов - через этот API.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Query

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import EvaluationResult

router = APIRouter(tags=["evaluation"])


@router.get("/results", response_model=List[EvaluationResult])
async def get_evaluation_results(
    container: ContainerDep,
    flow_id: str = Query(..., description="ID агента"),
    skill_id: str = Query("default", description="ID skill"),
    run_date: Optional[date] = Query(None, description="Дата запуска (по умолчанию сегодня)"),
    limit: int = Query(50, ge=1, le=500, description="Лимит результатов"),
) -> List[EvaluationResult]:
    """
    Получение результатов evaluation.

    Возвращает последние результаты тестов для указанного агента/skill.
    """

    if run_date:
        results = await container.evaluation_repository.get_by_run(
            flow_id=flow_id,
            skill_id=skill_id,
            run_date=run_date,
        )
    else:
        results = await container.evaluation_repository.get_latest_results(
            flow_id=flow_id,
            skill_id=skill_id,
            limit=limit,
        )

    return results


@router.get("/results/summary")
async def get_evaluation_summary(
    container: ContainerDep,
    flow_id: str = Query(..., description="ID агента"),
    skill_id: str = Query("default", description="ID skill"),
    run_date: Optional[date] = Query(None, description="Дата запуска"),
):
    """
    Получение сводки по результатам evaluation.

    Возвращает статистику: всего тестов, пройдено, провалено, ошибки.
    """

    if run_date:
        results = await container.evaluation_repository.get_by_run(
            flow_id=flow_id,
            skill_id=skill_id,
            run_date=run_date,
        )
    else:
        results = await container.evaluation_repository.get_latest_results(
            flow_id=flow_id,
            skill_id=skill_id,
            limit=500,
        )

    # Считаем статистику
    total = len(results)
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    errors = sum(1 for r in results if r.status == "error")

    avg_duration = 0
    if total > 0:
        avg_duration = sum(r.duration_ms for r in results) // total

    avg_score = None
    total_scores = [r.get_total_score() for r in results if r.get_total_score() is not None]
    if total_scores:
        avg_score = sum(total_scores) / len(total_scores)

    return {
        "flow_id": flow_id,
        "skill_id": skill_id,
        "run_date": run_date or date.today().isoformat(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "pass_rate": (passed / total * 100) if total > 0 else 0,
        "avg_duration_ms": avg_duration,
        "avg_score": avg_score,
        "results": [
            {
                "test_case_id": r.test_case_id,
                "task_id": r.task_id,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "scores": r.scores,
                "total_score": r.get_total_score(),
                "error": r.error,
            }
            for r in results
        ],
    }


@router.get("/results/{test_case_id}")
async def get_test_result(
    test_case_id: str,
    container: ContainerDep,
    flow_id: str = Query(..., description="ID агента"),
    skill_id: str = Query("default", description="ID skill"),
    run_date: Optional[date] = Query(None, description="Дата запуска"),
) -> Optional[EvaluationResult]:
    """
    Получение результата конкретного теста.

    Возвращает последний результат для указанного тест-кейса.
    """

    if run_date:
        results = await container.evaluation_repository.get_by_run(
            flow_id=flow_id,
            skill_id=skill_id,
            run_date=run_date,
        )
    else:
        results = await container.evaluation_repository.get_latest_results(
            flow_id=flow_id,
            skill_id=skill_id,
            limit=100,
        )

    for r in results:
        if r.test_case_id == test_case_id:
            return r

    return None


@router.delete("/results")
async def delete_old_results(
    container: ContainerDep,
    days: int = Query(30, ge=1, le=365, description="Удалить результаты старше N дней"),
):
    """
    Удаление старых результатов evaluation.
    """

    deleted = await container.evaluation_repository.delete_old_results(
        days_to_keep=days,
    )

    return {"deleted": deleted}
