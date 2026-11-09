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


_GRADIENT_RE = re.compile(
    r"(?P<kind>linear|radial|conic)-gradient\(\s*(?P<body>.*)\)\s*$", re.S | re.I
)
_GRAD_ANGLE_RE = re.compile(r"^(-?\d+(?:\.\d+)?)deg\b")
_COLOR_RE = re.compile(
    r"#(?:[0-9a-fA-F]{3,8})\b|rgba?\([^()]*\)|\b(?:transparent|white|black)\b"
)
_SHADOW_LAYER_RE = re.compile(
    r"^\s*(inset\s+)?(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?(?:\s+(-?[\d.]+)(?:px)?)?\s+(.+?)\s*$",
    re.I,
)


def _parse_css_color(raw: str) -> tuple[float, float, float, float] | None:
    v = raw.strip().lower()
    if v in KEYWORD_COLORS:
        return KEYWORD_COLORS[v]
    match = HEX_RE.fullmatch(v)
    if match:
        return _hex_rgba(match.group(1))
    match = RGB_RE.fullmatch(v)
    if match:
        return _rgb_rgba(match.group("ch"))
    return None


def _split_top_level(raw: str) -> list[str]:
    """Сплит по запятым вне скобок — внутри rgba()/gradient() запятые не считаются."""

    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(raw):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append(raw[start:i])
            start = i + 1
    parts.append(raw[start:])
    return parts


def _parse_gradient(raw: str) -> Json | None:
    """linear/radial-gradient(...) → {kind, angleDeg, stops:[{color,pos}]}."""

    match = _GRADIENT_RE.match(raw.strip())
    if not match:
        return None
    kind = match.group("kind").lower()
    body = match.group("body")
    parts = _split_top_level(body)
    angle = 180.0 if kind == "linear" else None
    if parts and (angle_match := _GRAD_ANGLE_RE.match(parts[0].strip())):
        angle = float(angle_match.group(1))
        parts = parts[1:]
    elif parts and parts[0].strip().startswith("to "):
        named = {"to top": 0.0, "to right": 90.0, "to bottom": 180.0, "to left": 270.0}
        angle = named.get(parts[0].strip().lower())
        parts = parts[1:]
        if angle is None:
            return None
    stops: list[Json] = []
    for i, part in enumerate(parts):
        cm = _COLOR_RE.search(part)
        if not cm:
            return None
        color = _parse_css_color(cm.group(0))
        if color is None:
            return None
        rest = part[cm.end() :].strip()
        pm = re.match(r"([\d.]+)%", rest)
        pos = float(pm.group(1)) / 100 if pm else (0.0 if i == 0 else (1.0 if i == len(parts) - 1 else i / (len(parts) - 1)))
        stops.append({"color": _rgba_obj(color), "position": min(1.0, max(0.0, pos))})
    if len(stops) < 2:
        return None
    return {"kind": kind, "angle": angle, "stops": stops}


