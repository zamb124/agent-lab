"""LocalTTSEngine на Qwen3-TTS CustomVoice.

Быстрая часть — валидации и тишина без загрузки весов (без моков, реальные
entry/каталог/движок). Интеграционная часть — настоящий
``Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`` (~3.6 GB, session-фикстура, кэш HF)
на CPU: синтез RU-речи, форматы, ресемплинг, спикеры, сегментация, ``instruct``.

Запуск интеграционной части:

    uv run pytest tests/provider_litserve/test_qwen_tts_engine.py \
        --confcutdir=tests/provider_litserve -m "integration and slow" -v
"""

from __future__ import annotations

import io
import wave

import pytest

from apps.provider_litserve.catalog import ModelCatalog
from apps.provider_litserve.tts.engines import LocalTTSEngine
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveTTSModelEntry,
)

QWEN_TTS_API_ID = "qwen3-tts-test"
QWEN_TTS_HF_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"


def _engine(
    *,
    voice: str | None = "serena",
    synthesis_locale: str | None = "ru",
    sample_rate: int | None = 24000,
    instruct: str | None = None,
    tts_input_steps: tuple[str, ...] = (),
) -> LocalTTSEngine:
    cfg = ProviderLitserveInfraConfig(
        tts_models=[
            ProviderLitserveTTSModelEntry(
                api_model_id=QWEN_TTS_API_ID,
                hf_model_id=QWEN_TTS_HF_ID,
                voice=voice,
                synthesis_locale=synthesis_locale,
                sample_rate=sample_rate,
                instruct=instruct,
                tts_input_steps=tts_input_steps,
            ),
        ],
    )
    engine = LocalTTSEngine(cfg, ModelCatalog.from_seed(cfg))
    engine.setup("cpu")
    return engine


def _synthesize(
    engine: LocalTTSEngine,
    *,
    text: str = "Привет.",
    voice_override: str | None = None,
    response_format: str = "wav",
    sample_rate_override: int | None = None,
) -> bytes:
    return engine.synthesize(
        text=text,
        api_model_id=QWEN_TTS_API_ID,
        voice_override=voice_override,
        response_format=response_format,  # type: ignore[arg-type]
        sample_rate_override=sample_rate_override,
    )


def _wav_params(payload: bytes) -> tuple[int, int, int]:
    with wave.open(io.BytesIO(payload), "rb") as wf:
        return wf.getframerate(), wf.getnchannels(), wf.getnframes()


pytestmark = pytest.mark.timeout(30)


def test_synthesize_unknown_api_model_raises() -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="неизвестная модель"):
        engine.synthesize(
            text="Привет",
            api_model_id="no-such-model",
            voice_override=None,
            response_format="wav",
            sample_rate_override=None,
        )


def test_synthesize_unknown_speaker_raises() -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="CustomVoice speaker"):
        _synthesize(engine, voice_override="alloy")


def test_synthesize_voice_missing_everywhere_raises() -> None:
    engine = _engine(voice=None)
    with pytest.raises(ValueError, match="voice is not set"):
        _synthesize(engine)


def test_synthesize_bad_sample_rate_raises() -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="sample_rate"):
        _synthesize(engine, sample_rate_override=12345)


def test_synthesize_empty_text_returns_silence_pcm() -> None:
    engine = _engine()
    payload = engine.synthesize(
        text="   ",
        api_model_id=QWEN_TTS_API_ID,
        voice_override=None,
        response_format="pcm",
        sample_rate_override=None,
    )
    assert isinstance(payload, bytes)
    assert len(payload) > 0
    assert len(payload) % 2 == 0
    assert payload == b"\x00\x00" * (len(payload) // 2)


def test_synthesize_invisible_only_returns_silence_wav() -> None:
    """Zero-width символы срезает sanitize → тишина в WAV без обращения к модели."""
    engine = _engine()
    payload = _synthesize(engine, text="\u200b\u200b")
    rate, channels, _frames = _wav_params(payload)
    assert rate == 24000
    assert channels == 1


@pytest.fixture(scope="session")
def shared_qwen_engine() -> LocalTTSEngine:
    """Реальный Qwen3-TTS CustomVoice на CPU — один прогрев на сессию."""
    engine = _engine()
    try:
        _synthesize(engine, text="Прогрев.")
    except (RuntimeError, OSError) as exc:
        pytest.skip(f"Qwen3-TTS недоступен в окружении теста: {exc}")
    return engine


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(600)
def test_qwen_synthesize_russian_wav(shared_qwen_engine: LocalTTSEngine) -> None:
    payload = _synthesize(
        shared_qwen_engine, text="Проверка синтеза русской речи."
    )
    rate, channels, frames = _wav_params(payload)
    assert rate == 24000
    assert channels == 1
    assert frames > 24000 // 4  # хотя бы четверть секунды речи


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(600)
def test_qwen_synthesize_pcm_format_and_resample(shared_qwen_engine: LocalTTSEngine) -> None:
    payload = _synthesize(
        shared_qwen_engine,
        text="Частота шестнадцать килогерц.",
        response_format="pcm",
        sample_rate_override=16000,
    )
    assert len(payload) % 2 == 0
    assert len(payload) > 16000 // 2  # >0.25с * 2 байта/сэмпл
    wav_payload = _synthesize(
        shared_qwen_engine,
        text="Частота шестнадцать килогерц.",
        sample_rate_override=16000,
    )
    rate, _channels, _frames = _wav_params(wav_payload)
    assert rate == 16000


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(600)
def test_qwen_synthesize_speakers_case_and_instruct() -> None:
    """Другой спикер (регистронезависимый) и entry-level instruct — рабочие пути."""
    engine = _engine(instruct="Говори медленно и спокойно")
    engine.setup("cpu")
    payload = _synthesize(
        engine,
        text="Говорю другим голосом.",
        voice_override="  SeReNa ",
    )
    rate, _channels, frames = _wav_params(payload)
    assert rate == 24000
    assert frames > 0


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(600)
def test_qwen_synthesize_long_text_segments(shared_qwen_engine: LocalTTSEngine) -> None:
    text = ("Проверка длинного синтеза речи с разбиением на сегменты. " * 40).strip()
    assert len(text) > 900
    payload = _synthesize(shared_qwen_engine, text=text)
    rate, _channels, frames = _wav_params(payload)
    assert rate == 24000
    assert frames > 24000 * 5  # длинный текст → несколько секунд аудио


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(600)
def test_qwen_synthesize_latin_and_digits(shared_qwen_engine: LocalTTSEngine) -> None:
    """Смешанный RU/LAT текст — без транслитерации, модель читает оба алфавита."""
    payload = _synthesize(
        shared_qwen_engine,
        text="Звоните на iPhone 15 до 18 часов.",
        voice_override="serena",
    )
    rate, _channels, frames = _wav_params(payload)
    assert rate == 24000
    assert frames > 0
