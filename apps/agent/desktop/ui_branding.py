"""
Build-time UI rebranding: замена user-visible «Goose»/«goose» на Humanitec без поломки goosed/.goosehints.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict

from apps.agent.desktop.build_contract import HumanitecDistroConfig
from core.types import JsonObject, parse_json_object

PROTECTED_MESSAGE_SUBSTRINGS: tuple[str, ...] = (
    ".goosehints",
    "goosed",
    "GOOSE_",
    "goose://",
)

GOOSEHINTS_MESSAGE_KEY_PREFIX = "goosehintsModal."

PROTECTED_MESSAGE_PATTERN = re.compile(
    "|".join(re.escape(fragment) for fragment in PROTECTED_MESSAGE_SUBSTRINGS)
)


class I18nMessageEntry(TypedDict):
    defaultMessage: str


I18nMessages = dict[str, I18nMessageEntry]


def should_skip_i18n_message_key(message_key: str) -> bool:
    return message_key.startswith(GOOSEHINTS_MESSAGE_KEY_PREFIX)


def replace_ui_product_name_in_text(text: str, *, ui_product_name: str) -> str:
    protected_segments: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected_segments.append(match.group(0))
        return f"__HUMANITEC_PROTECTED_{len(protected_segments) - 1}__"

    working_text = PROTECTED_MESSAGE_PATTERN.sub(protect, text)
    working_text = working_text.replace("Goose", ui_product_name)
    working_text = working_text.replace("goose", ui_product_name)
    for index, original in enumerate(protected_segments):
        working_text = working_text.replace(f"__HUMANITEC_PROTECTED_{index}__", original)
    return working_text


def parse_i18n_messages(raw_payload: object, source_label: str) -> I18nMessages:
    if not isinstance(raw_payload, dict):
        raise ValueError(f"{source_label} must be a JSON object")
    parsed_messages: I18nMessages = {}
    for message_key, message_entry in raw_payload.items():
        if not isinstance(message_key, str):
            raise ValueError(f"{source_label} keys must be strings")
        if not isinstance(message_entry, dict):
            continue
        default_message = message_entry.get("defaultMessage")
        if not isinstance(default_message, str):
            continue
        parsed_messages[message_key] = {"defaultMessage": default_message}
    return parsed_messages


def apply_ui_product_name_to_i18n_messages(
    messages: I18nMessages,
    *,
    ui_product_name: str,
) -> I18nMessages:
    patched_messages: I18nMessages = {}
    for message_key, message_entry in messages.items():
        if should_skip_i18n_message_key(message_key):
            patched_messages[message_key] = message_entry
            continue
        default_message = message_entry.get("defaultMessage")
        if not isinstance(default_message, str):
            patched_messages[message_key] = message_entry
            continue
        patched_messages[message_key] = {
            "defaultMessage": replace_ui_product_name_in_text(
                default_message,
                ui_product_name=ui_product_name,
            ),
        }
    return patched_messages


def _replace_in_file_text(
    file_path: Path,
    replacements: dict[str, str],
    *,
    required_any: tuple[str, ...] = (),
) -> None:
    text = file_path.read_text(encoding="utf-8")
    modified = False
    for source, target in replacements.items():
        if source in text:
            text = text.replace(source, target)
            modified = True
    if required_any:
        if not any(marker in text for marker in required_any):
            missing = ", ".join(repr(marker) for marker in required_any)
            raise ValueError(f"{file_path}: expected branding markers missing: {missing}")
    if modified:
        _ = file_path.write_text(text, encoding="utf-8")


def patch_base_chat_watermark(goose_desktop: Path, distro: HumanitecDistroConfig) -> None:
    base_chat_path = goose_desktop / "src" / "components" / "BaseChat.tsx"
    text = base_chat_path.read_text(encoding="utf-8")
    goose_import = "import { Goose } from './icons';"
    watermark_import = "import humanitecWatermarkIcon from '../images/icon.png';"
    if goose_import in text and watermark_import not in text:
        text = text.replace(goose_import, watermark_import, 1)

    watermark_anchor = """          {/* Goose watermark - top right */}
          <div className="absolute top-[14px] right-4 z-[60] flex flex-row items-center gap-1">
            <a
              href="https://goose-docs.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="no-drag flex flex-row items-center gap-1 hover:opacity-80 transition-opacity"
            >
              <Goose className="size-5 goose-icon-animation" />
              <span className="text-sm leading-none text-text-secondary -translate-y-px">
                goose
              </span>
            </a>
            <EnvironmentBadge className="translate-y-px" />
          </div>"""
    watermark_patch = f"""          {{/* Humanitec watermark - top right */}}
          <div className="absolute top-[14px] right-4 z-[60] flex flex-row items-center gap-1">
            <a
              href="{distro.homepage}"
              target="_blank"
              rel="noopener noreferrer"
              className="no-drag flex flex-row items-center gap-1 hover:opacity-80 transition-opacity"
            >
              <img
                src={{humanitecWatermarkIcon}}
                alt="{distro.ui_product_name}"
                className="size-5 rounded-sm"
              />
              <span className="text-sm leading-none text-text-secondary -translate-y-px">
                {distro.ui_product_name_lower}
              </span>
            </a>
            <EnvironmentBadge className="translate-y-px" />
          </div>"""
    if watermark_anchor in text:
        text = text.replace(watermark_anchor, watermark_patch, 1)
    elif distro.homepage not in text or distro.ui_product_name_lower not in text:
        raise ValueError(f"{base_chat_path}: watermark anchor missing")
    _ = base_chat_path.write_text(text, encoding="utf-8")


def patch_loading_goose_messages(goose_desktop: Path, distro: HumanitecDistroConfig) -> None:
    loading_goose_path = goose_desktop / "src" / "components" / "LoadingGoose.tsx"
    replacements = {
        "defaultMessage: 'goose is thinking…'": (
            f"defaultMessage: '{distro.ui_product_name} is thinking…'"
        ),
        "defaultMessage: 'goose is working on it…'": (
            f"defaultMessage: '{distro.ui_product_name} is working on it…'"
        ),
        "defaultMessage: 'goose is waiting…'": (
            f"defaultMessage: '{distro.ui_product_name} is waiting…'"
        ),
        "defaultMessage: 'goose is compacting the conversation...'": (
            f"defaultMessage: '{distro.ui_product_name} is compacting the conversation...'"
        ),
    }
    _replace_in_file_text(
        loading_goose_path,
        replacements,
        required_any=(f"{distro.ui_product_name} is working on it…",),
    )


def patch_onboarding_guard_messages(goose_desktop: Path, distro: HumanitecDistroConfig) -> None:
    onboarding_path = goose_desktop / "src" / "components" / "onboarding" / "OnboardingGuard.tsx"
    _replace_in_file_text(
        onboarding_path,
        {
            "defaultMessage: 'Unable to connect to Goose server'": (
                f"defaultMessage: 'Unable to connect to {distro.ui_product_name} agent server'"
            ),
        },
        required_any=(f"Unable to connect to {distro.ui_product_name} agent server",),
    )


def patch_main_process_ui_strings(goose_desktop: Path, distro: HumanitecDistroConfig) -> None:
    main_path = goose_desktop / "src" / "main.ts"
    replacements = {
        "'Focus Goose Window'": f"'Focus {distro.ui_product_name} Window'",
        "'About Goose'": f"'About {distro.ui_product_name}'",
        "'Hide Goose'": f"'Hide {distro.bundle_name}'",
        "'聚焦 Goose 窗口'": f"'聚焦 {distro.ui_product_name} 窗口'",
        "'关于 Goose'": f"'关于 {distro.ui_product_name}'",
        "'隐藏 Goose'": f"'隐藏 {distro.bundle_name}'",
        "applicationName: 'Goose'": f"applicationName: '{distro.display_name}'",
        "title: 'Goose'": f"title: '{distro.display_name}'",
        "title: 'Goose Failed to Start'": f"title: '{distro.display_name} Failed to Start'",
        "item.label === 'Goose'": f"item.label === '{distro.bundle_name}'",
        "menuT('Focus Goose Window')": f"menuT('Focus {distro.ui_product_name} Window')",
        "menuT('About Goose')": f"menuT('About {distro.ui_product_name}')",
    }
    _replace_in_file_text(
        main_path,
        replacements,
        required_any=(f"item.label === '{distro.bundle_name}'",),
    )


def patch_forge_usage_descriptions(goose_desktop: Path, distro: HumanitecDistroConfig) -> None:
    forge_path = goose_desktop / "forge.config.ts"
    _replace_in_file_text(
        forge_path,
        {
            "'Goose needs access to your calendars to help manage and query calendar events.'": (
                f"'{distro.ui_product_name} needs access to your calendars to help manage "
                "and query calendar events.'"
            ),
            "'Goose needs access to your reminders to help manage and query reminders.'": (
                f"'{distro.ui_product_name} needs access to your reminders to help manage "
                "and query reminders.'"
            ),
        },
        required_any=(f"{distro.ui_product_name} needs access to your calendars",),
    )


def patch_ru_i18n_messages(goose_desktop: Path, distro: HumanitecDistroConfig) -> None:
    ru_messages_path = goose_desktop / "src" / "i18n" / "messages" / "ru.json"
    if not ru_messages_path.is_file():
        return
    merged_messages: JsonObject = parse_json_object(
        ru_messages_path.read_text(encoding="utf-8"),
        field_name=str(ru_messages_path),
    )
    parsed_messages = parse_i18n_messages(merged_messages, str(ru_messages_path))
    patched_messages = apply_ui_product_name_to_i18n_messages(
        parsed_messages,
        ui_product_name=distro.ui_product_name,
    )
    for message_key, message_entry in patched_messages.items():
        existing_entry = merged_messages.get(message_key)
        if not isinstance(existing_entry, dict):
            continue
        existing_entry["defaultMessage"] = message_entry["defaultMessage"]
    _ = ru_messages_path.write_text(
        json.dumps(merged_messages, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_patched_desktop_ui_sources(
    goose_desktop: Path,
    distro: HumanitecDistroConfig,
) -> None:
    base_chat_text = (goose_desktop / "src" / "components" / "BaseChat.tsx").read_text(
        encoding="utf-8"
    )
    if "goose-docs.ai" in base_chat_text:
        raise ValueError("BaseChat.tsx still references goose-docs.ai")
    if distro.ui_product_name_lower not in base_chat_text:
        raise ValueError("BaseChat.tsx missing Humanitec watermark label")

    ru_messages_path = goose_desktop / "src" / "i18n" / "messages" / "ru.json"
    if ru_messages_path.is_file():
        merged_messages = parse_json_object(
            ru_messages_path.read_text(encoding="utf-8"),
            field_name=str(ru_messages_path),
        )
        parsed_messages = parse_i18n_messages(merged_messages, str(ru_messages_path))
        goosehints_entry = parsed_messages.get("goosehintsModal.dialogTitle")
        if goosehints_entry is not None:
            goosehints_title = goosehints_entry.get("defaultMessage")
            if goosehints_title is not None and ".goosehints" not in goosehints_title:
                raise ValueError("goosehintsModal.dialogTitle lost .goosehints reference")


def apply_ui_branding(goose_desktop: Path, distro: HumanitecDistroConfig) -> None:
    patch_base_chat_watermark(goose_desktop, distro)
    patch_loading_goose_messages(goose_desktop, distro)
    patch_onboarding_guard_messages(goose_desktop, distro)
    patch_main_process_ui_strings(goose_desktop, distro)
    patch_forge_usage_descriptions(goose_desktop, distro)
    patch_ru_i18n_messages(goose_desktop, distro)
    verify_patched_desktop_ui_sources(goose_desktop, distro)
