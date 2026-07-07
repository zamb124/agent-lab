#!/usr/bin/env python3
"""Bootstrap tests/ui/design-system catalog and component folders."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DS_ROOT = ROOT / "tests" / "ui" / "design-system"
COMPONENTS_DIR = DS_ROOT / "components"
LIB_COMPONENTS = ROOT / "core" / "frontend" / "static" / "lib" / "components"

PRODUCTION = frozenset(
    {
        "platform-button",
        "platform-segmented-control",
        "platform-picker-card",
        "platform-json-editor",
        "platform-field",
    }
)

LEGACY_WTR_SPECS: dict[str, str] = {
    "platform-bottom-sheet-stack": "frontend_core/browser/components/platform-bottom-sheet-stack.spec.js",
    "platform-button": "frontend_core/browser/components/platform-button.spec.js",
    "platform-cron-field": "frontend_core/browser/components/platform-cron-field.spec.js",
    "platform-field": "frontend_core/browser/components/fields.spec.js",
    "platform-file-viewer-modal": "frontend_core/browser/components/platform-file-viewer-modal.spec.js",
    "platform-modal-search-field": "frontend_core/browser/components/platform-modal-search-field.spec.js",
    "platform-modal-stack": "frontend_core/browser/components/platform-modal-stack.spec.js",
    "platform-picker-card": "frontend_core/browser/components/platform-picker-card.spec.js",
    "platform-segmented-control": "frontend_core/browser/components/platform-segmented-control.spec.js",
    "platform-shell-page": "frontend_core/browser/components/platform-shell-page.spec.js",
    "platform-span-attributes-viewer": "frontend_core/browser/components/platform-span-attributes-viewer.spec.js",
    "platform-timezone-picker": "frontend_core/browser/components/platform-timezone-picker.spec.js",
    "platform-trace-viewer": "frontend_core/browser/components/platform-trace-viewer.spec.js",
    "platform-user-chip": "frontend_core/browser/components/platform-user-chip.spec.js",
    "platform-work-item-badge": "frontend_core/browser/components/platform-work-item-badge.spec.js",
}

BACKFILL_BATCH = (
    "platform-breadcrumbs",
    "platform-confirm-modal",
    "platform-icon",
    "platform-modal-stack",
    "platform-switch",
    "platform-help-hint",
    "platform-metric-card",
    "platform-searchable-combobox",
    "platform-variable-input",
    "platform-file-card",
)


_DEFINE_RE = re.compile(
    r"customElements\.define\s*\(\s*['\"](platform-[a-z0-9-]+)['\"]",
    re.MULTILINE,
)


LIB_ROOT = ROOT / "core" / "frontend" / "static" / "lib"


def _discover_components() -> list[tuple[str, str]]:
    """Return (component tag, import path) for each registered platform-* element."""
    found: dict[str, str] = {}
    components_root = LIB_ROOT / "components"
    for path in components_root.rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        for match in _DEFINE_RE.finditer(text):
            tag = match.group(1)
            rel = path.relative_to(LIB_ROOT).as_posix().removesuffix(".js")
            found[tag] = f"@platform/lib/{rel}.js"
    if not found:
        raise RuntimeError("no platform components registered via customElements.define")
    return sorted(found.items(), key=lambda item: item[0])


def _title_en(component: str) -> str:
    return component.removeprefix("platform-").replace("-", " ").title()


def _contract_spec(component: str, import_path: str) -> str:
    legacy = LEGACY_WTR_SPECS.get(component)
    if legacy is not None:
        rel_posix = f"../../../../{legacy}"
        return textwrap.dedent(
            f"""\
            /** L1 contract — reuses legacy WTR spec until inlined. */
            import '{rel_posix}';
            """
        )
    return textwrap.dedent(
        f"""\
        /**
         * {component} — L1 contract (T0 backlog): module registration smoke.
         */
        import {{ expect }} from '../../../../frontend_core/browser/helpers/render.js';
        import '{import_path}';

        describe('{component}', () => {{
            it('registers custom element', async () => {{
                expect(customElements.get('{component}')).to.exist;
            }});
        }});
        """
    )


def _manifest_yaml(component: str, import_path: str) -> str:
    tier = "T1" if component in PRODUCTION else "T0"
    return textwrap.dedent(
        f"""\
        component: {component}
        doc_slug: {component}
        tier: {tier}
        title_ru: {_title_en(component)}
        title_en: {_title_en(component)}
        import: "{import_path}"
        variants:
          - id: default
            props: {{}}
            scenarios: [render]
        playwright:
          min_steps: 2
          min_screenshots: 1
        """
    )


def _readme_ru(component: str, status: str) -> str:
    return textwrap.dedent(
        f"""\
        # {_title_en(component)}

        Платформенный компонент `{component}`.

        Статус документации: **{status}**.

        ## Запуск тестов

        ```bash
        npm run test:ui-kit -- tests/ui/design-system/components/{component}/contract.spec.js
        uv run pytest tests/ui/design-system/components/{component}/playwright.spec.py -v
        ```
        """
    )


def _readme_en(component: str, status: str) -> str:
    return textwrap.dedent(
        f"""\
        # {_title_en(component)}

        Platform component `{component}`.

        Documentation status: **{status}**.

        ## Run tests

        ```bash
        npm run test:ui-kit -- tests/ui/design-system/components/{component}/contract.spec.js
        uv run pytest tests/ui/design-system/components/{component}/playwright.spec.py -v
        ```
        """
    )


def _playwright_spec(component: str, status: str) -> str:
    if status != "production":
        return (
            f'"""pytest placeholder — backlog component; enable when status=production."""\n\n'
            "import pytest\n\n\n"
            f'@pytest.mark.skip(reason="{component}: backlog — Playwright L2 pending")\n'
            "def test_backlog_placeholder() -> None:\n"
            '    raise AssertionError("backlog")\n'
        )
    test_fn = f"test_{component.replace('-', '_')}_default_gallery"
    return textwrap.dedent(
        f"""\
        \"\"\"Playwright L2 doc scenario for {component}.\"\"\"

        from __future__ import annotations

        import pytest

        from tests.ui.design_system_doc import ComponentDocRecorder


        @pytest.mark.ui_component(
            service="platform",
            tag="ui-kit",
            component="{component}",
            variant="default",
            doc_slug="{component}",
        )
        @pytest.mark.asyncio
        async def {test_fn}(
            ui_kit_page,
            component_doc: ComponentDocRecorder,
        ) -> None:
            await ui_kit_page.load("{component}", "default")
            root = ui_kit_page.root_locator
            await root.wait_for(state="visible", timeout=15_000)
            await component_doc.step("Компонент смонтирован в playground", page=ui_kit_page.page)
            await component_doc.screenshot(page=ui_kit_page.page)
            await component_doc.step("Variant default отображается", page=ui_kit_page.page)
        """
    )


def _ensure_component(component: str, import_path: str, *, status: str) -> None:
    folder = COMPONENTS_DIR / component
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.yaml").write_text(_manifest_yaml(component, import_path), encoding="utf-8")
    (folder / "README.md").write_text(_readme_ru(component, status), encoding="utf-8")
    (folder / "README.en.md").write_text(_readme_en(component, status), encoding="utf-8")
    contract = folder / "contract.spec.js"
    if not contract.exists() or status in ("backlog", "backfill"):
        contract.write_text(_contract_spec(component, import_path), encoding="utf-8")
    playwright = folder / "playwright.spec.py"
    if not playwright.exists():
        playwright.write_text(_playwright_spec(component, status), encoding="utf-8")
    shots = folder / "screenshots"
    shots.mkdir(exist_ok=True)


def main() -> None:
    components = _discover_components()
    catalog_entries: list[dict[str, str]] = []
    for component, import_path in components:
        if component in PRODUCTION:
            status = "production"
        elif component in BACKFILL_BATCH:
            status = "backfill"
        else:
            status = "backlog"
        _ensure_component(component, import_path, status=status)
        entry: dict[str, str] = {
            "component": component,
            "doc_slug": component,
            "status": status,
            "tier": "T1" if component in PRODUCTION else "T0",
        }
        if status == "backlog":
            entry["deadline"] = "2026-Q3"
        catalog_entries.append(entry)

    catalog = {"components": catalog_entries}
    DS_ROOT.mkdir(parents=True, exist_ok=True)
    (DS_ROOT / "catalog.yaml").write_text(
        yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"UI Kit design-system bootstrap: {len(catalog_entries)} components")


if __name__ == "__main__":
    main()
