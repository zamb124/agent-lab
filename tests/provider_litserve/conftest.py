"""Изолированный conftest для тестов provider_litserve.

Зачем отдельный conftest и почему запускаем с ``--confcutdir=tests/provider_litserve``:

* эти тесты — pure unit + lightweight integration (Silero VAD модель ~2 MB);
* им не нужны Postgres/Redis/Alembic-миграции/импорт ``apps.flows.main``,
  которые тянет корневой ``tests/conftest.py`` (это десятки секунд старта);
* любой тест провайдера должен укладываться в **15 секунд** (см.
  ``pytestmark`` ниже и в самих модулях).

Без моков и monkeypatch:

* ``unique_id`` — реальный uuid4-фрагмент (тот же контракт, что в корневом
  conftest).
* ``shared_silero_vad_engine`` — session-scoped реальный
  ``LocalVADEngine`` с однократной загрузкой Silero модели через
  ``torch.hub`` (при наличии интернета). Используется в интеграционных
  тестах, чтобы модель не грузилась повторно на каждый тест.
* ``_reset_provider_litserve_runtime_catalog`` — autouse, между тестами
  чистит runtime-каталог через публичный API модуля
  (``reset_runtime_catalog_for_tests``), не через подмену атрибутов.

Запуск:

    uv run --python 3.13 pytest tests/provider_litserve/ \\
        --confcutdir=tests/provider_litserve \\
        -m "not integration and not slow" -v
"""

from __future__ import annotations

import uuid

import pytest

from apps.provider_litserve.runtime_models import reset_runtime_catalog_for_tests


@pytest.fixture
def unique_id() -> str:
    """Уникальный фрагмент uuid для изоляции тестовых сущностей."""
    return uuid.uuid4().hex[:8]


@pytest.fixture(autouse=True)
def _reset_provider_litserve_runtime_catalog():
    """Перед/после каждого теста чистим runtime-каталог моделей."""
    reset_runtime_catalog_for_tests()
    yield
    reset_runtime_catalog_for_tests()


@pytest.fixture(scope="session")
def shared_silero_vad_engine():
    """Session-scoped реальный VAD-движок: модель Silero загружается один раз.

    Используется только интеграционными тестами (``integration`` + ``slow``).
    Если ``silero-vad`` или интернет недоступны, тесты, зависящие от этой
    фикстуры, помечаются ``pytest.skip`` — без моков.
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
