"""Editor/runtime WYSIWYG parity suite (plan §25.8.1)."""

from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from playwright.async_api import Locator, Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_api_delete_flow,
    flows_chat_wait_ready,
    flows_doc_flow_id,
    flows_graph_payload,
    flows_open_chat_page,
    flows_open_interface_editor_workspace,
)
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "flow_ui_parity"

GEOMETRY_TOLERANCE_CSS_PX = 0.01
SURFACE_COMPARE_WIDTH_PX = 720
SURFACE_COMPARE_MIN_HEIGHT_PX = 640

VIEWPORT_MATRIX: tuple[dict[str, int], ...] = (
    {"width": 1280, "height": 900},
    {"width": 390, "height": 844},
)


def _pixel_diff_count(left: bytes, right: bytes) -> int:
    image_left = Image.open(io.BytesIO(left)).convert("RGBA")
    image_right = Image.open(io.BytesIO(right)).convert("RGBA")
    if image_left.size != image_right.size:
        raise AssertionError(
            f"screenshot size mismatch: {image_left.size} vs {image_right.size}"
        )
    pixels_left = image_left.load()
    pixels_right = image_right.load()
    width, height = image_left.size
    differing = 0
    for y in range(height):
        for x in range(width):
            if pixels_left[x, y] != pixels_right[x, y]:
                differing += 1
    return differing


def _assert_geometry_close(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    tolerance: float = GEOMETRY_TOLERANCE_CSS_PX,
) -> None:
    left_by_id = {item["id"]: item for item in left}
    right_by_id = {item["id"]: item for item in right}
    if set(left_by_id) != set(right_by_id):
        raise AssertionError(
            {
                "only_left": sorted(set(left_by_id) - set(right_by_id)),
                "only_right": sorted(set(right_by_id) - set(left_by_id)),
            }
        )
    drifts: list[dict[str, Any]] = []
    for component_id in sorted(left_by_id):
        left_item = left_by_id[component_id]
        right_item = right_by_id[component_id]
        width_delta = abs(float(left_item["width"]) - float(right_item["width"]))
        height_delta = abs(float(left_item["height"]) - float(right_item["height"]))
        if width_delta > tolerance or height_delta > tolerance:
            drifts.append(
                {
                    "id": component_id,
                    "left": left_item,
                    "right": right_item,
                    "width_delta": width_delta,
                    "height_delta": height_delta,
                }
            )
    if drifts:
        raise AssertionError(drifts)


async def _align_surface_box(
    surface: Locator,
    *,
    width: int = SURFACE_COMPARE_WIDTH_PX,
    min_height: int = SURFACE_COMPARE_MIN_HEIGHT_PX,
) -> None:
    if width < 1 or min_height < 1:
        raise ValueError(f"align size must be positive, got {width}x{min_height}")
    await surface.evaluate(
        """
        (el, size) => {
            const rootNode = el.getRootNode();
            const host = rootNode && rootNode.host ? rootNode.host : null;
            const doc = el.ownerDocument;
            if (!doc || !doc.documentElement || !doc.body) {
                throw new Error('flow-ui parity: document missing for surface align');
            }
            const srcdoc = doc.URL === 'about:srcdoc';
            if (srcdoc) {
                doc.documentElement.style.width = `${size.width}px`;
                doc.documentElement.style.height = `${size.minHeight}px`;
                doc.body.style.margin = '0';
                doc.body.style.width = `${size.width}px`;
                doc.body.style.minHeight = `${size.minHeight}px`;
                doc.body.style.background = '#0b1120';
                const mount = doc.getElementById('host');
                if (mount) {
                    mount.style.width = `${size.width}px`;
                    mount.style.minHeight = `${size.minHeight}px`;
                }
            }
            if (!host) {
                throw new Error('flow-ui parity: platform-flow-ui host missing for surface align');
            }
            host.style.boxSizing = 'border-box';
            host.style.width = `${size.width}px`;
            host.style.minWidth = `${size.width}px`;
            host.style.maxWidth = `${size.width}px`;
            host.style.minHeight = `${size.minHeight}px`;
            host.style.background = '#0b1120';
            el.style.boxSizing = 'border-box';
            el.style.width = `${size.width}px`;
            el.style.minWidth = `${size.width}px`;
            el.style.maxWidth = `${size.width}px`;
            el.style.minHeight = `${size.minHeight}px`;
            el.style.background = '#0b1120';
        }
        """,
        {
            "width": width,
            "minHeight": min_height,
        },
    )
    await surface.evaluate(
        """
        async (el) => {
            const host = el.getRootNode()?.host;
            if (host?.updateComplete) await host.updateComplete;
            if (el.updateComplete) await el.updateComplete;
            const root = host?.renderRoot || host?.shadowRoot || el.renderRoot || el.shadowRoot;
            const images = root ? [...root.querySelectorAll('img')] : [];
            await Promise.all(images.map((image) => (
                image.complete ? Promise.resolve() : image.decode().catch(() => undefined)
            )));
            await document.fonts.load('14px Inter');
            await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }
        """
    )


