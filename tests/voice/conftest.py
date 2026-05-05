"""Фикстуры для тестов voice сервиса."""

import pytest
import pytest_asyncio

from apps.voice.providers.stt.mock import MockSTTProvider
from apps.voice.providers.tts.mock import MockTTSProvider
from apps.voice.providers.vad.mock import MockVADProvider
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_chunker import VoiceChunker
from apps.voice.services.voice_session import VoiceSession


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests():
    """Переопределение корневой session-фикстуры: тесты voice не используют Postgres."""
    yield


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
async def voice_session(unique_id: str) -> VoiceSession:
    """Реальная VoiceSession с уникальным session_id."""
    session = VoiceSession(session_id=f"test-session-{unique_id}")
    yield session
    await session.cancel()
