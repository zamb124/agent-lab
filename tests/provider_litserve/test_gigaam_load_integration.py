"""GigaAM STT: реальная загрузка модели и транскрибация (без моков).

Регрессия инцидента 2026-11-11: transformers>=5 конструирует модели на
meta-device безусловно, remote-код ``modeling_gigaam`` собирал
FeatureExtractor через hydra и падал на смешении cpu/meta-тензоров.
``_GigaAMAdapter.load`` обходит ``AutoModel.from_pretrained``: класс
резолвится напрямую через ``get_class_from_dynamic_module``, веса
заливаются ``load_state_dict`` — этот файл проверяет весь путь на
настоящей модели.

GigaAM-v3 (~1 GB ``pytorch_model.bin``) и Qwen3-TTS-1.7B-CustomVoice (~3.6 GB)
скачиваются один раз в session-фикстурах и кэшируются в HF-кэше машины.

Запуск:

    uv run --python 3.13 pytest tests/provider_litserve/test_gigaam_load_integration.py \
        --confcutdir=tests/provider_litserve \\
        -m "integration and slow" -v
"""

from __future__ import annotations

import io
import wave

import pytest
import torch

from apps.provider_litserve.catalog import ModelCatalog
from apps.provider_litserve.stt.engines import _GigaAMAdapter
from apps.provider_litserve.tts.engines import LocalTTSEngine
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveTTSModelEntry,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.timeout(600),
]

GIGAAM_REPO_ID = "ai-sage/GigaAM-v3"
GIGAAM_REVISION = "e2e_rnnt"
RU_SPEECH_TEXT = "Проверка распознавания русской речи."
TTS_API_ID = "qwen-tts-gigaam-test"


@pytest.fixture(scope="session")
def shared_gigaam_stt():
    """Session-scoped реальный GigaAM на CPU: загрузка один раз на сессию."""
    adapter = _GigaAMAdapter(ProviderLitserveInfraConfig(), "cpu")
    try:
        model = adapter.load(GIGAAM_REPO_ID, GIGAAM_REVISION)
    except (RuntimeError, OSError) as exc:
        pytest.skip(f"GigaAM недоступен в окружении теста: {exc}")
    return adapter, model


@pytest.fixture(scope="session")
def shared_ru_speech_wav():
    """Реальная RU-речь через Qwen3-TTS CustomVoice — та же цепочка, что на проде."""
    cfg = ProviderLitserveInfraConfig(
        tts_models=[
            ProviderLitserveTTSModelEntry(
                api_model_id=TTS_API_ID,
                hf_model_id="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                voice="serena",
                synthesis_locale="ru",
                sample_rate=24000,
            ),
        ],
    )
    engine = LocalTTSEngine(cfg, ModelCatalog.from_seed(cfg))
    engine.setup("cpu")
    try:
        return engine.synthesize(
            text=RU_SPEECH_TEXT,
            api_model_id=TTS_API_ID,
            voice_override=None,
            response_format="wav",
            sample_rate_override=None,
        )
    except (RuntimeError, OSError) as exc:
        pytest.skip(f"Qwen3-TTS недоступен в окружении теста: {exc}")


def test_gigaam_load_returns_transcribing_model(shared_gigaam_stt):
    """Регрессия meta-device: load() обязан пройти и вернуть объект с transcribe."""
    _adapter, model = shared_gigaam_stt
    assert callable(model.transcribe)


def test_gigaam_transcribes_tts_russian_speech(shared_gigaam_stt, shared_ru_speech_wav):
    """Прод-цепочка TTS→STT: GigaAM распознаёт реальную RU-речь Qwen3-TTS."""
    adapter, model = shared_gigaam_stt
    text = adapter.transcribe(model, shared_ru_speech_wav, None)
    normalized = text.casefold()
    assert "проверка" in normalized
    assert "реч" in normalized


def test_gigaam_transcribe_silence_returns_string(shared_gigaam_stt):
    """Тишина — валидный вход: transcribe отдаёт строку без исключений."""
    adapter, model = shared_gigaam_stt
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    text = adapter.transcribe(model, buf.getvalue(), None)
    assert isinstance(text, str)


def test_gigaam_load_unknown_repo_raises():
    """Несуществующая HF-репа — ошибка наружу, без тихих фолбеков."""
    adapter = _GigaAMAdapter(ProviderLitserveInfraConfig(), "cpu")
    with pytest.raises(OSError):
        adapter.load("definitely-not-a-repo/x-y-z-123", None)


def test_gigaam_load_cuda_device_without_cuda_raises(monkeypatch):
    """Запрошенный CUDA при её отсутствии — понятная ошибка до обращения к HF."""
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    adapter = _GigaAMAdapter(ProviderLitserveInfraConfig(), "cuda:0")
    with pytest.raises(RuntimeError, match="CUDA недоступен"):
        adapter.load(GIGAAM_REPO_ID, GIGAAM_REVISION)
