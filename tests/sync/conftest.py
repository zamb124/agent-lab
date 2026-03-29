"""Фикстуры для тестов Sync Service.

Использует платформенный паттерн: реальная БД, без моков.
"""

from __future__ import annotations

import asyncio
import os
import uuid

from tests.fixtures.test_database_env import TEST_DATABASE_ENV

for _k, _v in TEST_DATABASE_ENV.items():
    os.environ.setdefault(_k, _v)
os.environ.setdefault("S3__ENABLED", "true")
os.environ.setdefault("S3__DEFAULT_BUCKET", "test-bucket")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL", "http://localhost:19002")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__ACCESS_KEY_ID", "minioadmin")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__SECRET_ACCESS_KEY", "minioadmin")
import uuid
from collections.abc import AsyncIterator
from typing import Callable

import pytest
import pytest_asyncio

from apps.sync.db.base import SyncDatabase
import apps.sync.db.models  # noqa: F401 — регистрация моделей в Base.metadata
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.file_repository import SyncFileRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.meeting_repository import CallMeetingRepository, CallRecordingRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from core.clients.stt_client import STTTranscriptionResult
from core.files.models import AudioTranscriptionStatus

from sqlalchemy import text


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
    await run_migrations_async(service="sync")

    db = SyncDatabase(sync_db_url)
    yield db


_SYNC_DELETE_ORDER = (
    # Дочерние таблицы первыми; без TRUNCATE — меньше AccessExclusiveLock и deadlock с xdist.
    "sync_call_links",
    "sync_call_speaker_segments",
    "sync_call_meetings",
    "sync_call_recordings",
    "sync_call_participants",
    "sync_calls",
    "sync_message_files",
    "sync_message_contents",
    "sync_messages",
    "sync_threads",
    "sync_git_resource_refs",
    "sync_files",
    "sync_channel_members",
    "sync_channels",
    "sync_spaces",
)


@pytest_asyncio.fixture()
async def sync_db_clean(sync_database: SyncDatabase) -> None:
    """Полная очистка данных sync перед тестом: DELETE по порядку FK (без TRUNCATE)."""
    async with sync_database.session() as session:
        for table in _SYNC_DELETE_ORDER:
            await session.execute(text(f'DELETE FROM "{table}"'))
        seq_row = await session.execute(
            text("SELECT pg_get_serial_sequence('sync_message_contents', 'id')")
        )
        seq_name = seq_row.scalar_one_or_none()
        if seq_name:
            await session.execute(text(f"SELECT setval('{seq_name}', 1, false)"))
        await session.commit()


@pytest.fixture()
def unique_id() -> str:
    """Уникальный ID для изоляции тестовых данных."""
    return uuid.uuid4().hex[:12]


@pytest.fixture()
def company_id(unique_id: str) -> str:
    """company_id для изоляции тестов."""
    return f"test_company_{unique_id}"


@pytest.fixture()
def space_repo(sync_database: SyncDatabase) -> SpaceRepository:
    return SpaceRepository(db=sync_database)


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
def call_meeting_repo(sync_database: SyncDatabase) -> CallMeetingRepository:
    return CallMeetingRepository(db=sync_database)


@pytest.fixture()
def sync_user_repository(sync_database: SyncDatabase):
    """UserRepository shared БД (как в dispatch_sync_command)."""
    from apps.sync.container import get_sync_container

    return get_sync_container().user_repository


