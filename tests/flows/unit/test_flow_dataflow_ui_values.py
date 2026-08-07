"""Logic dataflow seeds ui_values.* from Flow UI submit contract."""

from __future__ import annotations

from core.a2a.extensions import A2UI_PLATFORM_CATALOG_ID, PLATFORM_UI_SUBMIT_ACTION
from core.models.flow_interface import (
    FlowInterfaceConfig,
    FlowInterfacePolicy,
    FlowUIDocumentTemplate,
)
from core.state.flow_ui import (
    FlowUIAction,
    FlowUIComponent,
    FlowUIContainerLayout,
    FlowUIDataModel,
    FlowUIDocument,
    FlowUIPage,
    FlowUIStackDefinition,
    FlowUISurface,
    LocalizedText,
)
from core.variables import VariableResolver
from tests.flows.fixtures.dataflow_graphs import inspect


def _lead_form_interface() -> FlowInterfaceConfig:
    policy = FlowInterfacePolicy()
    components = {
        "root": FlowUIComponent(
            component_id="root",
            type="PageShell",
            kind="container",
            children=["form"],
            container_layout=FlowUIContainerLayout(
                mode="stack",
                stack=FlowUIStackDefinition(gap_token="space.4"),
            ),
            properties={"presentation": "page", "contentMode": "values"},
        ),
        "form": FlowUIComponent(
            component_id="form",
            type="Form",
            kind="container",
            children=["email", "submit"],
            container_layout=FlowUIContainerLayout(
                mode="stack",
                stack=FlowUIStackDefinition(gap_token="space.3"),
            ),
            properties={"formId": "lead"},
        ),
        "email": FlowUIComponent(
            component_id="email",
            type="TextField",
            bindings={"value": "/values/email"},
            properties={"label": "Email"},
        ),
        "submit": FlowUIComponent(
            component_id="submit",
            type="Button",
            properties={"label": "Send", "variant": "primary"},
            actions={
                "press": FlowUIAction(
                    kind="event",
                    name=PLATFORM_UI_SUBMIT_ACTION,
                    context={"formId": "lead"},
                )
            },
        ),
    }
    surface = FlowUISurface(
        surface_id="main",
        root_component_id="root",
        components=components,
        data_model=FlowUIDataModel(values={"email": ""}),
    )
    document = FlowUIDocument(
        document_id="template:test-lead:1.0.0",
        template_version="1.0.0",
        catalog_id=A2UI_PLATFORM_CATALOG_ID,
        active_page_id="main",
        pages={
            "main": FlowUIPage(
                page_id="main",
                title=LocalizedText(default="Lead"),
                route="/",
                root_surface_id="main",
            )
        },
        surfaces={"main": surface},
        policy=policy,
    )
    return FlowInterfaceConfig(
        template=FlowUIDocumentTemplate(
            template_id="test.lead",
            version="1.0.0",
            document=document,
        ),
        catalog_id=A2UI_PLATFORM_CATALOG_ID,
        policy=policy,
    )


def test_inspector_entry_seeds_ui_values_from_submit_contract() -> None:
    interface = _lead_form_interface()
    result = inspect(
        entry="llm_1",
        nodes_payload={"llm_1": {"type": "llm_node", "prompt": "ok"}},
        interface=interface,
    )
    chips = result.nodes["llm_1"].canvas.inputs
    email_chip = next(chip for chip in chips if chip.label == "ui_values.email")
    assert email_chip.kind == "ui_value"
    assert email_chip.status == "ok"
    labels = {chip.label for chip in chips}
    assert "content" in labels
    assert "ui_values.email" in labels


def test_inspector_without_interface_has_no_ui_values_chips() -> None:
    result = inspect(
        entry="llm_1",
        nodes_payload={"llm_1": {"type": "llm_node", "prompt": "ok"}},
        variables_payload={"company_name": {"value": "ACME"}},
    )
    labels = {chip.label for chip in result.nodes["llm_1"].canvas.inputs}
    assert labels == {"content", "variables.company_name"}
    assert all(not label.startswith("ui_values.") for label in labels)


def test_inspector_downstream_ui_values_mapping_is_guaranteed() -> None:
    interface = _lead_form_interface()
    result = inspect(
        entry="a",
        nodes_payload={
            "a": {"type": "llm_node", "prompt": "start"},
            "b": {
                "type": "llm_node",
                "prompt": "hello",
                "input_mapping": {"email": "@state:ui_values.email"},
            },
        },
        edges_payload=[{"from_node": "a", "to_node": "b"}],
        interface=interface,
    )
    row = result.nodes["b"].input_mapping[0]
    assert row.source_path == "ui_values.email"
    assert row.status == "ok"
    assert not any(issue.code == "missing_state_path" for issue in result.nodes["b"].issues)
    mapping_chip = next(
        chip for chip in result.nodes["b"].canvas.inputs if chip.label == "ui_values.email"
    )
    assert mapping_chip.kind == "ui_value"
    assert mapping_chip.status == "ok"
    incoming = {desc.path: desc for desc in result.nodes["b"].incoming_state}
    assert "ui_values.email" in incoming
    assert incoming["ui_values.email"].availability == "guaranteed"
    assert incoming["ui_values.email"].source == "flow_ui_contract"


def test_inspector_prompt_ui_values_root_is_available() -> None:
    interface = _lead_form_interface()
    result = inspect(
        entry="llm_1",
        nodes_payload={
            "llm_1": {
                "type": "llm_node",
                "prompt": "Lead email: {ui_values.email}",
            },
        },
        interface=interface,
    )
    node = result.nodes["llm_1"]
    assert not any(issue.code == "unknown_prompt_variable" for issue in node.issues)
    ui_req = next(req for req in node.required_inputs if req.name == "ui_values")
    assert ui_req.satisfied is True
    assert ui_req.origin == "prompt"


def test_variable_resolver_renders_ui_values_nested_path() -> None:
    rendered = VariableResolver.render_template(
        "Hi {ui_values.email}",
        local_vars={"ui_values": {"email": "a@b.c"}},
    )
    assert rendered == "Hi a@b.c"
