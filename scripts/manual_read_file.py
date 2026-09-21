"""Ручной прогон read_file на локальном файле (без flow).

Пример:
  uv run python scripts/manual_read_file.py "АКТЫ СТРАХОВКА.PDF"
  uv run python scripts/manual_read_file.py path/to/file.pdf --page-start 0 --page-end 0
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from apps.flows.tools.files.files import read_file
from core.billing import set_billing_service
from core.context import set_context
from core.files.file_ref import FileRef
from core.models.context_models import Context
from core.models.identity_models import User
from core.state import ExecutionState
from core.types import require_json_array, require_json_object
from tests.fixtures.ai_provider_defaults import make_test_company


@dataclass(frozen=True, slots=True)
class ManualReadFileCliArgs:
    path: Path
    page_start: int
    page_end: int
    preview_chars: int


def _parse_args() -> ManualReadFileCliArgs:
    parser = argparse.ArgumentParser(description="Ручной прогон read_file tool")
    _ = parser.add_argument("path", type=Path, help="Путь к файлу (локальный)")
    _ = parser.add_argument("--page-start", type=int, default=0)
    _ = parser.add_argument("--page-end", type=int, default=-1)
    _ = parser.add_argument("--preview-chars", type=int, default=1200)
    namespace = parser.parse_args()
    return ManualReadFileCliArgs(
        path=cast(Path, namespace.path),
        page_start=cast(int, namespace.page_start),
        page_end=cast(int, namespace.page_end),
        preview_chars=cast(int, namespace.preview_chars),
    )


async def _run(args: ManualReadFileCliArgs) -> int:
    file_path = args.path.resolve()
    if not file_path.is_file():
        print(f"Файл не найден: {file_path}", file=sys.stderr)
        return 1

    from apps.flows.src.container import get_container as get_flows_container

    set_billing_service(get_flows_container().billing_service)
    set_context(
        Context(
            user=User(user_id="manual_user", name="Manual User"),
            active_company=make_test_company(company_id="system", name="System"),
            session_id="manual_session",
            channel="manual",
            metadata={"user_id": "manual_user"},
        )
    )

    file_ref = FileRef(
        original_name=file_path.name,
        url=str(file_path),
        content_type="application/pdf" if file_path.suffix.lower() == ".pdf" else "application/octet-stream",
        file_size=file_path.stat().st_size,
    )
    state = ExecutionState.create(
        task_id="manual_read",
        context_id="manual_ctx",
        user_id="manual_user",
        session_id="manual_flow:manual_ctx",
        files=[file_ref],
    )

    payload = require_json_object(
        await read_file.run(
            {
                "names": [file_ref.original_name],
                "page_start": args.page_start,
                "page_end": args.page_end,
            },
            state,
        ),
        "manual_read_file.payload",
    )
    print("success:", payload.get("success"))
    files = require_json_array(payload.get("files"), "manual_read_file.files")
    if not files:
        print("Нет результатов")
        return 1

    file_result = require_json_object(files[0], "manual_read_file.files[0]")
    print("file success:", file_result.get("success"))
    print("read_lane:", file_result.get("read_lane"))
    if file_result.get("error"):
        print("error:", file_result.get("error"))
        return 1

    results = require_json_array(file_result.get("results"), "manual_read_file.results")
    for item in results:
        page = require_json_object(item, "manual_read_file.result_item")
        text = str(page.get("result", ""))
        preview = text[: args.preview_chars]
        print("---")
        print(f"page {page.get('page_index')} chars={len(text)}")
        print(preview)
        if len(text) > args.preview_chars:
            print("...")
    return 0


def main() -> None:
    cli_args = _parse_args()
    raise SystemExit(asyncio.run(_run(cli_args)))


if __name__ == "__main__":
    main()
