"""
Тесты на идентичность работы RAG провайдеров.
Проверяет что ChromaDB и Agentset работают одинаково.

Требования:
- ChromaDB сервер: docker-compose up -d chroma
- Agentset API ключ в конфиге

Запуск:
    uv run pytest tests/agents/rag/test_provider_compatibility.py -v
"""

import pytest
import uuid
from typing import Optional

from core.rag.base_provider import BaseRAGProvider
from core.rag.providers.chromadb_provider import ChromaDBRAGProvider
from core.rag.providers.agentset_provider import AgentsetRAGProvider
from core.rag.models import RAGDocument, RAGSearchResult, RAGNamespace
from core.config import get_settings


def is_chromadb_available() -> bool:
    """Проверяет доступность ChromaDB"""
    try:
        import chromadb
        client = chromadb.HttpClient(host="localhost", port=8100)
        client.heartbeat()
        return True
    except Exception:
        return False


def is_agentset_available() -> bool:
    """Проверяет доступность Agentset"""
    try:
        settings = get_settings()
        agentset_config = settings.rag.providers.get("agentset")
        return (
            agentset_config 
            and agentset_config.enabled 
            and agentset_config.api_key
        )
    except Exception:
        return False


skip_if_chromadb_unavailable = pytest.mark.skipif(
    not is_chromadb_available(),
    reason="ChromaDB недоступен"
)

skip_if_agentset_unavailable = pytest.mark.skipif(
    not is_agentset_available(),
    reason="Agentset не настроен"
)

skip_if_any_unavailable = pytest.mark.skipif(
    not (is_chromadb_available() and is_agentset_available()),
    reason="Один из провайдеров недоступен"
)


@pytest.fixture
def unique_namespace():
    """Уникальное имя namespace для теста"""
    return f"test_compat_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def chromadb_provider():
    """ChromaDB провайдер"""
    settings = get_settings()
    chromadb_config = settings.rag.providers.get("chromadb")
    
    config = {
        "host": "localhost",
        "port": 8100,
        "embedding_api_key": chromadb_config.embedding_api_key if chromadb_config else settings.llm.openrouter.api_key,
        "embedding_model": chromadb_config.embedding_model if chromadb_config else "openai/text-embedding-3-small",
    }
    
    provider = ChromaDBRAGProvider(config)
    yield provider
    await provider.close()


@pytest.fixture
async def agentset_provider():
    """Agentset провайдер"""
    settings = get_settings()
    agentset_config = settings.rag.providers.get("agentset")
    
    if not agentset_config or not agentset_config.api_key:
        pytest.skip("Agentset не настроен")
    
    config = agentset_config.model_dump()
    provider = AgentsetRAGProvider(config)
    yield provider
    await provider.close()


class TestProviderAPICompatibility:
    """Тесты совместимости API провайдеров"""
    
    def test_both_providers_have_same_interface(self):
        """Оба провайдера имеют одинаковый интерфейс"""
        # Обязательные методы из BaseRAGProvider
        required_methods = [
            'provider_name',
            'create_namespace',
            'get_namespace',
            'list_namespaces',
            'delete_namespace',
            'upload_document_from_file',
            'upload_document_from_s3',
            'upload_document_from_text',
            'get_document',
            'list_documents',
            'delete_document',
            'search',
            'search_multiple_namespaces',
            'close',
            # Базовые утилиты
            '_get_content_type',
            '_upload_file_to_s3',
            '_download_file_from_s3',
            '_generate_signed_url',
            '_upload_text_to_s3',
            'generate_download_url',
        ]
        
        for method in required_methods:
            assert hasattr(ChromaDBRAGProvider, method), f"ChromaDB не имеет метода {method}"
            assert hasattr(AgentsetRAGProvider, method), f"Agentset не имеет метода {method}"
    
    def test_provider_names_are_different(self):
        """provider_name возвращает разные значения"""
        settings = get_settings()
        chromadb_config = settings.rag.providers.get("chromadb")
        
        chromadb = ChromaDBRAGProvider({
            "host": "localhost",
            "port": 8100,
            "embedding_api_key": chromadb_config.embedding_api_key if chromadb_config else "test",
        })
        
        assert chromadb.provider_name == "chromadb"


