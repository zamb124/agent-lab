"""
AX-снимок для control: строим дерево accessibility через Playwright accessibility API
или через JS в странице (CDP Runtime / page.evaluate).

Fallback-режимы запрещены: при недоступности источника поднимается `BrowserCapabilityError`.
"""

from __future__ import annotations

from typing import Any

from apps.browser.control.types import BrowserCapabilityError


async def _dom_accessibility_tree_from_page(
    page: Any,
    *,
    emit_generic_role: bool,
) -> dict[str, Any]:
    """
    Accessibility-подобное дерево, построенное внутри страницы.

    Цель: работать на CDP-движках без стабильного `Accessibility.getFullAXTree`.
    Дерево опирается на DOM + ARIA атрибуты и возвращает минимально полезные узлы:
    role/name/value/children.
    """
    try:
        data = await page.evaluate(
            """(opts) => {
  const EMIT_GENERIC_ROLE = Boolean(opts && opts.emit_generic_role);
  const MAX_NODES = 2500;
  let n = 0;

  const normalize = (s) => String(s || '').trim().replace(/\\s+/g, ' ').slice(0, 400);

  const roleOf = (el) => {
    const r = el.getAttribute && el.getAttribute('role');
    if (r) return String(r).toLowerCase();
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'a' && el.getAttribute('href')) return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'input') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      if (t === 'checkbox') return 'checkbox';
      if (t === 'radio') return 'radio';
      if (t === 'range') return 'slider';
      if (t === 'button' || t === 'submit' || t === 'reset') return 'button';
      return 'textbox';
    }
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return 'combobox';
    if (tag === 'option') return 'option';
    if (tag === 'h1' || tag === 'h2' || tag === 'h3' || tag === 'h4' || tag === 'h5' || tag === 'h6') return 'heading';
    if (EMIT_GENERIC_ROLE) return 'generic';
    return '';
  };

  const valueOf = (el) => {
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      const v = el.value;
      if (v == null) return null;
      const s = normalize(v);
      return s ? s : null;
    }
    return null;
  };

  const nameOf = (el) => {
    const aria = el.getAttribute && el.getAttribute('aria-label');
    if (aria) return normalize(aria);
    const labelledBy = el.getAttribute && el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const ids = labelledBy.split(/\\s+/g).filter(Boolean);
      const parts = [];
      for (const id of ids) {
        const ref = document.getElementById(id);
        if (ref) parts.push(normalize(ref.textContent));
      }
      const joined = normalize(parts.filter(Boolean).join(' '));
      if (joined) return joined;
    }
    if (el.tagName && el.tagName.toLowerCase() === 'img') {
      const alt = el.getAttribute('alt');
      if (alt) return normalize(alt);
    }
    return normalize(el.textContent);
  };

  const visible = (el) => {
    try {
      const style = window.getComputedStyle(el);
      if (!style) return true;
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      const rect = el.getBoundingClientRect();
      return !(rect.width === 0 || rect.height === 0);
    } catch (_) {
      return true;
    }
  };

  const pickChildren = (el) => {
    const out = [];
    for (const ch of el.children || []) {
      if (n >= MAX_NODES) break;
      if (!ch || !ch.tagName) continue;
      out.push(ch);
      if (out.length >= 40) break;
    }
    return out;
  };

  const build = (el) => {
    if (!el || !el.tagName) return null;
    if (n >= MAX_NODES) return null;
    n += 1;
    const node = { name: nameOf(el) };
    const r = roleOf(el);
    if (r && (EMIT_GENERIC_ROLE || r !== 'generic')) node.role = r;
    const v = valueOf(el);
    if (v !== null) node.value = v;
    const children = [];
    for (const ch of pickChildren(el)) {
      if (!visible(ch)) continue;
      const sub = build(ch);
      if (sub) children.push(sub);
      if (children.length >= 40) break;
    }
    if (children.length) node.children = children;
    return node;
  };

  const root = document.documentElement || document.body;
  const tree = root ? build(root) : { role: 'WebArea', name: '' };
  const title = normalize(document.title);
  const out = tree || { role: 'WebArea', name: '' };
  if (!out.name && title) out.name = title;
  return out;
}""",
            {"emit_generic_role": emit_generic_role},
        )
    except Exception as exc:
        raise BrowserCapabilityError(
            "dom_accessibility_unavailable",
            "Не удалось построить accessibility дерево через page.evaluate",
            details={"error": str(exc)},
        ) from exc
    if not isinstance(data, dict):
        raise BrowserCapabilityError(
            "ax_snapshot_invalid",
            "DOM accessibility tree вернул не dict",
            details={"type": type(data).__name__},
        )
    return data


