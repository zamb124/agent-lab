"""Сборка и установка реального HumanitecAgent release для desktop E2E."""

from __future__ import annotations

import platform
import plistlib
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from apps.agent.desktop.artifact_verify import (
    ArtifactVerificationError,
    is_placeholder_artifact,
    verify_release_artifact,
)
from apps.agent.desktop.build_contract import (
    artifact_path as contract_artifact_path,
)
from apps.agent.desktop.build_contract import (
    load_default_distro_config,
)
from apps.agent.local_releases import resolve_local_release_artifact_path
from scripts.agent_build import detect_host_platform

REPO_ROOT = Path(__file__).resolve().parents[3]
DESKTOP_ROOT = REPO_ROOT / "apps" / "agent" / "desktop"
DIST_DIR = DESKTOP_ROOT / "dist"
# macOS Launch Services помечает бандлы под $TMPDIR флагом `in-temp-dir` и
# отказывается делать их authoritative claimant для custom URL scheme (`open
# linnex://...` падает `kLSApplicationNotFoundErr` либо уходит в чужой stale
# bundle). Устанавливаем desktop E2E copy вне temp — иначе реальный OS-level
# deep link (в отличие от IPC test-only моста) недетерминированно не долетает.
_MACOS_LS_INSTALL_ROOT = Path.home() / "Library" / "Caches" / "agent-lab-desktop-e2e" / "installs"
_LSREGISTER_BIN = Path(
    "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks"
    "/LaunchServices.framework/Support/lsregister"
)


def _lsregister_unclaim(app_path: Path) -> None:
    if platform.system() != "Darwin" or not _LSREGISTER_BIN.is_file():
        return
    subprocess.run(
        [str(_LSREGISTER_BIN), "-u", str(app_path)],
        check=False,
        capture_output=True,
        text=True,
    )


@dataclass(frozen=True)
class HumanitecDesktopInstall:
    artifact_path: Path
    executable: Path
    bundle_name: str
    install_root: Path
    protocol_scheme: str

    def cleanup(self) -> None:
        if self.install_root.is_dir():
            _lsregister_unclaim(self.install_root / f"{self.bundle_name}.app")
            shutil.rmtree(self.install_root, ignore_errors=True)


def _git_head_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    sha = completed.stdout.strip()
    if not sha:
        raise RuntimeError("git rev-parse HEAD returned empty sha")
    return sha