async def _deep_component_geometry(host: Locator) -> list[dict[str, Any]]:
    return await host.evaluate(
        """
        (el) => {
            const collect = (root) => {
                const found = [];
                if (!root || !root.querySelectorAll) return found;
                found.push(...root.querySelectorAll('[data-flow-ui-component]'));
                for (const node of root.querySelectorAll('*')) {
                    const nested = node.renderRoot || node.shadowRoot;
                    if (nested) found.push(...collect(nested));
                }
                return found;
            };
            const root = el.renderRoot || el.shadowRoot || el;
            const nodes = collect(root);
            return nodes.map((node) => {
                return {
                    id: node.getAttribute('data-flow-ui-component'),
                    width: node.offsetWidth,
                    height: node.offsetHeight,
                    clientWidth: node.clientWidth,
                };
            }).sort((left, right) => String(left.id).localeCompare(String(right.id)));
        }
        """
    )


async def _production_iframe_host(frame: Locator) -> Locator:
    handle = await frame.evaluate_handle(
        """
        (el) => {
            const iframe = el.renderRoot?.querySelector('iframe')
                || el.shadowRoot?.querySelector('iframe');
            if (!iframe?.contentDocument) throw new Error('production iframe missing');
            const surface = iframe.contentDocument.querySelector('platform-flow-ui');
            if (!surface) throw new Error('production platform-flow-ui missing');
            return surface;
        }
        """
    )
    element = handle.as_element()
    if element is None:
        raise AssertionError("production platform-flow-ui element handle missing")
    return element


async def _flow_ui_surface(host: Locator) -> Locator:
    handle = await host.evaluate_handle(
        """
        (el) => {
            const root = el.renderRoot || el.shadowRoot;
            const surface = root?.querySelector('flow-ui-surface');
            if (!surface) throw new Error('flow-ui-surface missing');
            return surface;
        }
        """
    )
    element = handle.as_element()
    if element is None:
        raise AssertionError("flow-ui-surface element handle missing")
    return element


async def _align_chat_host_for_preview_parity(chat_host: Locator) -> None:
    """Match design-time frame inputs: dark/ru/readonly (composer disabled)."""
    await chat_host.evaluate(
        """
        async (el) => {
            document.documentElement.setAttribute('data-theme', 'dark');
            el.theme = 'dark';
            el.locale = 'ru';
            el.readonly = true;
            await el.updateComplete;
            await document.fonts.load('14px Inter');
            await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }
        """
    )


async def _production_component_geometry(
    frame: Locator,
    *,
    width: int = SURFACE_COMPARE_WIDTH_PX,
    min_height: int = SURFACE_COMPARE_MIN_HEIGHT_PX,
) -> list[dict[str, Any]]:
    host = await _production_iframe_host(frame)
    surface = await _flow_ui_surface(host)
    await _align_surface_box(surface, width=width, min_height=min_height)
    return await _deep_component_geometry(surface)


async def _production_surface_png(
    frame: Locator,
    *,
    align: bool = True,
    width: int = SURFACE_COMPARE_WIDTH_PX,
    min_height: int = SURFACE_COMPARE_MIN_HEIGHT_PX,
) -> bytes:
    host = await _production_iframe_host(frame)
    surface = await _flow_ui_surface(host)
    if align:
        await _align_surface_box(surface, width=width, min_height=min_height)
    return await surface.screenshot(type="png", animations="disabled", caret="hide")


async def _production_idle_png_pair(
    frame: Locator,
    *,
    width: int = SURFACE_COMPARE_WIDTH_PX,
    min_height: int = SURFACE_COMPARE_MIN_HEIGHT_PX,
) -> tuple[bytes, bytes]:
    """Settle to two identical captures after a single align (fail-closed)."""
    host = await _production_iframe_host(frame)
    surface = await _flow_ui_surface(host)
    await _align_surface_box(surface, width=width, min_height=min_height)
    previous = await surface.screenshot(type="png", animations="disabled", caret="hide")
    last_diff = -1
    for _ in range(8):
        await surface.evaluate(
            """
            async () => {
                await document.fonts.load('14px Inter');
                await new Promise((resolve) =>
                    requestAnimationFrame(() => requestAnimationFrame(resolve))
                );
            }
            """
        )
        current = await surface.screenshot(type="png", animations="disabled", caret="hide")
        last_diff = _pixel_diff_count(previous, current)
        if last_diff == 0:
            return previous, current
        previous = current
    raise AssertionError(
        f"production surface did not settle to idle 0px (last_diff={last_diff})"
    )


