"""Unit-тесты единого CalDAV-слоя календаря (без сети)."""

from __future__ import annotations

import pytest

from core.calendar.caldav_discovery import (
    CALDAV_PROVIDERS,
    caldav_provider_for_imap_host,
    resolve_caldav_base_url,
)
from core.calendar.service import CalDavClient, calendar_source_for_provider
from core.models import CalendarEventSource, CalendarProvider


def test_caldav_providers_set() -> None:
    assert CalendarProvider.YANDEX in CALDAV_PROVIDERS
    assert CalendarProvider.MAILRU in CALDAV_PROVIDERS
    assert CalendarProvider.CALDAV in CALDAV_PROVIDERS
    assert CalendarProvider.GOOGLE not in CALDAV_PROVIDERS


def test_resolve_caldav_base_url_presets() -> None:
    assert resolve_caldav_base_url(CalendarProvider.YANDEX, None) == "https://caldav.yandex.ru"
    assert resolve_caldav_base_url(CalendarProvider.MAILRU, None) == "https://calendar.mail.ru"


def test_resolve_caldav_base_url_explicit_overrides_and_strips() -> None:
    assert (
        resolve_caldav_base_url(CalendarProvider.YANDEX, "https://dav.example.com/")
        == "https://dav.example.com"
    )


def test_resolve_caldav_base_url_custom_requires_explicit() -> None:
    with pytest.raises(ValueError):
        _ = resolve_caldav_base_url(CalendarProvider.CALDAV, None)


def test_caldav_provider_for_imap_host() -> None:
    assert caldav_provider_for_imap_host("imap.mail.ru") == CalendarProvider.MAILRU
    assert caldav_provider_for_imap_host("IMAP.YANDEX.COM") == CalendarProvider.YANDEX
    assert caldav_provider_for_imap_host("imap.yandex.ru") == CalendarProvider.YANDEX
    assert caldav_provider_for_imap_host("imap.gmail.com") is None


def test_calendar_source_for_provider() -> None:
    assert calendar_source_for_provider(CalendarProvider.MAILRU) == CalendarEventSource.MAILRU
    assert calendar_source_for_provider(CalendarProvider.CALDAV) == CalendarEventSource.CALDAV
    assert calendar_source_for_provider(CalendarProvider.YANDEX) == CalendarEventSource.YANDEX


def test_caldav_client_url_building_template() -> None:
    client = CalDavClient("https://calendar.mail.ru")
    assert (
        client._calendar_url(username="user@mail.ru", calendar_id="default")
        == "https://calendar.mail.ru/calendars/user@mail.ru/default/"
    )
    assert (
        client._event_url(username="user@mail.ru", calendar_id="default", external_event_id="uid1")
        == "https://calendar.mail.ru/calendars/user@mail.ru/default/uid1.ics"
    )


def test_caldav_client_url_building_absolute_href() -> None:
    client = CalDavClient("https://calendar.mail.ru")
    # discovery отдаёт абсолютный path календаря
    assert (
        client._calendar_url(username="user@mail.ru", calendar_id="/calendars/user@mail.ru/main")
        == "https://calendar.mail.ru/calendars/user@mail.ru/main/"
    )
    assert (
        client._event_url(
            username="user@mail.ru",
            calendar_id="default",
            external_event_id="/calendars/user@mail.ru/main/e1.ics",
        )
        == "https://calendar.mail.ru/calendars/user@mail.ru/main/e1.ics"
    )


def test_caldav_client_requires_absolute_base_url() -> None:
    with pytest.raises(ValueError):
        _ = CalDavClient("caldav.mail.ru")