def _parse_shadow(raw: str) -> list[Json] | None:
    """CSS box-shadow → список слоёв {inset,x,y,blur,spread,color}; None — не тень."""

    if not re.search(r"\dpx", raw):
        return None
    if re.search(r"(?:linear|radial|conic)-gradient\(|url\(|calc\(|var\(", raw):
        return None
    layers: list[Json] = []
    for layer_raw in _split_top_level(raw):
        match = _SHADOW_LAYER_RE.match(layer_raw.strip())
        if not match:
            return None
        inset, x, y, blur, spread, color_raw = match.groups()
        color = _parse_css_color(color_raw)
        if color is None:
            return None
        layers.append(
            {
                "inset": bool(inset),
                "x": float(x),
                "y": float(y),
                "blur": float(blur),
                "spread": float(spread or 0),
                "color": _rgba_obj(color),
            }
        )
    return layers or None


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
    styles: list[Json] = []
    for name in sorted(blocks):
        values: dict[str, Any] = {}
        kind: str | None = None
        for mode, mode_key in (("Dark", "dark"), ("Light", "light")):
            raw = blocks[name].get(mode_key) or blocks[name].get("dark")
            if raw is None:
                continue
            alias = ALIAS_RE.fullmatch(raw.strip())
            if alias:
                tgt = alias.group(1)
                tgt_raw = blocks.get(tgt, {}).get(mode_key) or blocks.get(tgt, {}).get("dark")
                fallback = alias.group("fallback")
                raw = tgt_raw if tgt_raw is not None else (fallback or "")
            gradient = _parse_gradient(raw.strip())
            if gradient is not None:
                kind = "gradient"
                values[mode] = gradient
                continue
            shadow = _parse_shadow(raw.strip())
            if shadow is not None:
                kind = "shadow"
                values[mode] = shadow
        if kind and values:
            styles.append(
                {
                    "name": _to_figma_name(name),
                    "css": f"--{name}",
                    "kind": kind,
                    "values": values,
                }
            )
    return {
        "collection": DEFAULT_COLLECTION,
        "modes": list(MODES),
        "tokens": tokens,
        "skipped": skipped,
        "styles": styles,
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
  if (t.value === undefined || t.value === null) continue;
  try {
    v.setValueForMode(modeId, t.value);
    stats.values++;
  } catch (e) { stats.errors.push(t.name + ': ' + e.message); }
}
return { collectionId: coll.id, stats };
"""


_ALIAS_JS = """
const spec = SPEC;
const coll = (await figma.variables.getLocalVariableCollectionsAsync()).find(c => c.name === spec.collection);
if (!coll) return { stats: { aliases: 0, errors: ['no collection ' + spec.collection] } };
const modeId = coll.modes[0].modeId;
const local = {};
(await figma.variables.getLocalVariablesAsync()).forEach(v => {
  if (v.variableCollectionId === coll.id) local[v.name] = v;
});
const stats = { aliases: 0, errors: [] };
for (const a of spec.aliases) {
  const v = local[a.name];
  const tgt = local[a.alias];
  if (!v || !tgt) { stats.errors.push(a.name + ' -> ' + a.alias + ' miss'); continue; }
  try {
    v.setValueForMode(modeId, { type: 'VARIABLE_ALIAS', id: tgt.id });
    stats.aliases++;
  } catch (e) { stats.errors.push(a.name + ': ' + e.message); }
}
return { collectionId: coll.id, stats };
"""


_STYLES_JS = """
const spec = SPEC;
const paints = await figma.getLocalPaintStylesAsync();
const effects = await figma.getLocalEffectStylesAsync();
const stats = { created: 0, updated: 0, errors: [] };
function gTransform(angle) {
  const rad = ((angle == null ? 180 : angle) - 90) * Math.PI / 180;
  const c = Math.cos(rad), s = Math.sin(rad);
  return [[c, -s, 0.5], [s, c, 0.5]];
}
for (const s of spec.styles) {
  try {
    if (s.kind === 'gradient') {
      let st = paints.find(p => p.name === s.name);
      if (!st) { st = figma.createPaintStyle(); st.name = s.name; stats.created++; }
      else stats.updated++;
      const stops = s.value.stops.map(x => ({ color: { r: x.color.r, g: x.color.g, b: x.color.b, a: x.color.a }, position: x.position }));
      st.paints = [s.value.kind === 'radial'
        ? { type: 'GRADIENT_RADIAL', gradientTransform: [[1, 0, 0], [0, 1, 0]], gradientStops: stops }
        : { type: 'GRADIENT_LINEAR', gradientTransform: gTransform(s.value.angle), gradientStops: stops }];
    } else {
      let st = effects.find(p => p.name === s.name);
      if (!st) { st = figma.createEffectStyle(); st.name = s.name; stats.created++; }
      else stats.updated++;
      st.effects = s.value.map(l => ({
        type: l.inset ? 'INNER_SHADOW' : 'DROP_SHADOW',
        color: { r: l.color.r, g: l.color.g, b: l.color.b, a: l.color.a },
        offset: { x: l.x, y: l.y }, radius: l.blur, spread: l.spread,
        visible: true, blendMode: 'NORMAL',
      }));
    }
  } catch (e) { stats.errors.push(s.name + ': ' + e.message); }
}
return { stats };
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


