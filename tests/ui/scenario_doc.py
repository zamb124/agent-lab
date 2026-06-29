"""Генерация пользовательской инструкции (Markdown + скриншоты) из UI E2E теста."""

from __future__ import annotations

import inspect
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Основная готовность перед скриншотом не опирается на networkidle: WS держит соединение открытым.
_READY_MS = 30_000
_VISUAL_READY_MS = 12_000
_STABLE_LAYOUT_FRAMES = 6
# Lit-корни платформенных SPA в E2E (см. tests/ui/apps.py).
_SHELL_SELECTOR = "sync-app, crm-app, rag-app, flows-app, frontend-app, office-app"
_LOADING_SELECTOR = (
    "glass-spinner, "
    ".loading-container, "
    ".loading-spinner, "
    ".loading-state, "
    ".loading-overlay, "
    ".island-loading-overlay, "
    ".motion-skeleton, "
    ".skeleton, "
    "[aria-busy='true'], "
    "[data-loading='true'], "
    "platform-button[loading], "
    "glass-button[loading], "
    "[role='progressbar']"
)


async def _force_light_theme(page: Page) -> None:
    await page.evaluate(
        """
        () => {
            try {
                window.localStorage.setItem('platform_theme', 'light');
            } catch (_) {}
            document.documentElement.removeAttribute('data-platform-theme-lock');
            document.documentElement.setAttribute('data-theme', 'light');
            const meta = document.querySelector('meta[name="theme-color"]');
            if (meta) meta.setAttribute('content', '#ffffff');
        }
        """
    )


async def _await_fonts_ready(page: Page) -> None:
    await page.wait_for_function(
        "() => !document.fonts || document.fonts.status === 'loaded'",
        timeout=_VISUAL_READY_MS,
    )


async def _await_visible_images_ready(page: Page) -> None:
    await page.wait_for_function(
        """
        () => {
            const elements = [];
            const walk = (root) => {
                if (!root || !root.querySelectorAll) return;
                for (const el of root.querySelectorAll('*')) {
                    elements.push(el);
                    if (el.shadowRoot) walk(el.shadowRoot);
                }
            };
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return false;
                if (rect.bottom < 0 || rect.right < 0) return false;
                if (rect.top > window.innerHeight || rect.left > window.innerWidth) return false;
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
            };

            walk(document);
            return elements
                .filter((el) => el instanceof HTMLImageElement && visible(el))
                .every((img) => img.complete && img.naturalWidth > 0);
        }
        """,
        timeout=_VISUAL_READY_MS,
    )


async def _await_no_blocking_loaders(page: Page) -> None:
    await page.wait_for_function(
        """
        (selector) => {
            const matches = [];
            const walk = (root) => {
                if (!root || !root.querySelectorAll) return;
                for (const el of root.querySelectorAll(selector)) matches.push(el);
                for (const el of root.querySelectorAll('*')) {
                    if (el.shadowRoot) walk(el.shadowRoot);
                }
            };
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    return false;
                }
                return true;
            };

            walk(document);
            return !matches.some(visible);
        }
        """,
        arg=_LOADING_SELECTOR,
        timeout=_VISUAL_READY_MS,
    )


async def _await_stable_layout(page: Page) -> None:
    await page.wait_for_function(
        """
        ([shellSelector, frames]) => new Promise((resolve) => {
            let last = '';
            let stableFrames = 0;

            const snapshot = () => {
                const shell = document.querySelector(shellSelector) || document.body;
                const rect = shell.getBoundingClientRect();
                const doc = document.documentElement;
                return [
                    Math.round(rect.width),
                    Math.round(rect.height),
                    Math.round(rect.top),
                    Math.round(rect.left),
                    Math.round(doc.scrollWidth),
                    Math.round(doc.scrollHeight),
                    Math.round(document.body.scrollWidth),
                    Math.round(document.body.scrollHeight),
                    document.body.innerText.length,
                ].join(':');
            };

            const tick = () => {
                const current = snapshot();
                if (current === last) {
                    stableFrames += 1;
                } else {
                    stableFrames = 0;
                    last = current;
                }
                if (stableFrames >= frames) {
                    resolve(true);
                    return;
                }
                requestAnimationFrame(tick);
            };

            requestAnimationFrame(tick);
        })
        """,
        arg=[_SHELL_SELECTOR, _STABLE_LAYOUT_FRAMES],
        timeout=_VISUAL_READY_MS,
    )


