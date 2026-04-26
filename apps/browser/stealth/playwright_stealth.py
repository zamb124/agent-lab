"""
Stealth для Playwright BrowserContext (включая CDP движки вроде Lightpanda).

Зона ответственности:
- только anti-detect (без "humanization");
- только init-script + настройки контекста, которые должны применяться ДО первого документа;
- выбор профиля по `ContextSignature.anti_bot_tier` и совместимость по `stealth_init_version`.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.browser.runtime.types import ContextSignature


@dataclass(frozen=True)
class StealthPlan:
    version: str
    tier: str
    init_scripts: tuple[str, ...]
    extra_http_headers: dict[str, str]


def _accept_language_from_locale(locale: str) -> str:
    if not locale:
        raise ValueError("locale обязателен")
    # Простая форма "en-US,en;q=0.9".
    primary = locale.split(",")[0].strip()
    if not primary:
        raise ValueError("locale должен быть непустым")
    base = primary.split("-")[0].strip()
    if not base:
        raise ValueError("locale должен содержать базовый язык")
    if primary == base:
        return f"{base},{base};q=0.9"
    return f"{primary},{base};q=0.9"


def _build_v1_init_scripts(*, locale: str) -> tuple[str, ...]:
    if not locale:
        raise ValueError("locale обязателен")

    # Важно: init scripts должны быть самодостаточными и без внешних зависимостей.
    # Патчи вдохновлены практиками playwright-stealth, но реализованы локально.
    scripts: list[str] = []

    # 1) navigator.webdriver -> undefined (наиболее частый детектор automation).
    scripts.append(
        r"""
(() => {
  try {
    Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => undefined });
  } catch (_) {}
})();
""".strip()
    )

    # 2) window.chrome runtime (некоторые проверки ожидают наличие chrome.* в Chromium).
    scripts.append(
        r"""
(() => {
  try {
    const w = window;
    if (!('chrome' in w)) {
      Object.defineProperty(w, 'chrome', { value: {}, configurable: true });
    }
    const c = w.chrome;
    if (!('runtime' in c)) {
      Object.defineProperty(c, 'runtime', { value: {}, configurable: true });
    }
  } catch (_) {}
})();
""".strip()
    )

    # 3) navigator.languages (часто пустой/один язык в headless).
    # Здесь сознательно используем только данные из locale, без "угадывания" списков.
    locale_primary = locale.split(",")[0].strip()
    base = locale_primary.split("-")[0].strip()
    languages_json = f'["{locale_primary}","{base}"]'
    scripts.append(
        rf"""
(() => {{
  try {{
    const langs = {languages_json};
    Object.defineProperty(Navigator.prototype, 'languages', {{ get: () => langs }});
  }} catch (_) {{}}
}})();
""".strip()
    )

    # 4) navigator.plugins / navigator.mimeTypes (в headless часто 0).
    scripts.append(
        r"""
(() => {
  try {
    const fakeArray = (items) => {
      const arr = items.slice();
      Object.defineProperty(arr, 'item', { value: (i) => arr[i] ?? null });
      Object.defineProperty(arr, 'namedItem', { value: (n) => arr.find((x) => x && x.name === n) ?? null });
      return arr;
    };
    const plugins = fakeArray([
      { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
      { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
      { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
    ]);
    Object.defineProperty(Navigator.prototype, 'plugins', { get: () => plugins });

    const mimeTypes = fakeArray([
      { type: 'application/pdf', suffixes: 'pdf', description: '', enabledPlugin: plugins[0] },
      { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: plugins[1] },
    ]);
    Object.defineProperty(Navigator.prototype, 'mimeTypes', { get: () => mimeTypes });
  } catch (_) {}
})();
""".strip()
    )

    # 5) permissions.query: Notification часто используется в детекторах.
    scripts.append(
        r"""
(() => {
  try {
    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (originalQuery) {
      window.navigator.permissions.query = (parameters) => {
        if (parameters && parameters.name === 'notifications') {
          return Promise.resolve({ state: Notification.permission });
        }
        return originalQuery(parameters);
      };
    }
  } catch (_) {}
})();
""".strip()
    )

    return tuple(scripts)


def build_stealth_plan(signature: ContextSignature) -> StealthPlan:
    if not isinstance(signature, ContextSignature):
        raise TypeError("signature должен быть ContextSignature")
    if not signature.stealth_init_version:
        raise ValueError("stealth_init_version обязателен")
    if not signature.anti_bot_tier:
        raise ValueError("anti_bot_tier обязателен")

    version = signature.stealth_init_version
    tier = signature.anti_bot_tier

    if version != "v1":
        raise ValueError(f"Неизвестная stealth_init_version={version!r}")

    # Tier намеренно делаем строгим: это вход в анти-бот профиль и должен быть детерминированным.
    # Если нужен новый tier, его следует явно добавить.
    if tier not in ("white", "gray", "black"):
        raise ValueError(f"Неизвестный anti_bot_tier={tier!r}")

    init_scripts = _build_v1_init_scripts(locale=signature.locale)
    headers = {"Accept-Language": _accept_language_from_locale(signature.locale)}
    return StealthPlan(
        version=version,
        tier=tier,
        init_scripts=init_scripts,
        extra_http_headers=headers,
    )


async def apply_stealth_to_context(context: object, signature: ContextSignature) -> None:
    """
    Применить stealth-план к уже созданному BrowserContext ДО открытия страниц.
    """
    plan = build_stealth_plan(signature)

    # Lightpanda в текущей реализации CDP логирует/частично не поддерживает
    # addScriptOnNewDocument (в т.ч. runImmediately) и может вести себя нестабильно.
    # В этом режиме оставляем только заголовки (минимальный safe-path).
    allow_init_scripts = signature.emulate_locale_timezone_via_cdp

    # 1) init scripts
    if allow_init_scripts:
        for script in plan.init_scripts:
            # Playwright API: add_init_script(script: str)
            await context.add_init_script(script)  # type: ignore[attr-defined]

    # 2) headers
    await context.set_extra_http_headers(plan.extra_http_headers)  # type: ignore[attr-defined]

