"""Publish validator for Flow UI documents (plan §18.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from core.a2a.extensions import PLATFORM_UI_SUBMIT_ACTION
from core.state.flow_ui import FlowUIComponent, FlowUIDocument, FlowUISurface

INTERACTIVE_TYPES = frozenset(
    {
        "TextField",
        "TextArea",
        "NumberField",
        "Select",
        "ChoicePicker",
        "CheckBox",
        "Switch",
        "FileUpload",
        "DateTimeInput",
        "DatePicker",
        "Slider",
    }
)


@dataclass(frozen=True, slots=True)
class FlowUIPublishProblem:
    code: str
    message: str
    severity: str = "error"


class _SubmitActionRef(TypedDict):
    surface_id: str
    component_id: str
    reachable: bool
    disabled_forever: bool
    form_id: str | None


def _walk_reachable(
    surface: FlowUISurface,
    component_id: str,
    visited: set[str] | None = None,
) -> set[str]:
    seen: set[str] = visited if visited is not None else set()
    if not component_id or component_id in seen:
        return seen
    component = surface.components.get(component_id)
    if component is None:
        return seen
    seen.add(component_id)
    for child_id in component.children:
        _ = _walk_reachable(surface, child_id, seen)
    return seen


def _is_permanently_disabled(component: FlowUIComponent) -> bool:
    return component.properties.get("disabled") is True and "disabled" not in component.bindings


def validate_flow_ui_publish(document: FlowUIDocument) -> list[FlowUIPublishProblem]:
    """Return blocking publish problems for an interface document."""
    problems: list[FlowUIPublishProblem] = []
    if document.active_page_id not in document.pages:
        problems.append(
            FlowUIPublishProblem(
                code="page.active_missing",
                message="Active page does not exist.",
            )
        )

    submit_actions: list[_SubmitActionRef] = []
    for surface_id, surface in document.surfaces.items():
        root_id = surface.root_component_id
        if root_id not in surface.components:
            problems.append(
                FlowUIPublishProblem(
                    code="surface.root",
                    message=f"{surface_id}: root component missing",
                )
            )
        reachable = _walk_reachable(surface, root_id)
        for component_id, component in surface.components.items():
            for action in component.actions.values():
                if action.kind == "event" and action.name == PLATFORM_UI_SUBMIT_ACTION:
                    form_id: str | None = None
                    raw_form = action.context.get("formId")
                    if isinstance(raw_form, str):
                        form_id = raw_form
                    submit_actions.append(
                        {
                            "surface_id": surface_id,
                            "component_id": component_id,
                            "reachable": component_id in reachable,
                            "disabled_forever": _is_permanently_disabled(component),
                            "form_id": form_id,
                        }
                    )
            for binding_name, path in component.bindings.items():
                if not path.startswith("/"):
                    problems.append(
                        FlowUIPublishProblem(
                            code="binding.invalid",
                            message=f"{component_id}.{binding_name}: binding must be absolute JSON Pointer",
                        )
                    )
                    continue
                if path.startswith("/system/secrets"):
                    problems.append(
                        FlowUIPublishProblem(
                            code="binding.secret",
                            message=f"{component_id}.{binding_name}: secret binding forbidden",
                        )
                    )
                if (
                    any(action.kind == "event" for action in component.actions.values())
                    and not path.startswith(("/values", "/system/", "/content/"))
                ):
                    problems.append(
                        FlowUIPublishProblem(
                            code="binding.scope",
                            message=f"{component_id}.{binding_name}: interactive binding must stay under /values",
                        )
                    )

        interactive = [
            component
            for component in surface.components.values()
            if component.type in INTERACTIVE_TYPES and component.component_id in reachable
        ]
        if interactive and not any(
            item["surface_id"] == surface_id and item["reachable"] is True for item in submit_actions
        ):
            problems.append(
                FlowUIPublishProblem(
                    code="submit.form_unreachable",
                    message=f"{surface_id}: interactive form page has no reachable platform.ui.submit",
                )
            )

    if not submit_actions:
        problems.append(
            FlowUIPublishProblem(
                code="submit.missing",
                message="Add a reachable platform.ui.submit button before publishing.",
            )
        )
    elif not any(item["reachable"] is True for item in submit_actions):
        problems.append(
            FlowUIPublishProblem(
                code="submit.unreachable",
                message="platform.ui.submit exists only on unreachable components.",
            )
        )

    for item in submit_actions:
        if item["disabled_forever"] is True:
            problems.append(
                FlowUIPublishProblem(
                    code="submit.disabled_forever",
                    message=f"{item['surface_id']}:{item['component_id']}: submit button is permanently disabled",
                )
            )

    by_form: dict[str, list[_SubmitActionRef]] = {}
    for item in submit_actions:
        form_id = item["form_id"]
        if form_id is None or form_id == "":
            continue
        by_form.setdefault(form_id, []).append(item)
    for form_id, items in by_form.items():
        surfaces = {item["surface_id"] for item in items}
        if len(items) > 1 and len(surfaces) > 1:
            problems.append(
                FlowUIPublishProblem(
                    code="submit.form_conflict",
                    message=f"Duplicate platform.ui.submit actions share formId {form_id} across surfaces",
                )
            )

    return problems


def assert_flow_ui_publishable(document: FlowUIDocument) -> None:
    problems = validate_flow_ui_publish(document)
    if problems:
        raise ValueError("; ".join(f"{item.code}: {item.message}" for item in problems))
