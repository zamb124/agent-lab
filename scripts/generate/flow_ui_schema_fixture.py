"""JSON Schema грамматики и галерея шаблонов Flow UI как фикстуры для JS-тестов редактора.

Источники — ``GET /flows/api/v1/flow-ui/schema`` (Pydantic ``FlowUIDocument`` +
``x-flow-ui-frozen-state-fields``) и ``GET /flows/api/v1/flow-ui/templates`` (галерея на ``en``,
``OffsetPage``). Фикстуры ``tests/fixtures/flow_ui/schema.json`` и ``templates.json`` читаются
vitest/WTR-тестами ``interface-editor-domain``, ``blocks-matrix`` и ``template-modal``; дрейф ловит
``tests/core/ui_document/test_flow_ui_schema_fixture.py``.

    uv run python -m scripts.generate.flow_ui_schema_fixture          # перезаписать
    uv run python -m scripts.generate.flow_ui_schema_fixture --check  # только сравнить
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.flows.src.flow_ui.schema import flow_ui_schema  # noqa: E402
from apps.flows.src.flow_ui.templates import FlowUITemplate, flow_ui_templates  # noqa: E402
from core.pagination import OffsetPage  # noqa: E402

SCHEMA_FIXTURE = ROOT / "tests/fixtures/flow_ui/schema.json"
TEMPLATES_FIXTURE = ROOT / "tests/fixtures/flow_ui/templates.json"
TEMPLATES_FIXTURE_LIMIT = 200


def render_schema() -> str:
    return json.dumps(flow_ui_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def templates_page() -> OffsetPage[FlowUITemplate]:
    templates = flow_ui_templates("en")
    return OffsetPage[FlowUITemplate](
        items=templates,
        total=len(templates),
        limit=TEMPLATES_FIXTURE_LIMIT,
        offset=0,
    )


def render_templates() -> str:
    return json.dumps(templates_page().model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--check", action="store_true", help="сравнить фикстуры с текущим кодом")
    args = parser.parse_args()
    rendered = {SCHEMA_FIXTURE: render_schema(), TEMPLATES_FIXTURE: render_templates()}
    if args.check:
        stale = [
            path for path, content in rendered.items()
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            for path in stale:
                print(f"{path.relative_to(ROOT)} is stale; run scripts/generate/flow_ui_schema_fixture.py", file=sys.stderr)
            return 1
        print("flow-ui fixtures are up to date")
        return 0
    for path, content in rendered.items():
        _ = path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
