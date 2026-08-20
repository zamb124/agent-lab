"""Unit-тесты build-time UI rebranding HumanitecAgent."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from apps.agent.desktop.build_contract import HumanitecDistroConfig, load_default_distro_config
from apps.agent.desktop.ui_branding import (
    I18nMessages,
    apply_ui_branding,
    apply_ui_product_name_to_i18n_messages,
    parse_i18n_messages,
    rebrand_legacy_product_names_in_text,
    replace_ui_product_name_in_text,
    should_skip_i18n_message_key,
    verify_no_goose_docs_urls,
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


def test_rebrand_legacy_product_names_replaces_humanitec_before_goose() -> None:
    distro = HumanitecDistroConfig.model_validate(
        {
            "id": "humanitec",
            "display_name": "LinnexAgent",
            "bundle_name": "LinnexAgent",
            "ui_product_name": "Linnex",
            "ui_product_name_lower": "linnex",
            "protocol_scheme": "linnex",
            "auth_callback_path": "auth/callback",
            "pairing_path": "pairing",
            "primary_color": "#694E9F",
            "platform_mcp_path": "/flows/api/v1/agent/platform-mcp",
            "default_frontend_base_url": "https://linnex.io",
            "homepage": "https://linnex.io",
            "maintainer": "Linnex <info@linnex.io>",
            "default_extensions": ["developer"],
        }
    )
    source = "HumanitecAgent подключается к Humanitec и goose"
    expected = "LinnexAgent подключается к Linnex и Linnex"
    assert rebrand_legacy_product_names_in_text(source, distro=distro) == expected


def test_apply_ui_product_name_to_i18n_messages_skips_goosehints_modal() -> None:
    distro = load_default_distro_config()
    messages: I18nMessages = {
        "loadingGoose.streaming": {"defaultMessage": "goose работает над этим…"},
        "goosehintsModal.dialogTitle": {
            "defaultMessage": "Настроить подсказки проекта (.goosehints)",
        },
    }
    patched = apply_ui_product_name_to_i18n_messages(
        messages,
        distro=distro,
    )
    streaming_entry = patched["loadingGoose.streaming"]
    assert isinstance(streaming_entry, dict)
    assert streaming_entry["defaultMessage"] == f"{distro.ui_product_name} работает над этим…"
    goosehints_entry = patched["goosehintsModal.dialogTitle"]
    assert isinstance(goosehints_entry, dict)
    assert goosehints_entry["defaultMessage"] == "Настроить подсказки проекта (.goosehints)"


def test_patch_goose_docs_urls_replaces_all_desktop_sources() -> None:
    goose_desktop = DESKTOP_ROOT / "vendor" / "goose" / "ui" / "desktop"
    if not goose_desktop.is_dir():
        raise FileNotFoundError(f"Goose submodule is not initialized: {goose_desktop}")

    ui_branding_relative_paths = (
        "src/components/BaseChat.tsx",
        "src/components/extensions/ExtensionsView.tsx",
        "src/components/settings/providers/modal/constants.tsx",
        "forge.config.ts",
    )
    ui_branding_backups = {
        goose_desktop / relative_path: (goose_desktop / relative_path).read_text(encoding="utf-8")
        for relative_path in ui_branding_relative_paths
        if (goose_desktop / relative_path).is_file()
    }

    git_reset = subprocess.run(
        ["git", "checkout", "--", *ui_branding_relative_paths],
        cwd=str(goose_desktop),
        check=False,
        capture_output=True,
        text=True,
    )
    if git_reset.returncode != 0:
        raise AssertionError(
            "git checkout failed before apply_ui_branding\n"
            + f"stdout:\n{git_reset.stdout}\n"
            + f"stderr:\n{git_reset.stderr}"
        )

    try:
        apply_ui_branding(goose_desktop, load_default_distro_config())
        verify_no_goose_docs_urls(goose_desktop)
        constants_payload = (
            goose_desktop / "src" / "components" / "settings" / "providers" / "modal" / "constants.tsx"
        ).read_text(encoding="utf-8")
        assert f"{load_default_distro_config().homepage}/docs/quickstart" in constants_payload
    finally:
        for ui_path, ui_backup in ui_branding_backups.items():
            _ = ui_path.write_text(ui_backup, encoding="utf-8")


@pytest.mark.parametrize(
    ("fixture_name", "forbidden", "required"),
    [
        (
            "ru_goose_status.json",
            ("Спросить goose", "goose работает"),
            ("Спросить Linnex", "Linnex работает"),
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
        distro=load_default_distro_config(),
    )
    serialized = json.dumps(patched, ensure_ascii=False)
    for token in forbidden:
        assert token not in serialized
    for token in required:
        assert token in serialized
