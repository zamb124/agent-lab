"""
Stealth для Playwright BrowserContext.

Зона ответственности:
- только anti-detect (без "humanization");
- только init-script + настройки контекста, которые должны применяться ДО первого документа;
- выбор профиля по `ContextSignature.anti_bot_tier` и совместимость по `stealth_init_version`.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.browser.engine.types import ContextSignature


@dataclass(frozen=True)
class StealthPlan:
    version: str
    tier: str
    extra_http_headers: dict[str, str]
    navigator_languages_override: tuple[str, ...]


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

    # Для согласованности с сетью используем языки ровно из locale (без эвристик).
    locale_primary = signature.locale.split(",")[0].strip()
    base_lang = locale_primary.split("-")[0].strip()
    if not locale_primary or not base_lang:
        raise ValueError("locale должен содержать базовый язык")
    languages = (locale_primary, base_lang)
    headers = {"Accept-Language": _accept_language_from_locale(signature.locale)}
    return StealthPlan(
        version=version,
        tier=tier,
        extra_http_headers=headers,
        navigator_languages_override=languages,
    )


async def apply_stealth_to_context(context: object, signature: ContextSignature) -> None:
    """
    Применить stealth-план к уже созданному BrowserContext ДО открытия страниц.
    """
    plan = build_stealth_plan(signature)

    from playwright_stealth import Stealth  # сторонняя библиотека, init scripts инжектятся внутрь

    # 1) init scripts (playwright-stealth)
    stealth = Stealth(
        init_scripts_only=True,
        navigator_languages_override=plan.navigator_languages_override,
    )
    await stealth.apply_stealth_async(context)

    # 2) headers (сетевой слой не покрывается js-evasions)
    await context.set_extra_http_headers(plan.extra_http_headers)  # type: ignore[attr-defined]

