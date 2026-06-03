"""Контракт ответа OpenAI-compatible embeddings для AIEmbeddingClient."""

from core.ai.embedding_client import EmbeddingResponsePayload


def test_embedding_response_payload_accepts_openai_compatible_fields() -> None:
    payload = EmbeddingResponsePayload.model_validate(
        {
            "object": "list",
            "model": "qwen/qwen3-embedding-0.6b",
            "data": [
                {
                    "object": "embedding",
                    "embedding": [0.1, 0.2, 0.3],
                    "index": 0,
                }
            ],
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }
    )

    assert payload.data[0].embedding == [0.1, 0.2, 0.3]
