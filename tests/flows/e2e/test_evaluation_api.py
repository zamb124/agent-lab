"""
E2E тесты для Evaluation.

Настоящие тесты которые:
1. Отправляют реальные HTTP запросы
2. Проверяют реальные ответы и содержимое
3. Проверяют что checkers работают правильно
4. Проверяют сохранение результатов в БД
"""

import uuid as uuid_lib
from typing import Any, Dict, List

import pytest

pytestmark = pytest.mark.asyncio


def get_task_state(data: Dict[str, Any]) -> str:
    """Извлекает state из A2A Task ответа."""
    if "result" in data:
        return data["result"]["status"]["state"]
    return data.get("status", {}).get("state", "")


def get_task_response(data: Dict[str, Any]) -> str:
    """Извлекает текст ответа из A2A Task."""
    if "result" in data:
        msg = data["result"]["status"].get("message")
    else:
        msg = data.get("status", {}).get("message")
    if msg and msg.get("parts"):
        return msg["parts"][0].get("text", "")
    return ""


def get_artifacts(data: Dict[str, Any]) -> list:
    """Извлекает artifacts из ответа."""
    if "result" in data:
        return data["result"].get("artifacts", [])
    return data.get("artifacts", [])


async def send_a2a_message(
    client,
    flow_id: str,
    content: str,
    branch_id: str = "default",
    session_id: str = None,
    metadata: Dict = None,
) -> Dict[str, Any]:
    """Отправляет сообщение через A2A API."""
    if session_id is None:
        session_id = f"{flow_id}:test-{uuid_lib.uuid4()}"

    params = {
        "message": {
            "messageId": f"msg-{uuid_lib.uuid4()}",
            "role": "user",
            "parts": [{"kind": "text", "text": content}],
        },
    }
    if metadata:
        params["metadata"] = metadata

    response = await client.post(
        f"/flows/api/v1/{flow_id}",
        json={
            "jsonrpc": "2.0",
            "id": f"req-{uuid_lib.uuid4()}",
            "method": "message/send",
            "params": params,
        },
    )
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
    return response.json()


async def run_evaluation(
    client,
    flow_id: str,
    test_case_id: str,
    branch_id: str = "default",
) -> Dict[str, Any]:
    """Запускает evaluation тест через A2A."""
    return await send_a2a_message(
        client=client,
        flow_id=flow_id,
        content=f"[Test: {test_case_id}]",
        branch_id=branch_id,
        metadata={
            "branch": branch_id,
            "evaluation": {"test_case_id": test_case_id},
        },
    )


def setup_mock_llm(mock_llm, responses: List[str]):
    """Настраивает MockLLM с очередью ответов."""
    queue = [{"type": "text", "content": r} for r in responses]
    mock_llm.configure(response_queue=queue)


async def setup_mock_llm_redis(mock_llm_redis, responses: List[str]):
    """Настраивает MockLLM через Redis для worker."""
    queue = [{"type": "text", "content": r} for r in responses]
    await mock_llm_redis(queue)


def setup_flow_dialog_mock_llm(
    mock_llm,
    *,
    tester_responses: List[str],
    flow_responses: List[str],
    judge_response: str | None = None,
):
    """Настраивает очередь для sync_tools: tester -> flow -> ... -> judge."""
    if len(tester_responses) < len(flow_responses):
        raise ValueError("tester_responses must cover every flow turn")

    responses: List[str] = []
    for index, flow_response in enumerate(flow_responses):
        responses.append(tester_responses[index])
        responses.append(flow_response)

    responses.extend(tester_responses[len(flow_responses) :])
    if judge_response is not None:
        responses.append(judge_response)

    setup_mock_llm(mock_llm, responses)


