"""Генерация docs/scenarios/platform/ui-kit из Playwright L2 (@pytest.mark.ui_component)."""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Page

from tests.ui.scenario_doc import (
    _await_screenshot_ready,
    _normalize_segment,
    _strip_optional,
    build_screenshot_filename,
    prepare_flat_screenshot_output,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCS_ROOT = _REPO_ROOT / "docs" / "scenarios" / "platform" / "ui-kit"
_ENV_DISABLE = "UI_KIT_DOCS"


@dataclass
class _StepRecord:
    label: str
    label_en: str | None
    details: str | None
    details_en: str | None
    image_rel: str | None


@dataclass
class ComponentDocRecorder:
    """Пишет docs/scenarios/platform/ui-kit/<doc_slug>/ из Playwright ui_component тестов."""

    title: str
    description: str
    component: str
    variant: str
    slug: str
    out_dir: Path
    steps: list[_StepRecord] = field(default_factory=list)
    _screenshots_prepared: bool = field(default=False, init=False, repr=False)

    @classmethod
    def from_pytest_node(cls, node) -> ComponentDocRecorder:
        marker = node.get_closest_marker("ui_component")
        if marker is None:
            raise ValueError("ComponentDocRecorder требует @pytest.mark.ui_component(...)")

        component = marker.kwargs.get("component")
        variant = marker.kwargs.get("variant")
        doc_slug = marker.kwargs.get("doc_slug")
        if not isinstance(component, str) or not component.startswith("platform-"):
            raise ValueError("ui_component marker requires component=platform-*")
        if not isinstance(variant, str) or not variant.strip():
            raise ValueError("ui_component marker requires variant=...")
        if doc_slug is None:
            slug = _normalize_segment(component, "doc_slug")
        else:
            slug = _normalize_segment(str(doc_slug), "doc_slug")

        title = _strip_optional(marker.kwargs.get("title"))
        description = (marker.kwargs.get("description") or "").strip()
        doc = inspect.getdoc(node.function)
        if doc:
            doc = doc.strip()
            if not title:
                lines = doc.split("\n", 1)
                title = lines[0].strip()
                description = lines[1].strip() if len(lines) > 1 else description
            elif not description:
                description = doc
        if not title:
            title = node.name.replace("test_", "").replace("_", " ").strip().title() or node.name

        out_dir = _DOCS_ROOT / slug
        return cls(
            title=str(title),
            description=description,
            component=component,
            variant=variant.strip(),
            slug=slug,
            out_dir=out_dir,
        )

    def disabled(self) -> bool:
        value = os.environ.get(_ENV_DISABLE, "").strip().lower()
        return value in ("0", "false", "no", "off")

    def _prepare_screenshot_output(self) -> Path:
        if not self._screenshots_prepared:
            self._screenshots_prepared = True
            return prepare_flat_screenshot_output(self.out_dir, self.slug)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return self.out_dir

    async def step(
        self,
        label: str,
        page: Page | None = None,
        *,
        full_page: bool = True,
        label_en: str | None = None,
        screenshot_name: str | None = None,
        details: str | None = None,
        details_en: str | None = None,
    ) -> None:
        rel: str | None = None
        if page is not None and not self.disabled():
            step_no = len(self.steps) + 1
            shot_dir = self._prepare_screenshot_output()
            fname = build_screenshot_filename(
                self.slug,
                step_no,
                label,
                label_en=label_en,
                screenshot_name=screenshot_name,
            )
            await _await_screenshot_ready(page)
            await page.screenshot(path=str(shot_dir / fname), full_page=full_page)
            rel = fname
        self.steps.append(
            _StepRecord(
                label=label,
                label_en=label_en,
                details=details,
                details_en=details_en,
                image_rel=rel,
            )
        )

    async def screenshot(
        self,
        page: Page,
        *,
        full_page: bool = True,
        screenshot_name: str | None = None,
    ) -> None:
        if self.disabled():
            return
        step_no = len(self.steps)
        if step_no == 0:
            await self.step(
                "Preview",
                page=page,
                full_page=full_page,
                screenshot_name=screenshot_name,
            )
            return
        shot_dir = self._prepare_screenshot_output()
        last = self.steps[-1]
        fname = last.image_rel or build_screenshot_filename(
            self.slug,
            step_no,
            last.label,
            label_en=last.label_en,
            screenshot_name=screenshot_name,
        )
        await _await_screenshot_ready(page)
        await page.screenshot(path=str(shot_dir / fname), full_page=full_page)
        if last.image_rel is None:
            self.steps[-1] = _StepRecord(
                label=last.label,
                label_en=last.label_en,
                details=last.details,
                details_en=last.details_en,
                image_rel=fname,
            )

    def _render_readme(self, *, lang: str) -> str:
        if lang == "en":
            title = self.title
            intro = self.description or f"UI Kit component `{self.component}` variant `{self.variant}`."
            step_heading = "## Step"
        else:
            title = self.title
            intro = self.description or f"Компонент UI Kit `{self.component}`, variant `{self.variant}`."
            step_heading = "## Шаг"

        lines = [f"# {title}", "", intro, "", f"**Component:** `{self.component}`  ", f"**Variant:** `{self.variant}`", ""]
        for index, step in enumerate(self.steps, start=1):
            label = step.label_en if lang == "en" and step.label_en else step.label
            lines.append(f"{step_heading} {index}. {label}")
            details = step.details_en if lang == "en" and step.details_en else step.details
            if details:
                lines.append("")
                lines.append(details)
            if step.image_rel:
                lines.append("")
                lines.append(f"![Step {index}]({step.image_rel})")
            lines.append("")
        lines.extend(
            [
                "## Run tests locally",
                "",
                "```bash",
                f"npm run test:ui-kit -- tests/ui/design-system/components/{self.component}/contract.spec.js",
                f"uv run pytest tests/ui/design-system/components/{self.component}/playwright.spec.py -v",
                "make ui-doc",
                "```",
                "",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    def finalize(self) -> None:
        if self.disabled():
            return
        if len(self.steps) < 2:
            raise ValueError(f"ComponentDocRecorder {self.slug}: minimum 2 steps required")
        has_shot = any(step.image_rel for step in self.steps)
        if not has_shot:
            raise ValueError(f"ComponentDocRecorder {self.slug}: minimum 1 screenshot required")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "README.md").write_text(self._render_readme(lang="ru"), encoding="utf-8")
        (self.out_dir / "README.en.md").write_text(self._render_readme(lang="en"), encoding="utf-8")
