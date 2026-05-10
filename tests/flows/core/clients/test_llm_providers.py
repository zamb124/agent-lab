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
from core.variables import VariableResolutionError
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

    def test_resolve_var_missing_key_raises_error(self):
        """Отсутствующий ключ вызывает VariableResolutionError."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test:session",
            variables={"other_key": "value"}
        )
        with pytest.raises(VariableResolutionError):
            _resolve_var("@var:missing_key", state)

    def test_resolve_var_no_state_raises_error(self):
        """@var: без state вызывает VariableResolutionError."""
        with pytest.raises(VariableResolutionError):
            _resolve_var("@var:my_key", None)

    def test_resolve_var_empty_variables_raises_error(self):
        """@var: с пустыми variables вызывает VariableResolutionError."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test:session",
            variables={}
        )
        with pytest.raises(VariableResolutionError):
            _resolve_var("@var:my_key", state)


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

    def test_detect_provider_provider_litserve(self):
        """Определяет provider_litserve по локальному URL."""
        result = _detect_provider("http://127.0.0.1:8014/v1")
        assert result == "provider_litserve"

    def test_detect_provider_yandex(self):
        result = _detect_provider("https://llm.api.cloud.yandex.net/v1")
        assert result == "yandex"

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

    def test_get_llm_with_provider_litserve_from_settings(self):
        """Системный provider_litserve создает LLMClient с локальным base_url."""
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "qwen/qwen3.5-397b-a17b"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = 4096
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "provider_litserve"
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = None
                mock_settings.return_value.provider_litserve.resolve_openai_v1_base_url.return_value = (
                    "http://127.0.0.1:8014/v1"
                )

                client = get_llm(model_name="qwen/qwen3.5-397b-a17b")

                assert isinstance(client, LLMClient)
                assert client.base_url == "http://127.0.0.1:8014/v1"
                assert client.api_key == "litserve-local"
                assert client.llm_provider == "provider_litserve"


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
                folder_id=None,
                max_tokens=None,
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
                folder_id=None,
                max_tokens=None,
                state=state,
            )


