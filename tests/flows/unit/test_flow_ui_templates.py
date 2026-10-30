"""Галерея шаблонов интерфейса: единственная копия документов для редактора и чата по умолчанию."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.flow_ui.document import FlowUIConversation, FlowUIDocument, FlowUIInputBase
from core.flow_ui.templates import (
    DEFAULT_CHAT_TEMPLATE_ID,
    FlowUITemplate,
    default_chat_document,
    flow_ui_templates,
)
from core.models.i18n_models import Language

ICONS_DIR = Path("core/frontend/static/assets/icons")

EXPECTED_TEMPLATE_IDS = [
    "chat",
    "assistant_context",
    "lead_form",
    "login",
    "contact",
    "validated_form",
    "dashboard",
    "stats_overview",
    "status_tracker",
    "task_list",
    "product_detail",
    "purchase_complete",
    "user_profile",
    "event_detail",
    "notification_center",
    "blank",
]


def _by_id(locale: Language) -> dict[str, FlowUITemplate]:
    return {template.template_id: template for template in flow_ui_templates(locale)}


def test_gallery_order_and_ids_are_stable() -> None:
    assert [template.template_id for template in flow_ui_templates(Language.RU)] == EXPECTED_TEMPLATE_IDS
    assert [template.template_id for template in flow_ui_templates(Language.EN)] == EXPECTED_TEMPLATE_IDS
    assert DEFAULT_CHAT_TEMPLATE_ID == "chat"


@pytest.mark.parametrize("locale", [Language.RU, Language.EN])
def test_every_template_is_a_valid_single_page_document(locale: Language) -> None:
    for template in flow_ui_templates(locale):
        document = template.document
        assert FlowUIDocument.model_validate(document.model_dump(mode="json")) == document
        assert document.start_page_id == "main"
        assert [page.page_id for page in document.pages] == ["main"]
        assert document.pages[0].title != "", template.template_id
        assert template.title != "" and template.description != "", template.template_id


@pytest.mark.parametrize("locale", [Language.RU, Language.EN])
def test_template_icons_exist_as_platform_svg(locale: Language) -> None:
    for template in flow_ui_templates(locale):
        assert (ICONS_DIR / f"{template.icon}.svg").is_file(), template.icon


def test_locales_differ_only_in_copy() -> None:
    ru = _by_id(Language.RU)
    en = _by_id(Language.EN)
    for template_id in EXPECTED_TEMPLATE_IDS:
        ru_blocks = [(block.type, block.block_id) for block in ru[template_id].document.blocks()]
        en_blocks = [(block.type, block.block_id) for block in en[template_id].document.blocks()]
        assert ru_blocks == en_blocks, template_id
        assert ru[template_id].category == en[template_id].category
        assert ru[template_id].icon == en[template_id].icon
    assert ru["lead_form"].title != en["lead_form"].title


def test_categories_cover_the_gallery_tabs() -> None:
    categories = {template.category for template in flow_ui_templates(Language.EN)}
    assert categories == {"conversation", "forms", "dashboards", "content", "utility"}
    assert _by_id(Language.EN)["blank"].category == "utility"
    assert _by_id(Language.EN)["blank"].document.pages[0].blocks == []


def test_default_chat_document_is_the_minimal_feed() -> None:
    document = default_chat_document()
    assert [(block.type, block.block_id) for block in document.blocks()] == [
        ("agent_identity", "agent-identity"),
        ("conversation", "conversation"),
    ]
    assert document.conversation_settings().greeting == ""
    gallery_chat = _by_id(Language.EN)[DEFAULT_CHAT_TEMPLATE_ID].document
    feed = [block for block in gallery_chat.blocks() if isinstance(block, FlowUIConversation)]
    assert len(feed) == 1 and feed[0].block_id == "conversation"
    assert feed[0].settings.greeting != ""


def test_form_templates_write_fields_and_have_a_submit_action() -> None:
    forms = [template for template in flow_ui_templates(Language.EN) if template.category == "forms"]
    assert [template.template_id for template in forms] == ["lead_form", "login", "contact", "validated_form"]
    for template in forms:
        inputs = [block for block in template.document.blocks() if isinstance(block, FlowUIInputBase)]
        assert inputs, template.template_id
        fields = [block.field for block in inputs]
        assert len(fields) == len(set(fields)), template.template_id
        actions = [block for block in template.document.blocks() if block.type == "button"]
        assert actions, template.template_id
