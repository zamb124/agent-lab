"""Определение CalDAV-эндпоинта ящика: домен-пресеты, IMAP-хост, well-known проба."""

from __future__ import annotations

import pytest

from core.calendar.caldav_discovery import (
    CaldavAutolinkKind,
    caldav_base_url_from_probe,
    caldav_probe_decision,
    caldav_provider_for_mail_domain,
    resolve_caldav_target,
    well_known_caldav_url,
)
from core.config import get_settings
from core.models import CalendarProvider


def test_mail_domain_presets_cover_provider_aliases() -> None:
    assert caldav_provider_for_mail_domain("mail.ru") == CalendarProvider.MAILRU
    assert caldav_provider_for_mail_domain("BK.RU") == CalendarProvider.MAILRU
    assert caldav_provider_for_mail_domain("inbox.ru") == CalendarProvider.MAILRU
    assert caldav_provider_for_mail_domain("ya.ru") == CalendarProvider.YANDEX
    assert caldav_provider_for_mail_domain("yandex.kz") == CalendarProvider.YANDEX
    assert caldav_provider_for_mail_domain("example.org") is None


@pytest.mark.asyncio
async def test_resolve_target_by_mail_domain_preset() -> None:
    """Реальный ящик zambas124@mail.ru резолвится в CalDAV mail.ru без сети."""
    resolution = await resolve_caldav_target(
        mail_domain="mail.ru",
        imap_host="imap.mail.ru",
    )
    assert resolution.kind == CaldavAutolinkKind.CALDAV
    assert resolution.provider == CalendarProvider.MAILRU
    assert resolution.base_url == "https://calendar.mail.ru"
    assert resolution.require_target() == (CalendarProvider.MAILRU, "https://calendar.mail.ru")


@pytest.mark.asyncio
async def test_resolve_target_falls_back_to_imap_host_preset() -> None:
    """Адрес на своём домене, но ящик обслуживает Яндекс: провайдер по IMAP-хосту."""
    resolution = await resolve_caldav_target(
        mail_domain="corp.example",
        imap_host="imap.yandex.ru",
    )
    assert resolution.kind == CaldavAutolinkKind.CALDAV
    assert resolution.provider == CalendarProvider.YANDEX
    assert resolution.base_url == "https://caldav.yandex.ru"


@pytest.mark.asyncio
async def test_resolve_target_gmail_requires_oauth() -> None:
    resolution = await resolve_caldav_target(
        mail_domain="gmail.com",
        imap_host="imap.gmail.com",
    )
    assert resolution.kind == CaldavAutolinkKind.NEEDS_OAUTH
    assert resolution.provider == CalendarProvider.GOOGLE
    with pytest.raises(ValueError):
        _ = resolution.require_target()


@pytest.mark.asyncio
async def test_resolve_target_unsupported_when_probe_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = get_settings().calendar_sync
    monkeypatch.setattr(config, "autolink_well_known_probe_enabled", False)
    resolution = await resolve_caldav_target(
        mail_domain="corp.example",
        imap_host="imap.corp.example",
    )
    assert resolution.kind == CaldavAutolinkKind.UNSUPPORTED
    assert resolution.provider is None


def test_probe_decision_treats_auth_challenge_as_endpoint() -> None:
    assert caldav_probe_decision(200) is True
    assert caldav_probe_decision(207) is True
    assert caldav_probe_decision(301) is True
    assert caldav_probe_decision(401) is True
    assert caldav_probe_decision(404) is False
    assert caldav_probe_decision(500) is False


def test_well_known_url_and_base_url_from_probe() -> None:
    assert well_known_caldav_url("Corp.Example.") == "https://corp.example/.well-known/caldav"
    assert (
        caldav_base_url_from_probe(
            "https://corp.example/.well-known/caldav",
            "https://dav.corp.example:8443/dav/principals/",
        )
        == "https://dav.corp.example:8443"
    )


def test_base_url_from_probe_rejects_unusable_url() -> None:
    with pytest.raises(ValueError):
        _ = caldav_base_url_from_probe("https://corp.example/.well-known/caldav", "/dav/")
