"""
Фикстуры для управления сервисами платформы в тестах.

Каждый сервис:
- Запускается как реальный HTTP сервер на своем порту
- Использует тестовую конфигурацию (БД, Redis, и т.д.)
- Запускается один раз на всю сессию тестов
- Переиспользуется между параллельными pytest worker'ами
- Автоматически останавливается после завершения тестов

Доступные сервисы:
- flows_service: flows-сервис (порт 9001)
- rag_service: RAG сервис (порт 9002)
- crm_service: CRM сервис (порт 9003)
- frontend_service: Frontend сервис (порт 9004)
- sync_service: Sync сервис (порт 9005)
"""

import pytest
from tests.fixtures.test_database_env import TEST_DATABASE_ENV
from tests.fixtures.workers import SessionServerManager


# Константы для lock файлов
_FLOWS_SERVER_LOCK = "/tmp/platform_test_flows_server.lock"
_FLOWS_SERVER_PID = "/tmp/platform_test_flows_server.pid"

_RAG_SERVER_LOCK = "/tmp/platform_test_rag_server.lock"
_RAG_SERVER_PID = "/tmp/platform_test_rag_server.pid"

_CRM_SERVER_LOCK = "/tmp/platform_test_crm_server.lock"
_CRM_SERVER_PID = "/tmp/platform_test_crm_server.pid"

_FRONTEND_SERVER_LOCK = "/tmp/platform_test_frontend_server.lock"
_FRONTEND_SERVER_PID = "/tmp/platform_test_frontend_server.pid"

_SYNC_SERVER_LOCK = "/tmp/platform_test_sync_server.lock"
_SYNC_SERVER_PID = "/tmp/platform_test_sync_server.pid"


# Общие env переменные для всех сервисов (те же БД, что в conftest и миграциях)
_COMMON_TEST_ENV = {
    **TEST_DATABASE_ENV,
    "TESTING": "true",
    "DATABASE__REDIS_URL": "redis://localhost:63792/0",
    "TASKS__BROKER_URL": "redis://localhost:63792/1",
    "AUTH__PERMISSIONS_ENABLED": "false",
    "SERVER__DEFAULT_TENANT_ID": "test_tenant",
    "SERVER__FLOWS_SERVICE_URL": "http://localhost:9001",
    "SERVER__RAG_SERVICE_URL": "http://localhost:9002",
    "SERVER__CRM_SERVICE_URL": "http://localhost:9003",
    "SERVER__FRONTEND_SERVICE_URL": "http://localhost:9004",
    "SERVER__SYNC_SERVICE_URL": "http://localhost:9005",
    "SERVER__VOICE_SERVICE_URL": "http://localhost:9015",
    "VOICE__STT__PROVIDER": "mock",
    "VOICE__STT__MOCK_TRANSCRIPT_TEXT": "Тестовая транскрипция sync worker",
    "CALLS__LIVEKIT_URL": "ws://localhost:7890",
    "CALLS__LIVEKIT_PUBLIC_URL": "http://localhost:7890",
    "CALLS__LIVEKIT_API_KEY": "devkey",
    "CALLS__LIVEKIT_API_SECRET": "secret",
    "S3__ENABLED": "true",
    "S3__DEFAULT_BUCKET": "test-bucket",
    "S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL": "http://localhost:19002",
    "S3__BUCKETS__TEST-BUCKET__ACCESS_KEY_ID": "minioadmin",
    "S3__BUCKETS__TEST-BUCKET__SECRET_ACCESS_KEY": "minioadmin",
    "S3__BUCKETS__TEST-BUCKET__REGION_NAME": "us-east-1",
    "S3__BUCKETS__TEST-BUCKET__PROVIDER": "minio",
    "PUSH__ENABLED": "true",
    "PUSH__VAPID_PUBLIC_KEY": "BP1OB4uP0WSgQqumAOefg1PdsN9S7qA1-UK26qjSPa11ylB1HgbcrVi6peEUkhkdfrADeTa_dwypXYiucfbu3JQ",
    "PUSH__VAPID_PRIVATE_KEY": "lwzkecdrLZYcyUVhYUQuAnXYk92xup132qCCk5BtUEs",
    "PUSH__VAPID_EMAIL": "test@humanitec.ru",
    "RAG__ENABLED": "true",
    "RAG__DEFAULT_PROVIDER": "pgvector",
    "RAG__PROVIDERS__PGVECTOR__ENABLED": "true",
    "LLM__OPENROUTER__API_KEY": "sk-test-key",
}


