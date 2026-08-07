"""One A2A Artifact representation for each materialized Flow UI change."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy

from a2a.types import Artifact, Part

from core.a2a import (
    A2UI_EXTENSION_URI,
    A2UI_MIME_TYPE,
    A2ARepresentation,
    A2ARepresentationSnapshot,
    struct_from_mapping,
    value_from_json,
)
from core.a2ui import A2UI091Codec
from core.state.flow_ui import FlowUIDocument, FlowUITransition
from core.types import JsonObject, JsonValue, require_json_object


def _surface_id(message: JsonObject) -> str:
    for key in ("createSurface", "updateComponents", "updateDataModel", "deleteSurface"):
        payload = message.get(key)
        if isinstance(payload, dict):
            surface_id = payload.get("surfaceId")
            if isinstance(surface_id, str) and surface_id:
                return surface_id
    raise ValueError("A2UI server message does not identify a surface")


def _iter_accessible_strings(value: JsonValue) -> Iterable[str]:
    if isinstance(value, str):
        text = value.strip()
        if text:
            yield text
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_accessible_strings(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_accessible_strings(item)


def _accessible_summary(document: FlowUIDocument, surface_id: str | None) -> str:
    page = document.pages[document.active_page_id]
    title = page.title.default.strip() or "Flow interface"
    surfaces = (
        [document.surfaces[surface_id]]
        if surface_id is not None and surface_id in document.surfaces
        else list(document.surfaces.values())
    )
    strings: list[str] = []
    seen: set[str] = set()
    for surface in surfaces:
        for component in surface.components.values():
            for key in ("label", "title", "text", "description"):
                raw = component.properties.get(key)
                if isinstance(raw, str) and raw.strip() and raw.strip() not in seen:
                    strings.append(raw.strip())
                    seen.add(raw.strip())
        for text in _iter_accessible_strings(surface.data_model.content):
            if text not in seen:
                strings.append(text)
                seen.add(text)
            if len(strings) >= 24:
                break
    body = "\n\n".join(strings[:24])
    return f"# {title}\n\n{body}" if body else f"# {title}\n\nInteractive interface updated."


def _artifact_metadata(
    document: FlowUIDocument,
    representation: A2ARepresentationSnapshot,
    *,
    base_revision: int | None,
    surface_id: str | None,
) -> JsonObject:
    pages = {
        page_id: require_json_object(
            page.model_dump(mode="json"),
            f"FlowUIPage.{page_id}",
        )
        for page_id, page in document.pages.items()
    }
    return {
        "platformUi": {
            "documentId": document.document_id,
            "baseRevision": base_revision,
            "revision": document.revision,
            "schemaVersion": document.schema_version,
            "templateVersion": document.template_version,
            "activePageId": document.active_page_id,
            "surfaceId": surface_id,
            "representation": str(representation.representation),
            "catalogId": representation.catalog_id or document.catalog_id,
            "pages": pages,
            "sessionViewState": deepcopy(document.session_view_state),
            "policy": require_json_object(
                document.policy.model_dump(mode="json"),
                "FlowInterfacePolicySnapshot",
            ),
        }
    }


class FlowUIRepresentationService:
    def __init__(self) -> None:
        self._codec: A2UI091Codec = A2UI091Codec()

    def encode_transition(
        self,
        transition: FlowUITransition,
        representation: A2ARepresentationSnapshot,
    ) -> list[Artifact]:
        if representation.representation == A2ARepresentation.A2UI_0_9_1:
            messages = self._codec.encode_effect_batch(
                transition.before,
                transition.after,
            )
            if not messages:
                return self.encode_snapshot(transition.after, representation)
            grouped: dict[str, list[JsonObject]] = defaultdict(list)
            for message in messages:
                grouped[_surface_id(message)].append(message)
            return [
                self._a2ui_artifact(
                    document=transition.after,
                    surface_id=surface_id,
                    messages=surface_messages,
                    base_revision=transition.before.revision,
                )
                for surface_id, surface_messages in grouped.items()
            ]
        return [
            self._generic_artifact(
                document=transition.after,
                representation=representation,
                base_revision=transition.before.revision,
            )
        ]

    def encode_snapshot(
        self,
        document: FlowUIDocument,
        representation: A2ARepresentationSnapshot,
    ) -> list[Artifact]:
        if representation.representation == A2ARepresentation.A2UI_0_9_1:
            grouped: dict[str, list[JsonObject]] = defaultdict(list)
            for message in self._codec.encode_document_snapshot(document):
                grouped[_surface_id(message)].append(message)
            return [
                self._a2ui_artifact(
                    document=document,
                    surface_id=surface_id,
                    messages=messages,
                    base_revision=None,
                )
                for surface_id, messages in grouped.items()
            ]
        return [
            self._generic_artifact(
                document=document,
                representation=representation,
                base_revision=None,
            )
        ]

    def _a2ui_artifact(
        self,
        *,
        document: FlowUIDocument,
        surface_id: str,
        messages: list[JsonObject],
        base_revision: int | None,
    ) -> Artifact:
        return Artifact(
            artifact_id=f"flow-ui:{document.document_id}:{surface_id}",
            name=f"ui.surface.{surface_id}",
            description="Declarative Linnex Flow UI surface",
            parts=[self._codec.encode_data_part(messages)],
            metadata=struct_from_mapping(
                _artifact_metadata(
                    document,
                    A2ARepresentationSnapshot(
                        representation=A2ARepresentation.A2UI_0_9_1,
                        negotiated_extensions=[A2UI_EXTENSION_URI],
                        extension_uri=A2UI_EXTENSION_URI,
                        catalog_id=document.catalog_id,
                        output_mime_type=A2UI_MIME_TYPE,
                    ),
                    base_revision=base_revision,
                    surface_id=surface_id,
                )
            ),
            extensions=[A2UI_EXTENSION_URI],
        )

    @staticmethod
    def _generic_artifact(
        *,
        document: FlowUIDocument,
        representation: A2ARepresentationSnapshot,
        base_revision: int | None,
    ) -> Artifact:
        payload = require_json_object(
            document.model_dump(mode="json"),
            "FlowUIDocument",
        )
        return Artifact(
            artifact_id=f"flow-ui:{document.document_id}",
            name="ui.document",
            description="Accessible Flow UI snapshot",
            parts=[
                Part(
                    text=_accessible_summary(document, None),
                    media_type="text/markdown",
                ),
                Part(
                    data=value_from_json(
                        {
                            "flowUi": deepcopy(payload),
                            "revision": document.revision,
                        }
                    ),
                    media_type="application/json",
                ),
            ],
            metadata=struct_from_mapping(
                _artifact_metadata(
                    document,
                    representation,
                    base_revision=base_revision,
                    surface_id=None,
                )
            ),
        )


__all__ = ["FlowUIRepresentationService"]
