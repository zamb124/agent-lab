"""Exact A2UI v0.9.1 wire boundary over standard A2A v1.0 data Parts."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

from a2a.types import Part

from core.a2a.codec import (
    get_part_data,
    mapping_from_struct,
    part_has_data,
    struct_from_mapping,
    value_from_json,
)
from core.a2a.extensions import (
    A2UI_EXTENSION_URI,
    A2UI_MIME_TYPE,
    A2UI_PLATFORM_CATALOG_ID,
    A2UI_VERSION,
    is_a2ui_media_type,
)
from core.a2ui.codec import (
    A2UIBatchApplyError,
    A2UIBatchApplyResult,
    A2UIClientAction,
    A2UIClientCapabilities,
    A2UIClientDataModel,
    A2UIDecodedInteraction,
)
from core.state.flow_ui import (
    FlowUIAction,
    FlowUICheck,
    FlowUIComponent,
    FlowUIComponentKind,
    FlowUIContainerLayout,
    FlowUIDataModel,
    FlowUIDocument,
    FlowUIProvenance,
    FlowUIResponsivePlacement,
    FlowUIStackDefinition,
    FlowUISurface,
)
from core.state.flow_ui_delta import delete_json_pointer, set_json_pointer
from core.types import JsonObject, JsonValue, require_json_object, require_json_value

_ACCEPTED_VERSIONS = frozenset({"v0.9", "v0.9.1"})
_SERVER_MESSAGE_KEYS = frozenset(
    {"createSurface", "updateComponents", "updateDataModel", "deleteSurface"}
)
_CLIENT_MESSAGE_KEYS = frozenset({"action", "error"})
_MESSAGE_KEYS = _SERVER_MESSAGE_KEYS | _CLIENT_MESSAGE_KEYS
_COMPONENT_RESERVED_FIELDS = frozenset(
    {
        "id",
        "component",
        "children",
        "child",
        "kind",
        "layout",
        "placement",
        "action",
        "actionSlot",
        "actions",
        "visibility",
        "checks",
        "provenance",
    }
)


@dataclass
class _WireSurface:
    catalog_id: str
    send_data_model: bool
    components: dict[str, JsonObject]
    data_model: JsonObject


def _camelize(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    if not isinstance(value, dict):
        return value
    output: JsonObject = {}
    for key, item in value.items():
        segments = key.split("_")
        camel_key = segments[0] + "".join(segment.capitalize() for segment in segments[1:])
        output[camel_key] = _camelize(item)
    return output


def _snakeize(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [_snakeize(item) for item in value]
    if not isinstance(value, dict):
        return value
    output: JsonObject = {}
    for key, item in value.items():
        chars: list[str] = []
        for char in key:
            if char.isupper():
                chars.extend(("_", char.lower()))
            else:
                chars.append(char)
        output["".join(chars)] = _snakeize(item)
    return output


def _encode_action(action: FlowUIAction) -> JsonObject:
    if action.kind == "local":
        return {
            "functionCall": {
                "call": action.name,
                "args": deepcopy(action.context),
            }
        }
    return {
        "event": {
            "name": action.name,
            "context": deepcopy(action.context),
        }
    }


def _decode_action(payload: JsonObject) -> FlowUIAction:
    if set(payload) == {"event"}:
        event = require_json_object(payload["event"], "component.action.event")
        if set(event) - {"name", "context"}:
            raise ValueError("A2UI event action contains unknown fields")
        name = event.get("name")
        context = event.get("context", {})
        if not isinstance(name, str) or not name:
            raise ValueError("A2UI event action requires name")
        return FlowUIAction(
            kind="event",
            name=name,
            context=require_json_object(context, "component.action.event.context"),
        )
    if set(payload) == {"functionCall"}:
        function = require_json_object(
            payload["functionCall"], "component.action.functionCall"
        )
        if set(function) - {"call", "args", "returnType"}:
            raise ValueError("A2UI functionCall contains unknown fields")
        name = function.get("call")
        args = function.get("args", {})
        if not isinstance(name, str) or not name:
            raise ValueError("A2UI functionCall requires call")
        return FlowUIAction(
            kind="local",
            name=name,
            context=require_json_object(args, "component.action.functionCall.args"),
        )
    raise ValueError("A2UI action must contain exactly event or functionCall")


def _encode_component(component: FlowUIComponent) -> JsonObject:
    encoded: JsonObject = {
        "id": component.component_id,
        "component": component.type,
        **deepcopy(component.properties),
    }
    for property_name, path in component.bindings.items():
        encoded[property_name] = {"path": path}
    if component.children:
        encoded["children"] = list(component.children)
    encoded["kind"] = component.kind
    if component.container_layout is not None:
        layout = require_json_object(
            component.container_layout.model_dump(mode="json", exclude_none=True),
            "FlowUIContainerLayout",
        )
        encoded["layout"] = _camelize(layout)
    placement = require_json_object(
        component.placement.model_dump(mode="json", exclude_none=True),
        "FlowUIResponsivePlacement",
    )
    encoded["placement"] = _camelize(placement)
    if len(component.actions) == 1:
        slot, action = next(iter(component.actions.items()))
        encoded["action"] = _encode_action(action)
        encoded["actionSlot"] = slot
    elif component.actions:
        encoded["actions"] = {
            slot: _encode_action(action) for slot, action in component.actions.items()
        }
    if component.visibility is not None:
        encoded["visibility"] = deepcopy(component.visibility)
    if component.checks:
        encoded["checks"] = [
            require_json_object(
                check.model_dump(mode="json", exclude_none=True),
                "component.checks[]",
            )
            for check in component.checks
        ]
    if component.provenance is not None:
        provenance = require_json_object(
            component.provenance.model_dump(mode="json", exclude_none=True),
            "FlowUIProvenance",
        )
        encoded["provenance"] = _camelize(provenance)
    return encoded


def _decode_component(payload: JsonObject) -> FlowUIComponent:
    component_id = payload.get("id")
    component_type = payload.get("component")
    if not isinstance(component_id, str) or not component_id:
        raise ValueError("A2UI component requires a non-empty id")
    if not isinstance(component_type, str) or not component_type:
        raise ValueError("A2UI component requires a non-empty component type")

    children_value = payload.get("children")
    if children_value is None and isinstance(payload.get("child"), str):
        children_value = [payload["child"]]
    children: list[str] = []
    if children_value is not None:
        if not isinstance(children_value, list) or not all(
            isinstance(child, str) and child for child in children_value
        ):
            raise ValueError("A2UI component children must be non-empty strings")
        children = cast(list[str], children_value)

    bindings: dict[str, str] = {}
    properties: JsonObject = {}
    for key, value in payload.items():
        if key in _COMPONENT_RESERVED_FIELDS:
            continue
        if isinstance(value, dict) and set(value) == {"path"}:
            path = value.get("path")
            if isinstance(path, str) and path.startswith("/"):
                bindings[key] = path
                continue
        properties[key] = deepcopy(value)

    actions: dict[str, FlowUIAction] = {}
    action_value = payload.get("action")
    if isinstance(action_value, dict):
        slot = payload.get("actionSlot", "press")
        if not isinstance(slot, str) or not slot:
            raise ValueError("A2UI actionSlot must be a non-empty string")
        actions[slot] = _decode_action(
            require_json_object(action_value, "component.action")
        )
    actions_value = payload.get("actions")
    if actions_value is not None:
        actions_payload = require_json_object(actions_value, "component.actions")
        for slot, item in actions_payload.items():
            if not slot:
                raise ValueError("A2UI action slot must be non-empty")
            actions[slot] = _decode_action(
                require_json_object(item, f"component.actions.{slot}")
            )

    explicit_kind = payload.get("kind")
    if explicit_kind not in {None, "leaf", "container", "overlay"}:
        raise ValueError("A2UI platform component kind is invalid")
    kind = cast(
        FlowUIComponentKind,
        explicit_kind or ("container" if children else "leaf"),
    )

    layout_value = payload.get("layout")
    layout: FlowUIContainerLayout | None = None
    if layout_value is not None:
        layout = FlowUIContainerLayout.model_validate(
            _snakeize(require_json_value(layout_value, "component.layout"))
        )
    elif kind == "container":
        layout = FlowUIContainerLayout(
            mode="stack",
            stack=FlowUIStackDefinition(),
        )

    placement_value = payload.get("placement")
    placement = (
        FlowUIResponsivePlacement()
        if placement_value is None
        else FlowUIResponsivePlacement.model_validate(
            _snakeize(require_json_value(placement_value, "component.placement"))
        )
    )
    provenance_value = payload.get("provenance")
    provenance = (
        None
        if provenance_value is None
        else FlowUIProvenance.model_validate(
            _snakeize(require_json_value(provenance_value, "component.provenance"))
        )
    )
    visibility_value = payload.get("visibility")
    checks_value = payload.get("checks", [])
    if not isinstance(checks_value, list) or not all(
        isinstance(item, dict) for item in checks_value
    ):
        raise ValueError("A2UI component checks must be objects")
    return FlowUIComponent(
        component_id=component_id,
        type=component_type,
        kind=kind,
        properties=properties,
        children=children,
        container_layout=layout,
        placement=placement,
        bindings=bindings,
        actions=actions,
        visibility=(
            None
            if visibility_value is None
            else require_json_object(visibility_value, "component.visibility")
        ),
        checks=[
            FlowUICheck.model_validate(require_json_object(item, "component.checks[]"))
            for item in checks_value
        ],
        provenance=provenance,
    )


def _surface_to_wire(surface: FlowUISurface) -> _WireSurface:
    return _WireSurface(
        catalog_id=surface.catalog_id,
        send_data_model=surface.send_data_model,
        components={
            component_id: _encode_component(component)
            for component_id, component in surface.components.items()
        },
        data_model=require_json_object(
            surface.data_model.model_dump(mode="json"), "FlowUIDataModel"
        ),
    )


def _wire_to_surface(surface_id: str, wire: _WireSurface) -> FlowUISurface:
    components = {
        component_id: _decode_component(payload)
        for component_id, payload in wire.components.items()
    }
    if "root" not in components:
        raise ValueError(f"A2UI surface {surface_id!r} has no root component")
    return FlowUISurface(
        surface_id=surface_id,
        catalog_id=wire.catalog_id,
        root_component_id="root",
        components=components,
        data_model=FlowUIDataModel.model_validate(wire.data_model),
        send_data_model=wire.send_data_model,
    )


def _message(kind: str, payload: JsonObject) -> JsonObject:
    return {"version": A2UI_VERSION, kind: payload}


def _validate_envelope(message: JsonObject, *, server_only: bool = False) -> tuple[str, JsonObject]:
    if set(message) - ({"version"} | _MESSAGE_KEYS):
        raise ValueError("A2UI message contains unknown top-level fields")
    version = message.get("version")
    if version not in _ACCEPTED_VERSIONS:
        raise ValueError(f"Unsupported A2UI message version: {version!r}")
    keys = (set(message) & _SERVER_MESSAGE_KEYS) if server_only else (set(message) & _MESSAGE_KEYS)
    if len(keys) != 1 or len(message) != 2:
        raise ValueError("A2UI message must contain version and exactly one message payload")
    kind = next(iter(keys))
    return kind, require_json_object(message[kind], f"A2UI.{kind}")


def _json_pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _diff_data_model(
    before: JsonValue,
    after: JsonValue,
    *,
    path: str = "",
) -> list[tuple[str, JsonValue | None, bool]]:
    if before == after:
        return []
    pointer = path or "/"
    if isinstance(before, dict) and isinstance(after, dict):
        updates: list[tuple[str, JsonValue | None, bool]] = []
        for key in before:
            if key not in after:
                child_path = f"{path}/{_json_pointer_segment(key)}"
                updates.append((child_path, None, False))
        for key in after:
            child_path = f"{path}/{_json_pointer_segment(key)}"
            if key not in before:
                updates.append((child_path, deepcopy(after[key]), True))
            else:
                updates.extend(_diff_data_model(before[key], after[key], path=child_path))
        return updates
    return [(pointer, deepcopy(after), True)]


class A2UI091Codec:
    @property
    def extension_uri(self) -> str:
        return A2UI_EXTENSION_URI

    @property
    def version(self) -> str:
        return A2UI_VERSION

    @property
    def mime_type(self) -> str:
        return A2UI_MIME_TYPE

    def validate_client_capabilities(
        self,
        metadata: JsonObject,
        *,
        required_catalog_id: str,
    ) -> A2UIClientCapabilities:
        raw = metadata.get("a2uiClientCapabilities")
        capabilities = require_json_object(raw, "a2uiClientCapabilities")
        version_keys = [key for key in ("v0.9.1", "v0.9") if key in capabilities]
        if len(version_keys) != 1 or set(capabilities) != set(version_keys):
            raise ValueError("a2uiClientCapabilities must contain one supported version")
        version = version_keys[0]
        payload = require_json_object(capabilities[version], f"a2uiClientCapabilities.{version}")
        if set(payload) - {"supportedCatalogIds", "inlineCatalogs"}:
            raise ValueError("a2uiClientCapabilities contains unknown fields")
        catalog_ids = payload.get("supportedCatalogIds")
        if not isinstance(catalog_ids, list) or not all(
            isinstance(item, str) and item for item in catalog_ids
        ):
            raise ValueError("supportedCatalogIds must be a list of non-empty strings")
        if required_catalog_id not in catalog_ids:
            raise ValueError(f"A2UI client does not support catalog {required_catalog_id!r}")
        inline_value = payload.get("inlineCatalogs", [])
        if not isinstance(inline_value, list) or not all(
            isinstance(item, dict) for item in inline_value
        ):
            raise ValueError("inlineCatalogs must be a list of objects")
        if inline_value:
            raise ValueError("inline A2UI catalogs are not accepted by Linnex")
        return A2UIClientCapabilities(
            version=version,
            supported_catalog_ids=cast(list[str], catalog_ids),
            inline_catalogs=[],
        )

    def _decode_client_data_model(
        self,
        metadata: JsonObject,
    ) -> A2UIClientDataModel | None:
        raw = metadata.get("a2uiClientDataModel")
        if raw is None:
            return None
        payload = require_json_object(raw, "a2uiClientDataModel")
        if set(payload) != {"version", "surfaces"}:
            raise ValueError("a2uiClientDataModel must contain version and surfaces")
        version = payload.get("version")
        if version not in _ACCEPTED_VERSIONS:
            raise ValueError(f"Unsupported A2UI data model version: {version!r}")
        surfaces_value = require_json_object(
            payload.get("surfaces"), "a2uiClientDataModel.surfaces"
        )
        surfaces = {
            surface_id: require_json_object(value, f"a2uiClientDataModel.{surface_id}")
            for surface_id, value in surfaces_value.items()
        }
        return A2UIClientDataModel(
            version=cast(str, version),
            surfaces=surfaces,
        )

    def decode_client_action(
        self,
        part: Part,
        metadata: JsonObject,
    ) -> A2UIDecodedInteraction:
        messages = self.decode_data_part(part)
        action_messages: list[tuple[str, JsonObject]] = []
        for message in messages:
            kind, payload = _validate_envelope(message)
            if kind == "action":
                version = cast(str, message["version"])
                action_messages.append((version, payload))
        if len(action_messages) != 1:
            raise ValueError("A2UI client Part must contain exactly one action")
        version, payload = action_messages[0]
        if set(payload) != {
            "name",
            "surfaceId",
            "sourceComponentId",
            "timestamp",
            "context",
        }:
            raise ValueError("A2UI action has missing or unknown fields")
        action = A2UIClientAction.model_validate(
            {
                "version": version,
                "name": payload["name"],
                "surface_id": payload["surfaceId"],
                "source_component_id": payload["sourceComponentId"],
                "timestamp": payload["timestamp"],
                "context": payload["context"],
            }
        )
        capabilities = (
            None
            if "a2uiClientCapabilities" not in metadata
            else self.validate_client_capabilities(
                metadata,
                required_catalog_id=A2UI_PLATFORM_CATALOG_ID,
            )
        )
        return A2UIDecodedInteraction(
            action=action,
            data_model=self._decode_client_data_model(metadata),
            capabilities=capabilities,
        )

    def encode_document_snapshot(self, document: FlowUIDocument) -> list[JsonObject]:
        messages: list[JsonObject] = []
        for surface in document.surfaces.values():
            messages.extend(
                [
                    _message(
                        "createSurface",
                        {
                            "surfaceId": surface.surface_id,
                            "catalogId": surface.catalog_id,
                            "sendDataModel": surface.send_data_model,
                        },
                    ),
                    _message(
                        "updateComponents",
                        {
                            "surfaceId": surface.surface_id,
                            "components": [
                                _encode_component(component)
                                for component in surface.components.values()
                            ],
                        },
                    ),
                    _message(
                        "updateDataModel",
                        {
                            "surfaceId": surface.surface_id,
                            "path": "/",
                            "value": require_json_object(
                                surface.data_model.model_dump(mode="json"),
                                "FlowUIDataModel",
                            ),
                        },
                    ),
                ]
            )
        return messages

    def encode_effect_batch(
        self,
        before: FlowUIDocument,
        after: FlowUIDocument,
    ) -> list[JsonObject]:
        messages: list[JsonObject] = []
        for surface_id in before.surfaces:
            if surface_id not in after.surfaces:
                messages.append(_message("deleteSurface", {"surfaceId": surface_id}))
        for surface_id, surface in after.surfaces.items():
            old = before.surfaces.get(surface_id)
            if old is None:
                snapshot = after.model_copy(
                    update={"surfaces": {surface_id: surface}},
                    deep=True,
                )
                messages.extend(self.encode_document_snapshot(snapshot))
                continue
            if (
                old.catalog_id != surface.catalog_id
                or old.send_data_model != surface.send_data_model
                or old.components.keys() - surface.components.keys()
            ):
                messages.append(_message("deleteSurface", {"surfaceId": surface_id}))
                snapshot = after.model_copy(
                    update={"surfaces": {surface_id: surface}},
                    deep=True,
                )
                messages.extend(self.encode_document_snapshot(snapshot))
                continue
            changed_components = [
                component
                for component_id, component in surface.components.items()
                if old.components.get(component_id) != component
            ]
            if changed_components:
                messages.append(
                    _message(
                        "updateComponents",
                        {
                            "surfaceId": surface_id,
                            "components": [
                                _encode_component(component)
                                for component in changed_components
                            ],
                        },
                    )
                )
            old_data = require_json_object(
                old.data_model.model_dump(mode="json"), "FlowUIDataModel"
            )
            new_data = require_json_object(
                surface.data_model.model_dump(mode="json"), "FlowUIDataModel"
            )
            for path, value, has_value in _diff_data_model(old_data, new_data):
                payload: JsonObject = {"surfaceId": surface_id, "path": path}
                if has_value:
                    payload["value"] = value
                messages.append(_message("updateDataModel", payload))
        return messages

    def encode_data_part(self, messages: Sequence[JsonObject]) -> Part:
        if not messages:
            raise ValueError("A2UI data Part requires at least one message")
        validated: list[JsonObject] = []
        for message in messages:
            _ = _validate_envelope(message)
            validated.append(deepcopy(message))
        return Part(
            data=value_from_json(validated),
            media_type=A2UI_MIME_TYPE,
            metadata=struct_from_mapping({"mimeType": A2UI_MIME_TYPE}),
        )

    def decode_data_part(self, part: Part) -> list[JsonObject]:
        if not part_has_data(part):
            raise ValueError("A2UI payload must use an A2A data Part")
        metadata = mapping_from_struct(part.metadata)
        declared_types = [
            value
            for value in (part.media_type, metadata.get("mimeType"))
            if isinstance(value, str) and value
        ]
        if not declared_types or not all(is_a2ui_media_type(value) for value in declared_types):
            raise ValueError("A2UI data Part has a missing or conflicting MIME type")
        value = get_part_data(part)
        if not isinstance(value, list) or not value:
            raise ValueError("A2UI A2A data payload must be a non-empty message list")
        messages: list[JsonObject] = []
        for index, item in enumerate(value):
            message = require_json_object(item, f"A2UI messages[{index}]")
            _ = _validate_envelope(message)
            messages.append(deepcopy(message))
        return messages

    def apply_agent_message_batch(
        self,
        document: FlowUIDocument,
        messages: Sequence[JsonObject],
    ) -> A2UIBatchApplyResult:
        wire_surfaces = {
            surface_id: _surface_to_wire(surface)
            for surface_id, surface in document.surfaces.items()
        }
        errors: list[A2UIBatchApplyError] = []
        applied = 0
        for index, message in enumerate(messages):
            before_message = deepcopy(wire_surfaces)
            try:
                kind, payload = _validate_envelope(message, server_only=True)
                self._apply_server_message(wire_surfaces, kind=kind, payload=payload)
            except (TypeError, ValueError) as exc:
                wire_surfaces = before_message
                errors.append(
                    A2UIBatchApplyError(
                        message_index=index,
                        code="INVALID_A2UI_MESSAGE",
                        message=str(exc),
                    )
                )
            else:
                applied += 1

        updated = document.model_copy(deep=True)
        decoded_surfaces: dict[str, FlowUISurface] = {}
        for surface_id, wire in wire_surfaces.items():
            try:
                decoded = _wire_to_surface(surface_id, wire)
            except (TypeError, ValueError) as exc:
                existing = document.surfaces.get(surface_id)
                if existing is not None:
                    decoded_surfaces[surface_id] = existing.model_copy(deep=True)
                errors.append(
                    A2UIBatchApplyError(
                        message_index=max(0, len(messages) - 1),
                        code="INVALID_A2UI_SURFACE",
                        message=str(exc),
                    )
                )
            else:
                decoded_surfaces[surface_id] = decoded
        updated.surfaces = decoded_surfaces
        if applied:
            updated.revision += 1
        try:
            validated = FlowUIDocument.model_validate(updated.model_dump(mode="python"))
        except ValueError as exc:
            errors.append(
                A2UIBatchApplyError(
                    message_index=max(0, len(messages) - 1),
                    code="INVALID_FLOW_UI_DOCUMENT",
                    message=str(exc),
                )
            )
            validated = document.model_copy(deep=True)
            applied = 0
        return A2UIBatchApplyResult(
            document=validated,
            applied_message_count=applied,
            errors=errors,
        )

    def _apply_server_message(
        self,
        surfaces: dict[str, _WireSurface],
        *,
        kind: str,
        payload: JsonObject,
    ) -> None:
        if kind == "createSurface":
            if set(payload) - {"surfaceId", "catalogId", "theme", "sendDataModel"}:
                raise ValueError("createSurface contains unknown fields")
            surface_id = payload.get("surfaceId")
            catalog_id = payload.get("catalogId")
            if not isinstance(surface_id, str) or not surface_id:
                raise ValueError("createSurface requires surfaceId")
            if not isinstance(catalog_id, str) or not catalog_id:
                raise ValueError("createSurface requires catalogId")
            if surface_id in surfaces:
                raise ValueError(f"A2UI surface already exists: {surface_id!r}")
            send_data_model = payload.get("sendDataModel", False)
            if not isinstance(send_data_model, bool):
                raise ValueError("createSurface.sendDataModel must be boolean")
            surfaces[surface_id] = _WireSurface(
                catalog_id=catalog_id,
                send_data_model=send_data_model,
                components={},
                data_model={"content": {}, "values": {}, "system": {}},
            )
            return

        surface_id = payload.get("surfaceId")
        if not isinstance(surface_id, str) or not surface_id:
            raise ValueError(f"{kind} requires surfaceId")
        if kind == "deleteSurface":
            if set(payload) != {"surfaceId"}:
                raise ValueError("deleteSurface contains unknown fields")
            _ = surfaces.pop(surface_id, None)
            return
        if surface_id not in surfaces:
            raise ValueError(f"A2UI surface does not exist: {surface_id!r}")
        surface = surfaces[surface_id]
        if kind == "updateComponents":
            if set(payload) != {"surfaceId", "components"}:
                raise ValueError("updateComponents contains unknown fields")
            components = payload.get("components")
            if not isinstance(components, list) or not components:
                raise ValueError("updateComponents.components must be non-empty")
            seen: set[str] = set()
            for item in components:
                component = require_json_object(item, "updateComponents.components[]")
                component_id = component.get("id")
                component_type = component.get("component")
                if not isinstance(component_id, str) or not component_id:
                    raise ValueError("A2UI component requires id")
                if not isinstance(component_type, str) or not component_type:
                    raise ValueError("A2UI component requires component")
                if component_id in seen:
                    raise ValueError(f"duplicate component id in update: {component_id!r}")
                seen.add(component_id)
                surface.components[component_id] = deepcopy(component)
            return
        if kind != "updateDataModel":
            raise ValueError(f"Unsupported server A2UI message: {kind!r}")
        if set(payload) - {"surfaceId", "path", "value"}:
            raise ValueError("updateDataModel contains unknown fields")
        path = payload.get("path", "/")
        if not isinstance(path, str):
            raise ValueError("updateDataModel.path must be a JSON Pointer")
        current: JsonValue = deepcopy(surface.data_model)
        if "value" in payload:
            current = set_json_pointer(
                current,
                "" if path == "/" else path,
                require_json_value(payload["value"], "updateDataModel.value"),
            )
        elif path == "/":
            current = {}
        else:
            current = delete_json_pointer(current, path)
        surface.data_model = require_json_object(current, "A2UI surface data model")


__all__ = ["A2UI091Codec"]
