"""
Контракт сборки HumanitecAgent: distro, имена артефактов, префиксы GitHub Release assets.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

DESKTOP_ROOT = Path(__file__).resolve().parent
DISTRO_JSON = DESKTOP_ROOT / "distro" / "humanitec.json"

VALID_PLATFORMS: tuple[str, ...] = (
    "windows",
    "macos-arm64",
    "macos-x64",
    "linux-deb",
    "linux-rpm",
    "linux-appimage",
)


class HumanitecDistroConfig(BaseModel):
    id: str
    display_name: str
    bundle_name: str
    protocol_scheme: str
    auth_callback_path: str
    pairing_path: str
    primary_color: str
    platform_mcp_path: str
    default_frontend_base_url: str
    homepage: str
    maintainer: str
    default_extensions: list[str] = Field(min_length=1)


def load_distro_config(path: Path | None = None) -> HumanitecDistroConfig:
    distro_path = path if path is not None else DISTRO_JSON
    if not distro_path.is_file():
        raise FileNotFoundError(f"Distro config missing: {distro_path}")
    return HumanitecDistroConfig.model_validate(
        json.loads(distro_path.read_text(encoding="utf-8"))
    )


@lru_cache(maxsize=1)
def load_default_distro_config() -> HumanitecDistroConfig:
    return load_distro_config()


def asset_name_pattern(platform: str, bundle_name: str) -> str:
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform!r}")
    patterns: dict[str, str] = {
        "windows": f"{bundle_name}-Setup-",
        "macos-arm64": f"{bundle_name}-macos-arm64-",
        "macos-x64": f"{bundle_name}-macos-x64-",
        "linux-deb": "humanitec-agent_",
        "linux-rpm": "humanitec-agent-",
        "linux-appimage": f"{bundle_name}-",
    }
    return patterns[platform]


def asset_file_suffix(platform: str) -> str:
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform!r}")
    suffixes: dict[str, str] = {
        "windows": ".msi",
        "macos-arm64": ".dmg",
        "macos-x64": ".dmg",
        "linux-deb": ".deb",
        "linux-rpm": ".rpm",
        "linux-appimage": ".AppImage",
    }
    return suffixes[platform]


def matches_release_asset_name(platform: str, asset_name: str, bundle_name: str) -> bool:
    return asset_name.startswith(asset_name_pattern(platform, bundle_name)) and asset_name.endswith(
        asset_file_suffix(platform)
    )


def artifact_filename(platform: str, version_sha: str, bundle_name: str) -> str:
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform!r}")
    if platform == "windows":
        return f"{bundle_name}-Setup-{version_sha}.msi"
    if platform in {"macos-arm64", "macos-x64"}:
        return f"{bundle_name}-{platform}-{version_sha}.dmg"
    if platform == "linux-deb":
        return f"humanitec-agent_{version_sha}_amd64.deb"
    if platform == "linux-rpm":
        return f"humanitec-agent-{version_sha}.x86_64.rpm"
    if platform == "linux-appimage":
        return f"{bundle_name}-{version_sha}.AppImage"
    raise ValueError(f"Unsupported platform: {platform!r}")


def artifact_path(
    dist_dir: Path,
    platform: str,
    version_sha: str,
    distro: HumanitecDistroConfig | None = None,
) -> Path:
    resolved_distro = distro if distro is not None else load_default_distro_config()
    return dist_dir / artifact_filename(platform, version_sha, resolved_distro.bundle_name)