@pytest.fixture(scope="session")
def flows_service():
    """
    Сервис flows как реальный HTTP на порту 9001.
    
    Используется для:
    - flows и графы
    - Обработка задач через TaskIQ
    - WebSocket connections
    
    Зависимости:
    - PostgreSQL (порт 54322)
    - Redis (порт 63792)
    - TaskIQ worker (должен быть запущен отдельно)
    """
    manager = SessionServerManager(
        name="Flows",
        lock_file=_FLOWS_SERVER_LOCK,
        pid_file=_FLOWS_SERVER_PID,
        app_path="apps.flows.main:app",
        port=9001,
        startup_wait=20.0,
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
    - PostgreSQL (порт 54322) - для document_processing_status, namespaces, pgvector embeddings
    - MinIO (порт 19002) - для хранения файлов
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


_VOICE_SERVER_LOCK = "/tmp/platform_test_voice_server.lock"
_VOICE_SERVER_PID = "/tmp/platform_test_voice_server.pid"


@pytest.fixture(scope="session")
def voice_service():
    """Voice gateway на 9015 для CRM transcribe и межсервисных вызовов."""
    manager = SessionServerManager(
        name="Voice",
        lock_file=_VOICE_SERVER_LOCK,
        pid_file=_VOICE_SERVER_PID,
        app_path="apps.voice.main:app",
        port=9015,
        startup_wait=12.0,
        env=_COMMON_TEST_ENV,
    )
    with manager.start():
        yield


@pytest.fixture(scope="session")
def crm_service(flows_service, rag_service, voice_service):
    """
    CRM сервис как реальный HTTP сервер на порту 9003.
    
    Используется для:
    - Entity management (contacts, notes, tasks)
    - Relationship management
    - Entity types и schemas
    - Attachments (через RAG service)
    
    Зависимости:
    - PostgreSQL (порт 54322) - для entity_types, relationships, relationship_types, entities через pgvector
    - RAG service (порт 9002) - для attachments
    - Voice gateway (порт 9015) — транскрипция и межсервисные вызовы
    """
    manager = SessionServerManager(
        name="CRM",
        lock_file=_CRM_SERVER_LOCK,
        pid_file=_CRM_SERVER_PID,
        app_path="apps.crm.main:app",
        port=9003,
        startup_wait=12.0,
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
        startup_wait=20.0,
        env=_COMMON_TEST_ENV
    )
    
    with manager.start():
        yield


@pytest.fixture(scope="session")
def sync_service():
    """
    Sync сервис как реальный HTTP сервер на порту 9005.

    Используется для:
    - Инженерный чат (spaces, channels, threads, messages)
    - WebSocket realtime
    - Git-интеграция

    Зависимости:
    - PostgreSQL (порт 54322)
    - Redis (порт 63792)
    - Sync Worker (должен быть запущен отдельно)
    """
    manager = SessionServerManager(
        name="Sync",
        lock_file=_SYNC_SERVER_LOCK,
        pid_file=_SYNC_SERVER_PID,
        app_path="apps.sync.main:app",
        port=9005,
        startup_wait=10.0,
        env=_COMMON_TEST_ENV,
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def all_services(flows_service, rag_service, crm_service, frontend_service, sync_service):
    """
    Запускает все сервисы платформы.
    
    Используется для полных E2E тестов всей платформы.
    
    Сервисы запускаются в следующем порядке:
    1. Agents (9001) - базовый сервис
    2. RAG (9002) - зависит от PostgreSQL с pgvector
    3. CRM (9003) - зависит от RAG и Agents
    4. Frontend (9004) - зависит от Agents
    5. Sync (9005) - зависит от PostgreSQL и Redis
    """
    return {
        "flows": "http://localhost:9001",
        "rag": "http://localhost:9002",
        "crm": "http://localhost:9003",
        "frontend": "http://localhost:9004",
        "sync": "http://localhost:9005",
        "s3_endpoint": "http://localhost:19002",
    }

