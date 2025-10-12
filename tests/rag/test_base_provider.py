"""
Тесты для базового RAG провайдера и фабрики.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.core.rag.base_provider import BaseRAGProvider
from app.core.rag.factory import get_rag_provider, RAG_PROVIDERS
from app.models.rag_models import RAGDocument, RAGSearchResult, RAGNamespace


class MockRAGProvider(BaseRAGProvider):
    """Моковый провайдер для тестов"""
    
    @property
    def provider_name(self) -> str:
        return "mock"
    
    async def create_namespace(self, name: str, description=None, **kwargs):
        return RAGNamespace(
            namespace_id="mock_ns_123",
            name=name,
            document_count=0
        )
    
    async def get_namespace(self, namespace_id: str):
        if namespace_id == "mock_ns_123":
            return RAGNamespace(
                namespace_id=namespace_id,
                name="test_namespace",
                document_count=5
            )
        return None
    
    async def list_namespaces(self):
        return [
            RAGNamespace(namespace_id="ns1", name="Namespace 1", document_count=3),
            RAGNamespace(namespace_id="ns2", name="Namespace 2", document_count=7)
        ]
    
    async def delete_namespace(self, namespace_id: str):
        return namespace_id == "mock_ns_123"
    
    async def upload_document_from_file(
        self, namespace_id, file_path, document_name=None, metadata=None, **kwargs
    ):
        return RAGDocument(
            document_id="doc_123",
            name=document_name or "test.pdf",
            namespace=namespace_id,
            status="processing",
            metadata=metadata or {}
        )
    
    async def upload_document_from_s3(
        self, namespace_id, s3_key, document_name=None, metadata=None, **kwargs
    ):
        return RAGDocument(
            document_id="doc_s3_456",
            name=document_name or s3_key,
            namespace=namespace_id,
            status="processing",
            metadata=metadata or {}
        )
    
    async def get_document(self, namespace_id, document_id):
        if document_id == "doc_123":
            return RAGDocument(
                document_id=document_id,
                name="test.pdf",
                namespace=namespace_id,
                status="ready"
            )
        return None
    
    async def list_documents(self, namespace_id, limit=100):
        return [
            RAGDocument(
                document_id="doc1",
                name="document1.pdf",
                namespace=namespace_id,
                status="ready"
            ),
            RAGDocument(
                document_id="doc2",
                name="document2.txt",
                namespace=namespace_id,
                status="processing"
            )
        ]
    
    async def delete_document(self, namespace_id, document_id):
        return document_id in ["doc1", "doc2", "doc_123"]
    
    async def search(self, namespace_id, query, limit=5, filters=None, **kwargs):
        return [
            RAGSearchResult(
                content=f"Результат для запроса: {query}",
                score=0.95,
                document_id="doc1",
                document_name="relevant_doc.pdf",
                namespace=namespace_id,
                metadata={"page": 1}
            ),
            RAGSearchResult(
                content=f"Второй результат для: {query}",
                score=0.85,
                document_id="doc2",
                document_name="another_doc.txt",
                namespace=namespace_id,
                metadata={"page": 3}
            )
        ]


class TestBaseRAGProvider:
    """Тесты для базового провайдера"""
    
    @pytest.mark.asyncio
    async def test_search_multiple_namespaces(self):
        """Тест поиска по нескольким namespace"""
        provider = MockRAGProvider({})
        
        results = await provider.search_multiple_namespaces(
            namespace_ids=["ns1", "ns2"],
            query="test query",
            limit=5
        )
        
        assert "ns1" in results
        assert "ns2" in results
        assert len(results["ns1"]) == 2
        assert len(results["ns2"]) == 2
        assert results["ns1"][0].content == "Результат для запроса: test query"
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Тест использования провайдера как контекстного менеджера"""
        provider = MockRAGProvider({})
        
        async with provider as p:
            assert p == provider
            namespaces = await p.list_namespaces()
            assert len(namespaces) == 2


class TestRAGFactory:
    """Тесты для фабрики RAG провайдеров"""
    
    def test_rag_providers_registered(self):
        """Проверка что провайдеры зарегистрированы"""
        assert "agentset" in RAG_PROVIDERS
        assert RAG_PROVIDERS["agentset"].__name__ == "AgentsetRAGProvider"
    
    @patch("app.core.rag.factory.get_settings")
    def test_get_rag_provider_disabled(self, mock_get_settings):
        """Тест когда RAG отключен"""
        mock_settings = MagicMock()
        mock_settings.rag.enabled = False
        mock_get_settings.return_value = mock_settings
        
        with pytest.raises(ValueError, match="RAG не включен"):
            get_rag_provider()
    
    @patch("app.core.rag.factory.get_settings")
    def test_get_rag_provider_unknown_provider(self, mock_get_settings):
        """Тест с неизвестным провайдером"""
        mock_settings = MagicMock()
        mock_settings.rag.enabled = True
        mock_settings.rag.default_provider = "unknown_provider"
        mock_get_settings.return_value = mock_settings
        
        with pytest.raises(ValueError, match="Неизвестный RAG провайдер"):
            get_rag_provider()
    
    @patch("app.core.rag.factory.get_settings")
    def test_get_rag_provider_no_config(self, mock_get_settings):
        """Тест когда нет конфигурации провайдера"""
        mock_settings = MagicMock()
        mock_settings.rag.enabled = True
        mock_settings.rag.default_provider = "agentset"
        mock_settings.rag.providers.get.return_value = None
        mock_get_settings.return_value = mock_settings
        
        with pytest.raises(ValueError, match="Не найдена конфигурация"):
            get_rag_provider()
    
    @patch("app.core.rag.factory.get_settings")
    def test_get_rag_provider_provider_disabled(self, mock_get_settings):
        """Тест когда провайдер отключен"""
        mock_settings = MagicMock()
        mock_settings.rag.enabled = True
        mock_settings.rag.default_provider = "agentset"
        
        mock_provider_config = MagicMock()
        mock_provider_config.model_dump.return_value = {"enabled": False}
        mock_settings.rag.providers.get.return_value = mock_provider_config
        
        mock_get_settings.return_value = mock_settings
        
        with pytest.raises(ValueError, match="отключен"):
            get_rag_provider()

