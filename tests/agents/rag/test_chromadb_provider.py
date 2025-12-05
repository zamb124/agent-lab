"""
Интеграционные тесты для ChromaDB RAG провайдера.
Тесты работают с реальным ChromaDB сервером.

Запуск ChromaDB:
    docker-compose up -d chroma

Запуск тестов:
    uv run pytest tests/agents/rag/test_chromadb_provider.py -v
"""

import pytest
import uuid
import asyncio

from core.rag.providers.chromadb_provider import ChromaDBRAGProvider
from core.rag.models import RAGDocument, RAGSearchResult, RAGNamespace
from core.rag.factory import RAG_PROVIDERS, get_rag_provider
from core.config import get_settings


def is_chromadb_available() -> bool:
    """Проверяет доступность ChromaDB сервера"""
    try:
        import chromadb
        
        # Для локальных тестов используем localhost:8100
        client = chromadb.HttpClient(host="localhost", port=8100)
        client.heartbeat()
        return True
    except Exception:
        return False


skip_if_chromadb_unavailable = pytest.mark.skipif(
    not is_chromadb_available(),
    reason="ChromaDB сервер недоступен. Запустите: docker-compose up -d chroma"
)


@pytest.fixture
def unique_namespace():
    """Генерирует уникальное имя namespace для теста"""
    return f"test_ns_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def chromadb_provider():
    """Создает реальный ChromaDB провайдер для тестов"""
    settings = get_settings()
    chromadb_config = settings.rag.providers.get("chromadb")
    
    config = {
        "host": "localhost",  # Для локальных тестов
        "port": 8100,
        "embedding_api_key": chromadb_config.embedding_api_key if chromadb_config else settings.llm.openrouter.api_key,
    }
    
    # Получаем embedding конфигурацию
    embedding_config = None
    if hasattr(settings.rag, 'embedding') and settings.rag.embedding:
        embedding_config = settings.rag.embedding.model_dump()
    
    provider = ChromaDBRAGProvider(config, embedding_config=embedding_config)
    yield provider
    await provider.close()


@pytest.fixture
async def chromadb_provider_with_cleanup(chromadb_provider, unique_namespace):
    """Провайдер с автоматической очисткой namespace после теста"""
    created_namespaces = []
    
    class ProviderWrapper:
        def __init__(self, provider):
            self._provider = provider
            self.namespace = unique_namespace
        
        def __getattr__(self, name):
            return getattr(self._provider, name)
        
        async def create_namespace(self, name=None, **kwargs):
            ns_name = name or self.namespace
            ns = await self._provider.create_namespace(ns_name, **kwargs)
            created_namespaces.append(ns.namespace_id)
            return ns
    
    wrapper = ProviderWrapper(chromadb_provider)
    yield wrapper
    
    for ns_id in created_namespaces:
        try:
            await chromadb_provider.delete_namespace(ns_id)
        except Exception:
            pass


class TestChromaDBProviderRegistration:
    """Тесты регистрации провайдера"""
    
    def test_chromadb_registered_in_factory(self):
        """ChromaDB провайдер зарегистрирован в фабрике"""
        assert "chromadb" in RAG_PROVIDERS
        assert RAG_PROVIDERS["chromadb"] == ChromaDBRAGProvider


