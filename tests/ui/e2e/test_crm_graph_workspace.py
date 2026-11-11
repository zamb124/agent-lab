"""E2E: единый graph workspace — редирект с /crm/mindmap."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.crm_activity_tasks_helpers import (
    crm_api_create_entity,
    crm_api_create_relationship,
    crm_api_ensure_entity_type,
    crm_api_ensure_namespace,
    crm_api_ensure_relationship_type,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_activate_namespace_for_next_load
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="crm",
    tag="entities",
    doc_slug="graph-explore",
    title="Граф связей: кто с кем связан",
    title_en="Relation graph: who is linked to whom",
    description=(
        "**Для чего:** увидеть всю картину связей картотеки сразу — "
        "кто в какой компании работает, какая сделка к кому относится.\n\n"
        "**Какие проблемы решает:** по одной карточке не видно окружения "
        "клиента. Граф показывает записи узлами, а связи — линиями: "
        "3D-обзор для общей картины и «mind map» для чтения дерева.\n\n"
        "**Результат:** вы нашли нужную запись на графе и открыли её "
        "карточку прямо из картинки."
    ),
    description_en=(
        "**Purpose:** see the whole web of record links at once — who "
        "works at which company, which deal belongs to whom.\n\n"
        "**Problems solved:** a single card does not show the customer "
        "neighbourhood. The graph draws records as nodes and links as "
        "edges: a 3D overview for the big picture and a mind map for "
        "reading the tree.\n\n"
        "**Result:** you found the record on the graph and opened its "
        "card right from the picture."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180, func_only=True)
async def test_crm_graph_explore_scenario(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    page = ui_page_system
    namespace = f"g_{unique_id}"
    org_name = f"ООО «Ромашка» {unique_id[:6]}"
    contact_name = f"Иван Петров {unique_id[:6]}"
    project_name = f"Проект «Альфа» {unique_id[:6]}"
    note_name = f"Заметка о сделке {unique_id[:6]}"

    await crm_api_ensure_namespace(crm_ui.origin, auth_token_system, namespace=namespace)
    for type_id, type_name in (
        ("organization", "Организация"),
        ("contact", "Контакт"),
        ("project", "Проект"),
    ):
        await crm_api_ensure_entity_type(
            crm_ui.origin,
            auth_token_system,
            type_id=type_id,
            name=type_name,
            namespace=namespace,
        )
    await crm_api_ensure_relationship_type(
        crm_ui.origin, auth_token_system, type_id="works_at", name="Работает в"
    )
    await crm_api_ensure_relationship_type(
        crm_ui.origin,
        auth_token_system,
        type_id="related_to",
        name="Связана с",
        is_directed=False,
    )

    org_id = await crm_api_create_entity(
        crm_ui.origin, auth_token_system,
        entity_type="organization", name=org_name, namespace=namespace,
    )
    contact_id = await crm_api_create_entity(
        crm_ui.origin, auth_token_system,
        entity_type="contact", name=contact_name, namespace=namespace,
    )
    project_id = await crm_api_create_entity(
        crm_ui.origin, auth_token_system,
        entity_type="project", name=project_name, namespace=namespace,
    )
    await crm_api_create_relationship(
        crm_ui.origin, auth_token_system,
        source_entity_id=contact_id, target_entity_id=org_id,
        relationship_type="works_at", namespace=namespace,
    )
    note_id = await crm_api_create_entity(
        crm_ui.origin, auth_token_system,
        entity_type="note", name=note_name, namespace=namespace,
    )
    await crm_api_create_relationship(
        crm_ui.origin, auth_token_system,
        source_entity_id=project_id, target_entity_id=org_id,
        relationship_type="related_to", namespace=namespace,
    )
    await crm_api_create_relationship(
        crm_ui.origin, auth_token_system,
        source_entity_id=note_id, target_entity_id=contact_id,
        relationship_type="related_to", namespace=namespace,
    )

    await sync_e2e_activate_namespace_for_next_load(page, namespace)
    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(f"{crm_ui.origin}/crm/graph?view=3d", wait_until="domcontentloaded")
    workspace = page.locator("crm-graph-workspace")
    await expect(workspace).to_be_visible(timeout=60_000)
    await expect(page.locator("crm-graph-canvas")).to_be_visible(timeout=60_000)
    await page.wait_for_function(
        """() => {
            const deep = (root) => {
                const direct = root.querySelector('crm-graph-workspace');
                if (direct) return direct;
                for (const el of root.querySelectorAll('*')) {
                    if (el.shadowRoot) {
                        const found = deep(el.shadowRoot);
                        if (found) return found;
                    }
                }
                return null;
            };
            const ws = deep(document);
            return ws && Array.isArray(ws._graphNodes) && ws._graphNodes.length >= 3;
        }""",
        timeout=60_000,
    )
    await scenario.step(
        "Граф связей пространства",
        page,
        screenshot_name="graph-3d-overview",
        label_en="Space relation graph",
        details=(
            "Откройте раздел «Граф» — записи пространства рисуются "
            "узлами, а связи между ними — линиями. Слева внизу — легенда "
            "цветов по типам записей, сверху слева — поиск по графу."
        ),
        details_en=(
            "Open the Graph section — space records are drawn as nodes "
            "and their links as edges. The legend at bottom left shows "
            "record-type colours, the search pill is at top left."
        ),
    )

    toolbar = page.locator("crm-graph-toolbar")
    await expect(toolbar).to_be_visible(timeout=30_000)
    await toolbar.get_by_role("button", name="Mind map", exact=True).click()
    mindmap = page.locator("crm-mindmap-canvas")
    await expect(mindmap).to_be_visible(timeout=60_000)
    await expect(
        mindmap.get_by_text(org_name, exact=False)
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Режим «mind map»",
        page,
        screenshot_name="graph-mindmap",
        label_en="Mind map mode",
        details=(
            "Кнопка «Mind map» на панели справа переключает граф в "
            "дерево: связанные записи раскладываются по веткам с "
            "читаемыми подписями — так проще изучать окружение клиента."
        ),
        details_en=(
            "The Mind map button on the right-hand toolbar turns the "
            "graph into a tree: linked records unfold along branches "
            "with readable labels — easier to study a customer "
            "neighbourhood."
        ),
    )

    org_node = mindmap.locator("g.node-hit", has_text=org_name).first
    await org_node.click(button="right")
    context_menu = page.locator("crm-graph-context-menu")
    await expect(context_menu).to_be_visible(timeout=30_000)
    await scenario.step(
        "Меню действий узла",
        page,
        screenshot_name="graph-node-menu",
        label_en="Node action menu",
        details=(
            "Правая кнопка по узлу открывает меню: «Открыть карточку», "
            "приблизить узел, построить путь от него или перестроить "
            "граф вокруг выбранной записи."
        ),
        details_en=(
            "Right-click a node to open the menu: Open card, zoom to "
            "the node, build a path from it, or rebuild the graph "
            "around the chosen record."
        ),
    )

    await context_menu.get_by_role("button", name=re.compile("Открыть карточку|Open card")).click()
    entity_page = page.locator("crm-entity-detail-page")
    await expect(entity_page).to_be_visible(timeout=60_000)
    await expect(
        entity_page.get_by_text(org_name, exact=False).first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Карточка записи из графа",
        page,
        screenshot_name="graph-entity-card",
        label_en="Record card from the graph",
        details=(
            "«Открыть карточку» ведёт на страницу записи: поля, связи, "
            "заметки и задачи клиента.\n\n"
            "**Итог.** Граф — это живая карта картотеки: нашли узел — "
            "и сразу в карточке."
        ),
        details_en=(
            "Open card takes you to the record page: fields, links, "
            "notes and customer tasks.\n\n"
            "**Summary.** The graph is a live map of the card index: "
            "find a node — and you are already in the card."
        ),
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_crm_mindmap_legacy_path_redirects_to_graph_workspace(
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(f"{crm_ui.origin}/crm/mindmap", wait_until="domcontentloaded")
    await expect(ui_page_system).to_have_url(
        re.compile(r'/crm/graph\?.*view=mindmap'),
        timeout=60_000,
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_crm_mindmap_legacy_with_root_redirects(
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(
        f"{crm_ui.origin}/crm/mindmap/entity_legacy_root_test",
        wait_until="domcontentloaded",
    )
    await expect(ui_page_system).to_have_url(
        re.compile(r'/crm/graph\?.*view=mindmap.*root=entity_legacy_root_test'),
        timeout=60_000,
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_crm_graph_workspace_switch_3d_to_mindmap_updates_url(
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(
        f"{crm_ui.origin}/crm/graph?view=3d",
        wait_until="domcontentloaded",
    )
    await expect(ui_page_system.locator("crm-graph-workspace")).to_be_visible(timeout=60_000)
    toolbar = ui_page_system.locator("crm-graph-toolbar")
    await expect(toolbar).to_be_visible(timeout=30_000)
    await toolbar.get_by_role("button", name="Mind map", exact=True).click()
    await expect(ui_page_system).to_have_url(
        re.compile(r'/crm/graph\?.*view=mindmap'),
        timeout=60_000,
    )
    await expect(ui_page_system.locator("crm-mindmap-canvas")).to_be_visible(timeout=30_000)
