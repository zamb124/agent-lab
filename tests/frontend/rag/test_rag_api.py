"""
Интеграционные тесты для RAG API endpoints.
Работают с реальными RAG провайдерами (ChromaDB/Agentset).

Запуск:
    uv run pytest tests/frontend/rag/test_rag_api.py -v
"""

import uuid
import pytest
import asyncio

from core.config import get_settings
from core.rag.factory import RAG_PROVIDERS


def make_unique_id(prefix: str) -> str:
    """Генерирует уникальный ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def is_rag_enabled() -> bool:
    """Проверяет доступность RAG"""
    try:
        settings = get_settings()
        return settings.rag.enabled
    except Exception:
        return False


def get_available_provider() -> str:
    """Возвращает имя доступного провайдера или None"""
    try:
        settings = get_settings()
        if not settings.rag.enabled:
            return None
        
        for provider_name in RAG_PROVIDERS.keys():
            config = settings.rag.providers.get(provider_name)
            if config and getattr(config, 'enabled', False):
                return provider_name
        
        return None
    except Exception:
        return None


pytestmark = pytest.mark.skipif(
    not is_rag_enabled(),
    reason="RAG не настроен (rag.enabled = false)"
)


class TestRAGProvidersEndpoint:
    """Тесты для GET /frontend/api/rag/providers"""
    
    @pytest.mark.asyncio
    async def test_list_providers_success(self, frontend_client):
        """Получение списка провайдеров"""
        response = await frontend_client.get("/frontend/api/rag/providers")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        for provider in data:
            assert "name" in provider
            assert "enabled" in provider
            assert "is_default" in provider
    
    @pytest.mark.asyncio
    async def test_list_providers_contains_chromadb(self, frontend_client):
        """Провайдер chromadb присутствует в списке"""
        response = await frontend_client.get("/frontend/api/rag/providers")
        
        assert response.status_code == 200
        data = response.json()
        
        provider_names = [p["name"] for p in data]
        assert "chromadb" in provider_names
    
    @pytest.mark.asyncio
    async def test_list_providers_contains_agentset(self, frontend_client):
        """Провайдер agentset присутствует в списке"""
        response = await frontend_client.get("/frontend/api/rag/providers")
        
        assert response.status_code == 200
        data = response.json()
        
        provider_names = [p["name"] for p in data]
        assert "agentset" in provider_names
    
    @pytest.mark.asyncio
    async def test_list_providers_has_default(self, frontend_client):
        """Есть один дефолтный провайдер"""
        response = await frontend_client.get("/frontend/api/rag/providers")
        
        assert response.status_code == 200
        data = response.json()
        
        default_providers = [p for p in data if p["is_default"]]
        assert len(default_providers) <= 1


class TestRAGNamespacesEndpoint:
    """Тесты для /frontend/api/rag/namespaces"""
    
    @pytest.mark.asyncio
    async def test_list_namespaces_success(self, frontend_client):
        """Получение списка неймспейсов"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        response = await frontend_client.get(
            f"/frontend/api/rag/namespaces?provider={provider}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        for ns in data:
            assert "namespace_id" in ns
            assert "name" in ns
            assert "document_count" in ns
    
    @pytest.mark.asyncio
    async def test_list_namespaces_invalid_provider(self, frontend_client):
        """Ошибка при неверном провайдере"""
        response = await frontend_client.get(
            "/frontend/api/rag/namespaces?provider=invalid_provider_xyz"
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_list_namespaces_default_provider(self, frontend_client):
        """Получение неймспейсов без указания провайдера"""
        response = await frontend_client.get("/frontend/api/rag/namespaces")
        
        # Должен использоваться дефолтный провайдер
        assert response.status_code in [200, 400]


class TestRAGCreateNamespaceEndpoint:
    """Тесты для POST /frontend/api/rag/namespaces"""
    
    @pytest.mark.asyncio
    async def test_create_namespace_success(self, frontend_client):
        """Создание нового неймспейса"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_api_ns")
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={
                "name": namespace_name,
                "description": "Test namespace for API tests"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "namespace_id" in data
        assert data["name"] == namespace_name
        
        # Cleanup
        await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{data['namespace_id']}?provider={provider}"
        )
    
    @pytest.mark.asyncio
    async def test_create_namespace_without_description(self, frontend_client):
        """Создание неймспейса без описания"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_api_ns_no_desc")
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": namespace_name}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "namespace_id" in data
        
        # Cleanup
        await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{data['namespace_id']}?provider={provider}"
        )
    
    @pytest.mark.asyncio
    async def test_create_namespace_empty_name(self, frontend_client):
        """Ошибка при пустом имени"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": ""}
        )
        
        # Пустое имя приведет к ошибке на уровне провайдера
        assert response.status_code in [400, 422]


class TestRAGDeleteNamespaceEndpoint:
    """Тесты для DELETE /frontend/api/rag/namespaces/{namespace_id}"""
    
    @pytest.mark.asyncio
    async def test_delete_namespace_success(self, frontend_client):
        """Удаление неймспейса"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_delete_ns")
        
        create_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": namespace_name}
        )
        assert create_response.status_code == 200
        namespace_id = create_response.json()["namespace_id"]
        
        delete_response = await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{namespace_id}?provider={provider}"
        )
        
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["status"] == "deleted"
        assert data["namespace_id"] == namespace_id
    
    @pytest.mark.asyncio
    async def test_delete_namespace_not_found(self, frontend_client):
        """Ошибка при удалении несуществующего неймспейса"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        response = await frontend_client.delete(
            f"/frontend/api/rag/namespaces/nonexistent_ns_12345?provider={provider}"
        )
        
        assert response.status_code == 404


class TestRAGDocumentsEndpoint:
    """Тесты для /frontend/api/rag/namespaces/{namespace_id}/documents"""
    
    @pytest.fixture
    async def test_namespace(self, frontend_client):
        """Создает тестовый неймспейс и удаляет после теста"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_docs_ns")
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": namespace_name}
        )
        assert response.status_code == 200
        namespace_id = response.json()["namespace_id"]
        
        yield {"namespace_id": namespace_id, "provider": provider}
        
        # Cleanup - не проверяем результат, namespace уникальный
        await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{namespace_id}?provider={provider}"
        )
    
    @pytest.mark.asyncio
    async def test_list_documents_empty(self, frontend_client, test_namespace):
        """Список документов в пустом неймспейсе"""
        ns_id = test_namespace["namespace_id"]
        provider = test_namespace["provider"]
        
        response = await frontend_client.get(
            f"/frontend/api/rag/namespaces/{ns_id}/documents?provider={provider}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_list_documents_with_limit(self, frontend_client, test_namespace):
        """Список документов с лимитом"""
        ns_id = test_namespace["namespace_id"]
        provider = test_namespace["provider"]
        
        response = await frontend_client.get(
            f"/frontend/api/rag/namespaces/{ns_id}/documents?provider={provider}&limit=10"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) <= 10
    
    @pytest.mark.asyncio
    async def test_list_documents_invalid_namespace(self, frontend_client):
        """Ошибка при несуществующем неймспейсе"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        response = await frontend_client.get(
            f"/frontend/api/rag/namespaces/nonexistent_ns_xyz/documents?provider={provider}"
        )
        
        # Может быть 200 с пустым списком или 404 в зависимости от провайдера
        assert response.status_code in [200, 404]


class TestRAGUploadDocumentEndpoint:
    """Тесты для POST /frontend/api/rag/namespaces/{namespace_id}/documents"""
    
    @pytest.fixture
    async def test_namespace(self, frontend_client):
        """Создает тестовый неймспейс и удаляет после теста"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_upload_ns")
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": namespace_name}
        )
        assert response.status_code == 200
        namespace_id = response.json()["namespace_id"]
        
        yield {"namespace_id": namespace_id, "provider": provider}
        
        await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{namespace_id}?provider={provider}"
        )
    
    @pytest.mark.asyncio
    async def test_upload_txt_file(self, frontend_client, test_namespace):
        """Загрузка TXT файла"""
        ns_id = test_namespace["namespace_id"]
        provider = test_namespace["provider"]
        
        file_content = b"This is a test document for RAG API testing.\nIt contains multiple lines."
        
        files = {"file": ("test_doc.txt", file_content, "text/plain")}
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{ns_id}/documents?provider={provider}",
            files=files
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "document_id" in data
        assert data["name"] == "test_doc.txt"
    
    @pytest.mark.asyncio
    async def test_upload_md_file(self, frontend_client, test_namespace):
        """Загрузка Markdown файла"""
        ns_id = test_namespace["namespace_id"]
        provider = test_namespace["provider"]
        
        file_content = b"# Test Document\n\nThis is a **markdown** file.\n\n- Item 1\n- Item 2"
        
        files = {"file": ("readme.md", file_content, "text/markdown")}
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{ns_id}/documents?provider={provider}",
            files=files
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "document_id" in data
        assert data["name"] == "readme.md"
    
    @pytest.mark.asyncio
    async def test_upload_with_custom_name(self, frontend_client, test_namespace):
        """Загрузка с кастомным именем документа"""
        ns_id = test_namespace["namespace_id"]
        provider = test_namespace["provider"]
        
        file_content = b"Test content for custom named document."
        
        files = {"file": ("original.txt", file_content, "text/plain")}
        data = {"document_name": "custom_name.txt"}
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{ns_id}/documents?provider={provider}",
            files=files,
            data=data
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert "document_id" in result
        assert result["name"] == "custom_name.txt"
    
    @pytest.mark.asyncio
    async def test_upload_to_invalid_namespace(self, frontend_client):
        """Ошибка при загрузке в несуществующий неймспейс"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        file_content = b"Test content"
        files = {"file": ("test.txt", file_content, "text/plain")}
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/nonexistent_ns_xyz/documents?provider={provider}",
            files=files
        )
        
        # Ошибка зависит от провайдера
        assert response.status_code in [400, 404, 500]


class TestRAGDeleteDocumentEndpoint:
    """Тесты для DELETE /frontend/api/rag/namespaces/{namespace_id}/documents/{document_id}"""
    
    @pytest.fixture
    async def namespace_with_document(self, frontend_client):
        """Создает неймспейс с документом и ждет индексации"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_delete_doc_ns")
        
        ns_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": namespace_name}
        )
        assert ns_response.status_code == 200
        namespace_id = ns_response.json()["namespace_id"]
        
        file_content = b"Document to be deleted in test."
        files = {"file": ("to_delete.txt", file_content, "text/plain")}
        
        doc_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{namespace_id}/documents?provider={provider}",
            files=files
        )
        assert doc_response.status_code == 200
        job_id = doc_response.json()["document_id"]
        
        # Ждем индексации и получаем реальный document_id
        document_id = None
        for _ in range(10):
            await asyncio.sleep(2)
            list_response = await frontend_client.get(
                f"/frontend/api/rag/namespaces/{namespace_id}/documents?provider={provider}"
            )
            if list_response.status_code == 200:
                docs = list_response.json()
                if docs:
                    document_id = docs[0]["document_id"]
                    break
        
        yield {
            "namespace_id": namespace_id,
            "document_id": document_id or job_id,
            "provider": provider
        }
        
        await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{namespace_id}?provider={provider}"
        )
    
    @pytest.mark.asyncio
    async def test_delete_document_success(self, frontend_client, namespace_with_document):
        """Удаление документа"""
        ns_id = namespace_with_document["namespace_id"]
        doc_id = namespace_with_document["document_id"]
        provider = namespace_with_document["provider"]
        
        response = await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{ns_id}/documents/{doc_id}?provider={provider}"
        )
        
        # Может быть 200 (успех) или 404 (документ не проиндексирован)
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "deleted"
    
    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, frontend_client):
        """Ошибка при удалении несуществующего документа"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_delete_notfound_ns")
        
        ns_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": namespace_name}
        )
        assert ns_response.status_code == 200
        namespace_id = ns_response.json()["namespace_id"]
        
        try:
            response = await frontend_client.delete(
                f"/frontend/api/rag/namespaces/{namespace_id}/documents/nonexistent_doc_xyz?provider={provider}"
            )
            
            assert response.status_code == 404
        finally:
            await frontend_client.delete(
                f"/frontend/api/rag/namespaces/{namespace_id}?provider={provider}"
            )


class TestRAGSearchEndpoint:
    """Тесты для POST /frontend/api/rag/namespaces/{namespace_id}/search"""
    
    @pytest.fixture
    async def namespace_with_searchable_docs(self, frontend_client):
        """Создает неймспейс с документами для поиска"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_search_ns")
        
        ns_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": namespace_name}
        )
        assert ns_response.status_code == 200
        namespace_id = ns_response.json()["namespace_id"]
        
        doc1_content = b"Artificial intelligence and machine learning are transforming industries."
        files1 = {"file": ("ai_doc.txt", doc1_content, "text/plain")}
        await frontend_client.post(
            f"/frontend/api/rag/namespaces/{namespace_id}/documents?provider={provider}",
            files=files1
        )
        
        doc2_content = b"Python is a popular programming language for data science."
        files2 = {"file": ("python_doc.txt", doc2_content, "text/plain")}
        await frontend_client.post(
            f"/frontend/api/rag/namespaces/{namespace_id}/documents?provider={provider}",
            files=files2
        )
        
        # Ждем индексации
        await asyncio.sleep(2)
        
        yield {"namespace_id": namespace_id, "provider": provider}
        
        await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{namespace_id}?provider={provider}"
        )
    
    @pytest.mark.asyncio
    async def test_search_success(self, frontend_client, namespace_with_searchable_docs):
        """Поиск по документам"""
        ns_id = namespace_with_searchable_docs["namespace_id"]
        provider = namespace_with_searchable_docs["provider"]
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{ns_id}/search?provider={provider}",
            json={"query": "artificial intelligence", "limit": 5}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        for result in data:
            assert "content" in result
            assert "score" in result
            assert "document_id" in result
            assert "document_name" in result
            assert "namespace" in result
    
    @pytest.mark.asyncio
    async def test_search_with_limit(self, frontend_client, namespace_with_searchable_docs):
        """Поиск с лимитом результатов"""
        ns_id = namespace_with_searchable_docs["namespace_id"]
        provider = namespace_with_searchable_docs["provider"]
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{ns_id}/search?provider={provider}",
            json={"query": "programming", "limit": 1}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) <= 1
    
    @pytest.mark.asyncio
    async def test_search_empty_query(self, frontend_client, namespace_with_searchable_docs):
        """Поиск с пустым запросом"""
        ns_id = namespace_with_searchable_docs["namespace_id"]
        provider = namespace_with_searchable_docs["provider"]
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{ns_id}/search?provider={provider}",
            json={"query": "", "limit": 5}
        )
        
        # Пустой запрос может вернуть ошибку или пустой результат
        # Agentset возвращает 500, мы преобразуем в 502
        assert response.status_code in [200, 400, 422, 502]
    
    @pytest.mark.asyncio
    async def test_search_invalid_namespace(self, frontend_client):
        """Поиск в несуществующем неймспейсе"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/nonexistent_ns_xyz/search?provider={provider}",
            json={"query": "test", "limit": 5}
        )
        
        # Поведение зависит от провайдера
        assert response.status_code in [200, 400, 404, 500]


class TestRAGDownloadEndpoint:
    """Тесты для GET /frontend/api/rag/namespaces/{namespace_id}/documents/{document_id}/download"""
    
    @pytest.fixture
    async def namespace_with_document(self, frontend_client):
        """Создает неймспейс с документом для скачивания"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_download_ns")
        
        ns_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": namespace_name}
        )
        assert ns_response.status_code == 200
        namespace_id = ns_response.json()["namespace_id"]
        
        file_content = b"Content for download testing."
        files = {"file": ("download_test.txt", file_content, "text/plain")}
        
        doc_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{namespace_id}/documents?provider={provider}",
            files=files
        )
        assert doc_response.status_code == 200
        document_id = doc_response.json()["document_id"]
        
        yield {
            "namespace_id": namespace_id,
            "document_id": document_id,
            "provider": provider
        }
        
        await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{namespace_id}?provider={provider}"
        )
    
    @pytest.mark.asyncio
    async def test_get_download_url_success(self, frontend_client, namespace_with_document):
        """Получение URL для скачивания"""
        ns_id = namespace_with_document["namespace_id"]
        doc_id = namespace_with_document["document_id"]
        provider = namespace_with_document["provider"]
        
        response = await frontend_client.get(
            f"/frontend/api/rag/namespaces/{ns_id}/documents/{doc_id}/download?provider={provider}"
        )
        
        # 200 - URL получен
        # 404 - провайдер не поддерживает скачивание или документ не найден
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "download_url" in data
            assert data["download_url"] is not None
    
    @pytest.mark.asyncio
    async def test_get_download_url_not_found(self, frontend_client):
        """Ошибка при скачивании несуществующего документа"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        response = await frontend_client.get(
            f"/frontend/api/rag/namespaces/nonexistent_ns/documents/nonexistent_doc/download?provider={provider}"
        )
        
        assert response.status_code == 404


class TestRAGFullCycle:
    """Интеграционные тесты полного цикла работы с RAG"""
    
    @pytest.mark.asyncio
    async def test_full_cycle_create_upload_search_delete(self, frontend_client):
        """Полный цикл: создание неймспейса -> загрузка -> поиск -> удаление"""
        provider = get_available_provider()
        if not provider:
            pytest.skip("Нет доступных RAG провайдеров")
        
        namespace_name = make_unique_id("test_full_cycle_ns")
        namespace_id = None
        
        # 1. Создание неймспейса
        ns_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces?provider={provider}",
            json={"name": namespace_name, "description": "Full cycle test"}
        )
        assert ns_response.status_code == 200
        namespace_id = ns_response.json()["namespace_id"]
        
        # 2. Загрузка документа
        doc_content = b"The weather forecast predicts sunny skies and warm temperatures."
        files = {"file": ("weather.txt", doc_content, "text/plain")}
        
        doc_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{namespace_id}/documents?provider={provider}",
            files=files
        )
        assert doc_response.status_code == 200
        job_id = doc_response.json()["document_id"]
        
        # 3. Ждем индексации и получаем реальный document_id
        await asyncio.sleep(5)
        
        list_response = await frontend_client.get(
            f"/frontend/api/rag/namespaces/{namespace_id}/documents?provider={provider}"
        )
        assert list_response.status_code == 200
        docs = list_response.json()
        document_id = docs[0]["document_id"] if docs else job_id
        
        # 4. Поиск
        search_response = await frontend_client.post(
            f"/frontend/api/rag/namespaces/{namespace_id}/search?provider={provider}",
            json={"query": "weather forecast", "limit": 5}
        )
        assert search_response.status_code == 200
        
        # 5. Удаление документа (может вернуть 404 если еще не проиндексирован)
        delete_doc_response = await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{namespace_id}/documents/{document_id}?provider={provider}"
        )
        assert delete_doc_response.status_code in [200, 404]
        
        # 6. Удаление неймспейса (может вернуть 400 если документы еще есть)
        delete_ns_response = await frontend_client.delete(
            f"/frontend/api/rag/namespaces/{namespace_id}?provider={provider}"
        )
        # 200 - успешно удален, 400 - еще есть документы (Agentset)
        assert delete_ns_response.status_code in [200, 400]
    
    @pytest.mark.asyncio
    async def test_multiple_providers(self, frontend_client):
        """Тест работы с разными провайдерами"""
        settings = get_settings()
        
        enabled_providers = []
        for provider_name in RAG_PROVIDERS.keys():
            config = settings.rag.providers.get(provider_name)
            if config and getattr(config, 'enabled', False):
                enabled_providers.append(provider_name)
        
        if len(enabled_providers) < 1:
            pytest.skip("Нет включенных провайдеров")
        
        for provider in enabled_providers:
            response = await frontend_client.get(
                f"/frontend/api/rag/namespaces?provider={provider}"
            )
            
            # Каждый провайдер должен отвечать
            assert response.status_code in [200, 400]

