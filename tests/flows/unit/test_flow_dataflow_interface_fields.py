"""Инспектор dataflow видит поля интерфейса как обычные пути ``ExecutionState``."""

from __future__ import annotations

from core.flow_ui.document import (
    FlowUIActionSpec,
    FlowUIButton,
    FlowUIConversation,
    FlowUIDocument,
    FlowUINumberInput,
    FlowUIPage,
    FlowUITextInput,
)
from core.variables import VariableResolver
from tests.flows.fixtures.dataflow_graphs import inspect


def _lead_form_interface() -> FlowUIDocument:
    return FlowUIDocument(
        start_page_id="main",
        pages=[
            FlowUIPage(
                page_id="main",
                title="Lead",
                blocks=[
                    FlowUITextInput(block_id="email", field="email", label="Email"),
                    FlowUINumberInput(
                        block_id="headcount", field="lead.headcount", label="Headcount"
                    ),
                    FlowUIButton(
                        block_id="submit",
                        label="Send",
                        action=FlowUIActionSpec(name="submit"),
                    ),
                    FlowUIConversation(block_id="conversation"),
                ],
            )
        ],
    )


def test_inspector_entry_seeds_interface_fields() -> None:
    result = inspect(
        entry="llm_1",
        nodes_payload={"llm_1": {"type": "llm_node", "prompt": "ok"}},
        interface=_lead_form_interface(),
    )
    chips = {chip.label: chip for chip in result.nodes["llm_1"].canvas.inputs}
    assert chips["email"].kind == "interface"
    assert chips["email"].status == "ok"
    assert chips["email"].type == "string"
    assert chips["lead.headcount"].kind == "interface"
    assert chips["lead.headcount"].type == "number"
    assert "content" in chips


def test_inspector_without_interface_has_no_interface_chips() -> None:
    result = inspect(
        entry="llm_1",
        nodes_payload={"llm_1": {"type": "llm_node", "prompt": "ok"}},
        variables_payload={"company_name": {"value": "ACME"}},
    )
    labels = {chip.label for chip in result.nodes["llm_1"].canvas.inputs}
    assert labels == {"content", "variables.company_name"}


def test_inspector_downstream_interface_field_mapping_is_known() -> None:
    result = inspect(
        entry="a",
        nodes_payload={
            "a": {"type": "llm_node", "prompt": "start"},
            "b": {
                "type": "llm_node",
                "prompt": "hello",
                "input_mapping": {"email": "@state:email"},
            },
        },
        edges_payload=[{"from_node": "a", "to_node": "b"}],
        interface=_lead_form_interface(),
    )
    row = result.nodes["b"].input_mapping[0]
    assert row.source_path == "email"
    assert row.status == "ok"
    assert not any(issue.code == "missing_state_path" for issue in result.nodes["b"].issues)
    incoming = {desc.path: desc for desc in result.nodes["b"].incoming_state}
    assert incoming["email"].source == "interface"


def test_inspector_prompt_placeholder_of_interface_field_is_available() -> None:
    result = inspect(
        entry="llm_1",
        nodes_payload={
            "llm_1": {
                "type": "llm_node",
                "prompt": "Lead email: {email}",
            },
        },
        interface=_lead_form_interface(),
    )
    node = result.nodes["llm_1"]
    assert not any(issue.code == "unknown_prompt_variable" for issue in node.issues)
    email_req = next(req for req in node.required_inputs if req.name == "email")
    assert email_req.satisfied is True
    assert email_req.origin == "prompt"


def test_variable_resolver_renders_nested_interface_field() -> None:
    rendered = VariableResolver.render_template(
        "Team of {lead.headcount}",
        local_vars={"lead": {"headcount": 12}},
    )
    assert rendered == "Team of 12"
