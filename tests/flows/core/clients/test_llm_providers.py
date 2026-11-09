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
from datetime import datetime, timezone
from typing import cast
from unittest.mock import MagicMock, patch

import httpx2
import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.models.enums import NodeType as RuntimeNodeType
from tests.fixtures.billing import make_test_billing_service


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


from apps.flows.src.runtime.execution_context import execution_context_for  # noqa: E402
from apps.flows.src.state import ExecutionState  # noqa: E402
from core.ai.llm_models_service import LLMModelsService  # noqa: E402
from core.ai.task_names import TASK_SYNC_LLM_MODELS  # noqa: E402
from core.clients.llm.client import LLMClient  # noqa: E402
from core.clients.llm.provider_resolution import (  # noqa: E402
    _detect_provider,
    _get_default_base_url,
    _resolve_var,
)
from core.clients.llm.runtime import (  # noqa: E402
    create_llm_transport_client as create_transport_llm_client,
)
from core.clients.scheduler_client import SchedulerClient  # noqa: E402
from core.config.models import YandexLLMProviderConfig  # noqa: E402
from core.context import clear_context  # noqa: E402
from core.scheduler.models import (  # noqa: E402
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)
from core.variables import VariableResolutionError  # noqa: E402


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

    def test_resolve_var_from_state_variables(self, unique_id):
        """@var:key резолвится из state.variables."""
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id="test:session",
            variables={"my_api_key": "sk-resolved-key"},
        )
        result = _resolve_var("@var:my_api_key", state.variables)
        assert result == "sk-resolved-key"

    def test_resolve_var_missing_key_raises_error(self, unique_id):
        """Отсутствующий ключ вызывает VariableResolutionError."""
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id="test:session",
            variables={"other_key": "value"},
        )
        with pytest.raises(VariableResolutionError):
            _resolve_var("@var:missing_key", state.variables)

    def test_resolve_var_no_state_raises_error(self):
        """@var: без state вызывает VariableResolutionError."""
        with pytest.raises(VariableResolutionError):
            _resolve_var("@var:my_key", None)

    def test_resolve_var_empty_variables_raises_error(self, unique_id):
        """@var: с пустыми variables вызывает VariableResolutionError."""
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id="test:session",
            variables={},
        )
        with pytest.raises(VariableResolutionError):
            _resolve_var("@var:my_key", state.variables)


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

    def test_detect_provider_none_for_litserve_rag_url(self):
        """LitServe больше не является LLM provider."""
        result = _detect_provider("http://127.0.0.1:8014/v1")
        assert result is None

    def test_detect_provider_yandex(self):
        result = _detect_provider("https://llm.api.cloud.yandex.net/v1")
        assert result == "yandex"

    @pytest.mark.parametrize(
        ("url", "provider"),
        [
            ("https://api.groq.com/openai/v1", "groq"),
            ("https://api.cerebras.ai/v1", "cerebras"),
            ("https://generativelanguage.googleapis.com/v1beta/openai", "google"),
            ("https://models.github.ai/inference", "github"),
            ("https://router.huggingface.co/v1", "huggingface"),
            ("https://integrate.api.nvidia.com/v1", "nvidia"),
            ("https://api.mistral.ai/v1", "mistral"),
            ("https://api.z.ai/api/paas/v4", "zai"),
            ("https://api.sambanova.ai/v1", "sambanova"),
            ("https://api.deepinfra.com/v1/openai", "deepinfra"),
        ],
    )
    def test_detect_provider_external_openai_compatible(self, url: str, provider: str):
        result = _detect_provider(url)
        assert result == provider

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


