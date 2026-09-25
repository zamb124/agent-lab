"""EmbedConfig: presentation and launcher position are independent typed fields."""

import pytest
from pydantic import ValidationError

from core.models.embed_models import EmbedConfig, EmbedInterfaceLook, EmbedStatus


def test_embed_config_rejects_unknown_position() -> None:
    with pytest.raises(ValidationError):
        _ = EmbedConfig(
            embed_id="embed_bad_position",
            company_id="company_test",
            name="Bad position",
            flow_id="flow_x",
            presentation="drawer",
            position="fullscreen",  # pyright: ignore[reportArgumentType]
            created_by="user_1",
            status=EmbedStatus.ACTIVE,
        )


def test_embed_interface_look_mirrors_config() -> None:
    config = EmbedConfig(
        embed_id="embed_page_1",
        company_id="company_test",
        name="Page",
        flow_id="flow_x",
        presentation="page",
        position="bottom-left",
        show_launcher=True,
        created_by="user_1",
    )
    look = EmbedInterfaceLook.from_embed_config(config)
    assert look.presentation == "page"
    assert look.position == "bottom-left"
    assert look.show_launcher is True
