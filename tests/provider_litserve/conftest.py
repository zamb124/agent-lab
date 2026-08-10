"""Парсеры и чистые юнит-проверки provider_litserve без docker-compose-test (Postgres/Redis).

Корневой ``tests/conftest.py`` поднимает БД и Redis Pub/Sub session-wide; здесь те же
имена фикстур переопределены для деревьев только под ``tests/provider_litserve/``.

``shared_silero_vad_engine`` — session-scoped реальный LocalVADEngine для
integration+slow тестов Silero (модель ~2 MB, один раз на сессию).
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests():
    yield


@pytest.fixture(scope="session", autouse=True)
def platform_notification_manager_redis(setup_database_before_tests):
    _ = setup_database_before_tests
    yield


@pytest.fixture(scope="session")
def shared_silero_vad_engine():
    """Session-scoped реальный VAD-движок: модель Silero загружается один раз.

    Если ``silero-vad`` или torch.hub недоступны — skip зависимых тестов.
    """
    from apps.provider_litserve.vad.engines import LocalVADEngine
    from core.config.models import (
        ProviderLitserveInfraConfig,
        ProviderLitserveVADModelEntry,
    )

    api_id = "silero-shared"
    cfg = ProviderLitserveInfraConfig(
        sqlite_path="./data/test/silero-shared.db",
        vad_models=[
            ProviderLitserveVADModelEntry(
                api_model_id=api_id,
                hf_model_id="snakers4/silero-vad",
                sample_rate=16000,
                threshold=0.5,
            ),
        ],
        vad_default_api_model_id=api_id,
    )
    engine = LocalVADEngine(cfg)
    engine.setup("cpu")

    try:
        entry = cfg.vad_models[0]
        engine._ensure_model(entry)
    except (RuntimeError, OSError) as exc:
        pytest.skip(f"Silero VAD недоступен в окружении теста: {exc}")
    return engine, cfg, api_id
