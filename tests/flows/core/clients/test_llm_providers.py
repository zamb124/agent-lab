"""
Тесты LLM провайдеров и конфигурации нод.

Проверяем:
- Резолюция api_key и base_url (прямая и через @var:)
- Определение провайдера по base_url
- Передача параметров из конфига ноды в LLMClient
- Синхронизация моделей от провайдеров
"""

import os
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest


@contextmanager
def disable_testing_mode():
    """Контекст для отключения TESTING mode."""
    old_testing = os.environ.get("TESTING")
    old_pytest = os.environ.pop("PYTEST_CURRENT_TEST", None)
    old_pytest_raise = os.environ.pop("_PYTEST_RAISE", None)
    os.environ["TESTING"] = "false"
    
    try:
        yield
    finally:
        if old_testing:
            os.environ["TESTING"] = old_testing
        if old_pytest:
            os.environ["PYTEST_CURRENT_TEST"] = old_pytest
        if old_pytest_raise:
            os.environ["_PYTEST_RAISE"] = old_pytest_raise

from core.clients.llm.factory import (
    _resolve_var,
    _detect_provider,
    _get_default_base_url,
    get_llm,
    LLMClient,
)
from core.state import ExecutionState


class TestResolveVar:
    """Тесты резолюции @var: переменных."""

    def test_resolve_var_none_returns_none(self):
        """None value возвращает None."""
        result = _resolve_var(None, None)
        assert result is None

    def test_resolve_var_empty_returns_none(self):
        """Пустая строка возвращает None."""
        result = _resolve_var("", None)
        assert result is None

    def test_resolve_var_direct_value_returned_as_is(self):
        """Прямое значение (без @var:) возвращается без изменений."""
        result = _resolve_var("sk-test-key-123", None)
        assert result == "sk-test-key-123"

    def test_resolve_var_from_state_variables(self):
        """@var:key резолвится из state.variables."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test:session",
            variables={"my_api_key": "sk-resolved-key"}
        )
        result = _resolve_var("@var:my_api_key", state)
        assert result == "sk-resolved-key"

    def test_resolve_var_missing_key_returns_none(self):
        """Отсутствующий ключ возвращает None."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test:session",
            variables={"other_key": "value"}
        )
        result = _resolve_var("@var:missing_key", state)
        assert result is None

    def test_resolve_var_no_state_returns_none(self):
        """@var: без state возвращает None."""
        result = _resolve_var("@var:my_key", None)
        assert result is None

    def test_resolve_var_empty_variables_returns_none(self):
        """@var: с пустыми variables возвращает None."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test:session",
            variables={}
        )
        result = _resolve_var("@var:my_key", state)
        assert result is None


class TestDetectProvider:
    """Тесты определения провайдера по base_url."""

    def test_detect_provider_openrouter(self):
        """Определяет openrouter по base_url."""
        result = _detect_provider("https://openrouter.ai/api/v1")
        assert result == "openrouter"

    def test_detect_provider_bothub(self):
        """Определяет bothub по base_url."""
        result = _detect_provider("https://bothub.chat/api/v2/openai/v1")
        assert result == "bothub"

    def test_detect_provider_openai(self):
        """Определяет openai по base_url."""
        result = _detect_provider("https://api.openai.com/v1")
        assert result == "openai"

    def test_detect_provider_none_for_unknown(self):
        """None для неизвестного URL."""
        result = _detect_provider("https://custom.llm.provider/v1")
        assert result is None

    def test_detect_provider_none_for_empty(self):
        """None для пустого URL."""
        result = _detect_provider(None)
        assert result is None
        result = _detect_provider("")
        assert result is None


class TestGetLLMWithCustomCredentials:
    """Тесты get_llm с кастомными credentials."""

    def test_get_llm_with_custom_api_key_creates_client(self):
        """get_llm с кастомным api_key создает LLMClient с этим ключом."""
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "gpt-4"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = 4096
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = MagicMock(base_url="https://api.openai.com/v1")
                
                client = get_llm(
                    model_name="gpt-4",
                    api_key="sk-custom-user-key",
                    base_url="https://api.openai.com/v1"
                )
                
                assert isinstance(client, LLMClient)
                assert client.api_key == "sk-custom-user-key"
                assert client.base_url == "https://api.openai.com/v1"
                assert client.model == "gpt-4"

    def test_get_llm_with_var_resolved_from_state(self):
        """get_llm с @var: резолвит из state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test:session",
            variables={
                "user_api_key": "sk-from-variable",
                "user_base_url": "https://bothub.chat/api/v2/openai/v1"
            }
        )
        
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "gpt-4"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = 4096
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "bothub"
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = MagicMock(base_url="https://bothub.chat/api/v2/openai/v1")
                mock_settings.return_value.llm.openai = None
                
                client = get_llm(
                    model_name="gpt-4",
                    api_key="@var:user_api_key",
                    base_url="@var:user_base_url",
                    state=state
                )
                
                assert isinstance(client, LLMClient)
                assert client.api_key == "sk-from-variable"
                assert client.base_url == "https://bothub.chat/api/v2/openai/v1"

    def test_get_llm_detects_provider_from_base_url(self):
        """get_llm определяет провайдера по base_url если не указан явно."""
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "gpt-4"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = 4096
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.openrouter = MagicMock(
                    base_url="https://openrouter.ai/api/v1",
                    site_url="https://example.com",
                    site_name="Test"
                )
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = None
                
                client = get_llm(
                    model_name="gpt-4",
                    api_key="sk-openrouter-key",
                    base_url="https://openrouter.ai/api/v1"
                )
                
                assert isinstance(client, LLMClient)
                # Должны быть openrouter headers
                assert "HTTP-Referer" in client.default_headers

    def test_get_llm_explicit_provider_overrides_detection(self):
        """Явно указанный provider имеет приоритет над auto-detection."""
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "gpt-4"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = 4096
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = MagicMock(base_url="https://bothub.chat/api/v2/openai/v1")
                mock_settings.return_value.llm.openai = None
                
                client = get_llm(
                    model_name="gpt-4",
                    api_key="sk-bothub-key",
                    base_url="https://bothub.chat/api/v2/openai/v1",
                    provider="bothub"
                )
                
                assert isinstance(client, LLMClient)
                assert client.api_key == "sk-bothub-key"
                # Bothub не добавляет special headers
                assert "HTTP-Referer" not in client.default_headers