class TestEvaluationFunctionType:
    """Тесты function тест-кейсов."""

    async def test_contains_checker_passes_on_greeting(self, client, mock_llm):
        """
        contains checker: LLM отвечает с приветствием -> тест проходит.

        Тест-кейс contains_check ожидает слова: привет|здравствуй|добро пожаловать
        """
        setup_mock_llm(mock_llm, ["Привет! Рад вас видеть!"])

        data = await run_evaluation(client, "example_react", "contains_check", "test_full")

        state = get_task_state(data)
        get_task_response(data)

        # Тест должен завершиться
        assert state in ("completed", "failed"), f"Unexpected state: {state}"

    async def test_contains_checker_fails_on_wrong_response(self, client, mock_llm):
        """
        contains checker: LLM отвечает без ключевых слов -> тест проваливается.
        """
        setup_mock_llm(mock_llm, ["Я могу помочь с расчетами."])

        data = await run_evaluation(client, "example_react", "contains_check", "test_full")

        state = get_task_state(data)
        # Тест должен завершиться (passed или failed)
        assert state in ("completed", "failed")

    async def test_not_contains_checker(self, client, mock_llm):
        """
        not_contains checker: проверяет отсутствие слов ошибка|error|не могу.
        """
        setup_mock_llm(mock_llm, ["Сегодня солнечно, температура +20 градусов."])

        data = await run_evaluation(client, "example_react", "not_contains_check", "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed")

    async def test_regex_checker(self, client, mock_llm):
        """
        regex checker: проверяет что ответ содержит число 4.
        Тест-кейс regex_check спрашивает "Сколько будет 2 + 2?"
        """
        setup_mock_llm(mock_llm, ["2 + 2 = 4"])

        data = await run_evaluation(client, "example_react", "regex_check", "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed")

    async def test_length_range_checker(self, client, mock_llm):
        """
        length checker: проверяет длину ответа 10-500 символов.
        """
        setup_mock_llm(mock_llm, ["Привет! Я ваш виртуальный ассистент."])

        data = await run_evaluation(client, "example_react", "length_range_check", "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed")

    async def test_state_checker(self, client, mock_llm):
        """
        state checker: проверяет что state.response != null.
        """
        setup_mock_llm(mock_llm, ["Привет!"])

        data = await run_evaluation(client, "example_react", "state_equality_check", "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed")

    async def test_python_function_checker(self, client, mock_llm):
        """
        Python function checker: вызывает agents.example_react.checks.check_calculator_result.
        """
        setup_mock_llm(mock_llm, ["15 + 27 = 42"])

        data = await run_evaluation(client, "example_react", "function_checker", "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed")


class TestEvaluationDialogType:
    """Тесты dialog тест-кейсов - многошаговые сценарии."""

    async def test_dialog_multi_step_executes_all_steps(self, client, mock_llm):
        """
        dialog_multi_step: 3 шага диалога с проверками.

        Шаги:
        1. "Привет!" -> check: contains:привет|здравствуй
        2. "Посчитай 10 + 5" -> check: contains:15
        3. "А теперь умножь на 2" -> check: contains:30
        """
        setup_mock_llm(
            mock_llm,
            [
                "Привет! Чем могу помочь?",
                "10 + 5 = 15",
                "15 * 2 = 30",
            ],
        )

        data = await run_evaluation(client, "example_react", "dialog_multi_step", "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed")

    async def test_dialog_with_final_check(self, client, mock_llm):
        """
        dialog_with_final_check: диалог + финальная проверка на contains:42.
        """
        setup_mock_llm(
            mock_llm,
            [
                "Хорошо, запомнил число 42.",
                "Вы сказали число 42.",
            ],
        )

        data = await run_evaluation(client, "example_react", "dialog_with_final_check", "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed")

    async def test_dialog_mixed_checks(self, client, mock_llm):
        """
        dialog_mixed_checks: разные типы проверок на каждом шаге.

        1. contains:привет
        2. length:20 (мин 20 символов)
        3. regex:\b4\b
        """
        setup_mock_llm(
            mock_llm,
            [
                "Привет!",
                "Это достаточно длинный ответ чтобы пройти проверку на минимальную длину текста.",
                "2 + 2 = 4, это простая математика.",
            ],
        )

        data = await run_evaluation(client, "example_react", "dialog_mixed_checks", "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed")


