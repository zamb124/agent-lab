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


def _slug_from_node(node_id: str) -> str:
    """Уникальная папка: файл + имя теста (без коллизий)."""
    if "::" in node_id:
        file_part, name = node_id.split("::", 1)
        stem = Path(file_part).stem
        safe = re.sub(r"[^\w\-]+", "_", f"{stem}__{name}", flags=re.UNICODE)
        return safe.strip("_")
    return re.sub(r"[^\w\-]+", "_", node_id, flags=re.UNICODE).strip("_")


@dataclass
class _StepRecord:
    label: str
    image_rel: str | None


@dataclass
class ScenarioRecorder:
    """Накапливает шаги и скриншоты, в finalize пишет README.md под docs/scenarios."""

    title: str
    description: str
    tag: str | None
    slug: str
    out_dir: Path
    steps: list[_StepRecord] = field(default_factory=list)

    @classmethod
    def from_pytest_node(cls, node) -> ScenarioRecorder:
        m = node.get_closest_marker("scenario")
        title: str | None = None
        description = ""
        if m is not None:
            title = m.kwargs.get("title")
            if title is None and m.args:
                title = str(m.args[0])
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

        tag_m = node.get_closest_marker("scenario_tag")
        tag: str | None = None
        if tag_m is not None:
            if tag_m.args:
                tag = str(tag_m.args[0])
            else:
                tag = tag_m.kwargs.get("tag")
                if tag is not None:
                    tag = str(tag)

        slug = _slug_from_node(node.nodeid)
        base = _DOCS_SCENARIOS
        if tag:
            base = base / tag
        out_dir = base / slug

        return cls(
            title=title,
            description=description,
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