class TestLlmNodeLLMConfig:
    """Тесты передачи LLM конфига из LlmNode."""

    @pytest.mark.asyncio
    async def test_llm_node_passes_llm_config_to_factory(self):
        """LlmNode передает llm config в get_llm."""
        from apps.flows.src.runtime.nodes import LlmNode
        from apps.flows.src.models.node_config import NodeConfig, NodeLLMOverride, NodeType
        
        node_config = NodeConfig(
            node_id="test_node",
            type=NodeType.LLM_NODE,
            name="Test Node",
            prompt="Test prompt",
            llm_override=NodeLLMOverride(
                model="gpt-4-turbo",
                temperature=0.5,
                provider="bothub",
                api_key="sk-node-api-key",
                base_url="https://bothub.chat/api/v2/openai/v1"
            )
        )
        
        node = LlmNode(
            node_id="test_node",
            config={"prompt": "Test prompt"},
        )
        node._node_config = node_config
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test:session",
        )
        
        with patch("apps.flows.src.runtime.nodes.get_llm") as mock_get_llm:
            mock_get_llm.return_value = MagicMock()
            
            node._get_llm(state)
            
            mock_get_llm.assert_called_once_with(
                model_name="gpt-4-turbo",
                temperature=0.5,
                provider="bothub",
                api_key="sk-node-api-key",
                base_url="https://bothub.chat/api/v2/openai/v1",
                state=state,
            )

    @pytest.mark.asyncio
    async def test_llm_node_passes_llm_config_dict(self):
        """LlmNode передает llm_config_dict в get_llm."""
        from apps.flows.src.runtime.nodes import LlmNode
        
        llm_config = {
            "model": "claude-3",
            "temperature": 0.7,
            "provider": "openrouter",
            "api_key": "@var:my_key",
            "base_url": "@var:my_url"
        }
        
        node = LlmNode(
            node_id="test_node",
            config={"prompt": "Test prompt", "llm": llm_config},
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test:session",
            variables={
                "my_key": "sk-variable-key",
                "my_url": "https://openrouter.ai/api/v1"
            }
        )
        
        with patch("apps.flows.src.runtime.nodes.get_llm") as mock_get_llm:
            mock_get_llm.return_value = MagicMock()
            
            node._get_llm(state)
            
            mock_get_llm.assert_called_once_with(
                model_name="claude-3",
                temperature=0.7,
                provider="openrouter",
                api_key="@var:my_key",
                base_url="@var:my_url",
                state=state,
            )


