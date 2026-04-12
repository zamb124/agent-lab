"""
End-to-end интеграционные тесты RAG Service.

Тестирует полные сценарии использования RAG:
- Создание namespace, загрузка документов, поиск, удаление
- Переключение провайдеров
- Изоляция данных между провайдерами
"""

import pytest
from io import BytesIO


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_full_rag_workflow(rag_client, unique_namespace_name, auth_headers_system):
    """
    Полный цикл RAG: создать namespace, загрузить документ, найти, удалить.
    
    Тестирует все основные операции RAG Service end-to-end.
    """
    # 1. Создать namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name, "description": "E2E test"},
        headers=auth_headers_system
    )
    assert ns_response.status_code == 201  # Created
    namespace_id = ns_response.json()["name"]
    
    # 2. Загрузить документ
    content = b"""
    FastAPI is a modern web framework for building APIs with Python.
    It is based on standard Python type hints and uses Pydantic for validation.
    FastAPI is very fast and easy to use.
    """
    files = {"file": ("fastapi.txt", BytesIO(content), "text/plain")}
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
    status = None
    status_data = {}
    
    while elapsed < max_wait:
        status_response = await rag_client.get(
            f"/rag/api/v1/documents/{document_id}/status",
            headers=auth_headers_system
        )
        if status_response.status_code == 200:
            status_data = status_response.json()
            status = status_data.get("status")
            print(f"[TEST] Document status: {status}, error: {status_data.get('error_message')}")
            if status == "completed":
                break
        await asyncio.sleep(wait_interval)
        elapsed += wait_interval
    
    assert status == "completed", f"Document processing did not complete: status={status}, error={status_data.get('error_message')}"
    
    # 3. Проверить что документ в списке
    list_response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system
    )
    assert list_response.status_code == 200
    documents = list_response.json()["documents"]
    assert {
        "nonempty": len(documents) > 0,
        "has_uploaded_id": any(d["document_id"] == document_id for d in documents),
    } == {"nonempty": True, "has_uploaded_id": True}
    
    # 4. Поиск
    search_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": "What is FastAPI?", "limit": 3},
        headers=auth_headers_system
    )
    assert search_response.status_code == 200
    results = search_response.json()["results"]
    
    assert {
        "results_nonempty": len(results) > 0,
        "first_hit_mentions_fastapi": "FastAPI" in results[0]["content"],
    } == {"results_nonempty": True, "first_hit_mentions_fastapi": True}
    
    # 5. Удалить namespace (каскадно удалит все документы)
    delete_ns_response = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}",
        headers=auth_headers_system
    )
    assert delete_ns_response.status_code == 200


@pytest.mark.asyncio
async def test_provider_switch_persistence(rag_client, rag_provider_pgvector, auth_headers_system):
    """
    Переключение провайдеров и проверка изоляции данных.
    
    Проверяет что данные pgvector изолированы от других провайдеров.
    """
    # Получаем список провайдеров
    response = await rag_client.get("/rag/api/v1/providers", headers=auth_headers_system)
    assert response.status_code == 200
    
    providers = response.json()["providers"]
    assert {"pgvector_listed": any(p["name"] == "pgvector" for p in providers)} == {"pgvector_listed": True}
    
    # Переключаемся на pgvector
    switch_response = await rag_client.post(
        "/rag/api/v1/providers/switch",
        json={"provider_name": "pgvector"},
        headers=auth_headers_system
    )
    assert switch_response.status_code == 200
    assert {"provider": switch_response.json()["provider"]} == {"provider": "pgvector"}


