"""build_provider_litserve_v1_models_response: RAG и STT/TTS/VAD попадают в каталог."""

from __future__ import annotations

import pytest

from apps.provider_litserve.openai_server_contracts import (
    build_provider_litserve_v1_models_response,
)
from core.models.provider_litserve_model import ProviderLitserveModelPair

pytestmark = pytest.mark.timeout(15)


def test_v1_models_response_contains_audio_kinds(unique_id):
    response = build_provider_litserve_v1_models_response(
        embedding_entries=[
            ProviderLitserveModelPair(
                api_model_id="emb-openai",
                hf_model_id="Qwen/Qwen3-Embedding-0.6B",
                dimension=1024,
                context_length=8192,
            ),
            ProviderLitserveModelPair(
                api_model_id=f"emb-{unique_id}",
                hf_model_id="Qwen/Qwen3-Embedding-0.6B",
            ),
        ],
        rerank_entries=[
            ProviderLitserveModelPair(
                api_model_id="rerank-openai",
                hf_model_id="Qwen/Qwen3-Reranker-0.6B",
                context_length=8192,
            ),
            ProviderLitserveModelPair(
                api_model_id=f"rerank-{unique_id}",
                hf_model_id="Qwen/Qwen3-Reranker-0.6B",
            ),
        ],
        stt_model_ids=[f"stt-{unique_id}"],
        tts_model_ids=[f"tts-{unique_id}"],
        vad_model_ids=[f"vad-{unique_id}"],
        created=1_700_000_000,
    )
    assert response.object == "list"
    by_id = {item.id: item for item in response.data}
    assert f"stt-{unique_id}" in by_id
    assert f"tts-{unique_id}" in by_id
    assert f"vad-{unique_id}" in by_id
    assert f"emb-{unique_id}" in by_id
    assert f"rerank-{unique_id}" in by_id
    assert by_id["emb-openai"].native_dimension == 1024
    assert by_id["emb-openai"].context_length == 8192
    assert "audio" in by_id[f"stt-{unique_id}"].architecture.input_modalities
    assert "text" in by_id[f"stt-{unique_id}"].architecture.output_modalities
    assert "text" in by_id[f"tts-{unique_id}"].architecture.input_modalities
    assert "audio" in by_id[f"tts-{unique_id}"].architecture.output_modalities
    assert "audio" in by_id[f"vad-{unique_id}"].architecture.input_modalities


def test_v1_models_response_dedupes_audio_ids(unique_id):
    api_id = f"stt-dup-{unique_id}"
    response = build_provider_litserve_v1_models_response(
        embedding_entries=[
            ProviderLitserveModelPair(
                api_model_id="emb", hf_model_id="Qwen/Qwen3-Embedding-0.6B"
            )
        ],
        rerank_entries=[
            ProviderLitserveModelPair(
                api_model_id="rerank", hf_model_id="Qwen/Qwen3-Reranker-0.6B"
            )
        ],
        stt_model_ids=[api_id, api_id],
        tts_model_ids=[],
        vad_model_ids=[],
        created=1_700_000_000,
    )
    matched = [item for item in response.data if item.id == api_id]
    assert len(matched) == 1


def test_v1_models_response_dedupes_pair_api_ids(unique_id):
    pair = ProviderLitserveModelPair(api_model_id="emb", hf_model_id="x/y")
    response = build_provider_litserve_v1_models_response(
        embedding_entries=[pair, pair],
        rerank_entries=[],
        stt_model_ids=[],
        tts_model_ids=[],
        vad_model_ids=[],
        created=1_700_000_000,
    )
    matched = [item for item in response.data if item.id == "emb"]
    assert len(matched) == 1