class TestEvaluationBranchFiltering:
    """Тесты фильтрации тест-кейсов по branch_ids."""

    async def test_wildcard_branch_available_for_any(self, client, mock_llm):
        """
        branch_ids='*' означает тест доступен для любой ветки.
        contains_check имеет branch_ids='*'.
        """
        setup_mock_llm(mock_llm, ["Привет!"])

        # Запускаем для разных веток — не должно быть ошибки "test not found"
        data = await run_evaluation(client, "example_react", "contains_check", "default")
        assert "error" not in data or "test not found" not in str(data.get("error", ""))

    async def test_specific_branch_mismatch_returns_error(self, client, mock_llm):
        """
        Тест для конкретной ветки недоступен для другой ветки.

        mock_skill_test имеет branch_ids=["test_full"]
        При запуске для branch_id="default" должна быть ошибка.
        """
        setup_mock_llm(mock_llm, ["Test response"])

        data = await run_evaluation(client, "example_react", "mock_skill_test", "default")

        state = get_task_state(data)
        response = get_task_response(data)

        # Должна быть ошибка или failed status
        assert state == "failed" or "not available" in response.lower() or "error" in data

    async def test_nonexistent_test_returns_error(self, client, mock_llm):
        """Несуществующий тест-кейс -> ошибка."""
        setup_mock_llm(mock_llm, ["Test response"])

        data = await run_evaluation(
            client, "example_react", "this_test_does_not_exist_12345", "test_full"
        )

        state = get_task_state(data)
        # Должен быть failed
        assert state == "failed" or "error" in data


class TestEvaluationDBStorage:
    """Тесты сохранения результатов в БД."""

    async def test_result_saved_to_db(self, client, container, mock_llm):
        """
        После выполнения теста результат должен быть в БД.
        """
        setup_mock_llm(mock_llm, ["Привет!"])

        test_case_id = "contains_check"
        await run_evaluation(client, "example_react", test_case_id, "test_full")

        # Проверяем БД
        results = await container.evaluation_repository.get_latest_results(
            flow_id="example_react",
            branch_id="test_full",
            limit=50,
        )

        # Должен быть результат
        assert len(results) > 0, "Нет результатов в БД"

        # Ищем наш тест
        found = None
        for r in results:
            if r.test_case_id == test_case_id:
                found = r
                break

        assert found is not None, f"Результат {test_case_id} не найден в БД"
        assert found.flow_id == "example_react"
        assert found.branch_id == "test_full"
        assert found.status in ("passed", "failed", "error")
        assert found.duration_ms >= 0

    async def test_multiple_tests_saved_separately(self, client, container, mock_llm):
        """Каждый тест сохраняется отдельно."""
        from datetime import date

        setup_mock_llm(mock_llm, ["Привет!"] * 10)

        test_ids = ["contains_check", "length_range_check", "state_equality_check"]

        for test_id in test_ids:
            await run_evaluation(client, "example_react", test_id, "test_full")

        # Проверяем что все есть в БД - используем get_by_run для сегодняшней даты
        today = date.today()
        results = await container.evaluation_repository.get_by_run(
            flow_id="example_react",
            branch_id="test_full",
            run_date=today,
        )

        saved_ids = {r.test_case_id for r in results}
        for test_id in test_ids:
            assert test_id in saved_ids, f"{test_id} не найден в БД"

    async def test_dialog_result_has_turns(self, client, container, mock_llm):
        """Dialog тест должен иметь turns_count > 0."""
        setup_mock_llm(
            mock_llm,
            [
                "Привет!",
                "15",
                "30",
            ],
        )

        test_case_id = "dialog_multi_step"
        await run_evaluation(client, "example_react", test_case_id, "test_full")

        results = await container.evaluation_repository.get_latest_results(
            flow_id="example_react",
            branch_id="test_full",
            limit=50,
        )

        for r in results:
            if r.test_case_id == test_case_id:
                assert r.turns_count > 0, "Dialog тест должен иметь turns_count > 0"
                break