async def _await_page_ready(page: Page) -> None:
    """Дождаться DOM, SPA-shell и визуальной стабильности перед снимком инструкции."""
    await page.wait_for_load_state("domcontentloaded", timeout=_READY_MS)
    await page.wait_for_function(
        "() => document.readyState === 'complete'",
        timeout=_READY_MS,
    )
    root = page.locator(_SHELL_SELECTOR)
    if await root.count() > 0:
        await root.first.wait_for(state="visible", timeout=_READY_MS)
    await _await_fonts_ready(page)
    await _await_visible_images_ready(page)
    await _await_no_blocking_loaders(page)
    await _await_stable_layout(page)


async def _await_screenshot_ready(page: Page) -> None:
    await _force_light_theme(page)
    await _await_page_ready(page)
    try:
        await page.wait_for_load_state("networkidle", timeout=1_500)
    except PlaywrightTimeoutError:
        pass
    await _force_light_theme(page)
    await _await_stable_layout(page)


_DOCS_SCENARIOS = _REPO_ROOT / "docs" / "scenarios"
_ENV_DISABLE = "UI_SCENARIO_DOCS"

# Папка по умолчанию при отсутствии tag: docs/scenarios/<service>/general/<slug>/
DEFAULT_SCENARIO_TAG = "general"

_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_\-]{0,63}$")


def _slug_from_node(node_id: str) -> str:
    """Уникальная папка теста: файл + имя теста (без коллизий)."""
    if "::" in node_id:
        file_part, name = node_id.split("::", 1)
        stem = Path(file_part).stem
        safe = re.sub(r"[^\w\-]+", "_", f"{stem}__{name}", flags=re.UNICODE)
        return safe.strip("_")
    return re.sub(r"[^\w\-]+", "_", node_id, flags=re.UNICODE).strip("_")


def _normalize_segment(name: str, field: str) -> str:
    s = (name or "").strip().lower()
    if not s:
        raise ValueError(f"pytest.mark.scenario: пустой {field}")
    if not _SEGMENT_RE.match(s):
        raise ValueError(
            f"pytest.mark.scenario: {field}={name!r} — допустимы латиница, цифры, _, - (сегмент пути docs/scenarios)"
        )
    return s


def _strip_optional(s: object | None) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t or None


@dataclass
class _StepRecord:
    label: str
    label_en: str | None
    details: str | None
    details_en: str | None
    image_rel: str | None