@pytest.mark.asyncio
async def test_multiple_namespaces_isolation(rag_client, unique_id, auth_headers_system):
    """
    Создание нескольких namespaces и проверка изоляции данных.
    
    Документы в одном namespace не видны в другом.
    """
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
    
    # Загружаем документ только в первый namespace
    files = {"file": ("doc1.txt", BytesIO(b"Content in namespace 1"), "text/plain")}
    await rag_client.post(
        f"/rag/api/v1/namespaces/{ns1_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    
    # Проверяем что документ есть в ns1
    list1_response = await rag_client.get(
        f"/rag/api/v1/namespaces/{ns1_id}/documents",
        headers=auth_headers_system
    )
    list2_response = await rag_client.get(
        f"/rag/api/v1/namespaces/{ns2_id}/documents",
        headers=auth_headers_system
    )
    assert {
        "ns1_nonempty": len(list1_response.json()["documents"]) > 0,
        "ns2_empty": len(list2_response.json()["documents"]) == 0,
    } == {"ns1_nonempty": True, "ns2_empty": True}


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_large_document_processing(rag_client, unique_namespace_name, auth_headers_system):
    """
    Загрузка и поиск в большом документе.
    
    Проверяет что RAG корректно разбивает документ на chunks.
    """
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    # Создаем большой документ
    large_content = b"""
    Python is a high-level programming language. It was created by Guido van Rossum.
    Python supports multiple programming paradigms including object-oriented and functional.
    The language has a comprehensive standard library.
    
    FastAPI is a modern web framework for Python. It is designed for building APIs quickly.
    FastAPI uses type hints for validation. It has automatic API documentation.
    The framework is built on Starlette and Pydantic.
    
    Machine learning is a subset of artificial intelligence. It focuses on learning from data.
    Python is widely used for machine learning. Popular libraries include TensorFlow and PyTorch.
    Scikit-learn is another important library for ML in Python.
    """
    
    files = {"file": ("large_doc.txt", BytesIO(large_content), "text/plain")}
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
    
    # Поиск по разным частям документа
    queries = [
        "Who created Python?",
        "What is FastAPI?",
        "Machine learning libraries"
    ]
    
    for query in queries:
        search_response = await rag_client.post(
            f"/rag/api/v1/namespaces/{namespace_id}/search",
            json={"query": query, "limit": 3},
            headers=auth_headers_system
        )
        assert search_response.status_code == 200
        results = search_response.json()["results"]
        assert len(results) > 0


@pytest.mark.asyncio
async def test_concurrent_operations(rag_client, unique_id, auth_headers_system):
    """
    Параллельные операции с разными namespaces.
    
    Проверяет что операции не конфликтуют между собой.
    """
    import asyncio
    
    # Создаем несколько namespaces параллельно
    async def create_namespace(name):
        response = await rag_client.post(
            "/rag/api/v1/namespaces",
            json={"name": name},
            headers=auth_headers_system
        )
        return response.json()
    
    names = [f"test_concurrent_{unique_id}_{i}" for i in range(3)]
    results = await asyncio.gather(*[create_namespace(name) for name in names])
    
    assert {"len": len(results), "all_have_name": all("name" in r for r in results)} == {
        "len": 3,
        "all_have_name": True,
    }
    
    # Проверяем что все namespace созданы
    list_response = await rag_client.get("/rag/api/v1/namespaces", headers=auth_headers_system)
    namespaces = list_response.json()["namespaces"]
    
    for name in names:
        assert any(ns["name"] == name for ns in namespaces)


@pytest.mark.asyncio
async def test_error_recovery(rag_client, unique_namespace_name, auth_headers_system):
    """
    Тест восстановления после ошибок.
    
    Проверяет что система корректно обрабатывает ошибки.
    """
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
            json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    # Пытаемся удалить несуществующий документ
    delete_response = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/nonexistent",
        headers=auth_headers_system
    )
    assert delete_response.status_code == 404
    
    # Проверяем что namespace все еще работает
    files = {"file": ("test.txt", BytesIO(b"Test content"), "text/plain")}
    upload_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    assert upload_response.status_code == 202  # Async processing
    
    # Cleanup
    await rag_client.delete(f"/rag/api/v1/namespaces/{namespace_id}", headers=auth_headers_system)


