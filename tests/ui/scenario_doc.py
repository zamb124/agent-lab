"""Генерация пользовательской инструкции (Markdown + скриншоты) из UI E2E теста."""

from __future__ import annotations

import inspect
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Page

_REPO_ROOT = Path(__file__).resolve().parents[2]
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
            f"pytest.mark.scenario: {field}={name!r} — допустимы латиница, цифры, _, - (сегмент пути MkDocs)"
        )
    return s


@dataclass
class _StepRecord:
    label: str
    image_rel: str | None


@dataclass
class ScenarioRecorder:
    """Накапливает шаги и скриншоты; в finalize пишет README под docs/scenarios/<service>/<tag>/<slug>/."""

    title: str
    description: str
    service: str
    tag: str
    slug: str
    out_dir: Path
    steps: list[_StepRecord] = field(default_factory=list)

    @classmethod
    def from_pytest_node(cls, node) -> ScenarioRecorder:
        m = node.get_closest_marker("scenario")
        if m is None:
            raise ValueError("ScenarioRecorder требует @pytest.mark.scenario(...) на тесте")

        raw_service = m.kwargs.get("service")
        if raw_service is None:
            raise ValueError(
                'Укажите сервис: @pytest.mark.scenario(service="sync", ...) '
                "(sync | flows | crm | rag | frontend — сегмент пути и группа в MkDocs)"
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

        slug = _slug_from_node(node.nodeid)
        out_dir = _DOCS_SCENARIOS / service / tag / slug

        return cls(
            title=title,
            description=description,
            service=service,
            tag=tag,
            slug=slug,
            out_dir=out_dir,
        )

    def disabled(self) -> bool:
        v = os.environ.get(_ENV_DISABLE, "").strip().lower()
        return v in ("0", "false", "no", "off")

    async def step(self, label: str, page: Page | None = None, *, full_page: bool = False) -> None:
        """Фиксирует шаг; при переданном page делает скриншот текущего состояния."""
        rel: str | None = None
        if page is not None:
            n = len(self.steps) + 1
            shot_dir = self.out_dir / "screenshots"
            shot_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{n:03d}.png"
            await page.screenshot(path=str(shot_dir / fname), full_page=full_page)
            rel = f"screenshots/{fname}"
        self.steps.append(_StepRecord(label=label, image_rel=rel))

    def finalize(self) -> None:
        if self.disabled():
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
            if s.image_rel:
                lines.append(f"![{s.label}]({s.image_rel})")
                lines.append("")
        readme = self.out_dir / "README.md"
        readme.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