class TestLLMModelsServiceRealAPI:
    """
    Реальные тесты синхронизации моделей от провайдеров.
    Ходят к настоящим API endpoint'ам.
    """

    @pytest.mark.asyncio
    async def test_fetch_bothub_models_real_api(self):
        """
        Реальный запрос к BotHub API для получения списка моделей.
        Использует endpoint: https://bothub.chat/api/v2/model/list?children=1
        """
        from apps.flows.src.services.llm_models_service import LLMModelsService
        from apps.flows.src.db.llm_model_repository import LLMModelRepository
        from apps.flows.config import get_settings
        
        settings = get_settings()
        if not settings.llm.bothub or not settings.llm.bothub.api_key:
            pytest.skip("BotHub API key не настроен в конфиге")
        
        mock_repo = MagicMock(spec=LLMModelRepository)
        service = LLMModelsService(mock_repo)
        
        try:
            models = await service._fetch_bothub_models()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                pytest.skip(
                    "BotHub API отклонил запрос (неверный или отозванный ключ, ограничение доступа)"
                )
            raise
        
        # BotHub должен вернуть список моделей
        assert isinstance(models, list)
        assert len(models) > 0, "BotHub должен вернуть хотя бы одну модель"
        
        # Проверяем что все элементы - строки
        for model_id in models:
            assert isinstance(model_id, str)
            assert len(model_id) > 0
        
        print(f"BotHub вернул {len(models)} моделей")
        print(f"Примеры моделей: {models[:5]}")

    @pytest.mark.asyncio
    async def test_fetch_openrouter_models_real_api(self):
        """
        Реальный запрос к OpenRouter API для получения списка моделей.
        Использует endpoint: {base_url}/models
        """
        from apps.flows.src.services.llm_models_service import LLMModelsService
        from apps.flows.src.db.llm_model_repository import LLMModelRepository
        from apps.flows.config import get_settings
        
        settings = get_settings()
        if not settings.llm.openrouter or not settings.llm.openrouter.api_key:
            pytest.skip("OpenRouter API key не настроен в конфиге")
        
        mock_repo = MagicMock(spec=LLMModelRepository)
        service = LLMModelsService(mock_repo)
        
        models = await service._fetch_openrouter_models()
        
        # OpenRouter должен вернуть список моделей
        assert isinstance(models, list)
        assert len(models) > 0, "OpenRouter должен вернуть хотя бы одну модель"
        
        # Проверяем что все элементы - строки
        for model_id in models:
            assert isinstance(model_id, str)
            assert len(model_id) > 0
        
        # Проверяем что есть известные модели (примеры)
        model_ids_lower = [m.lower() for m in models]
        has_gpt = any("gpt" in m for m in model_ids_lower)
        has_claude = any("claude" in m for m in model_ids_lower)
        
        assert has_gpt or has_claude, "OpenRouter должен содержать GPT или Claude модели"
        
        print(f"OpenRouter вернул {len(models)} моделей")
        print(f"Примеры моделей: {models[:5]}")

    @pytest.mark.asyncio
    async def test_fetch_openai_models_real_api(self):
        """
        Реальный запрос к OpenAI API для получения списка моделей.
        Использует endpoint: {base_url}/models
        """
        from apps.flows.src.services.llm_models_service import LLMModelsService
        from apps.flows.src.db.llm_model_repository import LLMModelRepository
        from apps.flows.config import get_settings
        
        settings = get_settings()
        if not settings.llm.openai or not settings.llm.openai.api_key:
            pytest.skip("OpenAI API key не настроен в конфиге")
        
        mock_repo = MagicMock(spec=LLMModelRepository)
        service = LLMModelsService(mock_repo)
        
        models = await service._fetch_openai_models()
        
        # OpenAI должен вернуть список моделей
        assert isinstance(models, list)
        assert len(models) > 0, "OpenAI должен вернуть хотя бы одну модель"
        
        # Проверяем что все элементы - строки
        for model_id in models:
            assert isinstance(model_id, str)
            assert len(model_id) > 0
        
        # Проверяем что есть известные модели OpenAI
        model_ids_lower = [m.lower() for m in models]
        has_gpt = any("gpt" in m for m in model_ids_lower)
        has_davinci = any("davinci" in m for m in model_ids_lower)
        has_whisper = any("whisper" in m for m in model_ids_lower)
        has_embedding = any("embedding" in m for m in model_ids_lower)
        
        assert has_gpt or has_davinci or has_whisper or has_embedding, \
            "OpenAI должен содержать GPT, Davinci, Whisper или Embedding модели"
        
        print(f"OpenAI вернул {len(models)} моделей")
        print(f"Примеры моделей: {models[:10]}")

    @pytest.mark.asyncio
    async def test_sync_models_saves_correct_provider(self):
        """
        Полный цикл синхронизации: fetch от реального API и сохранение в БД.
        """
        from apps.flows.src.services.llm_models_service import LLMModelsService
        from apps.flows.src.db.llm_model_repository import LLMModelRepository
        from apps.flows.src.models import LLMModel
        from apps.flows.config import get_settings
        from core.db import Storage
        
        settings = get_settings()
        provider = settings.llm.provider
        
        # Проверяем что провайдер настроен
        if provider == "bothub" and (not settings.llm.bothub or not settings.llm.bothub.api_key):
            pytest.skip("BotHub API key не настроен")
        if provider == "openrouter" and (not settings.llm.openrouter or not settings.llm.openrouter.api_key):
            pytest.skip("OpenRouter API key не настроен")
        
        # Storage использует PostgreSQL напрямую из settings
        storage = Storage()
        repo = LLMModelRepository(storage)
        service = LLMModelsService(repo)
        
        # Синхронизируем
        count = await service.sync_models()
        
        assert count > 0, f"Должны синхронизироваться модели от {provider}"
        
        # Проверяем что модели сохранились в БД
        saved_models = await repo.list_by_provider(provider)
        
        assert len(saved_models) > 0
        for model in saved_models:
            assert model.provider == provider
            assert isinstance(model.model_id, str)
            assert len(model.model_id) > 0
        
        print(f"Синхронизировано {count} моделей от {provider}")
        print(f"В БД сохранено {len(saved_models)} моделей")

    @pytest.mark.asyncio
    async def test_sync_all_providers_real_api(self):
        """
        Синхронизация моделей от ВСЕХ настроенных провайдеров.
        """
        from apps.flows.src.services.llm_models_service import LLMModelsService
        from apps.flows.src.db.llm_model_repository import LLMModelRepository
        from apps.flows.config import get_settings
        from core.db import Storage
        
        settings = get_settings()
        
        # Проверяем что хотя бы один провайдер настроен
        has_bothub = settings.llm.bothub and settings.llm.bothub.api_key
        has_openrouter = settings.llm.openrouter and settings.llm.openrouter.api_key
        has_openai = settings.llm.openai and settings.llm.openai.api_key
        
        if not (has_bothub or has_openrouter or has_openai):
            pytest.skip("Нет настроенных провайдеров")
        
        storage = Storage()
        repo = LLMModelRepository(storage)
        service = LLMModelsService(repo)
        
        # Синхронизируем ВСЕ провайдеры
        results = await service.sync_all_providers()
        
        assert isinstance(results, dict)
        total = sum(results.values())
        assert total > 0, "Должны синхронизироваться модели хотя бы от одного провайдера"
        
        print(f"Синхронизация всех провайдеров: {results}")
        print(f"Всего моделей: {total}")
        
        # Проверяем что можем получить модели по каждому провайдеру
        for provider, count in results.items():
            if count > 0:
                models = await service.get_models_by_provider(provider)
                assert len(models) == count, f"Количество моделей {provider} должно совпадать"
                print(f"  {provider}: {count} моделей, примеры: {models[:3]}")

    @pytest.mark.asyncio
    async def test_bothub_models_response_structure(self):
        """
        Тест структуры ответа от BotHub API.
        Проверяем что парсим response правильно.
        """
        from apps.flows.config import get_settings
        
        settings = get_settings()
        if not settings.llm.bothub or not settings.llm.bothub.api_key:
            pytest.skip("BotHub API key не настроен в конфиге")
        
        url = "https://bothub.chat/api/v2/model/list?children=1"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm.bothub.api_key}",
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code in (401, 403):
                pytest.skip(
                    "BotHub API отклонил запрос (неверный или отозванный ключ, ограничение доступа)"
                )
            response.raise_for_status()
            data = response.json()
        
        # Логируем структуру для отладки
        print(f"Response type: {type(data)}")
        if isinstance(data, list):
            print(f"Response is list with {len(data)} items")
            if data:
                print(f"First item structure: {data[0]}")
        elif isinstance(data, dict):
            print(f"Response keys: {data.keys()}")
        
        # Проверяем что можем извлечь модели
        models = []
        items = data if isinstance(data, list) else data.get("data", [])
        for item in items:
            model_id = item.get("name") or item.get("id")
            if model_id:
                models.append(model_id)
        
        assert len(models) > 0, "Должны извлечь хотя бы одну модель"
        print(f"Извлечено {len(models)} моделей: {models[:10]}...")