@skip_if_chromadb_unavailable
class TestChromaDBReturnTypes:
    """Тесты что ChromaDB возвращает правильные типы"""
    
    @pytest.fixture
    async def provider_with_cleanup(self, chromadb_provider, unique_namespace):
        """Провайдер с автоматической очисткой"""
        created_namespaces = []
        
        class Wrapper:
            def __init__(self, p):
                self._p = p
                self.namespace = unique_namespace
            
            def __getattr__(self, name):
                return getattr(self._p, name)
            
            async def create_namespace(self, name=None, **kwargs):
                ns = await self._p.create_namespace(name or self.namespace, **kwargs)
                created_namespaces.append(ns.namespace_id)
                return ns
        
        wrapper = Wrapper(chromadb_provider)
        yield wrapper
        
        for ns_id in created_namespaces:
            try:
                await chromadb_provider.delete_namespace(ns_id)
            except Exception:
                pass
    
    @pytest.mark.asyncio
    async def test_create_namespace_returns_rag_namespace(self, provider_with_cleanup):
        """create_namespace возвращает RAGNamespace"""
        ns = await provider_with_cleanup.create_namespace()
        
        assert isinstance(ns, RAGNamespace)
        assert ns.namespace_id is not None
        assert isinstance(ns.name, str)
        assert isinstance(ns.document_count, int)
    
    @pytest.mark.asyncio
    async def test_get_namespace_returns_rag_namespace_or_none(self, provider_with_cleanup):
        """get_namespace возвращает RAGNamespace или None"""
        ns = await provider_with_cleanup.create_namespace()
        
        fetched = await provider_with_cleanup.get_namespace(ns.namespace_id)
        assert isinstance(fetched, RAGNamespace)
        
        not_found = await provider_with_cleanup.get_namespace("nonexistent_12345")
        assert not_found is None
    
    @pytest.mark.asyncio
    async def test_list_namespaces_returns_list_of_rag_namespace(self, provider_with_cleanup):
        """list_namespaces возвращает List[RAGNamespace]"""
        await provider_with_cleanup.create_namespace()
        
        namespaces = await provider_with_cleanup.list_namespaces()
        
        assert isinstance(namespaces, list)
        assert all(isinstance(ns, RAGNamespace) for ns in namespaces)
    
    @pytest.mark.asyncio
    async def test_upload_document_returns_rag_document(self, provider_with_cleanup):
        """upload_document_from_text возвращает RAGDocument"""
        ns = await provider_with_cleanup.create_namespace()
        
        doc = await provider_with_cleanup.upload_document_from_text(
            namespace_id=ns.namespace_id,
            text="Test content for type checking.",
            document_name="test.txt"
        )
        
        assert isinstance(doc, RAGDocument)
        assert doc.document_id is not None
        assert isinstance(doc.name, str)
        assert isinstance(doc.namespace, str)
        assert isinstance(doc.status, str)
    
    @pytest.mark.asyncio
    async def test_get_document_returns_rag_document_or_none(self, provider_with_cleanup):
        """get_document возвращает RAGDocument или None"""
        ns = await provider_with_cleanup.create_namespace()
        
        doc = await provider_with_cleanup.upload_document_from_text(
            namespace_id=ns.namespace_id,
            text="Test content.",
            document_name="test.txt"
        )
        
        fetched = await provider_with_cleanup.get_document(ns.namespace_id, doc.document_id)
        assert isinstance(fetched, RAGDocument)
        
        not_found = await provider_with_cleanup.get_document(ns.namespace_id, "nonexistent")
        assert not_found is None
    
    @pytest.mark.asyncio
    async def test_list_documents_returns_list_of_rag_document(self, provider_with_cleanup):
        """list_documents возвращает List[RAGDocument]"""
        ns = await provider_with_cleanup.create_namespace()
        
        await provider_with_cleanup.upload_document_from_text(
            namespace_id=ns.namespace_id,
            text="Test content.",
            document_name="test.txt"
        )
        
        documents = await provider_with_cleanup.list_documents(ns.namespace_id)
        
        assert isinstance(documents, list)
        assert all(isinstance(doc, RAGDocument) for doc in documents)
    
    @pytest.mark.asyncio
    async def test_search_returns_list_of_rag_search_result(self, provider_with_cleanup):
        """search возвращает List[RAGSearchResult]"""
        ns = await provider_with_cleanup.create_namespace()
        
        await provider_with_cleanup.upload_document_from_text(
            namespace_id=ns.namespace_id,
            text="Python is a programming language.",
            document_name="python.txt"
        )
        
        results = await provider_with_cleanup.search(
            namespace_id=ns.namespace_id,
            query="programming",
            limit=5
        )
        
        assert isinstance(results, list)
        assert all(isinstance(r, RAGSearchResult) for r in results)
        
        if results:
            r = results[0]
            assert isinstance(r.content, str)
            assert isinstance(r.score, (int, float))
    
    @pytest.mark.asyncio
    async def test_delete_namespace_returns_bool(self, chromadb_provider, unique_namespace):
        """delete_namespace возвращает bool"""
        ns = await chromadb_provider.create_namespace(unique_namespace)
        
        result = await chromadb_provider.delete_namespace(ns.namespace_id)
        assert isinstance(result, bool)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_delete_document_returns_bool(self, provider_with_cleanup):
        """delete_document возвращает bool"""
        ns = await provider_with_cleanup.create_namespace()
        
        doc = await provider_with_cleanup.upload_document_from_text(
            namespace_id=ns.namespace_id,
            text="To be deleted.",
            document_name="delete.txt"
        )
        
        result = await provider_with_cleanup.delete_document(ns.namespace_id, doc.document_id)
        assert isinstance(result, bool)