class TestLLMModelsServiceSchedulerIdempotency:
    @staticmethod
    def _schedule_model(payload: dict):
        from core.scheduler.models import PlatformScheduledTask

        return PlatformScheduledTask.model_validate(payload)

    @pytest.mark.asyncio
    async def test_start_background_sync_reuses_existing_pending_schedule(self):
        from apps.flows.src.services.llm_models_service import LLMModelsService

        repository = MagicMock()
        scheduler_client = AsyncMock()
        scheduler_client.list_schedules.return_value = [
            self._schedule_model({
                "id": "existing-task",
                "company_id": "system",
                "schedule_id": "sched-1",
                "target_service": "flows",
                "task_name": "sync_llm_models_task",
                "queue_name": "default",
                "schedule_type": "interval",
                "cron": None,
                "interval_seconds": 60,
                "run_at": None,
                "timezone": "UTC",
                "payload": {},
                "status": "pending",
                "created_by_user_id": "system",
                "created_at": "2026-03-29T00:00:00+00:00",
                "updated_at": "2026-03-29T00:00:00+00:00",
                "last_run_at": None,
                "next_run_at": None,
                "error_message": None,
            })
        ]
        service = LLMModelsService(repository, scheduler_client)

        await service.start_background_sync(interval=60)

        scheduler_client.create_schedule.assert_not_called()
        scheduler_client.resume_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_background_sync_resumes_paused_schedule(self):
        from apps.flows.src.services.llm_models_service import LLMModelsService

        repository = MagicMock()
        scheduler_client = AsyncMock()
        scheduler_client.list_schedules.return_value = [
            self._schedule_model({
                "id": "paused-task",
                "company_id": "system",
                "schedule_id": None,
                "target_service": "flows",
                "task_name": "sync_llm_models_task",
                "queue_name": "default",
                "schedule_type": "interval",
                "cron": None,
                "interval_seconds": 60,
                "run_at": None,
                "timezone": "UTC",
                "payload": {},
                "status": "paused",
                "created_by_user_id": "system",
                "created_at": "2026-03-29T00:00:00+00:00",
                "updated_at": "2026-03-29T00:00:00+00:00",
                "last_run_at": None,
                "next_run_at": None,
                "error_message": None,
            })
        ]
        scheduler_client.resume_schedule.return_value = self._schedule_model({
            "id": "paused-task",
            "company_id": "system",
            "schedule_id": "sched-resumed",
            "target_service": "flows",
            "task_name": "sync_llm_models_task",
            "queue_name": "default",
            "schedule_type": "interval",
            "cron": None,
            "interval_seconds": 60,
            "run_at": None,
            "timezone": "UTC",
            "payload": {},
            "status": "pending",
            "created_by_user_id": "system",
            "created_at": "2026-03-29T00:00:00+00:00",
            "updated_at": "2026-03-29T00:00:00+00:00",
            "last_run_at": None,
            "next_run_at": None,
            "error_message": None,
        })
        service = LLMModelsService(repository, scheduler_client)

        await service.start_background_sync(interval=60)

        scheduler_client.resume_schedule.assert_called_once_with("paused-task")
        scheduler_client.create_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_background_sync_raises_on_duplicates(self):
        from apps.flows.src.services.llm_models_service import LLMModelsService

        repository = MagicMock()
        scheduler_client = AsyncMock()
        scheduler_client.list_schedules.return_value = [
            self._schedule_model({
                "id": "task-1",
                "company_id": "system",
                "schedule_id": "sched-1",
                "target_service": "flows",
                "task_name": "sync_llm_models_task",
                "queue_name": "default",
                "schedule_type": "interval",
                "cron": None,
                "interval_seconds": 60,
                "run_at": None,
                "timezone": "UTC",
                "payload": {},
                "status": "pending",
                "created_by_user_id": "system",
                "created_at": "2026-03-29T00:00:00+00:00",
                "updated_at": "2026-03-29T00:00:00+00:00",
                "last_run_at": None,
                "next_run_at": None,
                "error_message": None,
            }),
            self._schedule_model({
                "id": "task-2",
                "company_id": "system",
                "schedule_id": "sched-2",
                "target_service": "flows",
                "task_name": "sync_llm_models_task",
                "queue_name": "default",
                "schedule_type": "interval",
                "cron": None,
                "interval_seconds": 60,
                "run_at": None,
                "timezone": "UTC",
                "payload": {},
                "status": "pending",
                "created_by_user_id": "system",
                "created_at": "2026-03-29T00:00:00+00:00",
                "updated_at": "2026-03-29T00:00:00+00:00",
                "last_run_at": None,
                "next_run_at": None,
                "error_message": None,
            }),
        ]
        service = LLMModelsService(repository, scheduler_client)

        with pytest.raises(ValueError, match="multiple LLM sync schedules"):
            await service.start_background_sync(interval=60)

    @pytest.mark.asyncio
    async def test_stop_background_sync_cancels_cached_schedule_id(self):
        from apps.flows.src.services.llm_models_service import LLMModelsService

        repository = MagicMock()
        scheduler_client = AsyncMock()
        scheduler_client.cancel_schedule.return_value = self._schedule_model({
            "id": "existing-task",
            "company_id": "system",
            "schedule_id": None,
            "target_service": "flows",
            "task_name": "sync_llm_models_task",
            "queue_name": "default",
            "schedule_type": "interval",
            "cron": None,
            "interval_seconds": 60,
            "run_at": None,
            "timezone": "UTC",
            "payload": {},
            "status": "cancelled",
            "created_by_user_id": "system",
            "created_at": "2026-03-29T00:00:00+00:00",
            "updated_at": "2026-03-29T00:00:00+00:00",
            "last_run_at": None,
            "next_run_at": None,
            "error_message": None,
        })
        service = LLMModelsService(repository, scheduler_client)
        service._sync_schedule_id = "existing-task"

        await service.stop_background_sync()

        scheduler_client.cancel_schedule.assert_called_once_with("existing-task")