class TestGetDefaultBaseUrl:
    """Тесты _get_default_base_url."""

    def test_get_default_base_url_openrouter(self):
        """Возвращает base_url для openrouter."""
        mock_settings = MagicMock()
        mock_settings.llm.openrouter = MagicMock(base_url="https://openrouter.ai/api/v1")
        
        result = _get_default_base_url("openrouter", mock_settings)
        assert result == "https://openrouter.ai/api/v1"

    def test_get_default_base_url_bothub(self):
        """Возвращает base_url для bothub."""
        mock_settings = MagicMock()
        mock_settings.llm.bothub = MagicMock(base_url="https://bothub.chat/api/v2/openai/v1")
        
        result = _get_default_base_url("bothub", mock_settings)
        assert result == "https://bothub.chat/api/v2/openai/v1"

    def test_get_default_base_url_openai(self):
        """Возвращает base_url для openai."""
        mock_settings = MagicMock()
        mock_settings.llm.openai = MagicMock(base_url="https://api.openai.com/v1")
        
        result = _get_default_base_url("openai", mock_settings)
        assert result == "https://api.openai.com/v1"

    def test_get_default_base_url_fallback(self):
        """Fallback на OpenAI для неизвестного провайдера."""
        mock_settings = MagicMock()
        
        result = _get_default_base_url("unknown", mock_settings)
        assert result == "https://api.openai.com/v1"

    def test_get_default_base_url_no_config(self):
        """Fallback если конфиг провайдера не настроен."""
        mock_settings = MagicMock()
        mock_settings.llm.openrouter = None
        
        result = _get_default_base_url("openrouter", mock_settings)
        assert result == "https://openrouter.ai/api/v1"
