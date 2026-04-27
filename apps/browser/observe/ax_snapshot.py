"""
AX-снимок для control: строим компактный интерактивный снимок через JS.

Fallback-режимы запрещены: при недоступности источника поднимается `BrowserCapabilityError`.
"""

from __future__ import annotations

from typing import Any

from apps.browser.contracts.control_types import BrowserCapabilityError


async def dom_accessibility_tree_dict_from_page(
    page: Any,
) -> dict[str, Any]:
    """
    Построить browser-use-подобный snapshot интерактивных элементов.

    Возвращает компактное дерево:
    - root role/name
    - children: только интерактивные элементы (link/button/input/...).
    """
    try:
        data = await page.evaluate(
            """() => {
  const normalize = (s) => String(s).trim().replace(/\\s+/g, ' ').slice(0, 300);

  const roleOf = (el) => {
    const explicit = normalize(el.getAttribute('role') || '').toLowerCase();
    if (explicit) return explicit;
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'a' && el.getAttribute('href')) return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const t = normalize(el.getAttribute('type') || 'text').toLowerCase();
      if (t === 'checkbox') return 'checkbox';
      if (t === 'radio') return 'radio';
      if (t === 'range') return 'slider';
      if (t === 'button' || t === 'submit' || t === 'reset') return 'button';
      return 'textbox';
    }
    if (el.isContentEditable) return 'textbox';
    return '';
  };

  const nameOf = (el) => {
    const aria = normalize(el.getAttribute('aria-label') || '');
    if (aria) return aria;
    const title = normalize(el.getAttribute('title') || '');
    if (title) return title;
    const alt = normalize(el.getAttribute('alt') || '');
    if (alt) return alt;
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      const placeholder = normalize(el.getAttribute('placeholder') || '');
      if (placeholder) return placeholder;
    }
    const text = normalize(el.innerText || el.textContent || '');
    if (text) return text;
    return '';
  };

  const valueOf = (el) => {
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'a') return normalize(el.getAttribute('href') || '');
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return normalize(el.value || '');
    return '';
  };

  const isDisabled = (el) => {
    if (el.hasAttribute('disabled')) return true;
    return normalize(el.getAttribute('aria-disabled') || '').toLowerCase() === 'true';
  };

  const nodes = Array.from(document.querySelectorAll(
    'a[href],button,input,textarea,select,[role],[tabindex],[contenteditable="true"]'
  ));

  const children = [];
  const seen = new Set();
  for (let i = 0; i < nodes.length; i += 1) {
    const el = nodes[i];
    if (!el || !el.tagName) continue;
    if (isDisabled(el)) continue;

    const role = roleOf(el);
    if (!role) continue;

    const name = nameOf(el);
    if (!name) continue;

    const value = valueOf(el);
    const dedupe = `${role}|${name}|${value}`;
    if (seen.has(dedupe)) continue;
    seen.add(dedupe);

    const node = { role, name };
    if (value) node.value = value;
    children.push(node);
    if (children.length >= 500) break;
  }

  return {
    role: 'WebArea',
    name: normalize(document.title || ''),
    children,
  };
}""",
        )
    except Exception as exc:
        raise BrowserCapabilityError(
            "dom_accessibility_unavailable",
            "Не удалось построить интерактивный snapshot через page.evaluate",
            details={"error": str(exc)},
        ) from exc

    if not isinstance(data, dict):
        raise BrowserCapabilityError(
            "ax_snapshot_invalid",
            "DOM snapshot вернул не dict",
            details={"type": type(data).__name__},
        )
    return data