@skip_if_chromadb_unavailable
class TestChromaDBProviderNamespaces:
    """Тесты работы с namespaces"""
    
    @pytest.mark.asyncio
    async def test_create_namespace(self, chromadb_provider_with_cleanup):
        """Создание namespace"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace(
            description="Test namespace for integration tests"
        )
        
        assert isinstance(namespace, RAGNamespace)
        assert namespace.namespace_id is not None
        assert namespace.document_count == 0
    
    @pytest.mark.asyncio
    async def test_get_namespace(self, chromadb_provider_with_cleanup):
        """Получение namespace"""
        provider = chromadb_provider_with_cleanup
        
        created = await provider.create_namespace()
        
        fetched = await provider.get_namespace(created.namespace_id)
        
        assert fetched is not None
        assert fetched.namespace_id == created.namespace_id
    
    @pytest.mark.asyncio
    async def test_get_namespace_not_exists(self, chromadb_provider):
        """Получение несуществующего namespace"""
        namespace = await chromadb_provider.get_namespace("nonexistent_namespace_12345")
        assert namespace is None
    
    @pytest.mark.asyncio
    async def test_list_namespaces(self, chromadb_provider_with_cleanup):
        """Список namespaces"""
        provider = chromadb_provider_with_cleanup
        
        await provider.create_namespace()
        
        namespaces = await provider.list_namespaces()
        
        assert isinstance(namespaces, list)
        assert len(namespaces) >= 1
        assert all(isinstance(ns, RAGNamespace) for ns in namespaces)
    
    @pytest.mark.asyncio
    async def test_delete_namespace(self, chromadb_provider, unique_namespace):
        """Удаление namespace"""
        namespace = await chromadb_provider.create_namespace(name=unique_namespace)
        
        result = await chromadb_provider.delete_namespace(namespace.namespace_id)
        
        assert result is True
        
        fetched = await chromadb_provider.get_namespace(namespace.namespace_id)
        assert fetched is None


@skip_if_chromadb_unavailable
class TestChromaDBProviderDocuments:
    """Тесты работы с документами"""
    
    @pytest.mark.asyncio
    async def test_upload_document_from_text(self, chromadb_provider_with_cleanup):
        """Загрузка текстового документа"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        document = await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text="This is a test document about artificial intelligence and machine learning. "
                 "AI systems can process large amounts of data and make predictions.",
            document_name="test_ai_document.txt",
            metadata={"category": "tech", "source": "test"}
        )
        
        assert isinstance(document, RAGDocument)
        assert document.document_id is not None
        assert document.name == "test_ai_document.txt"
        assert document.namespace == namespace.namespace_id
        assert document.status == "completed"
    
    @pytest.mark.asyncio
    async def test_get_document(self, chromadb_provider_with_cleanup):
        """Получение документа"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        uploaded = await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text="Test content for document retrieval.",
            document_name="retrieval_test.txt"
        )
        
        fetched = await provider.get_document(namespace.namespace_id, uploaded.document_id)
        
        assert fetched is not None
        assert fetched.document_id == uploaded.document_id
    
    @pytest.mark.asyncio
    async def test_get_document_not_found(self, chromadb_provider_with_cleanup):
        """Документ не найден"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        document = await provider.get_document(namespace.namespace_id, "nonexistent_doc_id")
        
        assert document is None
    
    @pytest.mark.asyncio
    async def test_list_documents(self, chromadb_provider_with_cleanup):
        """Список документов"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text="First document content.",
            document_name="doc1.txt"
        )
        
        await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text="Second document content.",
            document_name="doc2.txt"
        )
        
        documents = await provider.list_documents(namespace.namespace_id)
        
        assert len(documents) == 2
        names = {d.name for d in documents}
        assert "doc1.txt" in names
        assert "doc2.txt" in names
    
    @pytest.mark.asyncio
    async def test_delete_document(self, chromadb_provider_with_cleanup):
        """Удаление документа"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        document = await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text="Document to be deleted.",
            document_name="to_delete.txt"
        )
        
        result = await provider.delete_document(namespace.namespace_id, document.document_id)
        
        assert result is True
        
        fetched = await provider.get_document(namespace.namespace_id, document.document_id)
        assert fetched is None


