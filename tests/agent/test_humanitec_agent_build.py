"""
Тесты контракта и placeholder-сборки HumanitecAgent для всех платформ.
"""

from __future__ import annotations

import os
import platform as py_platform
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from apps.agent.desktop.artifact_verify import is_placeholder_artifact, verify_artifact
from apps.agent.desktop.build_contract import (
    VALID_PLATFORMS,
    artifact_filename,
    asset_name_pattern,
    load_default_distro_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ROOT = REPO_ROOT / "apps" / "agent" / "desktop"
DIST_DIR = DESKTOP_ROOT / "dist"
BUILD_SCRIPT = DESKTOP_ROOT / "scripts" / "build.sh"
APPLY_BRANDING_SCRIPT = DESKTOP_ROOT / "scripts" / "apply_branding.sh"
BRANDING_DIR = DESKTOP_ROOT / "branding"


def _tool_path_env() -> dict[str, str]:
    env = os.environ.copy()
    runtime_dir = Path(os.environ.get("PLATFORM_RUNTIME_DIR", "~/.cache/agent-lab/runtimes")).expanduser()
    runtime_bin = runtime_dir / "bin"
    env["PATH"] = f"{runtime_bin}:{env.get('PATH', '')}"
    cargo_home = runtime_dir / "cargo"
    rustup_home = runtime_dir / "rustup"
    if (cargo_home / "bin" / "cargo").is_file():
        env["CARGO_HOME"] = str(cargo_home)
    if rustup_home.is_dir():
        env["RUSTUP_HOME"] = str(rustup_home)
    return env


def _which_tool(name: str) -> str | None:
    env = _tool_path_env()
    return shutil.which(name, path=env["PATH"])


def test_distro_config_branding_fields() -> None:
    distro = load_default_distro_config()
    assert distro.id == "humanitec"
    assert distro.display_name == "HumanitecAgent"
    assert distro.bundle_name == "HumanitecAgent"
    assert distro.protocol_scheme == "humanitec"
    assert distro.platform_mcp_path == "/flows/api/v1/agent/platform-mcp"
    assert "platform_mcp" in distro.default_extensions


def test_distro_fields_in_release_artifact(tmp_path: Path) -> None:
    version_sha = f"distro-{uuid.uuid4().hex[:12]}"
    platform_name = "macos-arm64"
    artifact = _run_build(
        platform_name=platform_name,
        version_sha=version_sha,
        output_dir=tmp_path,
        artifact_mode="placeholder",
    )
    content = artifact.read_text(encoding="utf-8")
    distro = load_default_distro_config()
    assert "HumanitecAgent" in content
    assert "protocol_scheme=humanitec" in content
    assert f"{distro.protocol_scheme}://" == "humanitec://"
    assert distro.platform_mcp_path == "/flows/api/v1/agent/platform-mcp"
    assert "platform_mcp" in distro.default_extensions


@pytest.mark.parametrize("platform_name", VALID_PLATFORMS)
def test_artifact_filename_matches_download_contract(platform_name: str) -> None:
    distro = load_default_distro_config()
    version_sha = "abc123456789"
    filename = artifact_filename(platform_name, version_sha, distro.bundle_name)
    pattern = asset_name_pattern(platform_name, distro.bundle_name)
    assert filename.startswith(pattern)
    assert version_sha in filename


def test_branding_desktop_templates() -> None:
    for desktop_name in ("forge.deb.desktop", "forge.rpm.desktop"):
        content = (BRANDING_DIR / desktop_name).read_text(encoding="utf-8")
        assert "Name=HumanitecAgent" in content
        assert "x-scheme-handler/humanitec" in content


def _run_build(
    *,
    platform_name: str,
    version_sha: str,
    output_dir: Path,
    artifact_mode: str,
) -> Path:
    env = _tool_path_env()
    env["AGENT_OUTPUT_DIR"] = str(output_dir)
    command = [
        str(BUILD_SCRIPT),
        "--platform",
        platform_name,
        "--artifact-mode",
        artifact_mode,
        "--version-sha",
        version_sha,
    ]
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "build.sh failed\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    distro = load_default_distro_config()
    artifact = output_dir / artifact_filename(platform_name, version_sha, distro.bundle_name)
    if not artifact.is_file():
        raise AssertionError(f"Expected artifact missing: {artifact}")
    return artifact


@pytest.mark.parametrize("platform_name", VALID_PLATFORMS)
def test_placeholder_build_each_platform(platform_name: str, tmp_path: Path) -> None:
    version_sha = f"test-{uuid.uuid4().hex}"
    output_dir = tmp_path / platform_name
    artifact = _run_build(
        platform_name=platform_name,
        version_sha=version_sha,
        output_dir=output_dir,
        artifact_mode="placeholder",
    )
    verify_artifact(
        artifact,
        platform=platform_name,
        version_sha=version_sha,
        artifact_mode="placeholder",
    )


def test_apply_branding_script_patches_goose_desktop() -> None:
    goose_desktop = DESKTOP_ROOT / "vendor" / "goose" / "ui" / "desktop"
    if not goose_desktop.is_dir():
        raise FileNotFoundError(f"Goose submodule is not initialized: {goose_desktop}")

    package_json = goose_desktop / "package.json"
    forge_config = goose_desktop / "forge.config.ts"
    package_backup = package_json.read_text(encoding="utf-8")
    forge_backup = forge_config.read_text(encoding="utf-8")
    deb_backup = (goose_desktop / "forge.deb.desktop").read_text(encoding="utf-8")
    rpm_backup = (goose_desktop / "forge.rpm.desktop").read_text(encoding="utf-8")

    try:
        completed = subprocess.run(
            [str(APPLY_BRANDING_SCRIPT)],
            cwd=str(REPO_ROOT),
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "apply_branding.sh failed\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

        package_payload = package_json.read_text(encoding="utf-8")
        forge_payload = forge_config.read_text(encoding="utf-8")
        deb_payload = (goose_desktop / "forge.deb.desktop").read_text(encoding="utf-8")

        assert '"productName": "HumanitecAgent"' in package_payload
        assert '"name": "humanitecagent"' in package_payload
        assert "name: process.env.GOOSE_BUNDLE_NAME" in forge_payload
        assert "executableName: process.env.GOOSE_BUNDLE_NAME" in forge_payload
        assert "tmpdir: process.env.ELECTRON_PACKAGER_TMPDIR" in forge_payload
        assert "name: 'humanitecagent'" in forge_payload
        assert "bin: 'HumanitecAgent'" in forge_payload
        assert "schemes: ['humanitec']" in forge_payload
        assert "@electron-forge/maker-wix" in forge_payload
        assert "@reforged/maker-appimage" in forge_payload
        assert "name: '@electron-forge/maker-deb',\n      platforms: ['linux']," in forge_payload
        assert "Name=HumanitecAgent" in deb_payload
        assert "x-scheme-handler/humanitec" in deb_payload
        defaults_payload = (goose_desktop / "humanitec.defaults.json").read_text(encoding="utf-8")
        assert '"platform_mcp_path": "/flows/api/v1/agent/platform-mcp"' in defaults_payload
        assert '"platform_mcp"' in defaults_payload
    finally:
        _ = package_json.write_text(package_backup, encoding="utf-8")
        _ = forge_config.write_text(forge_backup, encoding="utf-8")
        _ = (goose_desktop / "forge.deb.desktop").write_text(deb_backup, encoding="utf-8")
        _ = (goose_desktop / "forge.rpm.desktop").write_text(rpm_backup, encoding="utf-8")
        defaults_path = goose_desktop / "humanitec.defaults.json"
        if defaults_path.is_file():
            defaults_path.unlink()


def test_artifact_ready_distinguishes_placeholder_from_release() -> None:
    from scripts.agent_build import artifact_ready

    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    version_sha = completed.stdout.strip()
    if not version_sha:
        raise RuntimeError("git rev-parse HEAD returned empty sha")
    platform_name = _native_platform()
    if platform_name is None:
        raise RuntimeError("Unsupported host OS for artifact_ready contract test")
    distro = load_default_distro_config()
    artifact = DIST_DIR / artifact_filename(platform_name, version_sha, distro.bundle_name)
    if not artifact.is_file():
        raise FileNotFoundError(
            f"Expected local artifact for contract test: {artifact}. "
            "Run placeholder build for current HEAD first."
        )
    if is_placeholder_artifact(artifact):
        if artifact_ready(platform_name, version_sha, artifact_mode="release"):
            raise AssertionError("placeholder artifact must not satisfy release artifact_ready")
        if not artifact_ready(platform_name, version_sha, artifact_mode="placeholder"):
            raise AssertionError("placeholder artifact must satisfy placeholder artifact_ready")
        return
    if not artifact_ready(platform_name, version_sha, artifact_mode="release"):
        raise AssertionError("release artifact must satisfy release artifact_ready")
    if artifact_ready(platform_name, version_sha, artifact_mode="placeholder"):
        raise AssertionError("release artifact must not satisfy placeholder artifact_ready")


def _native_platform() -> str | None:
    system = py_platform.system().lower()
    machine = py_platform.machine().lower()
    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "macos-arm64"
        return "macos-x64"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux-deb"
    return None


@pytest.mark.agent_build_release
@pytest.mark.timeout(3600)
@pytest.mark.xdist_group(name="agent_build_release")
def test_release_build_native_platform(tmp_path: Path) -> None:
    platform_name = _native_platform()
    if platform_name is None:
        raise RuntimeError("Unsupported host OS for HumanitecAgent release build")

    if platform_name == "windows" and _which_tool("pnpm") is None:
        raise RuntimeError("pnpm is required for Windows release build")

    if _which_tool("pnpm") is None or _which_tool("cargo") is None:
        raise RuntimeError("pnpm and cargo are required for HumanitecAgent release build")

    goose_vendor = DESKTOP_ROOT / "vendor" / "goose"
    if not goose_vendor.is_dir():
        raise FileNotFoundError(f"Goose submodule is not initialized: {goose_vendor}")

    version_sha = f"release-{uuid.uuid4().hex[:12]}"
    output_dir = tmp_path / "release"
    artifact = _run_build(
        platform_name=platform_name,
        version_sha=version_sha,
        output_dir=output_dir,
        artifact_mode="release",
    )
    verify_artifact(
        artifact,
        platform=platform_name,
        version_sha=version_sha,
        artifact_mode="release",
    )