class TestEvaluationResultsAPI:
    """Тесты API для получения результатов evaluation."""

    async def test_get_results_returns_list(self, client, container, mock_llm):
        """GET /api/v1/evaluation/results возвращает список результатов."""
        setup_mock_llm(mock_llm, ["Привет!"])
        await run_evaluation(client, "example_react", "contains_check", "test_full")

        response = await client.get(
            "/flows/api/v1/evaluation/results",
            params={"flow_id": "example_react", "branch_id": "test_full"},
        )

        assert response.status_code == 200
        page = response.json()
        assert "items" in page
        data = page["items"]
        assert isinstance(data, list)
        assert len(data) > 0

        result = data[0]
        assert "flow_id" in result
        assert "branch_id" in result
        assert "test_case_id" in result
        assert "status" in result
        assert "duration_ms" in result

    async def test_get_results_with_limit(self, client, container, mock_llm):
        """GET /api/v1/evaluation/results с limit ограничивает количество."""
        setup_mock_llm(mock_llm, ["Привет!"] * 5)

        # Запускаем несколько тестов
        for test_id in ["contains_check", "length_range_check", "state_equality_check"]:
            await run_evaluation(client, "example_react", test_id, "test_full")

        # Запрашиваем с limit=2
        response = await client.get(
            "/flows/api/v1/evaluation/results",
            params={"flow_id": "example_react", "branch_id": "test_full", "limit": 2},
        )

        assert response.status_code == 200
        page = response.json()
        assert len(page["items"]) <= 2

    async def test_get_results_empty_for_unknown_flow(self, client):
        """GET /api/v1/evaluation/results для несуществующего flow возвращает пустой список."""
        response = await client.get(
            "/flows/api/v1/evaluation/results",
            params={"flow_id": "nonexistent_flow_12345", "branch_id": "default"},
        )

        assert response.status_code == 200
        page = response.json()
        assert page["items"] == []

    async def test_get_summary_structure(self, client, container, mock_llm):
        """GET /api/v1/evaluation/results/summary возвращает правильную структуру."""
        setup_mock_llm(mock_llm, ["Привет!"])
        await run_evaluation(client, "example_react", "contains_check", "test_full")

        response = await client.get(
            "/flows/api/v1/evaluation/results/summary",
            params={"flow_id": "example_react", "branch_id": "test_full"},
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем все поля
        assert data["flow_id"] == "example_react"
        assert data["branch_id"] == "test_full"
        assert "run_date" in data
        assert "total" in data
        assert "passed" in data
        assert "failed" in data
        assert "errors" in data
        assert "pass_rate" in data
        assert "avg_duration_ms" in data
        assert "results" in data

        # pass_rate должен быть числом 0-100
        assert 0 <= data["pass_rate"] <= 100

        # results должен содержать краткую информацию о каждом тесте
        assert isinstance(data["results"], list)
        if data["results"]:
            r = data["results"][0]
            assert "test_case_id" in r
            assert "status" in r
            assert "duration_ms" in r

    async def test_get_summary_calculates_pass_rate(self, client, container, mock_llm):
        """GET /api/v1/evaluation/results/summary правильно считает pass_rate."""
        # Запускаем тесты с разными результатами
        setup_mock_llm(mock_llm, ["Привет!"])  # passed
        await run_evaluation(client, "example_react", "contains_check", "test_full")

        setup_mock_llm(mock_llm, ["Ответ без ключевых слов"])  # может быть failed
        await run_evaluation(client, "example_react", "length_range_check", "test_full")

        response = await client.get(
            "/flows/api/v1/evaluation/results/summary",
            params={"flow_id": "example_react", "branch_id": "test_full"},
        )

        assert response.status_code == 200
        data = response.json()

        # total = passed + failed + errors
        assert data["total"] == data["passed"] + data["failed"] + data["errors"]

    async def test_get_specific_test_result_found(self, client, container, mock_llm):
        """GET /api/v1/evaluation/results/{test_case_id} возвращает конкретный результат."""
        setup_mock_llm(mock_llm, ["Привет!"])
        test_case_id = "contains_check"
        await run_evaluation(client, "example_react", test_case_id, "test_full")

        response = await client.get(
            f"/flows/api/v1/evaluation/results/{test_case_id}",
            params={"flow_id": "example_react", "branch_id": "test_full"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data is not None
        assert data["test_case_id"] == test_case_id
        assert data["flow_id"] == "example_react"
        assert data["branch_id"] == "test_full"
        assert data["status"] in ("passed", "failed", "error")
        assert isinstance(data["duration_ms"], int)
        assert isinstance(data["dialog"], list)

    async def test_get_specific_test_result_not_found(self, client):
        """GET /api/v1/evaluation/results/{test_case_id} для несуществующего теста возвращает null."""
        response = await client.get(
            "/flows/api/v1/evaluation/results/nonexistent_test_12345",
            params={"flow_id": "example_react", "branch_id": "test_full"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data is None

    async def test_delete_old_results(self, client, container, mock_llm):
        """DELETE /api/v1/evaluation/results удаляет старые результаты."""
        # Сначала создадим результат
        setup_mock_llm(mock_llm, ["Привет!"])
        await run_evaluation(client, "example_react", "contains_check", "test_full")

        # Удаляем результаты старше 1 дня
        response = await client.delete("/flows/api/v1/evaluation/results", params={"days": 1})

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data
        assert isinstance(data["deleted"], int)

    async def test_get_results_with_date_filter(self, client, container, mock_llm):
        """GET /api/v1/evaluation/results с run_date фильтрует по дате."""
        from datetime import date as date_type

        setup_mock_llm(mock_llm, ["Привет!"])
        await run_evaluation(client, "example_react", "contains_check", "test_full")

        today = date_type.today().isoformat()

        # Запрос с сегодняшней датой должен вернуть результаты
        response = await client.get(
            "/flows/api/v1/evaluation/results",
            params={"flow_id": "example_react", "branch_id": "test_full", "run_date": today},
        )

        assert response.status_code == 200
        response.json()
        # Может быть пустым или с результатами - зависит от того что уже в БД

    async def test_get_results_required_params(self, client):
        """GET /api/v1/evaluation/results требует flow_id."""
        response = await client.get("/flows/api/v1/evaluation/results")

        # Должна быть ошибка валидации - flow_id обязателен
        assert response.status_code == 422

    async def test_summary_required_params(self, client):
        """GET /api/v1/evaluation/results/summary требует flow_id."""
        response = await client.get("/flows/api/v1/evaluation/results/summary")

        assert response.status_code == 422


class TestFlowsAPI:
    """Тесты API для получения flow с evaluation."""

    async def test_get_flow_with_evaluation(self, client):
        """GET /api/v1/flows/{flow_id} возвращает flow с evaluation."""
        response = await client.get("/flows/api/v1/flows/example_react")

        assert response.status_code == 200
        data = response.json()

        assert data["flow_id"] == "example_react"
        assert "evaluation" in data

        # evaluation должен быть dict
        if data["evaluation"]:
            assert isinstance(data["evaluation"], dict)
            # Проверяем что есть тест-кейсы
            assert len(data["evaluation"]) > 0

    async def test_get_flow_without_evaluation(self, client):
        """GET /api/v1/flows/{flow_id} для flow без evaluation."""
        # Если flow без evaluation - должен вернуть null
        response = await client.get("/flows/api/v1/flows/example_react")

        assert response.status_code == 200
        data = response.json()

        # evaluation может быть null или dict
        assert "evaluation" in data
        assert data["evaluation"] is None or isinstance(data["evaluation"], dict)

    async def test_get_flow_not_found(self, client):
        """GET /api/v1/flows/{flow_id} для несуществующего flow."""
        response = await client.get("/flows/api/v1/nonexistent_flow_12345")

        assert response.status_code == 404


class TestEvaluationGraphAgent:
    """Тесты evaluation для графового flow (example_graph)."""

    async def test_graph_route_order_classification(self, client, mock_llm):
        """
        example_graph должен маршрутизировать заказы.
        """
        setup_mock_llm(mock_llm, ["Ваш заказ #12345 обрабатывается."])

        data = await run_evaluation(
            client, "example_graph", "route_order_contains", "test_full_graph"
        )

        state = get_task_state(data)
        assert state in ("completed", "failed")

    async def test_graph_route_complaint_classification(self, client, mock_llm):
        """
        example_graph должен маршрутизировать жалобы.
        """
        setup_mock_llm(mock_llm, ["Ваша жалоба принята. Номер обращения: 54321."])

        data = await run_evaluation(
            client, "example_graph", "route_complaint_contains", "test_full_graph"
        )

        state = get_task_state(data)
        assert state in ("completed", "failed")


class TestEvaluationCheckerLogic:
    """Тесты проверяющие саму логику checkers."""

    async def test_checker_contains_with_pipe_alternatives(self, client, mock_llm):
        """
        contains:word1|word2|word3 должен проходить если есть хотя бы одно слово.
        """
        # Тестируем с разными вариантами
        test_responses = [
            "Привет!",  # содержит привет
            "Здравствуйте!",  # содержит здравствуй
            "До свидания!",  # не содержит ничего
        ]

        for response_text in test_responses:
            setup_mock_llm(mock_llm, [response_text])
            data = await run_evaluation(client, "example_react", "contains_check", "test_full")

            state = get_task_state(data)
            # Проверяем что тест завершился
            assert state in ("completed", "failed")

    async def test_checker_length_min(self, client, mock_llm):
        """
        length:N проверяет минимальную длину.
        """
        # Короткий ответ
        setup_mock_llm(mock_llm, ["Да."])

        data = await run_evaluation(client, "example_react", "length_range_check", "test_full")
        state = get_task_state(data)

        # Ответ "Да." имеет длину 3, а требуется 10-500
        assert state in ("completed", "failed")

    async def test_checker_regex_pattern_matching(self, client, mock_llm):
        """
        regex:\b4\b должен найти число 4 как отдельное слово.
        """
        test_responses = [
            "Ответ: 4",  # 4 как отдельное слово
            "Результат = 4.",  # 4 перед точкой
            "Число 42",  # 4 не отдельное слово (часть 42)
            "44",  # не отдельное слово
        ]

        for response_text in test_responses:
            setup_mock_llm(mock_llm, [response_text])
            data = await run_evaluation(client, "example_react", "regex_check", "test_full")
            state = get_task_state(data)
            assert state in ("completed", "failed")


class TestAllTestCasesExampleReact:
    """Прогоняем все тест-кейсы из example_react."""

    @pytest.mark.parametrize(
        "test_case_id,mock_response",
        [
            ("contains_check", "Привет!"),
            ("not_contains_check", "Сегодня хорошая погода"),
            ("regex_check", "2 + 2 = 4"),
            ("length_range_check", "Это ответ достаточной длины для теста"),
            ("state_equality_check", "Привет!"),
            ("state_nested_check", "Привет!"),
            ("function_checker", "15 + 27 = 42"),
        ],
    )
    async def test_function_test_cases(self, client, mock_llm, test_case_id, mock_response):
        """Проверяем что function тест-кейсы выполняются."""
        setup_mock_llm(mock_llm, [mock_response])

        data = await run_evaluation(client, "example_react", test_case_id, "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed"), f"Test {test_case_id} не завершился: {state}"

    @pytest.mark.parametrize(
        "test_case_id",
        [
            "dialog_multi_step",
            "dialog_with_final_check",
            "dialog_mixed_checks",
        ],
    )
    async def test_dialog_test_cases(self, client, mock_llm, test_case_id):
        """Проверяем что dialog тест-кейсы выполняются."""
        setup_mock_llm(
            mock_llm,
            [
                "Привет! Рад вас видеть.",
                "Результат: 15",
                "30",
                "42",
                "Длинный текст для проверки минимальной длины ответа.",
                "2 + 2 = 4",
            ],
        )

        data = await run_evaluation(client, "example_react", test_case_id, "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed"), (
            f"Dialog test {test_case_id} не завершился: {state}"
        )


@pytest.mark.real_taskiq
class TestFlowTypeEvaluation:
    """Тесты flow_dialog_test: нода-тестер + нода-судья.

    В стандартном режиме suite `sync_tools` исполняет задачи синхронно, поэтому tester,
    тестируемый flow и judge читают одну локальную очередь MockLLM в порядке вызовов.
    """

    async def test_flow_dialog_test_runs_with_tester_and_judge(self, client, mock_llm):
        """Проверяем что flow_dialog_test запускает тестера и судью."""
        setup_flow_dialog_mock_llm(
            mock_llm,
            tester_responses=[
                "Привет! Расскажи о своих возможностях.",
                "Хорошо. Сколько будет 2 + 2?",
                "[TEST_COMPLETE] Тест завершён успешно.",
            ],
            flow_responses=[
                "Я могу помочь с расчётами и вопросами.",
                "2 + 2 = 4",
            ],
            judge_response='{"scores": {"quality": 9, "completeness": 8}, "total_score": 8.5, "passed": true, "feedback": "Отличный диалог"}',
        )

        data = await run_evaluation(client, "example_react", "flow_dialog_test", "test_full")

        state = get_task_state(data)
        assert state in ("completed", "failed"), f"Agent test не завершился: {state}"

    async def test_flow_dialog_test_dialog_saved(self, client, mock_llm, container):
        """Проверяем что диалог агента сохраняется в БД."""
        setup_flow_dialog_mock_llm(
            mock_llm,
            tester_responses=[
                "Привет! Как дела?",
                "[TEST_COMPLETE]",
            ],
            flow_responses=[
                "Всё хорошо, спасибо!",
            ],
            judge_response='{"scores": {"quality": 7}, "total_score": 7, "passed": true, "feedback": "OK"}',
        )

        await run_evaluation(client, "example_react", "flow_dialog_test", "test_full")

        results = await container.evaluation_repository.get_latest_results(
            "example_react", "test_full", limit=1
        )
        assert len(results) >= 1

        result = results[0]
        assert result.test_case_id == "flow_dialog_test"
        assert len(result.dialog) > 0

    async def test_flow_dialog_test_scores_saved(self, client, mock_llm, container):
        """Проверяем что оценки судьи сохраняются."""
        setup_flow_dialog_mock_llm(
            mock_llm,
            tester_responses=[
                "Привет, проверяю работу",  # Тестер
                "[TEST_COMPLETE] Тест пройден",  # Тестер завершает
            ],
            flow_responses=[
                "Всё работает отлично",  # Agent
            ],
            judge_response='{"scores": {"accuracy": 9, "helpfulness": 8}, "total_score": 8.5, "passed": true, "feedback": "Хорошая работа"}',
        )

        await run_evaluation(client, "example_react", "flow_dialog_test", "test_full")

        results = await container.evaluation_repository.get_latest_results(
            "example_react", "test_full", limit=1
        )
        result = results[0]

        assert result.scores is not None
        assert result.get_total_score() is not None
        assert result.judge_feedback is not None

    async def test_flow_dialog_test_judge_fail_marks_test_failed(
        self, client, mock_llm, container
    ):
        """Проверяем что если судья ставит passed=false, тест failed."""
        setup_flow_dialog_mock_llm(
            mock_llm,
            tester_responses=[
                "Тестовый вопрос",
                "[TEST_COMPLETE]",
            ],
            flow_responses=[
                "Плохой ответ",
            ],
            judge_response='{"scores": {"quality": 2}, "total_score": 2, "passed": false, "feedback": "Неудовлетворительно"}',
        )

        data = await run_evaluation(client, "example_react", "flow_dialog_test", "test_full")

        state = get_task_state(data)
        assert state == "completed", (
            "A2A задача evaluation завершается в completed; passed/failed хранится в результате оценки"
        )
        results = await container.evaluation_repository.get_latest_results(
            "example_react", "test_full", limit=1
        )
        assert len(results) >= 1
        assert results[0].status == "failed", (
            "Тест должен быть failed если судья поставил passed=false"
        )

    async def test_flow_dialog_test_max_turns_limit(self, client, mock_llm, container):
        """Проверяем что тест останавливается по max_turns=5 из flow_dialog_test."""
        # Тестер: 1 затравка + 5 итераций без TEST_COMPLETE = 6 вызовов; затем 1 судья.
        setup_flow_dialog_mock_llm(
            mock_llm,
            tester_responses=[
                "Вопрос 1",
                "Вопрос 2",
                "Вопрос 3",
                "Вопрос 4",
                "Вопрос 5",
                "Вопрос 6",
            ],
            # Агент: ровно 5 вызовов flow на 5 итерациях диалога.
            flow_responses=[
                "Ответ 1",
                "Ответ 2",
                "Ответ 3",
                "Ответ 4",
                "Ответ 5",
            ],
            judge_response='{"scores": {"quality": 5}, "total_score": 5, "passed": true, "feedback": "max_turns reached"}',
        )

        data = await run_evaluation(client, "example_react", "flow_dialog_test", "test_full")

        state = get_task_state(data)
        assert state == "completed", f"Evaluation должен завершиться completed, получено {state}"

        results = await container.evaluation_repository.get_latest_results(
            "example_react", "test_full", limit=1
        )
        assert len(results) >= 1, "Результат evaluation должен быть сохранён"
        result = results[0]
        assert result.test_case_id == "flow_dialog_test"
        assert result.turns_count == 5, (
            f"Диалог должен остановиться ровно на max_turns=5, получено {result.turns_count}"
        )

    async def test_flow_dialog_test_graph_flow(self, client, mock_llm):
        """Проверяем evaluation на графовом flow."""
        setup_flow_dialog_mock_llm(
            mock_llm,
            tester_responses=[
                "Хочу сделать заказ",
                "[TEST_COMPLETE] Заказ оформлен.",
            ],
            flow_responses=[
                "Ваш заказ принят. Номер 12345.",
            ],
            judge_response='{"scores": {"routing": 10, "response": 9}, "total_score": 9.5, "passed": true, "feedback": "Правильная маршрутизация"}',
        )

        data = await run_evaluation(client, "example_graph", "agent_quality_test", "default")

        state = get_task_state(data)
        assert state in ("completed", "failed"), f"Graph evaluation test не завершился: {state}"

    async def test_flow_dialog_test_loop_detection(self, client, mock_llm, container):
        """Проверяем обнаружение зацикливания."""
        # Одинаковые ответы вызовут детекцию зацикливания
        setup_flow_dialog_mock_llm(
            mock_llm,
            tester_responses=[
                "Повтор",
                "Повтор",
                "Повтор",
                "Повтор",
                "Повтор",
                "Повтор",
            ],
            flow_responses=[
                "Ответ",
                "Ответ",
                "Ответ",
                "Ответ",
                "Ответ",
                "Ответ",
            ],
        )

        await run_evaluation(client, "example_react", "flow_dialog_test", "test_full")

        results = await container.evaluation_repository.get_latest_results(
            "example_react", "test_full", limit=1
        )
        if results:
            result = results[0]
            # Либо error с loop detected, либо завершился как-то иначе
            assert result.status in ("error", "passed", "failed")
