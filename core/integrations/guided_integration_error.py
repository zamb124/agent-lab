"""
Structured ошибка OAuth/интеграций с подсказками для HTML и JSON клиентов.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


@dataclass(frozen=True)
class GuidedIntegrationLink:
    href: str
    label_ru: str
    label_en: str


OAuthErrorLocale = Literal["ru", "en"]


class GuidedIntegrationPayloadLink(TypedDict):
    href: str
    label: str


class GuidedIntegrationPayload(TypedDict):
    code: str
    title: str
    message: str
    steps: list[str]
    links: list[GuidedIntegrationPayloadLink]


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
        if code.strip() == "":
            raise ValueError("GuidedIntegrationError: code обязателен")
        self.code: str = code.strip()
        self.title_ru: str = title_ru
        self.title_en: str = title_en
        self.message_ru: str = message_ru
        self.message_en: str = message_en
        self.links: tuple[GuidedIntegrationLink, ...] = links
        self.steps_ru: tuple[str, ...] = steps_ru
        self.steps_en: tuple[str, ...] = steps_en
        super().__init__(message_ru)

    def message_for_locale(self, locale: OAuthErrorLocale) -> str:
        return self.message_en if locale == "en" else self.message_ru

    def title_for_locale(self, locale: OAuthErrorLocale) -> str:
        return self.title_en if locale == "en" else self.title_ru

    def steps_for_locale(self, locale: OAuthErrorLocale) -> tuple[str, ...]:
        return self.steps_en if locale == "en" else self.steps_ru

    def guided_payload(self, locale: OAuthErrorLocale) -> GuidedIntegrationPayload:
        links_out: list[GuidedIntegrationPayloadLink] = []
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
