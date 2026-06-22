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
- office_service: Documents/Office сервис (порт 9008)
- search_service: Search MCP сервис (порт 9010)
- provider_litserve_service: локальный OpenAI-compatible provider_litserve (порт 9014)
- capability_gateway_service: capability gateway (порт 9016)
- code_runner_python_service: Python runner (порт 9017)
- code_runner_node_service: Node.js runner (порт 9018)
- code_runner_go_service: Go runner (порт 9019)
- code_runner_csharp_service: C# runner (порт 9020)
"""

import os

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

_OFFICE_SERVER_LOCK = "/tmp/platform_test_office_server.lock"
_OFFICE_SERVER_PID = "/tmp/platform_test_office_server.pid"

_SEARCH_SERVER_LOCK = "/tmp/platform_test_search_server.lock"
_SEARCH_SERVER_PID = "/tmp/platform_test_search_server.pid"

_PROVIDER_LITSERVE_SERVER_LOCK = "/tmp/platform_test_provider_litserve_server.lock"
_PROVIDER_LITSERVE_SERVER_PID = "/tmp/platform_test_provider_litserve_server.pid"

_CAPABILITY_GATEWAY_SERVER_LOCK = "/tmp/platform_test_capability_gateway_server.lock"
_CAPABILITY_GATEWAY_SERVER_PID = "/tmp/platform_test_capability_gateway_server.pid"

_CODE_RUNNER_PYTHON_SERVER_LOCK = "/tmp/platform_test_code_runner_python_server.lock"
_CODE_RUNNER_PYTHON_SERVER_PID = "/tmp/platform_test_code_runner_python_server.pid"

_CODE_RUNNER_NODE_SERVER_LOCK = "/tmp/platform_test_code_runner_node_server.lock"
_CODE_RUNNER_NODE_SERVER_PID = "/tmp/platform_test_code_runner_node_server.pid"

_CODE_RUNNER_GO_SERVER_LOCK = "/tmp/platform_test_code_runner_go_server.lock"
_CODE_RUNNER_GO_SERVER_PID = "/tmp/platform_test_code_runner_go_server.pid"

_CODE_RUNNER_CSHARP_SERVER_LOCK = "/tmp/platform_test_code_runner_csharp_server.lock"
_CODE_RUNNER_CSHARP_SERVER_PID = "/tmp/platform_test_code_runner_csharp_server.pid"


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
    "SERVER__SEARCH_SERVICE_URL": "http://localhost:9010",
    "SERVER__VOICE_SERVICE_URL": "http://localhost:9015",
    "SERVER__PROVIDER_LITSERVE_SERVICE_URL": "http://localhost:9014",
    "SERVER__CAPABILITY_GATEWAY_SERVICE_URL": "http://localhost:9016",
    "SERVER__CODE_RUNNER_PYTHON_SERVICE_URL": "http://localhost:9017",
    "SERVER__CODE_RUNNER_NODE_SERVICE_URL": "http://localhost:9018",
    "SERVER__CODE_RUNNER_GO_SERVICE_URL": "http://localhost:9019",
    "SERVER__CODE_RUNNER_CSHARP_SERVICE_URL": "http://localhost:9020",
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
    "RAG__EMBEDDING__PROVIDER": "provider_litserve",
    "RAG__EMBEDDING__API__MODEL": "qwen/qwen3-embedding-0.6b",
    "RAG__EMBEDDING__API__DIMENSION": "1024",
    "RAG__EMBEDDING__API__MRL_OUTPUT_DIMENSION": "1024",
    "PROVIDER_LITSERVE__API__BASE_URL": "http://localhost:9014/v1",
    "LLM__OPENROUTER__API_KEY": "sk-test-key",
}


def _with_mock_llm_lane(base_env: dict[str, str], lane: str) -> dict[str, str]:
    return {**base_env, "MOCK_LLM_REDIS_KEY": f"mock_llm:responses:{lane}"}


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
        startup_wait=120.0,
        env=_with_mock_llm_lane(_COMMON_TEST_ENV, "flows"),
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def capability_gateway_service(setup_database_before_tests, flows_service):
    """Trusted capability gateway как реальный HTTP-сервер на порту 9016."""
    _ = setup_database_before_tests, flows_service
    manager = SessionServerManager(
        name="CapabilityGateway",
        lock_file=_CAPABILITY_GATEWAY_SERVER_LOCK,
        pid_file=_CAPABILITY_GATEWAY_SERVER_PID,
        app_path="apps.capability_gateway.main:app",
        port=9016,
        startup_wait=60.0,
        env=_COMMON_TEST_ENV,
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def code_runner_python_service(capability_gateway_service):
    """Python code runner как реальный HTTP сервер на порту 9017."""
    manager = SessionServerManager(
        name="CodeRunnerPython",
        lock_file=_CODE_RUNNER_PYTHON_SERVER_LOCK,
        pid_file=_CODE_RUNNER_PYTHON_SERVER_PID,
        app_path="apps.code_runner_python.main:app",
        port=9017,
        startup_wait=12.0,
        env=_COMMON_TEST_ENV,
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def code_runner_node_service(capability_gateway_service):
    """Node.js code runner как реальный HTTP сервер на порту 9018."""
    manager = SessionServerManager(
        name="CodeRunnerNode",
        lock_file=_CODE_RUNNER_NODE_SERVER_LOCK,
        pid_file=_CODE_RUNNER_NODE_SERVER_PID,
        app_path="apps.code_runner_node.main:app",
        port=9018,
        startup_wait=12.0,
        env=_COMMON_TEST_ENV,
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def code_runner_go_service(capability_gateway_service):
    """Go code runner как реальный HTTP сервер на порту 9019."""
    manager = SessionServerManager(
        name="CodeRunnerGo",
        lock_file=_CODE_RUNNER_GO_SERVER_LOCK,
        pid_file=_CODE_RUNNER_GO_SERVER_PID,
        app_path="apps.code_runner_go.main:app",
        port=9019,
        startup_wait=12.0,
        env=_COMMON_TEST_ENV,
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def code_runner_csharp_service(capability_gateway_service):
    """C# code runner как реальный HTTP сервер на порту 9020."""
    manager = SessionServerManager(
        name="CodeRunnerCsharp",
        lock_file=_CODE_RUNNER_CSHARP_SERVER_LOCK,
        pid_file=_CODE_RUNNER_CSHARP_SERVER_PID,
        app_path="apps.code_runner_csharp.main:app",
        port=9020,
        startup_wait=20.0,
        env=_COMMON_TEST_ENV,
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def sandbox_services(
    code_runner_python_service,
    code_runner_node_service,
    code_runner_go_service,
    code_runner_csharp_service,
):
    """Поднимает sandbox-контур (capability_gateway + code-runner-*) для тестов capabilities и TaskIQ.

    Не autouse: при -n 5 каждый лишний worker держал бы ref_count на тяжёлых сервисах
    и конкурировал за filelock при session startup. Явная зависимость — в тестах
    capabilities/ и через taskiq_worker для real_taskiq с code nodes.
    """
    return {
        "flows": "http://localhost:9001",
        "capability_gateway": "http://localhost:9016",
        "code_runner_python": "http://localhost:9017",
        "code_runner_node": "http://localhost:9018",
        "code_runner_go": "http://localhost:9019",
        "code_runner_csharp": "http://localhost:9020",
    }


@pytest.fixture(scope="session")
def rag_service(provider_litserve_service):
    """
    RAG сервис как реальный HTTP сервер на порту 9002.

    Используется для:
    - Семантический поиск через pgvector
    - Обработка документов
    - Управление namespace

    Зависимости:
    - PostgreSQL (порт 54322) — для document_processing_status, namespaces, pgvector embeddings
    - MinIO (порт 19002) — для хранения файлов
    - provider_litserve (порт 9014) — для embeddings/rerank HTTP
    - RAGWorker (должен быть запущен отдельно)
    """
    _ = provider_litserve_service
    manager = SessionServerManager(
        name="RAG",
        lock_file=_RAG_SERVER_LOCK,
        pid_file=_RAG_SERVER_PID,
        app_path="apps.rag.main:app",
        port=9002,
        startup_wait=18.0,
        env=_with_mock_llm_lane(_COMMON_TEST_ENV, "rag"),
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def provider_litserve_service():
    """provider_litserve как реальный HTTP-сервис на порту 9014."""
    manager = SessionServerManager(
        name="ProviderLitserve",
        lock_file=_PROVIDER_LITSERVE_SERVER_LOCK,
        pid_file=_PROVIDER_LITSERVE_SERVER_PID,
        app_path="apps.provider_litserve.main:app",
        port=9014,
        startup_wait=180.0,
        log_file="/tmp/provider_litserve_server_test.log",
        err_file="/tmp/provider_litserve_server_test_err.log",
        env={
            **_COMMON_TEST_ENV,
            "PROVIDER_LITSERVE__API__BASE_URL": "http://localhost:9014/v1",
            "PROVIDER_LITSERVE__INFRA__BACKEND": "placeholder",
            "PROVIDER_LITSERVE__INFRA__ACCELERATOR": "cpu",
            "PROVIDER_LITSERVE__INFRA__EMBEDDING_ACCELERATOR": "cpu",
            "PROVIDER_LITSERVE__INFRA__RERANK_ACCELERATOR": "cpu",
            "PROVIDER_LITSERVE__INFRA__GATEWAY_PORT": "9014",
            "PROVIDER_LITSERVE__INFRA__SQLITE_PATH": "/tmp/platform_test_provider_litserve_registry.db",
        },
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
        # Voice стартует за ~1s изолированно, но под -n auto CPU насыщен и 12s readiness
        # не успевал: выравниваем с DB-сервисами (frontend 20, office 25, sync 45).
        startup_wait=30.0,
        env=_COMMON_TEST_ENV,
    )
    with manager.start():
        yield


@pytest.fixture(scope="session")
def crm_service(flows_service, rag_service, voice_service):
    """
    CRM сервис как реальный HTTP сервер на порту 9003.

    Используется для:
    - Управление сущностями (контакты, заметки, задачи)
    - Управление связями
    - Типы сущностей и схемы
    - Вложения (через RAG-сервис)

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
        env=_with_mock_llm_lane(_COMMON_TEST_ENV, "crm"),
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def frontend_service():
    """
    Frontend сервис как реальный HTTP сервер на порту 9004.

    Используется для:
    - Веб-интерфейс
    - Статические файлы
    - API-эндпоинты frontend

    Зависимости:
    - Agents-сервис (порт 9001) — для backend API
    """
    manager = SessionServerManager(
        name="Frontend",
        lock_file=_FRONTEND_SERVER_LOCK,
        pid_file=_FRONTEND_SERVER_PID,
        app_path="apps.frontend.main:app",
        port=9004,
        startup_wait=20.0,
        env=_with_mock_llm_lane(_COMMON_TEST_ENV, "flows"),
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
        startup_wait=45.0,
        env=_with_mock_llm_lane(_COMMON_TEST_ENV, "sync"),
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def office_service():
    """
    Documents/Office сервис как реальный HTTP сервер на порту 9008.

    Используется для:
    - Documents BFF
    - Привязки flow files к OnlyOffice editor
    - Byte-level mutations, которые пишут обратно в тот же FileRecord/S3 object
    """
    manager = SessionServerManager(
        name="Office",
        lock_file=_OFFICE_SERVER_LOCK,
        pid_file=_OFFICE_SERVER_PID,
        app_path="apps.office.main:app",
        port=9008,
        startup_wait=25.0,
        env=_COMMON_TEST_ENV,
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def search_service():
    """
    Search MCP сервис как реальный HTTP сервер на порту 9010.

    В интеграционных тестах Search MCP поднимается реальным HTTP-сервисом.
    TinyFish/Linkup/Serper отключены конфигом, Tavily оставлен включенным,
    чтобы public_search flow прошел через настоящий MCP и настоящий provider.
    """
    manager = SessionServerManager(
        name="Search",
        lock_file=_SEARCH_SERVER_LOCK,
        pid_file=_SEARCH_SERVER_PID,
        app_path="apps.search.main:app",
        port=9010,
        startup_wait=12.0,
        env={
            **_COMMON_TEST_ENV,
            "DATABASE__SEARCH_URL": TEST_DATABASE_ENV["DATABASE__SEARCH_URL"],
            "SEARCH__TINYFISH__API_KEY": "",
            "SEARCH__TINYFISH__ENABLED": "false",
            "SEARCH__LINKUP__API_KEY": "",
            "SEARCH__LINKUP__ENABLED": "false",
            "SEARCH__SERPER__API_KEY": "",
            "SEARCH__SERPER__ENABLED": "false",
            "SEARCH__PROVIDER_STATE_KEY_PREFIX": f"test:search:providers:{os.getpid()}",
            "SEARCH__UNAVAILABLE_TTL_SECONDS": "30",
        },
    )

    with manager.start():
        yield


@pytest.fixture(scope="session")
def all_services(
    flows_service,
    rag_service,
    crm_service,
    frontend_service,
    sync_service,
    office_service,
    search_service,
    provider_litserve_service,
):
    """
    Запускает все сервисы платформы.

    Используется для полных E2E тестов всей платформы.

    Сервисы запускаются в следующем порядке:
    1. Agents (9001) - базовый сервис
    2. RAG (9002) - зависит от PostgreSQL с pgvector
    3. CRM (9003) - зависит от RAG и Agents
    4. Frontend (9004) - зависит от Agents
    5. Sync (9005) - зависит от PostgreSQL и Redis
    6. Office (9008) - зависит от PostgreSQL, Redis, MinIO и OnlyOffice Document Server
    7. Search (9010) — основной MCP-поиск
    8. ProviderLitserve (9014) — локальные embedding/rerank/speech модели
    """
    _ = provider_litserve_service
    return {
        "flows": "http://localhost:9001",
        "rag": "http://localhost:9002",
        "crm": "http://localhost:9003",
        "frontend": "http://localhost:9004",
        "sync": "http://localhost:9005",
        "office": "http://localhost:9008",
        "search": "http://localhost:9010",
        "provider_litserve": "http://localhost:9014",
        "capability_gateway": "http://localhost:9016",
        "code_runner_python": "http://localhost:9017",
        "code_runner_node": "http://localhost:9018",
        "code_runner_go": "http://localhost:9019",
        "code_runner_csharp": "http://localhost:9020",
        "s3_endpoint": "http://localhost:19002",
    }
