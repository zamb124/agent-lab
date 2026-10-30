"""``GET .../interface`` Flow UI: design-time документ, права поверхности, look embed и identity flow.

Runtime state и артефакты сюда не входят — они идут только через A2A Task.
"""

from __future__ import annotations

from typing import Literal

from core.models.base import StrictBaseModel
from core.models.embed_models import EmbedInterfaceLook
from core.ui_document.document import FlowUIDocument


class FlowInterfaceViewer(StrictBaseModel):
    """Права поверхности для текущего зрителя."""

    can_edit_flow: bool
    can_interact: bool
    can_share: bool
    auth_mode: Literal["platform", "embed", "share"]


class FlowInterfaceCapabilities(StrictBaseModel):
    cancel: bool
    files: bool
    voice: bool


class FlowInterfaceIdentity(StrictBaseModel):
    title: str
    image_url: str | None = None


class FlowInterfaceResponse(StrictBaseModel):
    flow_id: str
    branch_id: str
    document: FlowUIDocument
    viewer: FlowInterfaceViewer
    look: EmbedInterfaceLook | None = None
    capabilities: FlowInterfaceCapabilities
    flow_identity: FlowInterfaceIdentity


__all__ = [
    "FlowInterfaceCapabilities",
    "FlowInterfaceIdentity",
    "FlowInterfaceResponse",
    "FlowInterfaceViewer",
]
