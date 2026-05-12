"""
Structured ошибка OAuth/интеграций с подсказками для HTML и JSON клиентов.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class GuidedIntegrationLink:
    href: str
    label_ru: str
    label_en: str


OAuthErrorLocale = Literal["ru", "en"]


class GuidedIntegrationError(Exception):
    """Стабильный code и двуязычные строки для серверной HTML-страницы или JSON.guided."""

    def __init__(
        self,
        *,
        code: str,
        title_ru: str,
        title_en: str,
        message_ru: str,
        message_en: str,
        links: tuple[GuidedIntegrationLink, ...] = (),
        steps_ru: tuple[str, ...] = (),
        steps_en: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("GuidedIntegrationError: code обязателен")
        self.code = code.strip()
        self.title_ru = title_ru
        self.title_en = title_en
        self.message_ru = message_ru
        self.message_en = message_en
        self.links = links
        self.steps_ru = steps_ru
        self.steps_en = steps_en
        super().__init__(message_ru)

    def message_for_locale(self, locale: OAuthErrorLocale) -> str:
        return self.message_en if locale == "en" else self.message_ru

    def title_for_locale(self, locale: OAuthErrorLocale) -> str:
        return self.title_en if locale == "en" else self.title_ru

    def steps_for_locale(self, locale: OAuthErrorLocale) -> tuple[str, ...]:
        return self.steps_en if locale == "en" else self.steps_ru

    def guided_payload(self, locale: OAuthErrorLocale) -> dict[str, Any]:
        links_out: list[dict[str, str]] = []
        for link in self.links:
            label = link.label_en if locale == "en" else link.label_ru
            links_out.append({"href": link.href, "label": label})
        return {
            "code": self.code,
            "title": self.title_for_locale(locale),
            "message": self.message_for_locale(locale),
            "steps": list(self.steps_for_locale(locale)),
            "links": links_out,
        }
