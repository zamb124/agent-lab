"""
E2E helpers для Browser Runtime (Lightpanda/CDP): включение теста, выбор CDP URL
и утилиты для измерения времени/размера результатов по шагам сценария.

Тесты должны быть opt-in: запускаются только при явном флаге окружения.
"""

from __future__ import annotations

import cProfile
import io
import json
import os
import pstats
import time
from collections.abc import Awaitable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class StepRow:
    line: int
    step: str
    wall_ms: float
    output_bytes: Optional[int] = None
    output_lines: Optional[int] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class E2eStepReport:
    """Накопление строк сценария и печать таблицы (время, размер сериализации)."""

    scenario_name: str
    steps: list[StepRow] = field(default_factory=list)
    cdp_url_reported: str = ""

    def _next_line(self) -> int:
        return len(self.steps) + 1

    def add(
        self,
        step: str,
        wall_s: float,
        *,
        output_obj: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        ob: Optional[int] = None
        ol: Optional[int] = None
        if output_obj is not None:
            if isinstance(output_obj, str):
                ob = len(output_obj.encode("utf-8"))
                ol = output_obj.count("\n") + (1 if output_obj else 0)
            else:
                raw = json.dumps(output_obj, default=str, ensure_ascii=True)
                ob = len(raw.encode("utf-8"))
        row = StepRow(
            line=self._next_line(),
            step=step,
            wall_ms=round(wall_s * 1000, 3),
            output_bytes=ob,
            output_lines=ol,
            extra=dict(extra) if extra else {},
        )
        self.steps.append(row)

    def format_markdown_table(self) -> str:
        lines: list[str] = []
        head = (
            f"### e2e: {self.scenario_name}\n\n"
            f"CDP: `{self.cdp_url_reported}`\n\n"
            "| # | step | wall_ms | out_bytes | out_lines | extra |\n"
            "|---|------|--------:|----------:|----------:|------|\n"
        )
        lines.append(head)
        for s in self.steps:
            ex = json.dumps(s.extra, ensure_ascii=True) if s.extra else ""
            oln = "" if s.output_lines is None else str(s.output_lines)
            obb = "" if s.output_bytes is None else str(s.output_bytes)
            lines.append(
                f"| {s.line} | {s.step} | {s.wall_ms} | {obb} | {oln} | {ex} |\n"
            )
        return "".join(lines)

    def print_to_stdout(self) -> None:
        print()
        print(self.format_markdown_table().rstrip())
        print()


@contextmanager
def maybe_cprofile() -> Iterator[Optional[cProfile.Profile]]:
    if os.environ.get("BROWSER__E2E_CPROFILE", "").strip() not in (
        "1",
        "true",
        "yes",
    ):
        yield None
        return
    pr = cProfile.Profile()
    pr.enable()
    try:
        yield pr
    finally:
        pr.disable()
        stream = io.StringIO()
        stats = pstats.Stats(pr, stream=stream)
        stats.sort_stats("cumtime")
        stats.print_stats(40)
        print()
        print("--- cProfile (cumtime, top 40) ---")
        print(stream.getvalue())


async def atimed(
    report: E2eStepReport,
    step: str,
    awaitable: Awaitable[Any],
    *,
    output_fn: Callable[[Any], Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    t0 = time.perf_counter()
    result = await awaitable
    wall = time.perf_counter() - t0
    if output_fn is not None:
        out = output_fn(result)
    else:
        out = result
    report.add(step, wall, output_obj=out, extra=extra)
    return result


def summarize_fetch(r: Any) -> dict[str, Any]:
    html = getattr(r, "html", None)
    return {
        "status_code": getattr(r, "status_code", None),
        "final_url": getattr(r, "final_url", None),
        "html_len": len(html) if isinstance(html, str) else 0,
    }


def summarize_visibility_tree(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": v.get("schema"),
        "node_count": v.get("node_count"),
        "url": v.get("url"),
    }


def json_bytes(obj: Any) -> int:
    return len(json.dumps(obj, default=str, ensure_ascii=True).encode("utf-8"))


def e2e_lightpanda_cdp_url() -> str | None:
    u = os.environ.get("BROWSER__E2E_LIGHTPANDA_CDP_URL", "").strip()
    if u:
        return u
    u2 = os.environ.get("BROWSER__CDP_URL", "").strip()
    return u2 or None


def e2e_lightpanda_enabled() -> bool:
    v = os.environ.get("BROWSER__E2E_LIGHTPANDA", "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")
