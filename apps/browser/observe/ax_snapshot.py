"""
AX-снимок для control: строим дерево accessibility через JS в странице (page.evaluate).

Fallback-режимы запрещены: при недоступности источника поднимается `BrowserCapabilityError`.
"""

from __future__ import annotations

from typing import Any

from apps.browser.contracts.control_types import BrowserCapabilityError


async def dom_accessibility_tree_dict_from_page(
    page: Any,
) -> dict[str, Any]:
    """
    Accessibility-подобное дерево, построенное внутри страницы.

    Цель: работать на CDP-движках.
    Дерево опирается на DOM + ARIA атрибуты и возвращает минимально полезные узлы:
    role/name/value/children.
    """
    def _is_context_destroyed_error(exc: Exception) -> bool:
        msg = str(exc)
        return "Execution context was destroyed" in msg

    async def _eval_once() -> dict[str, Any]:
        return await page.evaluate(
            """() => {
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
    if (r) node.role = r;
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
        )

    try:
        data = await _eval_once()
    except Exception as exc:
        if _is_context_destroyed_error(exc):
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5_000)
                data = await _eval_once()
            except Exception as exc2:
                raise BrowserCapabilityError(
                    "dom_accessibility_unavailable",
                    "Не удалось построить accessibility дерево через page.evaluate",
                    details={"error": str(exc2)},
                ) from exc2
        else:
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