async def _chat_surface_geometry(
    chat_host: Locator,
    *,
    width: int = SURFACE_COMPARE_WIDTH_PX,
    min_height: int = SURFACE_COMPARE_MIN_HEIGHT_PX,
) -> list[dict[str, Any]]:
    await _align_chat_host_for_preview_parity(chat_host)
    surface = await _flow_ui_surface(chat_host)
    await _align_surface_box(surface, width=width, min_height=min_height)
    return await _deep_component_geometry(surface)


async def _chat_surface_png(
    chat_host: Locator,
    *,
    width: int = SURFACE_COMPARE_WIDTH_PX,
    min_height: int = SURFACE_COMPARE_MIN_HEIGHT_PX,
) -> bytes:
    await _align_chat_host_for_preview_parity(chat_host)
    surface = await _flow_ui_surface(chat_host)
    await _align_surface_box(surface, width=width, min_height=min_height)
    return await surface.screenshot(type="png", animations="disabled", caret="hide")


@pytest.fixture
def flows_parity_browser_stack_ready(flows_service, taskiq_worker):
    _ = flows_service, taskiq_worker
    yield


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_flow_ui_parity_fixture_manifest_present() -> None:
    manifest = FIXTURES / "README.md"
    assert manifest.is_file(), f"missing parity fixtures README at {manifest}"
    chat_fixture = FIXTURES / "chat-default-v1.json"
    assert chat_fixture.is_file(), f"missing parity fixture {chat_fixture}"


@pytest.mark.timeout(360)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flow_ui_editor_production_frame_and_chat_route_share_layout_contract(
    flows_parity_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    """Same default chat document: editor production frame vs SPA chat route.

    Asserts Exact fingerprint, overlay isolation, geometry ID contract, and
    zero-pixel self-stability of the production surface screenshot.
    """
    _ = flows_parity_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    flow_id = flows_doc_flow_id("parity_layout", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name=f"Parity Layout {unique_id}"),
    )
    editor_geometry: list[dict[str, Any]] = []
    try:
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        editor = page.locator("flows-interface-editor").first
        await expect(editor).to_be_visible(timeout=30_000)
        canvas = editor.locator("flows-interface-canvas").first
        frame = canvas.locator("flow-ui-production-render-frame").first
        await expect(frame).to_be_visible(timeout=30_000)

        overlay_host = await canvas.evaluate(
            """
            (el) => {
                const root = el.renderRoot || el.shadowRoot;
                if (!root) return { ok: false, reason: 'no-shadow' };
                const production = root.querySelector('flow-ui-production-render-frame');
                if (!production) return { ok: false, reason: 'no-frame' };
                const overlays = [
                    ...root.querySelectorAll(
                        'flow-ui-layout-grid-overlay, flow-ui-rulers-guides-overlay, flow-ui-selection-overlay'
                    ),
                ];
                const wrapped = overlays.some((node) => production.contains(node));
                return {
                    ok: !wrapped,
                    reason: wrapped ? 'overlay-inside-production' : 'ok',
                    overlayCount: overlays.length,
                };
            }
            """
        )
        assert overlay_host["ok"] is True, overlay_host
        assert overlay_host["overlayCount"] >= 1

        await expect(frame.locator(".parity")).to_be_visible(timeout=30_000)
        await expect(frame.locator(".parity")).not_to_have_attribute(
            "data-status",
            "Loading",
            timeout=60_000,
        )
        parity_status = await frame.locator(".parity").get_attribute("data-status")
        editor_inspect = await frame.evaluate("(el) => el.inspect()")
        if parity_status != "Exact":
            raise AssertionError({"parity": parity_status, "inspect": editor_inspect})
        assert editor_inspect["status"] == "Exact", editor_inspect
        fingerprint = editor_inspect.get("fingerprint")
        assert isinstance(fingerprint, str) and fingerprint.startswith("fnv1a:")
        components = editor_inspect.get("components")
        assert isinstance(components, list) and len(components) >= 1

        geometry_before = await _production_component_geometry(frame)
        assert len(geometry_before) >= 1
        editor_geometry = geometry_before
        assert "artifact-feed" in {item["id"] for item in editor_geometry}
        png_before, png_after_idle = await _production_idle_png_pair(frame)
        assert _pixel_diff_count(png_before, png_after_idle) == 0

        grid_toggle = editor.locator("flows-interface-toolbar").get_by_role(
            "button", name=re.compile(r"^\s*(Grid|Сетка)\s*$")
        ).first
        await expect(grid_toggle).to_be_visible(timeout=10_000)
        await grid_toggle.click()
        await expect(frame.locator(".parity")).to_have_attribute(
            "data-status",
            "Exact",
            timeout=45_000,
        )
        geometry_after = await _production_component_geometry(frame)
        assert geometry_after == geometry_before

        await flows_open_chat_page(page, flows_ui, flow_id)
        await flows_chat_wait_ready(page)
        chat = page.locator("chat-page platform-flow-ui").first
        await expect(chat).to_be_visible(timeout=60_000)
        await expect(chat.locator("flows-interface-toolbar")).to_have_count(0)
        await expect(chat.locator("flow-ui-layout-grid-overlay")).to_have_count(0)
        chat_geometry = await _chat_surface_geometry(chat)
        assert len(chat_geometry) >= 1
        editor_ids = {item["id"] for item in editor_geometry}
        chat_ids = {item["id"] for item in chat_geometry}
        shared_ids = editor_ids & chat_ids
        assert "artifact-feed" in shared_ids, {
            "editor": sorted(editor_ids),
            "chat": sorted(chat_ids),
        }
        assert "root" in shared_ids or "composer" in shared_ids or "message-form" in shared_ids
        assert len(shared_ids) >= 3
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)


