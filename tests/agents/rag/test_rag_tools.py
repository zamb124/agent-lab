"""
Тесты для RAG инструментов для агентов.
"""

import uuid
import pytest
import pytest_asyncio

from apps.agents.models import FlowConfig
from core.rag.models import AgentRAGConfig


class TestGetRagConfigFromContext:
    """Тесты для получения RAG конфигурации из контекста"""
    
    def test_flow_config_rag(self, test_context):
        """Flow конфигурация используется"""
        from apps.agents.tools.misc.rag_tools import _get_rag_config_from_context
        
        flow_rag = AgentRAGConfig(
            enabled=True,
            namespace_scope="flow",
            search_scopes=["flow"]
        )
        
        test_context.flow_config = FlowConfig(
            flow_id="test",
            name="Test",
            entry_point_agent="test",
            source="test",
            rag_config=flow_rag
        )
        test_context.agent_config = None
        
        rag_config = _get_rag_config_from_context(test_context)
        
        assert rag_config is not None
        assert rag_config.enabled is True
        assert rag_config.namespace_scope == "flow"
    
    def test_no_rag_config(self, test_context):
        """Возвращает дефолт если RAG явно не отключен"""
        from apps.agents.tools.misc.rag_tools import _get_rag_config_from_context
        
        # FlowConfig с rag_config=None создаст дефолтный конфиг через валидатор
        test_context.flow_config = FlowConfig(
            flow_id="test",
            name="Test",
            entry_point_agent="test",
            source="test"
        )
        test_context.agent_config = None
        
        rag_config = _get_rag_config_from_context(test_context)
        
        # Из-за валидатора ensure_rag_config возвращается дефолт
        assert rag_config is not None
        assert rag_config.enabled is True


@pytest.mark.integration
class TestKnowledgeBaseAPI:
    """Интеграционные тесты для API endpoints базы знаний"""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup_rag_provider(self):
        """Очистка RAG провайдера после каждого теста"""
        yield
        from core.rag.factory import close_default_rag_provider
        await close_default_rag_provider()

    @pytest.mark.asyncio
    async def test_upload_text_success(self, frontend_client, frontend_flow_repo):
        """Тест успешной загрузки текста через API"""
        flow_id = f"test_flow_{uuid.uuid4().hex[:8]}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Flow",
            entry_point_agent="test.agent",
            source="test",
            rag_config=AgentRAGConfig(
                enabled=True,
                namespace_scope="flow",
                search_scopes=["flow"]
            )
        )
        await frontend_flow_repo.set(flow_config)

        text_content = "Это тестовый текст для загрузки в базу знаний"
        document_name = "test_document.txt"

        response = await frontend_client.post(
            f"/frontend/api/knowledge-base/flows/{flow_id}/text",
            json={
                "text": text_content,
                "document_name": document_name,
                "description": "Тестовый документ"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == document_name
        assert data["status"] == "processing"
        assert "document_id" in data

    @pytest.mark.asyncio
    async def test_upload_text_flow_not_found(self, frontend_client):
        """Тест загрузки текста для несуществующего flow"""
        response = await frontend_client.post(
            "/frontend/api/knowledge-base/flows/nonexistent_flow/text",
            json={
                "text": "test text",
                "document_name": "test.txt"
            }
        )

        assert response.status_code == 404
        assert "не найден" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_flow_documents(self, frontend_client, frontend_flow_repo):
        """Тест получения списка документов flow"""
        flow_id = f"test_flow_{uuid.uuid4().hex[:8]}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Flow",
            entry_point_agent="test.agent",
            source="test",
            rag_config=AgentRAGConfig(
                enabled=True,
                namespace_scope="flow",
                search_scopes=["flow"]
            )
        )
        await frontend_flow_repo.set(flow_config)

        response = await frontend_client.get(f"/frontend/api/knowledge-base/flows/{flow_id}/documents")

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total" in data
        assert isinstance(data["documents"], list)