async def dom_accessibility_tree_dict_from_page(
    page: Any,
    *,
    emit_generic_role: bool,
) -> dict[str, Any]:
    """
    Accessibility-подобное дерево, построенное **внутри страницы** через `page.evaluate`.

    Это базовый режим для LLM-friendly snapshot: минимальная структура (role/name/value/children)
    без зависимости от Playwright accessibility API и CDP Accessibility домена.
    """
    return await _dom_accessibility_tree_from_page(page, emit_generic_role=emit_generic_role)


def _str_from_cdp_ax_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, dict):
        raw = v.get("value")
        if raw is not None and not isinstance(raw, (dict, list)):
            return str(raw)
    return ""


def cdp_ax_nodes_to_tree_dict(
    nodes: list[dict[str, Any]],
    *,
    emit_generic_role: bool,
) -> dict[str, Any]:
    if not nodes:
        return {"role": "WebArea", "name": "", "children": []}
    by_id: dict[str, dict[str, Any]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("nodeId")
        if isinstance(nid, str) and nid:
            by_id[nid] = n
    if not by_id:
        return {"role": "WebArea", "name": "", "children": []}
    child_ref: set[str] = set()
    for n in by_id.values():
        for cid in n.get("childIds") or []:
            if isinstance(cid, str):
                child_ref.add(cid)
    root_ids = [i for i in by_id if i not in child_ref]
    if not root_ids:
        root_ids = [next(iter(by_id.keys()))]

    def node_to_dict(n: dict[str, Any]) -> dict[str, Any]:
        role_raw = _str_from_cdp_ax_value(n.get("role"))
        role = role_raw if role_raw else ("generic" if emit_generic_role else "")
        name = _str_from_cdp_ax_value(n.get("name"))
        out: dict[str, Any] = {"name": name}
        if role:
            out["role"] = role
        bid = n.get("backendDOMNodeId")
        if bid is not None and isinstance(bid, int):
            out["backendDOMNodeId"] = bid
        vraw = n.get("value")
        if vraw is not None:
            vs = _str_from_cdp_ax_value(vraw)
            if vs:
                out["value"] = vs
        cids = n.get("childIds")
        children: list[dict[str, Any]] = []
        if isinstance(cids, list):
            for cid in cids:
                if isinstance(cid, str) and cid in by_id:
                    child = by_id[cid]
                    if not child.get("ignored", False) or (child.get("childIds") or []):
                        children.append(node_to_dict(child))
        if children:
            out["children"] = children
        return out

    if len(root_ids) == 1:
        return node_to_dict(by_id[root_ids[0]])
    return {
        "role": "WebArea",
        "name": "",
        "children": [node_to_dict(by_id[rid]) for rid in root_ids if rid in by_id],
    }


async def ax_snapshot_dict_from_page(page: Any, *, emit_generic_role: bool) -> dict[str, Any]:
    acc = getattr(page, "accessibility", None)
    if acc is not None and hasattr(acc, "snapshot"):
        snap = await acc.snapshot()
        if snap is None:
            raise BrowserCapabilityError(
                "ax_snapshot_unavailable",
                "accessibility.snapshot() вернул None",
            )
        if not isinstance(snap, dict):
            raise BrowserCapabilityError(
                "ax_snapshot_invalid",
                "accessibility.snapshot() вернул не dict",
                details={"type": type(snap).__name__},
            )
        return snap
    return await _dom_accessibility_tree_from_page(page, emit_generic_role=emit_generic_role)