_BOARD_JS = r"""
const spec = SPEC;
const FONT_R = { family: 'Inter', style: 'Regular' };
const FONT_M = { family: 'Inter', style: 'Medium' };
const FONT_S = { family: 'Inter', style: 'Semi Bold' };
await figma.loadFontAsync(FONT_R); await figma.loadFontAsync(FONT_M); await figma.loadFontAsync(FONT_S);
await figma.loadAllPagesAsync();
let page = figma.root.children.find(p => p.name === spec.page);
if (!page) { page = figma.createPage(); page.name = spec.page; }
await page.loadAsync();
for (const n of [...page.children]) n.remove();
const colls = await figma.variables.getLocalVariableCollectionsAsync();
const allVars = await figma.variables.getLocalVariablesAsync();
const byColl = {};
for (const c of colls) {
  byColl[c.name] = {};
  for (const v of allVars) if (v.variableCollectionId === c.id) byColl[c.name][v.name] = v;
}
const varsD = byColl[spec.collDark] || {};
const varsL = byColl[spec.collLight] || {};
const rgba = (a) => a ? { r: a[0], g: a[1], b: a[2], a: a.length > 3 ? a[3] : 1 } : { r: 1, g: 0, b: 1, a: 1 };
function txt(str, font, size, color) {
  const t = figma.createText();
  t.fontName = font; t.characters = str; t.fontSize = size;
  t.fills = [{ type: 'SOLID', color: color || { r: 0.6, g: 0.6, b: 0.65 } }];
  return t;
}
function boundFill(node, v, fallback) {
  if (v) {
    try { node.fills = [{ type: 'SOLID', color: fallback, boundVariables: { color: { type: 'VARIABLE_ALIAS', id: v.id } } }]; return; }
    catch (e) {}
  }
  node.fills = [{ type: 'SOLID', color: fallback }];
}
function section(title) {
  const s = figma.createFrame();
  s.name = 'section/' + title;
  s.layoutMode = 'VERTICAL'; s.itemSpacing = 16; s.paddingLeft = s.paddingRight = s.paddingTop = s.paddingBottom = 28;
  s.primaryAxisSizingMode = 'AUTO'; s.counterAxisSizingMode = 'AUTO';
  s.fills = [{ type: 'SOLID', color: { r: 0.08, g: 0.08, b: 0.12 } }];
  s.cornerRadius = 16; s.clipsContent = false;
  s.appendChild(txt(title, FONT_S, 20, { r: 0.95, g: 0.95, b: 1 }));
  return s;
}
function groupFrame(title, width) {
  const g = figma.createFrame();
  g.name = 'group/' + title;
  g.layoutMode = 'VERTICAL'; g.itemSpacing = 10; g.paddingTop = g.paddingBottom = 4;
  g.resize(width, 40);
  g.primaryAxisSizingMode = 'AUTO'; g.counterAxisSizingMode = 'FIXED';
  g.fills = [];
  g.appendChild(txt(title, FONT_M, 13, { r: 0.55, g: 0.6, b: 0.8 }));
  const grid = figma.createFrame();
  grid.name = 'grid';
  grid.layoutMode = 'HORIZONTAL'; grid.layoutWrap = 'WRAP';
  grid.itemSpacing = 12; grid.counterAxisSpacing = 12;
  grid.resize(width, 40);
  grid.primaryAxisSizingMode = 'FIXED'; grid.counterAxisSizingMode = 'AUTO';
  grid.fills = [];
  g.appendChild(grid);
  return { g, grid };
}
function colorCard(t) {
  const card = figma.createFrame();
  card.name = t.n;
  card.layoutMode = 'HORIZONTAL'; card.itemSpacing = 10;
  card.paddingLeft = card.paddingRight = card.paddingTop = card.paddingBottom = 10;
  card.primaryAxisSizingMode = 'AUTO'; card.counterAxisSizingMode = 'AUTO';
  card.fills = [{ type: 'SOLID', color: { r: 0.14, g: 0.15, b: 0.22 } }];
  card.cornerRadius = 10;
  card.strokes = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1, a: 0.08 } }]; card.strokeWeight = 1;
  for (const [v, fb, tag] of [[varsD[t.n], rgba(t.d), 'D'], [varsL[t.n], rgba(t.l), 'L']]) {
    const wrap = figma.createFrame();
    wrap.name = tag; wrap.layoutMode = 'VERTICAL'; wrap.itemSpacing = 4;
    wrap.primaryAxisSizingMode = 'FIXED'; wrap.counterAxisSizingMode = 'FIXED';
    wrap.primaryAxisAlignItems = 'CENTER';
    wrap.resize(56, 76); wrap.fills = [];
    const sw = figma.createRectangle();
    sw.name = tag; sw.resize(56, 56); sw.cornerRadius = 8;
    sw.strokes = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1, a: 0.15 } }]; sw.strokeWeight = 1;
    boundFill(sw, v, fb);
    wrap.appendChild(sw);
    wrap.appendChild(txt(tag, FONT_M, 9, { r: 0.55, g: 0.55, b: 0.6 }));
    card.appendChild(wrap);
  }
  const col = figma.createFrame();
  col.layoutMode = 'VERTICAL'; col.itemSpacing = 4; col.fills = [];
  col.primaryAxisSizingMode = 'AUTO'; col.counterAxisSizingMode = 'AUTO';
  col.appendChild(txt(t.n, FONT_M, 11, { r: 0.9, g: 0.9, b: 0.95 }));
  col.appendChild(txt(t.c, FONT_R, 9));
  card.appendChild(col);
  return card;
}
let y = 0;
function place(node, x) {
  page.appendChild(node); node.x = x; node.y = 0;
  return node.x + node.width + 40;
}
const root = figma.createFrame();
root.name = 'tokens-board';
root.layoutMode = 'HORIZONTAL'; root.itemSpacing = 32; root.paddingLeft = root.paddingTop = root.paddingRight = root.paddingBottom = 32;
root.primaryAxisSizingMode = 'AUTO'; root.counterAxisSizingMode = 'AUTO';
root.fills = [{ type: 'SOLID', color: { r: 0.05, g: 0.05, b: 0.08 } }];
const colW = 1240;
const colorsSec = section('Цвета — ' + spec.collDark + ' / ' + spec.collLight);
const groups = {};
for (const t of spec.colors) { const g = t.n.split('/')[0]; (groups[g] = groups[g] || []).push(t); }
for (const gName of Object.keys(groups).sort()) {
  const { g, grid } = groupFrame(gName + ' (' + groups[gName].length + ')', colW);
  for (const t of groups[gName]) grid.appendChild(colorCard(t));
  colorsSec.appendChild(g);
}
const miscSec = section('Метрики');
for (const gName of Object.keys(spec.floatGroups).sort()) {
  const { g, grid } = groupFrame(gName, colW);
  for (const t of spec.floatGroups[gName]) {
    const chip = figma.createFrame();
    chip.name = t.n; chip.layoutMode = 'HORIZONTAL'; chip.itemSpacing = 8;
    chip.paddingLeft = chip.paddingRight = 12; chip.paddingTop = chip.paddingBottom = 8;
    chip.primaryAxisSizingMode = 'AUTO'; chip.counterAxisSizingMode = 'AUTO';
    chip.fills = [{ type: 'SOLID', color: { r: 0.14, g: 0.15, b: 0.22 } }]; chip.cornerRadius = 8;
    chip.appendChild(txt(t.n, FONT_R, 10, { r: 0.8, g: 0.8, b: 0.85 }));
    chip.appendChild(txt(String(t.v), FONT_M, 10, { r: 0.6, g: 0.65, b: 0.95 }));
    grid.appendChild(chip);
  }
  miscSec.appendChild(g);
}
const stylesSec = section('Градиенты и тени');
for (const mode of spec.modes) {
  const { g, grid } = groupFrame(mode, colW);
  for (const s of spec.styles.filter(x => x.v[mode])) {
    const sw = figma.createFrame();
    sw.name = s.n; sw.resize(150, 84); sw.cornerRadius = 10; sw.clipsContent = true;
    sw.strokes = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1, a: 0.15 } }]; sw.strokeWeight = 1;
    const vv = s.v[mode];
    if (s.k === 'gradient') {
      const stops = vv.stops.map(x => ({ color: { r: x.color.r, g: x.color.g, b: x.color.b, a: x.color.a }, position: x.position }));
      const rad = (((vv.angle == null ? 180 : vv.angle) - 90) * Math.PI) / 180;
      sw.fills = [{ type: 'GRADIENT_LINEAR', gradientTransform: [[Math.cos(rad), -Math.sin(rad), 0.5], [Math.sin(rad), Math.cos(rad), 0.5]], gradientStops: stops }];
    } else {
      sw.fills = [{ type: 'SOLID', color: { r: 0.16, g: 0.17, b: 0.26 } }];
      sw.effects = vv.map(l => ({ type: l.inset ? 'INNER_SHADOW' : 'DROP_SHADOW', color: { r: l.color.r, g: l.color.g, b: l.color.b, a: l.color.a }, offset: { x: l.x, y: l.y }, radius: l.blur, spread: l.spread, visible: true, blendMode: 'NORMAL' }));
    }
    const lab = txt(s.n, FONT_R, 9, { r: 1, g: 1, b: 1, a: 0.75 });
    lab.x = 4; lab.y = 70;
    const holder = figma.createFrame(); holder.name = s.n; holder.fills = [];
    holder.layoutMode = 'VERTICAL'; holder.itemSpacing = 4; holder.primaryAxisSizingMode = 'AUTO'; holder.counterAxisSizingMode = 'AUTO';
    holder.appendChild(sw); lab.y = 0; holder.appendChild(txt(s.n, FONT_R, 9, { r: 0.75, g: 0.75, b: 0.8 }));
    grid.appendChild(holder);
  }
  stylesSec.appendChild(g);
}
const head = txt('Linnex · Liquid Glass — Design Tokens', FONT_S, 28, { r: 0.95, g: 0.95, b: 1 });
const sub = txt(spec.colors.length + ' colors · ' + spec.floatCount + ' metrics · ' + spec.styles.length + ' styles → collections «' + spec.collDark + '», «' + spec.collLight + '»', FONT_R, 13);
const headCol = figma.createFrame();
headCol.layoutMode = 'VERTICAL'; headCol.itemSpacing = 8; headCol.fills = [];
headCol.primaryAxisSizingMode = 'AUTO'; headCol.counterAxisSizingMode = 'AUTO';
headCol.appendChild(head); headCol.appendChild(sub);
root.appendChild(headCol);
root.appendChild(colorsSec);
root.appendChild(miscSec);
root.appendChild(stylesSec);
page.appendChild(root);
return { pageId: page.id, cards: spec.colors.length };
"""


