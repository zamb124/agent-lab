"""
Фикстуры для управления сервисами платформы в тестах.

Каждый сервис:
- Запускается как реальный HTTP сервер на своем порту
- Использует тестовую конфигурацию (БД, Redis, и т.д.)
- Запускается один раз на всю сессию тестов
- Переиспользуется между параллельными pytest worker'ами
- Автоматически останавливается после завершения тестов

Доступные сервисы:
- agents_service: Agents сервис (порт 8000)
- rag_service: RAG сервис (порт 8004)
- crm_service: CRM сервис (порт 8003)
- frontend_service: Frontend сервис (порт 8001)
"""

import pytest
from tests.fixtures.workers import SessionServerManager


# Константы для lock файлов
_AGENTS_SERVER_LOCK = "/tmp/platform_test_agents_server.lock"
_AGENTS_SERVER_PID = "/tmp/platform_test_agents_server.pid"

_RAG_SERVER_LOCK = "/tmp/platform_test_rag_server.lock"
_RAG_SERVER_PID = "/tmp/platform_test_rag_server.pid"

_CRM_SERVER_LOCK = "/tmp/platform_test_crm_server.lock"
_CRM_SERVER_PID = "/tmp/platform_test_crm_server.pid"

_FRONTEND_SERVER_LOCK = "/tmp/platform_test_frontend_server.lock"
_FRONTEND_SERVER_PID = "/tmp/platform_test_frontend_server.pid"


# Общие env переменные для всех сервисов
_COMMON_TEST_ENV = {
    "TESTING": "true",
    "DATABASE__URL": "postgresql+asyncpg://platform_user:admin@localhost:5434/platform_test",
    "DATABASE__SHARED_URL": "postgresql+asyncpg://platform_user:admin@localhost:5434/platform_test",
    "DATABASE__CRM_URL": "postgresql+asyncpg://platform_user:admin@localhost:5434/platform_test",
    "DATABASE__REDIS_URL": "redis://localhost:6380/0",
    "TASKS__BROKER_URL": "redis://localhost:6380/1",
    "AUTH__PERMISSIONS_ENABLED": "false",
    "SERVER__DEFAULT_TENANT_ID": "test_tenant",
    "SERVER__AGENTS_SERVICE_URL": "http://localhost:9001",
    "SERVER__RAG_SERVICE_URL": "http://localhost:9002",
    "SERVER__CRM_SERVICE_URL": "http://localhost:9003",
    "SERVER__FRONTEND_SERVICE_URL": "http://localhost:9004",
    "S3__DEFAULT_BUCKET": "test-bucket",
    "RAG__ENABLED": "true",
    "RAG__DEFAULT_PROVIDER": "pgvector",
    "RAG__PROVIDERS__PGVECTOR__ENABLED": "true",
    "RAG__PROVIDERS__PGVECTOR__EMBEDDING_API_KEY": "sk-test-key",
}


@pytest.fixture(scope="session")
def agents_service():
    """
    Agents сервис как реальный HTTP сервер на порту 9001.
    
    Используется для:
    - AI агенты и flows
    - Обработка задач через TaskIQ
    - WebSocket connections
    
    Зависимости:
    - PostgreSQL (порт 5434)
    - Redis (порт 6380)
    - TaskIQ worker (должен быть запущен отдельно)
    """
    manager = SessionServerManager(
        name="Agents",
        lock_file=_AGENTS_SERVER_LOCK,
        pid_file=_AGENTS_SERVER_PID,
        app_path="apps.agents.main:app",
        port=9001,
        startup_wait=3.0,
        env=_COMMON_TEST_ENV
    )
    
    with manager.start():
        yield


@pytest.fixture(scope="session")
def rag_service():
    """
    RAG сервис как реальный HTTP сервер на порту 9002.
    
    Используется для:
    - Semantic search через pgvector
    - Document processing
    - Namespace management
    
    Зависимости:
    - PostgreSQL (порт 5434) - для document_processing_status, namespaces, pgvector embeddings
    - MinIO (порт 9000) - для хранения файлов
    - RAGWorker (должен быть запущен отдельно)
    """
    manager = SessionServerManager(
        name="RAG",
        lock_file=_RAG_SERVER_LOCK,
        pid_file=_RAG_SERVER_PID,
        app_path="apps.rag.main:app",
        port=9002,
        startup_wait=3.0,
        env=_COMMON_TEST_ENV
    )
    
    with manager.start():
        yield


@pytest.fixture(scope="session")
def crm_service():
    """
    CRM сервис как реальный HTTP сервер на порту 9003.
    
    Используется для:
    - Entity management (contacts, notes, tasks)
    - Relationship management
    - Entity types и schemas
    - Attachments (через RAG service)
    
    Зависимости:
    - PostgreSQL (порт 5434) - для entity_types, relationships, relationship_types, entities через pgvector
    - RAG service (порт 9002) - для attachments
    - Agents service (порт 9001) - для AI анализа через A2A
    """
    manager = SessionServerManager(
        name="CRM",
        lock_file=_CRM_SERVER_LOCK,
        pid_file=_CRM_SERVER_PID,
        app_path="apps.crm.main:app",
        port=9003,
        startup_wait=5.0,
        log_file="/tmp/crm_server.log",
        err_file="/tmp/crm_server_err.log",
        env=_COMMON_TEST_ENV
    )
    
    with manager.start():
        yield


@pytest.fixture(scope="session")
def frontend_service():
    """
    Frontend сервис как реальный HTTP сервер на порту 9004.
    
    Используется для:
    - Web UI
    - Static файлы
    - Frontend API endpoints
    
    Зависимости:
    - Agents service (порт 9001) - для backend API
    """
    manager = SessionServerManager(
        name="Frontend",
        lock_file=_FRONTEND_SERVER_LOCK,
        pid_file=_FRONTEND_SERVER_PID,
        app_path="apps.frontend.main:app",
        port=9004,
        startup_wait=2.0,
        env=_COMMON_TEST_ENV
    )
    
    with manager.start():
        yield


@pytest.fixture(scope="session")
def all_services(agents_service, rag_service, crm_service, frontend_service):
    """
    Запускает все сервисы платформы.
    
    Используется для полных E2E тестов всей платформы.
    
    Сервисы запускаются в следующем порядке:
    1. Agents (9001) - базовый сервис
    2. RAG (9002) - зависит от PostgreSQL с pgvector
    3. CRM (9003) - зависит от RAG и Agents
    4. Frontend (9004) - зависит от Agents
    """
    return {
        "agents": "http://localhost:9001",
        "rag": "http://localhost:9002",
        "s3_endpoint": "http://localhost:9010",
        "crm": "http://localhost:9003",
        "frontend": "http://localhost:9004",
    }

