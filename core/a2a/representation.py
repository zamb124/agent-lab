"""Negotiated result representation without introducing a second transport."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from core.models.base import StrictBaseModel


class A2ARepresentation(StrEnum):
    GENERIC_A2A = "generic-a2a"
    A2UI_0_9_1 = "a2ui-0.9.1"


class A2ARepresentationSnapshot(StrictBaseModel):
    representation: A2ARepresentation = A2ARepresentation.GENERIC_A2A
    negotiated_extensions: list[str] = Field(default_factory=list)
    extension_uri: str | None = Field(default=None, min_length=1)
    catalog_id: str | None = Field(default=None, min_length=1)
    output_mime_type: str = Field(default="application/json", min_length=1)


__all__ = ["A2ARepresentation", "A2ARepresentationSnapshot"]
