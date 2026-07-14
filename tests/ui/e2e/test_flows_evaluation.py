"""UI E2E сценарии Flows: Evaluation Lab."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    flows_api_create_flow,
    flows_doc_flow_id,
    flows_llm_payload,
    flows_seed_mock_llm,
)
from tests.ui.e2e.flows_evaluation_e2e_helpers import (
    flows_eval_add_case_from_template,
    flows_eval_compare_runs,
    flows_eval_create_suite,
    flows_eval_open_evaluation_page,
    flows_eval_run,
    flows_eval_select_panel,
    flows_eval_set_baseline,
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
    await expect(case_row).to_be_visible(timeout=30_000)
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
