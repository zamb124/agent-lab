"""ImageGenSpec: выбор транспорта и валидация set-параметров (без сети и БД)."""

from __future__ import annotations

import pytest

from core.ai.models import ResolvedAIModel
from core.ai.providers import AICapability
from core.clients.image_gen import (
    ImageGenSpec,
    pick_image_gen_transport,
    validate_image_gen_spec,
)


def _resolved(provider: str, model: str = "m") -> ResolvedAIModel:
    return ResolvedAIModel(
        capability=AICapability.IMAGE_GEN,
        provider=provider,
        model=model,
    )


class TestTransportPick:
    def test_google_defaults_to_native(self) -> None:
        spec = ImageGenSpec(prompt="x")
        assert pick_image_gen_transport(_resolved("google"), spec) == "google_native"

    def test_non_google_defaults_to_chat(self) -> None:
        spec = ImageGenSpec(prompt="x")
        assert pick_image_gen_transport(_resolved("openrouter"), spec) == "openai_chat"

    def test_explicit_native_requires_google(self) -> None:
        spec = ImageGenSpec(prompt="x", transport="google_native")
        with pytest.raises(ValueError, match="google_native"):
            _ = pick_image_gen_transport(_resolved("openrouter"), spec)

    def test_explicit_chat_for_google_allowed(self) -> None:
        spec = ImageGenSpec(prompt="x", transport="openai_chat")
        transport = pick_image_gen_transport(_resolved("google"), spec)
        assert transport == "openai_chat"


class TestSpecValidation:
    def test_plain_spec_passes_everywhere(self) -> None:
        spec = ImageGenSpec(prompt="x", references=("file_1",))
        validate_image_gen_spec(spec, "google_native")
        validate_image_gen_spec(spec, "openai_chat")

    def test_geometry_supported_by_both(self) -> None:
        spec = ImageGenSpec(prompt="x", aspect_ratio="16:9", image_size="2K")
        validate_image_gen_spec(spec, "google_native")
        validate_image_gen_spec(spec, "openai_chat")

    def test_output_format_native_only(self) -> None:
        spec = ImageGenSpec(prompt="x", output_format="jpeg")
        validate_image_gen_spec(spec, "google_native")
        with pytest.raises(ValueError, match="unsupported_parameter:output_format"):
            validate_image_gen_spec(spec, "openai_chat")

    def test_count_native_only(self) -> None:
        spec = ImageGenSpec(prompt="x", count=2)
        validate_image_gen_spec(spec, "google_native")
        with pytest.raises(ValueError, match="unsupported_parameter:count"):
            validate_image_gen_spec(spec, "openai_chat")

    def test_mask_seed_negative_unsupported_everywhere(self) -> None:
        for spec in (
            ImageGenSpec(prompt="x", mask_file_id="file_a"),
            ImageGenSpec(prompt="x", seed=42),
            ImageGenSpec(prompt="x", negative_prompt="bad"),
        ):
            with pytest.raises(ValueError, match="unsupported_parameter"):
                validate_image_gen_spec(spec, "google_native")
            with pytest.raises(ValueError, match="unsupported_parameter"):
                validate_image_gen_spec(spec, "openai_chat")

    def test_native_references_limit(self) -> None:
        spec = ImageGenSpec(prompt="x", references=tuple(f"file_{i}" for i in range(15)))
        with pytest.raises(ValueError, match="at most 14"):
            validate_image_gen_spec(spec, "google_native")
        validate_image_gen_spec(spec, "openai_chat")


class TestSpecModel:
    def test_empty_reference_rejected(self) -> None:
        with pytest.raises(ValueError, match="references"):
            _ = ImageGenSpec(prompt="x", references=("",))

    def test_count_bounds(self) -> None:
        with pytest.raises(ValueError):
            _ = ImageGenSpec(prompt="x", count=5)
        with pytest.raises(ValueError):
            _ = ImageGenSpec(prompt="x", count=0)

    def test_prompt_required(self) -> None:
        with pytest.raises(ValueError):
            _ = ImageGenSpec(prompt="")
