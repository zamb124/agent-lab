"""Flow UI submit contract: what a flow actually receives from a screen.

One server-side projector builds both channels of a submit, so the editor
preview, the durable state and the LLM prompt can never disagree:

* ``values`` — flat ``{field: value}`` map addressed by the flow as
  ``@state:ui_values.<field>``;
* ``content`` — deterministic Markdown of the interaction, written into
  ``state.content`` (the default input of an ``llm_node``).

Markdown mode is authored, not guessed:

* page-level ``PageShell.properties.contentMode``
  — ``auto`` (default), ``values``, ``page``, ``message``;
* component-level ``properties.markdownMode`` — ``auto``, ``always``,
  ``exclude``; ``properties.markdownLabel`` overrides the printed label;
* ``properties.fieldName`` overrides the flat field key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from core.files.file_ref import FileRef, format_a2a_files_content
from core.state.flow_ui import FlowUIComponent, FlowUIDocument, FlowUISurface
from core.types import JsonObject, JsonValue

FlowUIContentMode = Literal["auto", "values", "page", "message"]
FlowUIMarkdownMode = Literal["auto", "always", "exclude"]

CONTENT_MODES: frozenset[str] = frozenset(get_args(FlowUIContentMode))
MARKDOWN_MODES: frozenset[str] = frozenset(get_args(FlowUIMarkdownMode))

VALUES_POINTER_PREFIX = "/values"

# Components whose static copy is page content (rendered in `page` mode).
_STATIC_TEXT_TYPES: frozenset[str] = frozenset(
    {"Heading", "Text", "Markdown", "CodeBlock", "Alert", "EmptyState", "Badge", "Status"}
)
_HEADING_TYPES: frozenset[str] = frozenset({"Heading"})
_CODE_TYPES: frozenset[str] = frozenset({"CodeBlock"})


@dataclass(frozen=True)
class FlowUIContractField:
    """One user-editable value the flow receives."""

    field: str
    pointer: str
    component_id: str
    component_type: str
    label: str
    value: JsonValue
    included_in_content: bool


@dataclass(frozen=True)
class FlowUISubmitContract:
    surface_id: str
    content_mode: FlowUIContentMode
    fields: tuple[FlowUIContractField, ...]
    values: JsonObject
    content: str


def _localized(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        default = value.get("default")
        if isinstance(default, str):
            return default
    return ""


def _unescape_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def _pointer_get(values: JsonObject, pointer: str) -> JsonValue | None:
    """Read a ``/values/...`` pointer out of the submitted values object."""
    if pointer == VALUES_POINTER_PREFIX:
        return values
    if not pointer.startswith(f"{VALUES_POINTER_PREFIX}/"):
        return None
    current: JsonValue = values
    for raw_segment in pointer[len(VALUES_POINTER_PREFIX) + 1 :].split("/"):
        segment = _unescape_pointer_segment(raw_segment)
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def _component_property(component: FlowUIComponent, name: str) -> JsonValue | None:
    value = component.properties.get(name)
    return None if value is None else value


def _content_mode(surface: FlowUISurface) -> FlowUIContentMode:
    root = surface.components.get(surface.root_component_id)
    raw = None if root is None else _component_property(root, "contentMode")
    if raw is None:
        return "auto"
    if not isinstance(raw, str) or raw not in CONTENT_MODES:
        raise ValueError(f"Flow UI contentMode must be one of {sorted(CONTENT_MODES)}: {raw!r}")
    return raw  # pyright: ignore[reportReturnType]


def _markdown_mode(component: FlowUIComponent) -> FlowUIMarkdownMode:
    raw = _component_property(component, "markdownMode")
    if raw is None:
        return "auto"
    if not isinstance(raw, str) or raw not in MARKDOWN_MODES:
        raise ValueError(
            f"Flow UI markdownMode must be one of {sorted(MARKDOWN_MODES)}: {raw!r}"
        )
    return raw  # pyright: ignore[reportReturnType]


def _component_label(component: FlowUIComponent, *, default_label: str) -> str:
    override = _component_property(component, "markdownLabel")
    if isinstance(override, str) and override.strip() != "":
        return override
    for name in ("label", "title", "text"):
        label = _localized(component.properties.get(name))
        if label.strip() != "":
            return label
    return default_label


def _value_binding_pointer(component: FlowUIComponent) -> str | None:
    """Pointer of the user-editable value this component writes, if any."""
    for binding_name in ("value", "values", "files"):
        pointer = component.bindings.get(binding_name)
        if isinstance(pointer, str) and pointer.startswith(VALUES_POINTER_PREFIX):
            return pointer
    return None


def _ordered_components(surface: FlowUISurface) -> list[FlowUIComponent]:
    """Document order walk from the surface root; cycles cannot repeat a node."""
    ordered: list[FlowUIComponent] = []
    seen: set[str] = set()

    def visit(component_id: str) -> None:
        if component_id in seen:
            return
        seen.add(component_id)
        component = surface.components.get(component_id)
        if component is None:
            return
        ordered.append(component)
        for child_id in component.children:
            visit(child_id)

    visit(surface.root_component_id)
    return ordered


_INPUT_TYPES: frozenset[str] = frozenset(
    {
        "TextField",
        "TextArea",
        "NumberField",
        "Select",
        "ChoicePicker",
        "CheckBox",
        "Switch",
        "Slider",
        "DateTimeInput",
        "DatePicker",
        "FileUpload",
    }
)


def _field_owners(ordered: list[FlowUIComponent]) -> list[FlowUIComponent]:
    """One field per ``/values`` pointer.

    Helper components may write the same pointer (SuggestedPrompts fills the
    composer input); the editable input owns the field, so the flow never sees
    the same user value twice under two keys.
    """
    owner_by_pointer: dict[str, FlowUIComponent] = {}
    order: list[str] = []
    for component in ordered:
        pointer = _value_binding_pointer(component)
        if pointer is None:
            continue
        current = owner_by_pointer.get(pointer)
        if current is None:
            owner_by_pointer[pointer] = component
            order.append(pointer)
            continue
        if current.type not in _INPUT_TYPES and component.type in _INPUT_TYPES:
            owner_by_pointer[pointer] = component
    return [owner_by_pointer[pointer] for pointer in order]


def _field_key(component: FlowUIComponent, pointer: str, taken: set[str]) -> str:
    override = _component_property(component, "fieldName")
    if isinstance(override, str) and override.strip() != "":
        candidate = override.strip()
    else:
        candidate = _unescape_pointer_segment(pointer.rsplit("/", 1)[-1])
    if candidate == "" or candidate in taken:
        # Collisions keep the full pointer so two screens never silently merge.
        candidate = pointer[len(VALUES_POINTER_PREFIX) + 1 :].replace("/", "_") or "value"
    while candidate in taken:
        candidate = f"{candidate}_{component.component_id}"
    return candidate


def _is_empty(value: JsonValue | None) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _file_refs_from_value(value: JsonValue) -> list[FileRef]:
    if not isinstance(value, list):
        return []
    refs: list[FileRef] = []
    for item in value:
        refs.append(FileRef.model_validate(item))
    return refs


def _render_value_markdown(component: FlowUIComponent, value: JsonValue) -> str:
    """Markdown fragment for one submitted value (without its label)."""
    if component.type == "FileUpload":
        return format_a2a_files_content(_file_refs_from_value(value)).strip()
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if component.type in _CODE_TYPES:
            return f"```\n{value}\n```"
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, (str, int, float, bool)):
                parts.append(f"- {item}")
            elif isinstance(item, dict):
                inline = ", ".join(f"{key}: {item[key]}" for key in sorted(item))
                parts.append(f"- {inline}")
        return "\n".join(parts)
    if isinstance(value, dict):
        return "\n".join(f"- **{key}:** {value[key]}" for key in sorted(value))
    return ""


def _render_static_markdown(component: FlowUIComponent) -> str:
    """Markdown fragment for authored copy (page mode)."""
    if component.type in _HEADING_TYPES:
        level_raw = component.properties.get("level")
        level = level_raw if isinstance(level_raw, int) and 1 <= level_raw <= 6 else 2
        text = _localized(component.properties.get("text")) or _localized(
            component.properties.get("title")
        )
        return "" if text.strip() == "" else f"{'#' * level} {text}"
    if component.type in _CODE_TYPES:
        code = _localized(component.properties.get("code"))
        return "" if code.strip() == "" else f"```\n{code}\n```"
    for name in ("text", "content", "message", "label"):
        text = _localized(component.properties.get(name))
        if text.strip() != "":
            return text
    return ""


def _multiline(text: str) -> bool:
    return "\n" in text.strip()


def _labeled_fragment(label: str, rendered: str) -> str:
    block = _multiline(rendered) or rendered.startswith("```") or rendered.startswith("- ")
    if block:
        return f"**{label}:**\n{rendered}"
    return f"**{label}:** {rendered}"


def build_flow_ui_submit_contract(
    document: FlowUIDocument,
    *,
    surface_id: str,
    values: JsonObject,
) -> FlowUISubmitContract:
    """Project one accepted submit into the flat values and Markdown a flow sees."""
    surface = document.surfaces.get(surface_id)
    if surface is None:
        raise ValueError(f"Unknown Flow UI surface: {surface_id!r}")

    mode = _content_mode(surface)
    ordered = _ordered_components(surface)

    fields: list[FlowUIContractField] = []
    flat_values: JsonObject = {}
    taken: set[str] = set()

    for component in _field_owners(ordered):
        pointer = _value_binding_pointer(component)
        if pointer is None:
            continue
        markdown_mode = _markdown_mode(component)
        value = _pointer_get(values, pointer)
        key = _field_key(component, pointer, taken)
        taken.add(key)
        flat_values[key] = value
        fields.append(
            FlowUIContractField(
                field=key,
                pointer=pointer,
                component_id=component.component_id,
                component_type=component.type,
                label=_component_label(component, default_label=key),
                value=value,
                included_in_content=markdown_mode != "exclude" and not _is_empty(value),
            )
        )

    content = _render_content(
        mode=mode,
        ordered=ordered,
        fields=fields,
        document=document,
        surface=surface,
    )
    return FlowUISubmitContract(
        surface_id=surface_id,
        content_mode=mode,
        fields=tuple(fields),
        values=flat_values,
        content=content,
    )


def _is_attachment(field: FlowUIContractField) -> bool:
    return field.component_type == "FileUpload"


def _single_free_text(fields: list[FlowUIContractField]) -> FlowUIContractField | None:
    """A chat composer submit: exactly one filled free-text field (files aside)."""
    filled = [
        field for field in fields if field.included_in_content and not _is_attachment(field)
    ]
    if len(filled) != 1:
        return None
    field = filled[0]
    if field.component_type not in {"TextArea", "TextField"}:
        return None
    return field if isinstance(field.value, str) else None


def _attachments_markdown(fields: list[FlowUIContractField]) -> str:
    """Message-mode appendix: raw [FILE] blocks, no **files:** label."""
    refs: list[FileRef] = []
    for field in fields:
        if not field.included_in_content or not _is_attachment(field):
            continue
        refs.extend(_file_refs_from_value(field.value if field.value is not None else []))
    return format_a2a_files_content(refs).strip()


def flow_ui_submit_file_refs(contract: FlowUISubmitContract) -> list[FileRef]:
    """FileUpload values from one submit as canonical FileRef list for state.files."""
    refs: list[FileRef] = []
    for field in contract.fields:
        if field.component_type != "FileUpload":
            continue
        refs.extend(_file_refs_from_value(field.value if field.value is not None else []))
    return refs


def _render_content(
    *,
    mode: FlowUIContentMode,
    ordered: list[FlowUIComponent],
    fields: list[FlowUIContractField],
    document: FlowUIDocument,
    surface: FlowUISurface,
) -> str:
    if mode == "message":
        return _render_message_markdown(fields)

    if mode == "page":
        return _render_page_markdown(
            ordered=ordered,
            fields=fields,
            document=document,
            surface=surface,
        )

    if mode == "values":
        return _render_values_markdown(fields)

    # auto: a lone free-text field stays verbatim (chat), everything else is a
    # labeled field list, so an llm_node always gets readable content.
    return _render_message_markdown(fields)


def _render_message_markdown(fields: list[FlowUIContractField]) -> str:
    field = _single_free_text(fields)
    attachments = _attachments_markdown(fields)
    if field is not None and isinstance(field.value, str):
        text = field.value.strip()
        if attachments == "":
            return text
        if text == "":
            return attachments
        return f"{text}\n{attachments}"
    # File-only composer submit (empty/absent free text): keep [FILE] canon,
    # never fall through to labeled **files:** bullet/values rendering.
    if attachments != "":
        non_attachment = [
            item
            for item in fields
            if item.included_in_content
            and not _is_attachment(item)
            and not _is_empty(item.value)
        ]
        if not non_attachment:
            return attachments
    return _render_values_markdown(fields)


def _render_values_markdown(fields: list[FlowUIContractField]) -> str:
    blocks: list[str] = []
    for field in fields:
        if not field.included_in_content:
            continue
        rendered = _render_value_markdown(
            FlowUIComponent(
                component_id=field.component_id,
                type=field.component_type,
            ),
            field.value if field.value is not None else "",
        )
        if rendered.strip() == "":
            continue
        blocks.append(_labeled_fragment(field.label, rendered))
    return "\n\n".join(blocks)


def _render_page_markdown(
    *,
    ordered: list[FlowUIComponent],
    fields: list[FlowUIContractField],
    document: FlowUIDocument,
    surface: FlowUISurface,
) -> str:
    fields_by_component = {field.component_id: field for field in fields}
    blocks: list[str] = []
    # The page title only leads when the screen has no H1 of its own.
    has_top_heading = any(
        component.type in _HEADING_TYPES and component.properties.get("level") == 1
        for component in ordered
    )
    page_title = ""
    for page in document.pages.values():
        if page.root_surface_id == surface.surface_id:
            page_title = page.title.default
            break
    if page_title.strip() != "" and not has_top_heading:
        blocks.append(f"# {page_title}")

    for component in ordered:
        markdown_mode = _markdown_mode(component)
        if markdown_mode == "exclude":
            continue
        field = fields_by_component.get(component.component_id)
        if field is not None:
            if not field.included_in_content:
                continue
            rendered = _render_value_markdown(
                component,
                field.value if field.value is not None else "",
            )
            if rendered.strip() == "":
                continue
            blocks.append(_labeled_fragment(field.label, rendered))
            continue
        if component.type not in _STATIC_TEXT_TYPES and markdown_mode != "always":
            continue
        rendered = _render_static_markdown(component)
        if rendered.strip() != "":
            blocks.append(rendered)
    return "\n\n".join(blocks)


def iter_flow_ui_submit_contract_fields(
    document: FlowUIDocument,
) -> tuple[FlowUIContractField, ...]:
    """Design-time field list across all surfaces (same projector as runtime submit)."""
    taken: set[str] = set()
    fields: list[FlowUIContractField] = []
    for surface_id in sorted(document.surfaces):
        surface = document.surfaces[surface_id]
        contract = build_flow_ui_submit_contract(
            document,
            surface_id=surface_id,
            values=dict(surface.data_model.values),
        )
        for field in contract.fields:
            if field.field in taken:
                continue
            taken.add(field.field)
            fields.append(field)
    return tuple(fields)


__all__ = [
    "CONTENT_MODES",
    "MARKDOWN_MODES",
    "FlowUIContentMode",
    "FlowUIContractField",
    "FlowUIMarkdownMode",
    "FlowUISubmitContract",
    "build_flow_ui_submit_contract",
    "flow_ui_submit_file_refs",
    "iter_flow_ui_submit_contract_fields",
]