def _run_apply_branding() -> None:
    """Только для тестов сборки/branding. Pytest fixtures не вызывают."""
    apply_branding = DESKTOP_ROOT / "scripts" / "apply_branding.sh"
    if not apply_branding.is_file():
        raise FileNotFoundError(f"apply_branding.sh missing: {apply_branding}")
    completed = subprocess.run(
        [str(apply_branding)],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "apply_branding.sh failed\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def ensure_humanitec_desktop_release_artifact() -> Path:
    """Read-only verify: артефакт собирает make agent-ensure до pytest, не fixture."""
    configured_mode = __import__("os").environ.get("AGENT_ARTIFACT_MODE")
    if configured_mode is not None and configured_mode != "release":
        raise ValueError(
            f"desktop E2E requires AGENT_ARTIFACT_MODE=release, got {configured_mode!r}"
        )
    host_platform = detect_host_platform()
    artifact = resolve_local_release_artifact_path(host_platform)
    if is_placeholder_artifact(artifact):
        raise ArtifactVerificationError(
            f"placeholder artifact forbidden for desktop E2E: {artifact}"
        )
    distro = load_default_distro_config()
    verify_release_artifact(
        artifact,
        platform=host_platform,
        distro=distro,
    )
    return artifact


def _install_macos_dmg(
    artifact_path: Path,
    distro_bundle_name: str,
    protocol_scheme: str,
) -> HumanitecDesktopInstall:
    if platform.system() != "Darwin":
        raise RuntimeError("macOS DMG install requires darwin host")
    if shutil.which("hdiutil") is None:
        raise FileNotFoundError("hdiutil is required to mount HumanitecAgent DMG")

    _MACOS_LS_INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
    install_root = _MACOS_LS_INSTALL_ROOT / uuid.uuid4().hex
    install_root.mkdir(parents=True)
    mount_dir = Path(tempfile.mkdtemp(prefix="humanitec-agent-mount-"))
    attach_result = subprocess.run(
        [
            "hdiutil",
            "attach",
            "-nobrowse",
            "-readonly",
            "-mountpoint",
            str(mount_dir),
            str(artifact_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if attach_result.returncode != 0:
        raise RuntimeError(
            "failed to mount HumanitecAgent DMG: "
            + attach_result.stderr
            + attach_result.stdout
        )
    try:
        app_candidates = sorted(mount_dir.glob("*.app"))
        if not app_candidates:
            visible = sorted(entry.name for entry in mount_dir.iterdir())
            raise FileNotFoundError(f"no .app in DMG, entries: {visible}")
        source_app = app_candidates[0]
        if source_app.name != f"{distro_bundle_name}.app":
            raise FileNotFoundError(
                f"unexpected bundle name {source_app.name!r}, expected {distro_bundle_name}.app"
            )
        target_app = install_root / source_app.name
        shutil.copytree(source_app, target_app)
        if _LSREGISTER_BIN.is_file():
            register_result = subprocess.run(
                [str(_LSREGISTER_BIN), "-f", str(target_app)],
                check=False,
                capture_output=True,
                text=True,
            )
            if register_result.returncode != 0:
                raise RuntimeError(
                    "lsregister -f failed for desktop E2E install: "
                    + register_result.stderr
                    + register_result.stdout
                )
        executable = target_app / "Contents" / "MacOS" / distro_bundle_name
        if not executable.is_file():
            raise FileNotFoundError(f"HumanitecAgent executable missing: {executable}")
        info_plist = target_app / "Contents" / "Info.plist"
        with info_plist.open("rb") as handle:
            plist_payload = plistlib.load(handle)
        display_name = plist_payload.get("CFBundleDisplayName")
        if display_name != distro_bundle_name and plist_payload.get("CFBundleName") != distro_bundle_name:
            raise ArtifactVerificationError(
                f"installed app branding mismatch: {display_name!r}"
            )
        return HumanitecDesktopInstall(
            artifact_path=artifact_path,
            executable=executable,
            bundle_name=distro_bundle_name,
            install_root=install_root,
            protocol_scheme=protocol_scheme,
        )
    finally:
        detach_result = subprocess.run(
            ["hdiutil", "detach", str(mount_dir), "-quiet"],
            check=False,
            capture_output=True,
            text=True,
        )
        if detach_result.returncode != 0:
            raise RuntimeError(
                "failed to detach HumanitecAgent DMG: "
                + detach_result.stderr
                + detach_result.stdout
            )
        if mount_dir.is_dir():
            mount_dir.rmdir()


def _install_linux_artifact(
    artifact_path: Path,
    distro_bundle_name: str,
    protocol_scheme: str,
) -> HumanitecDesktopInstall:
    host_platform = detect_host_platform()
    install_root = Path(tempfile.mkdtemp(prefix="humanitec-agent-install-"))
    if host_platform == "linux-deb":
        if shutil.which("dpkg-deb") is None:
            raise FileNotFoundError("dpkg-deb is required for deb install")
        extract_result = subprocess.run(
            ["dpkg-deb", "-x", str(artifact_path), str(install_root)],
            check=False,
            capture_output=True,
            text=True,
        )
        if extract_result.returncode != 0:
            raise RuntimeError(f"dpkg-deb extract failed: {extract_result.stderr}")
        candidates = list(install_root.rglob(distro_bundle_name))
        if not candidates:
            candidates = list(install_root.rglob("*HumanitecAgent*"))
        if not candidates:
            raise FileNotFoundError(f"HumanitecAgent binary not found in deb: {install_root}")
        executable = candidates[0]
        if not executable.is_file():
            raise FileNotFoundError(f"HumanitecAgent executable is not a file: {executable}")
        return HumanitecDesktopInstall(
            artifact_path=artifact_path,
            executable=executable,
            bundle_name=distro_bundle_name,
            install_root=install_root,
            protocol_scheme=protocol_scheme,
        )
    if host_platform == "linux-appimage":
        target = install_root / artifact_path.name
        shutil.copy2(artifact_path, target)
        target.chmod(target.stat().st_mode | 0o111)
        return HumanitecDesktopInstall(
            artifact_path=artifact_path,
            executable=target,
            bundle_name=distro_bundle_name,
            install_root=install_root,
            protocol_scheme=protocol_scheme,
        )
    raise RuntimeError(f"unsupported Linux desktop E2E platform: {host_platform}")


def install_humanitec_desktop_release(artifact_path: Path) -> HumanitecDesktopInstall:
    distro = load_default_distro_config()
    host_platform = detect_host_platform()
    if host_platform.startswith("macos"):
        return _install_macos_dmg(
            artifact_path,
            distro.bundle_name,
            distro.protocol_scheme,
        )
    if host_platform.startswith("linux"):
        return _install_linux_artifact(
            artifact_path,
            distro.bundle_name,
            distro.protocol_scheme,
        )
    if host_platform == "windows":
        raise RuntimeError("Windows HumanitecAgent desktop E2E install is not implemented yet")
    raise RuntimeError(f"unsupported host platform for desktop E2E: {platform.system()}")


def expected_release_artifact_path(version_sha: str) -> Path:
    distro = load_default_distro_config()
    host_platform = detect_host_platform()
    return contract_artifact_path(DIST_DIR, host_platform, version_sha, distro)
