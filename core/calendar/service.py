"""
Сервис платформенного календаря.
"""

from __future__ import annotations

import re
import secrets
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import uuid4
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from core.calendar.repositories import CalendarEventSqlRepository, CalendarIntegrationSqlRepository
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.user_repository import UserRepository
from core.db.storage import Storage
from core.http import get_httpx_client
from core.models import (
    CalendarAttendee,
    CalendarEvent,
    CalendarEventSource,
    CalendarEventStatus,
    CalendarExternalRef,
    CalendarIntegration,
    CalendarIntegrationCredentials,
    CalendarIntegrationSettings,
    CalendarProvider,
)
from core.websocket.publisher import Notification, NotificationType, notify_user


@dataclass(frozen=True)
class GoogleOAuthConfig:
    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    scope: str


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_datetime(value: datetime) -> str:
    return _ensure_utc(value).isoformat().replace("+00:00", "Z")


def _ical_datetime(value: datetime, all_day: bool) -> str:
    utc_value = _ensure_utc(value)
    if all_day:
        return utc_value.strftime("%Y%m%d")
    return utc_value.strftime("%Y%m%dT%H%M%SZ")


def _unfold_ical_lines(raw_ics: str) -> list[str]:
    unfolded: list[str] = []
    for line in raw_ics.splitlines():
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
            continue
        unfolded.append(line)
    return unfolded


def _parse_ical_datetime(value: str, all_day: bool) -> datetime:
    normalized = value.strip()
    if all_day:
        parsed = datetime.strptime(normalized, "%Y%m%d")
        return parsed.replace(tzinfo=timezone.utc)
    if normalized.endswith("Z"):
        parsed = datetime.strptime(normalized, "%Y%m%dT%H%M%SZ")
        return parsed.replace(tzinfo=timezone.utc)
    parsed = datetime.strptime(normalized, "%Y%m%dT%H%M%S")
    return parsed.replace(tzinfo=timezone.utc)


def _parse_ical_event(raw_ics: str) -> dict:
    lines = _unfold_ical_lines(raw_ics)
    values: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        upper_key = key.upper()
        values[upper_key] = raw_value
    uid = values.get("UID")
    if not uid:
        raise ValueError("ICS event must contain UID")
    dtstart_key = next((key for key in values if key.startswith("DTSTART")), None)
    dtend_key = next((key for key in values if key.startswith("DTEND")), None)
    if not dtstart_key or not dtend_key:
        raise ValueError("ICS event must contain DTSTART and DTEND")
    dtstart_value = values[dtstart_key]
    dtend_value = values[dtend_key]
    all_day = "VALUE=DATE" in dtstart_key
    start_at = _parse_ical_datetime(dtstart_value, all_day=all_day)
    end_at = _parse_ical_datetime(dtend_value, all_day=all_day)
    return {
        "id": uid,
        "summary": values.get("SUMMARY", "Yandex event"),
        "description": values.get("DESCRIPTION"),
        "location": values.get("LOCATION"),
        "status": values.get("STATUS", "CONFIRMED").lower(),
        "all_day": all_day,
        "start_at": start_at,
        "end_at": end_at,
        "url": values.get("URL"),
    }


def _parse_google_datetime(payload: dict) -> datetime:
    date_time = payload.get("dateTime")
    if isinstance(date_time, str):
        return datetime.fromisoformat(date_time.replace("Z", "+00:00"))
    date = payload.get("date")
    if not isinstance(date, str):
        raise ValueError("Google event must have start/end dateTime or date")
    return datetime.fromisoformat(f"{date}T00:00:00+00:00")


