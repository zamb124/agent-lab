"""OpenFGA fixtures для pytest: реальный сервер из docker-compose-test.

Требует `make test-up` (postgres-test + openfga-test + bootstrap).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio

from core.authz import AuthzService
from core.authz.factory import build_authz_service
from core.config import get_settings, set_settings
from core.config.models import OpenFGAConfig
from scripts.testing.openfga_bootstrap import _ENV_PATH, load_env_file

_ROOT = Path(__file__).resolve().parents[2]


def _apply_openfga_env(env: dict[str, str]) -> None:
    for key, value in env.items():
        if key.startswith("OPENFGA__"):
            os.environ[key] = value


@pytest.fixture(scope="session")
def openfga_test_env() -> dict[str, str]:
    """Читает reports/openfga-test.env после make test-up bootstrap."""
    env_path = Path(os.environ.get("OPENFGA_TEST_ENV_PATH", str(_ENV_PATH)))
    if not env_path.is_file():
        pytest.skip(
            f"OpenFGA test env missing ({env_path}). Run `make test-up` "
            "(starts openfga-test and scripts/testing/openfga_bootstrap.py)."
        )
    env = load_env_file(env_path)
    required = (
        "OPENFGA__API_URL",
        "OPENFGA__STORE_ID",
        "OPENFGA__AUTHORIZATION_MODEL_ID",
    )
    for key in required:
        if not env.get(key):
            pytest.skip(f"OpenFGA test env incomplete: missing {key} in {env_path}")
    _apply_openfga_env(env)
    return env


@pytest.fixture(scope="session")
def openfga_settings(openfga_test_env: dict[str, str]) -> Iterator[OpenFGAConfig]:
    """Патчит get_settings().openfga на session; восстанавливает после."""
    original = get_settings()
    patched = original.model_copy(
        update={
            "openfga": OpenFGAConfig(
                enabled=True,
                api_url=openfga_test_env["OPENFGA__API_URL"],
                store_id=openfga_test_env["OPENFGA__STORE_ID"],
                authorization_model_id=openfga_test_env["OPENFGA__AUTHORIZATION_MODEL_ID"],
                api_token=openfga_test_env.get("OPENFGA__API_TOKEN") or None,
                timeout_ms=int(openfga_test_env.get("OPENFGA__TIMEOUT_MS") or "30000"),
            )
        }
    )
    set_settings(patched)
    try:
        yield patched.openfga
    finally:
        set_settings(original)


@pytest_asyncio.fixture
async def authz_service(openfga_settings: OpenFGAConfig) -> AsyncIterator[AuthzService]:
    """Свежий AuthzService на каждый тест (общий store, уникальные object id в кейсах)."""
    service = build_authz_service(openfga_settings)
    try:
        yield service
    finally:
        await service.close()
