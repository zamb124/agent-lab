"""HITL custom Interface: host-composer и Submit формы = transport.send."""

from __future__ import annotations

import os

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.hitl_e2e_bridge import (
    hitl_api_assert_turn_role,
    hitl_assert_work_item_open,
    hitl_create_custom_ui_flow,
    hitl_form_submit_interface_config,
    hitl_host_composer_interface_config,
    hitl_start_via_a2a,
    hitl_wait_work_item_terminal,
)
from tests.ui.e2e.worktracker_e2e_helpers import (
    worktracker_claim_task,
    worktracker_hitl_click_send_and_assert_http,
    worktracker_hitl_embedded_chat,
    worktracker_open_task_page,
)
from tests.ui.harness import AppUI

_ = os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_custom_ui_host_composer_completes(
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
    unique_id: str,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    flow_id = f"hitl_c1_{unique_id}"
    title = f"HITL host {unique_id}"
    reply = f"host-complete {unique_id}"
    await hitl_create_custom_ui_flow(
        flows_ui.origin,
        auth_token_system,
        flow_id=flow_id,
        mode="single_reply",
        interface=hitl_host_composer_interface_config(),
        title=title,
    )
    work_item_id = await hitl_start_via_a2a(
        flows_ui.origin,
        auth_token_system,
        flow_id=flow_id,
        text=f"start {unique_id}",
        title_contains=title,
    )
    wt_page = ui_page_system
    editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
    await worktracker_claim_task(wt_page, editor)
    chat = await worktracker_hitl_embedded_chat(editor)
    host_composer = chat.locator(".hitl-host-composer").first
    await expect(host_composer).to_be_visible(timeout=30_000)
    await host_composer.locator("textarea").fill(reply)
    send = host_composer.locator("button.hitl-host-send").first
    await expect(send).to_be_enabled(timeout=10_000)
    await worktracker_hitl_click_send_and_assert_http(wt_page, send)
    await hitl_api_assert_turn_role(
        flows_ui.origin, auth_token_system, work_item_id, reply, "operator"
    )
    await hitl_wait_work_item_terminal(
        worktracker_ui.origin, auth_token_system, work_item_id
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_custom_form_submit_is_operator_ask(
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
    unique_id: str,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    flow_id = f"hitl_c2_{unique_id}"
    title = f"HITL form {unique_id}"
    reply = f"form-ask {unique_id}"
    await hitl_create_custom_ui_flow(
        flows_ui.origin,
        auth_token_system,
        flow_id=flow_id,
        mode="takeover",
        interface=hitl_form_submit_interface_config(),
        title=title,
    )
    work_item_id = await hitl_start_via_a2a(
        flows_ui.origin,
        auth_token_system,
        flow_id=flow_id,
        text=f"start {unique_id}",
        title_contains=title,
    )
    wt_page = ui_page_system
    editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
    await worktracker_claim_task(wt_page, editor)
    chat = await worktracker_hitl_embedded_chat(editor)
    field = chat.locator('[data-flow-ui-component="note-field"] input[type="text"]').first
    await expect(field).to_be_visible(timeout=30_000)
    await field.fill(reply)
    submit = chat.locator('[data-flow-ui-component="submit"] button').first
    await expect(submit).to_be_enabled(timeout=10_000)
    await worktracker_hitl_click_send_and_assert_http(wt_page, submit)
    await hitl_api_assert_turn_role(
        flows_ui.origin, auth_token_system, work_item_id, reply, "operator"
    )
    await hitl_assert_work_item_open(worktracker_ui.origin, auth_token_system, work_item_id)
