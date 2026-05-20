import pytest

from core.urn import (
    URN,
    BranchURN,
    FlowURN,
    NodeURN,
    ToolURN,
    VariableURN,
    extract_resource_id,
    is_urn,
    normalize_to_urn,
)


def test_urn_uses_resource_type_and_resource_id_names() -> None:
    urn = URN.parse("urn:iman:node:summarizer")

    assert urn.resource_type == "node"
    assert urn.resource_id == "summarizer"
    assert str(urn) == "urn:iman:node:summarizer"


def test_flow_urn_replaces_agent_term() -> None:
    flow_urn = FlowURN.create("customer_service")

    assert flow_urn.resource_type == "flow"
    assert flow_urn.resource_id == "customer_service"
    assert flow_urn.urn == "urn:iman:flow:customer_service"


def test_specialized_urn_factories_use_canonical_entity_ids() -> None:
    assert NodeURN.create("summarizer").urn == "urn:iman:node:summarizer"
    assert ToolURN.create("calculator").urn == "urn:iman:tool:calculator"
    assert BranchURN.create("refund").urn == "urn:iman:branch:refund"
    assert VariableURN.create("api_key").urn == "urn:iman:variable:api_key"


def test_legacy_agent_and_skill_resource_types_are_rejected() -> None:
    with pytest.raises(ValueError, match="Неизвестный тип ресурса"):
        URN.parse("urn:iman:agent:customer_service")

    with pytest.raises(ValueError, match="Неизвестный тип ресурса"):
        URN.parse("urn:iman:skill:refund")


def test_extract_resource_id_and_normalize_to_urn() -> None:
    assert extract_resource_id("urn:iman:node:summarizer") == "summarizer"
    assert extract_resource_id("plain_resource") == "plain_resource"
    assert normalize_to_urn("plain_flow", "flow").urn == "urn:iman:flow:plain_flow"
    assert is_urn("urn:iman:flow:customer_service") is True
