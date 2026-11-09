# pyright: reportAny=false
# JSON-RPC wire-данные подпроцесса по природе Any

"""Синк дизайн-токенов tokens.css → Figma Variables.

Источник правды — ``core/frontend/static/assets/css/tokens.css`` и его
``@import`` на ``core/frontend/static/lib/flow-ui/shell/tokens.css``:
``:root`` — режим Dark, ``[data-theme="light"]`` — режим Light.

``uv run python -m scripts.tools.figma_tokens <команда>``:

- ``extract`` — спека токенов (JSON) из CSS: имя ``a/b/c``, тип
  COLOR/FLOAT/STRING, значения по режимам, ``var()`` → алиас;
- ``sync`` — push спеки в Figma через figma-console-mcp: коллекция
  ``Platform``, режимы Dark/Light; идемпотентно (переменные по имени,
  значения обновляются, алиасы — ``VariableAlias``), по успеху переписывает
  ``figma_tokens.snapshot.json``;
- ``check`` — дрейф-гейт: extract против snapshot; расходится — FAIL
  «прогони sync»;
- ``snapshot`` — переписать snapshot без push (baseline; Figma-сторона
  догоняется следующим sync).

Целевой файл — ``.cursor/figma.json`` (``fileKey``, ``collection``); без
fileKey sync работает с активным файлом моста. Файл обязан быть Design
(``editorType: figma``): на FigJam-борде переменные не создаются.

Значения, которые не ложатся в Variables (градиенты, многослойные тени,
calc/clamp/env, filter, url), уходят в ``skipped`` спеки — это paint/effect
styles, а не переменные.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, TypedDict

from scripts.tools.figma_mcp import _Server

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN_SOURCES = (
    REPO_ROOT / "core/frontend/static/assets/css/tokens.css",
    REPO_ROOT / "core/frontend/static/lib/flow-ui/shell/tokens.css",
)
SNAPSHOT_PATH = REPO_ROOT / "scripts/tools/figma_tokens.snapshot.json"
FIGMA_JSON = REPO_ROOT / ".cursor/figma.json"
DEFAULT_COLLECTION = "Platform"
MODES = ("Dark", "Light")
CHUNK_SIZE = 120

Json = dict[str, Any]  # pyright: ignore[reportExplicitAny] — wire-данные JSON-RPC

BLOCK_RE = re.compile(r"(?P<sel>[^{}]+)\{(?P<body>[^{}]*)\}")
LIGHT_SEL_RE = re.compile(r"data-theme=['\"]light['\"]")
VAR_RE = re.compile(r"--([a-zA-Z0-9_-]+)\s*:\s*(.*?);", re.S)
ALIAS_RE = re.compile(r"var\(\s*--([a-zA-Z0-9_-]+)\s*(?:,(?P<fallback>.*))?\)", re.S)
HEX_RE = re.compile(r"#([0-9a-fA-F]{3,8})")
RGB_RE = re.compile(r"rgba?\((?P<ch>[0-9.,\s%]+)\)")
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

# Значения, не ложащиеся в Figma Variables — уходят в skipped с причиной.
SKIP_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:linear|radial|conic)-gradient\("), "gradient"),
    (re.compile(r"drop-shadow\(|inset\b|^\s*\d+px\s+-?\d+px|,\s*0?\s*\d+px\s+-?\d+px"), "shadow"),
    (re.compile(r"calc\(|clamp\(|env\(|\bmin\(|\bmax\("), "computed"),
    (re.compile(r"var\("), "compound"),  # var() внутри составного значения
    (re.compile(r"url\("), "asset"),
    (re.compile(r"brightness\(|saturate\(|invert\(|blur\("), "css-filter"),
    (re.compile(r"\bsolid\b|\bdashed\b|\bdotted\b"), "border-shorthand"),
)

KEYWORD_COLORS: dict[str, tuple[float, float, float, float]] = {
    "transparent": (0.0, 0.0, 0.0, 0.0),
    "white": (1.0, 1.0, 1.0, 1.0),
    "black": (0.0, 0.0, 0.0, 1.0),
}


class TokenSpec(TypedDict, total=False):
    name: str
    css: str
    type: str
    values: dict[str, Any]  # pyright: ignore[reportExplicitAny] — литерал или {"$alias": name}
    alias: bool


def _to_figma_name(css_name: str) -> str:
    return css_name.replace("-", "/")


def _parse_blocks() -> dict[str, dict[str, str]]:
    """var_name -> {'dark': raw, 'light': raw}; поздние :root блоки мержатся."""

    out: dict[str, dict[str, str]] = {}
    for path in TOKEN_SOURCES:
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for block in BLOCK_RE.finditer(text):
            sel = block.group("sel").split(";")[-1].strip()
            if LIGHT_SEL_RE.search(sel):
                mode = "light"
            elif sel == ":root":
                mode = "dark"
            else:
                continue
            for var in VAR_RE.finditer(block.group("body")):
                name = var.group(1)
                entry = out.setdefault(name, {})
                if mode not in entry:
                    entry[mode] = var.group(2).strip()
    return out


def _hex_rgba(digits: str) -> tuple[float, float, float, float]:
    if len(digits) in (3, 4):
        digits = "".join(ch * 2 for ch in digits)
    r = int(digits[0:2], 16) / 255
    g = int(digits[2:4], 16) / 255
    b = int(digits[4:6], 16) / 255
    a = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
    return (r, g, b, a)


def _rgb_rgba(channels: str) -> tuple[float, float, float, float]:
    parts = [p.strip() for p in channels.split(",") if p.strip()]
    vals: list[float] = []
    for i, part in enumerate(parts[:4]):
        num = float(part.rstrip("%"))
        vals.append(num / 100 if part.endswith("%") else (num / 255 if i < 3 else num))
    while len(vals) < 3:
        vals.append(0.0)
    if len(vals) == 3:
        vals.append(1.0)
    return (vals[0], vals[1], vals[2], vals[3])


def _rgba_obj(value: tuple[float, float, float, float]) -> Json:
    return {"r": value[0], "g": value[1], "b": value[2], "a": value[3]}


def _classify_literal(raw: str) -> tuple[str, Any] | tuple[None, str]:
    """(kind, value) для литерала; (None, причина) для неподдерживаемого."""

    v = raw.strip()
    if v.lower() in KEYWORD_COLORS:
        return ("COLOR", _rgba_obj(KEYWORD_COLORS[v.lower()]))
    match = HEX_RE.fullmatch(v)
    if match:
        return ("COLOR", _rgba_obj(_hex_rgba(match.group(1))))
    match = RGB_RE.fullmatch(v)
    if match:
        return ("COLOR", _rgba_obj(_rgb_rgba(match.group("ch"))))
    if v.startswith("cubic-bezier(") or v in {
        "linear", "ease", "ease-in", "ease-out", "ease-in-out", "step-start", "step-end",
    }:
        return ("STRING", v)
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(px|rem|em|ms|s|%)?", v)
    if match:
        num = float(match.group(1))
        unit = match.group(2)
        if unit == "ms":
            num = num / 1000
        elif unit in ("rem", "em"):
            num = num * 16
        return ("FLOAT", num)
    for pattern, reason in SKIP_PATTERNS:
        if pattern.search(v):
            return (None, reason)
    if v in {"inherit", "initial", "unset", "revert", "none", "auto"}:
        return (None, "css-keyword")
    # Строки (шрифтовые стеки, ключевые слова) — STRING; без управляющих.
    if re.fullmatch(r"[\w\s.,'\"()/%+-]+", v) and not re.search(r"[{};]|--", v):
        return ("STRING", v)
    return (None, "unclassified")


def _resolve(
    name: str,
    mode: str,
    blocks: dict[str, dict[str, str]],
    seen: frozenset[str] = frozenset(),
) -> tuple[str, Any] | tuple[None, str]:
    """Значение var_name в режиме: литерал, {"$alias": name} или пропуск."""

    raw = blocks.get(name, {}).get(mode) or blocks.get(name, {}).get("dark")
    if raw is None:
        return (None, "undefined")
    alias = ALIAS_RE.fullmatch(raw)
    if alias:
        target = alias.group(1)
        if target in blocks and target not in seen:
            return ("ALIAS", target)
        fallback = alias.group("fallback")
        if fallback is not None:
            inner = ALIAS_RE.search(fallback)
            if inner and inner.group(1) in blocks and inner.group(1) not in seen:
                return ("ALIAS", inner.group(1))
            return _classify_literal(fallback)
        return (None, "alias-miss")
    return _classify_literal(raw)


def _token_type(
    name: str,
    blocks: dict[str, dict[str, str]],
    seen: frozenset[str] = frozenset(),
) -> str | None:
    """resolvedType токена: по литералу; алиас — тип цели (транзитивно)."""

    if name in seen:
        return None
    raw = blocks.get(name, {}).get("dark") or blocks.get(name, {}).get("light")
    if raw is None:
        return None
    alias = ALIAS_RE.fullmatch(raw)
    if alias:
        target = alias.group(1)
        if target in blocks:
            return _token_type(target, blocks, seen | {name})
        fallback = alias.group("fallback")
        if fallback is not None:
            kind, _ = _classify_literal(ALIAS_RE.sub("", fallback).strip() or fallback)
            return kind
        return None
    kind, _ = _classify_literal(raw)
    return kind


def extract() -> Json:
    """Спека токенов из TOKEN_SOURCES — детерминированная (сортировка по имени)."""

    blocks = _parse_blocks()
    tokens: list[TokenSpec] = []
    skipped: list[Json] = []
    for name in sorted(blocks):
        resolved = _token_type(name, blocks)
        if resolved is None:
            raw = blocks[name].get("dark") or blocks[name].get("light") or ""
            alias = ALIAS_RE.fullmatch(raw.strip())
            if alias:
                reason = f"alias-unsupported:{alias.group(1)}"
            else:
                _, reason = _classify_literal(raw)
            skipped.append({"css": f"--{name}", "reason": reason or "unresolvable"})
            continue
        values: dict[str, Any] = {}
        reasons: set[str] = set()
        for mode in MODES:
            mode_key = "dark" if mode == "Dark" else "light"
            kind, val = _resolve(name, mode_key, blocks)
            if kind == "ALIAS":
                target_type = _token_type(str(val), blocks)
                if target_type == resolved:
                    values[mode] = {"$alias": _to_figma_name(str(val))}
                else:
                    kind2, val2 = _resolve(str(val), mode_key, blocks)
                    if kind2 and kind2 != "ALIAS":
                        values[mode] = val2
                    else:
                        reasons.add(f"alias-unsupported:{val}")
            elif kind is not None:
                values[mode] = val
            else:
                reasons.add(f"{mode_key}:{val}")
        if not values:
            skipped.append({"css": f"--{name}", "reason": next(iter(reasons), "empty")})
            continue
        spec: TokenSpec = {
            "name": _to_figma_name(name),
            "css": f"--{name}",
            "type": resolved,
            "values": values,
        }
        if reasons:
            skipped.append({"css": f"--{name}", "reason": ";".join(sorted(reasons))})
        tokens.append(spec)
    return {
        "collection": DEFAULT_COLLECTION,
        "modes": list(MODES),
        "tokens": tokens,
        "skipped": skipped,
    }


def _spec_equal(left: Json, right: Json) -> list[str]:
    diffs: list[str] = []
    lt = {t["name"]: t for t in left.get("tokens", [])}
    rt = {t["name"]: t for t in right.get("tokens", [])}
    for name in sorted(set(lt) - set(rt)):
        diffs.append(f"  + новый токен {name}")
    for name in sorted(set(rt) - set(lt)):
        diffs.append(f"  - удалён токен {name}")
    for name in sorted(set(lt) & set(rt)):
        if lt[name] != rt[name]:
            diffs.append(f"  ~ изменён токен {name}")
    ls = {s["css"] for s in left.get("skipped", [])}
    rs = {s["css"] for s in right.get("skipped", [])}
    for css in sorted(ls - rs):
        diffs.append(f"  + skipped {css}")
    for css in sorted(rs - ls):
        diffs.append(f"  - skipped {css}")
    return diffs


def _write_snapshot(spec: Json) -> None:
    SNAPSHOT_PATH.write_text(
        json.dumps(spec, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _unwrap(resp: Json) -> Json:
    for item in resp.get("result", {}).get("content", []):
        text = str(item.get("text", ""))
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return resp


_SYNC_JS = """
const spec = SPEC;
let coll = (await figma.variables.getLocalVariableCollectionsAsync()).find(c => c.name === spec.collection);
if (!coll) coll = figma.variables.createVariableCollection(spec.collection);
const modeId = coll.modes[0].modeId;
const local = {};
(await figma.variables.getLocalVariablesAsync()).forEach(v => {
  if (v.variableCollectionId === coll.id) local[v.name] = v;
});
const stats = { created: 0, values: 0, aliases: 0, errors: [] };
for (const t of spec.tokens) {
  let v = local[t.name];
  if (!v) {
    try { v = figma.variables.createVariable(t.name, coll, t.type); stats.created++; local[t.name] = v; }
    catch (e) { stats.errors.push(t.name + ' create: ' + e.message); continue; }
  } else if (v.resolvedType !== t.type) {
    stats.errors.push(t.name + ' type ' + v.resolvedType + ' != ' + t.type); continue;
  }
  try { v.setVariableCodeSyntax('WEB', t.css); } catch (e) {}
  try {
    if (t.alias) {
      const tgt = local[t.alias];
      if (!tgt) { stats.errors.push(t.name + ' alias-miss ' + t.alias); continue; }
      v.setValueForMode(modeId, { type: 'VARIABLE_ALIAS', id: tgt.id });
      stats.aliases++;
    } else {
      v.setValueForMode(modeId, t.value);
      stats.values++;
    }
  } catch (e) { stats.errors.push(t.name + ': ' + e.message); }
}
return { collectionId: coll.id, stats };
"""


_RECON_JS = """
const colls = (await figma.variables.getLocalVariableCollectionsAsync()).map(c => ({
  id: c.id, name: c.name, modes: c.modes.map(m => ({ name: m.name, modeId: m.modeId })),
}));
const vars = (await figma.variables.getLocalVariablesAsync()).map(v => ({
  name: v.name, collectionId: v.variableCollectionId, type: v.resolvedType,
}));
return { collections: colls, variables: vars.map(v => v.name + '|' + v.collectionId + '|' + v.type) };
"""


def _figma_exec(server: _Server, code: str, timeout_ms: int = 120_000) -> Json:
    resp = server.tool(
        "figma_execute",
        {"code": code, "timeout": timeout_ms},
    )
    data = _unwrap(resp)
    for key in ("result", "data", "value", "returnValue"):
        inner = data.get(key) if isinstance(data, dict) else None
        if isinstance(inner, dict):
            return inner
    return data


def _project_file_key() -> str | None:
    if not FIGMA_JSON.is_file():
        return None
    try:
        cfg = json.loads(FIGMA_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    key = cfg.get("fileKey")
    return str(key) if key else None


def _require_design_file(server: _Server, file_key: str | None, wait: float = 30) -> Json:
    status: Json = {}
    url = f"https://www.figma.com/design/{file_key}" if file_key else ""
    deadline = time.time() + wait
    while True:
        status = _unwrap(server.tool("figma_get_status", {"probe": True}))
        if url and status.get("currentFileKey") != file_key:
            _unwrap(server.tool("figma_navigate", {"url": url, "lock": True}))
            status = _unwrap(server.tool("figma_get_status", {"probe": True}))
        if not file_key or status.get("currentFileKey") == file_key:
            if status.get("transport", {}).get("active") == "websocket":
                break
        if time.time() >= deadline:
            break
        print("sync: жду Desktop Bridge…", file=sys.stderr)
        time.sleep(3)
    if status.get("transport", {}).get("active") != "websocket":
        raise SystemExit(
            "sync: мост не подключён — откройте Design-файл в Figma Desktop и запустите "
            "Plugins → Development → Figma Desktop Bridge"
        )
    editor = status.get("editorType")
    current = status.get("currentFileKey")
    if file_key and current and current != file_key:
        raise SystemExit(
            f"sync: мост на файле {current} ({status.get('currentFileName')}), "
            f"а проект ждёт {file_key} — откройте Desktop Bridge в целевом файле"
        )
    if editor != "figma":
        raise SystemExit(
            f"sync: активный файл — {editor} ({status.get('currentFileName')}); "
            "переменные создаются только в Design-файле (editorType: figma)"
        )
    return status


def cmd_extract() -> int:
    print(json.dumps(extract(), ensure_ascii=False, indent=1))
    return 0


def cmd_snapshot() -> int:
    spec = extract()
    _write_snapshot(spec)
    print(f"snapshot: {len(spec['tokens'])} токенов, {len(spec['skipped'])} skipped → {SNAPSHOT_PATH.name}")
    return 0


def cmd_check() -> int:
    if not SNAPSHOT_PATH.is_file():
        print("figma_tokens_drift: FAIL — нет snapshot; прогоните `uv run python -m scripts.tools.figma_tokens snapshot`", file=sys.stderr)
        return 1
    current = extract()
    baseline = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    diffs = _spec_equal(current, baseline)
    if diffs:
        print("figma_tokens_drift: FAIL — tokens.css расходится с синкнутым слепком:", file=sys.stderr)
        for line in diffs[:40]:
            print(line, file=sys.stderr)
        if len(diffs) > 40:
            print(f"  … ещё {len(diffs) - 40}", file=sys.stderr)
        print(
            "  правка: `uv run python -m scripts.tools.figma_tokens sync` (Figma открыт, мост запущен) "
            "и закоммитьте figma_tokens.snapshot.json",
            file=sys.stderr,
        )
        return 1
    print(f"figma_tokens_drift: OK ({len(current['tokens'])} токенов)")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    spec = extract()
    file_key = str(args.file_key or "") or _project_file_key()
    server = _Server()
    try:
        if not server.start():
            print("sync: figma-console-mcp не инициализировался", file=sys.stderr)
            return 2
        status = _require_design_file(server, file_key or None, wait=float(args.wait_plugin or 30))
        base = str(args.collection or spec["collection"])

        # Free-план: 1 режим на коллекцию → по коллекции на режим темы.
        collections: list[tuple[str, str, list[Json]]] = []
        for mode in spec["modes"]:
            coll_name = f"{base} · {mode}"
            mode_tokens: list[Json] = []
            for t in spec["tokens"]:
                val = t["values"].get(mode)
                if val is None:
                    continue
                item: Json = {"name": t["name"], "css": t["css"], "type": t["type"]}
                if isinstance(val, dict) and "$alias" in val:
                    item["alias"] = val["$alias"]
                else:
                    item["value"] = val
                mode_tokens.append(item)
            collections.append((mode, coll_name, mode_tokens))

        recon = _figma_exec(server, _RECON_JS)
        coll_ids = {c.get("name"): c.get("id") for c in recon.get("collections", [])}
        existing_by_coll: dict[str, set[str]] = {}
        for raw in recon.get("variables", []):
            name, cid, _typ = str(raw).split("|", 2)
            existing_by_coll.setdefault(cid, set()).add(name)

        print(f"sync: файл «{status.get('currentFileName')}», skipped {len(spec['skipped'])}")
        all_stale: list[str] = []
        for mode, coll_name, mode_tokens in collections:
            desired = {t["name"] for t in mode_tokens}
            existing = existing_by_coll.get(coll_ids.get(coll_name, ""), set())
            stale = sorted(existing - desired)
            all_stale.extend(f"{coll_name}:{n}" for n in stale)
            print(f"  «{coll_name}»: {len(desired)} токенов (новых ~{len(desired - existing)}), stale {len(stale)}")
        if args.dry_run:
            for item in spec["skipped"][:25]:
                print(f"  skipped: {item['css']} ({item['reason']})")
            return 0

        totals = {"created": 0, "values": 0, "aliases": 0, "errors": []}
        for mode, coll_name, mode_tokens in collections:
            for start in range(0, len(mode_tokens), CHUNK_SIZE):
                chunk = mode_tokens[start : start + CHUNK_SIZE]
                payload = json.dumps(
                    {"collection": coll_name, "tokens": chunk}, ensure_ascii=False
                )
                result = _figma_exec(
                    server,
                    _SYNC_JS.replace("SPEC", payload, 1),
                )
                stats = result.get("stats", result)
                if not isinstance(stats, dict) or "created" not in stats:
                    print(f"  execute вернул неожиданное: {json.dumps(result, ensure_ascii=False)[:500]}", file=sys.stderr)
                    stats = {"created": 0, "values": 0, "aliases": 0, "errors": ["execute-response"]}
                totals["created"] += int(stats.get("created", 0))
                totals["values"] += int(stats.get("values", 0))
                totals["aliases"] += int(stats.get("aliases", 0))
                errors = stats.get("errors", [])
                if isinstance(errors, list):
                    totals["errors"].extend(f"{mode}:{e}" for e in errors)
                print(
                    f"  {mode} {start}-{start + len(chunk)}: "
                    f"+{stats.get('created', 0)} vars, {stats.get('values', 0)} values, "
                    f"{stats.get('aliases', 0)} aliases, {len(errors)} errors"
                )
        print(
            f"sync: итого +{totals['created']} переменных, {totals['values']} значений, "
            f"{totals['aliases']} алиасов; ошибок {len(totals['errors'])}; stale {len(all_stale)}"
        )
        for line in totals["errors"][:30]:
            print(f"  error: {line}", file=sys.stderr)
        if all_stale:
            print("  stale (есть в Figma, нет в CSS — не удаляются автоматически):")
            for name in all_stale[:30]:
                print(f"    {name}")
        if totals["errors"]:
            print("sync: завершено с ошибками — snapshot не обновлён", file=sys.stderr)
            return 1
        _write_snapshot(spec)
        print(f"snapshot обновлён: {SNAPSHOT_PATH.name}")
        return 0
    finally:
        server.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    _ = parser.add_argument(
        "command",
        choices=["extract", "sync", "check", "snapshot"],
    )
    _ = parser.add_argument("--file-key", default="", help="ключ Design-файла Figma")
    _ = parser.add_argument("--collection", default="", help=f"коллекция переменных (default {DEFAULT_COLLECTION})")
    _ = parser.add_argument("--dry-run", action="store_true", help="только отчёт, без записи в Figma")
    _ = parser.add_argument(
        "--wait-plugin",
        type=float,
        default=0,
        metavar="SECONDS",
        help="ждать подключения моста перед sync",
    )
    ns = parser.parse_args()
    if ns.command == "extract":
        return cmd_extract()
    if ns.command == "snapshot":
        return cmd_snapshot()
    if ns.command == "check":
        return cmd_check()
    return cmd_sync(ns)


if __name__ == "__main__":
    sys.exit(main())