class TestLLMModelsServiceProviderLitserve:
    @pytest.mark.asyncio
    async def test_fetch_provider_litserve_models_uses_service_scoped_settings(self):
        from apps.flows.src.services.llm_models_service import LLMModelsService
        from apps.flows.src.db.llm_model_repository import LLMModelRepository

        class _Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"id": "qwen/qwen3-embedding-4b"}, {"id": "qwen/qwen3-reranker-4b"}]}

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def get(self, url):
                assert url == "http://127.0.0.1:8014/v1/models"
                return _Response()

        repository = MagicMock(spec=LLMModelRepository)
        service = LLMModelsService(repository, AsyncMock())
        settings = MagicMock()
        settings.provider_litserve.resolve_openai_v1_base_url.return_value = "http://127.0.0.1:8014/v1"

        with patch("apps.flows.src.services.llm_models_service.get_settings", return_value=settings):
            with patch(
                "apps.flows.src.services.llm_models_service.get_httpx_client",
                return_value=_Client(),
            ):
                models = await service._fetch_provider_litserve_models()

        assert models == ["qwen/qwen3-embedding-4b", "qwen/qwen3-reranker-4b"]

    @pytest.mark.asyncio
    async def test_sync_all_providers_includes_provider_litserve_without_services_attr(self):
        from apps.flows.src.services.llm_models_service import LLMModelsService
        from apps.flows.src.db.llm_model_repository import LLMModelRepository

        repository = MagicMock(spec=LLMModelRepository)
        service = LLMModelsService(repository, AsyncMock())
        service.sync_models_by_provider = AsyncMock(return_value=2)
        settings = MagicMock()
        settings.llm.bothub = None
        settings.llm.openrouter = None
        settings.llm.openai = None
        settings.llm.yandex = None
        settings.provider_litserve.api.base_url = "http://127.0.0.1:8014/v1"

        with patch("apps.flows.src.services.llm_models_service.get_settings", return_value=settings):
            results = await service.sync_all_providers()

        assert results == {"provider_litserve": 2}
        service.sync_models_by_provider.assert_awaited_once_with("provider_litserve")


