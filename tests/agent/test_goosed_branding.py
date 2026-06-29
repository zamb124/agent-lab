"""Unit-тесты goosed prompt rebranding HumanitecAgent."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.agent.desktop.build_contract import HumanitecDistroConfig, load_default_distro_config
from apps.agent.desktop.goosed_branding import (
    FORBIDDEN_GOOSED_PROMPT_MARKERS,
    apply_goosed_branding,
    verify_goosed_prompt_templates,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_GOOSE = REPO_ROOT / "apps" / "agent" / "desktop" / "vendor" / "goose"
PROMPTS_DIR = VENDOR_GOOSE / "crates" / "goose" / "src" / "prompts"


@pytest.fixture
def distro() -> HumanitecDistroConfig:
    return load_default_distro_config()


def test_branded_prompt_sources_exist() -> None:
    branded_dir = REPO_ROOT / "apps" / "agent" / "desktop" / "branding" / "prompts"
    for prompt_name in ("system.md", "subagent_system.md", "tiny_model_system.md"):
        prompt_path = branded_dir / prompt_name
        if not prompt_path.is_file():
            raise FileNotFoundError(f"missing branded prompt: {prompt_path}")


def test_apply_goosed_branding_replaces_goose_identity(distro: HumanitecDistroConfig) -> None:
    if not VENDOR_GOOSE.is_dir():
        raise FileNotFoundError(f"Goose submodule is not initialized: {VENDOR_GOOSE}")

    prompt_backups = {
        prompt_path: prompt_path.read_text(encoding="utf-8")
        for prompt_path in PROMPTS_DIR.glob("*.md")
    }
    rust_backups = {
        VENDOR_GOOSE / "crates/goose/src/prompt_template.rs": (
            VENDOR_GOOSE / "crates/goose/src/prompt_template.rs"
        ).read_text(encoding="utf-8"),
        VENDOR_GOOSE / "crates/goose/src/agents/prompt_manager.rs": (
            VENDOR_GOOSE / "crates/goose/src/agents/prompt_manager.rs"
        ).read_text(encoding="utf-8"),
        VENDOR_GOOSE / "crates/goose/src/agents/mcp_client.rs": (
            VENDOR_GOOSE / "crates/goose/src/agents/mcp_client.rs"
        ).read_text(encoding="utf-8"),
    }

    try:
        apply_goosed_branding(VENDOR_GOOSE, distro)
        verify_goosed_prompt_templates(PROMPTS_DIR, distro)
        system_prompt = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
        for marker in FORBIDDEN_GOOSED_PROMPT_MARKERS:
            assert marker not in system_prompt
        assert distro.ui_product_name in system_prompt
        prompt_template = (VENDOR_GOOSE / "crates/goose/src/prompt_template.rs").read_text(
            encoding="utf-8"
        )
        assert f"{distro.ui_product_name}'s personality" in prompt_template
        assert "goose's personality" not in prompt_template
    finally:
        for prompt_path, backup in prompt_backups.items():
            _ = prompt_path.write_text(backup, encoding="utf-8")
        for rust_path, backup in rust_backups.items():
            _ = rust_path.write_text(backup, encoding="utf-8")
