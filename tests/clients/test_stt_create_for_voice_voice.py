"""Unit: `STTClientFactory.create_for_voice` с tier model и company `secrets`."""

from __future__ import annotations

import pytest

from core.clients.stt_client import STTClientFactory, CloudRuSTTClient, YandexSTTClient
from core.config.models import (
    CloudRuSTTConfig,
    STTProvidersConfig,
    YandexSTTBackendConfig,
)

pytestmark = pytest.mark.timeout(15)
def test_create_for_voice_cloud_ru_uses_resolved_model_when_set() -> None:
    cfg = STTProvidersConfig(
        cloud_ru=CloudRuSTTConfig(
            enabled=True,
            api_key="dep-key",
            base_url="http://example.invalid/v1/audio/transcriptions",
            model="openai/whisper-large-v3",
            response_format="text",
            temperature=0.5,
            language="ru",
            timeout=60.0,
        ),
    )
    client = STTClientFactory.create_for_voice(
        cfg=cfg,
        provider_name="cloud_ru",
        model="tier-model-override",
        default_language="ru",
        timeout_s=None,
        secrets=None,
    )
    assert isinstance(client, CloudRuSTTClient)
    assert client._model == "tier-model-override"


def test_create_for_voice_cloud_ru_falls_back_to_backend_model() -> None:
    cfg = STTProvidersConfig(
        cloud_ru=CloudRuSTTConfig(
            enabled=True,
            api_key="dep-key",
            base_url="http://example.invalid/v1/audio/transcriptions",
            model="openai/whisper-large-v3",
            response_format="text",
            temperature=0.5,
            language="ru",
            timeout=60.0,
        ),
    )
    client = STTClientFactory.create_for_voice(
        cfg=cfg,
        provider_name="cloud_ru",
        model=None,
        default_language="ru",
        timeout_s=None,
        secrets=None,
    )
    assert isinstance(client, CloudRuSTTClient)
    assert client._model == "openai/whisper-large-v3"


def test_create_for_voice_cloud_ru_merges_company_api_key() -> None:
    cfg = STTProvidersConfig(
        cloud_ru=CloudRuSTTConfig(
            enabled=True,
            api_key="dep-key",
            base_url="http://example.invalid/v1/audio/transcriptions",
            model="openai/whisper-large-v3",
            response_format="text",
            temperature=0.5,
            language="ru",
            timeout=60.0,
        ),
    )
    client = STTClientFactory.create_for_voice(
        cfg=cfg,
        provider_name="cloud_ru",
        model=None,
        default_language="ru",
        timeout_s=None,
        secrets={"api_key": "company-key"},
    )
    assert isinstance(client, CloudRuSTTClient)
    assert client._api_key == "company-key"


def test_create_for_voice_yandex_merges_secrets_strings() -> None:
    cfg = STTProvidersConfig(
        yandex=YandexSTTBackendConfig(
            enabled=True,
            api_key="cfg-key",
            folder_id="cfg-folder",
        ),
    )
    client = STTClientFactory.create_for_voice(
        cfg=cfg,
        provider_name="yandex",
        model="general",
        default_language="ru",
        timeout_s=120.0,
        secrets={"folder_id": "company-folder"},
    )
    assert isinstance(client, YandexSTTClient)
    assert client._api_key == "cfg-key"
    assert client._folder_id == "company-folder"