class GoogleCalendarClient:
    BASE_URL = "https://www.googleapis.com/calendar/v3"

    async def list_events(
        self,
        access_token: str,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[dict]:
        url = f"{self.BASE_URL}/calendars/{calendar_id}/events"
        params = {
            "timeMin": _iso_datetime(start_at),
            "timeMax": _iso_datetime(end_at),
            "singleEvents": "true",
            "maxResults": "2500",
        }
        headers = {"Authorization": f"Bearer {access_token}"}
        async with get_httpx_client(timeout=60.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
        payload = response.json()
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("Google events response must contain list 'items'")
        return items

    async def upsert_event(
        self,
        access_token: str,
        calendar_id: str,
        external_event_id: str | None,
        body: dict,
    ) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with get_httpx_client(timeout=60.0) as client:
            if external_event_id:
                url = f"{self.BASE_URL}/calendars/{calendar_id}/events/{external_event_id}"
                response = await client.put(url, json=body, headers=headers)
            else:
                url = f"{self.BASE_URL}/calendars/{calendar_id}/events"
                response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
        return response.json()

    async def delete_event(self, access_token: str, calendar_id: str, external_event_id: str) -> None:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.BASE_URL}/calendars/{calendar_id}/events/{external_event_id}"
        async with get_httpx_client(timeout=60.0) as client:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()


class YandexCalDavClient:
    BASE_URL = "https://caldav.yandex.ru"

    def _calendar_url(self, username: str, calendar_id: str) -> str:
        return f"{self.BASE_URL}/calendars/{username}/{calendar_id}/"

    def _event_url(self, username: str, calendar_id: str, external_event_id: str) -> str:
        if external_event_id.startswith("http://") or external_event_id.startswith("https://"):
            return external_event_id
        if external_event_id.startswith("/"):
            return f"{self.BASE_URL}{external_event_id}"
        return f"{self._calendar_url(username=username, calendar_id=calendar_id)}{external_event_id}.ics"

    async def list_events(
        self,
        username: str,
        app_password: str,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[dict]:
        url = self._calendar_url(username=username, calendar_id=calendar_id)
        report_body = f"""<?xml version="1.0" encoding="utf-8" ?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag />
    <c:calendar-data />
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
        <c:time-range start="{_ical_datetime(start_at, all_day=False)}" end="{_ical_datetime(end_at, all_day=False)}" />
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>"""
        headers = {"Depth": "1", "Content-Type": "application/xml"}
        async with get_httpx_client(timeout=60.0) as client:
            response = await client.request(
                "REPORT",
                url,
                content=report_body.encode("utf-8"),
                headers=headers,
                auth=(username, app_password),
            )
            response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
        events: list[dict] = []
        for item in root.findall("d:response", ns):
            href_node = item.find("d:href", ns)
            calendar_data_node = item.find("d:propstat/d:prop/c:calendar-data", ns)
            etag_node = item.find("d:propstat/d:prop/d:getetag", ns)
            if href_node is None or calendar_data_node is None or not calendar_data_node.text:
                continue
            parsed = _parse_ical_event(calendar_data_node.text)
            parsed["href"] = href_node.text
            parsed["etag"] = etag_node.text if etag_node is not None else None
            events.append(parsed)
        return events

    async def upsert_event(
        self,
        username: str,
        app_password: str,
        calendar_id: str,
        external_event_id: str | None,
        event: CalendarEvent,
    ) -> dict:
        if external_event_id:
            event_url = self._event_url(
                username=username,
                calendar_id=calendar_id,
                external_event_id=external_event_id,
            )
            uid_match = re.search(r"/([^/]+)\.ics$", event_url)
            if uid_match is None:
                raise ValueError(f"Cannot extract Yandex event UID from URL: {event_url}")
            uid = uid_match.group(1)
        else:
            uid = uuid4().hex
            event_url = self._event_url(
                username=username,
                calendar_id=calendar_id,
                external_event_id=uid,
            )
        status = event.status.value.upper()
        ics = "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Humanitec//Calendar//EN",
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"SUMMARY:{event.title}",
                f"DESCRIPTION:{event.description or ''}",
                f"LOCATION:{event.location or ''}",
                f"DTSTART:{_ical_datetime(event.start_at, all_day=event.all_day)}",
                f"DTEND:{_ical_datetime(event.end_at, all_day=event.all_day)}",
                f"STATUS:{status}",
                "END:VEVENT",
                "END:VCALENDAR",
                "",
            ]
        )
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        async with get_httpx_client(timeout=60.0) as client:
            response = await client.put(event_url, content=ics.encode("utf-8"), headers=headers, auth=(username, app_password))
            response.raise_for_status()
        return {
            "id": uid,
            "href": event_url,
            "etag": response.headers.get("ETag"),
        }

    async def delete_event(
        self,
        username: str,
        app_password: str,
        calendar_id: str,
        external_event_id: str,
    ) -> None:
        event_url = self._event_url(
            username=username,
            calendar_id=calendar_id,
            external_event_id=external_event_id,
        )
        async with get_httpx_client(timeout=60.0) as client:
            response = await client.delete(event_url, auth=(username, app_password))
            response.raise_for_status()


