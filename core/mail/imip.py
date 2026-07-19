"""iMIP (text/calendar) bridge: invite via mail ↔ CalendarEvent."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from core.mail.models import InboundMailMessage, MailAttachment, OutboundMailMessage
from core.models.calendar_models import (
    CalendarAttendee,
    CalendarEvent,
    CalendarEventSource,
    CalendarEventStatus,
    CalendarEventUpsertPayload,
)

_DT_RE = re.compile(
    r"^DTSTART(?::|;VALUE=DATE-TIME:|;TZID=[^:]+:)(\d{8}T\d{6}Z?)\r?$",
    re.MULTILINE,
)
_DTEND_RE = re.compile(
    r"^DTEND(?::|;VALUE=DATE-TIME:|;TZID=[^:]+:)(\d{8}T\d{6}Z?)\r?$",
    re.MULTILINE,
)
_SUMMARY_RE = re.compile(r"^SUMMARY:(.*)\r?$", re.MULTILINE)
_UID_RE = re.compile(r"^UID:(.*)\r?$", re.MULTILINE)
_DESC_RE = re.compile(r"^DESCRIPTION:(.*)\r?$", re.MULTILINE)


def _format_ics_dt(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def _parse_ics_dt(raw: str) -> datetime:
    token = raw.strip()
    if token.endswith("Z"):
        return datetime.strptime(token, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    return datetime.strptime(token, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def build_imip_request_ics(
    *,
    event_uid: str,
    title: str,
    description: str,
    start_at: datetime,
    end_at: datetime,
    organizer_email: str,
    attendee_email: str,
) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//Platform//Mail//EN",
        "VERSION:2.0",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{event_uid}",
        f"DTSTAMP:{_format_ics_dt(datetime.now(timezone.utc))}",
        f"DTSTART:{_format_ics_dt(start_at)}",
        f"DTEND:{_format_ics_dt(end_at)}",
        f"SUMMARY:{title}",
        f"DESCRIPTION:{description}",
        f"ORGANIZER:mailto:{organizer_email}",
        f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{attendee_email}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def build_outbound_imip_invite(
    *,
    to_address: str,
    organizer_email: str,
    title: str,
    description: str,
    start_at: datetime,
    end_at: datetime,
    event_uid: str | None = None,
) -> tuple[OutboundMailMessage, str]:
    uid = event_uid if event_uid is not None else uuid.uuid4().hex
    ics = build_imip_request_ics(
        event_uid=uid,
        title=title,
        description=description,
        start_at=start_at,
        end_at=end_at,
        organizer_email=organizer_email,
        attendee_email=to_address,
    )
    message = OutboundMailMessage(
        to_addresses=[to_address],
        subject=f"Invitation: {title}",
        body_text=f"Calendar invite: {title}\n{description}",
        attachments=[
            MailAttachment(
                filename="invite.ics",
                content_type="text/calendar",
                content=ics.encode("utf-8"),
            )
        ],
    )
    return message, uid


def extract_imip_ics(message: InboundMailMessage) -> str | None:
    for attachment in message.attachments:
        if (
            attachment.content_type.startswith("text/calendar")
            or attachment.filename.lower().endswith(".ics")
        ):
            return attachment.content.decode("utf-8")
    if message.body_text is not None and "BEGIN:VCALENDAR" in message.body_text:
        return message.body_text
    return None


def calendar_upsert_payload_from_imip(
    ics_text: str,
    *,
    attendee_email: str,
    mailbox_binding_id: str,
) -> CalendarEventUpsertPayload:
    if not mailbox_binding_id.strip():
        raise ValueError("mailbox_binding_id is required for iMIP calendar upsert")
    uid_match = _UID_RE.search(ics_text)
    summary_match = _SUMMARY_RE.search(ics_text)
    start_match = _DT_RE.search(ics_text)
    end_match = _DTEND_RE.search(ics_text)
    desc_match = _DESC_RE.search(ics_text)
    if uid_match is None or summary_match is None or start_match is None or end_match is None:
        raise ValueError("iMIP ICS missing UID/SUMMARY/DTSTART/DTEND")
    event_uid = uid_match.group(1).strip()
    title = summary_match.group(1).strip()
    description = desc_match.group(1).strip() if desc_match is not None else None
    return CalendarEventUpsertPayload(
        title=title,
        kind="event",
        source=CalendarEventSource.PLATFORM,
        source_id=f"imip:{event_uid}",
        description=description,
        status=CalendarEventStatus.CONFIRMED,
        timezone="UTC",
        start_at=_parse_ics_dt(start_match.group(1)),
        end_at=_parse_ics_dt(end_match.group(1)),
        attendees=[
            CalendarAttendee(email=attendee_email, response_status="needsAction"),
        ],
        metadata={"imip_uid": event_uid},
        mailbox_binding_id=mailbox_binding_id,
    )


def apply_imip_to_existing_event(
    event: CalendarEvent,
    *,
    response_status: str,
    attendee_email: str,
) -> CalendarEventUpsertPayload:
    attendees: list[CalendarAttendee] = []
    matched = False
    for attendee in event.attendees:
        if attendee.email is not None and attendee.email.lower() == attendee_email.lower():
            attendees.append(
                CalendarAttendee(
                    attendee_id=attendee.attendee_id,
                    email=attendee.email,
                    display_name=attendee.display_name,
                    response_status=response_status,
                )
            )
            matched = True
        else:
            attendees.append(attendee)
    if not matched:
        attendees.append(
            CalendarAttendee(email=attendee_email, response_status=response_status)
        )
    return CalendarEventUpsertPayload(
        title=event.title,
        kind=event.kind,
        source=event.source,
        source_id=event.source_id,
        namespace=event.namespace,
        description=event.description,
        location=event.location,
        status=event.status,
        timezone=event.timezone,
        all_day=event.all_day,
        start_at=event.start_at,
        end_at=event.end_at,
        attendees=attendees,
        recurrence_rule=event.recurrence_rule,
        recurrence_id=event.recurrence_id,
        series_id=event.series_id,
        deep_link=event.deep_link,
        mailbox_binding_id=event.mailbox_binding_id,
        metadata=dict(event.metadata),
    )
