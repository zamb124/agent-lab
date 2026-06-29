"""Build-time rebranding goosed prompt templates and Rust identity strings."""

from __future__ import annotations

import shutil
from pathlib import Path

from apps.agent.desktop.build_contract import HumanitecDistroConfig

DESKTOP_ROOT = Path(__file__).resolve().parent
BRANDED_PROMPTS_DIR = DESKTOP_ROOT / "branding" / "prompts"
GOOSED_PROMPTS_RELATIVE = Path("crates/goose/src/prompts")

FORBIDDEN_GOOSED_PROMPT_MARKERS: tuple[str, ...] = (
    " called goose",
    "AAIF (Agentic AI Foundation)",
    "created by AAIF",
    "the goose AI framework",
    "main goose agent",
    "You are goose,",
)


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
    if required_any and not any(marker in text for marker in required_any):
        missing = ", ".join(repr(marker) for marker in required_any)
        raise ValueError(f"{file_path}: expected goosed branding markers missing: {missing}")
    if modified:
        _ = file_path.write_text(text, encoding="utf-8")


def apply_goosed_prompt_templates(vendor_goose: Path, distro: HumanitecDistroConfig) -> None:
    prompts_target = vendor_goose / GOOSED_PROMPTS_RELATIVE
    if not prompts_target.is_dir():
        raise FileNotFoundError(f"goosed prompts dir missing: {prompts_target}")
    if not BRANDED_PROMPTS_DIR.is_dir():
        raise FileNotFoundError(f"branded prompts dir missing: {BRANDED_PROMPTS_DIR}")

    for branded_prompt_path in sorted(BRANDED_PROMPTS_DIR.glob("*.md")):
        _ = shutil.copyfile(branded_prompt_path, prompts_target / branded_prompt_path.name)

    verify_goosed_prompt_templates(prompts_target, distro)


def patch_goosed_rust_sources(vendor_goose: Path, distro: HumanitecDistroConfig) -> None:
    prompt_template_path = vendor_goose / "crates/goose/src/prompt_template.rs"
    prompt_manager_path = vendor_goose / "crates/goose/src/agents/prompt_manager.rs"
    mcp_client_path = vendor_goose / "crates/goose/src/agents/mcp_client.rs"

    _replace_in_file_text(
        prompt_template_path,
        {
            "Main system prompt that defines goose's personality and behavior": (
                f"Main system prompt that defines {distro.ui_product_name}'s personality and behavior"
            ),
            "Prompt for generating new Goose apps based on the user instructions": (
                f"Prompt for generating new {distro.ui_product_name} apps based on the user instructions"
            ),
            "Prompt for updating existing Goose apps based on feedback": (
                f"Prompt for updating existing {distro.ui_product_name} apps based on feedback"
            ),
            "Prompt used when goose creates step-by-step plans. CLI only": (
                f"Prompt used when {distro.ui_product_name_lower} creates step-by-step plans. CLI only"
            ),
        },
        required_any=(f"{distro.ui_product_name}'s personality",),
    )
    _replace_in_file_text(
        prompt_manager_path,
        {
            '"You are a general-purpose AI agent called goose, created by Block".to_string()': (
                f'"You are a general-purpose AI agent called {distro.ui_product_name}, '
                f'part of the Humanitec platform".to_string()'
            ),
        },
        required_any=(f"called {distro.ui_product_name}",),
    )
    _replace_in_file_text(
        mcp_client_path,
        {
            '.unwrap_or("You are a general-purpose AI agent called goose")': (
                f'.unwrap_or("You are a general-purpose AI agent called {distro.ui_product_name}")'
            ),
        },
        required_any=(f"called {distro.ui_product_name}",),
    )


def verify_goosed_prompt_templates(prompts_dir: Path, distro: HumanitecDistroConfig) -> None:
    system_prompt_path = prompts_dir / "system.md"
    if not system_prompt_path.is_file():
        raise FileNotFoundError(f"system.md missing after goosed branding: {system_prompt_path}")
    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    for marker in FORBIDDEN_GOOSED_PROMPT_MARKERS:
        if marker in system_prompt:
            raise ValueError(f"system.md still contains forbidden marker: {marker!r}")
    if distro.ui_product_name not in system_prompt:
        raise ValueError(f"system.md missing product name: {distro.ui_product_name}")


def apply_goosed_branding(vendor_goose: Path, distro: HumanitecDistroConfig) -> None:
    apply_goosed_prompt_templates(vendor_goose, distro)
    patch_goosed_rust_sources(vendor_goose, distro)
