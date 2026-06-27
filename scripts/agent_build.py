#!/usr/bin/env python3
"""
Сборка и публикация артефактов HumanitecAgent.

Единый entrypoint для make agent, make test, CI (humanitec-agent-build) и release.
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_ROOT = REPO_ROOT / "apps" / "agent" / "desktop"
BUILD_SCRIPT = DESKTOP_ROOT / "scripts" / "build.sh"
DIST_DIR = DESKTOP_ROOT / "dist"
VENDOR_DIR = DESKTOP_ROOT / "vendor" / "goose"
GITMODULES_PATH = REPO_ROOT / ".gitmodules"

sys.path.insert(0, str(REPO_ROOT))

from apps.agent.desktop.artifact_verify import (  # noqa: E402, I001
    MIN_RELEASE_BYTES,
    is_placeholder_artifact,
)
from apps.agent.desktop.build_contract import (  # noqa: E402, I001
    VALID_PLATFORMS,
    artifact_path as contract_artifact_path,
    asset_name_pattern,
    load_default_distro_config,
)


def _bash_script_path(script: Path) -> str:
    return script.resolve().as_posix()


def _build_shell_command(
    *,
    platform_name: str,
    artifact_mode: str,
    version_sha: str,
) -> list[str]:
    build_args = [
        "--platform",
        platform_name,
        "--artifact-mode",
        artifact_mode,
        "--version-sha",
        version_sha,
    ]
    if sys.platform == "win32":
        return ["bash", _bash_script_path(BUILD_SCRIPT), *build_args]
    return [str(BUILD_SCRIPT), *build_args]


def _run_build(
    *,
    platform_name: str,
    artifact_mode: str,
    version_sha: str,
) -> None:
    if platform_name not in VALID_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform_name!r}")
    if artifact_mode not in {"placeholder", "release"}:
        raise ValueError(f"Unsupported artifact mode: {artifact_mode!r}")
    if not BUILD_SCRIPT.is_file():
        raise FileNotFoundError(f"Build script missing: {BUILD_SCRIPT}")
    command = _build_shell_command(
        platform_name=platform_name,
        artifact_mode=artifact_mode,
        version_sha=version_sha,
    )
    print(f"agent-build: {' '.join(command)}", flush=True)
    _ = subprocess.run(command, check=True, cwd=str(REPO_ROOT))


def ensure_submodule() -> None:
    if not GITMODULES_PATH.is_file():
        print("agent-build: .gitmodules missing, skip submodule init", flush=True)
        return
    if VENDOR_DIR.is_dir() and any(VENDOR_DIR.iterdir()):
        print(f"agent-build: vendor present at {VENDOR_DIR}", flush=True)
        return
    print("agent-build: init submodule apps/agent/desktop/vendor/goose", flush=True)
    _ = subprocess.run(
        [
            "git",
            "submodule",
            "update",
            "--init",
            "apps/agent/desktop/vendor/goose",
        ],
        check=True,
        cwd=str(REPO_ROOT),
    )


def detect_host_platform() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "macos-arm64"
        return "macos-x64"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux-deb"
    raise RuntimeError(f"Unsupported host OS for HumanitecAgent build: {system}")


def artifact_ready(platform_name: str, version_sha: str, *, artifact_mode: str) -> bool:
    if artifact_mode not in {"placeholder", "release"}:
        raise ValueError(f"Unsupported artifact mode: {artifact_mode!r}")
    distro = load_default_distro_config()
    expected = contract_artifact_path(DIST_DIR, platform_name, version_sha, distro)
    if not expected.is_file():
        return False
    prefix = asset_name_pattern(platform_name, distro.bundle_name)
    if not expected.name.startswith(prefix):
        return False
    if artifact_mode == "placeholder":
        return is_placeholder_artifact(expected)
    if is_placeholder_artifact(expected):
        return False
    return expected.stat().st_size >= MIN_RELEASE_BYTES


def build_platform(*, platform_name: str, artifact_mode: str, version_sha: str) -> Path:
    ensure_submodule()
    distro = load_default_distro_config()
    expected = contract_artifact_path(DIST_DIR, platform_name, version_sha, distro)
    _run_build(platform_name=platform_name, artifact_mode=artifact_mode, version_sha=version_sha)
    if not expected.is_file():
        raise FileNotFoundError(f"Expected artifact missing after build: {expected}")
    return expected


def build_all(*, artifact_mode: str, version_sha: str) -> list[Path]:
    built: list[Path] = []
    for platform_name in VALID_PLATFORMS:
        built.append(
            build_platform(
                platform_name=platform_name,
                artifact_mode=artifact_mode,
                version_sha=version_sha,
            )
        )
    return built


def ensure_local(*, artifact_mode: str, version_sha: str) -> Path | None:
    host_platform = detect_host_platform()
    if artifact_ready(host_platform, version_sha, artifact_mode=artifact_mode):
        distro = load_default_distro_config()
        existing = contract_artifact_path(DIST_DIR, host_platform, version_sha, distro)
        print(f"agent-build: artifact already present: {existing}", flush=True)
        return existing
    return build_platform(
        platform_name=host_platform,
        artifact_mode=artifact_mode,
        version_sha=version_sha,
    )


def publish_release(*, release_tag: str, version_sha: str) -> None:
    distro = load_default_distro_config()
    missing: list[str] = []
    artifact_files: list[Path] = []
    for platform_name in VALID_PLATFORMS:
        path = contract_artifact_path(DIST_DIR, platform_name, version_sha, distro)
        if not path.is_file():
            missing.append(platform_name)
            continue
        artifact_files.append(path)
    if missing:
        raise FileNotFoundError(
            "Missing HumanitecAgent artifacts for platforms: "
            + ", ".join(missing)
            + f". Run: make agent-build-all AGENT_VERSION_SHA={version_sha}"
        )

    checksum_lines: list[str] = []
    for artifact_path in artifact_files:
        digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        checksum_lines.append(f"{digest}  {artifact_path.name}")
    checksums_path = DIST_DIR / "checksums.txt"
    checksums_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    artifact_files.append(checksums_path)

    gh_command = [
        "gh",
        "release",
        "view",
        release_tag,
        "--repo",
        _github_repo_slug(),
    ]
    view_result = subprocess.run(gh_command, cwd=str(REPO_ROOT), check=False)
    if view_result.returncode != 0:
        create_command = [
            "gh",
            "release",
            "create",
            release_tag,
            "--repo",
            _github_repo_slug(),
            "--title",
            f"HumanitecAgent {release_tag}",
            "--notes",
            f"HumanitecAgent build for commit {version_sha}",
        ]
        print(f"agent-build: {' '.join(create_command)}", flush=True)
        _ = subprocess.run(create_command, check=True, cwd=str(REPO_ROOT))

    upload_command = [
        "gh",
        "release",
        "upload",
        release_tag,
        "--repo",
        _github_repo_slug(),
        "--clobber",
        *[str(path) for path in artifact_files],
    ]
    print(f"agent-build: {' '.join(upload_command)}", flush=True)
    _ = subprocess.run(upload_command, check=True, cwd=str(REPO_ROOT))


def _github_repo_slug() -> str:
    remote_result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    remote_url = remote_result.stdout.strip()
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]
    if remote_url.startswith("git@"):
        _, path_part = remote_url.split(":", maxsplit=1)
        return path_part
    if "github.com/" in remote_url:
        return remote_url.split("github.com/", maxsplit=1)[1]
    raise ValueError(f"Cannot resolve GitHub repo slug from origin: {remote_url!r}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HumanitecAgent build orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure_parser = subparsers.add_parser(
        "ensure-local",
        help="Build host-platform artifact if missing",
    )
    ensure_parser.add_argument("--artifact-mode", default="placeholder")
    ensure_parser.add_argument("--version-sha", required=True)

    build_parser = subparsers.add_parser("build", help="Build one platform")
    build_parser.add_argument("--platform", required=True)
    build_parser.add_argument("--artifact-mode", default="placeholder")
    build_parser.add_argument("--version-sha", required=True)

    build_all_parser = subparsers.add_parser("build-all", help="Build all platforms")
    build_all_parser.add_argument("--artifact-mode", default="placeholder")
    build_all_parser.add_argument("--version-sha", required=True)

    publish_parser = subparsers.add_parser("publish-release", help="Upload dist to GitHub Release")
    publish_parser.add_argument("--tag", required=True)
    publish_parser.add_argument("--version-sha", required=True)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    command = str(args.command)
    if command == "ensure-local":
        _ = ensure_local(artifact_mode=str(args.artifact_mode), version_sha=str(args.version_sha))
        return 0
    if command == "build":
        _ = build_platform(
            platform_name=str(args.platform),
            artifact_mode=str(args.artifact_mode),
            version_sha=str(args.version_sha),
        )
        return 0
    if command == "build-all":
        _ = build_all(_artifact_mode=str(args.artifact_mode), version_sha=str(args.version_sha))
        return 0
    if command == "publish-release":
        publish_release(release_tag=str(args.tag), version_sha=str(args.version_sha))
        return 0
    raise ValueError(f"Unsupported command: {command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