@pytest_asyncio.fixture()
async def livekit_demo_publisher():
    """Запускает headless demo publisher в комнате LiveKit через livekit-cli контейнер."""
    processes: list[asyncio.subprocess.Process] = []

    async def _ensure_cli_container_running() -> None:
        compose_up = await asyncio.create_subprocess_exec(
            "docker-compose",
            "-f",
            "docker-compose-test.yaml",
            "up",
            "-d",
            "livekit-cli-test",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        compose_output, _ = await compose_up.communicate()
        if compose_up.returncode != 0:
            raise RuntimeError(
                "Не удалось поднять livekit-cli-test контейнер: "
                f"{compose_output.decode('utf-8', errors='replace')}"
            )

    async def _start(*, room_name: str, settle_seconds: float = 3.0) -> str:
        if room_name == "":
            raise ValueError("room_name обязателен для demo publisher.")
        await _ensure_cli_container_running()
        identity = f"test-publisher-{uuid.uuid4().hex[:8]}"
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
            identity,
            "--publish-demo",
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
        return identity

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


@pytest.fixture()
def mock_sync_recording_source(monkeypatch) -> Callable[[bytes, str], None]:
    """Подменяет скачивание raw-записи в sync pipeline тестовым содержимым."""
    from apps.sync.realtime import tasks as sync_tasks

    def _apply(audio_bytes: bytes = b"fake-audio-bytes", content_type: str = "audio/wav") -> None:
        async def _stubbed_download(*, source_url: str, timeout_seconds: float) -> tuple[bytes, str]:
            return audio_bytes, content_type

        monkeypatch.setattr(sync_tasks, "_download_recording_bytes", _stubbed_download)

    return _apply


@pytest.fixture()
def mock_sync_stt_client(monkeypatch) -> Callable[[str], object]:
    """Подменяет STTClientFactory в sync pipeline и возвращает объект-клиент для проверок."""
    from apps.sync.realtime import tasks as sync_tasks

    class _MockSTTClient:
        def __init__(self, transcript_text: str) -> None:
            self._transcript_text = transcript_text
            self.calls: list[dict[str, str]] = []

        async def transcribe_audio(
            self,
            *,
            audio_bytes: bytes,
            file_name: str,
            mime_type: str,
            language: str | None = None,
        ) -> STTTranscriptionResult:
            self.calls.append(
                {
                    "file_name": file_name,
                    "mime_type": mime_type,
                    "language": language or "",
                    "size": str(len(audio_bytes)),
                }
            )
            return STTTranscriptionResult(
                provider="mock",
                status=AudioTranscriptionStatus.DONE,
                text=self._transcript_text,
                language=language,
            )

    def _apply(transcript_text: str) -> _MockSTTClient:
        client = _MockSTTClient(transcript_text=transcript_text)
        monkeypatch.setattr(sync_tasks.STTClientFactory, "create_client", staticmethod(lambda: client))
        return client

    return _apply


@pytest.fixture()
def mock_sync_egress_result(monkeypatch) -> Callable[[str, str], None]:
    """Подменяет резолв egress результата в sync pipeline."""
    from apps.sync.realtime import tasks as sync_tasks

    def _apply(
        egress_id: str = "egress-test-id",
        source_url: str = "http://recordings.local/egress-test.mp4",
    ) -> None:
        async def _stubbed_resolve(*, room_name: str, timeout_seconds: float) -> tuple[str, str]:
            return egress_id, source_url

        monkeypatch.setattr(sync_tasks, "_resolve_livekit_egress_result", _stubbed_resolve)

    return _apply


@pytest.fixture()
def wait_for_meeting_pipeline_complete(call_meeting_repo):
    """Ожидает завершения meeting pipeline до готового транскрипта и summary."""

    async def _wait(
        meeting_id: str,
        company_id: str,
        *,
        timeout_seconds: float = 40.0,
        expected_namespace: str | None = None,
        require_export_done: bool = True,
    ):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        latest = await call_meeting_repo.get(meeting_id)
        poll_index = 0
        while loop.time() < deadline:
            poll_index += 1
            latest = await call_meeting_repo.get(meeting_id)
            if latest is None:
                if poll_index % 8 == 0:
                    print(f"[wait_meeting_pipeline] meeting={meeting_id} status=missing")
                await asyncio.sleep(0.25)
                continue
            if latest.company_id != company_id:
                raise AssertionError(
                    f"Встреча {meeting_id} принадлежит другой компании: {latest.company_id}."
                )
            summary = latest.summary_json or {}
            has_summary = "short_summary" in summary
            has_transcript = isinstance(latest.transcript_text_file_id, str) and latest.transcript_text_file_id != ""
            export_ok = (latest.export_status == "done") if require_export_done else True
            namespace_ok = True
            if expected_namespace is not None:
                namespace_ok = latest.export_target_namespace == expected_namespace
            if poll_index % 8 == 0:
                print(
                    "[wait_meeting_pipeline] "
                    f"meeting={meeting_id} "
                    f"recording={latest.recording_id} "
                    f"export_status={latest.export_status} "
                    f"has_transcript={has_transcript} "
                    f"has_summary={has_summary} "
                    f"namespace={latest.export_target_namespace}"
                )
            if has_summary and has_transcript and export_ok and namespace_ok:
                return latest
            await asyncio.sleep(0.25)

        current_summary = {}
        current_export_status = "missing"
        current_namespace = None
        current_transcript_file = None
        if latest is not None:
            current_summary = latest.summary_json or {}
            current_export_status = latest.export_status
            current_namespace = latest.export_target_namespace
            current_transcript_file = latest.transcript_text_file_id
        raise AssertionError(
            "Meeting pipeline не завершился в срок: "
            f"meeting_id={meeting_id}, "
            f"export_status={current_export_status}, "
            f"export_target_namespace={current_namespace}, "
            f"transcript_text_file_id={current_transcript_file}, "
            f"summary_keys={list(current_summary.keys())}."
        )

    return _wait
