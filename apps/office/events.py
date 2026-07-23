"""Каталог событий Office на шине `platform:events`."""

from __future__ import annotations

from pydantic import BaseModel

from core.events import register_platform_event

OFFICE_DOCUMENT_SAVED = "office/document/saved"


class OfficeDocumentSavedPayload(BaseModel):
    file_id: str
    company_id: str
    title: str | None = None


register_platform_event(
    OFFICE_DOCUMENT_SAVED,
    OfficeDocumentSavedPayload,
    description="Документ Office сохранён (OnlyOffice callback).",
)
