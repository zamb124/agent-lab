"""Подсветка цели клика на скриншотах UI E2E (зелёная рамка)."""

from __future__ import annotations

from playwright.async_api import BrowserContext

# Слушатель в фазе capture: до обработчиков страницы, элемент ещё на месте для скриншота.
_UI_CLICK_OUTLINE_SCRIPT = """
(() => {
  const OUTLINE = '3px solid #22c55e';
  const OFFSET = '2px';
  function clearPrevious() {
    document.querySelectorAll('[data-pytest-ui-click-highlight]').forEach((el) => {
      el.removeAttribute('data-pytest-ui-click-highlight');
      el.style.outline = '';
      el.style.outlineOffset = '';
    });
  }
  document.addEventListener(
    'click',
    (e) => {
      const t = e.target;
      if (!t || t.nodeType !== Node.ELEMENT_NODE) {
        return;
      }
      if (t === document.documentElement || t === document.body) {
        return;
      }
      clearPrevious();
      t.setAttribute('data-pytest-ui-click-highlight', '1');
      t.style.outline = OUTLINE;
      t.style.outlineOffset = OFFSET;
    },
    true
  );
})();
"""


async def install_click_highlight_on_context(context: BrowserContext) -> None:
    """Вешает на все документы в контексте подсветку последнего клика (для scenario.step / скриншотов)."""
    await context.add_init_script(_UI_CLICK_OUTLINE_SCRIPT)