def _board_payload(spec: Json) -> Json:
    colors: list[Json] = []
    float_groups: dict[str, list[Json]] = {}
    float_count = 0
    for t in spec["tokens"]:
        vals = t["values"]
        dark = vals.get("Dark")
        light = vals.get("Light")
        if t["type"] == "COLOR":
            def _c(v: Any) -> Any:  # pyright: ignore[reportExplicitAny]
                if isinstance(v, dict) and "$alias" in v:
                    return None
                return [v["r"], v["g"], v["b"], v["a"]] if isinstance(v, dict) else v

            colors.append({"n": t["name"], "c": t["css"], "d": _c(dark), "l": _c(light)})
        elif t["type"] == "FLOAT" and isinstance(dark, (int, float)):
            group = t["name"].split("/")[0]
            float_groups.setdefault(group, []).append({"n": t["name"], "v": dark})
            float_count += 1
    styles = [
        {"n": s["name"], "k": s["kind"], "v": s["values"]}
        for s in spec.get("styles", [])
    ]
    return {
        "page": "🎨 Design Tokens",
        "collDark": f"{spec['collection']} · Dark",
        "collLight": f"{spec['collection']} · Light",
        "modes": spec["modes"],
        "colors": colors,
        "floatGroups": float_groups,
        "floatCount": float_count,
        "styles": styles,
    }


