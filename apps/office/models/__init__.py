"""Таблицы Documents. Одна таблица — один модуль."""

from apps.office.models.event import OfficeDocumentEvent
from apps.office.models.link import DocumentLink
from apps.office.models.revision import OfficeDocumentRevision

__all__ = [
    "DocumentLink",
    "OfficeDocumentEvent",
    "OfficeDocumentRevision",
]