@pytest.mark.timeout(30)
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
        assert settings.llm.bothub and settings.llm.bothub.api_key, "BotHub API key не настроен в конфиге"
        
        mock_repo = MagicMock(spec=LLMModelRepository)
        service = LLMModelsService(mock_repo, AsyncMock())
        
        try:
            models = await service._fetch_bothub_models()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise AssertionError(
                    "BotHub API отклонил запрос (неверный или отозванный ключ, ограничение доступа)"
                ) from exc
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
        assert settings.llm.openrouter and settings.llm.openrouter.api_key, (
            "OpenRouter API key не настроен в конфиге"
        )
        
        mock_repo = MagicMock(spec=LLMModelRepository)
        service = LLMModelsService(mock_repo, AsyncMock())
        
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
        if not (settings.llm.openai and settings.llm.openai.api_key):
            pytest.skip("OpenAI не настроен: в LLMConfig нет openai или api_key")

        mock_repo = MagicMock(spec=LLMModelRepository)
        service = LLMModelsService(mock_repo, AsyncMock())

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
        if provider == "bothub":
            assert settings.llm.bothub and settings.llm.bothub.api_key, "BotHub API key не настроен"
        if provider == "openrouter":
            assert settings.llm.openrouter and settings.llm.openrouter.api_key, "OpenRouter API key не настроен"
        
        # Storage использует PostgreSQL напрямую из settings
        storage = Storage()
        repo = LLMModelRepository(storage)
        service = LLMModelsService(repo, AsyncMock())
        
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
        
        assert has_bothub or has_openrouter or has_openai, "Нет настроенных провайдеров (bothub/openrouter/openai)"
        
        storage = Storage()
        repo = LLMModelRepository(storage)
        service = LLMModelsService(repo, AsyncMock())
        
        # Синхронизируем ВСЕ провайдеры
        results = await service.sync_all_providers()
        
        assert isinstance(results, dict)
        total = sum(results.values())
        assert total > 0, "Должны синхронизироваться модели хотя бы от одного провайдера"
        
        print(f"Синхронизация всех провайдеров: {results}")
        print(f"Всего моделей: {total}")
        
        # Репозиторий только upsert; записи снятые с API не удаляются — в БД может быть больше строк.
        for provider, count in results.items():
            if count > 0:
                models = await service.get_models_by_provider(provider)
                assert len(models) >= count, (
                    f"В БД должно быть не меньше моделей {provider}, чем синхронизировано"
                )
                print(f"  {provider}: {count} моделей, примеры: {models[:3]}")

    @pytest.mark.asyncio
    async def test_bothub_models_response_structure(self):
        """
        Тест структуры ответа от BotHub API.
        Проверяем что парсим response правильно.
        """
        from apps.flows.config import get_settings
        
        settings = get_settings()
        assert settings.llm.bothub and settings.llm.bothub.api_key, "BotHub API key не настроен в конфиге"
        
        url = "https://bothub.chat/api/v2/model/list?children=1"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm.bothub.api_key}",
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code in (401, 403):
                pytest.fail(
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


class TestGetLLMYandex:
    def test_get_llm_yandex_sets_api_key_headers(self):
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "yandexgpt"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = None
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "yandex"
                mock_settings.return_value.llm.yandex = MagicMock(
                    api_key="AQVN-key",
                    folder_id="folder-1",
                    base_url="https://llm.api.cloud.yandex.net/v1",
                )
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = None
                mock_settings.return_value.provider_litserve = MagicMock()

                client = get_llm(model_name="yandexgpt")
                assert isinstance(client, LLMClient)
                assert client.default_headers["Authorization"] == "Api-Key AQVN-key"
                assert client.default_headers["x-folder-id"] == "folder-1"
                assert client.base_url == "https://llm.api.cloud.yandex.net/v1"

    def test_get_llm_yandex_missing_folder_raises(self):
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "m"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = None
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "yandex"
                mock_settings.return_value.llm.yandex = MagicMock(
                    api_key="AQVN-key",
                    folder_id="",
                    base_url="https://llm.api.cloud.yandex.net/v1",
                )
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = None
                mock_settings.return_value.provider_litserve = MagicMock()

                with pytest.raises(ValueError, match="folder_id"):
                    get_llm(model_name="m")

    def test_get_llm_yandex_custom_key_uses_override_folder_and_uri(self):
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "yandexgpt"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = None
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.yandex = MagicMock(
                    api_key="platform",
                    folder_id="platform-folder",
                    base_url="https://llm.api.cloud.yandex.net/v1",
                )
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = MagicMock(base_url="https://api.openai.com/v1")
                mock_settings.return_value.provider_litserve = MagicMock()

                client = get_llm(
                    model_name="gpt://other/yandexgpt-5.1/latest",
                    api_key="user-key",
                    provider="yandex",
                    base_url="https://llm.api.cloud.yandex.net/v1",
                    folder_id="user-folder",
                )
                assert isinstance(client, LLMClient)
                assert client.default_headers["x-folder-id"] == "user-folder"
                assert client.model == "gpt://user-folder/yandexgpt-5.1/latest"

    def test_get_llm_yandex_custom_key_falls_back_platform_folder(self):
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "yandexgpt"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = None
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.yandex = MagicMock(
                    api_key="platform",
                    folder_id="platform-folder",
                    base_url="https://llm.api.cloud.yandex.net/v1",
                )
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = MagicMock(base_url="https://api.openai.com/v1")
                mock_settings.return_value.provider_litserve = MagicMock()

                client = get_llm(
                    model_name="gpt://stale/yandexgpt-5.1/latest",
                    api_key="user-key",
                    provider="yandex",
                    base_url="https://llm.api.cloud.yandex.net/v1",
                )
                assert client.default_headers["x-folder-id"] == "platform-folder"
                assert client.model == "gpt://platform-folder/yandexgpt-5.1/latest"

    def test_get_llm_yandex_custom_key_without_any_folder_raises(self):
        with disable_testing_mode():
            with patch("core.clients.llm.factory.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "yandexgpt"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = None
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.yandex = None
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = MagicMock(base_url="https://api.openai.com/v1")
                mock_settings.return_value.provider_litserve = MagicMock()

                with pytest.raises(ValueError, match="folder_id"):
                    get_llm(
                        model_name="gpt://b1/x/y",
                        api_key="user-key",
                        provider="yandex",
                        base_url="https://llm.api.cloud.yandex.net/v1",
                    )

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

    def test_get_default_base_url_provider_litserve(self):
        """Возвращает base_url для provider_litserve."""
        mock_settings = MagicMock()
        mock_settings.provider_litserve.resolve_openai_v1_base_url.return_value = "http://127.0.0.1:8014/v1"

        result = _get_default_base_url("provider_litserve", mock_settings)
        assert result == "http://127.0.0.1:8014/v1"

    def test_get_default_base_url_yandex(self):
        mock_settings = MagicMock()
        mock_settings.llm.yandex = MagicMock(base_url="https://llm.api.cloud.yandex.net/v1")
        result = _get_default_base_url("yandex", mock_settings)
        assert result == "https://llm.api.cloud.yandex.net/v1"

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
