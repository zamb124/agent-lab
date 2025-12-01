"""
Тесты для API knowledge_base.

Используется реальная БД и RAG провайдер (Agentset).
Тесты пропускаются если RAG не настроен.
"""

import uuid
import pytest
import pytest_asyncio

from apps.agents.models import FlowConfig, AgentConfig, AgentType, CodeMode, LLMConfig


def make_unique_id(prefix: str) -> str:
    """Генерирует уникальный ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def is_rag_enabled() -> bool:
    """Проверяет доступность RAG"""
    try:
        from core.config import get_settings
        settings = get_settings()
        return settings.rag.enabled
    except Exception:
        return False


# Пропускаем все тесты если RAG не настроен
pytestmark = pytest.mark.skipif(
    not is_rag_enabled(),
    reason="RAG не настроен (rag.enabled = false)"
)


@pytest_asyncio.fixture
async def kb_test_agent(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент для flow базы знаний"""
    from core.context import set_context
    set_context(frontend_client.test_context)
    
    agent_id = make_unique_id("kb_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="Knowledge Base Test Agent",
        description="Agent for KB testing",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are a test agent with knowledge base",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test"
    )
    await frontend_agent_repo.set(agent)
    yield agent
    set_context(frontend_client.test_context)
    await frontend_agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def kb_test_flow(frontend_flow_repo, kb_test_agent, frontend_client) -> FlowConfig:
    """Тестовый flow для тестов базы знаний"""
    from core.context import set_context
    set_context(frontend_client.test_context)
    
    flow_id = make_unique_id("kb_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Knowledge Base Test Flow",
        description="Flow for KB testing",
        entry_point_agent=kb_test_agent.agent_id,
        source="test",
        canvas_data=None,
        rag_config=None
    )
    await frontend_flow_repo.set(flow)
    yield flow
    set_context(frontend_client.test_context)
    await frontend_flow_repo.delete(flow_id)


