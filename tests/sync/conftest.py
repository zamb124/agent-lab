"""Фикстуры для тестов Sync Service.

Использует платформенный паттерн: реальная БД, без моков.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from pathlib import Path

from tests.fixtures.auth import set_test_company_member_roles
from tests.fixtures.test_database_env import TEST_DATABASE_ENV, TEST_LIVEKIT_API_SECRET

for _k, _v in TEST_DATABASE_ENV.items():
    os.environ.setdefault(_k, _v)
os.environ.setdefault("S3__ENABLED", "true")
os.environ.setdefault("S3__DEFAULT_BUCKET", "test-bucket")
os.environ.setdefault("S3__ENDPOINT_URL", "http://localhost:19002")
os.environ.setdefault("S3__ACCESS_KEY_ID", "minioadmin")
os.environ.setdefault("S3__SECRET_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3__BUCKET_NAME", "test-bucket")
os.environ.setdefault("S3__PROVIDER", "minio")

_SYNC_DI = None
os.environ.setdefault("VOICE__STT__PROVIDER", "mock")
os.environ.setdefault(
    "VOICE__STT__MOCK_TRANSCRIPT_TEXT",
    "Тестовая транскрипция sync worker",
)
os.environ.setdefault("CALLS__SPEECH_TO_CHAT__SEGMENT_SECONDS", "2")
os.environ.setdefault("CALLS__SPEECH_TO_CHAT__POLL_INITIAL_DELAY_SECONDS", "0.5")
os.environ.setdefault("CALLS__SPEECH_TO_CHAT__POLL_INTERVAL_SECONDS", "1")
os.environ.setdefault("CALLS__LIVEKIT_URL", "ws://localhost:7890")
os.environ.setdefault("CALLS__LIVEKIT_PUBLIC_URL", "http://localhost:7890")
os.environ.setdefault("CALLS__LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("CALLS__LIVEKIT_API_SECRET", "platform-test-livekit-secret-32b!")

import core.config.base as _sync_test_config_base  # noqa: E402

_sync_test_config_base._settings_instance = None
from core.config import set_settings  # noqa: E402
from core.config.base import BaseSettings  # noqa: E402
from core.config.loader import load_merged_config  # noqa: E402

set_settings(BaseSettings(**load_merged_config(service_name="sync", silent=True)))

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from apps.sync import models as _sync_models  # noqa: E402, F401
from core.models.identity_models import Company, User  # noqa: E402
from core.utils.tokens import get_token_service  # noqa: E402

_SYNC_REPO_ROOT = Path(__file__).resolve().parents[2]


def _livekit_cli_test_container_running() -> bool:
    inspect = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "agentlab_livekit_cli_test"],
        capture_output=True,
        text=True,
        check=False,
    )
    return inspect.returncode == 0 and inspect.stdout.strip() == "true"


@pytest.fixture(scope="session")
def livekit_cli_test_container() -> None:
    """Поднимает контейнер lk cli до тестов; иначе docker-compose внутри тела теста съедает лимит timeout."""
    if _livekit_cli_test_container_running():
        yield
        return
    compose = _SYNC_REPO_ROOT / "docker-compose-test.yaml"
    r = subprocess.run(
        [
            "docker-compose",
            "-f",
            str(compose),
            "up",
            "-d",
            "--pull",
            "never",
            "livekit-cli-test",
        ],
        cwd=str(_SYNC_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"docker-compose up livekit-cli-test failed:\n{r.stdout}\n{r.stderr}")
    yield


def _get_sync_test_db_url() -> str:
    """URL тестовой БД sync. Берётся из ENV или дефолт."""
    return os.environ.get("DATABASE__SYNC_URL", TEST_DATABASE_ENV["DATABASE__SYNC_URL"])


@pytest.fixture(scope="session")
def sync_db_url() -> str:
    return _get_sync_test_db_url()


@pytest_asyncio.fixture(scope="session")
async def sync_database(sync_db_url: str) -> AsyncIterator[None]:
    """Поднимает пулы Oxyde. Схема применяется заранее в make test-up.

    Фикстура ничего не мигрирует: параллельные xdist-воркеры не должны конкурировать
    за Alembic. Актуальность head проверяет session-фикстура setup_database_before_tests.
    """
    import core.config.base as config_base

    os.environ["DATABASE__SYNC_URL"] = sync_db_url
    config_base._settings_instance = None

    from apps.sync.di import SyncDi
    from core.billing import set_billing_service
    from core.config import get_settings
    from core.di import open_di
    from core.di.kit import ProcessIdentity
    from core.files.urls import resolve_files_route_segment

    settings = get_settings()
    shared_url = settings.database.shared_url
    if shared_url is None or shared_url == "":
        raise ValueError("database.shared_url is not set")

    async with open_di(
        SyncDi,
        settings=settings,
        identity=ProcessIdentity(
            service_name="sync",
            files_route_segment=resolve_files_route_segment("sync"),
        ),
        database="sync_url",
    ) as di:
        set_billing_service(di.billing_service)
        global _SYNC_DI
        _SYNC_DI = di
        yield
        _SYNC_DI = None


def require_sync_di():
    from apps.sync.di import SyncDi

    di = _SYNC_DI
    if not isinstance(di, SyncDi):
        raise RuntimeError("Sync DI is not open")
    return di


@pytest.fixture()
def sync_di(sync_database: None):
    _ = sync_database
    return require_sync_di()


@pytest_asyncio.fixture()
async def sync_db_clean(sync_database: None) -> None:
    """No-op: тесты изолированы по company_id и уникальным entity ID (параллельный xdist)."""
    _ = sync_database


@pytest.fixture()
def sync_user_id(unique_id: str) -> str:
    return f"sync_user_{unique_id}"


@pytest.fixture()
def sync_user2_id(unique_id: str) -> str:
    return f"sync_user2_{unique_id}"


@pytest_asyncio.fixture()
async def sync_auth_token(
    sync_database: None,
    company_id: str,
    sync_user_id: str,
    sync_user2_id: str,
) -> str:
    """JWT для уникальной компании и пользователя (shared БД)."""
    _ = sync_database
    di = require_sync_di()
    company = Company(
        company_id=company_id,
        name=f"Sync test {company_id}",
        owner_user_id=sync_user_id,
        members={sync_user_id: ["owner", "admin"], sync_user2_id: ["member"]},
        balance=1000.0,
    )
    await Company.set(company)
    for member_user_id, roles in company.members.items():
        await set_test_company_member_roles(
            di.authz_service,
            company_id=company_id,
            user_id=member_user_id,
            roles=roles,
        )
    user = User(
        user_id=sync_user_id,
        name="Sync test user",
        emails=[f"{sync_user_id}@test.local"],
        companies={company_id: ["owner", "admin"]},
        active_company_id=company_id,
    )
    await User.set(user)
    user2 = User(
        user_id=sync_user2_id,
        name="Sync test user2",
        emails=[f"{sync_user2_id}@test.local"],
        companies={company_id: ["member"]},
        active_company_id=company_id,
    )
    await User.set(user2)
    token_service = get_token_service()
    return token_service.create_token(sync_user_id, company_id=company_id)


@pytest_asyncio.fixture()
async def sync_auth_token_user2(
    sync_auth_token: str,
    company_id: str,
    sync_user2_id: str,
    sync_database: None,
) -> str:
    _ = sync_database
    token_service = get_token_service()
    return token_service.create_token(sync_user2_id, company_id=company_id)


@pytest_asyncio.fixture()
async def sync_auth_headers(sync_auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sync_auth_token}"}


@pytest_asyncio.fixture()
async def sync_auth_headers_user2(sync_auth_token_user2: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sync_auth_token_user2}"}


@pytest.fixture()
def unique_id() -> str:
    """Уникальный ID для изоляции тестовых данных."""
    return uuid.uuid4().hex[:12]


@pytest.fixture()
def company_id(unique_id: str) -> str:
    """company_id для изоляции тестов."""
    return f"test_company_{unique_id}"



@pytest.fixture()
def sync_user_repository(sync_database: None) -> None:
    """Shared БД для записей User в sync-тестах."""
    _ = sync_database


@pytest_asyncio.fixture()
async def livekit_demo_publisher(livekit_cli_test_container):
    """Публикует тестовый Opus-трек в комнату LiveKit через lk (`tests/fixtures/sync/speech_demo.ogg`)."""
    processes: list[asyncio.subprocess.Process] = []

    async def _start(
        *,
        room_name: str,
        settle_seconds: float = 3.0,
        identity: str | None = None,
    ) -> str:
        if room_name == "":
            raise ValueError("room_name обязателен для demo publisher.")
        pub_identity = (
            identity
            if isinstance(identity, str) and identity.strip() != ""
            else f"test-publisher-{uuid.uuid4().hex[:8]}"
        )
        audio_fixture = _SYNC_REPO_ROOT / "tests/fixtures/sync/speech_demo.ogg"
        if not audio_fixture.is_file():
            raise RuntimeError(
                "Для speech-to-chat e2e нужен Opus-файл: tests/fixtures/sync/speech_demo.ogg"
            )
        cp = subprocess.run(
            [
                "docker",
                "cp",
                str(audio_fixture),
                "agentlab_livekit_cli_test:/tmp/speech_demo.ogg",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if cp.returncode != 0:
            raise RuntimeError(
                f"docker cp speech_demo.ogg в livekit-cli-test не удался:\n{cp.stdout}\n{cp.stderr}"
            )
        command = [
            "docker",
            "exec",
            "agentlab_livekit_cli_test",
            "/lk",
            "room",
            "join",
            "--url",
            "ws://livekit-test:7880",
            "--api-key",
            TEST_DATABASE_ENV["CALLS__LIVEKIT_API_KEY"],
            "--api-secret",
            TEST_LIVEKIT_API_SECRET,
            "--identity",
            pub_identity,
            "--publish",
            "/tmp/speech_demo.ogg",
            room_name,
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        processes.append(process)
        await asyncio.sleep(settle_seconds)
        if process.returncode is not None:
            output = ""
            if process.stdout is not None:
                output_bytes = await process.stdout.read()
                output = output_bytes.decode("utf-8", errors="replace")
            raise RuntimeError(
                "Demo publisher завершился до старта egress. "
                f"room={room_name}, returncode={process.returncode}, output={output}"
            )
        return pub_identity

    yield _start

    for process in processes:
        if process.returncode is not None:
            continue
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