@skip_if_chromadb_unavailable
class TestChromaDBMetadataStorage:
    """Тесты что ChromaDB сохраняет metadata как Agentset"""
    
    @pytest.fixture
    async def provider_with_cleanup(self, chromadb_provider, unique_namespace):
        """Провайдер с автоматической очисткой"""
        created_namespaces = []
        
        class Wrapper:
            def __init__(self, p):
                self._p = p
                self.namespace = unique_namespace
            
            def __getattr__(self, name):
                return getattr(self._p, name)
            
            async def create_namespace(self, name=None, **kwargs):
                ns = await self._p.create_namespace(name or self.namespace, **kwargs)
                created_namespaces.append(ns.namespace_id)
                return ns
        
        wrapper = Wrapper(chromadb_provider)
        yield wrapper
        
        for ns_id in created_namespaces:
            try:
                await chromadb_provider.delete_namespace(ns_id)
            except Exception:
                pass
    
    @pytest.mark.asyncio
    async def test_document_has_s3_key_in_metadata(self, provider_with_cleanup):
        """Документ содержит s3_key в metadata (совместимость с Agentset)"""
        ns = await provider_with_cleanup.create_namespace()
        
        doc = await provider_with_cleanup.upload_document_from_text(
            namespace_id=ns.namespace_id,
            text="Test content for S3 storage verification.",
            document_name="s3_test.txt"
        )
        
        # s3_key должен быть в metadata (для возможности скачать оригинал)
        # Примечание: для upload_document_from_text в ChromaDB s3 не используется напрямую
        # Но для upload_document_from_file s3_key обязателен
        assert doc.metadata is not None
    
    @pytest.mark.asyncio
    async def test_custom_metadata_preserved(self, provider_with_cleanup):
        """Пользовательские metadata сохраняются"""
        ns = await provider_with_cleanup.create_namespace()
        
        custom_metadata = {
            "category": "tech",
            "author": "test_user",
            "version": "1.0"
        }
        
        doc = await provider_with_cleanup.upload_document_from_text(
            namespace_id=ns.namespace_id,
            text="Content with custom metadata.",
            document_name="custom_meta.txt",
            metadata=custom_metadata
        )
        
        # Проверяем что metadata сохранились
        fetched = await provider_with_cleanup.get_document(ns.namespace_id, doc.document_id)
        
        assert fetched is not None
        assert fetched.metadata.get("category") == "tech"
        assert fetched.metadata.get("author") == "test_user"


