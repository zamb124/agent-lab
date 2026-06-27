"""Фикстуры для тестов Sync Service.

Использует платформенный паттерн: реальная БД, без моков.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from pathlib import Path

from tests.fixtures.test_database_env import TEST_DATABASE_ENV

for _k, _v in TEST_DATABASE_ENV.items():
    os.environ.setdefault(_k, _v)
os.environ.setdefault("S3__ENABLED", "true")
os.environ.setdefault("S3__DEFAULT_BUCKET", "test-bucket")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL", "http://localhost:19002")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__ACCESS_KEY_ID", "minioadmin")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__SECRET_ACCESS_KEY", "minioadmin")
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
os.environ.setdefault("CALLS__LIVEKIT_API_SECRET", "secret")

import core.config.base as _sync_test_config_base  # noqa: E402

_sync_test_config_base._settings_instance = None
from core.config import set_settings  # noqa: E402
from core.config.base import BaseSettings  # noqa: E402
from core.config.loader import load_merged_config  # noqa: E402

set_settings(BaseSettings(**load_merged_config(service_name="sync", silent=True)))

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

import apps.sync.db.models  # noqa: E402, F401 — регистрация моделей в Base.metadata
from apps.sync.db.base import SyncDatabase  # noqa: E402
from apps.sync.db.repositories.call_repository import CallRepository  # noqa: E402
from apps.sync.db.repositories.call_speech_egress_repository import (  # noqa: E402
    CallSpeechEgressTrackRepository,
)
from apps.sync.db.repositories.channel_repository import ChannelRepository  # noqa: E402
from apps.sync.db.repositories.file_repository import SyncFileRepository  # noqa: E402
from apps.sync.db.repositories.git_resource_ref_repository import (  # noqa: E402
    GitResourceRefRepository,
)
from apps.sync.db.repositories.meeting_repository import CallRecordingRepository  # noqa: E402
from apps.sync.db.repositories.message_repository import MessageRepository  # noqa: E402
from apps.sync.db.repositories.thread_repository import ThreadRepository  # noqa: E402
from core.models.identity_models import Company, Namespace, User  # noqa: E402
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
async def sync_database(sync_db_url: str) -> AsyncIterator[SyncDatabase]:
    """Создаёт SyncDatabase; схема только через Alembic (дерево migrations/sync)."""
    import core.config.base as config_base

    os.environ["DATABASE__SYNC_URL"] = sync_db_url
    config_base._settings_instance = None

    from apps.sync.container import reset_sync_container

    reset_sync_container()

    from core.db.migration_manifest import bootstrap_migration_registry
    from core.db.migrations import run_migrations_async

    bootstrap_migration_registry()
    await run_migrations_async(service="shared")
    await run_migrations_async(service="sync")

    db = SyncDatabase(sync_db_url)

    from apps.sync.container import get_sync_container
    from core.billing import set_billing_service

    container = get_sync_container()
    set_billing_service(container.billing_service)

    yield db


@pytest_asyncio.fixture()
async def sync_db_clean(sync_database: SyncDatabase) -> None:
    """No-op: тесты изолированы по company_id и уникальным entity ID (параллельный xdist)."""
    pass


@pytest.fixture()
def sync_user_id(unique_id: str) -> str:
    return f"sync_user_{unique_id}"


@pytest.fixture()
def sync_user2_id(unique_id: str) -> str:
    return f"sync_user2_{unique_id}"


@pytest_asyncio.fixture()
async def sync_auth_token(
    sync_database: SyncDatabase,
    company_id: str,
    sync_user_id: str,
    sync_user2_id: str,
) -> str:
    """JWT для уникальной компании и пользователя (shared БД)."""
    from apps.sync.container import get_sync_container

    container = get_sync_container()
    company = Company(
        company_id=company_id,
        name=f"Sync test {company_id}",
        owner_user_id=sync_user_id,
        members={sync_user_id: ["owner", "admin"], sync_user2_id: ["member"]},
        balance=1000.0,
    )
    await container.company_repository.set(company)
    user = User(
        user_id=sync_user_id,
        name="Sync test user",
        emails=[f"{sync_user_id}@test.local"],
        companies={company_id: ["owner", "admin"]},
        active_company_id=company_id,
    )
    await container.user_repository.set(user)
    user2 = User(
        user_id=sync_user2_id,
        name="Sync test user2",
        emails=[f"{sync_user2_id}@test.local"],
        companies={company_id: ["member"]},
        active_company_id=company_id,
    )
    await container.user_repository.set(user2)
    token_service = get_token_service()
    return token_service.create_token(sync_user_id, company_id=company_id)


@pytest_asyncio.fixture()
async def sync_auth_token_user2(
    sync_auth_token: str,
    company_id: str,
    sync_user2_id: str,
    sync_database: SyncDatabase,
) -> str:
    from apps.sync.container import get_sync_container

    get_sync_container()
    token_service = get_token_service()
    return token_service.create_token(sync_user2_id, company_id=company_id)


@pytest_asyncio.fixture()
async def sync_auth_headers(sync_auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sync_auth_token}"}


@pytest_asyncio.fixture()
async def sync_auth_headers_user2(sync_auth_token_user2: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sync_auth_token_user2}"}


@pytest_asyncio.fixture()
async def sync_ws_cookie(sync_auth_token: str, sync_user_id: str) -> dict[str, str]:
    return {"Cookie": f"auth_token={sync_auth_token}; session_id={sync_user_id}"}


@pytest.fixture()
def unique_id() -> str:
    """Уникальный ID для изоляции тестовых данных."""
    return uuid.uuid4().hex[:12]


@pytest.fixture()
def company_id(unique_id: str) -> str:
    """company_id для изоляции тестов."""
    return f"test_company_{unique_id}"


@pytest_asyncio.fixture()
async def sync_namespace(sync_auth_token: str, company_id: str, unique_id: str) -> str:
    """Создаёт уникальный namespace в shared `NamespaceRepository` и возвращает его имя.

    Sync-каналы привязываются к платформенному namespace (1:1); тесты,
    создающие topic-канал, должны использовать это имя напрямую.
    """
    from apps.sync.container import get_sync_container

    container = get_sync_container()
    name = f"ns_{unique_id}"
    await container.namespace_repository.set(
        Namespace(
            name=name,
            company_id=company_id,
            description=f"sync test namespace {unique_id}",
            is_default=False,
        )
    )
    return name


@pytest.fixture()
def channel_repo(sync_database: SyncDatabase) -> ChannelRepository:
    return ChannelRepository(db=sync_database)


@pytest.fixture()
def thread_repo(sync_database: SyncDatabase) -> ThreadRepository:
    return ThreadRepository(db=sync_database)


@pytest.fixture()
def message_repo(sync_database: SyncDatabase) -> MessageRepository:
    return MessageRepository(db=sync_database)


@pytest.fixture()
def file_repo(sync_database: SyncDatabase) -> SyncFileRepository:
    return SyncFileRepository(db=sync_database)


@pytest.fixture()
def git_ref_repo(sync_database: SyncDatabase) -> GitResourceRefRepository:
    return GitResourceRefRepository(db=sync_database)


@pytest.fixture()
def call_repo(sync_database: SyncDatabase) -> CallRepository:
    return CallRepository(db=sync_database)


@pytest.fixture()
def call_recording_repo(sync_database: SyncDatabase) -> CallRecordingRepository:
    return CallRecordingRepository(db=sync_database)


@pytest.fixture()
def speech_egress_repo(sync_database: SyncDatabase) -> CallSpeechEgressTrackRepository:
    return CallSpeechEgressTrackRepository(db=sync_database)


@pytest.fixture()
def sync_user_repository(sync_database: SyncDatabase):
    """UserRepository shared БД (тот же экземпляр, что использует op_*)."""
    from apps.sync.container import get_sync_container

    return get_sync_container().user_repository


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
            "devkey",
            "--api-secret",
            "secret",
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