@skip_if_chromadb_unavailable
class TestChromaDBProviderSearch:
    """Тесты поиска"""
    
    @pytest.mark.asyncio
    async def test_search_basic(self, chromadb_provider_with_cleanup):
        """Базовый семантический поиск"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text="Python is a programming language known for its simplicity and readability. "
                 "It is widely used in data science, web development, and automation.",
            document_name="python_guide.txt"
        )
        
        await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text="Cooking pasta requires boiling water, adding salt, and cooking for 8-10 minutes. "
                 "Drain and serve with your favorite sauce.",
            document_name="cooking_tips.txt"
        )
        
        results = await provider.search(
            namespace_id=namespace.namespace_id,
            query="programming language for data science",
            limit=5
        )
        
        assert len(results) >= 1
        assert isinstance(results[0], RAGSearchResult)
        assert results[0].score > 0
        assert "python" in results[0].content.lower() or "programming" in results[0].content.lower()
    
    @pytest.mark.asyncio
    async def test_search_with_metadata_filter(self, chromadb_provider_with_cleanup):
        """Поиск с фильтром по metadata"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text="Technical documentation about APIs and integration.",
            document_name="tech_doc.txt",
            metadata={"category": "tech"}
        )
        
        await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text="Business report about quarterly sales.",
            document_name="business_doc.txt",
            metadata={"category": "business"}
        )
        
        results = await provider.search(
            namespace_id=namespace.namespace_id,
            query="documentation",
            limit=5,
            filters={"category": "tech"}
        )
        
        assert len(results) >= 1
        assert results[0].metadata.get("category") == "tech"
    
    @pytest.mark.asyncio
    async def test_search_empty_results(self, chromadb_provider_with_cleanup):
        """Поиск без результатов"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        results = await provider.search(
            namespace_id=namespace.namespace_id,
            query="something completely unrelated",
            limit=5
        )
        
        assert isinstance(results, list)


@skip_if_chromadb_unavailable
class TestChromaDBProviderRawMethods:
    """Тесты raw методов для интеграции с CRM"""
    
    @pytest.mark.asyncio
    async def test_add_raw_and_query_raw(self, chromadb_provider_with_cleanup):
        """Прямое добавление и запрос для CRM интеграции"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        await provider.add_raw(
            namespace_id=namespace.namespace_id,
            ids=["entity_person_1", "entity_org_1"],
            documents=[
                "John Smith is a software engineer at TechCorp.",
                "TechCorp is a technology company specializing in AI solutions."
            ],
            metadatas=[
                {"entity_type": "person", "company_id": "test_company", "name": "John Smith"},
                {"entity_type": "organization", "company_id": "test_company", "name": "TechCorp"}
            ]
        )
        
        results = await provider.query_raw(
            namespace_id=namespace.namespace_id,
            query_texts=["software engineer"],
            n_results=5,
            where={"company_id": "test_company"}
        )
        
        assert "ids" in results
        assert len(results["ids"][0]) >= 1
    
    @pytest.mark.asyncio
    async def test_get_raw(self, chromadb_provider_with_cleanup):
        """Прямое получение записей"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        await provider.add_raw(
            namespace_id=namespace.namespace_id,
            ids=["test_id_1", "test_id_2"],
            documents=["Document 1", "Document 2"],
            metadatas=[{"key": "value1"}, {"key": "value2"}]
        )
        
        results = await provider.get_raw(
            namespace_id=namespace.namespace_id,
            ids=["test_id_1"]
        )
        
        assert "ids" in results
        assert "test_id_1" in results["ids"]
    
    @pytest.mark.asyncio
    async def test_update_raw(self, chromadb_provider_with_cleanup):
        """Прямое обновление записей"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        await provider.add_raw(
            namespace_id=namespace.namespace_id,
            ids=["update_test_id"],
            documents=["Original content"],
            metadatas=[{"status": "draft"}]
        )
        
        await provider.update_raw(
            namespace_id=namespace.namespace_id,
            ids=["update_test_id"],
            documents=["Updated content"],
            metadatas=[{"status": "published"}]
        )
        
        results = await provider.get_raw(
            namespace_id=namespace.namespace_id,
            ids=["update_test_id"]
        )
        
        assert results["metadatas"][0]["status"] == "published"
    
    @pytest.mark.asyncio
    async def test_delete_raw_by_ids(self, chromadb_provider_with_cleanup):
        """Прямое удаление по ID"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        await provider.add_raw(
            namespace_id=namespace.namespace_id,
            ids=["delete_test_1", "delete_test_2"],
            documents=["Doc 1", "Doc 2"],
            metadatas=[{"marker": "1"}, {"marker": "2"}]
        )
        
        await provider.delete_raw(
            namespace_id=namespace.namespace_id,
            ids=["delete_test_1"]
        )
        
        results = await provider.get_raw(
            namespace_id=namespace.namespace_id,
            ids=["delete_test_1", "delete_test_2"]
        )
        
        assert "delete_test_1" not in results["ids"]
        assert "delete_test_2" in results["ids"]
    
    @pytest.mark.asyncio
    async def test_delete_raw_by_where(self, chromadb_provider_with_cleanup):
        """Прямое удаление по фильтру where"""
        provider = chromadb_provider_with_cleanup
        
        namespace = await provider.create_namespace()
        
        await provider.add_raw(
            namespace_id=namespace.namespace_id,
            ids=["keep_id", "delete_by_filter_id"],
            documents=["Keep this", "Delete this"],
            metadatas=[
                {"status": "active"},
                {"status": "deleted"}
            ]
        )
        
        await provider.delete_raw(
            namespace_id=namespace.namespace_id,
            where={"status": "deleted"}
        )
        
        results = await provider.get_raw(
            namespace_id=namespace.namespace_id,
            ids=["keep_id", "delete_by_filter_id"]
        )
        
        assert "keep_id" in results["ids"]
        assert "delete_by_filter_id" not in results["ids"]


@skip_if_chromadb_unavailable
class TestChromaDBProviderFilters:
    """Тесты фильтров ChromaDB для CRM"""
    
    @pytest.mark.asyncio
    async def test_filter_eq(self, chromadb_provider_with_cleanup):
        """Фильтр $eq"""
        provider = chromadb_provider_with_cleanup
        namespace = await provider.create_namespace()
        
        await provider.add_raw(
            namespace_id=namespace.namespace_id,
            ids=["id1", "id2"],
            documents=["Doc 1", "Doc 2"],
            metadatas=[
                {"type": "person"},
                {"type": "organization"}
            ]
        )
        
        results = await provider.get_raw(
            namespace_id=namespace.namespace_id,
            where={"type": {"$eq": "person"}}
        )
        
        assert len(results["ids"]) == 1
        assert results["metadatas"][0]["type"] == "person"
    
    @pytest.mark.asyncio
    async def test_filter_in(self, chromadb_provider_with_cleanup):
        """Фильтр $in"""
        provider = chromadb_provider_with_cleanup
        namespace = await provider.create_namespace()
        
        await provider.add_raw(
            namespace_id=namespace.namespace_id,
            ids=["id1", "id2", "id3"],
            documents=["Doc 1", "Doc 2", "Doc 3"],
            metadatas=[
                {"category": "tech"},
                {"category": "business"},
                {"category": "science"}
            ]
        )
        
        results = await provider.get_raw(
            namespace_id=namespace.namespace_id,
            where={"category": {"$in": ["tech", "science"]}}
        )
        
        assert len(results["ids"]) == 2
        categories = {m["category"] for m in results["metadatas"]}
        assert categories == {"tech", "science"}
    
    @pytest.mark.asyncio
    async def test_filter_and(self, chromadb_provider_with_cleanup):
        """Фильтр $and"""
        provider = chromadb_provider_with_cleanup
        namespace = await provider.create_namespace()
        
        await provider.add_raw(
            namespace_id=namespace.namespace_id,
            ids=["id1", "id2", "id3"],
            documents=["Doc 1", "Doc 2", "Doc 3"],
            metadatas=[
                {"type": "person", "status": "active"},
                {"type": "person", "status": "inactive"},
                {"type": "organization", "status": "active"}
            ]
        )
        
        results = await provider.get_raw(
            namespace_id=namespace.namespace_id,
            where={
                "$and": [
                    {"type": "person"},
                    {"status": "active"}
                ]
            }
        )
        
        assert len(results["ids"]) == 1
        assert results["metadatas"][0]["type"] == "person"
        assert results["metadatas"][0]["status"] == "active"
    
    @pytest.mark.asyncio
    async def test_filter_or(self, chromadb_provider_with_cleanup):
        """Фильтр $or"""
        provider = chromadb_provider_with_cleanup
        namespace = await provider.create_namespace()
        
        await provider.add_raw(
            namespace_id=namespace.namespace_id,
            ids=["id1", "id2", "id3"],
            documents=["Doc 1", "Doc 2", "Doc 3"],
            metadatas=[
                {"priority": "high"},
                {"priority": "medium"},
                {"priority": "low"}
            ]
        )
        
        results = await provider.get_raw(
            namespace_id=namespace.namespace_id,
            where={
                "$or": [
                    {"priority": "high"},
                    {"priority": "low"}
                ]
            }
        )
        
        assert len(results["ids"]) == 2
        priorities = {m["priority"] for m in results["metadatas"]}
        assert priorities == {"high", "low"}


@skip_if_chromadb_unavailable  
class TestChromaDBProviderChunking:
    """Тесты chunking"""
    
    @pytest.mark.asyncio
    async def test_long_document_chunked(self, chromadb_provider_with_cleanup):
        """Длинный документ разбивается на chunks"""
        provider = chromadb_provider_with_cleanup
        namespace = await provider.create_namespace()
        
        long_text = "This is a test sentence. " * 500
        
        document = await provider.upload_document_from_text(
            namespace_id=namespace.namespace_id,
            text=long_text,
            document_name="long_doc.txt"
        )
        
        assert document.status == "completed"
        
        results = await provider.get_raw(
            namespace_id=namespace.namespace_id,
            where={"document_id": document.document_id}
        )
        
        assert len(results["ids"]) > 1


@skip_if_chromadb_unavailable
class TestChromaDBProviderRealFiles:
    """Тесты загрузки реальных файлов (DOCX, XLSX)"""
    
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
    async def test_upload_docx_file(self, provider_with_cleanup):
        """Загрузка DOCX файла"""
        from pathlib import Path
        
        docx_path = Path(__file__).parent / "Анкета 09.25.docx"
        if not docx_path.exists():
            pytest.skip(f"Тестовый DOCX не найден: {docx_path}")
        
        namespace = await provider_with_cleanup.create_namespace()
        
        document = await provider_with_cleanup.upload_document_from_file(
            namespace_id=namespace.namespace_id,
            file_path=str(docx_path),
            document_name="anketa.docx",
            metadata={"type": "form", "format": "docx"}
        )
        
        assert document is not None
        assert document.document_id is not None
        assert document.status == "completed"
        assert document.metadata.get("file_type") == "docx"
        assert "s3_key" in document.metadata
        
        # Проверяем что документ проиндексирован
        results = await provider_with_cleanup.search(
            namespace_id=namespace.namespace_id,
            query="анкета",
            limit=5
        )
        
        assert len(results) >= 1
        print(f"DOCX: найдено {len(results)} результатов")
        print(f"Первый результат: {results[0].content[:200]}...")
    
    @pytest.mark.asyncio
    async def test_upload_xlsx_file(self, provider_with_cleanup):
        """Загрузка XLSX файла"""
        from pathlib import Path
        
        xlsx_path = Path(__file__).parent / "all_products.xlsx"
        if not xlsx_path.exists():
            pytest.skip(f"Тестовый XLSX не найден: {xlsx_path}")
        
        namespace = await provider_with_cleanup.create_namespace()
        
        document = await provider_with_cleanup.upload_document_from_file(
            namespace_id=namespace.namespace_id,
            file_path=str(xlsx_path),
            document_name="products.xlsx",
            metadata={"type": "catalog", "format": "xlsx"}
        )
        
        assert document is not None
        assert document.document_id is not None
        assert document.status == "completed"
        assert document.metadata.get("file_type") == "xlsx"
        assert "s3_key" in document.metadata
        
        # Проверяем что документ проиндексирован
        results = await provider_with_cleanup.search(
            namespace_id=namespace.namespace_id,
            query="product",
            limit=5
        )
        
        assert len(results) >= 1
        print(f"XLSX: найдено {len(results)} результатов")
        print(f"Первый результат: {results[0].content[:200]}...")
    
    @pytest.mark.asyncio
    async def test_search_in_docx_content(self, provider_with_cleanup):
        """Поиск по содержимому DOCX"""
        from pathlib import Path
        
        docx_path = Path(__file__).parent / "Анкета 09.25.docx"
        if not docx_path.exists():
            pytest.skip(f"Тестовый DOCX не найден: {docx_path}")
        
        namespace = await provider_with_cleanup.create_namespace()
        
        await provider_with_cleanup.upload_document_from_file(
            namespace_id=namespace.namespace_id,
            file_path=str(docx_path),
            document_name="anketa.docx"
        )
        
        # Ищем по русскому тексту
        results = await provider_with_cleanup.search(
            namespace_id=namespace.namespace_id,
            query="форма заявления документ",
            limit=10
        )
        
        print(f"Поиск в DOCX: найдено {len(results)} результатов")
        for i, r in enumerate(results[:3]):
            print(f"  {i+1}. Score={r.score:.2f}: {r.content[:100]}...")
        
        assert isinstance(results, list)
    
    @pytest.mark.asyncio
    async def test_search_in_xlsx_content(self, provider_with_cleanup):
        """Поиск по содержимому XLSX"""
        from pathlib import Path
        
        xlsx_path = Path(__file__).parent / "all_products.xlsx"
        if not xlsx_path.exists():
            pytest.skip(f"Тестовый XLSX не найден: {xlsx_path}")
        
        namespace = await provider_with_cleanup.create_namespace()
        
        await provider_with_cleanup.upload_document_from_file(
            namespace_id=namespace.namespace_id,
            file_path=str(xlsx_path),
            document_name="products.xlsx"
        )
        
        # Ищем по содержимому таблицы
        results = await provider_with_cleanup.search(
            namespace_id=namespace.namespace_id,
            query="цена товар артикул",
            limit=10
        )
        
        print(f"Поиск в XLSX: найдено {len(results)} результатов")
        for i, r in enumerate(results[:3]):
            print(f"  {i+1}. Score={r.score:.2f}: {r.content[:100]}...")
        
        assert isinstance(results, list)
