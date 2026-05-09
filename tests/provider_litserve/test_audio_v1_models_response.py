"""build_provider_litserve_v1_models_response: STT/TTS/VAD попадают в каталог."""

from __future__ import annotations

import pytest

from apps.provider_litserve.openai_server_contracts import (
    build_provider_litserve_v1_models_response,
)


pytestmark = pytest.mark.timeout(15)


def test_v1_models_response_contains_audio_kinds(unique_id):
    response = build_provider_litserve_v1_models_response(
        embedding_openai_model_id="emb-openai",
        embedding_model_ids=[f"emb-{unique_id}"],
        embedding_hf_model_id="Qwen/Qwen3-Embedding-8B",
        embedding_dimension=1024,
        embedding_context_length=8192,
        rerank_openai_model_id="rerank-openai",
        rerank_model_ids=[f"rerank-{unique_id}"],
        rerank_hf_model_id="Qwen/Qwen3-Reranker-8B",
        rerank_context_length=8192,
        chat_model_ids=[f"chat-{unique_id}"],
        stt_model_ids=[f"stt-{unique_id}"],
        tts_model_ids=[f"tts-{unique_id}"],
        vad_model_ids=[f"vad-{unique_id}"],
        created=1_700_000_000,
    )
    assert response["object"] == "list"
    by_id = {item["id"]: item for item in response["data"]}
    assert f"stt-{unique_id}" in by_id
    assert f"tts-{unique_id}" in by_id
    assert f"vad-{unique_id}" in by_id
    assert "audio" in by_id[f"stt-{unique_id}"]["architecture"]["input_modalities"]
    assert "text" in by_id[f"stt-{unique_id}"]["architecture"]["output_modalities"]
    assert "text" in by_id[f"tts-{unique_id}"]["architecture"]["input_modalities"]
    assert "audio" in by_id[f"tts-{unique_id}"]["architecture"]["output_modalities"]
    assert "audio" in by_id[f"vad-{unique_id}"]["architecture"]["input_modalities"]


def test_v1_models_response_dedupes_audio_ids(unique_id):
    api_id = f"stt-dup-{unique_id}"
    response = build_provider_litserve_v1_models_response(
        embedding_openai_model_id="emb",
        embedding_model_ids=[],
        embedding_hf_model_id="Qwen/Qwen3-Embedding-8B",
        embedding_dimension=1024,
        embedding_context_length=8192,
        rerank_openai_model_id="rerank",
        rerank_model_ids=[],
        rerank_hf_model_id="Qwen/Qwen3-Reranker-8B",
        rerank_context_length=8192,
        chat_model_ids=[],
        stt_model_ids=[api_id, api_id],
        tts_model_ids=[],
        vad_model_ids=[],
        created=1_700_000_000,
    )
    matched = [item for item in response["data"] if item["id"] == api_id]
    assert len(matched) == 1
