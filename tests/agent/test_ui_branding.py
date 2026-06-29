"""Unit-тесты build-time UI rebranding HumanitecAgent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.agent.desktop.ui_branding import (
    I18nMessages,
    apply_ui_product_name_to_i18n_messages,
    parse_i18n_messages,
    replace_ui_product_name_in_text,
    should_skip_i18n_message_key,
)
from core.types import JsonObject, parse_json_object

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ROOT = REPO_ROOT / "apps" / "agent" / "desktop"


def test_should_skip_goosehints_modal_keys() -> None:
    assert should_skip_i18n_message_key("goosehintsModal.dialogTitle")
    assert not should_skip_i18n_message_key("loadingGoose.streaming")


def test_replace_ui_product_name_preserves_goosehints_paths() -> None:
    source = "Настроить подсказки проекта (.goosehints) для Goose"
    expected = "Настроить подсказки проекта (.goosehints) для Humanitec"
    assert (
        replace_ui_product_name_in_text(
            source,
            ui_product_name="Humanitec",
        )
        == expected
    )


def test_replace_ui_product_name_preserves_goosed_and_env() -> None:
    source = "Секретный ключ goosed (GOOSE_SERVER__SECRET_KEY) на сервере goose"
    expected = "Секретный ключ goosed (GOOSE_SERVER__SECRET_KEY) на сервере Humanitec"
    assert (
        replace_ui_product_name_in_text(
            source,
            ui_product_name="Humanitec",
        )
        == expected
    )


def test_apply_ui_product_name_to_i18n_messages_skips_goosehints_modal() -> None:
    messages: I18nMessages = {
        "loadingGoose.streaming": {"defaultMessage": "goose работает над этим…"},
        "goosehintsModal.dialogTitle": {
            "defaultMessage": "Настроить подсказки проекта (.goosehints)",
        },
    }
    patched = apply_ui_product_name_to_i18n_messages(
        messages,
        ui_product_name="Humanitec",
    )
    streaming_entry = patched["loadingGoose.streaming"]
    assert isinstance(streaming_entry, dict)
    assert streaming_entry["defaultMessage"] == "Humanitec работает над этим…"
    goosehints_entry = patched["goosehintsModal.dialogTitle"]
    assert isinstance(goosehints_entry, dict)
    assert goosehints_entry["defaultMessage"] == "Настроить подсказки проекта (.goosehints)"


@pytest.mark.parametrize(
    ("fixture_name", "forbidden", "required"),
    [
        (
            "ru_goose_status.json",
            ("Спросить goose", "goose работает"),
            ("Спросить Humanitec", "Humanitec работает"),
        ),
    ],
)
def test_i18n_fixture_rebrand(
    fixture_name: str,
    forbidden: tuple[str, ...],
    required: tuple[str, ...],
) -> None:
    fixture_path = DESKTOP_ROOT / "tests" / "fixtures" / fixture_name
    messages_raw: JsonObject = parse_json_object(
        fixture_path.read_text(encoding="utf-8"),
        field_name=str(fixture_path),
    )
    parsed_messages = parse_i18n_messages(messages_raw, str(fixture_path))
    patched = apply_ui_product_name_to_i18n_messages(
        parsed_messages,
        ui_product_name="Humanitec",
    )
    serialized = json.dumps(patched, ensure_ascii=False)
    for token in forbidden:
        assert token not in serialized
    for token in required:
        assert token in serialized
