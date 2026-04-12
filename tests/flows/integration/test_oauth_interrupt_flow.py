"""
Сквозной интеграционный тест OAuth FlowInterrupt + auto-resume.

Сценарий:
  1. flow с LlmNode + gdocs_create_document как tool
  2. MockLLM вызывает tool -> _resolve_gdocs_client бросает FlowInterrupt(OAuthInterrupt)
  3. Проверяем state.interrupt
  4. Эмулируем callback: вставляем credential в БД
  5. Resume flow (state.content="oauth_completed:google:docs")
  6. MockLLM снова вызывает tool -> credential найден -> GoogleDocsClient мокнут
  7. MockLLM возвращает финальный текст
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.integrations.repository import IntegrationCredentialRepository
from core.state import ExecutionState, InterruptKind


@pytest.fixture()
def credential_repository(app) -> IntegrationCredentialRepository:
    from core.config import get_settings
    settings = get_settings()
    return IntegrationCredentialRepository(db_url=settings.database.shared_url)


def _disable_gdocs_mock(monkeypatch) -> None:
    """Выключает mock_response у gdocs_create_document чтобы шёл реальный _run_impl."""
    from apps.flows.tools.google_docs import gdocs_create_document
    monkeypatch.setattr(gdocs_create_document, "_mock_response", None)


def _build_flow_config(flow_id: str) -> FlowConfig:
    return FlowConfig(
        flow_id=flow_id,
        name="OAuth Test Flow",
        entry="main",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "Ты ассистент. Используй gdocs_create_document для создания документа.",
                "tools": [
                    {"tool_id": "gdocs_create_document"},
                ],
            },
        },
        edges=[
            {"from_node": "main", "to_node": None},
        ],
    )


def _patch_oauth_config(monkeypatch) -> None:
    from core.config import get_settings
    from core.config.models import AuthConfig, AuthProviderConfig

    settings = get_settings()
    auth = AuthConfig(
        providers={
            "google": AuthProviderConfig(
                client_id="test-client-id",
                client_secret="test-secret",
                auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",
            ),
        },
    )
    monkeypatch.setattr(settings, "auth", auth)


async def _fake_create_document(self: Any, title: str, body_content: str = "") -> dict[str, Any]:
    return {
        "documentId": "fake-doc-id",
        "title": title,
    }


class TestOAuthInterruptFlow:
    @pytest.mark.asyncio
    async def test_flow_raises_oauth_interrupt_when_no_credential(
        self,
        app,
        mock_llm_with_queue,
        credential_repository,
        unique_id,
        monkeypatch,
    ) -> None:
        """
        Flow с gdocs tool без credentials -> FlowInterrupt(OAuthInterrupt).
        """
        _patch_oauth_config(monkeypatch)
        _disable_gdocs_mock(monkeypatch)

        await credential_repository.delete_by_user_provider_service(
            company_id="system",
            user_id="test_user",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "gdocs_create_document",
                "args": {"title": "Test Doc"},
            },
        ])

        container = get_container()
        flow_id = f"oauth-test-{unique_id}"
        flow_config = _build_flow_config(flow_id)
        flow = await container.flow_factory.create_flow(flow_config)

        state = ExecutionState(
            task_id=f"task-{unique_id}",
            context_id=f"ctx-{unique_id}",
            user_id=f"user-oauth-{unique_id}",
            session_id=f"{flow_id}:ctx-{unique_id}",
            content="Создай документ Test Doc",
        )

        flow.variables = {}

        result = await flow.run(state)

        assert result.interrupt is not None, "state.interrupt должен быть установлен"
        assert result.interrupt.body.kind == InterruptKind.OAUTH_REQUIRED
        assert result.interrupt.body.provider == "google"
        assert result.interrupt.body.service == "docs"
        assert "accounts.google.com" in result.interrupt.body.auth_url

    @pytest.mark.asyncio
    async def test_flow_resumes_after_oauth_credential_inserted(
        self,
        app,
        mock_llm_with_queue,
        credential_repository,
        unique_id,
        monkeypatch,
    ) -> None:
        """
        Полный цикл: interrupt -> вставка credential -> resume -> успех.
        """
        _patch_oauth_config(monkeypatch)
        _disable_gdocs_mock(monkeypatch)

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "gdocs_create_document",
                "args": {"title": "Resume Doc"},
            },
            {
                "type": "tool_call",
                "tool": "gdocs_create_document",
                "args": {"title": "Resume Doc"},
            },
            "Документ создан: Resume Doc",
        ])

        context_user_id = "test_user"
        context_company_id = "system"

        container = get_container()
        flow_id = f"oauth-resume-{unique_id}"
        flow_config = _build_flow_config(flow_id)
        flow = await container.flow_factory.create_flow(flow_config)

        state = ExecutionState(
            task_id=f"task-{unique_id}",
            context_id=f"ctx-{unique_id}",
            user_id=context_user_id,
            session_id=f"{flow_id}:ctx-{unique_id}",
            content="Создай документ Resume Doc",
        )

        flow.variables = {}

        result = await flow.run(state)

        assert result.interrupt is not None
        assert result.interrupt.body.kind == InterruptKind.OAUTH_REQUIRED

        now = datetime.now(timezone.utc)
        credential = IntegrationCredential(
            credential_id=f"cred-oauth-{unique_id}",
            company_id=context_company_id,
            user_id=context_user_id,
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token="test-access-token-for-resume",
            refresh_token="test-refresh-token",
            expires_at=now + timedelta(hours=1),
            created_at=now,
            updated_at=now,
        )
        await credential_repository.upsert(credential)

        monkeypatch.setattr(
            "core.clients.google_docs_client.GoogleDocsClient.create_document",
            _fake_create_document,
        )

        result.content = "oauth_completed:google:docs"

        resumed = await flow.run(result)

        assert resumed.interrupt is None, \
            f"interrupt должен быть None после resume, получили: {resumed.interrupt}"
        assert resumed.response is not None
        assert "Resume Doc" in resumed.response or "Документ создан" in resumed.response
