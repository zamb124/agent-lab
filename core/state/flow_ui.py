"""Version-neutral, trusted and fully materialized Flow UI domain."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from core.a2a.extensions import A2UI_PLATFORM_CATALOG_ID, PLATFORM_UI_SUBMIT_ACTION
from core.models.base import StrictBaseModel
from core.types import JsonObject, JsonValue

FlowUIContainerBand = Literal["compact", "medium", "wide"]
FlowUIComponentKind = Literal["container", "leaf", "overlay"]
FlowUIOwner = Literal["agent", "platform"]
FlowUIAlign = Literal["auto", "start", "center", "end", "stretch"]
FlowUIPlacementStart = int | Literal["auto"]
FlowUIPlacementSpan = int | Literal["full"]


class LocalizedText(StrictBaseModel):
    default: str = ""
    translations: dict[str, str] = Field(default_factory=dict)


class FlowUIDataModel(StrictBaseModel):
    content: JsonObject = Field(default_factory=dict)
    values: JsonObject = Field(default_factory=dict)
    system: JsonObject = Field(default_factory=dict)


class FlowInterfacePolicySnapshot(StrictBaseModel):
    show_reasoning: bool = False
    tool_calls_display: Literal["hidden", "compact", "detailed"] = "compact"
    show_activity: bool = True
    show_skill_loads: bool = True
    show_reflection: bool = True
    errors_display: Literal["generic", "detailed"] = "generic"
    show_run_trace: bool = False
    show_trace_actions: bool = False
    show_browser_previews: bool = True
    show_files_panel: bool = True
    allow_cancel: bool = True
    allow_voice: bool = True
    embed_safe_mode: bool = False
    allowed_catalog_ids: list[str] = Field(
        default_factory=lambda: [A2UI_PLATFORM_CATALOG_ID]
    )
    allowed_actions: list[str] = Field(
        default_factory=lambda: [PLATFORM_UI_SUBMIT_ACTION]
    )
    allowed_functions: list[str] = Field(
        default_factory=lambda: ["required", "email", "regex", "minLength", "maxLength"]
    )
    max_pages: int = Field(default=24, ge=1, le=100)
    max_surfaces: int = Field(default=48, ge=1, le=200)
    max_components_per_surface: int = Field(default=500, ge=1, le=5000)
    max_patch_bytes: int = Field(default=1_000_000, ge=1024, le=10_000_000)


class PageNavigationPolicy(StrictBaseModel):
    visible: bool = True
    allow_back: bool = True
    allow_direct: bool = True


class FlowUIGridDefinition(StrictBaseModel):
    columns_by_band: dict[FlowUIContainerBand, int] = Field(
        default_factory=lambda: {"compact": 4, "medium": 8, "wide": 12}
    )
    column_gap_token: str = "space.4"
    row_gap_token: str = "space.4"
    outer_padding_inline_token: str = "space.4"
    outer_padding_block_token: str = "space.4"
    max_content_width_token: str | None = "content.wide"
    auto_rows: Literal["content", "equal"] = "content"
    auto_flow: Literal["row", "column"] = "row"
    align_items: Literal["start", "center", "end", "stretch"] = "stretch"
    justify_items: Literal["start", "center", "end", "stretch"] = "stretch"
    baseline_step_token: str = "space.1"

    @model_validator(mode="after")
    def validate_bands(self) -> FlowUIGridDefinition:
        if set(self.columns_by_band) != {"compact", "medium", "wide"}:
            raise ValueError("grid columns_by_band must define compact, medium and wide")
        for band, columns in self.columns_by_band.items():
            if columns < 1 or columns > 24:
                raise ValueError(f"grid columns for {band} must be between 1 and 24")
        return self


class FlowUIStackDefinition(StrictBaseModel):
    direction: Literal["vertical", "horizontal"] = "vertical"
    gap_token: str = "space.4"
    align: Literal["start", "center", "end", "stretch"] = "stretch"


class FlowUIFlexDefinition(StrictBaseModel):
    direction: Literal["row", "column"] = "row"
    wrap: bool = True
    gap_token: str = "space.4"
    align_items: Literal["start", "center", "end", "stretch"] = "stretch"
    justify_content: Literal[
        "start", "center", "end", "space-between", "space-around"
    ] = "start"


class FlowUIContainerLayout(StrictBaseModel):
    mode: Literal["grid", "stack", "flex"]
    grid: FlowUIGridDefinition | None = None
    stack: FlowUIStackDefinition | None = None
    flex: FlowUIFlexDefinition | None = None

    @model_validator(mode="after")
    def validate_mode_payload(self) -> FlowUIContainerLayout:
        payloads = {"grid": self.grid, "stack": self.stack, "flex": self.flex}
        if payloads[self.mode] is None:
            raise ValueError(f"container layout mode {self.mode!r} requires its definition")
        if any(value is not None for key, value in payloads.items() if key != self.mode):
            raise ValueError("container layout may contain only the selected mode definition")
        return self


class FlowUIPlacement(StrictBaseModel):
    column_start: FlowUIPlacementStart = "auto"
    column_span: FlowUIPlacementSpan = "full"
    row_start: FlowUIPlacementStart = "auto"
    row_span: int = Field(default=1, ge=1, le=100)
    order: int = Field(default=0, ge=-1000, le=1000)
    align_self: FlowUIAlign = "auto"
    justify_self: FlowUIAlign = "auto"
    min_inline_size_token: str | None = None
    max_inline_size_token: str | None = None
    # Editor row resize: clamp max-block to row_span * baseline (not CSS grid-row span).
    block_clamp: bool = False

    @model_validator(mode="after")
    def validate_positive_starts(self) -> FlowUIPlacement:
        if isinstance(self.column_start, int) and self.column_start < 1:
            raise ValueError("column_start must be auto or a positive integer")
        if isinstance(self.row_start, int) and self.row_start < 1:
            raise ValueError("row_start must be auto or a positive integer")
        if isinstance(self.column_span, int) and self.column_span < 1:
            raise ValueError("column_span must be full or a positive integer")
        return self


class FlowUIPlacementPatch(StrictBaseModel):
    column_start: FlowUIPlacementStart | None = None
    column_span: FlowUIPlacementSpan | None = None
    row_start: FlowUIPlacementStart | None = None
    row_span: int | None = Field(default=None, ge=1, le=100)
    order: int | None = Field(default=None, ge=-1000, le=1000)
    align_self: FlowUIAlign | None = None
    justify_self: FlowUIAlign | None = None
    min_inline_size_token: str | None = None
    max_inline_size_token: str | None = None
    block_clamp: bool | None = None


class FlowUIResponsivePlacement(StrictBaseModel):
    base: FlowUIPlacement = Field(default_factory=FlowUIPlacement)
    overrides: dict[FlowUIContainerBand, FlowUIPlacementPatch] = Field(default_factory=dict)


class FlowUIAction(StrictBaseModel):
    kind: Literal["local", "event"] = "event"
    name: str = Field(min_length=1)
    context: JsonObject = Field(default_factory=dict)


class FlowUIProvenance(StrictBaseModel):
    task_id: str | None = None
    artifact_id: str | None = None
    part_index: int | None = Field(default=None, ge=0)
    agent_id: str | None = None


FlowUICheckFunction = Literal["required", "email", "regex", "minLength", "maxLength"]


class FlowUICheck(StrictBaseModel):
    """Authoritative field validation rule. Source of truth is checks[], not properties.required."""

    function: FlowUICheckFunction
    message: str = ""
    pattern: str | None = None
    value: int | None = None

    @model_validator(mode="after")
    def validate_check_payload(self) -> FlowUICheck:
        if self.function == "regex":
            if self.pattern is None or self.pattern == "":
                raise ValueError("regex check requires a non-empty pattern")
            if self.value is not None:
                raise ValueError("regex check must not set value")
            return self
        if self.function in {"minLength", "maxLength"}:
            if self.value is None:
                raise ValueError(f"{self.function} check requires value")
            if self.value < 0:
                raise ValueError(f"{self.function} check value must be >= 0")
            if self.pattern is not None:
                raise ValueError(f"{self.function} check must not set pattern")
            return self
        if self.pattern is not None or self.value is not None:
            raise ValueError(f"{self.function} check must not set pattern or value")
        return self


class FlowUIComponent(StrictBaseModel):
    component_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    kind: FlowUIComponentKind = "leaf"
    properties: JsonObject = Field(default_factory=dict)
    children: list[str] = Field(default_factory=list)
    container_layout: FlowUIContainerLayout | None = None
    placement: FlowUIResponsivePlacement = Field(default_factory=FlowUIResponsivePlacement)
    bindings: dict[str, str] = Field(default_factory=dict)
    actions: dict[str, FlowUIAction] = Field(default_factory=dict)
    visibility: JsonObject | None = None
    checks: list[FlowUICheck] = Field(default_factory=list)
    provenance: FlowUIProvenance | None = None

    @model_validator(mode="after")
    def validate_component_kind(self) -> FlowUIComponent:
        reserved = {
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
        }
        collisions = sorted(reserved.intersection(self.properties))
        if collisions:
            raise ValueError(f"component properties use reserved fields: {collisions!r}")
        if self.kind == "container" and self.container_layout is None:
            raise ValueError(f"container component {self.component_id!r} requires layout")
        if self.kind == "leaf" and self.children:
            raise ValueError(f"leaf component {self.component_id!r} cannot have children")
        for name, path in self.bindings.items():
            if not name or not path.startswith("/"):
                raise ValueError("component bindings must be named RFC 6901 pointers")
            if path.startswith("/system/secrets"):
                raise ValueError("bindings to system secrets are forbidden")
        return self


class FlowUISurface(StrictBaseModel):
    surface_id: str = Field(min_length=1)
    catalog_id: str = A2UI_PLATFORM_CATALOG_ID
    root_component_id: str = "root"
    components: dict[str, FlowUIComponent]
    data_model: FlowUIDataModel = Field(default_factory=FlowUIDataModel)
    owner: FlowUIOwner = "platform"
    send_data_model: bool = True

    @model_validator(mode="after")
    def validate_component_graph(self) -> FlowUISurface:
        if self.root_component_id != "root":
            raise ValueError("A2UI v0.9.1 surface root_component_id must be 'root'")
        if self.root_component_id not in self.components:
            raise ValueError(f"surface {self.surface_id!r} has no root component")
        for key, component in self.components.items():
            if key != component.component_id:
                raise ValueError("surface component map key must equal component_id")
            missing = [child for child in component.children if child not in self.components]
            if missing:
                raise ValueError(
                    f"component {component.component_id!r} references missing children {missing!r}"
                )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(component_id: str) -> None:
            if component_id in visiting:
                raise ValueError(f"component cycle detected at {component_id!r}")
            if component_id in visited:
                return
            visiting.add(component_id)
            for child_id in self.components[component_id].children:
                visit(child_id)
            visiting.remove(component_id)
            visited.add(component_id)

        visit(self.root_component_id)
        if visited != set(self.components):
            unreachable = sorted(set(self.components) - visited)
            raise ValueError(f"surface contains unreachable components: {unreachable!r}")
        self._validate_grid_placements()
        return self

    def _validate_grid_placements(self) -> None:
        for parent in self.components.values():
            layout = parent.container_layout
            if layout is None or layout.mode != "grid" or layout.grid is None:
                continue
            for child_id in parent.children:
                placement = self.components[child_id].placement
                by_band: dict[FlowUIContainerBand, FlowUIPlacementSpan] = {
                    "compact": placement.base.column_span,
                    "medium": placement.base.column_span,
                    "wide": placement.base.column_span,
                }
                for band, override in placement.overrides.items():
                    if override.column_span is not None:
                        by_band[band] = override.column_span
                for band, span in by_band.items():
                    columns = layout.grid.columns_by_band[band]
                    if isinstance(span, int) and span > columns:
                        raise ValueError(
                            f"component {child_id!r} span {span} exceeds {band} grid columns {columns}"
                        )
                resolved_start = placement.base.column_start
                resolved_span = placement.base.column_span
                for band_name, override in placement.overrides.items():
                    if band_name != "wide":
                        continue
                    if override.column_start is not None:
                        resolved_start = override.column_start
                    if override.column_span is not None:
                        resolved_span = override.column_span
                wide_columns = layout.grid.columns_by_band["wide"]
                if (
                    isinstance(resolved_start, int)
                    and isinstance(resolved_span, int)
                    and resolved_start + resolved_span - 1 > wide_columns
                ):
                    raise ValueError(
                        f"component {child_id!r} placement {resolved_start}+{resolved_span} exceeds wide grid columns {wide_columns}"
                    )


class FlowUIPage(StrictBaseModel):
    page_id: str = Field(min_length=1)
    title: LocalizedText = Field(default_factory=LocalizedText)
    route: str = Field(min_length=1, pattern=r"^/")
    root_surface_id: str = Field(min_length=1)
    navigation: PageNavigationPolicy = Field(default_factory=PageNavigationPolicy)
    default_target_profile_id: str = "runtime"


class FlowUIDocument(StrictBaseModel):
    schema_version: Literal[1] = 1
    document_id: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)
    template_version: str = Field(min_length=1)
    catalog_id: str = A2UI_PLATFORM_CATALOG_ID
    active_page_id: str = Field(min_length=1)
    session_view_state: JsonObject = Field(default_factory=dict)
    last_accepted_client_mutation_id: str | None = None
    pages: dict[str, FlowUIPage]
    surfaces: dict[str, FlowUISurface]
    global_data_model: FlowUIDataModel = Field(default_factory=FlowUIDataModel)
    policy: FlowInterfacePolicySnapshot = Field(default_factory=FlowInterfacePolicySnapshot)

    @model_validator(mode="after")
    def validate_document(self) -> FlowUIDocument:
        if len(self.pages) > self.policy.max_pages:
            raise ValueError("Flow UI page count exceeds policy")
        if len(self.surfaces) > self.policy.max_surfaces:
            raise ValueError("Flow UI surface count exceeds policy")
        if self.active_page_id not in self.pages:
            raise ValueError("active_page_id must reference an existing page")
        for key, page in self.pages.items():
            if key != page.page_id:
                raise ValueError("page map key must equal page_id")
            if page.root_surface_id not in self.surfaces:
                raise ValueError(f"page {page.page_id!r} references unknown surface")
        for key, surface in self.surfaces.items():
            if key != surface.surface_id:
                raise ValueError("surface map key must equal surface_id")
            if len(surface.components) > self.policy.max_components_per_surface:
                raise ValueError(f"surface {surface.surface_id!r} exceeds component policy")
            if surface.catalog_id not in self.policy.allowed_catalog_ids:
                raise ValueError(f"surface catalog {surface.catalog_id!r} is not allowed")
            for component in surface.components.values():
                for action in component.actions.values():
                    if action.kind == "event" and action.name not in self.policy.allowed_actions:
                        raise ValueError(
                            f"component event action {action.name!r} is not allowed by policy"
                        )
                for check in component.checks:
                    if check.function not in self.policy.allowed_functions:
                        raise ValueError(
                            f"component check function {check.function!r} is not allowed by policy"
                        )
        if not self._has_submit_action():
            raise ValueError("Flow UI document requires a platform.ui.submit action")
        return self

    def _has_submit_action(self) -> bool:
        return any(
            action.kind == "event" and action.name == PLATFORM_UI_SUBMIT_ACTION
            for surface in self.surfaces.values()
            for component in surface.components.values()
            for action in component.actions.values()
        )


class FlowUIInteraction(StrictBaseModel):
    interaction_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    base_revision: int = Field(ge=1)
    accepted_revision: int = Field(ge=1)
    action_name: Literal["platform.ui.submit"] = PLATFORM_UI_SUBMIT_ACTION
    surface_id: str = Field(min_length=1)
    source_component_id: str = Field(min_length=1)
    form_id: str | None = None
    page_id: str = Field(min_length=1)
    values_patch: JsonObject = Field(default_factory=dict)
    validated_values_snapshot: JsonObject = Field(default_factory=dict)
    original_message: JsonObject
    submitted_at: datetime


class FlowUIConflict(StrictBaseModel):
    document_id: str
    client_revision: int = Field(ge=1)
    server_revision: int = Field(ge=1)
    mutation_id: str | None = None
    reason: Literal["stale", "future", "duplicate-conflict"]


class FlowUIUpsertComponentsCommand(StrictBaseModel):
    kind: Literal["components.upsert"] = "components.upsert"
    surface_id: str
    components: list[FlowUIComponent]


class FlowUIDeleteComponentsCommand(StrictBaseModel):
    kind: Literal["components.delete"] = "components.delete"
    surface_id: str
    component_ids: list[str]


class FlowUISetDataCommand(StrictBaseModel):
    kind: Literal["data.set"] = "data.set"
    surface_id: str | None = None
    path: str = Field(pattern=r"^/")
    value: JsonValue


class FlowUIDeleteDataCommand(StrictBaseModel):
    kind: Literal["data.delete"] = "data.delete"
    surface_id: str | None = None
    path: str = Field(pattern=r"^/")


class FlowUINavigateCommand(StrictBaseModel):
    kind: Literal["navigate"] = "navigate"
    page_id: str


class FlowUIReplaceSurfaceCommand(StrictBaseModel):
    kind: Literal["surface.replace"] = "surface.replace"
    surface: FlowUISurface


class FlowUICreateSurfaceCommand(StrictBaseModel):
    kind: Literal["surface.create"] = "surface.create"
    surface: FlowUISurface


class FlowUIDeleteSurfaceCommand(StrictBaseModel):
    kind: Literal["surface.delete"] = "surface.delete"
    surface_id: str


FlowUICommand = Annotated[
    FlowUIUpsertComponentsCommand
    | FlowUIDeleteComponentsCommand
    | FlowUISetDataCommand
    | FlowUIDeleteDataCommand
    | FlowUINavigateCommand
    | FlowUICreateSurfaceCommand
    | FlowUIReplaceSurfaceCommand
    | FlowUIDeleteSurfaceCommand,
    Field(discriminator="kind"),
]


class FlowUISessionSnapshot(StrictBaseModel):
    flow_id: str
    branch_id: str
    context_id: str
    session_id: str
    document: FlowUIDocument
    active_task_id: str | None = None
    latest_task_id: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    viewer_permissions: list[Literal["view", "interact", "edit", "share"]]
    snapshot_sequence: int = Field(ge=0)
    state_hash: str
    generated_at: datetime


class FlowUITransition(StrictBaseModel):
    """Trusted, non-user-returnable side channel awaiting durable A2A projection."""

    transition_id: str = Field(min_length=1)
    before: FlowUIDocument
    after: FlowUIDocument
    source: str = Field(min_length=1)


__all__ = [
    "FlowUIAction",
    "FlowUICommand",
    "FlowUIComponent",
    "FlowUIConflict",
    "FlowUIContainerLayout",
    "FlowUICreateSurfaceCommand",
    "FlowUIDataModel",
    "FlowUIDeleteComponentsCommand",
    "FlowUIDeleteDataCommand",
    "FlowUIDeleteSurfaceCommand",
    "FlowUIDocument",
    "FlowUIFlexDefinition",
    "FlowUIGridDefinition",
    "FlowUIInteraction",
    "FlowUINavigateCommand",
    "FlowUIPage",
    "FlowUIPlacement",
    "FlowUIPlacementPatch",
    "FlowUIReplaceSurfaceCommand",
    "FlowUIResponsivePlacement",
    "FlowUISessionSnapshot",
    "FlowUISetDataCommand",
    "FlowUIStackDefinition",
    "FlowUISurface",
    "FlowUITransition",
    "FlowUIUpsertComponentsCommand",
    "FlowInterfacePolicySnapshot",
    "LocalizedText",
    "PageNavigationPolicy",
]
