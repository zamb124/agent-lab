"""Фикстуры для тестов voice сервиса."""

from collections.abc import AsyncGenerator, Iterator

import pytest
import pytest_asyncio

from apps.voice.providers.stt.mock import MockSTTProvider
from apps.voice.providers.tts.mock import MockTTSProvider
from apps.voice.providers.vad.mock import MockVADProvider
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_chunker import VoiceChunker
from apps.voice.services.voice_session import VoiceSession
from core.context import Context, reset_context, set_context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests():
    """Переопределение корневой session-фикстуры: тесты voice не используют Postgres."""
    yield


@pytest.fixture(autouse=True)
def voice_billing_context(unique_id: str) -> Iterator[None]:
    token = set_context(
        Context(
            user=User(user_id=f"voice-user-{unique_id}", name="voice-test"),
            host="test",
            session_id=f"voice-test:{unique_id}",
            channel="test",
            language=Language.RU,
            active_company=Company(
                company_id=f"voice-co-{unique_id}",
                name="voice-test",
                subdomain="voice-test",
            ),
            user_companies=[],
            trace_id=unique_id,
            auth_token="voice-test-token",
        )
    )
    try:
        yield
    finally:
        reset_context(token)


@pytest.fixture
def mock_vad() -> MockVADProvider:
    """VAD-провайдер — всегда обнаруживает речь."""
    return MockVADProvider(always_speech=True)


@pytest.fixture
def mock_vad_silent() -> MockVADProvider:
    """VAD-провайдер — никогда не обнаруживает речь."""
    return MockVADProvider(always_speech=False)


@pytest.fixture
def mock_stt() -> MockSTTProvider:
    """STT-провайдер — возвращает фиксированный текст."""
    return MockSTTProvider(text="тестовая транскрипция")


@pytest.fixture
def mock_tts() -> MockTTSProvider:
    """TTS-провайдер — синтезирует байты без ML-моделей."""
    return MockTTSProvider()


@pytest.fixture
def voice_chunker() -> VoiceChunker:
    return VoiceChunker()


@pytest.fixture
def barge_in_controller() -> BargeInController:
    return BargeInController(enabled=True)


@pytest_asyncio.fixture
async def voice_session(unique_id: str) -> AsyncGenerator[VoiceSession, None]:
    """Реальная VoiceSession с уникальным session_id."""
    session = VoiceSession(session_id=f"test-session-{unique_id}")
    yield session
    await session.cancel()