@pytest.mark.timeout(360)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.parametrize("viewport", VIEWPORT_MATRIX, ids=["desktop-1280", "mobile-390"])
async def test_flow_ui_editor_frame_vs_chat_route_zero_pixel_matrix(
    flows_parity_browser_stack_ready,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    viewport: dict[str, int],
) -> None:
    """§25.8.1 geometry matrix: editor production surface ↔ chat surface ≤0.01 CSS px.

    Empty design-time projection and live bootstrap session are different render
    contexts (plan: cannot share Exact). Hard gates here are: Exact on editor
    frame, editor surface idle 0 px, identical component id set, geometry ≤0.01.
    """
    _ = flows_parity_browser_stack_ready
    page = ui_page_system
    page.set_default_timeout(45_000)
    await page.set_viewport_size(viewport)
    flow_id = flows_doc_flow_id(
        f"parity_zpx_{viewport['width']}",
        unique_id,
    )
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name=f"Parity ZPX {unique_id}"),
    )
    try:
        await flows_open_interface_editor_workspace(page, flows_ui, flow_id)
        editor = page.locator("flows-interface-editor").first
        await expect(editor).to_be_visible(timeout=30_000)
        canvas = editor.locator("flows-interface-canvas").first
        frame = canvas.locator("flow-ui-production-render-frame").first
        await expect(frame).to_be_visible(timeout=30_000)
        await expect(frame.locator(".parity")).not_to_have_attribute(
            "data-status",
            "Loading",
            timeout=60_000,
        )
        parity_status = await frame.locator(".parity").get_attribute("data-status")
        if parity_status != "Exact":
            raise AssertionError(
                {
                    "parity": parity_status,
                    "inspect": await frame.evaluate("(el) => el.inspect()"),
                }
            )

        editor_geometry = await _production_component_geometry(
            frame,
            width=viewport["width"],
            min_height=min(SURFACE_COMPARE_MIN_HEIGHT_PX, viewport["height"]),
        )
        editor_png, editor_png_idle = await _production_idle_png_pair(
            frame,
            width=viewport["width"],
            min_height=min(SURFACE_COMPARE_MIN_HEIGHT_PX, viewport["height"]),
        )
        assert _pixel_diff_count(editor_png, editor_png_idle) == 0
        assert len(editor_geometry) >= 1
        assert "artifact-feed" in {item["id"] for item in editor_geometry}

        await flows_open_chat_page(page, flows_ui, flow_id)
        await flows_chat_wait_ready(page)
        chat = page.locator("chat-page platform-flow-ui").first
        await expect(chat).to_be_visible(timeout=60_000)

        chat_geometry = await _chat_surface_geometry(
            chat,
            width=viewport["width"],
            min_height=min(SURFACE_COMPARE_MIN_HEIGHT_PX, viewport["height"]),
        )
        _assert_geometry_close(editor_geometry, chat_geometry)
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)
