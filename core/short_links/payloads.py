from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import StringConstraints

from core.models import StrictBaseModel

ShortLinkPayloadField: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class SyncCallJoinPayload(StrictBaseModel):
    link_token: ShortLinkPayloadField
    company_id: ShortLinkPayloadField


class CompanyInvitePayload(StrictBaseModel):
    jwt: ShortLinkPayloadField


class FlowPreviewEmbedPayload(StrictBaseModel):
    handoff_id: ShortLinkPayloadField


ShortLinkPayload: TypeAlias = (
    SyncCallJoinPayload | CompanyInvitePayload | FlowPreviewEmbedPayload
)
