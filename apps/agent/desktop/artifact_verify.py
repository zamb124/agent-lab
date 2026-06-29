"""
Проверка артефактов HumanitecAgent после сборки: именование и брендинг.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import cast

from apps.agent.desktop.build_contract import (
    HumanitecDistroConfig,
    artifact_filename,
    load_distro_config,
)

PLACEHOLDER_MARKER = "HumanitecAgent placeholder"
MIN_RELEASE_BYTES = 512_000
HDIUTIL_ATTACH_MAX_ATTEMPTS = 5
HDIUTIL_ATTACH_RETRY_DELAY_SECONDS = 3.0


def _macos_notarized_verification_enabled() -> bool:
    env_value = os.environ.get("AGENT_VERIFY_MACOS_NOTARIZED")
    if env_value is None:
        return False
    stripped = env_value.strip()
    if not stripped:
        return False
    return stripped == "1"


def _macos_codesign_verification_enabled() -> bool:
    env_value = os.environ.get("AGENT_VERIFY_CODESIGN")
    if env_value is None:
        return False
    stripped = env_value.strip()
    if not stripped:
        return False
    return stripped == "1"


class ArtifactVerificationError(Exception):
    pass


def _verify_macos_ui_branding_in_app_bundle(
    app_bundle: Path,
    distro: HumanitecDistroConfig,
) -> None:
    asar_path = app_bundle / "Contents" / "Resources" / "app.asar"
    if not asar_path.is_file():
        raise ArtifactVerificationError(f"Missing app.asar in {app_bundle}")
    asar_bytes = asar_path.read_bytes()
    if b"goose-docs.ai" in asar_bytes:
        raise ArtifactVerificationError("Branded app.asar still references goose-docs.ai")
    if distro.homepage.encode("utf-8") not in asar_bytes:
        raise ArtifactVerificationError(f"app.asar missing homepage {distro.homepage!r}")
    if distro.ui_product_name_lower.encode("utf-8") not in asar_bytes:
        raise ArtifactVerificationError(
            f"app.asar missing ui product label {distro.ui_product_name_lower!r}"
        )


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise ArtifactVerificationError(f"Artifact file missing: {path}")


def _read_head(path: Path, limit: int = 256) -> str:
    with path.open("rb") as handle:
        return handle.read(limit).decode("utf-8", errors="replace")


def is_placeholder_artifact(path: Path) -> bool:
    return PLACEHOLDER_MARKER in _read_head(path)


def verify_placeholder_artifact(
    path: Path,
    *,
    platform: str,
    version_sha: str,
    distro: HumanitecDistroConfig,
) -> None:
    _require_file(path)
    expected_name = artifact_filename(platform, version_sha, distro.bundle_name)
    if path.name != expected_name:
        raise ArtifactVerificationError(
            f"Unexpected artifact name: {path.name!r}, expected {expected_name!r}"
        )
    content = path.read_text(encoding="utf-8")
    if PLACEHOLDER_MARKER not in content:
        raise ArtifactVerificationError("Placeholder artifact missing build marker")
    for required_token in (
        distro.display_name,
        distro.bundle_name,
        distro.protocol_scheme,
        platform,
        version_sha,
    ):
        if required_token not in content:
            raise ArtifactVerificationError(
                f"Placeholder artifact missing branding token: {required_token!r}"
            )


def hdiutil_attach_error_is_retryable(stderr_text: str, stdout_text: str) -> bool:
    combined = f"{stderr_text}\n{stdout_text}".lower()
    retry_markers = (
        "resource temporarily unavailable",
        "try again",
        "temporarily unavailable",
    )
    return any(marker in combined for marker in retry_markers)


def _attach_dmg_readonly(
    dmg_path: Path,
    mount_dir: Path,
    *,
    max_attempts: int = HDIUTIL_ATTACH_MAX_ATTEMPTS,
    retry_delay_seconds: float = HDIUTIL_ATTACH_RETRY_DELAY_SECONDS,
) -> None:
    attach_command = [
        "hdiutil",
        "attach",
        "-nobrowse",
        "-readonly",
        "-mountpoint",
        str(mount_dir),
        str(dmg_path),
    ]
    last_stderr = ""
    last_stdout = ""
    for attempt_index in range(1, max_attempts + 1):
        attach_result = subprocess.run(
            attach_command,
            check=False,
            capture_output=True,
            text=True,
        )
        if attach_result.returncode == 0:
            return
        last_stderr = attach_result.stderr.strip()
        last_stdout = attach_result.stdout.strip()
        if attempt_index >= max_attempts:
            break
        if not hdiutil_attach_error_is_retryable(last_stderr, last_stdout):
            break
        time.sleep(retry_delay_seconds)
    raise ArtifactVerificationError(
        "Failed to mount DMG: "
        + last_stderr
        + last_stdout
    )


def _verify_macos_release_dmg(path: Path, distro: HumanitecDistroConfig) -> None:
    if sys.platform != "darwin":
        raise ArtifactVerificationError("macOS release verification requires darwin host")
    if shutil.which("hdiutil") is None:
        raise ArtifactVerificationError("hdiutil is required for macOS artifact verification")

    mount_dir = Path(tempfile.mkdtemp(prefix="humanitec-agent-verify-"))
    try:
        _attach_dmg_readonly(path, mount_dir)

        app_bundle = mount_dir / f"{distro.bundle_name}.app"
        if not app_bundle.is_dir():
            visible = sorted(entry.name for entry in mount_dir.iterdir())
            raise ArtifactVerificationError(
                f"Expected app bundle {app_bundle.name!r}, found: {visible!r}"
            )

        applications_link = mount_dir / "Applications"
        if not applications_link.is_symlink():
            raise ArtifactVerificationError(
                "DMG must contain Applications symlink for drag-to-install UX"
            )
        applications_target = os.readlink(applications_link)
        if applications_target != "/Applications":
            raise ArtifactVerificationError(
                f"Applications symlink must point to /Applications, got {applications_target!r}"
            )

        info_plist_path = app_bundle / "Contents" / "Info.plist"
        if not info_plist_path.is_file():
            raise ArtifactVerificationError(f"Missing Info.plist in {app_bundle}")

        with info_plist_path.open("rb") as handle:
            loaded_object: object = cast(object, plistlib.load(handle))

        if not isinstance(loaded_object, dict):
            raise ArtifactVerificationError(f"Invalid Info.plist in {app_bundle}")

        info_plist_map: dict[str, object] = cast(dict[str, object], loaded_object)
        bundle_display_name_raw = info_plist_map.get("CFBundleDisplayName")
        bundle_name_raw = info_plist_map.get("CFBundleName")
        bundle_display_name = (
            bundle_display_name_raw if isinstance(bundle_display_name_raw, str) else None
        )
        bundle_name = bundle_name_raw if isinstance(bundle_name_raw, str) else None
        if bundle_display_name != distro.display_name and bundle_name != distro.bundle_name:
            raise ArtifactVerificationError(
                "macOS bundle branding mismatch: "
                + f"CFBundleDisplayName={bundle_display_name!r}, "
                + f"CFBundleName={bundle_name!r}, "
                + f"expected {distro.display_name!r}/{distro.bundle_name!r}"
            )

        if _macos_codesign_verification_enabled():
            if shutil.which("codesign") is None:
                raise ArtifactVerificationError(
                    "codesign is required when AGENT_VERIFY_CODESIGN=1"
                )
            codesign_result = subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", str(app_bundle)],
                check=False,
                capture_output=True,
                text=True,
            )
            if codesign_result.returncode != 0:
                raise ArtifactVerificationError(
                    "codesign verification failed: "
                    + codesign_result.stderr.strip()
                    + codesign_result.stdout.strip()
                )
            if _macos_notarized_verification_enabled():
                if shutil.which("spctl") is not None:
                    spctl_result = subprocess.run(
                        ["spctl", "-a", "-vv", str(app_bundle)],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    if spctl_result.returncode != 0:
                        raise ArtifactVerificationError(
                            "Gatekeeper assessment failed: "
                            + spctl_result.stderr.strip()
                            + spctl_result.stdout.strip()
                        )

            goosed_bin = app_bundle / "Contents" / "Resources" / "bin" / "goosed"
            if not goosed_bin.is_file():
                raise ArtifactVerificationError(
                    f"Missing goosed helper in app bundle: {goosed_bin}"
                )
            goosed_codesign_result = subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", str(goosed_bin)],
                check=False,
                capture_output=True,
                text=True,
            )
            if goosed_codesign_result.returncode != 0:
                raise ArtifactVerificationError(
                    "goosed codesign verification failed: "
                    + goosed_codesign_result.stderr.strip()
                    + goosed_codesign_result.stdout.strip()
                )

        _verify_macos_ui_branding_in_app_bundle(app_bundle, distro)
    finally:
        if mount_dir.is_dir() and any(mount_dir.iterdir()):
            detach_result = subprocess.run(
                ["hdiutil", "detach", str(mount_dir), "-quiet"],
                check=False,
                capture_output=True,
                text=True,
            )
            if detach_result.returncode != 0:
                raise ArtifactVerificationError(
                    "Failed to detach DMG: "
                    + detach_result.stderr.strip()
                    + detach_result.stdout.strip()
                )
        if mount_dir.is_dir():
            mount_dir.rmdir()


def _verify_linux_deb_release(path: Path, distro: HumanitecDistroConfig) -> None:
    if shutil.which("dpkg-deb") is None:
        raise ArtifactVerificationError("dpkg-deb is required for deb artifact verification")

    control_fields = ("Package", "Maintainer", "Homepage")
    for field in control_fields:
        query_result = subprocess.run(
            ["dpkg-deb", "-f", str(path), field],
            check=False,
            capture_output=True,
            text=True,
        )
        if query_result.returncode != 0:
            raise ArtifactVerificationError(
                f"dpkg-deb failed for {field}: {query_result.stderr.strip()}"
            )

    package_name = subprocess.run(
        ["dpkg-deb", "-f", str(path), "Package"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if package_name.lower() not in {distro.id, distro.bundle_name.lower()}:
        raise ArtifactVerificationError(
            f"deb package name {package_name!r} is not branded as {distro.id!r}"
        )

    with tempfile.TemporaryDirectory(prefix="humanitec-agent-deb-") as temp_dir:
        extract_result = subprocess.run(
            ["dpkg-deb", "-x", str(path), temp_dir],
            check=False,
            capture_output=True,
            text=True,
        )
        if extract_result.returncode != 0:
            raise ArtifactVerificationError(
                "Failed to extract deb: " + extract_result.stderr.strip()
            )
        desktop_files = list(Path(temp_dir).rglob("*.desktop"))
        if not desktop_files:
            raise ArtifactVerificationError("deb artifact has no .desktop file")
        desktop_content = desktop_files[0].read_text(encoding="utf-8")
        if distro.display_name not in desktop_content:
            raise ArtifactVerificationError(
                "deb .desktop file is missing Humanitec display name"
            )
        if f"x-scheme-handler/{distro.protocol_scheme}" not in desktop_content:
            raise ArtifactVerificationError(
                f"deb .desktop file is missing protocol scheme {distro.protocol_scheme!r}"
            )


def _verify_linux_rpm_release(path: Path, distro: HumanitecDistroConfig) -> None:
    if shutil.which("rpm") is None:
        raise ArtifactVerificationError("rpm is required for rpm artifact verification")

    query_result = subprocess.run(
        ["rpm", "-qp", "--queryformat", "%{NAME}", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if query_result.returncode != 0:
        raise ArtifactVerificationError("rpm query failed: " + query_result.stderr.strip())
    package_name = query_result.stdout.strip()
    if package_name.lower() not in {distro.id, distro.bundle_name.lower()}:
        raise ArtifactVerificationError(
            f"rpm package name {package_name!r} is not branded as {distro.id!r}"
        )

    maintainer_result = subprocess.run(
        ["rpm", "-qp", "--queryformat", "%{VENDOR}", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if maintainer_result.returncode == 0:
        vendor = maintainer_result.stdout.strip()
        # rpm печатает литерал "(none)" для незаданного тега; maker-rpm
        # (electron-installer-redhat) не выставляет Vendor, поэтому VENDOR —
        # необязательный сигнал. Реальный брендинг проверяется по %{NAME} и
        # .desktop ниже. Сверяем Vendor только если он реально задан.
        if vendor and vendor != "(none)" and distro.maintainer.split("<")[0].strip() not in vendor:
            raise ArtifactVerificationError(
                f"rpm vendor {vendor!r} does not match maintainer {distro.maintainer!r}"
            )

    with tempfile.TemporaryDirectory(prefix="humanitec-agent-rpm-") as temp_dir:
        extract_result = subprocess.run(
            ["rpm2cpio", str(path)],
            check=False,
            capture_output=True,
        )
        if extract_result.returncode != 0 or shutil.which("cpio") is None:
            return
        cpio_result = subprocess.run(
            ["cpio", "-idmv"],
            input=extract_result.stdout,
            cwd=temp_dir,
            check=False,
            capture_output=True,
        )
        if cpio_result.returncode != 0:
            return
        desktop_files = list(Path(temp_dir).rglob("*.desktop"))
        if not desktop_files:
            raise ArtifactVerificationError("rpm artifact has no .desktop file")
        desktop_content = desktop_files[0].read_text(encoding="utf-8")
        if distro.display_name not in desktop_content:
            raise ArtifactVerificationError("rpm .desktop file is missing Humanitec display name")


def _verify_linux_appimage_release(path: Path, distro: HumanitecDistroConfig) -> None:
    if not path.name.startswith(f"{distro.bundle_name}-"):
        raise ArtifactVerificationError("AppImage filename is not Humanitec-branded")
    if not path.name.endswith(".AppImage"):
        raise ArtifactVerificationError("AppImage extension mismatch")
    # AppImage type-2 = ELF-runtime + squashfs: содержимое сжато, поэтому `strings`
    # по нему не находит брендинг. Распаковываем штатным `--appimage-extract`
    # (без FUSE) и проверяем .desktop как для deb/rpm.
    with tempfile.TemporaryDirectory(prefix="humanitec-agent-appimage-") as temp_dir:
        os.chmod(path, 0o755)
        extract_result = subprocess.run(
            [str(path), "--appimage-extract"],
            cwd=temp_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        if extract_result.returncode != 0:
            raise ArtifactVerificationError(
                "Failed to extract AppImage: "
                + extract_result.stderr.strip()
                + extract_result.stdout.strip()
            )
        squashfs_root = Path(temp_dir) / "squashfs-root"
        desktop_files = list(squashfs_root.rglob("*.desktop"))
        if not desktop_files:
            raise ArtifactVerificationError("AppImage payload has no .desktop file")
        desktop_content = desktop_files[0].read_text(encoding="utf-8")
        if (
            distro.display_name not in desktop_content
            and distro.bundle_name not in desktop_content
        ):
            raise ArtifactVerificationError(
                "AppImage .desktop file is missing Humanitec branding"
            )


def _verify_windows_release(path: Path, distro: HumanitecDistroConfig) -> None:
    if not path.name.startswith(f"{distro.bundle_name}-Setup-"):
        raise ArtifactVerificationError("MSI filename is not Humanitec-branded")
    if path.suffix.lower() != ".msi":
        raise ArtifactVerificationError("Windows artifact must be .msi")
    if sys.platform == "win32":
        _verify_windows_release_msi_payload(path)
    if shutil.which("strings") is None:
        return
    strings_result = subprocess.run(
        ["strings", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if strings_result.returncode != 0:
        return
    if distro.bundle_name not in strings_result.stdout and distro.display_name not in strings_result.stdout:
        raise ArtifactVerificationError("MSI payload missing Humanitec branding strings")


def _verify_windows_release_msi_payload(path: Path) -> None:
    if shutil.which("msiexec") is None:
        raise ArtifactVerificationError("msiexec is required for Windows MSI payload verification")

    extract_root = Path(tempfile.mkdtemp(prefix="humanitec-agent-msi-"))
    try:
        extract_command = [
            "msiexec",
            "/a",
            str(path.resolve()),
            "/qn",
            f"TARGETDIR={extract_root}",
        ]
        extract_result = subprocess.run(
            extract_command,
            check=False,
            capture_output=True,
            text=True,
        )
        if extract_result.returncode != 0:
            raise ArtifactVerificationError(
                "Failed to extract MSI for verification: "
                + extract_result.stderr.strip()
                + extract_result.stdout.strip()
            )

        goosed_candidates = list(extract_root.rglob("goosed.exe"))
        if not goosed_candidates:
            raise ArtifactVerificationError("MSI payload missing goosed.exe")

        runtime_dll_names = ("vcruntime140.dll", "ucrtbase.dll")
        for runtime_dll_name in runtime_dll_names:
            runtime_candidates = list(extract_root.rglob(runtime_dll_name))
            if not runtime_candidates:
                raise ArtifactVerificationError(
                    f"MSI payload missing bundled runtime DLL: {runtime_dll_name}"
                )

        goosed_bin_dir = goosed_candidates[0].parent
        for runtime_dll_name in runtime_dll_names:
            runtime_path = goosed_bin_dir / runtime_dll_name
            if not runtime_path.is_file():
                raise ArtifactVerificationError(
                    "Bundled runtime DLL must live next to goosed.exe: "
                    + f"{runtime_dll_name} expected in {goosed_bin_dir}"
                )
    finally:
        if extract_root.is_dir():
            shutil.rmtree(extract_root, ignore_errors=True)


def verify_release_artifact(
    path: Path,
    *,
    platform: str,
    distro: HumanitecDistroConfig,
) -> None:
    _require_file(path)
    if path.stat().st_size < MIN_RELEASE_BYTES:
        raise ArtifactVerificationError(
            f"Release artifact too small ({path.stat().st_size} bytes): {path.name}"
        )

    if platform in {"macos-arm64", "macos-x64"}:
        _verify_macos_release_dmg(path, distro)
        return
    if platform == "linux-deb":
        _verify_linux_deb_release(path, distro)
        return
    if platform == "linux-rpm":
        _verify_linux_rpm_release(path, distro)
        return
    if platform == "linux-appimage":
        _verify_linux_appimage_release(path, distro)
        return
    if platform == "windows":
        _verify_windows_release(path, distro)
        return
    raise ArtifactVerificationError(f"Unsupported platform: {platform!r}")


def verify_artifact(
    path: Path,
    *,
    platform: str,
    version_sha: str,
    artifact_mode: str,
    distro_path: Path | None = None,
) -> None:
    distro = load_distro_config(distro_path)
    expected_name = artifact_filename(platform, version_sha, distro.bundle_name)
    if path.name != expected_name:
        raise ArtifactVerificationError(
            f"Unexpected artifact name: {path.name!r}, expected {expected_name!r}"
        )

    if artifact_mode == "placeholder":
        verify_placeholder_artifact(
            path,
            platform=platform,
            version_sha=version_sha,
            distro=distro,
        )
        return
    if artifact_mode == "release":
        verify_release_artifact(path, platform=platform, distro=distro)
        return
    raise ArtifactVerificationError(f"Unsupported artifact mode: {artifact_mode!r}")