def cmd_board(args: argparse.Namespace) -> int:
    spec = extract()
    file_key = str(args.file_key or "") or _project_file_key()
    server = _Server()
    try:
        if not server.start():
            print("board: figma-console-mcp не инициализировался", file=sys.stderr)
            return 2
        _require_design_file(server, file_key or None, wait=float(args.wait_plugin or 30))
        payload = _board_payload(spec)
        code = _BOARD_JS.replace("SPEC", json.dumps(payload, ensure_ascii=False), 1)
        result = _figma_exec(server, code, timeout_ms=300_000)
        print(f"board: {json.dumps(result, ensure_ascii=False)[:400]}")
        return 0
    finally:
        server.stop()


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
            aliases = [
                {"name": t["name"], "alias": t["alias"]}
                for t in mode_tokens
                if t.get("alias")
            ]
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
            for start in range(0, len(aliases), CHUNK_SIZE):
                batch = aliases[start : start + CHUNK_SIZE]
                payload = json.dumps(
                    {"collection": coll_name, "aliases": batch}, ensure_ascii=False
                )
                result = _figma_exec(
                    server,
                    _ALIAS_JS.replace("SPEC", payload, 1),
                )
                stats = result.get("stats", result)
                if not isinstance(stats, dict) or "aliases" not in stats:
                    print(f"  alias вернул неожиданное: {json.dumps(result, ensure_ascii=False)[:500]}", file=sys.stderr)
                    stats = {"aliases": 0, "errors": ["execute-response"]}
                totals["aliases"] += int(stats.get("aliases", 0))
                errors = stats.get("errors", [])
                if isinstance(errors, list):
                    totals["errors"].extend(f"{mode}:{e}" for e in errors)
                print(
                    f"  {mode} aliases {start}-{start + len(batch)}: "
                    f"{stats.get('aliases', 0)} aliases, {len(errors)} errors"
                )
        style_items: list[Json] = []
        for s in spec.get("styles", []):
            for mode in spec["modes"]:
                val = s["values"].get(mode)
                if val is None:
                    continue
                style_items.append(
                    {"name": f"{mode}/{s['name']}", "kind": s["kind"], "value": val}
                )
        if style_items:
            style_stats = {"created": 0, "updated": 0, "errors": 0}
            for start in range(0, len(style_items), CHUNK_SIZE):
                batch = style_items[start : start + CHUNK_SIZE]
                payload = json.dumps({"styles": batch}, ensure_ascii=False)
                result = _figma_exec(
                    server,
                    _STYLES_JS.replace("SPEC", payload, 1),
                )
                stats = result.get("stats", result)
                if not isinstance(stats, dict) or "created" not in stats:
                    print(f"  styles вернул неожиданное: {json.dumps(result, ensure_ascii=False)[:500]}", file=sys.stderr)
                    stats = {"created": 0, "updated": 0, "errors": ["execute-response"]}
                style_stats["created"] += int(stats.get("created", 0))
                style_stats["updated"] += int(stats.get("updated", 0))
                errors = stats.get("errors", [])
                if isinstance(errors, list):
                    totals["errors"].extend(f"style:{e}" for e in errors)
                    style_stats["errors"] += len(errors)
            print(
                f"  styles: +{style_stats['created']} created, "
                f"{style_stats['updated']} updated, {style_stats['errors']} errors"
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
        choices=["extract", "sync", "check", "snapshot", "board"],
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
    if ns.command == "board":
        return cmd_board(ns)
    return cmd_sync(ns)


if __name__ == "__main__":
    sys.exit(main())