class TestKnowledgeBaseDocumentsList:
    """Тесты для GET /frontend/api/knowledge-base/flows/{flow_id}/documents"""
    
    @pytest.mark.asyncio
    async def test_list_documents_empty(self, frontend_client, kb_test_flow):
        """Проверяем получение пустого списка документов"""
        response = await frontend_client.get(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/documents"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "documents" in data
        assert "total" in data
        assert isinstance(data["documents"], list)
        assert isinstance(data["total"], int)
    
    @pytest.mark.asyncio
    async def test_list_documents_flow_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего flow"""
        response = await frontend_client.get(
            "/frontend/api/knowledge-base/flows/nonexistent_flow_123/documents"
        )
        
        assert response.status_code == 404


class TestKnowledgeBaseUploadText:
    """Тесты для POST /frontend/api/knowledge-base/flows/{flow_id}/text"""
    
    @pytest.mark.asyncio
    async def test_upload_text_success(self, frontend_client, kb_test_flow):
        """Проверяем загрузку текста в базу знаний"""
        text_data = {
            "text": "Это тестовый документ для проверки базы знаний. "
                    "Он содержит информацию о работе системы.",
            "document_name": "test_document.txt",
            "description": "Test document for KB"
        }
        
        response = await frontend_client.post(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/text",
            json=text_data
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "document_id" in data
        assert data["name"] == "test_document.txt"
        assert data["status"] == "processing"
    
    @pytest.mark.asyncio
    async def test_upload_text_without_name(self, frontend_client, kb_test_flow):
        """Проверяем загрузку текста без указания имени"""
        text_data = {
            "text": "Короткий тестовый текст для проверки автоматического имени."
        }
        
        response = await frontend_client.post(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/text",
            json=text_data
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "document_id" in data
        assert data["status"] == "processing"
    
    @pytest.mark.asyncio
    async def test_upload_text_flow_not_found(self, frontend_client):
        """Проверяем 404 при загрузке в несуществующий flow"""
        text_data = {
            "text": "Test text",
            "document_name": "test.txt"
        }
        
        response = await frontend_client.post(
            "/frontend/api/knowledge-base/flows/nonexistent_flow_123/text",
            json=text_data
        )
        
        assert response.status_code == 404


class TestKnowledgeBaseUploadDocument:
    """Тесты для POST /frontend/api/knowledge-base/flows/{flow_id}/documents"""
    
    @pytest.mark.asyncio
    async def test_upload_txt_file(self, frontend_client, kb_test_flow):
        """Проверяем загрузку TXT файла"""
        file_content = b"This is a test document content.\nIt has multiple lines."
        
        files = {
            "file": ("test_document.txt", file_content, "text/plain")
        }
        
        response = await frontend_client.post(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/documents",
            files=files
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "document_id" in data
        assert data["name"] == "test_document.txt"
        assert data["status"] == "processing"
    
    @pytest.mark.asyncio
    async def test_upload_md_file(self, frontend_client, kb_test_flow):
        """Проверяем загрузку Markdown файла"""
        file_content = b"# Test Document\n\nThis is a **markdown** file.\n\n- Item 1\n- Item 2"
        
        files = {
            "file": ("readme.md", file_content, "text/markdown")
        }
        
        response = await frontend_client.post(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/documents",
            files=files
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "document_id" in data
        assert data["name"] == "readme.md"
    
    @pytest.mark.asyncio
    async def test_upload_document_flow_not_found(self, frontend_client):
        """Проверяем 404 при загрузке в несуществующий flow"""
        file_content = b"Test content"
        
        files = {
            "file": ("test.txt", file_content, "text/plain")
        }
        
        response = await frontend_client.post(
            "/frontend/api/knowledge-base/flows/nonexistent_flow_123/documents",
            files=files
        )
        
        assert response.status_code == 404


class TestKnowledgeBaseDeleteDocument:
    """Тесты для DELETE /frontend/api/knowledge-base/flows/{flow_id}/documents/{document_id}"""
    
    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, frontend_client, kb_test_flow):
        """Проверяем 404 при удалении несуществующего документа"""
        response = await frontend_client.delete(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/documents/nonexistent_doc_123"
        )
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_delete_document_flow_not_found(self, frontend_client):
        """Проверяем 404 при удалении из несуществующего flow"""
        response = await frontend_client.delete(
            "/frontend/api/knowledge-base/flows/nonexistent_flow_123/documents/doc_123"
        )
        
        assert response.status_code == 404


class TestKnowledgeBaseFullCycle:
    """Интеграционные тесты полного цикла работы с документами.
    
    Важно: Agentset API обрабатывает документы асинхронно.
    document_id при загрузке - это ID ingest job (job_xxx),
    а в списке документов - ID готового документа (doc_xxx).
    Поэтому тесты используют polling для ожидания готовности.
    """
    
    @staticmethod
    async def _wait_for_document(frontend_client, flow_id: str, timeout: int = 30) -> str:
        """Ждет появления документа в списке и возвращает его ID"""
        import asyncio
        
        for _ in range(timeout):
            list_response = await frontend_client.get(
                f"/frontend/api/knowledge-base/flows/{flow_id}/documents"
            )
            if list_response.status_code == 200:
                list_data = list_response.json()
                if list_data["documents"]:
                    return list_data["documents"][0]["document_id"]
            await asyncio.sleep(1)
        
        return None
    
    @pytest.mark.asyncio
    async def test_upload_list_delete_text_document(self, frontend_client, kb_test_flow):
        """Полный цикл: загрузка текста -> ожидание индексации -> список -> удаление"""
        text_data = {
            "text": "Test document for full cycle knowledge base testing.",
            "document_name": "full_cycle_test.txt"
        }
        
        upload_response = await frontend_client.post(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/text",
            json=text_data
        )
        
        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        assert "document_id" in upload_data
        assert upload_data["status"] == "processing"
        
        # Ждем пока документ будет проиндексирован (ingest job -> document)
        document_id = await self._wait_for_document(frontend_client, kb_test_flow.flow_id)
        
        if not document_id:
            pytest.skip("Документ не появился в списке за 30 секунд (Agentset indexing delay)")
        
        # Удаляем документ
        delete_response = await frontend_client.delete(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/documents/{document_id}"
        )
        
        assert delete_response.status_code == 200
        delete_data = delete_response.json()
        assert delete_data["success"] is True
    
    @pytest.mark.asyncio
    async def test_upload_list_delete_file_document(self, frontend_client, kb_test_flow):
        """Полный цикл: загрузка файла -> ожидание индексации -> список -> удаление"""
        file_content = b"Content for full cycle file test.\nMultiple lines here."
        
        files = {
            "file": ("cycle_test.txt", file_content, "text/plain")
        }
        
        upload_response = await frontend_client.post(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/documents",
            files=files
        )
        
        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        assert "document_id" in upload_data
        assert upload_data["status"] == "processing"
        
        # Ждем пока документ будет проиндексирован
        document_id = await self._wait_for_document(frontend_client, kb_test_flow.flow_id)
        
        if not document_id:
            pytest.skip("Документ не появился в списке за 30 секунд (Agentset indexing delay)")
        
        # Удаляем
        delete_response = await frontend_client.delete(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/documents/{document_id}"
        )
        
        assert delete_response.status_code == 200


class TestKnowledgeBaseRAGConfig:
    """Тесты для проверки RAG конфигурации flow"""
    
    @pytest.mark.asyncio
    async def test_rag_config_default_values(self, frontend_client, kb_test_flow, frontend_flow_repo):
        """Проверяем что flow имеет корректные дефолтные значения rag_config"""
        from core.context import set_context
        set_context(frontend_client.test_context)
        
        flow = await frontend_flow_repo.get(kb_test_flow.flow_id)
        
        # FlowConfig автоматически создает rag_config с дефолтными значениями
        assert flow.rag_config is not None
        assert flow.rag_config.enabled is True
        assert flow.rag_config.namespace_scope == "flow"
        assert "flow" in flow.rag_config.search_scopes
    
    @pytest.mark.asyncio
    async def test_rag_config_used_in_api(self, frontend_client, kb_test_flow):
        """Проверяем что API корректно работает с rag_config"""
        response = await frontend_client.get(
            f"/frontend/api/knowledge-base/flows/{kb_test_flow.flow_id}/documents"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total" in data