class TestLLMTransportWithCustomCredentials:
    """Тесты create_transport_llm_client с кастомными credentials."""

    def test_llm_transport_with_custom_api_key_creates_client(self):
        """create_transport_llm_client с кастомным api_key создает LLMClient с этим ключом."""
        with disable_testing_mode():
            with patch("core.clients.llm.runtime.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "gpt-4"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = 4096
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = MagicMock(
                    base_url="https://api.openai.com/v1"
                )

                client = create_transport_llm_client(
                    model_name="gpt-4",
                    api_key="sk-custom-user-key",
                    base_url="https://api.openai.com/v1",
        billing_service=make_test_billing_service(),
    )

                assert isinstance(client, LLMClient)
                assert client.api_key == "sk-custom-user-key"
                assert client.base_url == "https://api.openai.com/v1"
                assert client.model == "gpt-4"

    def test_llm_transport_with_var_resolved_from_state(self, unique_id):
        """create_transport_llm_client с @var: резолвит из state."""
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id="test:session",
            variables={
                "user_api_key": "sk-from-variable",
                "user_base_url": "https://bothub.chat/api/v2/openai/v1",
            },
        )

        with disable_testing_mode():
            with patch("core.clients.llm.runtime.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "gpt-4"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = 4096
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "bothub"
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = MagicMock(
                    base_url="https://bothub.chat/api/v2/openai/v1"
                )
                mock_settings.return_value.llm.openai = None

                client = create_transport_llm_client(
                    model_name="gpt-4",
                    api_key="@var:user_api_key",
                    base_url="@var:user_base_url",
                    variables=state.variables,
        billing_service=make_test_billing_service(),
    )

                assert isinstance(client, LLMClient)
                assert client.api_key == "sk-from-variable"
                assert client.base_url == "https://bothub.chat/api/v2/openai/v1"

    def test_llm_transport_detects_provider_from_base_url(self):
        """create_transport_llm_client определяет провайдера по base_url если не указан явно."""
        with disable_testing_mode():
            with patch("core.clients.llm.runtime.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "gpt-4"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = 4096
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.openrouter = MagicMock(
                    base_url="https://openrouter.ai/api/v1",
                    site_url="https://example.com",
                    site_name="Test",
                )
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = None

                client = create_transport_llm_client(
                    model_name="gpt-4",
                    api_key="sk-openrouter-key",
                    base_url="https://openrouter.ai/api/v1",
        billing_service=make_test_billing_service(),
    )

                assert isinstance(client, LLMClient)
                # Должны быть openrouter headers
                assert "HTTP-Referer" in client.default_headers

    def test_llm_transport_explicit_provider_overrides_detection(self):
        """Явно указанный provider имеет приоритет над auto-detection."""
        with disable_testing_mode():
            with patch("core.clients.llm.runtime.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "gpt-4"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = 4096
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = MagicMock(
                    base_url="https://bothub.chat/api/v2/openai/v1"
                )
                mock_settings.return_value.llm.openai = None

                client = create_transport_llm_client(
                    model_name="gpt-4",
                    api_key="sk-bothub-key",
                    base_url="https://bothub.chat/api/v2/openai/v1",
                    provider="bothub",
        billing_service=make_test_billing_service(),
    )

                assert isinstance(client, LLMClient)
                assert client.api_key == "sk-bothub-key"
                # Bothub не добавляет special headers
                assert "HTTP-Referer" not in client.default_headers


class TestLlmNodeLLMConfig:
    """Тесты передачи LLM конфига из LlmNode."""

    @pytest.mark.asyncio
    async def test_llm_node_passes_llm_config_to_factory(
        self,
        di: FlowsDi,
        unique_id,
    ):
        """LlmNode передает typed llm config в canonical AI runtime."""
        from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig, NodeType
        from apps.flows.src.runtime.nodes import LlmNode

        node_config = NodeConfig(
            node_id="test_node",
            type=NodeType.LLM_NODE,
            name="Test Node",
            prompt="Test prompt",
            llm=NodeLLMConfig(
                model="gpt-4-turbo",
                temperature=0.5,
                provider="bothub",
                api_key="sk-node-api-key",
                base_url="https://bothub.chat/api/v2/openai/v1",
            ),
        )

        node = LlmNode(
            node_id="test_node",
            config={"type": RuntimeNodeType.LLM_NODE.value, "prompt": "Test prompt"},
            execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, flow_factory=di.flow_factory, llm_context_memory_store=di.node_constructor.llm_context_memory_store, namespace_service=di.node_constructor.namespace_service, authz_service=di.node_constructor.authz_service, tool_registry=di.tool_registry, workflow_runtime=di.node_constructor.workflow_runtime, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, billing_service=di.node_constructor.billing_service,
        )
        node._node_config = node_config

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id="test:session",
        )

        with patch("apps.flows.src.runtime.nodes.create_llm_client_from_call_config") as mock_create_client:
            mock_create_client.return_value = MagicMock()

            clear_context()
            node._create_llm_client(state)

            mock_create_client.assert_called_once()
            config_arg = mock_create_client.call_args.args[0]
            assert {
                "model": config_arg.model,
                "temperature": config_arg.temperature,
                "provider": config_arg.provider,
                "api_key": config_arg.api_key,
                "base_url": config_arg.base_url,
                "folder_id": config_arg.folder_id,
                "max_tokens": config_arg.max_tokens,
                "variables": mock_create_client.call_args.kwargs["variables"],
                "fallback_models": mock_create_client.call_args.kwargs["fallback_models"],
            } == {
                "model": "gpt-4-turbo",
                "temperature": 0.5,
                "provider": "bothub",
                "api_key": "sk-node-api-key",
                "base_url": "https://bothub.chat/api/v2/openai/v1",
                "folder_id": None,
                "max_tokens": None,
                "variables": state.variables,
                "fallback_models": None,
            }

    @pytest.mark.asyncio
    async def test_llm_node_passes_llm_config_dict(
        self,
        di: FlowsDi,
        unique_id,
    ):
        """LlmNode передает llm_config_dict в canonical AI runtime."""
        from apps.flows.src.runtime.nodes import LlmNode

        llm_config = {
            "model": "claude-3",
            "temperature": 0.7,
            "provider": "openrouter",
            "api_key": "@var:my_key",
            "base_url": "@var:my_url",
        }

        node = LlmNode(
            node_id="test_node",
            config={
                "type": RuntimeNodeType.LLM_NODE.value,
                "prompt": "Test prompt",
                "llm": llm_config,
            },
            execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, flow_factory=di.flow_factory, llm_context_memory_store=di.node_constructor.llm_context_memory_store, namespace_service=di.node_constructor.namespace_service, authz_service=di.node_constructor.authz_service, tool_registry=di.tool_registry, workflow_runtime=di.node_constructor.workflow_runtime, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, billing_service=di.node_constructor.billing_service,
        )

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id="test:session",
            variables={"my_key": "sk-variable-key", "my_url": "https://openrouter.ai/api/v1"},
        )

        with patch("apps.flows.src.runtime.nodes.create_llm_client_from_call_config") as mock_create_client:
            mock_create_client.return_value = MagicMock()

            clear_context()
            node._create_llm_client(state)

            mock_create_client.assert_called_once()
            config_arg = mock_create_client.call_args.args[0]
            assert {
                "model": config_arg.model,
                "temperature": config_arg.temperature,
                "provider": config_arg.provider,
                "api_key": config_arg.api_key,
                "base_url": config_arg.base_url,
                "folder_id": config_arg.folder_id,
                "max_tokens": config_arg.max_tokens,
                "variables": mock_create_client.call_args.kwargs["variables"],
                "fallback_models": mock_create_client.call_args.kwargs["fallback_models"],
            } == {
                "model": "claude-3",
                "temperature": 0.7,
                "provider": "openrouter",
                "api_key": "@var:my_key",
                "base_url": "@var:my_url",
                "folder_id": None,
                "max_tokens": None,
                "variables": state.variables,
                "fallback_models": None,
            }


def _llm_sync_interval(unique_id: str) -> int:
    return 10_000 + int(unique_id[:4], 16)


def _llm_sync_service(di: FlowsDi) -> LLMModelsService:
    return LLMModelsService(SchedulerClient(), di.redis_client)


async def _create_llm_sync_schedule(
    client: SchedulerClient,
    interval_seconds: int,
) -> PlatformScheduledTask:
    return await client.create_schedule(
        PlatformScheduleCreateRequest(
            target_service="flows",
            task_name=TASK_SYNC_LLM_MODELS.name,
            queue_name=TASK_SYNC_LLM_MODELS.queue,
            schedule_type=PlatformScheduleType.INTERVAL,
            interval_seconds=interval_seconds,
            payload={"system_task": "llm_models_background_sync"},
            timezone="UTC",
            run_at=datetime.now(timezone.utc),
        )
    )


async def _open_llm_sync_schedules(
    client: SchedulerClient,
    interval_seconds: int,
) -> list[PlatformScheduledTask]:
    page = await client.list_schedules(
        PlatformScheduleFilter(
            target_service="flows",
            task_name=TASK_SYNC_LLM_MODELS.name,
            limit=500,
            offset=0,
        )
    )
    return [
        task
        for task in page.items
        if task.interval_seconds == interval_seconds
        and task.schedule_type == PlatformScheduleType.INTERVAL
        and task.status in {ScheduledTaskStatus.PENDING, ScheduledTaskStatus.PAUSED}
    ]


async def _cancel_llm_sync_schedule(client: SchedulerClient, schedule_task_id: str) -> None:
    current = await client.get_schedule(schedule_task_id)
    if current.status == ScheduledTaskStatus.CANCELLED:
        return
    _ = await client.cancel_schedule(schedule_task_id)


class TestLLMModelsServiceSchedulerIdempotency:
    @pytest.mark.asyncio
    async def test_start_background_sync_reuses_existing_pending_schedule(
        self,
        di: FlowsDi,
        unique_id: str,
    ) -> None:
        client = SchedulerClient()
        interval_seconds = _llm_sync_interval(unique_id)
        created = await _create_llm_sync_schedule(client, interval_seconds)
        service = _llm_sync_service(di)
        try:
            before = [
                task.schedule_task_id
                for task in await _open_llm_sync_schedules(client, interval_seconds)
            ]
            await service.start_background_sync(interval=interval_seconds)
            after = [
                task.schedule_task_id
                for task in await _open_llm_sync_schedules(client, interval_seconds)
            ]
            current = await client.get_schedule(created.schedule_task_id)
        finally:
            await _cancel_llm_sync_schedule(client, created.schedule_task_id)

        assert before == [created.schedule_task_id]
        assert after == before
        assert service._sync_schedule_task_id == created.schedule_task_id
        assert current.status == ScheduledTaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_start_background_sync_resumes_paused_schedule(
        self,
        di: FlowsDi,
        unique_id: str,
    ) -> None:
        client = SchedulerClient()
        interval_seconds = _llm_sync_interval(unique_id)
        created = await _create_llm_sync_schedule(client, interval_seconds)
        service = _llm_sync_service(di)
        try:
            paused = await client.pause_schedule(created.schedule_task_id)
            assert paused.status == ScheduledTaskStatus.PAUSED
            await service.start_background_sync(interval=interval_seconds)
            current = await client.get_schedule(created.schedule_task_id)
            open_ids = [
                task.schedule_task_id
                for task in await _open_llm_sync_schedules(client, interval_seconds)
            ]
        finally:
            await _cancel_llm_sync_schedule(client, created.schedule_task_id)

        assert current.status == ScheduledTaskStatus.PENDING
        assert current.schedule_task_id == created.schedule_task_id
        assert service._sync_schedule_task_id == created.schedule_task_id
        assert open_ids == [created.schedule_task_id]

    @pytest.mark.asyncio
    async def test_start_background_sync_raises_on_duplicates(
        self,
        di: FlowsDi,
        unique_id: str,
    ) -> None:
        client = SchedulerClient()
        interval_seconds = _llm_sync_interval(unique_id)
        first = await _create_llm_sync_schedule(client, interval_seconds)
        second = await _create_llm_sync_schedule(client, interval_seconds)
        service = _llm_sync_service(di)
        try:
            with pytest.raises(ValueError, match="multiple LLM sync schedules"):
                await service.start_background_sync(interval=interval_seconds)
        finally:
            await _cancel_llm_sync_schedule(client, first.schedule_task_id)
            await _cancel_llm_sync_schedule(client, second.schedule_task_id)

    @pytest.mark.asyncio
    async def test_stop_background_sync_cancels_cached_schedule_id(
        self,
        di: FlowsDi,
        unique_id: str,
    ) -> None:
        client = SchedulerClient()
        interval_seconds = _llm_sync_interval(unique_id)
        created = await _create_llm_sync_schedule(client, interval_seconds)
        service = _llm_sync_service(di)
        service._sync_schedule_task_id = created.schedule_task_id
        await service.stop_background_sync()
        current = await client.get_schedule(created.schedule_task_id)

        assert current.status == ScheduledTaskStatus.CANCELLED
        assert service._sync_schedule_task_id is None


@pytest.mark.network
@pytest.mark.timeout(120)
class TestLLMModelsServiceRealAPI:
    """
    Реальные тесты синхронизации моделей от провайдеров.
    Ходят к настоящим API endpoint'ам.
    """

    @pytest.mark.asyncio
    async def test_fetch_bothub_models_real_api(self, di: FlowsDi) -> None:
        """
        Реальный запрос к BotHub API для получения списка моделей.
        Использует endpoint: https://bothub.chat/api/v2/model/list?children=1
        """
        from apps.flows.config import get_settings

        settings = get_settings()
        assert settings.llm.bothub and settings.llm.bothub.api_key, (
            "BotHub API key не настроен в конфиге"
        )

        service = di.llm_models_service

        try:
            models = await service.fetch_models_by_provider("bothub")
        except httpx2.HTTPStatusError as exc:
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
    async def test_fetch_openrouter_models_real_api(self, di: FlowsDi) -> None:
        """
        Реальный запрос к OpenRouter API для получения списка моделей.
        Использует endpoint: {base_url}/models
        """
        from apps.flows.config import get_settings

        settings = get_settings()
        assert settings.llm.openrouter and settings.llm.openrouter.api_key, (
            "OpenRouter API key не настроен в конфиге"
        )

        service = di.llm_models_service

        try:
            models = await service.fetch_models_by_provider("openrouter")
        except httpx2.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                pytest.skip(
                    "OpenRouter API отклонил запрос (неверный или отозванный ключ, ограничение доступа)"
                )
            raise

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
    async def test_fetch_openai_models_real_api(self, di: FlowsDi) -> None:
        """
        Реальный запрос к OpenAI API для получения списка моделей.
        Использует endpoint: {base_url}/models
        """
        from apps.flows.config import get_settings

        settings = get_settings()
        if not (settings.llm.openai and settings.llm.openai.api_key):
            pytest.skip("OpenAI не настроен: в LLMConfig нет openai или api_key")

        service = di.llm_models_service

        models = await service.fetch_models_by_provider("openai")

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

        assert has_gpt or has_davinci or has_whisper or has_embedding, (
            "OpenAI должен содержать GPT, Davinci, Whisper или Embedding модели"
        )

        print(f"OpenAI вернул {len(models)} моделей")
        print(f"Примеры моделей: {models[:10]}")

    @pytest.mark.asyncio
    async def test_sync_models_saves_correct_provider(self, di: FlowsDi) -> None:
        """
        Полный цикл синхронизации: fetch от реального API и сохранение в БД.
        """
        from apps.flows.config import get_settings
        from core.ai.models import AIModelRecord

        settings = get_settings()
        provider = settings.llm.provider

        # Проверяем что провайдер настроен
        if provider == "bothub":
            assert settings.llm.bothub and settings.llm.bothub.api_key, "BotHub API key не настроен"
        if provider == "openrouter":
            if not (settings.llm.openrouter and settings.llm.openrouter.api_key):
                pytest.skip("OpenRouter API key не настроен")
            try:
                probe_service = di.llm_models_service
                await probe_service.fetch_models_by_provider("openrouter")
            except httpx2.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403):
                    pytest.skip(
                        "OpenRouter API отклонил запрос (неверный или отозванный ключ, ограничение доступа)"
                    )
                raise

        service = di.llm_models_service

        # Синхронизируем
        count = await service.sync_models()

        assert count > 0, f"Должны синхронизироваться модели от {provider}"

        # Проверяем что модели сохранились в БД
        saved_models = await AIModelRecord.list_unordered_by_provider(provider)

        assert len(saved_models) > 0
        for model in saved_models:
            assert model.provider == provider
            assert isinstance(model.model_id, str)
            assert len(model.model_id) > 0

        print(f"Синхронизировано {count} моделей от {provider}")
        print(f"В БД сохранено {len(saved_models)} моделей")

    @pytest.mark.asyncio
    async def test_sync_all_providers_real_api(self, di: FlowsDi) -> None:
        """
        Синхронизация моделей от ВСЕХ настроенных провайдеров.
        """
        from apps.flows.config import get_settings
        from core.ai.models import AIModelRecord

        settings = get_settings()

        # Проверяем что хотя бы один провайдер настроен
        has_bothub = settings.llm.bothub and settings.llm.bothub.api_key
        has_openrouter = settings.llm.openrouter and settings.llm.openrouter.api_key
        has_openai = settings.llm.openai and settings.llm.openai.api_key

        assert has_bothub or has_openrouter or has_openai, (
            "Нет настроенных провайдеров (bothub/openrouter/openai)"
        )

        service = di.llm_models_service

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
                models = await AIModelRecord.list_unordered_by_provider(provider)
                assert len(models) >= count, (
                    f"В БД должно быть не меньше моделей {provider}, чем синхронизировано"
                )
                print(
                    f"  {provider}: {count} моделей, "
                    f"примеры: {[model.model_id for model in models[:3]]}"
                )

    @pytest.mark.asyncio
    async def test_bothub_models_response_structure(self, di: FlowsDi) -> None:
        """
        Тест структуры ответа от BotHub API.
        Проверяем что парсим response правильно.
        """
        from apps.flows.config import get_settings

        settings = get_settings()
        assert settings.llm.bothub and settings.llm.bothub.api_key, (
            "BotHub API key не настроен в конфиге"
        )

        service = di.llm_models_service
        records = await service.discover_model_records_by_provider("bothub")

        assert records, "Должны извлечь хотя бы одну модель"
        assert all(record.provider == "bothub" for record in records)
        assert all(record.model_id.strip() for record in records)
        print(f"Извлечено {len(records)} моделей: {[record.model_id for record in records[:10]]}...")