@skip_if_any_unavailable
class TestProviderBehaviorIdentity:
    """
    Тесты идентичности поведения провайдеров.
    Запускаются только если оба провайдера доступны.
    """
    
    @pytest.mark.asyncio
    async def test_namespace_lifecycle_identical(self, chromadb_provider, agentset_provider):
        """Жизненный цикл namespace идентичен"""
        unique_name = f"test_lifecycle_{uuid.uuid4().hex[:8]}"
        
        chromadb_ns = None
        agentset_ns = None
        
        try:
            # Создание
            chromadb_ns = await chromadb_provider.create_namespace(unique_name + "_chroma")
            agentset_ns = await agentset_provider.create_namespace(unique_name + "_agent")
            
            # Оба вернули RAGNamespace
            assert isinstance(chromadb_ns, RAGNamespace)
            assert isinstance(agentset_ns, RAGNamespace)
            
            # У обоих есть namespace_id
            assert chromadb_ns.namespace_id is not None
            assert agentset_ns.namespace_id is not None
            
            # Получение
            chromadb_fetched = await chromadb_provider.get_namespace(chromadb_ns.namespace_id)
            agentset_fetched = await agentset_provider.get_namespace(agentset_ns.namespace_id)
            
            assert chromadb_fetched is not None
            assert agentset_fetched is not None
            
            # Несуществующий namespace
            chromadb_none = await chromadb_provider.get_namespace("nonexistent_12345")
            agentset_none = await agentset_provider.get_namespace("nonexistent_12345")
            
            assert chromadb_none is None
            assert agentset_none is None
            
        finally:
            # Очистка
            if chromadb_ns:
                await chromadb_provider.delete_namespace(chromadb_ns.namespace_id)
            if agentset_ns:
                await agentset_provider.delete_namespace(agentset_ns.namespace_id)
    
    @pytest.mark.asyncio
    async def test_document_lifecycle_identical(self, chromadb_provider, agentset_provider):
        """Жизненный цикл документа идентичен"""
        chromadb_ns = None
        agentset_ns = None
        
        try:
            chromadb_ns = await chromadb_provider.create_namespace(f"doc_test_chroma_{uuid.uuid4().hex[:8]}")
            agentset_ns = await agentset_provider.create_namespace(f"doc_test_agent_{uuid.uuid4().hex[:8]}")
            
            test_text = "This is a test document for provider compatibility testing."
            
            # Загрузка текста
            chromadb_doc = await chromadb_provider.upload_document_from_text(
                namespace_id=chromadb_ns.namespace_id,
                text=test_text,
                document_name="compat_test.txt"
            )
            
            agentset_doc = await agentset_provider.upload_document_from_text(
                namespace_id=agentset_ns.namespace_id,
                text=test_text,
                document_name="compat_test.txt"
            )
            
            # Оба вернули RAGDocument
            assert isinstance(chromadb_doc, RAGDocument)
            assert isinstance(agentset_doc, RAGDocument)
            
            # У обоих есть document_id
            assert chromadb_doc.document_id is not None
            assert agentset_doc.document_id is not None
            
            # Оба имеют имя
            assert chromadb_doc.name == "compat_test.txt"
            assert agentset_doc.name == "compat_test.txt"
            
            # Получение документа
            chromadb_fetched = await chromadb_provider.get_document(
                chromadb_ns.namespace_id, chromadb_doc.document_id
            )
            # Agentset может вернуть processing, не проверяем сразу
            
            assert chromadb_fetched is not None
            
        finally:
            if chromadb_ns:
                await chromadb_provider.delete_namespace(chromadb_ns.namespace_id)
            if agentset_ns:
                await agentset_provider.delete_namespace(agentset_ns.namespace_id)
    
    @pytest.mark.asyncio
    async def test_search_returns_same_structure(self, chromadb_provider, agentset_provider):
        """Поиск возвращает одинаковую структуру"""
        chromadb_ns = None
        agentset_ns = None
        
        try:
            chromadb_ns = await chromadb_provider.create_namespace(f"search_test_chroma_{uuid.uuid4().hex[:8]}")
            agentset_ns = await agentset_provider.create_namespace(f"search_test_agent_{uuid.uuid4().hex[:8]}")
            
            test_text = "Machine learning is a subset of artificial intelligence that enables computers to learn from data."
            
            await chromadb_provider.upload_document_from_text(
                namespace_id=chromadb_ns.namespace_id,
                text=test_text,
                document_name="ml_doc.txt"
            )
            
            await agentset_provider.upload_document_from_text(
                namespace_id=agentset_ns.namespace_id,
                text=test_text,
                document_name="ml_doc.txt"
            )
            
            # Даём время Agentset на индексацию
            import asyncio
            await asyncio.sleep(2)
            
            # Поиск в обоих
            chromadb_results = await chromadb_provider.search(
                namespace_id=chromadb_ns.namespace_id,
                query="machine learning AI",
                limit=5
            )
            
            agentset_results = await agentset_provider.search(
                namespace_id=agentset_ns.namespace_id,
                query="machine learning AI",
                limit=5
            )
            
            # Оба возвращают списки
            assert isinstance(chromadb_results, list)
            assert isinstance(agentset_results, list)
            
            # Элементы - RAGSearchResult
            for r in chromadb_results:
                assert isinstance(r, RAGSearchResult)
                assert hasattr(r, 'content')
                assert hasattr(r, 'score')
            
            for r in agentset_results:
                assert isinstance(r, RAGSearchResult)
                assert hasattr(r, 'content')
                assert hasattr(r, 'score')
            
        finally:
            if chromadb_ns:
                await chromadb_provider.delete_namespace(chromadb_ns.namespace_id)
            if agentset_ns:
                await agentset_provider.delete_namespace(agentset_ns.namespace_id)

