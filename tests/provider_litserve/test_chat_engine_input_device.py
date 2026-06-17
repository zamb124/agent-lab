"""LocalChatEngine tokenizer input device placement."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import torch

from apps.provider_litserve.llm import engines
from apps.provider_litserve.openai_server_contracts import (
    OpenAIChatCompletionsRequest,
    OpenAIChatMessage,
)
from core.config.models import ProviderLitserveInfraConfig


def _engine() -> engines.LocalChatEngine:
    cfg = ProviderLitserveInfraConfig()
    engine = engines.LocalChatEngine(cfg)
    engine.setup("cuda:0")
    return engine


def test_model_input_device_uses_embedding_weight_device() -> None:
    model = MagicMock()
    model.get_input_embeddings.return_value.weight.device = torch.device("cuda:0")
    device = engines._model_input_device(model, "cpu")
    assert device == torch.device("cuda:0")


def test_chat_moves_inputs_to_hf_device_map_model_device(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine()
    captured_device: list[torch.device] = []

    class _MovedTensor:
        def __init__(self, device: torch.device, shape: tuple[int, ...]) -> None:
            self.device = device
            self._shape = shape

        @property
        def shape(self) -> torch.Size:
            return torch.Size(self._shape)

    class _FakeTensor:
        def __init__(self, shape: tuple[int, ...]) -> None:
            self._shape = shape

        @property
        def shape(self) -> torch.Size:
            return torch.Size(self._shape)

        def to(self, device: torch.device) -> _MovedTensor:
            captured_device.append(device)
            return _MovedTensor(device, self._shape)

    fake_input_ids = _FakeTensor((1, 4))

    tokenizer = MagicMock()
    tokenizer.apply_chat_template.return_value = "prompt"
    tokenizer.return_value = {"input_ids": fake_input_ids}
    tokenizer.eos_token_id = 0
    tokenizer.decode.return_value = '{"page_summary":"s","chunks":[{"content":"c","metadata_summary":"m"}]}'

    model = MagicMock()
    model.hf_device_map = {"model.embed_tokens": 0}
    model.get_input_embeddings.return_value.weight.device = torch.device("cuda:0")
    model.generate.return_value = torch.tensor([[1, 2, 3, 4, 5, 6]])

    monkeypatch.setattr(engine, "_ensure_model", lambda: (tokenizer, model))

    request = OpenAIChatCompletionsRequest(
        model="qwen/qwen2.5-1.5b-instruct-crawl",
        messages=[OpenAIChatMessage(role="user", content="hello")],
        response_format={"type": "json_object"},
    )
    response = engine.chat(request)
    assert response.choices[0].message.content
    assert captured_device == [torch.device("cuda:0")]
    generate_kwargs = model.generate.call_args.kwargs
    assert generate_kwargs["input_ids"].device == torch.device("cuda:0")
