"""
Фикстуры HTTP-сервисов платформы: только readiness-проверки готового стека.

Все granian-процессы стартует `make test-up` через `scripts/test_stack.py up`
(декларативная таблица стека — в `scripts/test_stack.py`). pytest ничего не
запускает и не убивает: фикстура делает GET /health и падает с подсказкой
выполнить `make test-up`, если сервис недоступен.

Порты сервисов:
- flows 9001, rag 9002, crm 9003, frontend 9004, sync 9005, office 9008,
  search 9010, provider_litserve 9014, voice 9015, capability_gateway 9016,
  code_runner_{python,node,go,csharp} 9017-9020, worktracker 9021, secrets 9022.
"""

import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

_READINESS_RETRY_SEC = 5.0


def require_http_service(service_name: str, port: int, readiness_path: str = "/health") -> None:
    """Проверяет readiness HTTP-сервиса стека; иначе pytest.fail."""
    url = f"http://127.0.0.1:{port}{readiness_path}"
    deadline = time.monotonic() + _READINESS_RETRY_SEC
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 300:
                    return
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
        time.sleep(0.25)
    pytest.fail(
        f"Сервис {service_name} не запущен ({url}) — выполните make test-up",
        pytrace=False,
    )


@pytest.fixture(scope="session")
def flows_service(secrets_service):
    """Flows API на 9001 (граф, tools, A2A)."""
    _ = secrets_service
    require_http_service("flows", 9001)


@pytest.fixture(scope="session")
def capability_gateway_service(setup_database_before_tests, flows_service):
    """Trusted capability gateway на 9016."""
    _ = setup_database_before_tests, flows_service
    require_http_service("capability_gateway", 9016)


@pytest.fixture(scope="session")
def code_runner_python_service(capability_gateway_service):
    """Python code runner на 9017."""
    _ = capability_gateway_service
    require_http_service("code_runner_python", 9017)


@pytest.fixture(scope="session")
def code_runner_node_service(capability_gateway_service):
    """Node.js code runner на 9018."""
    _ = capability_gateway_service
    require_http_service("code_runner_node", 9018)


@pytest.fixture(scope="session")
def code_runner_go_service(capability_gateway_service):
    """Go code runner на 9019."""
    _ = capability_gateway_service
    require_http_service("code_runner_go", 9019)


@pytest.fixture(scope="session")
def code_runner_csharp_service(capability_gateway_service):
    """C# code runner на 9020."""
    _ = capability_gateway_service
    require_http_service("code_runner_csharp", 9020)


@pytest.fixture(scope="session")
def sandbox_services(
    code_runner_python_service,
    code_runner_node_service,
    code_runner_go_service,
    code_runner_csharp_service,
):
    """Sandbox-контур (capability_gateway + code-runner-*) для тестов capabilities и TaskIQ."""
    _ = (
        code_runner_python_service,
        code_runner_node_service,
        code_runner_go_service,
        code_runner_csharp_service,
    )
    return {
        "flows": "http://localhost:9001",
        "capability_gateway": "http://localhost:9016",
        "code_runner_python": "http://localhost:9017",
        "code_runner_node": "http://localhost:9018",
        "code_runner_go": "http://localhost:9019",
        "code_runner_csharp": "http://localhost:9020",
    }


@pytest.fixture(scope="session")
def provider_litserve_service():
    """provider_litserve на 9014 (embeddings/rerank, placeholder backend)."""
    require_http_service("provider_litserve", 9014)


@pytest.fixture(scope="session")
def rag_service(provider_litserve_service):
    """RAG API на 9002 (pgvector, документы, namespace)."""
    _ = provider_litserve_service
    require_http_service("rag", 9002)


@pytest.fixture(scope="session")
def voice_service():
    """Voice gateway на 9015 (CRM transcribe и межсервисные вызовы)."""
    require_http_service("voice", 9015)


@pytest.fixture(scope="session")
def crm_service(flows_service, rag_service, voice_service):
    """CRM API на 9003 (entities, graph, attachments)."""
    _ = flows_service, rag_service, voice_service
    require_http_service("crm", 9003)


@pytest.fixture(scope="session")
def frontend_service():
    """Frontend на 9004 (UI, статика, frontend API)."""
    require_http_service("frontend", 9004)


@pytest.fixture(scope="session")
def sync_service():
    """Sync на 9005 (чат, WebSocket realtime, Git)."""
    require_http_service("sync", 9005)


@pytest.fixture(scope="session")
def worktracker_http_service(setup_database_before_tests):
    """Worktracker на 9021 (WorkItem API)."""
    _ = setup_database_before_tests
    require_http_service("worktracker", 9021)


@pytest.fixture(scope="session")
def secrets_service(setup_database_before_tests):
    """Secrets/Variables на 9022 (@var: ссылки company variables)."""
    _ = setup_database_before_tests
    require_http_service("secrets", 9022)


@pytest.fixture(scope="session")
def office_service():
    """Documents/Office на 9008 (OnlyOffice BFF)."""
    require_http_service("office", 9008)


@pytest.fixture(scope="session")
def search_service():
    """Search MCP на 9010."""
    require_http_service("search", 9010)


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
    """Проверяет готовность всех сервисов платформы для полных E2E тестов."""
    _ = (
        flows_service,
        rag_service,
        crm_service,
        frontend_service,
        sync_service,
        office_service,
        search_service,
        provider_litserve_service,
    )
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