class CalendarService:
    def __init__(
        self,
        event_repository: CalendarEventSqlRepository,
        integration_repository: CalendarIntegrationSqlRepository,
        user_repository: UserRepository,
        company_repository: CompanyRepository,
        service_client: ServiceClient,
        storage: Storage,
    ) -> None:
        self._event_repository = event_repository
        self._integration_repository = integration_repository
        self._user_repository = user_repository
        self._company_repository = company_repository
        self._service_client = service_client
        self._storage = storage
        self._google_client = GoogleCalendarClient()
        self._yandex_client = YandexCalDavClient()

    def _get_google_oauth_config(self) -> GoogleOAuthConfig:
        settings = get_settings()
        provider = settings.auth.providers.get("google")
        if provider is None or not provider.enabled:
            raise ValueError("Google OAuth provider is disabled")
        if not provider.client_id:
            raise ValueError("Google OAuth client_id is required")
        if not provider.client_secret:
            raise ValueError("Google OAuth client_secret is required")
        if not provider.auth_url:
            raise ValueError("Google OAuth auth_url is required")
        if not provider.token_url:
            raise ValueError("Google OAuth token_url is required")
        return GoogleOAuthConfig(
            client_id=provider.client_id,
            client_secret=provider.client_secret,
            auth_url=provider.auth_url,
            token_url=provider.token_url,
            scope="https://www.googleapis.com/auth/calendar",
        )

    async def start_google_oauth(
        self,
        user_id: str,
        company_id: str,
        redirect_uri: str,
        return_path: str,
    ) -> str:
        if not return_path.startswith("/") or return_path.startswith("//"):
            raise ValueError("return_path must start with single '/'")
        oauth_config = self._get_google_oauth_config()
        state = secrets.token_urlsafe(32)
        state_key = f"calendar_oauth_state:{state}"
        state_payload = {
            "provider": CalendarProvider.GOOGLE.value,
            "user_id": user_id,
            "company_id": company_id,
            "redirect_uri": redirect_uri,
            "return_path": return_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._storage.set(
            key=state_key,
            value=json.dumps(state_payload),
            ttl=600,
            force_global=True,
        )
        query = urlencode(
            {
                "client_id": oauth_config.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": oauth_config.scope,
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
            }
        )
        return f"{oauth_config.auth_url}?{query}"

    async def complete_google_oauth(self, state: str, code: str) -> str:
        state_key = f"calendar_oauth_state:{state}"
        raw_state = await self._storage.get(key=state_key, force_global=True)
        if raw_state is None:
            raise ValueError("Calendar OAuth state is invalid or expired")
        await self._storage.delete(key=state_key, force_global=True)
        state_payload = json.loads(raw_state)
        if not isinstance(state_payload, dict):
            raise ValueError("Calendar OAuth state payload is invalid")
        if state_payload.get("provider") != CalendarProvider.GOOGLE.value:
            raise ValueError("Calendar OAuth state provider mismatch")
        user_id = state_payload.get("user_id")
        if not isinstance(user_id, str) or user_id == "":
            raise ValueError("Calendar OAuth state user_id is required")
        company_id = state_payload.get("company_id")
        if not isinstance(company_id, str) or company_id == "":
            raise ValueError("Calendar OAuth state company_id is required")
        redirect_uri = state_payload.get("redirect_uri")
        if not isinstance(redirect_uri, str) or redirect_uri == "":
            raise ValueError("Calendar OAuth state redirect_uri is required")
        return_path = state_payload.get("return_path")
        if not isinstance(return_path, str) or not return_path.startswith("/") or return_path.startswith("//"):
            raise ValueError("Calendar OAuth state return_path is invalid")

        oauth_config = self._get_google_oauth_config()
        async with get_httpx_client(timeout=30.0) as client:
            token_response = await client.post(
                oauth_config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": oauth_config.client_id,
                    "client_secret": oauth_config.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
        access_token = token_payload.get("access_token")
        if not isinstance(access_token, str) or access_token == "":
            raise ValueError("Google OAuth response missing access_token")
        refresh_token = token_payload.get("refresh_token")
        if not isinstance(refresh_token, str) or refresh_token == "":
            raise ValueError("Google OAuth response missing refresh_token")
        expires_in = token_payload.get("expires_in")
        expires_at = None
        if isinstance(expires_in, int) and expires_in > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        scope = token_payload.get("scope")
        token_type = token_payload.get("token_type")
        await self.connect_integration(
            user_id=user_id,
            company_id=company_id,
            payload={
                "provider": CalendarProvider.GOOGLE.value,
                "username": None,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "scope": scope if isinstance(scope, str) else None,
                "token_type": token_type if isinstance(token_type, str) else "Bearer",
                "default_calendar_id": "primary",
                "sync_enabled": True,
                "sync_inbound_enabled": True,
                "sync_outbound_enabled": True,
                "notifications_enabled": True,
            },
        )
        now = datetime.now(timezone.utc)
        await self.run_sync(
            user_id=user_id,
            company_id=company_id,
            start_at=now - timedelta(days=30),
            end_at=now + timedelta(days=365),
            provider=CalendarProvider.GOOGLE,
        )
        return return_path

    async def list_events(
        self,
        company_id: str,
        user_id: str,
        start_at: datetime,
        end_at: datetime,
        include_sources: set[CalendarEventSource] | None = None,
        limit: int = 1000,
    ) -> list[CalendarEvent]:
        if _ensure_utc(start_at) >= _ensure_utc(end_at):
            raise ValueError("Calendar list range start_at must be before end_at")
        local_events = await self._event_repository.list_in_range(
            company_id=company_id,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
        )
        merged_events = list(local_events)
        include_all_sources = include_sources is None
        if include_all_sources or CalendarEventSource.CRM in include_sources:
            merged_events.extend(
                await self._fetch_crm_events(
                    company_id=company_id,
                    user_id=user_id,
                    start_at=start_at,
                    end_at=end_at,
                )
            )
        if include_all_sources or CalendarEventSource.SYNC in include_sources:
            merged_events.extend(
                await self._fetch_sync_events(
                    company_id=company_id,
                    user_id=user_id,
                    start_at=start_at,
                    end_at=end_at,
                )
            )
        filtered_events = merged_events
        if include_sources:
            filtered_events = [item for item in merged_events if item.source in include_sources]
        filtered_events.sort(key=lambda item: item.start_at)
        return filtered_events[:limit]

    async def _resolve_invited_platform_user_ids(
        self,
        company_id: str,
        organizer_user_id: str,
        attendees: list[CalendarAttendee],
    ) -> list[str]:
        company = await self._company_repository.get(company_id)
        if company is None:
            raise ValueError(f"Company {company_id} not found")
        company_member_ids = set(company.members.keys())
        invited_ids: set[str] = set()
        invited_emails = {
            attendee.email.strip().lower()
            for attendee in attendees
            if attendee.email and attendee.email.strip()
        }
        for attendee in attendees:
            if attendee.attendee_id and attendee.attendee_id in company_member_ids:
                invited_ids.add(attendee.attendee_id)
        if invited_emails:
            for member_user_id in company_member_ids:
                member_user = await self._user_repository.get(member_user_id)
                if member_user is None:
                    raise ValueError(f"User {member_user_id} not found")
                member_emails = {email.strip().lower() for email in member_user.emails if email and email.strip()}
                if invited_emails.intersection(member_emails):
                    invited_ids.add(member_user_id)
        invited_ids.discard(organizer_user_id)
        return sorted(invited_ids)

    async def _notify_attendees_about_event_invite(
        self,
        event: CalendarEvent,
        organizer_user_id: str,
    ) -> None:
        if not event.attendees:
            return
        invited_user_ids = await self._resolve_invited_platform_user_ids(
            company_id=event.company_id,
            organizer_user_id=organizer_user_id,
            attendees=event.attendees,
        )
        if not invited_user_ids:
            return
        event_timezone = ZoneInfo(event.timezone)
        event_start_local = event.start_at.astimezone(event_timezone)
        event_start_label = event_start_local.strftime("%d.%m.%Y %H:%M")
        for invited_user_id in invited_user_ids:
            await notify_user(
                user_id=invited_user_id,
                notification=Notification(
                    type=NotificationType.CALENDAR_NEW_EVENT,
                    title="Приглашение на встречу",
                    message=f"Вас пригласили на встречу \"{event.title}\" на {event_start_label}.",
                    service="calendar",
                    priority="normal",
                    data={
                        "event_id": event.event_id,
                        "company_id": event.company_id,
                        "start_at": event.start_at.isoformat(),
                        "end_at": event.end_at.isoformat(),
                        "timezone": event.timezone,
                    },
                ),
            )

    async def upsert_event(self, event_id: str | None, payload: dict, user_id: str, company_id: str) -> CalendarEvent:
        now = datetime.now(timezone.utc)
        current = None
        if event_id is None:
            final_event_id = uuid4().hex
            created_at = now
            created_by = user_id
        else:
            current = await self._event_repository.get(event_id=event_id, company_id=company_id)
            if current is None:
                raise ValueError(f"Calendar event {event_id} not found")
            final_event_id = current.event_id
            created_at = current.created_at
            created_by = current.created_by_user_id

        start_at = _ensure_utc(payload["start_at"])
        end_at = _ensure_utc(payload["end_at"])
        if start_at >= end_at:
            raise ValueError("Calendar event start_at must be before end_at")

        source = CalendarEventSource(payload["source"])
        source_id = payload["source_id"] or final_event_id
        status = CalendarEventStatus(payload["status"])
        event = CalendarEvent(
            event_id=final_event_id,
            source=source,
            source_id=source_id,
            company_id=company_id,
            namespace=payload.get("namespace"),
            kind=payload["kind"],
            title=payload["title"],
            description=payload.get("description"),
            location=payload.get("location"),
            status=status,
            timezone=payload["timezone"],
            all_day=payload["all_day"],
            start_at=start_at,
            end_at=end_at,
            attendees=payload["attendees"],
            recurrence_rule=payload.get("recurrence_rule"),
            recurrence_id=payload.get("recurrence_id"),
            series_id=payload.get("series_id"),
            deep_link=payload.get("deep_link"),
            external_refs=(current.external_refs if current else []),
            metadata=payload["metadata"],
            created_by_user_id=created_by,
            updated_by_user_id=user_id,
            created_at=created_at,
            updated_at=now,
        )
        await self._event_repository.upsert(event)
        if event_id is None and event.source == CalendarEventSource.PLATFORM:
            await self._notify_attendees_about_event_invite(
                event=event,
                organizer_user_id=user_id,
            )
        return event

    async def delete_event(self, event_id: str, user_id: str, company_id: str) -> None:
        event = await self._event_repository.get(event_id=event_id, company_id=company_id)
        if event is None:
            raise ValueError(f"Calendar event {event_id} not found")
        await self._delete_external_links(event)
        deleted = await self._event_repository.delete(event_id=event_id, company_id=company_id)
        if not deleted:
            raise RuntimeError(f"Failed to delete calendar event {event_id}")

    async def list_integrations(self, user_id: str, company_id: str) -> list[CalendarIntegration]:
        return await self._integration_repository.list_by_user(company_id=company_id, user_id=user_id)

    async def connect_integration(self, user_id: str, company_id: str, payload: dict) -> CalendarIntegration:
        now = datetime.now(timezone.utc)
        provider = CalendarProvider(payload["provider"])
        if provider not in {CalendarProvider.GOOGLE, CalendarProvider.YANDEX}:
            raise ValueError(f"Unsupported calendar provider for integration: {provider}")
        if provider == CalendarProvider.YANDEX and not payload.get("username"):
            raise ValueError("Yandex integration username is required")
        existing = await self._integration_repository.get_by_user_provider(
            company_id=company_id,
            user_id=user_id,
            provider=provider,
        )
        integration = CalendarIntegration(
            integration_id=existing.integration_id if existing else uuid4().hex,
            company_id=company_id,
            user_id=user_id,
            provider=provider,
            credentials=CalendarIntegrationCredentials(
                username=payload.get("username"),
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token"),
                expires_at=payload.get("expires_at"),
                scope=payload.get("scope"),
                token_type=payload.get("token_type"),
            ),
            settings=CalendarIntegrationSettings(
                default_calendar_id=payload.get("default_calendar_id"),
                sync_enabled=payload["sync_enabled"],
                sync_inbound_enabled=payload["sync_inbound_enabled"],
                sync_outbound_enabled=payload["sync_outbound_enabled"],
                notifications_enabled=payload.get("notifications_enabled", True),
            ),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        await self._integration_repository.upsert(integration)
        return integration

    async def disconnect_integration(self, user_id: str, company_id: str, provider: CalendarProvider) -> None:
        integration = await self._integration_repository.get_by_user_provider(
            company_id=company_id,
            user_id=user_id,
            provider=provider,
        )
        if integration is None:
            raise ValueError(f"Calendar integration {provider} not found")
        deleted = await self._integration_repository.delete(
            integration_id=integration.integration_id,
            company_id=company_id,
            user_id=user_id,
        )
        if not deleted:
            raise RuntimeError(f"Failed to delete integration {provider}")

    async def run_sync(
        self,
        user_id: str,
        company_id: str,
        start_at: datetime,
        end_at: datetime,
        provider: CalendarProvider,
    ) -> dict[str, int]:
        if _ensure_utc(start_at) >= _ensure_utc(end_at):
            raise ValueError("Calendar sync range start_at must be before end_at")
        integration = await self._integration_repository.get_by_user_provider(
            company_id=company_id,
            user_id=user_id,
            provider=provider,
        )
        if integration is None:
            raise ValueError(f"Calendar integration {provider} not found")
        if not integration.settings.sync_enabled:
            raise ValueError(f"Calendar integration {provider} is disabled")
        calendar_id = integration.settings.default_calendar_id
        if not calendar_id:
            raise ValueError(f"{provider} integration default_calendar_id is required")

        imported = 0
        exported = 0
        if provider == CalendarProvider.GOOGLE:
            if integration.settings.sync_inbound_enabled:
                imported = await self._sync_google_inbound(
                    company_id=company_id,
                    user_id=user_id,
                    credentials=integration.credentials,
                    calendar_id=calendar_id,
                    start_at=start_at,
                    end_at=end_at,
                )
            if integration.settings.sync_outbound_enabled:
                exported = await self._sync_google_outbound(
                    user_id=user_id,
                    company_id=company_id,
                    credentials=integration.credentials,
                    calendar_id=calendar_id,
                    start_at=start_at,
                    end_at=end_at,
                )
            return {"imported": imported, "exported": exported}
        if provider == CalendarProvider.YANDEX:
            if not integration.credentials.username:
                raise ValueError("Yandex integration username is required")
            if integration.settings.sync_inbound_enabled:
                imported = await self._sync_yandex_inbound(
                    company_id=company_id,
                    user_id=user_id,
                    credentials=integration.credentials,
                    calendar_id=calendar_id,
                    start_at=start_at,
                    end_at=end_at,
                )
            if integration.settings.sync_outbound_enabled:
                exported = await self._sync_yandex_outbound(
                    user_id=user_id,
                    company_id=company_id,
                    credentials=integration.credentials,
                    calendar_id=calendar_id,
                    start_at=start_at,
                    end_at=end_at,
                )
            return {"imported": imported, "exported": exported}
        raise ValueError(f"Unsupported calendar provider: {provider}")

    async def _sync_google_inbound(
        self,
        company_id: str,
        user_id: str,
        credentials: CalendarIntegrationCredentials,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        items = await self._google_client.list_events(
            access_token=credentials.access_token,
            calendar_id=calendar_id,
            start_at=start_at,
            end_at=end_at,
        )
        existing = await self._event_repository.list_in_range(
            company_id=company_id,
            start_at=start_at - timedelta(days=3650),
            end_at=end_at + timedelta(days=3650),
            limit=10000,
        )
        imported = 0
        now = datetime.now(timezone.utc)
        for item in items:
            external_id = item.get("id")
            if not isinstance(external_id, str) or external_id == "":
                continue
            matched = None
            for candidate in existing:
                for ref in candidate.external_refs:
                    if (
                        ref.provider == CalendarProvider.GOOGLE
                        and ref.calendar_id == calendar_id
                        and ref.external_event_id == external_id
                    ):
                        matched = candidate
                        break
                if matched:
                    break
            start_payload = item.get("start")
            end_payload = item.get("end")
            if not isinstance(start_payload, dict) or not isinstance(end_payload, dict):
                continue
            start_value = _ensure_utc(_parse_google_datetime(start_payload))
            end_value = _ensure_utc(_parse_google_datetime(end_payload))
            if start_value >= end_value:
                continue
            raw_status = item.get("status") or CalendarEventStatus.CONFIRMED.value
            status = CalendarEventStatus(raw_status)
            event = CalendarEvent(
                event_id=matched.event_id if matched else uuid4().hex,
                source=CalendarEventSource.GOOGLE,
                source_id=external_id,
                company_id=company_id,
                namespace=None,
                kind="event",
                title=item.get("summary") or "Google event",
                description=item.get("description"),
                location=item.get("location"),
                status=status,
                timezone=start_payload.get("timeZone") or "UTC",
                all_day="date" in start_payload and "dateTime" not in start_payload,
                start_at=start_value,
                end_at=end_value,
                attendees=[],
                recurrence_rule=(item.get("recurrence") or [None])[0] if isinstance(item.get("recurrence"), list) else None,
                recurrence_id=item.get("recurringEventId"),
                series_id=item.get("iCalUID"),
                deep_link=item.get("htmlLink"),
                external_refs=[
                    CalendarExternalRef(
                        provider=CalendarProvider.GOOGLE,
                        calendar_id=calendar_id,
                        external_event_id=external_id,
                        etag=item.get("etag"),
                        last_synced_at=now,
                    )
                ],
                metadata={},
                created_by_user_id=matched.created_by_user_id if matched else user_id,
                updated_by_user_id=user_id,
                created_at=matched.created_at if matched else now,
                updated_at=now,
            )
            await self._event_repository.upsert(event)
            imported += 1
        return imported

    async def _sync_yandex_inbound(
        self,
        company_id: str,
        user_id: str,
        credentials: CalendarIntegrationCredentials,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        if not credentials.username:
            raise ValueError("Yandex integration username is required")
        items = await self._yandex_client.list_events(
            username=credentials.username,
            app_password=credentials.access_token,
            calendar_id=calendar_id,
            start_at=start_at,
            end_at=end_at,
        )
        existing = await self._event_repository.list_in_range(
            company_id=company_id,
            start_at=start_at - timedelta(days=3650),
            end_at=end_at + timedelta(days=3650),
            limit=10000,
        )
        imported = 0
        now = datetime.now(timezone.utc)
        for item in items:
            external_id = item.get("href")
            if not isinstance(external_id, str) or external_id == "":
                raise ValueError("Yandex event must contain href")
            matched = None
            for candidate in existing:
                for ref in candidate.external_refs:
                    if (
                        ref.provider == CalendarProvider.YANDEX
                        and ref.calendar_id == calendar_id
                        and ref.external_event_id == external_id
                    ):
                        matched = candidate
                        break
                if matched:
                    break
            start_value = _ensure_utc(item["start_at"])
            end_value = _ensure_utc(item["end_at"])
            if start_value >= end_value:
                raise ValueError("Yandex event start must be before end")
            raw_status = item.get("status") or CalendarEventStatus.CONFIRMED.value
            status = CalendarEventStatus(raw_status)
            source_id = item.get("id")
            if not isinstance(source_id, str) or source_id == "":
                raise ValueError("Yandex event must contain id")
            event = CalendarEvent(
                event_id=matched.event_id if matched else uuid4().hex,
                source=CalendarEventSource.YANDEX,
                source_id=source_id,
                company_id=company_id,
                namespace=None,
                kind="event",
                title=item.get("summary") or "Yandex event",
                description=item.get("description"),
                location=item.get("location"),
                status=status,
                timezone="UTC",
                all_day=bool(item.get("all_day")),
                start_at=start_value,
                end_at=end_value,
                attendees=[],
                recurrence_rule=None,
                recurrence_id=None,
                series_id=None,
                deep_link=item.get("url"),
                external_refs=[
                    CalendarExternalRef(
                        provider=CalendarProvider.YANDEX,
                        calendar_id=calendar_id,
                        external_event_id=external_id,
                        etag=item.get("etag"),
                        last_synced_at=now,
                    )
                ],
                metadata={},
                created_by_user_id=matched.created_by_user_id if matched else user_id,
                updated_by_user_id=user_id,
                created_at=matched.created_at if matched else now,
                updated_at=now,
            )
            await self._event_repository.upsert(event)
            imported += 1
        return imported

    async def _sync_google_outbound(
        self,
        user_id: str,
        company_id: str,
        credentials: CalendarIntegrationCredentials,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        events = await self._event_repository.list_in_range(
            company_id=company_id,
            start_at=start_at,
            end_at=end_at,
            limit=5000,
        )
        exported = 0
        for event in events:
            if event.source not in {
                CalendarEventSource.PLATFORM,
                CalendarEventSource.CRM,
                CalendarEventSource.SYNC,
                CalendarEventSource.FLOWS,
            }:
                continue
            ext_id = None
            for ref in event.external_refs:
                if ref.provider == CalendarProvider.GOOGLE and ref.calendar_id == calendar_id:
                    ext_id = ref.external_event_id
                    break
            payload = {
                "summary": event.title,
                "description": event.description or "",
                "location": event.location or "",
                "status": event.status.value,
                "start": {"dateTime": _iso_datetime(event.start_at), "timeZone": event.timezone},
                "end": {"dateTime": _iso_datetime(event.end_at), "timeZone": event.timezone},
            }
            saved = await self._google_client.upsert_event(
                access_token=credentials.access_token,
                calendar_id=calendar_id,
                external_event_id=ext_id,
                body=payload,
            )
            external_event_id = saved.get("id")
            if not isinstance(external_event_id, str) or external_event_id == "":
                raise RuntimeError("Google upsert response must contain id")
            refs = [ref for ref in event.external_refs if not (ref.provider == CalendarProvider.GOOGLE and ref.calendar_id == calendar_id)]
            refs.append(
                CalendarExternalRef(
                    provider=CalendarProvider.GOOGLE,
                    calendar_id=calendar_id,
                    external_event_id=external_event_id,
                    etag=saved.get("etag"),
                    last_synced_at=datetime.now(timezone.utc),
                )
            )
            event.external_refs = refs
            event.updated_by_user_id = user_id
            event.updated_at = datetime.now(timezone.utc)
            await self._event_repository.upsert(event)
            exported += 1
        return exported

    async def _sync_yandex_outbound(
        self,
        user_id: str,
        company_id: str,
        credentials: CalendarIntegrationCredentials,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        if not credentials.username:
            raise ValueError("Yandex integration username is required")
        events = await self._event_repository.list_in_range(
            company_id=company_id,
            start_at=start_at,
            end_at=end_at,
            limit=5000,
        )
        exported = 0
        for event in events:
            if event.source not in {
                CalendarEventSource.PLATFORM,
                CalendarEventSource.CRM,
                CalendarEventSource.SYNC,
                CalendarEventSource.FLOWS,
            }:
                continue
            ext_id = None
            for ref in event.external_refs:
                if ref.provider == CalendarProvider.YANDEX and ref.calendar_id == calendar_id:
                    ext_id = ref.external_event_id
                    break
            saved = await self._yandex_client.upsert_event(
                username=credentials.username,
                app_password=credentials.access_token,
                calendar_id=calendar_id,
                external_event_id=ext_id,
                event=event,
            )
            external_event_id = saved.get("href")
            if not isinstance(external_event_id, str) or external_event_id == "":
                raise RuntimeError("Yandex upsert response must contain href")
            refs = [ref for ref in event.external_refs if not (ref.provider == CalendarProvider.YANDEX and ref.calendar_id == calendar_id)]
            refs.append(
                CalendarExternalRef(
                    provider=CalendarProvider.YANDEX,
                    calendar_id=calendar_id,
                    external_event_id=external_event_id,
                    etag=saved.get("etag"),
                    last_synced_at=datetime.now(timezone.utc),
                )
            )
            event.external_refs = refs
            event.updated_by_user_id = user_id
            event.updated_at = datetime.now(timezone.utc)
            await self._event_repository.upsert(event)
            exported += 1
        return exported

    async def _delete_external_links(self, event: CalendarEvent) -> None:
        for ref in event.external_refs:
            integration = await self._integration_repository.get_by_user_provider(
                company_id=event.company_id,
                user_id=event.updated_by_user_id or event.created_by_user_id or "",
                provider=ref.provider,
            )
            if integration is None:
                continue
            if ref.provider == CalendarProvider.GOOGLE:
                await self._google_client.delete_event(
                    access_token=integration.credentials.access_token,
                    calendar_id=ref.calendar_id,
                    external_event_id=ref.external_event_id,
                )
            elif ref.provider == CalendarProvider.YANDEX:
                if not integration.credentials.username:
                    raise ValueError("Yandex integration username is required")
                await self._yandex_client.delete_event(
                    username=integration.credentials.username,
                    app_password=integration.credentials.access_token,
                    calendar_id=ref.calendar_id,
                    external_event_id=ref.external_event_id,
                )

    async def _fetch_crm_events(
        self,
        company_id: str,
        user_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[CalendarEvent]:
        notes = await self._service_client.get("crm", "/crm/api/v1/entities", params={"entity_type": "note", "limit": 200})
        tasks = await self._service_client.get("crm", "/crm/api/v1/entities", params={"entity_type": "task", "limit": 200})
        events: list[CalendarEvent] = []
        now = datetime.now(timezone.utc)
        for item in [*(notes or []), *(tasks or [])]:
            if not isinstance(item, dict):
                continue
            source_id = item.get("entity_id")
            if not isinstance(source_id, str) or source_id == "":
                continue
            raw_date = item.get("note_date") or item.get("due_date")
            if not isinstance(raw_date, str) or raw_date == "":
                continue
            start_value = datetime.fromisoformat(f"{raw_date}T09:00:00+00:00")
            end_value = datetime.fromisoformat(f"{raw_date}T10:00:00+00:00")
            if start_value >= end_at or end_value <= start_at:
                continue
            events.append(
                CalendarEvent(
                    event_id=f"crm-{source_id}",
                    source=CalendarEventSource.CRM,
                    source_id=source_id,
                    company_id=company_id,
                    namespace=None,
                    kind=item.get("entity_type") or "crm",
                    title=item.get("name") or "CRM event",
                    description=item.get("description"),
                    location=None,
                    status=CalendarEventStatus.CONFIRMED,
                    timezone="UTC",
                    all_day=False,
                    start_at=start_value,
                    end_at=end_value,
                    attendees=[],
                    recurrence_rule=None,
                    recurrence_id=None,
                    series_id=None,
                    deep_link=f"/crm?view=entities&entity_id={source_id}",
                    external_refs=[],
                    metadata={},
                    created_by_user_id=user_id,
                    updated_by_user_id=user_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        return events

    async def _fetch_sync_events(
        self,
        company_id: str,
        user_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[CalendarEvent]:
        meetings = await self._service_client.get("sync", "/sync/api/v1/meetings/")
        events: list[CalendarEvent] = []
        now = datetime.now(timezone.utc)
        for item in meetings or []:
            if not isinstance(item, dict):
                continue
            source_id = item.get("meeting_id")
            if not isinstance(source_id, str) or source_id == "":
                continue
            created_at_raw = item.get("created_at")
            if not isinstance(created_at_raw, str) or created_at_raw == "":
                continue
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
            start_value = _ensure_utc(created_at)
            end_value = start_value + timedelta(minutes=30)
            if start_value >= end_at or end_value <= start_at:
                continue
            events.append(
                CalendarEvent(
                    event_id=f"sync-{source_id}",
                    source=CalendarEventSource.SYNC,
                    source_id=source_id,
                    company_id=company_id,
                    namespace=None,
                    kind="meeting",
                    title=f"Sync meeting {source_id[:8]}",
                    description=None,
                    location=None,
                    status=CalendarEventStatus.CONFIRMED,
                    timezone="UTC",
                    all_day=False,
                    start_at=start_value,
                    end_at=end_value,
                    attendees=[],
                    recurrence_rule=None,
                    recurrence_id=None,
                    series_id=None,
                    deep_link=f"/sync?meeting={source_id}",
                    external_refs=[],
                    metadata={},
                    created_by_user_id=user_id,
                    updated_by_user_id=user_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        return events
