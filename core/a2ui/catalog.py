"""Trusted Linnex A2UI platform catalog shared by runtime and editor."""

from __future__ import annotations

import json
from hashlib import sha256

from pydantic import Field, model_validator

from core.a2a.extensions import A2UI_PLATFORM_CATALOG_ID, A2UI_VERSION
from core.models.base import StrictBaseModel
from core.types import JsonObject, require_json_object


class FlowUICatalogComponent(StrictBaseModel):
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    kind: str
    accepts_children: bool = False
    properties_schema: JsonObject = Field(default_factory=dict)


class FlowUICatalogFunction(StrictBaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    parameters_schema: JsonObject
    return_type: str


class FlowUICatalogManifest(StrictBaseModel):
    schema_version: int = 1
    catalog_id: str
    catalog_version: str
    a2ui_version: str
    components: dict[str, FlowUICatalogComponent]
    functions: dict[str, FlowUICatalogFunction]
    layout_bands: dict[str, int]
    reserved_component_fields: list[str]
    checksum: str | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> FlowUICatalogManifest:
        if self.catalog_id != A2UI_PLATFORM_CATALOG_ID:
            raise ValueError("platform manifest must use the canonical Linnex catalog ID")
        for name, component in self.components.items():
            if name != component.name:
                raise ValueError("catalog component map key must match component name")
        for name, function in self.functions.items():
            if name != function.name:
                raise ValueError("catalog function map key must match function name")
        if self.layout_bands != {"compact": 4, "medium": 8, "wide": 12}:
            raise ValueError("platform catalog layout bands are fixed to 4/8/12")
        return self

    def public_payload(self) -> JsonObject:
        payload = require_json_object(
            self.model_dump(mode="json", exclude={"checksum"}),
            "FlowUICatalogManifest",
        )
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload["checksum"] = f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"
        return payload


def _component(
    name: str,
    category: str,
    description: str,
    *,
    kind: str = "leaf",
    accepts_children: bool = False,
) -> FlowUICatalogComponent:
    return FlowUICatalogComponent(
        name=name,
        category=category,
        description=description,
        kind=kind,
        accepts_children=accepts_children,
        properties_schema={"type": "object", "additionalProperties": True},
    )


_COMPONENTS = [
    _component("PageShell", "layout", "Responsive page frame", kind="container", accepts_children=True),
    _component("Section", "layout", "Semantic page section", kind="container", accepts_children=True),
    _component("Grid", "layout", "Responsive 4/8/12-column grid", kind="container", accepts_children=True),
    _component("Stack", "layout", "Vertical or horizontal stack", kind="container", accepts_children=True),
    _component("Row", "layout", "Wrapping horizontal row", kind="container", accepts_children=True),
    _component("Column", "layout", "Vertical content column", kind="container", accepts_children=True),
    _component("Card", "content", "Elevated content group", kind="container", accepts_children=True),
    _component("Form", "input", "Validated form container", kind="container", accepts_children=True),
    _component("Tabs", "navigation", "Tabbed content container", kind="container", accepts_children=True),
    _component("Text", "content", "Plain text"),
    _component("Heading", "content", "Semantic heading"),
    _component("Markdown", "content", "Safe rendered Markdown"),
    _component("Image", "media", "Responsive image"),
    _component("Link", "action", "Safe hyperlink"),
    _component("Button", "action", "Action button"),
    _component("TextField", "input", "Single-line text input"),
    _component("TextArea", "input", "Multi-line text input"),
    _component("NumberField", "input", "Numeric input"),
    _component("Select", "input", "Single-value select"),
    _component("ChoicePicker", "input", "Single or multiple choice picker"),
    _component("CheckBox", "input", "Boolean checkbox"),
    _component("Switch", "input", "Boolean switch"),
    _component("Slider", "input", "Numeric slider"),
    _component("DatePicker", "input", "Date input"),
    _component("FileUpload", "input", "A2A file attachment input"),
    _component("VoiceInput", "input", "Voice dictation or duplex session control"),
    _component("Divider", "content", "Visual separator"),
    _component("Table", "data", "Accessible data table"),
    _component("Chart", "data", "Declarative chart"),
    _component("AgentIdentity", "platform", "Flow agent identity"),
    _component("TaskControls", "platform", "Current A2A Task controls"),
    _component("ConversationFeed", "platform", "Conversation presentation", kind="container", accepts_children=True),
    _component(
        "ArtifactFeed",
        "platform",
        "Lossless ordinary A2A Artifact feed",
        kind="container",
        accepts_children=True,
    ),
    _component("EmptyState", "platform", "Empty and greeting state"),
    _component("SuggestedPrompts", "platform", "Suggested flow intents"),
    _component("FileCollection", "platform", "Created or updated files"),
    _component("SkillActivity", "platform", "Loaded agent skill"),
    _component("ReflectionResult", "platform", "Reflection gate result"),
    _component("ActionPreview", "platform", "Pending trusted action preview"),
    _component("ActionResult", "platform", "Applied trusted action result"),
    _component("BrowserPreview", "platform", "Safe browser preview"),
    _component("ActivityCard", "platform", "Structured platform activity"),
    _component("JsonInspector", "platform", "Safe structured data inspector"),
    _component("ErrorBoundary", "platform", "Isolated invalid component boundary"),
]

_FUNCTIONS = [
    FlowUICatalogFunction(
        name=name,
        description=f"Trusted client-side {name} function",
        parameters_schema={"type": "object"},
        return_type="boolean",
    )
    for name in ("required", "email", "regex", "minLength", "maxLength")
]

LINNEX_PLATFORM_CATALOG = FlowUICatalogManifest(
    catalog_id=A2UI_PLATFORM_CATALOG_ID,
    catalog_version="1.0.0",
    a2ui_version=A2UI_VERSION,
    components={item.name: item for item in _COMPONENTS},
    functions={item.name: item for item in _FUNCTIONS},
    layout_bands={"compact": 4, "medium": 8, "wide": 12},
    reserved_component_fields=[
        "id",
        "component",
        "children",
        "kind",
        "layout",
        "placement",
        "action",
        "actionSlot",
        "bindings",
        "actions",
        "visibility",
        "checks",
        "provenance",
    ],
)


def get_linnex_platform_catalog() -> JsonObject:
    return LINNEX_PLATFORM_CATALOG.public_payload()


__all__ = [
    "FlowUICatalogComponent",
    "FlowUICatalogFunction",
    "FlowUICatalogManifest",
    "LINNEX_PLATFORM_CATALOG",
    "get_linnex_platform_catalog",
]
