"""UI E2E сценарии Flows: Evaluation Lab."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_code_echo_payload,
    flows_doc_flow_id,
    flows_llm_payload,
    flows_seed_mock_llm,
)
from tests.ui.e2e.flows_evaluation_e2e_helpers import (
    flows_eval_add_case_from_template,
    flows_eval_add_turn,
    flows_eval_api_get_case,
    flows_eval_api_list_cases,
    flows_eval_api_list_suites,
    flows_eval_compare_runs,
    flows_eval_create_blank_case,
    flows_eval_create_judge_node,
    flows_eval_create_rubric,
    flows_eval_create_suite,
    flows_eval_open_evaluation_page,
    flows_eval_run,
    flows_eval_save_case,
    flows_eval_select_panel,
    flows_eval_set_baseline,
    flows_eval_set_case_name,
    flows_eval_set_check_type,
    flows_eval_set_contains_values,
    flows_eval_set_input_kind,
    flows_eval_set_text_input,
    flows_eval_wait_run_finished,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="evaluation",
    doc_slug="eval-first-case",
    title="Первый тест качества агента",
    description=(
        "**Для чего:** эта инструкция поможет создать первый набор проверок и тест-кейс "
        "для агента.\n\n"
        "**Какие проблемы решает:** непонятно, с чего начать контроль качества ответов "
        "и какой шаблон выбрать.\n\n"
        "**Результат:** в Evaluation Lab сохранён первый тест-кейс в новом наборе."
    ),
    title_en="First agent quality test",
    description_en=(
        "**What for:** this guide helps you create the first check suite and test case "
        "for an agent.\n\n"
        "**Problems it solves:** it is unclear how to start controlling answer quality "
        "and which template to pick.\n\n"
        "**Result:** the first test case is saved in a new Evaluation Lab suite."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_eval_first_case(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("eval_first", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Отвечай про доставку садовых товаров.",
        ),
    )

    page = ui_page_system
    await flows_eval_open_evaluation_page(page, flows_ui, flow_id)
    await scenario.step(
        "Откройте Evaluation Lab",
        page,
        screenshot_name="evaluation-lab-opened",
        label_en="Open Evaluation Lab",
        details=(
            "В меню редактора выберите Evaluation Lab. Слева — наборы и кейсы, в центре "
            "матрица результатов, справа — редактор проверки."
        ),
        details_en=(
            "In the editor menu, choose Evaluation Lab. Suites and cases are on the left, "
            "the results matrix is in the center, and the case editor is on the right."
        ),
    )

    await flows_eval_create_suite(page)
    await scenario.step(
        "Создайте набор тестов",
        page,
        screenshot_name="evaluation-suite-created",
        label_en="Create a test suite",
        details=(
            "Нажмите «+» в блоке Suites. Появится новый набор — контейнер для связанных "
            "проверок одного агента."
        ),
        details_en=(
            "Click + in the Suites block. A new suite appears — a container for related "
            "checks of one agent."
        ),
    )

    await flows_eval_add_case_from_template(page, r"содержит|contains|fragment")
    case_editor = page.locator("flows-evaluation-case-editor").first
    await expect(case_editor).to_contain_text(re.compile(r"достав|delivery|input|ввод", re.I))
    await scenario.step(
        "Добавьте кейс из шаблона",
        page,
        screenshot_name="evaluation-case-from-template",
        label_en="Add a case from a template",
        details=(
            "Нажмите «Шаблоны» и выберите проверку «ответ содержит фрагмент». Шаблон "
            "сразу создаст кейс с готовым типом проверки."
        ),
        details_en=(
            "Click Templates and choose the response-contains-fragment check. The template "
            "instantly creates a case with a ready check type."
        ),
    )

    case_row = page.locator("flows-evaluation-suite-sidebar .row").filter(
        has_text=re.compile(r"содержит|contains", re.I)
    ).first
    await expect(case_row).to_be_visible(timeout=10_000)
    await scenario.step(
        "Проверьте сохранённый кейс",
        page,
        screenshot_name="evaluation-case-saved",
        label_en="Verify the saved case",
        details=(
            "**Демонстрация результата.** Новый кейс виден в списке Cases — значит, "
            "первая проверка качества создана и готова к запуску.\n\n"
            "**Итог.** Теперь вы умеете открыть Evaluation Lab, создать набор и добавить "
            "первый тест из шаблона."
        ),
        details_en=(
            "**Result demonstration.** The new case appears in the Cases list — your first "
            "quality check is created and ready to run.\n\n"
            "**Summary.** You can now open Evaluation Lab, create a suite, and add the first "
            "test from a template."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="evaluation",
    doc_slug="eval-run-compare",
    title="Запускаем тесты и сравниваем версии",
    description=(
        "**Для чего:** эта инструкция поможет прогнать проверки и сравнить два запуска.\n\n"
        "**Какие проблемы решает:** после изменения агента неясно, улучшилось ли качество "
        "и как зафиксировать эталон.\n\n"
        "**Результат:** два прогона выполнены, сравнение открыто, baseline выбран."
    ),
    title_en="Run tests and compare versions",
    description_en=(
        "**What for:** this guide helps you run checks and compare two execution runs.\n\n"
        "**Problems it solves:** after changing an agent, it is unclear whether quality "
        "improved and how to set a baseline.\n\n"
        "**Result:** two runs completed, comparison opened, baseline selected."
    ),
    timeout_seconds=120,
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.real_taskiq
@pytest.mark.timeout(360)
async def test_flows_eval_run_compare(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    taskiq_worker,
    unique_id: str,
) -> None:
    _ = taskiq_worker
    flow_id = flows_doc_flow_id("eval_compare", unique_id)
    await flows_seed_mock_llm(["Ответ про доставку: завтра курьером."])
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Отвечай про доставку.",
        ),
    )

    page = ui_page_system
    await flows_eval_open_evaluation_page(page, flows_ui, flow_id)
    await flows_eval_create_suite(page)
    await flows_eval_add_case_from_template(page, r"содержит|contains|fragment")
    await scenario.step(
        "Подготовьте набор с кейсом",
        page,
        screenshot_name="evaluation-ready-to-run",
        label_en="Prepare a suite with a case",
        details=(
            "Создайте набор и добавьте кейс из шаблона. Перед запуском убедитесь, что "
            "выбран нужный suite и case."
        ),
        details_en=(
            "Create a suite and add a case from a template. Before running, make sure the "
            "right suite and case are selected."
        ),
    )

    await flows_eval_run(page)
    await flows_eval_wait_run_finished(page)
    run_status = page.locator("flows-evaluation-page").get_by_text(
        re.compile(r"pass|fail|успех|ошиб|done|готов", re.I)
    ).first
    await expect(run_status).to_be_visible(timeout=60_000)
    await scenario.step(
        "Запустите первый прогон",
        page,
        screenshot_name="evaluation-first-run",
        label_en="Run the first evaluation",
        details=(
            "Нажмите «Запустить». Evaluation Lab отправит проверку в фон и покажет "
            "статус в верхней панели и матрице результатов."
        ),
        details_en=(
            "Click Run. Evaluation Lab submits the check in the background and shows "
            "status in the top toolbar and results matrix."
        ),
    )

    await flows_eval_run(page)
    await flows_eval_wait_run_finished(page)
    results_matrix = page.locator("flows-evaluation-results-matrix").first
    await expect(results_matrix).to_be_visible(timeout=30_000)
    await scenario.step(
        "Запустите второй прогон для сравнения",
        page,
        screenshot_name="evaluation-second-run",
        label_en="Run a second evaluation for comparison",
        details=(
            "Повторите запуск с тем же кейсом. В матрице появятся два прогона — "
            "их можно сравнить и выбрать эталон."
        ),
        details_en=(
            "Run again with the same case. The matrix shows two runs — "
            "you can compare them and pick a baseline."
        ),
    )

    await flows_eval_compare_runs(page)
    await flows_eval_set_baseline(page)
    compare_panel = page.locator("flows-evaluation-compare-panel").first
    await expect(compare_panel).to_be_visible(timeout=30_000)
    await scenario.step(
        "Сравните прогоны и зафиксируйте эталон",
        page,
        screenshot_name="evaluation-compare-baseline",
        label_en="Compare runs and set baseline",
        details=(
            "**Демонстрация результата.** Открыта панель Compare, а baseline зафиксирован — "
            "теперь можно отслеживать регрессии между версиями агента.\n\n"
            "**Итог.** Теперь вы умеете запускать проверки, сравнивать два прогона и "
            "назначать эталон для ветки."
        ),
        details_en=(
            "**Result demonstration.** The Compare panel is open and a baseline is set — "
            "you can now track regressions between agent versions.\n\n"
            "**Summary.** You can run checks, compare two runs, and assign a baseline for "
            "the branch."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="evaluation",
    doc_slug="eval-monitor-quality",
    title="Следим за качеством в работе",
    description=(
        "**Для чего:** эта инструкция покажет, где смотреть мониторинг качества и "
        "контрольные пороги.\n\n"
        "**Какие проблемы решает:** после запуска агента непонятно, как отслеживать "
        "деградацию ответов на реальных диалогах.\n\n"
        "**Результат:** открыта панель мониторинга с baselines и gate policies."
    ),
    title_en="Monitor quality in production",
    description_en=(
        "**What for:** this guide shows where to review quality monitoring and gate policies.\n\n"
        "**Problems it solves:** after launching an agent, it is unclear how to track answer "
        "degradation on real conversations.\n\n"
        "**Result:** the monitoring panel with baselines and gate policies is open."
    ),
    timeout_seconds=120,
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_eval_monitor_quality(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("eval_monitor", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Отвечай про доставку.",
        ),
    )

    page = ui_page_system
    await flows_eval_open_evaluation_page(page, flows_ui, flow_id)
    await flows_eval_create_suite(page)
    await scenario.step(
        "Откройте Evaluation Lab",
        page,
        screenshot_name="monitoring-lab-opened",
        label_en="Open Evaluation Lab",
        details=(
            "Evaluation Lab — единое место и для ручных проверок, и для мониторинга "
            "качества в работе."
        ),
        details_en=(
            "Evaluation Lab is the single place for manual checks and in-production "
            "quality monitoring."
        ),
    )

    await flows_eval_select_panel(page, r"Monitoring|Монитор")
    monitoring = page.locator("flows-evaluation-page .monitoring").first
    await expect(monitoring).to_be_visible(timeout=30_000)
    await expect(monitoring.get_by_text(re.compile(r"gate|гейт|baseline|базов", re.I)).first).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Откройте панель мониторинга",
        page,
        screenshot_name="monitoring-panel-opened",
        label_en="Open the monitoring panel",
        details=(
            "В блоке Workspace выберите Monitoring. Здесь собраны gate policies, baselines "
            "и online monitors для наблюдения за качеством."
        ),
        details_en=(
            "In the Workspace block, choose Monitoring. Gate policies, baselines, and online "
            "monitors for quality observation are collected here."
        ),
    )

    gate_section = monitoring.get_by_text(re.compile(r"gate|гейт", re.I)).first
    await expect(gate_section).to_be_visible(timeout=30_000)
    await scenario.step(
        "Найдите блок gate policies",
        page,
        screenshot_name="monitoring-gate-policies",
        label_en="Find the gate policies block",
        details=(
            "На панели найдите раздел gate policies и baselines. Здесь задаются пороги "
            "качества, при нарушении которых система сигнализирует о деградации."
        ),
        details_en=(
            "On the panel find the gate policies and baselines section. Here you set "
            "quality thresholds that trigger alerts when answers degrade."
        ),
    )

    await expect(monitoring.get_by_text(re.compile(r"ready|готов|active|актив", re.I)).first).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Проверьте статус мониторинга",
        page,
        screenshot_name="monitoring-status-visible",
        label_en="Check monitoring status",
        details=(
            "**Демонстрация результата.** На панели видны baselines и статус мониторинга — "
            "значит, контур наблюдения за качеством доступен для настройки.\n\n"
            "**Итог.** Теперь вы знаете, где открыть мониторинг качества и что искать "
            "перед настройкой gate policies."
        ),
        details_en=(
            "**Result demonstration.** The panel shows baselines and monitoring status — "
            "the quality observation layer is ready to configure.\n\n"
            "**Summary.** You now know where to open quality monitoring and what to look "
            "for before configuring gate policies."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="evaluation",
    doc_slug="eval-case-turns-inputs",
    title="Собираем кейс из нескольких turns",
    description=(
        "**Для чего:** эта инструкция поможет собрать тест-кейс с несколькими turns "
        "и разными типами входа.\n\n"
        "**Какие проблемы решает:** непонятно, как добавить второй ход диалога "
        "и переключить вход с текста на код или LLM-ноду.\n\n"
        "**Результат:** кейс сохранён с двумя turns, после перезагрузки данные на месте."
    ),
    title_en="Build a multi-turn evaluation case",
    description_en=(
        "**What for:** this guide helps you build a test case with several turns "
        "and different input kinds.\n\n"
        "**Problems it solves:** it is unclear how to add a second dialog turn "
        "and switch input from text to code or an LLM node.\n\n"
        "**Result:** the case is saved with two turns and survives reload."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_eval_case_turns_and_input_kinds(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("eval_turns", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_code_echo_payload(flow_id, name=f"Eval turns {unique_id}"),
    )

    page = ui_page_system
    await flows_eval_open_evaluation_page(page, flows_ui, flow_id)
    await flows_eval_create_suite(page)
    await scenario.step(
        "Откройте Evaluation Lab и создайте набор",
        page,
        screenshot_name="eval-turns-suite-ready",
        label_en="Open Evaluation Lab and create a suite",
        details=(
            "Откройте Evaluation Lab у агента и нажмите «+» у Suites. Набор нужен, "
            "чтобы хранить связанные кейсы в одном месте."
        ),
        details_en=(
            "Open Evaluation Lab for the agent and click + next to Suites. A suite keeps "
            "related cases in one place."
        ),
    )

    await flows_eval_create_blank_case(page)
    case_name = f"Turns case {unique_id}"
    await flows_eval_set_case_name(page, case_name)
    await flows_eval_set_text_input(page, "привет из turn 1")
    await flows_eval_set_contains_values(page, "echo")
    await scenario.step(
        "Создайте первый turn с текстовым входом",
        page,
        screenshot_name="eval-turns-first-text",
        label_en="Create the first turn with text input",
        details=(
            "Нажмите «Создать case», задайте название и оставьте тип входа «Текст». "
            "Введите сообщение пользователя и ожидаемый фрагмент ответа."
        ),
        details_en=(
            "Click Create case, set a name, and keep the Text input kind. "
            "Enter the user message and the expected response fragment."
        ),
    )

    await flows_eval_add_turn(page)
    await flows_eval_set_input_kind(page, "inline_code")
    editor = page.locator("flows-evaluation-case-editor").first
    await expect(editor.locator("flows-code-editor").first).to_be_visible(timeout=10_000)
    await flows_eval_set_input_kind(page, "node")
    await expect(editor.get_by_text(re.compile(r"tester|LLM node", re.I)).first).to_be_visible(
        timeout=10_000
    )
    await flows_eval_set_input_kind(page, "text")
    await flows_eval_set_text_input(page, "второй ход")
    await flows_eval_set_contains_values(page, "echo")
    await scenario.step(
        "Добавьте второй turn и переключите типы входа",
        page,
        screenshot_name="eval-turns-input-kinds",
        label_en="Add a second turn and switch input kinds",
        details=(
            "Нажмите «Добавить turn». Переключите тип входа: Текст → Код → LLM node → снова "
            "Текст. Так вы увидите три режима ввода; для сохранения оставьте текст."
        ),
        details_en=(
            "Click Add turn. Switch input kind: Text → Code → LLM node → Text again. "
            "You will see all three input modes; keep text for the saved case."
        ),
    )

    await flows_eval_save_case(page)
    case_row = page.locator("flows-evaluation-suite-sidebar .row").filter(
        has_text=re.compile(re.escape(case_name))
    ).first
    await expect(case_row).to_be_visible(timeout=15_000)

    await page.reload()
    await flows_eval_open_evaluation_page(page, flows_ui, flow_id)
    await expect(
        page.locator("flows-evaluation-suite-sidebar .row").filter(
            has_text=re.compile(re.escape(case_name))
        ).first
    ).to_be_visible(timeout=30_000)
    await page.locator("flows-evaluation-suite-sidebar .row").filter(
        has_text=re.compile(re.escape(case_name))
    ).first.click()
    editor = page.locator("flows-evaluation-case-editor").first
    await expect(editor).to_contain_text(re.compile(r"Turn 2|turn 2", re.I), timeout=15_000)
    await scenario.step(
        "Сохраните кейс и проверьте после перезагрузки",
        page,
        screenshot_name="eval-turns-reloaded",
        label_en="Save the case and verify after reload",
        details=(
            "**Демонстрация результата.** После сохранения и перезагрузки страницы кейс "
            "снова открывается с двумя turns — значит, структура сохранена.\n\n"
            "**Итог.** Теперь вы умеете собирать multi-turn кейс и переключать типы входа."
        ),
        details_en=(
            "**Result demonstration.** After save and reload the case opens again with two "
            "turns — the structure is persisted.\n\n"
            "**Summary.** You can build a multi-turn case and switch input kinds."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="evaluation",
    doc_slug="eval-llm-judge-score",
    title="Оцениваем ответ судьёй LLM",
    description=(
        "**Для чего:** эта инструкция поможет создать рубрику, judge-ноду и прогнать "
        "кейс с оценкой LLM judge.\n\n"
        "**Какие проблемы решает:** непонятно, где хранить критерии оценки и как "
        "увидеть score после запуска.\n\n"
        "**Результат:** кейс с LLM judge сохранён (только id), прогон показывает score."
    ),
    title_en="Score an answer with an LLM judge",
    description_en=(
        "**What for:** this guide helps you create a rubric, a judge node, and run "
        "a case with LLM judge scoring.\n\n"
        "**Problems it solves:** it is unclear where criteria live and how to see "
        "the score after a run.\n\n"
        "**Result:** an LLM judge case is saved (ids only) and the run shows a score."
    ),
    timeout_seconds=180,
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.real_taskiq
@pytest.mark.timeout(360)
async def test_flows_eval_llm_judge_create_and_run(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    taskiq_worker,
    unique_id: str,
) -> None:
    from apps.flows.src.evaluation.lab_service import EVALUATION_JUDGE_TOOL_NAME

    _ = taskiq_worker
    flow_id = flows_doc_flow_id("eval_judge_ui", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_code_echo_payload(flow_id, name=f"Eval judge {unique_id}"),
    )

    page = ui_page_system
    await flows_eval_open_evaluation_page(page, flows_ui, flow_id)
    await flows_eval_create_suite(page)
    await flows_eval_create_blank_case(page)
    case_name = f"Judge case {unique_id}"
    await flows_eval_set_case_name(page, case_name)
    await flows_eval_set_text_input(page, "проверь качество ответа")
    await flows_eval_set_check_type(page, "llm_judge")
    await scenario.step(
        "Создайте кейс и выберите проверку LLM judge",
        page,
        screenshot_name="eval-judge-check-selected",
        label_en="Create a case and select LLM judge",
        details=(
            "Создайте пустой case, задайте название и текстовый вход. В типе проверки "
            "выберите «LLM judge» — появятся поля рубрики и judge-ноды."
        ),
        details_en=(
            "Create a blank case, set a name and text input. In check type choose "
            "LLM judge — rubric and judge node fields appear."
        ),
    )

    await flows_eval_create_rubric(
        page,
        name=f"UI rubric {unique_id}",
        prompt="Ответ должен быть полезным и конкретным.",
        threshold="7",
    )
    await flows_eval_create_judge_node(page)
    await scenario.step(
        "Создайте рубрику и judge-ноду в flow",
        page,
        screenshot_name="eval-judge-rubric-and-node",
        label_en="Create a rubric and judge node in the flow",
        details=(
            "Нажмите «Новая рубрика», заполните название, threshold и промпт критериев, "
            "затем «Создать рубрику». После этого нажмите «Создать judge node» — нода "
            "появится в FlowConfig агента."
        ),
        details_en=(
            "Click New rubric, fill name, threshold and criteria prompt, then Create rubric. "
            "Next click Create judge node — the node is stored in the agent FlowConfig."
        ),
    )

    await flows_eval_save_case(page)
    await expect(
        page.locator("flows-evaluation-suite-sidebar .row").filter(
            has_text=re.compile(re.escape(case_name))
        ).first
    ).to_be_visible(timeout=20_000)

    suites = await flows_eval_api_list_suites(flows_ui.origin, auth_token_system, flow_id)
    assert len(suites) >= 1
    suite_id = str(suites[0]["suite_id"])
    cases = await flows_eval_api_list_cases(flows_ui.origin, auth_token_system, suite_id)
    saved = next(item for item in cases if item.get("name") == case_name)
    case_payload = await flows_eval_api_get_case(
        flows_ui.origin,
        auth_token_system,
        suite_id,
        str(saved["case_id"]),
    )
    turns = case_payload.get("turns")
    assert isinstance(turns, list) and len(turns) >= 1
    first_turn = turns[0]
    assert isinstance(first_turn, dict)
    checks = first_turn.get("checks")
    assert isinstance(checks, list) and len(checks) >= 1
    check = checks[0]
    assert isinstance(check, dict)
    assert check.get("type") == "llm_judge"
    judge_node_id = check.get("judge_node_id")
    assert isinstance(judge_node_id, str) and len(judge_node_id) > 0
    assert check.get("judge_node") is None
    flow = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    nodes = flow.get("nodes")
    assert isinstance(nodes, dict)
    assert judge_node_id in nodes
    await scenario.step(
        "Сохраните кейс и убедитесь, что хранятся только id",
        page,
        screenshot_name="eval-judge-case-saved-ids",
        label_en="Save the case and confirm only ids are stored",
        details=(
            "Нажмите «Создать». Кейс появляется в списке: в API у проверки есть "
            "judge_node_id и rubric_version_id, а тело judge-ноды лежит в flow."
        ),
        details_en=(
            "Click Create. The case appears in the list: the check stores judge_node_id "
            "and rubric_version_id, while the judge body lives in the flow."
        ),
    )

    await flows_seed_mock_llm(
        [
            {
                "type": "tool_call",
                "tool": EVALUATION_JUDGE_TOOL_NAME,
                "args": {
                    "scores": {"quality": 9.0},
                    "total_score": None,
                    "passed": True,
                    "feedback": "ui judge ok",
                },
            }
        ]
    )
    await flows_eval_run(page)
    await flows_eval_wait_run_finished(page)
    matrix = page.locator("flows-evaluation-results-matrix").first
    await expect(matrix).to_be_visible(timeout=30_000)
    await expect(matrix.locator(".score").first).to_be_visible(timeout=30_000)
    transcript = page.locator("flows-evaluation-transcript").first
    if await transcript.count() > 0:
        await expect(transcript).to_contain_text(re.compile(r"ui judge ok|9", re.I), timeout=30_000)
    await scenario.step(
        "Запустите кейс и посмотрите score",
        page,
        screenshot_name="eval-judge-score-visible",
        label_en="Run the case and inspect the score",
        details=(
            "**Демонстрация результата.** После «Запустить» в матрице результатов виден "
            "score, а в transcript — feedback судьи.\n\n"
            "**Итог.** Теперь вы умеете создать рубрику с judge-нодой и прогнать LLM judge "
            "до видимой оценки."
        ),
        details_en=(
            "**Result demonstration.** After Run the results matrix shows a score and the "
            "transcript shows judge feedback.\n\n"
            "**Summary.** You can create a rubric with a judge node and run an LLM judge "
            "until the score is visible."
        ),
    )
