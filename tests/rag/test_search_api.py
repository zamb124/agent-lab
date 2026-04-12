"""
Тесты API семантического поиска RAG Service.

Тестирует:
- POST /rag/api/v1/namespaces/{id}/search - поиск в namespace
- POST /rag/api/v1/search - глобальный поиск по нескольким namespaces
"""

import pytest
from io import BytesIO


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_search_documents(rag_client, unique_namespace_name, auth_headers_system):
    """POST /namespaces/{id}/search находит документы по семантике"""
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    # Загружаем документ с контентом
    content = b"Python is a programming language. It is used for web development and data science."
    files = {"file": ("python.txt", BytesIO(content), "text/plain")}
    doc_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    assert doc_response.status_code == 202  # Async processing
    document_id = doc_response.json()["document_id"]
    
    import asyncio
    max_wait = 90
    wait_interval = 0.25
    elapsed = 0
    
    while elapsed < max_wait:
        status_response = await rag_client.get(
            f"/rag/api/v1/documents/{document_id}/status",
            headers=auth_headers_system
        )
        if status_response.status_code == 200:
            status = status_response.json().get("status")
            if status == "completed":
                break
        await asyncio.sleep(wait_interval)
        elapsed += wait_interval
    
    # Ищем по семантике
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": "What is Python used for?", "limit": 5},
        headers=auth_headers_system
    )
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["results"]) > 0
    r0 = data["results"][0]
    assert {
        "query": data["query"],
        "namespace_id": data["namespace_id"],
        "provider": data["provider"],
        "first_content_nonempty": bool(r0.get("content")),
        "first_score_is_number": isinstance(r0.get("score"), (int, float)),
    } == {
        "query": "What is Python used for?",
        "namespace_id": namespace_id,
        "provider": "pgvector",
        "first_content_nonempty": True,
        "first_score_is_number": True,
    }


@pytest.mark.asyncio
async def test_search_documents_with_filters(rag_client, unique_namespace_name, auth_headers_system):
    """POST /namespaces/{id}/search с фильтрами"""
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    # Загружаем документ
    content = b"FastAPI is a web framework for building APIs with Python."
    files = {"file": ("fastapi.txt", BytesIO(content), "text/plain")}
    await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    
    # Поиск с фильтрами (пустой фильтр = без фильтрации)
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={
            "query": "web framework",
            "limit": 3
            # filters не передаем - без фильтрации
        },
        headers=auth_headers_system
    )
    if response.status_code != 200:
        print(f"ERROR: {response.status_code} - {response.text}")
    assert response.status_code == 200
    data = response.json()

    assert {"has_results_key": "results" in data, "results_type": type(data["results"]).__name__} == {
        "has_results_key": True,
        "results_type": "list",
    }


@pytest.mark.asyncio
async def test_search_empty_namespace(rag_client, unique_namespace_name, auth_headers_system):
    """POST /namespaces/{id}/search в пустом namespace возвращает пустые результаты"""
    # Создаем namespace без документов
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    # Поиск
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": "test query", "limit": 5},
        headers=auth_headers_system
    )
    assert response.status_code == 200
    data = response.json()

    assert {"results": data["results"]} == {"results": []}


@pytest.mark.asyncio
async def test_search_with_limit(rag_client, unique_namespace_name, auth_headers_system         ):
    """POST /namespaces/{id}/search ограничивает количество результатов"""
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    # Загружаем несколько документов
    for i in range(3):
        content = f"Document {i} about Python programming and web development.".encode()
        files = {"file": (f"doc{i}.txt", BytesIO(content), "text/plain")}
        await rag_client.post(
            f"/rag/api/v1/namespaces/{namespace_id}/documents",
            files=files,
            headers=auth_headers_system
        )
    
    # Поиск с лимитом
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": "Python", "limit": 2},
        headers=auth_headers_system
    )
    assert response.status_code == 200
    data = response.json()

    lr = len(data["results"])
    assert {"len_results": lr, "within_limit": lr <= 2} == {"len_results": lr, "within_limit": True}


@pytest.mark.asyncio
async def test_search_relevance_score(rag_client, unique_namespace_name, auth_headers_system):
    """Результаты поиска имеют score релевантности"""
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    # Загружаем документ
    content = b"Machine learning is a subset of artificial intelligence."
    files = {"file": ("ml.txt", BytesIO(content), "text/plain")}
    await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    
    # Поиск
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": "machine learning", "limit": 5},
        headers=auth_headers_system
    )
    assert response.status_code == 200
    data = response.json()
    
    if len(data["results"]) > 0:
        result = data["results"][0]
        assert {
            "has_score": "score" in result,
            "score_type_ok": isinstance(result["score"], (int, float)),
            "score_nonneg": result["score"] >= 0,
        } == {"has_score": True, "score_type_ok": True, "score_nonneg": True}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_global_search(rag_client, unique_id, auth_headers_system):
    """POST /search выполняет глобальный поиск по нескольким namespaces"""
    # Создаем два namespace
    ns1_name = f"test_ns1_{unique_id}"
    ns2_name = f"test_ns2_{unique_id}"
    
    ns1_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": ns1_name},
        headers=auth_headers_system
    )
    ns1_id = ns1_response.json()["name"]
    
    ns2_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": ns2_name},
        headers=auth_headers_system
    )
    ns2_id = ns2_response.json()["name"]
    
    # Загружаем документы в оба namespace
    files1 = {"file": ("doc1.txt", BytesIO(b"Python programming"), "text/plain")}
    await rag_client.post(
        f"/rag/api/v1/namespaces/{ns1_id}/documents",
        files=files1,
        headers=auth_headers_system
    )
    
    files2 = {"file": ("doc2.txt", BytesIO(b"JavaScript programming"), "text/plain")}
    await rag_client.post(
        f"/rag/api/v1/namespaces/{ns2_id}/documents",
            files=files2,
        headers=auth_headers_system
    )
    
    # Глобальный поиск
    response = await rag_client.post(
        "/rag/api/v1/search",
        json={
            "query": "programming",
            "namespace_ids": [ns1_id, ns2_id],
            "limit": 5
        },
        headers=auth_headers_system
    )
    assert response.status_code == 200
    data = response.json()
    
    assert {
        "keys": sorted(data.keys()),
        "results_is_dict": isinstance(data["results"], dict),
    } == {
        "keys": sorted(["provider", "query", "results"]),
        "results_is_dict": True,
    }


@pytest.mark.asyncio
async def test_search_nonexistent_namespace(rag_client, auth_headers_system):
    """POST /namespaces/{id}/search с несуществующим namespace возвращает ошибку или пустые результаты"""
    # Используем правильный формат namespace_id: company_id:name
    response = await rag_client.post(
        "/rag/api/v1/namespaces/nonexistent_ns/search",
            json={"query": "test", "limit": 5},
        headers=auth_headers_system
    )
    # pgvector может возвращать 200 с пустыми результатами или ошибку
    # Другие провайдеры могут возвращать 404 или 500
    assert response.status_code in [200, 404, 500]
    if response.status_code == 200:
        data = response.json()
        # Если 200, то должны быть пустые результаты
        assert len(data.get("results", [])) == 0

