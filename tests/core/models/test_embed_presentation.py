"""EmbedConfig.presentation + position=fullscreen → page."""

from core.models.embed_models import (
    EmbedConfig,
    EmbedInterfaceLook,
    EmbedStatus,
    resolve_embed_presentation,
)


def test_resolve_embed_presentation_drawer_default() -> None:
    assert (
        resolve_embed_presentation(presentation="drawer", position="bottom-right")
        == "drawer"
    )


def test_resolve_embed_presentation_page_explicit() -> None:
    assert resolve_embed_presentation(presentation="page", position="bottom-left") == "page"


def test_resolve_embed_presentation_fullscreen_to_page() -> None:
    assert (
        resolve_embed_presentation(presentation="drawer", position="fullscreen") == "page"
    )


def test_embed_config_model_validator_upgrades_fullscreen() -> None:
    config = EmbedConfig(
        embed_id="embed_fullscreen_upgrade",
        name="Fullscreen",
        flow_id="flow_x",
        presentation="drawer",
        position="fullscreen",
        created_by="user_1",
        status=EmbedStatus.ACTIVE,
    )
    assert config.presentation == "page"
    assert config.position == "bottom-right"


def test_embed_interface_look_from_page_config() -> None:
    config = EmbedConfig(
        embed_id="embed_page_1",
        name="Page",
        flow_id="flow_x",
        presentation="page",
        position="bottom-left",
        show_launcher=True,
        created_by="user_1",
    )
    look = EmbedInterfaceLook.from_embed_config(config)
    assert look.presentation == "page"
    assert look.show_launcher is False
    assert look.position == "bottom-right"
