"""Картинка AgentIdentity из FlowUIDocument — одно значение или конфликт."""

import pytest

from core.models.flow_interface import (
    build_default_chat_document,
    flow_ui_agent_identity_image_url,
)
from core.state.flow_ui import FlowUIComponent, FlowUIDocument
from core.types import JsonObject


def _document_with_identity_urls(*image_urls: str | None) -> FlowUIDocument:
    document = build_default_chat_document()
    payload = document.model_dump(mode="python")
    components = payload["surfaces"]["main"]["components"]
    first = True
    for index, image_url in enumerate(image_urls):
        if first:
            properties = dict(components["agent-identity"].get("properties") or {})
            if image_url is not None:
                properties["image_url"] = image_url
            components["agent-identity"]["properties"] = properties
            first = False
            continue
        component_id = f"agent-identity-{index}"
        extra_properties: JsonObject = {}
        if image_url is not None:
            extra_properties["image_url"] = image_url
        components[component_id] = FlowUIComponent(
            component_id=component_id,
            type="AgentIdentity",
            properties=extra_properties,
        ).model_dump(mode="python")
        components["header"]["children"] = [
            *components["header"]["children"],
            component_id,
        ]
    return FlowUIDocument.model_validate(payload)


def test_flow_ui_agent_identity_image_url_none_by_default() -> None:
    assert flow_ui_agent_identity_image_url(build_default_chat_document()) is None


def test_flow_ui_agent_identity_image_url_empty_string_is_none() -> None:
    assert flow_ui_agent_identity_image_url(_document_with_identity_urls("")) is None


def test_flow_ui_agent_identity_image_url_single_value() -> None:
    url = "/flows/api/v1/files/download/agent-img"
    assert flow_ui_agent_identity_image_url(_document_with_identity_urls(url)) == url


def test_flow_ui_agent_identity_image_url_matching_duplicates_ok() -> None:
    url = "/flows/api/v1/files/download/same"
    assert flow_ui_agent_identity_image_url(_document_with_identity_urls(url, url)) == url


def test_flow_ui_agent_identity_image_url_conflict() -> None:
    with pytest.raises(ValueError, match="conflict"):
        flow_ui_agent_identity_image_url(
            _document_with_identity_urls(
                "/flows/api/v1/files/download/a",
                "/flows/api/v1/files/download/b",
            )
        )
