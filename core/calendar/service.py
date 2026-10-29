"""
Сервис платформенного календаря.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import ClassVar
from urllib.parse import urlsplit
from uuid import uuid4
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx2
from pydantic import ConfigDict, Field

from core.calendar.caldav_discovery import (
    CALDAV_PROVIDERS,
    CaldavAutolinkKind,
    resolve_caldav_base_url,
    resolve_caldav_target,
)
from core.calendar.events import CALENDAR_EVENT_CREATED
from core.clients.service_client import ServiceClient, ServiceClientError
from core.config import get_settings
from core.events import publish_event_to_users
from core.http import get_httpx_client
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.integrations.oauth_service import OAuthService, OAuthTokenRefreshError
from core.logging import get_logger
from core.models import (
    CalendarAttendee,
    CalendarAutolinkOutcome,
    CalendarAutolinkStatus,
    CalendarEvent,
    CalendarEventSource,
    CalendarEventStatus,
    CalendarEventUpsertPayload,
    CalendarExternalRef,
    CalendarIntegration,
    CalendarIntegrationConnectPayload,
    CalendarIntegrationCredentialMetadata,
    CalendarIntegrationCredentials,
    CalendarIntegrationSettings,
    CalendarProvider,
)
from core.models.base import FlexibleBaseModel, StrictBaseModel
from core.models.identity_models import Company, User
from core.types import JsonObject, JsonValue, require_json_array, require_json_object
from core.websocket.publisher import Notification, NotificationType, notify_user

SYNC_LINK_TOKEN_META = "sync_link_token"
SYNC_CHANNEL_ID_META = "sync_channel_id"
SYNC_MEETING_FLAG_META = "sync_meeting"
SYNC_REMINDER_SENT_META = "sync_join_reminder_sent_at"

logger = get_logger(__name__)


GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


_PROVIDER_TO_SOURCE: dict[CalendarProvider, CalendarEventSource] = {
    CalendarProvider.GOOGLE: CalendarEventSource.GOOGLE,
    CalendarProvider.YANDEX: CalendarEventSource.YANDEX,
    CalendarProvider.MAILRU: CalendarEventSource.MAILRU,
    CalendarProvider.CALDAV: CalendarEventSource.CALDAV,
}


def calendar_source_for_provider(provider: CalendarProvider) -> CalendarEventSource:
    source = _PROVIDER_TO_SOURCE.get(provider)
    if source is None:
        raise ValueError(f"No calendar event source mapping for provider {provider}")
    return source


class GoogleCalendarDateTimePayload(FlexibleBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    date_time: str | None = Field(default=None, alias="dateTime")
    date: str | None = None
    time_zone: str | None = Field(default=None, alias="timeZone")


class GoogleCalendarEventPayload(FlexibleBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    id: str | None = None
    status: str | None = None
    summary: str | None = None
    description: str | None = None
    location: str | None = None
    start: GoogleCalendarDateTimePayload | None = None
    end: GoogleCalendarDateTimePayload | None = None
    recurrence: list[str] = Field(default_factory=list)
    recurring_event_id: str | None = Field(default=None, alias="recurringEventId")
    i_cal_uid: str | None = Field(default=None, alias="iCalUID")
    html_link: str | None = Field(default=None, alias="htmlLink")
    etag: str | None = None


class GoogleCalendarEventsResponse(FlexibleBaseModel):
    items: list[GoogleCalendarEventPayload] = Field(default_factory=list)


class GoogleCalendarEventUpsertPayload(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    summary: str
    description: str
    location: str
    status: str
    start: GoogleCalendarDateTimePayload
    end: GoogleCalendarDateTimePayload


class GoogleCalendarMutationResult(FlexibleBaseModel):
    id: str
    etag: str | None = None


class CalDavEventPayload(StrictBaseModel):
    id: str
    href: str
    etag: str | None = None
    summary: str
    description: str | None = None
    location: str | None = None
    status: str = CalendarEventStatus.CONFIRMED.value
    all_day: bool = False
    start_at: datetime
    end_at: datetime
    url: str | None = None


class CalDavMutationResult(StrictBaseModel):
    id: str
    href: str
    etag: str | None = None


class CalendarReauthRequiredError(RuntimeError):
    """Интеграция требует повторной OAuth авторизации пользователя."""


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


def _parse_ical_event(raw_ics: str, *, href: str, etag: str | None) -> CalDavEventPayload:
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
    return CalDavEventPayload(
        id=uid,
        href=href,
        etag=etag,
        summary=values.get("SUMMARY", "CalDAV event"),
        description=values.get("DESCRIPTION"),
        location=values.get("LOCATION"),
        status=values.get("STATUS", "CONFIRMED").lower(),
        all_day=all_day,
        start_at=start_at,
        end_at=end_at,
        url=values.get("URL"),
    )


def _parse_google_datetime(payload: GoogleCalendarDateTimePayload) -> datetime:
    if payload.date_time is not None:
        return datetime.fromisoformat(payload.date_time.replace("Z", "+00:00"))
    if payload.date is None:
        raise ValueError("Google event must have start/end dateTime or date")
    return datetime.fromisoformat(f"{payload.date}T00:00:00+00:00")


class GoogleCalendarClient:
    BASE_URL: ClassVar[str] = "https://www.googleapis.com/calendar/v3"

    async def list_events(
        self,
        access_token: str,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[GoogleCalendarEventPayload]:
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
            _ = response.raise_for_status()
        return GoogleCalendarEventsResponse.model_validate_json(response.text).items

    async def upsert_event(
        self,
        access_token: str,
        calendar_id: str,
        external_event_id: str | None,
        body: GoogleCalendarEventUpsertPayload,
    ) -> GoogleCalendarMutationResult:
        headers = {"Authorization": f"Bearer {access_token}"}
        json_body = require_json_object(body.model_dump(mode="json", by_alias=True), "Google event upsert payload")
        async with get_httpx_client(timeout=60.0) as client:
            if external_event_id:
                url = f"{self.BASE_URL}/calendars/{calendar_id}/events/{external_event_id}"
                response = await client.put(url, json=json_body, headers=headers)
            else:
                url = f"{self.BASE_URL}/calendars/{calendar_id}/events"
                response = await client.post(url, json=json_body, headers=headers)
            _ = response.raise_for_status()
        return GoogleCalendarMutationResult.model_validate_json(response.text)

    async def delete_event(self, access_token: str, calendar_id: str, external_event_id: str) -> None:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.BASE_URL}/calendars/{calendar_id}/events/{external_event_id}"
        async with get_httpx_client(timeout=60.0) as client:
            response = await client.delete(url, headers=headers)
            _ = response.raise_for_status()


class CalDavClient:
    """
    Единый CalDAV-клиент для всех парольных провайдеров (Yandex/Mail.ru/custom).

    Один протокол, разные base_url. Формат события на проводе — урезанный
    iCalendar VEVENT (UID/SUMMARY/DTSTART/DTEND/DESCRIPTION/LOCATION/STATUS).
    """

    def __init__(self, base_url: str) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError(f"CalDAV base_url must be absolute http(s) URL: {base_url!r}")
        self._base_url: str = normalized

    def _origin(self) -> str:
        parts = urlsplit(self._base_url)
        return f"{parts.scheme}://{parts.netloc}"

    def _absolutize(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        if path_or_url.startswith("/"):
            return f"{self._origin()}{path_or_url}"
        raise ValueError(f"Cannot absolutize CalDAV reference: {path_or_url!r}")

    def _calendar_url(self, username: str, calendar_id: str) -> str:
        if calendar_id.startswith(("http://", "https://", "/")):
            absolute = self._absolutize(calendar_id)
            return absolute if absolute.endswith("/") else f"{absolute}/"
        return f"{self._base_url}/calendars/{username}/{calendar_id}/"

    def _event_url(self, username: str, calendar_id: str, external_event_id: str) -> str:
        if external_event_id.startswith(("http://", "https://", "/")):
            return self._absolutize(external_event_id)
        return f"{self._calendar_url(username=username, calendar_id=calendar_id)}{external_event_id}.ics"

    def _discovery_roots(self) -> list[str]:
        """
        RFC 6764: сначала /.well-known/caldav (он редиректит на реальный корень,
        как у calendar.mail.ru → /principals/), затем сам base_url.
        """
        well_known = f"{self._origin()}/.well-known/caldav"
        if well_known == self._base_url:
            return [well_known]
        return [well_known, self._base_url]

    async def discover_default_calendar_id(self, username: str, app_password: str) -> str:
        """
        RFC 4791 discovery: current-user-principal -> calendar-home-set ->
        первая VEVENT-коллекция. Возвращает абсолютный path календаря
        (используется как default_calendar_id). Fail-closed при отсутствии.
        """
        auth = (username, app_password)
        ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
        principal_body = (
            '<?xml version="1.0" encoding="utf-8" ?>'
            '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
        )
        principal_href: str | None = None
        roots = self._discovery_roots()
        for index, root_url in enumerate(roots):
            is_last_root = index == len(roots) - 1
            try:
                principal_root = await self._propfind(
                    root_url, principal_body, depth="0", auth=auth
                )
            except httpx2.HTTPStatusError as error:
                # 401/403 — проблема доступа, а не адреса: следующий корень не поможет.
                if error.response.status_code in {401, 403} or is_last_root:
                    raise
                continue
            principal_href = self._first_text(
                principal_root, "d:response/d:propstat/d:prop/d:current-user-principal/d:href", ns
            )
            if principal_href:
                break
        if not principal_href:
            raise ValueError(f"CalDAV principal not found at {self._base_url}")
        home_body = (
            '<?xml version="1.0" encoding="utf-8" ?>'
            '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            "<d:prop><c:calendar-home-set/></d:prop></d:propfind>"
        )
        home_root = await self._propfind(self._absolutize(principal_href), home_body, depth="0", auth=auth)
        home_href = self._first_text(
            home_root, "d:response/d:propstat/d:prop/c:calendar-home-set/d:href", ns
        )
        if not home_href:
            raise ValueError(f"CalDAV calendar-home-set not found for {username}")
        list_body = (
            '<?xml version="1.0" encoding="utf-8" ?>'
            '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            "<d:prop><d:resourcetype/><c:supported-calendar-component-set/></d:prop></d:propfind>"
        )
        home_root_list = await self._propfind(self._absolutize(home_href), list_body, depth="1", auth=auth)
        for response_node in home_root_list.findall("d:response", ns):
            resourcetype = response_node.find("d:propstat/d:prop/d:resourcetype", ns)
            if resourcetype is None or resourcetype.find("c:calendar", ns) is None:
                continue
            comps = response_node.findall(
                "d:propstat/d:prop/c:supported-calendar-component-set/c:comp", ns
            )
            supports_vevent = not comps or any(comp.get("name") == "VEVENT" for comp in comps)
            if not supports_vevent:
                continue
            href_node = response_node.find("d:href", ns)
            if href_node is not None and href_node.text and href_node.text.strip():
                return href_node.text.strip()
        raise ValueError(f"No VEVENT calendar collection found for {username}")

    @staticmethod
    def _first_text(root: ElementTree.Element, path: str, ns: dict[str, str]) -> str | None:
        node = root.find(path, ns)
        if node is None or node.text is None:
            return None
        text = node.text.strip()
        return text if text else None

    async def _propfind(
        self, url: str, body: str, *, depth: str, auth: tuple[str, str]
    ) -> ElementTree.Element:
        headers = {"Depth": depth, "Content-Type": "application/xml"}
        async with get_httpx_client(timeout=60.0, follow_redirects=True) as client:
            response = await client.request(
                "PROPFIND", url, content=body.encode("utf-8"), headers=headers, auth=auth
            )
            _ = response.raise_for_status()
        return ElementTree.fromstring(response.text)

    async def list_events(
        self,
        username: str,
        app_password: str,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[CalDavEventPayload]:
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
            _ = response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
        events: list[CalDavEventPayload] = []
        for item in root.findall("d:response", ns):
            href_node = item.find("d:href", ns)
            calendar_data_node = item.find("d:propstat/d:prop/c:calendar-data", ns)
            etag_node = item.find("d:propstat/d:prop/d:getetag", ns)
            if href_node is None or not href_node.text or calendar_data_node is None or not calendar_data_node.text:
                continue
            parsed = _parse_ical_event(
                calendar_data_node.text,
                href=href_node.text,
                etag=etag_node.text if etag_node is not None else None,
            )
            events.append(parsed)
        return events

    async def upsert_event(
        self,
        username: str,
        app_password: str,
        calendar_id: str,
        external_event_id: str | None,
        event: CalendarEvent,
    ) -> CalDavMutationResult:
        if external_event_id:
            event_url = self._event_url(
                username=username,
                calendar_id=calendar_id,
                external_event_id=external_event_id,
            )
            uid_match = re.search(r"/([^/]+)\.ics$", event_url)
            if uid_match is None:
                raise ValueError(f"Cannot extract CalDAV event UID from URL: {event_url}")
            uid = uid_match.group(1)
        else:
            uid = uuid4().hex
            event_url = self._event_url(
                username=username,
                calendar_id=calendar_id,
                external_event_id=uid,
            )
        status = event.status.upper()
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
            _ = response.raise_for_status()
        response_headers = dict(response.headers.items())
        etag = response_headers.get("ETag")
        return CalDavMutationResult(id=uid, href=event_url, etag=etag)

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
            _ = response.raise_for_status()


def calendar_integration_from_credential(cred: IntegrationCredential) -> CalendarIntegration:
    """IntegrationCredential → CalendarIntegration (view model)."""
    metadata = CalendarIntegrationCredentialMetadata.model_validate(cred.metadata)
    return CalendarIntegration(
        integration_id=cred.credential_id,
        company_id=cred.company_id,
        user_id=cred.user_id,
        provider=CalendarProvider(cred.provider),
        mailbox_binding_id=cred.mailbox_binding_id,
        credentials=CalendarIntegrationCredentials(
            username=metadata.username,
            access_token=cred.access_token,
            refresh_token=cred.refresh_token,
            expires_at=cred.expires_at,
            scope=cred.scope,
            token_type=cred.token_type,
        ),
        settings=metadata.calendar_settings,
        created_at=cred.created_at,
        updated_at=cred.updated_at,
    )


def _calendar_integration_to_credential(integration: CalendarIntegration) -> IntegrationCredential:
    """CalendarIntegration → IntegrationCredential (storage model)."""
    metadata = CalendarIntegrationCredentialMetadata(
        username=integration.credentials.username,
        calendar_settings=integration.settings,
    )
    return IntegrationCredential(
        credential_id=integration.integration_id,
        company_id=integration.company_id,
        user_id=integration.user_id,
        provider=IntegrationProvider(integration.provider),
        service="calendar",
        mailbox_binding_id=integration.mailbox_binding_id,
        access_token=integration.credentials.access_token,
        refresh_token=integration.credentials.refresh_token,
        expires_at=integration.credentials.expires_at,
        scope=integration.credentials.scope,
        token_type=integration.credentials.token_type,
        metadata=require_json_object(metadata.model_dump(mode="json"), "calendar.integration.metadata"),
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


class CalendarService:
    def __init__(
        self,
        oauth_service: OAuthService,
        service_client: ServiceClient,
    ) -> None:
        self._oauth_service: OAuthService = oauth_service
        self._service_client: ServiceClient = service_client
        self._google_client: GoogleCalendarClient = GoogleCalendarClient()

    def _caldav_client_for(self, integration: CalendarIntegration) -> CalDavClient:
        base_url = resolve_caldav_base_url(integration.provider, integration.settings.caldav_base_url)
        return CalDavClient(base_url)

    async def _refresh_google_access_token(
        self,
        *,
        integration: CalendarIntegration,
    ) -> CalendarIntegration:
        """Делегирует refresh в OAuthService, возвращает обновлённый CalendarIntegration."""
        credential = _calendar_integration_to_credential(integration)
        try:
            refreshed = await self._oauth_service.refresh_token(credential)
        except OAuthTokenRefreshError as exc:
            raise CalendarReauthRequiredError(str(exc)) from exc
        return calendar_integration_from_credential(refreshed)

    @staticmethod
    def _is_google_access_token_expired(credentials: CalendarIntegrationCredentials) -> bool:
        if credentials.expires_at is None:
            return False
        expires_at = _ensure_utc(credentials.expires_at)
        return expires_at <= datetime.now(timezone.utc) + timedelta(minutes=2)

    async def start_google_oauth(
        self,
        user_id: str,
        company_id: str,
        redirect_uri: str,
        return_path: str,
    ) -> str:
        return await self._oauth_service.build_auth_url(
            provider=IntegrationProvider.GOOGLE,
            service="calendar",
            scopes=GOOGLE_CALENDAR_SCOPES,
            user_id=user_id,
            company_id=company_id,
            redirect_uri=redirect_uri,
            return_path=return_path,
        )

    async def complete_google_oauth(self, state: str, code: str) -> str:
        credential, return_path, _, _ = await self._oauth_service.complete_oauth(
            state_token=state,
            code=code,
        )
        cal_settings = CalendarIntegrationSettings(
            default_calendar_id="primary",
            sync_enabled=True,
            sync_inbound_enabled=True,
            sync_outbound_enabled=True,
            notifications_enabled=True,
        )
        metadata = CalendarIntegrationCredentialMetadata.model_validate(credential.metadata).model_copy(
            update={"calendar_settings": cal_settings}
        )
        updated = credential.model_copy(
            update={
                "metadata": require_json_object(metadata.model_dump(mode="json"), "calendar.integration.metadata"),
            }
        )
        await IntegrationCredential.upsert_by_credential_id(updated)

        now = datetime.now(timezone.utc)
        _ = await self.run_sync(
            user_id=credential.user_id,
            company_id=credential.company_id,
            start_at=now - timedelta(days=30),
            end_at=now + timedelta(days=365),
            integration_id=credential.credential_id,
        )
        return return_path

    async def list_events_by_start_at_asc(
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
        local_events = await CalendarEvent.list_overlapping_by_start_at_asc(
            company_id=company_id,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
        )
        merged_events = list(local_events)
        include_all_sources = include_sources is None
        if include_all_sources or CalendarEventSource.CRM in include_sources:
            try:
                merged_events.extend(
                    await self._fetch_crm_events(
                        company_id=company_id,
                        user_id=user_id,
                        start_at=start_at,
                        end_at=end_at,
                    )
                )
            except ServiceClientError as exc:
                logger.warning(
                    "calendar.optional_source_failed",
                    source=CalendarEventSource.CRM.value,
                    company_id=company_id,
                    error=str(exc),
                )
        if include_all_sources or CalendarEventSource.SYNC in include_sources:
            platform_event_ids = {
                e.event_id
                for e in local_events
                if e.source == CalendarEventSource.PLATFORM
            }
            try:
                merged_events.extend(
                    await self._fetch_sync_events(
                        company_id=company_id,
                        user_id=user_id,
                        start_at=start_at,
                        end_at=end_at,
                        exclude_platform_event_ids=platform_event_ids,
                    )
                )
            except ServiceClientError as exc:
                logger.warning(
                    "calendar.optional_source_failed",
                    source=CalendarEventSource.SYNC.value,
                    company_id=company_id,
                    error=str(exc),
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
        company = await Company.get(company_id)
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
            if not attendee.attendee_id:
                continue
            if attendee.attendee_id in company_member_ids:
                invited_ids.add(attendee.attendee_id)
                continue
            attendee_user = await User.get(attendee.attendee_id)
            if attendee_user is not None and company_id in attendee_user.companies:
                invited_ids.add(attendee.attendee_id)
        if invited_emails:
            for email in invited_emails:
                for member_user in await User.list_containing_email_ci_by_user_id_asc(email):
                    if member_user.user_id in company_member_ids or company_id in member_user.companies:
                        invited_ids.add(member_user.user_id)
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
        domain_payload = {
            "event_id": event.event_id,
            "company_id": event.company_id,
            "start_at": event.start_at.isoformat(),
            "end_at": event.end_at.isoformat(),
            "timezone": event.timezone,
            "title": event.title,
        }
        await publish_event_to_users(
            invited_user_ids,
            CALENDAR_EVENT_CREATED,
            domain_payload,
            company_id=event.company_id,
        )
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

    async def _reconcile_platform_sync_meeting(
        self,
        *,
        want_sync: bool,
        current: CalendarEvent | None,
        event_id: str,
        title: str,
        start_at: datetime,
        end_at: datetime,
        attendees: list[CalendarAttendee],
        organizer_user_id: str,
        company_id: str,
        metadata: dict[str, str],
    ) -> tuple[bool, str | None]:
        prev_token = metadata.get(SYNC_LINK_TOKEN_META)
        if not prev_token and current is not None:
            prev_token = current.metadata.get(SYNC_LINK_TOKEN_META)

        if want_sync:
            settings = get_settings()
            public_base = settings.server.platform_public_base_url
            if public_base is None or public_base.strip() == "":
                raise ValueError(
                    'Sync meeting requires server.platform_public_base_url in configuration.'
                )
            invited = await self._resolve_invited_platform_user_ids(
                company_id=company_id,
                organizer_user_id=organizer_user_id,
                attendees=attendees,
            )
            if not prev_token:
                body: JsonObject = {
                    "calendar_event_id": event_id,
                    "scheduled_title": title,
                    "scheduled_start_at": _iso_datetime(start_at),
                    "scheduled_end_at": _iso_datetime(end_at),
                    "calendar_member_user_ids": invited,
                }
                data = require_json_object(
                    await self._service_client.post(
                        "sync",
                        "/sync/api/v1/calls/links",
                        json=body,
                    ),
                    "Sync call link create response",
                )
                token = data.get("link_token")
                if not isinstance(token, str) or token == "":
                    raise ValueError('sync calls/links response has no link_token')
                channel_id = data.get("channel_id")
                if not isinstance(channel_id, str) or channel_id == "":
                    raise ValueError('sync calls/links response has no channel_id')
                metadata[SYNC_LINK_TOKEN_META] = token
                metadata[SYNC_CHANNEL_ID_META] = channel_id
                metadata[SYNC_MEETING_FLAG_META] = "1"
                join = data.get("join_url")
                if not isinstance(join, str) or join == "":
                    raise ValueError('sync calls/links response has no join_url')
                return True, join
            patch_body: JsonObject = {
                "scheduled_title": title,
                "scheduled_start_at": _iso_datetime(start_at),
                "scheduled_end_at": _iso_datetime(end_at),
                "calendar_member_user_ids": invited,
            }
            data = require_json_object(
                await self._service_client.patch(
                    "sync",
                    f"/sync/api/v1/calls/links/{prev_token}",
                    json=patch_body,
                ),
                "Sync call link update response",
            )
            token = data.get("link_token")
            if not isinstance(token, str) or token == "":
                raise ValueError('sync calls/links response has no link_token')
            channel_id = data.get("channel_id")
            if not isinstance(channel_id, str) or channel_id == "":
                raise ValueError('sync calls/links response has no channel_id')
            metadata[SYNC_LINK_TOKEN_META] = token
            metadata[SYNC_CHANNEL_ID_META] = channel_id
            metadata[SYNC_MEETING_FLAG_META] = "1"
            join = data.get("join_url")
            if not isinstance(join, str) or join == "":
                raise ValueError('sync calls/links response has no join_url')
            return True, join

        if prev_token:
            _ = await self._service_client.delete(
                "sync",
                f"/sync/api/v1/calls/links/{prev_token}",
            )
            _ = metadata.pop(SYNC_LINK_TOKEN_META, None)
            _ = metadata.pop(SYNC_CHANNEL_ID_META, None)
            _ = metadata.pop(SYNC_MEETING_FLAG_META, None)
            _ = metadata.pop(SYNC_REMINDER_SENT_META, None)
            return True, None

        return False, None

    async def upsert_event(
        self,
        event_id: str | None,
        payload: CalendarEventUpsertPayload,
        user_id: str,
        company_id: str,
    ) -> CalendarEvent:
        now = datetime.now(timezone.utc)

        current = None
        if event_id is None:
            final_event_id = uuid4().hex
            created_at = now
            created_by = user_id
        else:
            current = await CalendarEvent.by_event_id(event_id=event_id, company_id=company_id)
            if current is None:
                raise ValueError(f"Calendar event {event_id} not found")
            final_event_id = current.event_id
            created_at = current.created_at
            created_by = current.created_by_user_id

        start_at = _ensure_utc(payload.start_at)
        end_at = _ensure_utc(payload.end_at)
        if start_at >= end_at:
            raise ValueError("Calendar event start_at must be before end_at")

        attendees = list(payload.attendees)

        md: dict[str, str] = dict(payload.metadata)
        if current is not None:
            for meta_key, meta_val in current.metadata.items():
                if meta_key not in md:
                    md[meta_key] = meta_val

        source = payload.source
        source_id = payload.source_id or final_event_id
        status = payload.status
        want_sync = source == CalendarEventSource.PLATFORM and payload.kind == "meeting"

        mailbox_binding_id = payload.mailbox_binding_id
        if mailbox_binding_id is not None and not mailbox_binding_id.strip():
            raise ValueError("mailbox_binding_id must not be empty")
        if source == CalendarEventSource.PLATFORM:
            if event_id is None:
                if mailbox_binding_id is None:
                    raise ValueError("mailbox_binding_id is required for platform calendar events")
            elif mailbox_binding_id is None and current is not None:
                mailbox_binding_id = current.mailbox_binding_id
                if mailbox_binding_id is None:
                    raise ValueError("mailbox_binding_id is required for platform calendar events")
        elif mailbox_binding_id is None and current is not None:
            mailbox_binding_id = current.mailbox_binding_id

        deep_link_final = payload.deep_link
        if source == CalendarEventSource.PLATFORM:
            handled, dl = await self._reconcile_platform_sync_meeting(
                want_sync=want_sync,
                current=current,
                event_id=final_event_id,
                title=payload.title,
                start_at=start_at,
                end_at=end_at,
                attendees=attendees,
                organizer_user_id=user_id,
                company_id=company_id,
                metadata=md,
            )
            if handled:
                deep_link_final = dl

        event = CalendarEvent(
            event_id=final_event_id,
            source=source,
            source_id=source_id,
            company_id=company_id,
            namespace=payload.namespace,
            kind=payload.kind,
            title=payload.title,
            description=payload.description,
            location=payload.location,
            status=status,
            timezone=payload.timezone,
            all_day=payload.all_day,
            start_at=start_at,
            end_at=end_at,
            attendees=attendees,
            recurrence_rule=payload.recurrence_rule,
            recurrence_id=payload.recurrence_id,
            series_id=payload.series_id,
            deep_link=deep_link_final,
            external_refs=(current.external_refs if current else []),
            metadata=md,
            mailbox_binding_id=mailbox_binding_id,
            created_by_user_id=created_by,
            updated_by_user_id=user_id,
            created_at=created_at,
            updated_at=now,
        )
        await CalendarEvent.merge_by_event_id(event)
        if event_id is None and event.source == CalendarEventSource.PLATFORM:
            await self._notify_attendees_about_event_invite(
                event=event,
                organizer_user_id=user_id,
            )
        return event

    async def delete_event(self, event_id: str, company_id: str) -> None:
        event = await CalendarEvent.by_event_id(event_id=event_id, company_id=company_id)
        if event is None:
            raise ValueError(f"Calendar event {event_id} not found")
        token = event.metadata.get(SYNC_LINK_TOKEN_META)
        if token:
            _ = await self._service_client.delete(
                "sync",
                f"/sync/api/v1/calls/links/{token}",
            )
        await self._delete_external_links(event)
        deleted = await CalendarEvent.delete_by_company_and_event(company_id=company_id, event_id=event_id)
        if not deleted:
            raise RuntimeError(f"Failed to delete calendar event {event_id}")

    async def sync_meeting_reminder_recipient_user_ids(self, event: CalendarEvent) -> list[str]:
        organizer = event.created_by_user_id
        if organizer is None or organizer == "":
            raise ValueError('Sync reminder requires created_by_user_id on the event.')
        invited = await self._resolve_invited_platform_user_ids(
            company_id=event.company_id,
            organizer_user_id=organizer,
            attendees=event.attendees,
        )
        recipients = set(invited)
        recipients.add(organizer)
        return sorted(recipients)

    async def mark_sync_meeting_reminder_sent(self, event_id: str, company_id: str) -> None:
        event = await CalendarEvent.by_event_id(event_id=event_id, company_id=company_id)
        if event is None:
            return
        md = dict(event.metadata)
        md[SYNC_REMINDER_SENT_META] = _iso_datetime(datetime.now(timezone.utc))
        updated = event.model_copy(
            update={"metadata": md, "updated_at": datetime.now(timezone.utc)}
        )
        await CalendarEvent.merge_by_event_id(updated)

    async def list_integrations(self, user_id: str, company_id: str) -> list[CalendarIntegration]:
        credentials = await IntegrationCredential.list_by_created_at_for_user_asc(
            company_id=company_id,
            user_id=user_id,
        )
        return [
            calendar_integration_from_credential(c)
            for c in credentials
            if c.service == "calendar"
        ]

    async def connect_integration(
        self,
        user_id: str,
        company_id: str,
        payload: CalendarIntegrationConnectPayload,
    ) -> CalendarIntegration:
        now = datetime.now(timezone.utc)
        provider = payload.provider
        if provider != CalendarProvider.GOOGLE and provider not in CALDAV_PROVIDERS:
            raise ValueError(f"Unsupported calendar provider for integration: {provider}")
        existing = await IntegrationCredential.by_natural_key(
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider(provider),
            service="calendar",
            mailbox_binding_id=payload.mailbox_binding_id,
        )
        existing_settings = (
            calendar_integration_from_credential(existing).settings if existing else None
        )
        caldav_base_url: str | None = None
        default_calendar_id = payload.default_calendar_id
        if provider in CALDAV_PROVIDERS:
            if not payload.username:
                raise ValueError(f"{provider} integration username is required")
            caldav_base_url = resolve_caldav_base_url(
                provider,
                payload.caldav_base_url
                or (existing_settings.caldav_base_url if existing_settings else None),
            )
            if not default_calendar_id or not default_calendar_id.strip():
                if existing_settings and existing_settings.default_calendar_id:
                    default_calendar_id = existing_settings.default_calendar_id
                else:
                    client = CalDavClient(caldav_base_url)
                    default_calendar_id = await client.discover_default_calendar_id(
                        username=payload.username,
                        app_password=payload.access_token,
                    )
        integration = CalendarIntegration(
            integration_id=existing.credential_id if existing else uuid4().hex,
            company_id=company_id,
            user_id=user_id,
            provider=provider,
            mailbox_binding_id=payload.mailbox_binding_id,
            credentials=CalendarIntegrationCredentials(
                username=payload.username,
                access_token=payload.access_token,
                refresh_token=payload.refresh_token,
                expires_at=payload.expires_at,
                scope=payload.scope,
                token_type=payload.token_type,
            ),
            settings=CalendarIntegrationSettings(
                default_calendar_id=default_calendar_id,
                caldav_base_url=caldav_base_url,
                sync_enabled=payload.sync_enabled,
                sync_inbound_enabled=payload.sync_inbound_enabled,
                sync_outbound_enabled=payload.sync_outbound_enabled,
                notifications_enabled=payload.notifications_enabled,
            ),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        credential = _calendar_integration_to_credential(integration)
        await IntegrationCredential.upsert_by_credential_id(credential)
        return integration

    async def ensure_caldav_integration_from_mailbox(
        self,
        *,
        user_id: str,
        company_id: str,
        mailbox_binding_id: str,
        email_address: str,
        password: str,
        imap_host: str,
        mail_domain: str,
    ) -> CalendarAutolinkOutcome:
        """
        Идемпотентно поднимает CalDAV-интеграцию для ящика: пресет по домену,
        пресет по IMAP-хосту, затем RFC 6764 проба. Итог всегда типизирован,
        чтобы почта могла записать статус привязки.
        """
        resolution = await resolve_caldav_target(
            mail_domain=mail_domain,
            imap_host=imap_host,
        )
        if resolution.kind == CaldavAutolinkKind.NEEDS_OAUTH:
            return CalendarAutolinkOutcome(
                status=CalendarAutolinkStatus.NEEDS_OAUTH,
                detail=resolution.detail,
            )
        if resolution.kind == CaldavAutolinkKind.UNSUPPORTED:
            return CalendarAutolinkOutcome(
                status=CalendarAutolinkStatus.UNSUPPORTED,
                detail=resolution.detail,
            )
        provider, base_url = resolution.require_target()
        try:
            integration = await self.connect_integration(
                user_id=user_id,
                company_id=company_id,
                payload=CalendarIntegrationConnectPayload(
                    provider=provider,
                    mailbox_binding_id=mailbox_binding_id,
                    username=email_address,
                    access_token=password,
                    caldav_base_url=base_url,
                ),
            )
        except httpx2.HTTPStatusError as error:
            if error.response.status_code not in {401, 403}:
                raise
            # Пароль ящика не подошёл к CalDAV: у Mail.ru пароль внешнего
            # приложения выдаётся отдельно для календаря.
            return CalendarAutolinkOutcome(
                status=CalendarAutolinkStatus.NEEDS_PASSWORD,
                provider=provider,
                detail=(
                    f"{base_url} rejected the mailbox password "
                    f"(HTTP {error.response.status_code}): a separate app password "
                    "for the calendar is required"
                ),
            )
        return CalendarAutolinkOutcome(
            status=CalendarAutolinkStatus.LINKED,
            provider=provider,
            integration_id=integration.integration_id,
            detail=resolution.detail,
        )

    async def delete_calendar_integrations_for_mailbox(
        self,
        *,
        company_id: str,
        mailbox_binding_id: str,
    ) -> int:
        """Снять календарные интеграции ящика при его отвязке."""
        return await IntegrationCredential.delete_count_by_mailbox_binding_and_service(
            company_id=company_id,
            mailbox_binding_id=mailbox_binding_id,
            service="calendar",
        )

    async def upsert_imip_event(
        self,
        *,
        payload: CalendarEventUpsertPayload,
        user_id: str,
        company_id: str,
    ) -> CalendarEvent:
        """
        Идемпотентный upsert события из iMIP-приглашения: дедуп по source_id
        (`imip:{uid}`), чтобы повторный mail sync не плодил дубли.
        """
        if not payload.source_id or not payload.source_id.strip():
            raise ValueError("iMIP calendar payload requires source_id")
        existing = await CalendarEvent.by_company_source_and_source_id(
            company_id=company_id,
            source=payload.source,
            source_id=payload.source_id,
        )
        return await self.upsert_event(
            event_id=existing.event_id if existing else None,
            payload=payload,
            user_id=user_id,
            company_id=company_id,
        )

    async def disconnect_integration(self, user_id: str, company_id: str, integration_id: str) -> None:
        deleted = await IntegrationCredential.delete_by_credential_id(
            credential_id=integration_id,
            company_id=company_id,
            user_id=user_id,
        )
        if not deleted:
            raise ValueError(f"Calendar integration {integration_id} not found")

    async def run_sync(
        self,
        user_id: str,
        company_id: str,
        start_at: datetime,
        end_at: datetime,
        integration_id: str,
    ) -> dict[str, int]:
        if _ensure_utc(start_at) >= _ensure_utc(end_at):
            raise ValueError("Calendar sync range start_at must be before end_at")
        credential = await IntegrationCredential.find_for_user(
            company_id=company_id,
            user_id=user_id,
            credential_id=integration_id,
        )
        if credential is None or credential.service != "calendar":
            raise ValueError(f"Calendar integration {integration_id} not found")
        integration = calendar_integration_from_credential(credential)
        provider = integration.provider
        if not integration.settings.sync_enabled:
            raise ValueError(f"Calendar integration {integration_id} is disabled")
        calendar_id = integration.settings.default_calendar_id
        if not calendar_id:
            raise ValueError(f"{provider} integration default_calendar_id is required")

        imported = 0
        exported = 0
        if provider == CalendarProvider.GOOGLE:
            google_integration = integration
            if self._is_google_access_token_expired(google_integration.credentials):
                google_integration = await self._refresh_google_access_token(integration=google_integration)

            async def _run_google_sync(current_integration: CalendarIntegration) -> tuple[int, int]:
                imported_events = 0
                exported_events = 0
                if current_integration.settings.sync_inbound_enabled:
                    imported_events = await self._sync_google_inbound(
                        company_id=company_id,
                        user_id=user_id,
                        credentials=current_integration.credentials,
                        calendar_id=calendar_id,
                        start_at=start_at,
                        end_at=end_at,
                    )
                if current_integration.settings.sync_outbound_enabled:
                    exported_events = await self._sync_google_outbound(
                        user_id=user_id,
                        company_id=company_id,
                        credentials=current_integration.credentials,
                        calendar_id=calendar_id,
                        start_at=start_at,
                        end_at=end_at,
                    )
                return imported_events, exported_events

            try:
                imported, exported = await _run_google_sync(google_integration)
            except httpx2.HTTPStatusError as error:
                if error.response.status_code != 401:
                    raise
                google_integration = await self._refresh_google_access_token(integration=google_integration)
                imported, exported = await _run_google_sync(google_integration)
            return {"imported": imported, "exported": exported}
        if provider in CALDAV_PROVIDERS:
            if not integration.credentials.username:
                raise ValueError(f"{provider} integration username is required")
            client = self._caldav_client_for(integration)
            if integration.settings.sync_inbound_enabled:
                imported = await self._sync_caldav_inbound(
                    provider=provider,
                    client=client,
                    company_id=company_id,
                    user_id=user_id,
                    credentials=integration.credentials,
                    calendar_id=calendar_id,
                    mailbox_binding_id=integration.mailbox_binding_id,
                    start_at=start_at,
                    end_at=end_at,
                )
            if integration.settings.sync_outbound_enabled:
                exported = await self._sync_caldav_outbound(
                    provider=provider,
                    client=client,
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
        existing = await CalendarEvent.list_overlapping_by_start_at_asc(
            company_id=company_id,
            start_at=start_at - timedelta(days=3650),
            end_at=end_at + timedelta(days=3650),
            limit=10000,
        )
        imported = 0
        now = datetime.now(timezone.utc)
        for item in items:
            if item.id is None or item.id == "":
                continue
            matched = None
            for candidate in existing:
                for ref in candidate.external_refs:
                    if (
                        ref.provider == CalendarProvider.GOOGLE
                        and ref.calendar_id == calendar_id
                        and ref.external_event_id == item.id
                    ):
                        matched = candidate
                        break
                if matched:
                    break
            if item.start is None or item.end is None:
                continue
            start_value = _ensure_utc(_parse_google_datetime(item.start))
            end_value = _ensure_utc(_parse_google_datetime(item.end))
            if start_value >= end_value:
                continue
            raw_status = item.status or CalendarEventStatus.CONFIRMED.value
            status = CalendarEventStatus(raw_status)
            recurrence_rule = item.recurrence[0] if item.recurrence else None
            event = CalendarEvent(
                event_id=matched.event_id if matched else uuid4().hex,
                source=CalendarEventSource.GOOGLE,
                source_id=item.id,
                company_id=company_id,
                namespace=None,
                kind="event",
                title=item.summary if item.summary else "Google event",
                description=item.description,
                location=item.location,
                status=status,
                timezone=item.start.time_zone or "UTC",
                all_day=item.start.date is not None and item.start.date_time is None,
                start_at=start_value,
                end_at=end_value,
                attendees=[],
                recurrence_rule=recurrence_rule,
                recurrence_id=item.recurring_event_id,
                series_id=item.i_cal_uid,
                deep_link=item.html_link,
                external_refs=[
                    CalendarExternalRef(
                        provider=CalendarProvider.GOOGLE,
                        calendar_id=calendar_id,
                        external_event_id=item.id,
                        etag=item.etag,
                        last_synced_at=now,
                    )
                ],
                metadata={},
                created_by_user_id=matched.created_by_user_id if matched else user_id,
                updated_by_user_id=user_id,
                created_at=matched.created_at if matched else now,
                updated_at=now,
            )
            await CalendarEvent.merge_by_event_id(event)
            imported += 1
        return imported

    async def _sync_caldav_inbound(
        self,
        provider: CalendarProvider,
        client: CalDavClient,
        company_id: str,
        user_id: str,
        credentials: CalendarIntegrationCredentials,
        calendar_id: str,
        mailbox_binding_id: str | None,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        if not credentials.username:
            raise ValueError(f"{provider} integration username is required")
        source = calendar_source_for_provider(provider)
        items = await client.list_events(
            username=credentials.username,
            app_password=credentials.access_token,
            calendar_id=calendar_id,
            start_at=start_at,
            end_at=end_at,
        )
        existing = await CalendarEvent.list_overlapping_by_start_at_asc(
            company_id=company_id,
            start_at=start_at - timedelta(days=3650),
            end_at=end_at + timedelta(days=3650),
            limit=10000,
        )
        imported = 0
        now = datetime.now(timezone.utc)
        for item in items:
            matched = None
            for candidate in existing:
                for ref in candidate.external_refs:
                    if (
                        ref.provider == provider
                        and ref.calendar_id == calendar_id
                        and ref.external_event_id == item.href
                    ):
                        matched = candidate
                        break
                if matched:
                    break
            start_value = _ensure_utc(item.start_at)
            end_value = _ensure_utc(item.end_at)
            if start_value >= end_value:
                logger.warning(
                    "calendar.caldav_event_skipped_bad_range",
                    provider=provider.value,
                    href=item.href,
                )
                continue
            status = CalendarEventStatus(item.status)
            event = CalendarEvent(
                event_id=matched.event_id if matched else uuid4().hex,
                source=source,
                source_id=item.id,
                company_id=company_id,
                namespace=None,
                kind="event",
                title=item.summary if item.summary else f"{provider.value} event",
                description=item.description,
                location=item.location,
                status=status,
                timezone="UTC",
                all_day=item.all_day,
                start_at=start_value,
                end_at=end_value,
                attendees=[],
                recurrence_rule=None,
                recurrence_id=None,
                series_id=None,
                deep_link=item.url,
                external_refs=[
                    CalendarExternalRef(
                        provider=provider,
                        calendar_id=calendar_id,
                        external_event_id=item.href,
                        etag=item.etag,
                        last_synced_at=now,
                    )
                ],
                metadata={},
                mailbox_binding_id=mailbox_binding_id,
                created_by_user_id=matched.created_by_user_id if matched else user_id,
                updated_by_user_id=user_id,
                created_at=matched.created_at if matched else now,
                updated_at=now,
            )
            await CalendarEvent.merge_by_event_id(event)
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
        events = await CalendarEvent.list_overlapping_by_start_at_asc(
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
            payload = GoogleCalendarEventUpsertPayload(
                summary=event.title,
                description=event.description or "",
                location=event.location or "",
                status=event.status,
                start=GoogleCalendarDateTimePayload.model_validate(
                    {
                        "dateTime": _iso_datetime(event.start_at),
                        "timeZone": event.timezone,
                    }
                ),
                end=GoogleCalendarDateTimePayload.model_validate(
                    {
                        "dateTime": _iso_datetime(event.end_at),
                        "timeZone": event.timezone,
                    }
                ),
            )
            saved = await self._google_client.upsert_event(
                access_token=credentials.access_token,
                calendar_id=calendar_id,
                external_event_id=ext_id,
                body=payload,
            )
            refs = [ref for ref in event.external_refs if not (ref.provider == CalendarProvider.GOOGLE and ref.calendar_id == calendar_id)]
            refs.append(
                CalendarExternalRef(
                    provider=CalendarProvider.GOOGLE,
                    calendar_id=calendar_id,
                    external_event_id=saved.id,
                    etag=saved.etag,
                    last_synced_at=datetime.now(timezone.utc),
                )
            )
            event.external_refs = refs
            event.updated_by_user_id = user_id
            event.updated_at = datetime.now(timezone.utc)
            await CalendarEvent.merge_by_event_id(event)
            exported += 1
        return exported

    async def _sync_caldav_outbound(
        self,
        provider: CalendarProvider,
        client: CalDavClient,
        user_id: str,
        company_id: str,
        credentials: CalendarIntegrationCredentials,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        if not credentials.username:
            raise ValueError(f"{provider} integration username is required")
        events = await CalendarEvent.list_overlapping_by_start_at_asc(
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
                if ref.provider == provider and ref.calendar_id == calendar_id:
                    ext_id = ref.external_event_id
                    break
            saved = await client.upsert_event(
                username=credentials.username,
                app_password=credentials.access_token,
                calendar_id=calendar_id,
                external_event_id=ext_id,
                event=event,
            )
            refs = [ref for ref in event.external_refs if not (ref.provider == provider and ref.calendar_id == calendar_id)]
            refs.append(
                CalendarExternalRef(
                    provider=provider,
                    calendar_id=calendar_id,
                    external_event_id=saved.href,
                    etag=saved.etag,
                    last_synced_at=datetime.now(timezone.utc),
                )
            )
            event.external_refs = refs
            event.updated_by_user_id = user_id
            event.updated_at = datetime.now(timezone.utc)
            await CalendarEvent.merge_by_event_id(event)
            exported += 1
        return exported

    async def _integration_for_external_ref(
        self,
        *,
        company_id: str,
        user_id: str,
        ref: CalendarExternalRef,
    ) -> CalendarIntegration | None:
        """
        Интеграция, через которую событие ушло во внешний календарь. У одного
        провайдера может быть несколько интеграций (по одной на ящик), поэтому
        различаем их по calendar_id из ref.
        """
        credentials = await IntegrationCredential.list_by_user_provider_service_created_at_asc(
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider(ref.provider),
            service="calendar",
        )
        for credential in credentials:
            integration = calendar_integration_from_credential(credential)
            if integration.settings.default_calendar_id == ref.calendar_id:
                return integration
        return None

    async def _delete_external_links(self, event: CalendarEvent) -> None:
        owner_user_id = event.updated_by_user_id or event.created_by_user_id
        if owner_user_id is None or not owner_user_id.strip():
            return
        for ref in event.external_refs:
            integration = await self._integration_for_external_ref(
                company_id=event.company_id,
                user_id=owner_user_id,
                ref=ref,
            )
            if integration is None:
                continue
            if ref.provider == CalendarProvider.GOOGLE:
                await self._google_client.delete_event(
                    access_token=integration.credentials.access_token,
                    calendar_id=ref.calendar_id,
                    external_event_id=ref.external_event_id,
                )
            elif ref.provider in CALDAV_PROVIDERS:
                if not integration.credentials.username:
                    raise ValueError(f"{ref.provider} integration username is required")
                client = self._caldav_client_for(integration)
                await client.delete_event(
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
        notes_response = await self._service_client.post(
            "crm",
            "/crm/api/v1/entities/query",
            json={"entity_type": "note", "limit": 200, "search_mode": "hybrid"},
        )
        notes_items_raw = notes_response.get("items") if isinstance(notes_response, dict) else None
        notes_items = (
            require_json_array(notes_items_raw, "crm.notes.items")
            if isinstance(notes_items_raw, list)
            else []
        )
        events: list[CalendarEvent] = []
        now = datetime.now(timezone.utc)
        for item in notes_items:
            if not isinstance(item, dict):
                continue
            source_id = item.get("entity_id")
            if not isinstance(source_id, str) or source_id == "":
                continue
            raw_date = item.get("note_date")
            if not isinstance(raw_date, str) or raw_date == "":
                continue
            raw_name = item.get("name")
            raw_description = item.get("description")
            event = self._build_crm_calendar_event(
                source_id=source_id,
                date_str=raw_date[:10],
                kind="note",
                title=raw_name if isinstance(raw_name, str) else None,
                description=raw_description if isinstance(raw_description, str) else None,
                company_id=company_id,
                user_id=user_id,
                now=now,
                start_at=start_at,
                end_at=end_at,
            )
            if event is not None:
                events.append(event)

        # Срок задач живёт в парном WorkItem(crm_activity), не в CRM-узле.
        tasks_response = await self._service_client.get(
            "worktracker",
            "/worktracker/api/v1/work-items?kind=crm_activity&limit=200",
        )
        tasks_items_raw = tasks_response.get("items") if isinstance(tasks_response, dict) else None
        tasks_items = (
            require_json_array(tasks_items_raw, "worktracker.items")
            if isinstance(tasks_items_raw, list)
            else []
        )
        for item in tasks_items:
            if not isinstance(item, dict):
                continue
            due_raw = item.get("due_date")
            if not isinstance(due_raw, str) or due_raw == "":
                continue
            entity_id = self._crm_entity_id_from_work_item_links(item.get("links"))
            if entity_id is None:
                continue
            raw_title = item.get("title")
            raw_task_description = item.get("description")
            event = self._build_crm_calendar_event(
                source_id=entity_id,
                date_str=due_raw[:10],
                kind="task",
                title=raw_title if isinstance(raw_title, str) else None,
                description=raw_task_description if isinstance(raw_task_description, str) else None,
                company_id=company_id,
                user_id=user_id,
                now=now,
                start_at=start_at,
                end_at=end_at,
            )
            if event is not None:
                events.append(event)
        return events

    @staticmethod
    def _crm_entity_id_from_work_item_links(links: JsonValue) -> str | None:
        if not isinstance(links, list):
            return None
        for link in links:
            if not isinstance(link, dict):
                continue
            if link.get("link_kind") == "crm_entity":
                entity_id = link.get("entity_id")
                if isinstance(entity_id, str) and entity_id:
                    return entity_id
        return None

    def _build_crm_calendar_event(
        self,
        *,
        source_id: str,
        date_str: str,
        kind: str,
        title: str | None,
        description: str | None,
        company_id: str,
        user_id: str,
        now: datetime,
        start_at: datetime,
        end_at: datetime,
    ) -> CalendarEvent | None:
        start_value = datetime.fromisoformat(f"{date_str}T09:00:00+00:00")
        end_value = datetime.fromisoformat(f"{date_str}T10:00:00+00:00")
        if start_value >= end_at or end_value <= start_at:
            return None
        return CalendarEvent(
            event_id=f"crm-{source_id}",
            source=CalendarEventSource.CRM,
            source_id=source_id,
            company_id=company_id,
            namespace=None,
            kind=kind,
            title=title if title else "CRM event",
            description=description,
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

    async def _fetch_sync_events(
        self,
        company_id: str,
        user_id: str,
        start_at: datetime,
        end_at: datetime,
        exclude_platform_event_ids: set[str],
    ) -> list[CalendarEvent]:
        params: dict[str, str] = {
            "start_at": _iso_datetime(_ensure_utc(start_at)),
            "end_at": _iso_datetime(_ensure_utc(end_at)),
        }
        rows = await self._service_client.get(
            "sync",
            "/sync/api/v1/calls/links/scheduled",
            params=params,
        )
        events: list[CalendarEvent] = []
        now = datetime.now(timezone.utc)
        if not isinstance(rows, list):
            return events
        for item in rows:
            if not isinstance(item, dict):
                continue
            cal_id = item.get("calendar_event_id")
            if not isinstance(cal_id, str) or cal_id == "":
                continue
            if cal_id in exclude_platform_event_ids:
                continue
            raw_start = item.get("scheduled_start_at")
            raw_end = item.get("scheduled_end_at")
            if not isinstance(raw_start, str) or not isinstance(raw_end, str):
                continue
            start_value = _ensure_utc(datetime.fromisoformat(raw_start.replace("Z", "+00:00")))
            end_value = _ensure_utc(datetime.fromisoformat(raw_end.replace("Z", "+00:00")))
            if start_value >= end_at or end_value <= start_at:
                continue
            title_raw = item.get("title")
            title = title_raw if isinstance(title_raw, str) and title_raw.strip() else "Sync"
            join = item.get("join_url")
            if not isinstance(join, str) or join == "":
                continue
            deep = join
            source_id = item.get("link_token")
            if not isinstance(source_id, str) or source_id == "":
                continue
            events.append(
                CalendarEvent(
                    event_id=f"sync-cal-{cal_id}",
                    source=CalendarEventSource.SYNC,
                    source_id=source_id,
                    company_id=company_id,
                    namespace=None,
                    kind="meeting",
                    title=title,
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
                    deep_link=deep,
                    external_refs=[],
                    metadata={"calendar_event_id": cal_id},
                    created_by_user_id=user_id,
                    updated_by_user_id=user_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        return events
