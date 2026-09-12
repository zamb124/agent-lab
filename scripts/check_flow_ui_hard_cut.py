"""Zero-reference gate: Flow UI живёт только поверх чистого A2A 1.0.

Проверки:

1. В ``core/ apps/ tests/ scripts/ docs/openapi/ .cursor/rules/`` нет имён удалённых слоёв:
   A2UI и его каталог, платформенные надстройки над A2A (negotiation/representation/
   interaction parser/session service/OCC ``mutation_id``/``base_revision``), grid-раскладка
   (``row_start``/``column_span``/``container_layout``/``grid-geometry``), дубли состояния
   интерфейса в ExecutionState (``ui_document``/``ui_values``/``ui_state``), старый control plane
   и capability ``ui.*`` кроме ``ui.render``/``ui.navigate``.
2. В зонах Flow UI нет маркеров недоделанности и слоёв совместимости
   (``TODO|FIXME|HACK|XXX|compat|legacy|deprecated|shim|_v2|V2``).
3. Ключи рендереров ``blocks/*.js`` совпадают с типами Pydantic-union ``FlowUIBlock``;
   ``STATE_PATH_PATTERN`` и ``INPUT_BLOCK_TYPES`` в ``protocol/constants.js`` равны
   значениям ``core/flow_ui/document.py``.
4. Бюджеты: ни одного файла > 600 строк в ``flow-ui/`` и ``interface-editor/``;
   ``flow-ui/*.js`` ≤ 9000 строк; редактор (``interface-editor/`` + ``flows-interface-*`` модалки) ≤ 2500.
5. Sandbox блока ``html``: в ``flow-ui/`` нет ``allow-same-origin``/``unsafe-eval``; константы
   CSP/sandbox ``html-sandbox.js`` совпадают с фикстурой ``tests/fixtures/flow_ui/html_sandbox.json``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import get_args

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.flow_ui.document import INPUT_BLOCK_TYPES, STATE_PATH_PATTERN, FlowUIBlock  # noqa: E402

FLOW_UI_LIB = ROOT / "core/frontend/static/lib/flow-ui"
EDITOR_DIR = ROOT / "apps/flows/ui/components/interface-editor"
EDITOR_MODALS = sorted((ROOT / "apps/flows/ui/modals").glob("flows-interface-*.js"))
SANDBOX_FIXTURE = ROOT / "tests/fixtures/flow_ui/html_sandbox.json"

MAX_FILE_LINES = 600
MAX_FLOW_UI_LINES = 9000
MAX_EDITOR_LINES = 2500

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "a2ui",
        re.compile(r"a2ui|A2UI|humanitec\.ai/a2ui|supportedCatalogIds|\bplatformUi\b", re.IGNORECASE),
    ),
    (
        "legacy chat settings",
        re.compile(r"FlowChatSettings|EmbedChatPolicyOverride|resolve_effective_flow_chat"),
    ),
    (
        "legacy chat profile/runtime",
        re.compile(
            r"chat_override|chat-profile|platform-chat|a2a-chat-runtime|"
            r"lib/chat/|@platform/lib/chat"
        ),
    ),
    (
        "legacy ui_event channel",
        re.compile(
            r"ui_events_pending|PendingUIEvent|push_ui_event|"
            r"artifact\.name\s*===\s*['\"]ui_event['\"]"
        ),
    ),
    (
        "legacy flow ui state duplicates",
        re.compile(
            r"\bui_document\b|\bui_values\b|\bui_value\b|\bui_state\b|\bui_interaction\b|\bui_effect_cursor\b|"
            r"ui_template_version|ui_conflict|ui_applied_effect_ids|ui_last_synced_at|"
            r"ui_last_accepted_client_mutation|FlowUITransition|FlowUIInteraction|FlowUIConflict"
        ),
    ),
    (
        "legacy grid layout",
        re.compile(
            r"\brow_start\b|\bcolumn_span\b|\bcontainer_layout\b|grid-geometry|grid_geometry|"
            r"\bsurface_id\b|production-render-frame|render-fingerprint"
        ),
    ),
    (
        "legacy a2a superstructure",
        re.compile(
            r"a2a_representation|A2ARepresentation|representation_service|negotiated_extensions|"
            r"A2A_EXTENSIONS_HEADER|parse_a2a_extensions_header|interaction_parser|FlowUIInboundCommand|"
            r"FlowUIIngressKind|flow_ui_session_service|FlowUISessionService|flow_ui_presenter|"
            r"present_flow_ui_artifact|emit_flow_ui_|flow_ui_contract|FlowUISubmitContract|"
            r"strip_subscribe_platform_metadata|\bmutation_id\b|client_mutation_id|\bbase_revision\b|"
            r"\bexpected_revision\b"
        ),
    ),
    (
        "legacy interface config",
        re.compile(
            r"interface_override|EmbedInterfaceOverride|resolve_flow_interface_config|"
            r"apply_embed_interface_override|flow_ui_agent_identity_image_url|interface\.template|"
            r"interface\.policy|FlowInterfaceConfig|FlowUITemplateConfig"
        ),
    ),
    (
        "legacy control plane",
        re.compile(
            r"interface-profile|interface_profile|InterfaceProfile|platform\.ui\.|"
            r"contract-preview|contract_preview|push_embed_blocks|flow_ui_share_document_id|"
            r"redacted_value_paths"
        ),
    ),
    (
        "legacy ui capabilities",
        re.compile(
            r"ui\.(apply|create_surface|delete_components|delete_data|delete_surface|reset|"
            r"update_components|update_data|set_values|patch_values)\b"
        ),
    ),
]

UNFINISHED_MARKERS = re.compile(
    r"\b(?:TODO|FIXME|HACK|XXX|compat|legacy|deprecated)\b|(?<!lit-)\bshim\b|_v2\b|\bV2\b"
)

# Единственные допустимые упоминания удалённых имён.
ALLOWLIST_PREFIXES = (
    "core/frontend/static/lib/embed-chat/",  # CDN shim для старых embed-снипетов
    "migrations/",  # data-миграции читают старые ключи
    "scripts/check_flow_ui_hard_cut.py",
    "scripts/check_platform_events_canon.py",
    "core/state/execution_state.py",  # FORBIDDEN_* registry перечисляет удалённые поля
    "core/i18n/generated/",  # регенерируется из translations
)

ALLOWLIST_SUBSTRINGS = (
    ".cursor/rules/",  # rules перечисляют удалённые имена как запреты
)


def _iter_files() -> list[Path]:
    roots = [
        ROOT / "apps",
        ROOT / "core",
        ROOT / "tests",
        ROOT / ".cursor" / "rules",
        ROOT / "docs" / "openapi",
        ROOT / "scripts",
    ]
    files: list[Path] = []
    skip = {"node_modules", ".venv", "dist", "vendor", "__pycache__"}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skip for part in path.parts):
                continue
            if path.suffix not in {".py", ".js", ".ts", ".mdc", ".json", ".md", ".sh"}:
                continue
            files.append(path)
    return files


def _allowed(rel: str) -> bool:
    if any(rel.startswith(prefix) for prefix in ALLOWLIST_PREFIXES):
        return True
    return any(token in rel for token in ALLOWLIST_SUBSTRINGS)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _flow_ui_zone_files() -> list[Path]:
    zone: list[Path] = sorted(FLOW_UI_LIB.rglob("*.js"))
    zone.extend(sorted(EDITOR_DIR.glob("*.js")))
    zone.extend(EDITOR_MODALS)
    zone.extend(sorted((ROOT / "core/flow_ui").glob("*.py")))
    zone.extend(sorted((ROOT / "apps/flows/src/api/v1").glob("flow_ui*.py")))
    zone.extend(sorted((ROOT / "apps/flows/src/services").glob("flow_ui*.py")))
    return zone


def _check_forbidden_names(failures: list[str]) -> None:
    for path in _iter_files():
        rel = _rel(path)
        if _allowed(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS:
            if pattern.search(text):
                failures.append(f"{rel}: {label}")
                break

    for legacy_dir in (
        "core/frontend/static/lib/chat",
        "core/a2ui",
        "core/frontend/static/lib/a2ui",
        "core/frontend/static/lib/flow-ui/layout",
        "core/frontend/static/lib/flow-ui/rendering",
        "core/frontend/static/lib/flow-ui/catalog",
        "core/frontend/static/lib/flow-ui/templates",
    ):
        if (ROOT / legacy_dir).exists():
            failures.append(f"{legacy_dir}/: directory must be deleted")


def _check_unfinished_markers(failures: list[str]) -> None:
    for path in _flow_ui_zone_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = UNFINISHED_MARKERS.search(line)
            if match is not None:
                failures.append(f"{_rel(path)}:{number}: unfinished/compat marker {match.group(0)!r}")


def _python_block_types() -> set[str]:
    union = get_args(FlowUIBlock)[0]
    return {str(model.model_fields["type"].default) for model in get_args(union)}


def _js_renderer_keys() -> set[str]:
    """Методы объектов ``export const *_BLOCKS = { ... }`` — по одному рендереру на тип блока."""
    table_start = re.compile(r"^export const [A-Z_]+_BLOCKS = Object\.freeze\(\{$")
    method = re.compile(r"^    ([a-z_]+)\([^)]*\) \{$")
    keys: set[str] = set()
    for path in sorted((FLOW_UI_LIB / "blocks").glob("*.js")):
        if path.name == "registry.js":
            continue
        inside_table = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if table_start.match(line):
                inside_table = True
                continue
            if inside_table and line == "});":
                inside_table = False
                continue
            if inside_table:
                found = method.match(line)
                if found:
                    keys.add(found.group(1))
    return keys


def _check_registry_parity(failures: list[str]) -> None:
    python_types = _python_block_types()
    js_keys = _js_renderer_keys()
    for missing in sorted(python_types - js_keys):
        failures.append(f"blocks/*.js: no renderer for grammar type {missing!r}")
    for extra in sorted(js_keys - python_types):
        failures.append(f"blocks/*.js: renderer {extra!r} has no grammar type")


def _check_grammar_constants(failures: list[str]) -> None:
    constants_path = FLOW_UI_LIB / "protocol/constants.js"
    source = constants_path.read_text(encoding="utf-8")
    pattern = re.search(r"^export const STATE_PATH_PATTERN = /(.+)/;$", source, re.MULTILINE)
    if pattern is None or pattern.group(1) != STATE_PATH_PATTERN:
        failures.append(f"{_rel(constants_path)}: STATE_PATH_PATTERN differs from core/flow_ui/document.py")
    types_block = re.search(
        r"^export const INPUT_BLOCK_TYPES = Object\.freeze\(new Set\(\[\n((?:    '[a-z_]+',\n)+)\]\)\);$",
        source,
        re.MULTILINE,
    )
    if types_block is None:
        failures.append(f"{_rel(constants_path)}: INPUT_BLOCK_TYPES set literal not found")
        return
    js_types = set(re.findall(r"'([a-z_]+)'", types_block.group(1)))
    if js_types != set(INPUT_BLOCK_TYPES):
        failures.append(f"{_rel(constants_path)}: INPUT_BLOCK_TYPES differs from core/flow_ui/document.py")


def _check_budgets(failures: list[str]) -> None:
    flow_ui_files = sorted(FLOW_UI_LIB.rglob("*.js"))
    editor_files = sorted(EDITOR_DIR.glob("*.js")) + EDITOR_MODALS
    for path in flow_ui_files + editor_files:
        lines = _line_count(path)
        if lines > MAX_FILE_LINES:
            failures.append(f"{_rel(path)}: {lines} lines > {MAX_FILE_LINES}")
    flow_ui_total = sum(_line_count(path) for path in flow_ui_files)
    if flow_ui_total > MAX_FLOW_UI_LINES:
        failures.append(f"flow-ui/*.js: {flow_ui_total} lines > {MAX_FLOW_UI_LINES}")
    editor_total = sum(_line_count(path) for path in editor_files)
    if editor_total > MAX_EDITOR_LINES:
        failures.append(f"interface editor: {editor_total} lines > {MAX_EDITOR_LINES}")


def _check_sandbox(failures: list[str]) -> None:
    forbidden = re.compile(r"allow-same-origin|unsafe-eval")
    for path in sorted(FLOW_UI_LIB.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if forbidden.search(line):
                failures.append(f"{_rel(path)}:{number}: sandbox escape {forbidden.search(line).group(0)!r}")
    sandbox_source = (FLOW_UI_LIB / "runtime/html-sandbox.js").read_text(encoding="utf-8")
    csp = re.search(r'^export const FLOW_UI_HTML_CSP = "([^"]+)";$', sandbox_source, re.MULTILINE)
    sandbox = re.search(r"^export const FLOW_UI_HTML_SANDBOX = '([^']+)';$", sandbox_source, re.MULTILINE)
    if csp is None or sandbox is None:
        failures.append("html-sandbox.js: FLOW_UI_HTML_CSP / FLOW_UI_HTML_SANDBOX constants not found")
        return
    fixture = json.loads(SANDBOX_FIXTURE.read_text(encoding="utf-8"))
    if fixture["csp"] != csp.group(1):
        failures.append(f"html-sandbox.js: CSP differs from {_rel(SANDBOX_FIXTURE)}")
    if fixture["sandbox"] != sandbox.group(1):
        failures.append(f"html-sandbox.js: sandbox differs from {_rel(SANDBOX_FIXTURE)}")


def main() -> int:
    failures: list[str] = []
    _check_forbidden_names(failures)
    _check_unfinished_markers(failures)
    _check_registry_parity(failures)
    _check_grammar_constants(failures)
    _check_budgets(failures)
    _check_sandbox(failures)

    if failures:
        print("Flow UI hard-cut gate failed:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("Flow UI hard-cut gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