class TestLLMTransportYandex:
    def test_llm_transport_yandex_sets_api_key_headers(self):
        with disable_testing_mode():
            with patch("core.clients.llm.runtime.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "yandexgpt"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = None
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "yandex"
                mock_settings.return_value.llm.yandex = YandexLLMProviderConfig(
                    api_key="AQVN-key",
                    folder_id="folder-1",
                    base_url="https://llm.api.cloud.yandex.net/v1",
                )
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = None
                mock_settings.return_value.llm.platform_free_pool.enabled = False
                client = create_transport_llm_client(model_name="yandexgpt",
        billing_service=make_test_billing_service())
                assert isinstance(client, LLMClient)
                assert client.default_headers["Authorization"] == "Api-Key AQVN-key"
                assert client.default_headers["x-folder-id"] == "folder-1"
                assert client.base_url == "https://llm.api.cloud.yandex.net/v1"

    def test_llm_transport_yandex_missing_folder_raises(self):
        with disable_testing_mode():
            with patch("core.clients.llm.runtime.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "m"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = None
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "yandex"
                mock_settings.return_value.llm.yandex = YandexLLMProviderConfig(
                    api_key="AQVN-key",
                    folder_id="",
                    base_url="https://llm.api.cloud.yandex.net/v1",
                )
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = None
                mock_settings.return_value.llm.platform_free_pool.enabled = False
                with pytest.raises(ValueError, match="folder_id"):
                    create_transport_llm_client(model_name="m",
        billing_service=make_test_billing_service())

    def test_llm_transport_yandex_custom_key_uses_override_folder_and_uri(self):
        with disable_testing_mode():
            with patch("core.clients.llm.runtime.get_settings") as mock_settings:
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
                mock_settings.return_value.llm.openai = MagicMock(
                    base_url="https://api.openai.com/v1"
                )
                client = create_transport_llm_client(
                    model_name="gpt://other/yandexgpt-5.1/latest",
                    api_key="user-key",
                    provider="yandex",
                    base_url="https://llm.api.cloud.yandex.net/v1",
                    folder_id="user-folder",
        billing_service=make_test_billing_service(),
    )
                assert isinstance(client, LLMClient)
                assert client.default_headers["x-folder-id"] == "user-folder"
                assert client.model == "gpt://user-folder/yandexgpt-5.1/latest"

    def test_llm_transport_yandex_custom_key_falls_back_platform_folder(self):
        with disable_testing_mode():
            with patch("core.clients.llm.runtime.get_settings") as mock_settings:
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
                mock_settings.return_value.llm.openai = MagicMock(
                    base_url="https://api.openai.com/v1"
                )
                client = cast(
                    LLMClient,
                    create_transport_llm_client(
                        model_name="gpt://stale/yandexgpt-5.1/latest",
                        api_key="user-key",
                        provider="yandex",
                        base_url="https://llm.api.cloud.yandex.net/v1",
        billing_service=make_test_billing_service(),
    ),
                )
                assert client.default_headers["x-folder-id"] == "platform-folder"
                assert client.model == "gpt://platform-folder/yandexgpt-5.1/latest"

    def test_llm_transport_yandex_custom_key_without_any_folder_raises(self):
        with disable_testing_mode():
            with patch("core.clients.llm.runtime.get_settings") as mock_settings:
                mock_settings.return_value.llm.default_model = "yandexgpt"
                mock_settings.return_value.llm.models = {}
                mock_settings.return_value.llm.temperature = 0.2
                mock_settings.return_value.llm.max_tokens = None
                mock_settings.return_value.llm.timeout = 120.0
                mock_settings.return_value.llm.provider = "openai"
                mock_settings.return_value.llm.yandex = None
                mock_settings.return_value.llm.openrouter = None
                mock_settings.return_value.llm.bothub = None
                mock_settings.return_value.llm.openai = MagicMock(
                    base_url="https://api.openai.com/v1"
                )
                with pytest.raises(ValueError, match="folder_id"):
                    create_transport_llm_client(
                        model_name="gpt://b1/x/y",
                        api_key="user-key",
                        provider="yandex",
                        base_url="https://llm.api.cloud.yandex.net/v1",
        billing_service=make_test_billing_service(),
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

    def test_get_default_base_url_yandex(self):
        mock_settings = MagicMock()
        mock_settings.llm.yandex = MagicMock(base_url="https://llm.api.cloud.yandex.net/v1")
        result = _get_default_base_url("yandex", mock_settings)
        assert result == "https://llm.api.cloud.yandex.net/v1"

    @pytest.mark.parametrize(
        ("provider", "url"),
        [
            ("groq", "https://api.groq.com/openai/v1"),
            ("cerebras", "https://api.cerebras.ai/v1"),
            ("google", "https://generativelanguage.googleapis.com/v1beta/openai"),
            ("github", "https://models.github.ai/inference"),
            ("huggingface", "https://router.huggingface.co/v1"),
            ("nvidia", "https://integrate.api.nvidia.com/v1"),
            ("mistral", "https://api.mistral.ai/v1"),
            ("zai", "https://api.z.ai/api/paas/v4"),
            ("sambanova", "https://api.sambanova.ai/v1"),
            ("deepinfra", "https://api.deepinfra.com/v1/openai"),
        ],
    )
    def test_get_default_base_url_external_provider(self, provider: str, url: str):
        mock_settings = MagicMock()
        setattr(mock_settings.llm, provider, MagicMock(base_url=url))
        result = _get_default_base_url(provider, mock_settings)
        assert result == url

    def test_get_default_base_url_unknown_provider_raises(self):
        """Неизвестный провайдер не подменяется OpenAI."""
        mock_settings = MagicMock()

        with pytest.raises(ValueError, match="Unknown LLM provider"):
            _get_default_base_url("unknown", mock_settings)

    def test_get_default_base_url_no_config(self):
        """Fallback если конфиг провайдера не настроен."""
        mock_settings = MagicMock()
        mock_settings.llm.openrouter = None

        result = _get_default_base_url("openrouter", mock_settings)
        assert result == "https://openrouter.ai/api/v1"
