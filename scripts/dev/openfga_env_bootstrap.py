#!/usr/bin/env python3
"""Bootstrap OpenFGA store+model → OPENFGA__* env file (local/dev и pytest).

Идемпотентно: при существующем OPENFGA__STORE_ID в env-файле — reuse store, rewrite model.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path
from typing import cast

import httpx2

from core.authz.bootstrap import bootstrap_openfga
from core.authz.errors import AuthzUnavailable

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEV_API_URL = "http://127.0.0.1:9090"
DEFAULT_TEST_API_URL = "http://127.0.0.1:9093"
DEV_ENV_PATH = _ROOT / "reports" / "openfga-dev.env"
TEST_ENV_PATH = _ROOT / "reports" / "openfga-test.env"


async def wait_healthy(api_url: str, *, timeout_sec: float) -> None:
    health_url = f"{api_url.rstrip('/')}/healthz"
    deadline = time.monotonic() + timeout_sec
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            async with httpx2.AsyncClient(timeout=2.0) as client:
                response = await client.get(health_url)
                if response.status_code == 200:
                    return
                last_error = f"status={response.status_code}"
        except (httpx2.HTTPError, OSError) as exc:
            last_error = str(exc)
        await asyncio.sleep(0.5)
    raise AuthzUnavailable(
        f"OpenFGA not healthy at {health_url} within {timeout_sec}s: {last_error}"
    )


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"missing OpenFGA env: {path}")
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        result[key] = value
    return result


def write_env_file(
    api_url: str,
    store_id: str,
    model_id: str,
    path: Path,
    *,
    api_token: str = "",
) -> None:
    _ = path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        "\n".join(
            [
                "OPENFGA__ENABLED=true",
                f"OPENFGA__API_URL={api_url}",
                f"OPENFGA__STORE_ID={store_id}",
                f"OPENFGA__AUTHORIZATION_MODEL_ID={model_id}",
                f"OPENFGA__API_TOKEN={api_token}",
                "OPENFGA__TIMEOUT_MS=30000",
                "OPENFGA__DEFAULT_CONSISTENCY=MINIMIZE_LATENCY",
                "",
            ]
        ),
        encoding="utf-8",
    )


def apply_env_file_to_environ(path: Path) -> dict[str, str]:
    """Загружает OPENFGA__* из файла в os.environ (не перезаписывает уже заданные)."""
    env = load_env_file(path)
    for key, value in env.items():
        if not key.startswith("OPENFGA__"):
            continue
        if key in os.environ and os.environ[key] != "":
            continue
        os.environ[key] = value
    return env


def require_dev_openfga_env(path: Path = DEV_ENV_PATH) -> dict[str, str]:
    """Fail-fast для make app: нужен reports/openfga-dev.env после make dev-up."""
    if not path.is_file():
        raise SystemExit(
            f"OpenFGA env missing: {path}\n"
            + "Run `make dev-up` (starts openfga and bootstraps store/model)."
        )
    env = apply_env_file_to_environ(path)
    store_id = env.get("OPENFGA__STORE_ID", "").strip()
    model_id = env.get("OPENFGA__AUTHORIZATION_MODEL_ID", "").strip()
    if not store_id or not model_id:
        raise SystemExit(
            f"OpenFGA env incomplete in {path} (need STORE_ID and AUTHORIZATION_MODEL_ID).\n"
            + "Run `make dev-up` again."
        )
    return env


async def run(
    *,
    api_url: str,
    timeout_sec: float,
    env_path: Path,
    api_token: str | None,
) -> tuple[str, str]:
    await wait_healthy(api_url, timeout_sec=timeout_sec)
    reuse_store_id: str | None = None
    if env_path.is_file():
        existing = load_env_file(env_path)
        candidate = existing.get("OPENFGA__STORE_ID", "").strip()
        if candidate:
            reuse_store_id = candidate
    return await bootstrap_openfga(
        api_url=api_url,
        api_token=api_token,
        store_id=reuse_store_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap OpenFGA → OPENFGA__* env file")
    _ = parser.add_argument(
        "--api-url",
        default=os.environ.get("OPENFGA__API_URL", DEFAULT_DEV_API_URL),
    )
    _ = parser.add_argument("--timeout-sec", type=float, default=60.0)
    _ = parser.add_argument("--env-path", type=Path, default=DEV_ENV_PATH)
    _ = parser.add_argument(
        "--api-token",
        default=os.environ.get("OPENFGA__API_TOKEN") or os.environ.get("OPENFGA_API_TOKEN"),
    )
    args = parser.parse_args(argv)
    api_url = cast(str, args.api_url)
    timeout_sec = cast(float, args.timeout_sec)
    env_path = cast(Path, args.env_path)
    raw_token = cast(str | None, args.api_token)
    api_token = raw_token.strip() if raw_token else None
    if api_token == "":
        api_token = None
    store_id, model_id = asyncio.run(
        run(
            api_url=api_url,
            timeout_sec=timeout_sec,
            env_path=env_path,
            api_token=api_token,
        )
    )
    write_env_file(
        api_url,
        store_id,
        model_id,
        env_path,
        api_token=api_token if api_token is not None else "",
    )
    print(f"wrote {env_path}")
    print(f"store_id={store_id}")
    print(f"authorization_model_id={model_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
