"""
Тесты для RAG инструментов для агентов.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.misc.rag_tools import (
    search_knowledge_base,
    upload_document_to_knowledge_base,
    upload_text_to_knowledge_base,
    list_documents_in_knowledge_base
)
from app.models.rag_models import RAGSearchResult, RAGDocument


@pytest.fixture
def mock_context():
    """Фикстура для мока контекста"""
    from app.models.rag_models import AgentRAGConfig
    
    context = MagicMock()
    context.session_id = "session_123"
    context.user.user_id = "user_456"
    context.active_company.company_id = "company_789"
    
    mock_agent_config = MagicMock()
    mock_agent_config.agent_id = "agent_001"
    mock_agent_config.rag_config = None
    context.agent_config = mock_agent_config
    
    mock_flow_config = MagicMock()
    mock_flow_config.flow_id = "test_flow"
    mock_flow_config.rag_config = AgentRAGConfig(
        enabled=True,
        namespace_scope="flow",
        search_scopes=["flow", "company"]
    )
    context.flow_config = mock_flow_config
    
    return context


@pytest.fixture
def mock_rag_provider():
    """Фикстура для мока RAG провайдера"""
    provider = AsyncMock()
    
    provider.search_multiple_namespaces = AsyncMock(return_value={
        "company_789_agent_agent_001": [
            RAGSearchResult(
                content="Информация из документа агента",
                score=0.95,
                document_id="doc1",
                document_name="agent_doc.pdf",
                namespace="company_789_agent_agent_001",
                metadata={}
            )
        ],
        "company_789": [
            RAGSearchResult(
                content="Информация из общего документа",
                score=0.85,
                document_id="doc2",
                document_name="company_doc.txt",
                namespace="company_789",
                metadata={}
            )
        ]
    })
    
    provider.upload_document_from_s3 = AsyncMock(return_value=RAGDocument(
        document_id="new_doc_123",
        name="uploaded_file.pdf",
        namespace="company_789_agent_agent_001",
        status="processing"
    ))

    provider.upload_document_from_text = AsyncMock(return_value=RAGDocument(
        document_id="text_doc_456",
        name="Text document (42 chars)",
        namespace="company_789_agent_agent_001",
        status="processing"
    ))
    
    provider.list_documents = AsyncMock(return_value=[
        RAGDocument(
            document_id="doc1",
            name="document1.pdf",
            namespace="company_789_agent_agent_001",
            status="ready",
            created_at="2025-01-01T00:00:00Z"
        ),
        RAGDocument(
            document_id="doc2",
            name="document2.txt",
            namespace="company_789_agent_agent_001",
            status="processing",
            created_at="2025-01-02T00:00:00Z"
        )
    ])
    
    return provider


class TestSearchKnowledgeBase:
    """Тесты для инструмента поиска в базе знаний"""
    
    @pytest.mark.asyncio
    async def test_search_rag_disabled(self, mock_context, mock_rag_provider):
        """Тест когда RAG отключен"""
        mock_context.flow_config.rag_config = None
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                result = await search_knowledge_base.ainvoke(
                    {"query": "test query"},
                    config={}
                )
        
        assert result == "RAG не настроен для этого flow"
    
    @pytest.mark.asyncio
    async def test_search_success(self, mock_context, mock_rag_provider):
        """Тест успешного поиска"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.misc.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await search_knowledge_base.ainvoke(
                        {"query": "test query"},
                        config={}
                    )
        
        assert "Найдено 2 релевантных фрагментов" in result
        assert "agent_doc.pdf" in result
        assert "company_doc.txt" in result
        assert "релевантность: 0.95" in result
        
        mock_rag_provider.search_multiple_namespaces.assert_called_once()
        call_args = mock_rag_provider.search_multiple_namespaces.call_args
        
        assert call_args[1]["query"] == "test query"
        assert call_args[1]["limit"] == 5
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, mock_context, mock_rag_provider):
        """Тест когда ничего не найдено"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        mock_rag_provider.search_multiple_namespaces = AsyncMock(return_value={
            "mock_ns_id": []
        })
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.misc.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await search_knowledge_base.ainvoke(
                        {"query": "non existent"},
                        config={}
                    )
        
        assert "ничего не найдено" in result.lower()
    
    @pytest.mark.asyncio
    async def test_search_no_scopes_configured(self, mock_context, mock_rag_provider):
        """Тест когда не настроены скоупы"""
        from app.models.rag_models import AgentRAGConfig
        
        mock_context.flow_config.rag_config = AgentRAGConfig(
            enabled=True,
            namespace_scope="flow",
            search_scopes=[]
        )
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                result = await search_knowledge_base.ainvoke(
                    {"query": "test"},
                    config={}
                )
        
        assert "Не настроены скоупы поиска" in result


class TestUploadDocumentToKnowledgeBase:
    """Тесты для инструмента загрузки документов"""
    
    @pytest.mark.asyncio
    async def test_upload_rag_disabled(self, mock_context, mock_rag_provider):
        """Тест когда RAG отключен"""
        mock_context.flow_config.rag_config = None
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                result = await upload_document_to_knowledge_base.ainvoke(
                    {"file_id": "file_123", "tool_call_id": "test_call_456"},
                    config={}
                )
        
        assert result == "RAG не настроен для этого flow"
    
    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, mock_context):
        """Тест когда файл не найден"""
        mock_storage = AsyncMock()
        mock_storage.get = AsyncMock(return_value=None)
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.db.repositories.Storage", return_value=mock_storage):
                result = await upload_document_to_knowledge_base.ainvoke(
                    {"file_id": "nonexistent"},
                    config={}
                )
        
        assert "не найден" in result.lower()
    
    @pytest.mark.asyncio
    async def test_upload_success(self, mock_context, mock_rag_provider):
        """Тест успешной загрузки"""
        from app.models.file_models import FileRecord
        
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        
        mock_file_record = FileRecord(
            file_id="file_123",
            provider="yandex",
            original_name="document.pdf",
            s3_key="uploads/document.pdf",
            s3_bucket="test-bucket",
            content_type="application/pdf",
            file_size=1024
        )
        
        mock_file_processor = AsyncMock()
        mock_file_processor.get_file_record = AsyncMock(return_value=mock_file_record)
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_file_processor", return_value=mock_file_processor):
                with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                    with patch("app.tools.misc.rag_tools.get_or_create_namespace", new=mock_get_ns):
                        result = await upload_document_to_knowledge_base.ainvoke(
                            {"file_id": "file_123", "description": "Test doc"},
                            config={}
                        )
        
        assert "успешно добавлен" in result
        assert "new_doc_123" in result
        
        mock_rag_provider.upload_document_from_s3.assert_called_once()
        call_args = mock_rag_provider.upload_document_from_s3.call_args
        
        assert call_args[1]["s3_key"] == "uploads/document.pdf"
        assert call_args[1]["metadata"]["description"] == "Test doc"
    
    @pytest.mark.asyncio
    async def test_upload_to_company_scope(self, mock_context, mock_rag_provider):
        """Тест загрузки в скоуп компании"""
        from app.models.rag_models import AgentRAGConfig
        from app.models.file_models import FileRecord
        
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        mock_context.flow_config.flow_id = "test_flow"
        mock_context.flow_config.rag_config = AgentRAGConfig(
            enabled=True,
            namespace_scope="company",
            search_scopes=["company"]
        )
        
        mock_file_record = FileRecord(
            file_id="file_123",
            provider="yandex",
            original_name="doc.pdf",
            s3_key="doc.pdf",
            s3_bucket="test-bucket",
            content_type="application/pdf",
            file_size=1024
        )
        
        mock_file_processor = AsyncMock()
        mock_file_processor.get_file_record = AsyncMock(return_value=mock_file_record)
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_file_processor", return_value=mock_file_processor):
                with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                    with patch("app.tools.misc.rag_tools.get_or_create_namespace", new=mock_get_ns):
                        result = await upload_document_to_knowledge_base.ainvoke(
                            {"file_id": "file_123"},
                            config={}
                        )
        
        assert "общую базу компании" in result
        
        mock_rag_provider.upload_document_from_s3.assert_called_once()


class TestListDocumentsInKnowledgeBase:
    """Тесты для инструмента списка документов"""
    
    @pytest.mark.asyncio
    async def test_list_rag_disabled(self, mock_context, mock_rag_provider):
        """Тест когда RAG отключен"""
        mock_context.flow_config.rag_config = None
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                result = await list_documents_in_knowledge_base.ainvoke({}, config={})
        
        assert result == "RAG не настроен для этого flow"
    
    @pytest.mark.asyncio
    async def test_list_empty(self, mock_context, mock_rag_provider):
        """Тест когда нет документов"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        mock_rag_provider.list_documents = AsyncMock(return_value=[])
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.misc.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await list_documents_in_knowledge_base.ainvoke({}, config={})
        
        assert "пока нет документов" in result.lower()
    
    @pytest.mark.asyncio
    async def test_list_success(self, mock_context, mock_rag_provider):
        """Тест успешного получения списка"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        
        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.misc.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await list_documents_in_knowledge_base.ainvoke({}, config={})
        
        assert "Документы в базе знаний (2)" in result
        assert "document1.pdf" in result
        assert "document2.txt" in result
        assert "✅" in result
        assert "⏳" in result
        assert "doc1" in result
        assert "doc2" in result


class TestUploadTextToKnowledgeBase:
    """Тесты для инструмента загрузки текста"""

    @pytest.mark.asyncio
    async def test_upload_text_rag_disabled(self, mock_context, mock_rag_provider):
        """Тест когда RAG отключен"""
        mock_context.flow_config.rag_config = None

        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                result = await upload_text_to_knowledge_base.ainvoke(
                    {"text": "test text"},
                    config={}
                )

        assert result == "RAG не настроен для этого flow"

    @pytest.mark.asyncio
    async def test_upload_text_success(self, mock_context, mock_rag_provider):
        """Тест успешной загрузки текста"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")

        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.misc.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await upload_text_to_knowledge_base.ainvoke(
                        {"text": "test text content", "document_name": "test_doc.txt", "description": "Test doc"},
                        config={}
                    )

        assert "успешно добавлен" in result
        assert "text_doc_456" in result
        assert "Text document (42 chars)" in result

        mock_rag_provider.upload_document_from_text.assert_called_once()
        call_args = mock_rag_provider.upload_document_from_text.call_args

        assert call_args[1]["text"] == "test text content"
        assert call_args[1]["document_name"] == "test_doc.txt"
        assert call_args[1]["metadata"]["description"] == "Test doc"

    @pytest.mark.asyncio
    async def test_upload_text_auto_name(self, mock_context, mock_rag_provider):
        """Тест автоматической генерации имени документа"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")

        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.misc.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await upload_text_to_knowledge_base.ainvoke(
                        {"text": "test text content"},
                        config={}
                    )

        assert "Text document (42 chars)" in result

        mock_rag_provider.upload_document_from_text.assert_called_once()
        call_args = mock_rag_provider.upload_document_from_text.call_args

        assert call_args[1]["text"] == "test text content"
        assert call_args[1]["document_name"] == "Text document (17 chars)"

    @pytest.mark.asyncio
    async def test_upload_text_to_company_scope(self, mock_context, mock_rag_provider):
        """Тест загрузки текста в скоуп компании"""
        from app.models.rag_models import AgentRAGConfig

        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        mock_context.flow_config.flow_id = "test_flow"
        mock_context.flow_config.rag_config = AgentRAGConfig(
            enabled=True,
            namespace_scope="company",
            search_scopes=["company"]
        )

        with patch("app.tools.misc.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.misc.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.misc.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await upload_text_to_knowledge_base.ainvoke(
                        {"text": "test text content"},
                        config={}
                    )

        assert "общую базу компании" in result

        mock_rag_provider.upload_document_from_text.assert_called_once()


class TestAgentsetProviderTextUpload:
    """Тесты для upload_document_from_text в Agentset провайдере"""

    @pytest.mark.asyncio
    async def test_upload_text_via_s3_flow(self):
        """Тест загрузки текста через S3 flow"""
        from app.core.rag.providers.agentset_provider import AgentsetRAGProvider
        from unittest.mock import AsyncMock, patch, MagicMock

        provider = AgentsetRAGProvider({"api_key": "test", "base_url": "https://test.com"})

        # Mock S3 client
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_bytes = AsyncMock()

        # Mock upload_document_from_s3
        mock_s3_result = MagicMock()
        mock_s3_result.document_id = "test_doc_123"
        mock_s3_result.name = "test_doc.txt"
        mock_s3_result.status = "processing"

        with patch('app.core.rag.providers.agentset_provider.get_default_s3_client', return_value=mock_s3_client), \
             patch.object(provider, 'upload_document_from_s3', return_value=mock_s3_result) as mock_upload_s3:

            result = await provider.upload_document_from_text(
                namespace_id="test_ns",
                text="Test text content",
                document_name="test_doc.txt",
                metadata={"test": "metadata"}
            )

            # Проверяем, что текст был загружен в S3
            mock_s3_client.upload_bytes.assert_called_once()
            s3_call_args = mock_s3_client.upload_bytes.call_args

            # Проверяем, что данные переданы правильно
            assert s3_call_args[1]['data'] == b'Test text content'  # Текст в bytes
            assert s3_call_args[1]['content_type'] == 'text/plain'
            assert s3_call_args[1]['acl'] == 'private'

            # Проверяем название файла в S3 (должно содержать указанное название документа)
            s3_key = s3_call_args[1]['key']
            assert 'rag_text/test_ns/' in s3_key
            assert 'test_doc' in s3_key  # Должно содержать название документа без расширения

            # Проверяем, что upload_document_from_s3 был вызван с правильными метаданными
            mock_upload_s3.assert_called_once()
            s3_call_args = mock_upload_s3.call_args

            assert s3_call_args[1]['namespace_id'] == 'test_ns'
            assert s3_call_args[1]['document_name'] == 'test_doc.txt'

            # Проверяем метаданные
            metadata = s3_call_args[1]['metadata']
            assert metadata['test'] == 'metadata'  # Оригинальные метаданные
            assert metadata['original_text_length'] == 17  # Длина текста
            assert 's3_key' in metadata
            assert metadata['uploaded_via'] == 'text_upload'
            assert 'file_id' in metadata  # UUID для кодирования названия

            assert result.document_id == "test_doc_123"
            assert result.name == "test_doc.txt"
            assert result.status == "processing"

    @pytest.mark.asyncio
    async def test_upload_text_auto_filename_generation(self):
        """Тест автоматической генерации названия файла из текста"""
        from app.core.rag.providers.agentset_provider import AgentsetRAGProvider
        from unittest.mock import AsyncMock, patch, MagicMock

        provider = AgentsetRAGProvider({"api_key": "test", "base_url": "https://test.com"})

        # Mock S3 client
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_bytes = AsyncMock()

        # Mock upload_document_from_s3
        mock_s3_result = MagicMock()
        mock_s3_result.document_id = "test_doc_456"
        mock_s3_result.name = "auto_generated_name"
        mock_s3_result.status = "processing"

        with patch('app.core.rag.providers.agentset_provider.get_default_s3_client', return_value=mock_s3_client), \
             patch.object(provider, 'upload_document_from_s3', return_value=mock_s3_result) as mock_upload_s3:

            # Загружаем текст без указания названия документа
            result = await provider.upload_document_from_text(
                namespace_id="test_ns",
                text="Это пример текста для тестирования автоматической генерации названия файла из первых символов",
                metadata={"test": "metadata"}
            )

            # Проверяем, что файл был загружен в S3
            mock_s3_client.upload_bytes.assert_called_once()
            s3_call_args = mock_s3_client.upload_bytes.call_args

            # Проверяем, что название файла содержит первые символы текста
            s3_key = s3_call_args[1]['key']
            assert 'rag_text/test_ns/' in s3_key
            # Должно содержать начало текста, очищенное от спецсимволов
            assert 'Это пример текста' in s3_key or 'auto_generated' in s3_key


@pytest.mark.integration
class TestKnowledgeBaseAPI:
    """Тесты для API endpoints базы знаний (требуют запущенного сервера)"""

    @pytest.mark.asyncio
    async def test_upload_text_success(self, httpx_client, flow_repo, test_company):
        """Тест успешной загрузки текста через API"""
        from app.models import FlowConfig

        flow_id = f"test_flow_{uuid.uuid4().hex[:8]}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Flow",
            entry_point_agent="test.agent",
            source="test"
        )
        await flow_repo.set(flow_config)

        text_content = "Это тестовый текст для загрузки в базу знаний"
        document_name = "test_document.txt"

        response = await httpx_client.post(
            f"/api/v1/knowledge-base/flows/{flow_id}/text",
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
    async def test_upload_text_flow_not_found(self, httpx_client):
        """Тест загрузки текста для несуществующего flow"""
        response = await httpx_client.post(
            "/api/v1/knowledge-base/flows/nonexistent_flow/text",
            json={
                "text": "test text",
                "document_name": "test.txt"
            }
        )

        assert response.status_code == 404
        assert "не найден" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_text_empty_text(self, httpx_client, flow_repo, test_company):
        """Тест загрузки пустого текста"""
        from app.models import FlowConfig

        flow_id = f"test_flow_{uuid.uuid4().hex[:8]}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Flow",
            entry_point_agent="test.agent",
            source="test"
        )
        await flow_repo.set(flow_config)

        response = await httpx_client.post(
            f"/api/v1/knowledge-base/flows/{flow_id}/text",
            json={
                "text": "",
                "document_name": "empty.txt"
            }
        )

        # Пустой текст все равно должен обработаться
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "empty.txt"
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_upload_text_auto_name_generation(self, httpx_client, flow_repo, test_company):
        """Тест автоматической генерации имени документа"""
        from app.models import FlowConfig

        flow_id = f"test_flow_{uuid.uuid4().hex[:8]}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Flow",
            entry_point_agent="test.agent",
            source="test"
        )
        await flow_repo.set(flow_config)

        text_content = "Короткий текст для тестирования"

        response = await httpx_client.post(
            f"/api/v1/knowledge-base/flows/{flow_id}/text",
            json={
                "text": text_content
                # document_name не указан
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "Text document" in data["name"]
        assert "(37 chars)" in data["name"]

    @pytest.mark.asyncio
    async def test_get_flow_documents(self, httpx_client, flow_repo, test_company):
        """Тест получения списка документов flow"""
        from app.models import FlowConfig

        flow_id = f"test_flow_{uuid.uuid4().hex[:8]}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Test Flow",
            entry_point_agent="test.agent",
            source="test"
        )
        await flow_repo.set(flow_config)

        response = await httpx_client.get(f"/api/v1/knowledge-base/flows/{flow_id}/documents")

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total" in data
        assert isinstance(data["documents"], list)

