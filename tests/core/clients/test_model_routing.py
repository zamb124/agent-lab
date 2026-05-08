"""Контракт split_provider_prefixed_model (префикс платформенного провайдера в model)."""

import pytest

from core.clients.llm.model_routing import split_provider_prefixed_model


def test_split_when_provider_set_unchanged():
    assert split_provider_prefixed_model("openrouter", "openai/gpt-4o") == ("openrouter", "openai/gpt-4o")


def test_split_openrouter_vendor_model():
    assert split_provider_prefixed_model(None, "openrouter:openai/gpt-4o") == (
        "openrouter",
        "openai/gpt-4o",
    )


def test_split_openai_short_id():
    assert split_provider_prefixed_model("", "openai:gpt-4o") == ("openai", "gpt-4o")


def test_no_split_vendor_slash_only():
    assert split_provider_prefixed_model(None, "openai/gpt-4o") == (None, "openai/gpt-4o")


def test_no_split_unknown_head():
    assert split_provider_prefixed_model(None, "foo:bar") == (None, "foo:bar")


def test_no_split_empty_tail():
    assert split_provider_prefixed_model(None, "openrouter:") == (None, "openrouter:")


def test_no_split_only_colon():
    assert split_provider_prefixed_model(None, ":") == (None, ":")


@pytest.mark.parametrize(
    "slug",
    ["openrouter", "openai", "bothub", "provider_litserve", "yandex"],
)
def test_split_accepts_all_platform_slugs(slug: str):
    p, m = split_provider_prefixed_model(None, f"{slug}:x/y")
    assert p == slug
    assert m == "x/y"