@dataclass
class ScenarioRecorder:
    """Накапливает шаги и скриншоты; в finalize пишет README под docs/scenarios/<service>/<tag>/<slug>/ (slug из doc_slug маркера или из nodeid pytest)."""

    title: str
    description: str
    title_en: str | None
    description_en: str | None
    service: str
    tag: str
    slug: str
    out_dir: Path
    steps: list[_StepRecord] = field(default_factory=list)
    _screenshots_prepared: bool = field(default=False, init=False, repr=False)

    @classmethod
    def from_pytest_node(cls, node) -> ScenarioRecorder:
        m = node.get_closest_marker("scenario")
        if m is None:
            raise ValueError("ScenarioRecorder требует @pytest.mark.scenario(...) на тесте")

        raw_service = m.kwargs.get("service")
        if raw_service is None:
            raise ValueError(
                'Укажите сервис: @pytest.mark.scenario(service="sync", ...) '
                "(sync | flows | crm | rag | frontend — сегмент пути и группа в docs/scenarios)"
            )
        service = _normalize_segment(str(raw_service), "service")

        raw_tag = m.kwargs.get("tag")
        if raw_tag is None or not str(raw_tag).strip():
            tag = DEFAULT_SCENARIO_TAG
        else:
            tag = _normalize_segment(str(raw_tag), "tag")

        title: str | None = m.kwargs.get("title")
        if title is not None:
            title = str(title).strip() or None
        if title is None and m.args:
            title = str(m.args[0]).strip() or None
        description = (m.kwargs.get("description") or "").strip()

        title_en = _strip_optional(m.kwargs.get("title_en"))
        description_en = _strip_optional(m.kwargs.get("description_en"))

        doc = inspect.getdoc(node.function)
        if doc:
            doc = doc.strip()
            if not title:
                lines = doc.split("\n", 1)
                title = lines[0].strip()
                description = lines[1].strip() if len(lines) > 1 else ""
            elif not description:
                description = doc

        if not title:
            title = node.name.replace("test_", "").replace("_", " ").strip().title() or node.name
        resolved_title: str = str(title)

        raw_doc_slug = m.kwargs.get("doc_slug")
        if raw_doc_slug is not None:
            slug = _normalize_segment(str(raw_doc_slug), "doc_slug")
        else:
            slug = _slug_from_node(node.nodeid)
        out_dir = _DOCS_SCENARIOS / service / tag / slug

        return cls(
            title=resolved_title,
            description=description,
            title_en=title_en,
            description_en=description_en,
            service=service,
            tag=tag,
            slug=slug,
            out_dir=out_dir,
        )

    def disabled(self) -> bool:
        v = os.environ.get(_ENV_DISABLE, "").strip().lower()
        return v in ("0", "false", "no", "off")

    def _prepare_screenshot_dir(self) -> Path:
        shot_dir = self.out_dir / "screenshots"
        if not self._screenshots_prepared:
            if shot_dir.exists():
                shutil.rmtree(shot_dir)
            shot_dir.mkdir(parents=True, exist_ok=True)
            self._screenshots_prepared = True
            return shot_dir
        shot_dir.mkdir(parents=True, exist_ok=True)
        return shot_dir

    async def step(
        self,
        label: str,
        page: Page | None = None,
        *,
        full_page: bool = True,
        label_en: str | None = None,
        details: str | None = None,
        details_en: str | None = None,
    ) -> None:
        """Фиксирует шаг; при переданном page ждёт готовность UI и делает скриншот."""
        rel: str | None = None
        if page is not None and not self.disabled():
            n = len(self.steps) + 1
            shot_dir = self._prepare_screenshot_dir()
            fname = f"{n:03d}.png"
            await _await_screenshot_ready(page)
            await page.screenshot(
                path=str(shot_dir / fname),
                full_page=full_page,
                animations="disabled",
                caret="hide",
            )
            rel = f"screenshots/{fname}"
        le = _strip_optional(label_en)
        self.steps.append(
            _StepRecord(
                label=label,
                label_en=le,
                details=_strip_optional(details),
                details_en=_strip_optional(details_en),
                image_rel=rel,
            )
        )

    def finalize(self) -> None:
        if self.disabled():
            return
        # Неполный прогон (failed E2E) не должен затирать готовую инструкцию.
        if len(self.steps) < 2:
            return
        self.out_dir.mkdir(parents=True, exist_ok=True)
        lines: list[str] = [
            f"# {self.title}",
            "",
        ]
        if self.description:
            lines.extend([self.description, ""])
        for i, s in enumerate(self.steps, start=1):
            lines.append(f"## Шаг {i}. {s.label}")
            lines.append("")
            if s.details:
                lines.extend([s.details.strip(), ""])
            if s.image_rel:
                lines.append(f"![{s.label}]({s.image_rel})")
                lines.append("")
        readme = self.out_dir / "README.md"
        readme.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

        en_title = self.title_en or self.title
        en_description = self.description_en if self.description_en is not None else self.description
        en_lines: list[str] = [
            f"# {en_title}",
            "",
        ]
        if en_description:
            en_lines.extend([en_description, ""])
        for i, s in enumerate(self.steps, start=1):
            step_label = s.label_en if s.label_en is not None else s.label
            en_lines.append(f"## Step {i}. {step_label}")
            en_lines.append("")
            step_details = s.details_en if s.details_en is not None else s.details
            if step_details:
                en_lines.extend([step_details.strip(), ""])
            if s.image_rel:
                en_lines.append(f"![{step_label}]({s.image_rel})")
                en_lines.append("")
        (self.out_dir / "README.en.md").write_text("\n".join(en_lines).rstrip() + "\n", encoding="utf-8")
