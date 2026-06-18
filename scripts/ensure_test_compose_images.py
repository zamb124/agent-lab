#!/usr/bin/env python3
"""
Pull-or-build test compose images from GHCR before docker-compose-test up.

Пишет .env.test-compose-images для подстановки в docker-compose-test.yaml.
Перед pull требует GHCR auth: gh auth login + docker login (если ещё не залогинен).
При отсутствии образа в registry — локальная сборка; push только при TEST_IMAGES_PUSH=1.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env.test-compose-images"
DEFAULT_REGISTRY = "ghcr.io/zamb124"
DOCKER_PLATFORM = "linux/amd64"


@dataclass(frozen=True)
class ImageSpec:
    env_key: str
    repository_suffix: str
    tag: str
    dockerfile: Path
    target: str
    build_args: dict[str, str]


def _run(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        check=check,
        text=True,
        capture_output=capture,
    )


def _content_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _git_short_sha() -> str:
    result = _run(["git", "rev-parse", "--short", "HEAD"], capture=True)
    return result.stdout.strip()


def _git_is_dirty() -> bool:
    result = _run(["git", "status", "--porcelain"], capture=True)
    return bool(result.stdout.strip())


def _registry() -> str:
    value = os.environ.get("TEST_IMAGE_REGISTRY", "").strip()
    if value:
        return value.rstrip("/")
    return DEFAULT_REGISTRY


def _registry_host(registry: str) -> str:
    host = registry.split("/", maxsplit=1)[0].strip()
    if not host:
        raise ValueError(f"Invalid TEST_IMAGE_REGISTRY: {registry!r}")
    return host


def _skip_ghcr_auth_check() -> bool:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return True
    return os.environ.get("TEST_IMAGES_SKIP_GHCR_AUTH", "").strip() == "1"


def _gh_executable() -> str:
    gh_path = shutil.which("gh")
    if not gh_path:
        raise RuntimeError(
            "GitHub CLI (gh) не установлен. Установите gh (https://cli.github.com/) и повторите make test-up."
        )
    return gh_path


def _gh_auth_status_ok(gh_path: str) -> bool:
    result = subprocess.run(
        [gh_path, "auth", "status"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    return result.returncode == 0


def _gh_auth_status_text(gh_path: str) -> str:
    result = _run([gh_path, "auth", "status"], capture=True, check=False)
    return f"{result.stdout}\n{result.stderr}"


def _gh_has_read_packages_scope(gh_path: str) -> bool:
    return "read:packages" in _gh_auth_status_text(gh_path)


def _gh_ensure_read_packages_scope(gh_path: str) -> None:
    if _gh_has_read_packages_scope(gh_path):
        return
    print("[ensure] Токен gh без scope read:packages — нужен для pull образов из GHCR.")
    refresh_result = subprocess.run(
        [gh_path, "auth", "refresh", "-s", "read:packages"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if refresh_result.returncode != 0:
        print("[ensure] gh auth refresh не удался, запуск gh auth login -s read:packages...")
        _gh_auth_login_interactive(gh_path)
    if not _gh_has_read_packages_scope(gh_path):
        raise RuntimeError(
            "Токен gh без read:packages. Выполните: gh auth refresh -s read:packages или gh auth login -s read:packages"
        )


def _gh_auth_login_interactive(gh_path: str) -> None:
    print("[ensure] Требуется вход в GitHub для pull образов из GHCR.")
    print("[ensure] Запуск gh auth login (scope read:packages)...")
    _ = subprocess.run(
        [gh_path, "auth", "login", "-s", "read:packages"],
        cwd=PROJECT_ROOT,
        check=True,
    )


def _docker_has_ghcr_credentials(registry_host: str) -> bool:
    config_path = Path.home() / ".docker" / "config.json"
    if not config_path.is_file():
        return False
    raw_text = config_path.read_text(encoding="utf-8")
    decoded = cast(object, json.loads(raw_text))
    if not isinstance(decoded, dict):
        return False
    config_root = cast(dict[str, object], decoded)
    cred_helpers_raw = config_root.get("credHelpers")
    if isinstance(cred_helpers_raw, dict) and registry_host in cred_helpers_raw:
        return True
    auths_raw = config_root.get("auths")
    if not isinstance(auths_raw, dict):
        return False
    auths = cast(dict[str, object], auths_raw)
    entry_raw = auths.get(registry_host)
    if not isinstance(entry_raw, dict):
        return False
    auth_entry = cast(dict[str, object], entry_raw)
    auth_value_raw = auth_entry.get("auth")
    return isinstance(auth_value_raw, str) and bool(auth_value_raw.strip())


def _docker_login_ghcr_from_gh(gh_path: str, registry_host: str) -> None:
    user_result = _run([gh_path, "api", "user", "-q", ".login"], capture=True)
    token_result = _run([gh_path, "auth", "token"], capture=True)
    github_user = user_result.stdout.strip()
    github_token = token_result.stdout.strip()
    if not github_user:
        raise RuntimeError("gh api user вернул пустой login")
    if not github_token:
        raise RuntimeError("gh auth token пустой; выполните gh auth login")
    print(f"[ensure] docker login {registry_host} (user {github_user})")
    login_result = subprocess.run(
        ["docker", "login", registry_host, "-u", github_user, "--password-stdin"],
        input=github_token,
        text=True,
        check=False,
        cwd=PROJECT_ROOT,
    )
    if login_result.returncode != 0:
        raise RuntimeError(
            f"docker login {registry_host} не удался. Проверьте gh auth login и право read:packages на ghcr.io."
        )


def _ghcr_registry_reachable(registry: str) -> bool:
    probe_ref = _image_ref(registry, "agent-lab-base", "latest")
    result = _run(
        ["docker", "manifest", "inspect", probe_ref],
        check=False,
        capture=True,
    )
    if result.returncode == 0:
        return True
    stderr = result.stderr.lower()
    if "unauthorized" in stderr or "denied" in stderr:
        return False
    probe_detail = result.stderr.strip() or result.stdout.strip()
    raise RuntimeError(
        f"GHCR probe {probe_ref} failed: {probe_detail}. Убедитесь, что workflow Build Base Image выполнен на main."
    )


def _ensure_ghcr_auth(registry: str) -> None:
    if _skip_ghcr_auth_check():
        return

    registry_host = _registry_host(registry)
    if _docker_has_ghcr_credentials(registry_host) and _ghcr_registry_reachable(registry):
        print(f"[ensure] GHCR auth OK ({registry})")
        return

    gh_path = _gh_executable()
    if not _gh_auth_status_ok(gh_path):
        _gh_auth_login_interactive(gh_path)
    if not _gh_auth_status_ok(gh_path):
        raise RuntimeError("gh auth login не завершился успешно")

    _gh_ensure_read_packages_scope(gh_path)
    _docker_login_ghcr_from_gh(gh_path, registry_host)

    if not _ghcr_registry_reachable(registry):
        raise RuntimeError(
            f"После docker login {registry} недоступен. Проверьте read:packages и доступ к пакетам ghcr.io/zamb124: gh auth refresh -s read:packages"
        )
    print(f"[ensure] GHCR auth OK ({registry})")


def _image_ref(registry: str, suffix: str, tag: str) -> str:
    return f"{registry}/{suffix}:{tag}"


def _manifest_exists(image_ref: str) -> bool:
    result = _run(
        ["docker", "manifest", "inspect", image_ref],
        check=False,
        capture=True,
    )
    return result.returncode == 0


def _docker_pull(image_ref: str) -> bool:
    result = _run(["docker", "pull", image_ref], check=False)
    return result.returncode == 0


def _docker_build(spec: ImageSpec, image_ref: str, registry: str) -> None:
    args = [
        "docker",
        "build",
        "--platform",
        DOCKER_PLATFORM,
        "-f",
        str(spec.dockerfile.relative_to(PROJECT_ROOT)),
        "-t",
        image_ref,
    ]
    for key, value in spec.build_args.items():
        args.extend(["--build-arg", f"{key}={value}"])
    if spec.target:
        args.extend(["--target", spec.target])
    cache_ref = _image_ref(registry, spec.repository_suffix, "latest")
    if _manifest_exists(cache_ref):
        args.extend(["--cache-from", cache_ref])
    args.append(".")
    _ = _run(args)


def _docker_push(image_ref: str) -> None:
    _ = _run(["docker", "push", image_ref])


def _can_push() -> bool:
    return os.environ.get("TEST_IMAGES_PUSH", "").strip() == "1"


def _pull_candidates(registry: str, spec: ImageSpec) -> list[str]:
    primary = _image_ref(registry, spec.repository_suffix, spec.tag)
    if spec.tag == "latest":
        return [primary]
    latest = _image_ref(registry, spec.repository_suffix, "latest")
    return [primary, latest]


def _try_pull_image(image_ref: str) -> bool:
    if not _manifest_exists(image_ref):
        return False
    print(f"[ensure] pull {image_ref}")
    return _docker_pull(image_ref)


def _ensure_image(spec: ImageSpec, registry: str, *, try_pull: bool) -> str:
    image_ref = _image_ref(registry, spec.repository_suffix, spec.tag)
    if try_pull:
        for candidate in _pull_candidates(registry, spec):
            if not _try_pull_image(candidate):
                continue
            if candidate != image_ref:
                print(f"[ensure] tag {candidate} -> {image_ref}")
                _run(["docker", "tag", candidate, image_ref])
            return image_ref
        print(f"[ensure] registry miss for {spec.repository_suffix}:{spec.tag}, building locally")

    print(f"[ensure] build {image_ref}")
    _docker_build(spec, image_ref, registry)
    if _can_push():
        print(f"[ensure] push {image_ref}")
        _docker_push(image_ref)
    return image_ref


def _write_env_file(values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    _ = ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ensure] wrote {ENV_FILE.relative_to(PROJECT_ROOT)}")


def main() -> int:
    registry = _registry()
    _ensure_ghcr_auth(registry)
    git_sha = _git_short_sha()
    dirty = _git_is_dirty()
    deps_hash = _content_hash(
        [
            PROJECT_ROOT / "pyproject.toml",
            PROJECT_ROOT / "uv.lock",
            PROJECT_ROOT / "Dockerfile.test.base",
        ]
    )
    a2a_paths = sorted((PROJECT_ROOT / "apps" / "test_a2a_sample").rglob("*"))
    a2a_files = [path for path in a2a_paths if path.is_file()]
    a2a_hash = _content_hash(a2a_files)

    test_base_ref = _image_ref(registry, "agent-lab-test-base", f"deps-{deps_hash}")
    agent_lab_base_ref = _image_ref(registry, "agent-lab-base", "latest")

    force_build = os.environ.get("TEST_IMAGES_FORCE_BUILD", "").strip() == "1"
    try_pull_code_images = not force_build

    if dirty:
        print(
            "[ensure] git tree dirty — GHCR pull first (pytest runs from host); "
            "set TEST_IMAGES_FORCE_BUILD=1 to force local docker build"
        )
    elif force_build:
        print("[ensure] TEST_IMAGES_FORCE_BUILD=1 — code images will be built locally")

    test_base_spec = ImageSpec(
        env_key="TEST_BASE_IMAGE",
        repository_suffix="agent-lab-test-base",
        tag=f"deps-{deps_hash}",
        dockerfile=PROJECT_ROOT / "Dockerfile.test.base",
        target="",
        build_args={"BASE_IMAGE": agent_lab_base_ref},
    )
    if not _manifest_exists(test_base_ref):
        if not _manifest_exists(agent_lab_base_ref):
            print(f"[ensure] pull {agent_lab_base_ref}")
            if not _docker_pull(agent_lab_base_ref):
                raise RuntimeError(
                    f"Cannot pull {agent_lab_base_ref}; run build-base workflow or set TEST_IMAGE_REGISTRY"
                )
    test_base_ref = _ensure_image(test_base_spec, registry, try_pull=True)

    agent_lab_spec = ImageSpec(
        env_key="AGENT_LAB_IMAGE",
        repository_suffix="agent-lab",
        tag=git_sha,
        dockerfile=PROJECT_ROOT / "Dockerfile",
        target="full",
        build_args={"BASE_IMAGE": agent_lab_base_ref},
    )
    test_runner_spec = ImageSpec(
        env_key="AGENT_LAB_TEST_IMAGE",
        repository_suffix="agent-lab-test",
        tag=git_sha,
        dockerfile=PROJECT_ROOT / "Dockerfile.test",
        target="default",
        build_args={"TEST_BASE_IMAGE": test_base_ref},
    )
    a2a_spec = ImageSpec(
        env_key="AGENT_LAB_TEST_A2A_IMAGE",
        repository_suffix="agent-lab-test-a2a",
        tag=a2a_hash,
        dockerfile=PROJECT_ROOT / "apps" / "test_a2a_sample" / "Dockerfile",
        target="",
        build_args={},
    )

    env_values = {
        "AGENT_LAB_IMAGE": _ensure_image(agent_lab_spec, registry, try_pull=try_pull_code_images),
        "AGENT_LAB_TEST_IMAGE": _ensure_image(test_runner_spec, registry, try_pull=try_pull_code_images),
        "AGENT_LAB_TEST_A2A_IMAGE": _ensure_image(a2a_spec, registry, try_pull=try_pull_code_images),
        "TEST_BASE_IMAGE": test_base_ref,
        "TEST_IMAGE_REGISTRY": registry,
    }
    _write_env_file(env_values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
