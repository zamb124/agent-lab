"""Version-neutral A2UI codec contract and strict negotiation models."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from a2a.types import Part
from pydantic import Field

from core.models.base import StrictBaseModel
from core.state.flow_ui import FlowUIDocument
from core.types import JsonObject


class A2UIClientAction(StrictBaseModel):
    version: str
    name: str = Field(min_length=1)
    surface_id: str = Field(min_length=1)
    source_component_id: str = Field(min_length=1)
    timestamp: datetime
    context: JsonObject = Field(default_factory=dict)


class A2UIClientDataModel(StrictBaseModel):
    version: str
    surfaces: dict[str, JsonObject]


class A2UIClientCapabilities(StrictBaseModel):
    version: str
    supported_catalog_ids: list[str]
    inline_catalogs: list[JsonObject] = Field(default_factory=list)


class A2UIDecodedInteraction(StrictBaseModel):
    action: A2UIClientAction
    data_model: A2UIClientDataModel | None = None
    capabilities: A2UIClientCapabilities | None = None


class A2UIBatchApplyError(StrictBaseModel):
    message_index: int = Field(ge=0)
    code: str
    message: str


class A2UIBatchApplyResult(StrictBaseModel):
    document: FlowUIDocument
    applied_message_count: int = Field(ge=0)
    errors: list[A2UIBatchApplyError] = Field(default_factory=list)


@runtime_checkable
class A2UICodec(Protocol):
    @property
    def extension_uri(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def mime_type(self) -> str: ...

    def validate_client_capabilities(
        self,
        metadata: JsonObject,
        *,
        required_catalog_id: str,
    ) -> A2UIClientCapabilities: ...

    def decode_client_action(
        self,
        part: Part,
        metadata: JsonObject,
    ) -> A2UIDecodedInteraction: ...

    def encode_document_snapshot(self, document: FlowUIDocument) -> list[JsonObject]: ...

    def encode_effect_batch(
        self,
        before: FlowUIDocument,
        after: FlowUIDocument,
    ) -> list[JsonObject]: ...

    def encode_data_part(self, messages: Sequence[JsonObject]) -> Part: ...

    def decode_data_part(self, part: Part) -> list[JsonObject]: ...

    def apply_agent_message_batch(
        self,
        document: FlowUIDocument,
        messages: Sequence[JsonObject],
    ) -> A2UIBatchApplyResult: ...


class A2UICodecRegistry:
    def __init__(self, codecs: Iterable[A2UICodec] = ()) -> None:
        self._by_extension_uri: dict[str, A2UICodec] = {}
        for codec in codecs:
            self.register(codec)

    def register(self, codec: A2UICodec) -> None:
        if codec.extension_uri in self._by_extension_uri:
            raise ValueError(f"A2UI codec already registered: {codec.extension_uri!r}")
        self._by_extension_uri[codec.extension_uri] = codec

    def get(self, extension_uri: str) -> A2UICodec:
        try:
            return self._by_extension_uri[extension_uri]
        except KeyError as exc:
            raise ValueError(f"Unsupported A2UI extension: {extension_uri!r}") from exc

    @property
    def extension_uris(self) -> tuple[str, ...]:
        return tuple(self._by_extension_uri)


__all__ = [
    "A2UIBatchApplyError",
    "A2UIBatchApplyResult",
    "A2UIClientAction",
    "A2UIClientCapabilities",
    "A2UIClientDataModel",
    "A2UICodec",
    "A2UICodecRegistry",
    "A2UIDecodedInteraction",
]
