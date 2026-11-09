"""
Фикстуры HTTP-сервисов платформы: только readiness-проверки готового стека.

Все granian-процессы стартует `make test-up` через `scripts/testing/stack.py up`
(декларативная таблица стека — в `scripts/testing/stack.py`). pytest ничего не
запускает и не убивает: фикстура делает GET /health и падает с подсказкой
выполнить `make test-up`, если сервис недоступен.

Порты сервисов:
- flows 9001, rag 9002, crm 9003, frontend 9004, sync 9005, office 9008,
  search 9010, provider_litserve 9014, voice 9015, capability_gateway 9016,
  code_runner_{python,node,go,csharp} 9017-9020, worktracker 9021, secrets 9022,
  wiki 9023, guest_runtime 9024, realtime 9025, stock 9026, shop 9027,
  centrifugo 19000.
"""

import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

# Session-фикстура на каждом xdist gw: стек уже up, но health может
# не ответить 5 с под stampede старта. test_stack сам ждёт до 90 с.
_READINESS_RETRY_SEC = 30.0


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
        "flows": "http://127.0.0.1:9001",
        "capability_gateway": "http://127.0.0.1:9016",
        "code_runner_python": "http://127.0.0.1:9017",
        "code_runner_node": "http://127.0.0.1:9018",
        "code_runner_go": "http://127.0.0.1:9019",
        "code_runner_csharp": "http://127.0.0.1:9020",
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
def wiki_service_http(rag_service):
    """Wiki API на 9023 (страницы, доступ, поиск).

    Зависит от RAG: страница индексируется при каждом сохранении, без
    поднятого RAG запись не проходит.
    """
    _ = rag_service
    require_http_service("wiki", 9023)


@pytest.fixture(scope="session")
def guest_runtime_service(flows_service):
    """Ферма code_agent на 9024."""
    _ = flows_service
    require_http_service("guest_runtime", 9024)


@pytest.fixture(scope="session")
def voice_service():
    """Voice gateway на 9015 (CRM transcribe и межсервисные вызовы)."""
    require_http_service("voice", 9015)


@pytest.fixture(scope="session")
def crm_service(flows_service, rag_service, voice_service, realtime_service):
    """CRM API на 9003 (entities, graph, attachments)."""
    _ = flows_service, rag_service, voice_service, realtime_service
    require_http_service("crm", 9003)


@pytest.fixture(scope="session")
def frontend_service():
    """Frontend на 9004 (UI, статика, frontend API)."""
    require_http_service("frontend", 9004)


@pytest.fixture(scope="session")
def centrifugo_service():
    """Centrifugo user WS на 19000."""
    require_http_service("centrifugo", 19000)


@pytest.fixture(scope="session")
def realtime_service(centrifugo_service):
    """Bus PlatformEvent на 9025."""
    _ = centrifugo_service
    require_http_service("realtime", 9025)


@pytest.fixture(scope="session")
def sync_service(realtime_service):
    """Sync на 9005 (чат, Git). User WS — Centrifugo."""
    _ = realtime_service
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
def scheduler_service(setup_database_before_tests):
    """Scheduler control-plane на 9006 (расписания компании)."""
    _ = setup_database_before_tests
    require_http_service("scheduler", 9006)


@pytest.fixture(scope="session")
def office_service():
    """Documents/Office на 9008 (OnlyOffice BFF)."""
    require_http_service("office", 9008)


@pytest.fixture(scope="session")
def search_service():
    """Search MCP на 9010."""
    require_http_service("search", 9010)


@pytest.fixture(scope="session")
def shop_service(setup_database_before_tests):
    """Shop на 9027 (витрины и агрегатор; slug-хосты — *.lvh.me)."""
    _ = setup_database_before_tests
    require_http_service("shop", 9027)


@pytest.fixture(scope="session")
def geo_service(setup_database_before_tests):
    """Geo на 9028 (PostGIS+pgRouting; shop дёргает его за маршрутами)."""
    _ = setup_database_before_tests
    require_http_service("geo", 9028)


@pytest.fixture(scope="session")
def stock_service(setup_database_before_tests):
    """Stock на 9026 (складской учёт: локации, товары, перемещения)."""
    _ = setup_database_before_tests
    require_http_service("stock", 9026)


@pytest.fixture(scope="session")
def nominatim_service(setup_database_before_tests):
    """Эмулятор Nominatim на 18098 — провайдер геокодинга стека."""
    _ = setup_database_before_tests
    require_http_service("nominatim", 18098)


@pytest.fixture(scope="session")
def osm_extract_service(setup_database_before_tests):
    """Эмулятор OSM-зеркала экстрактов на 18099 (HEAD+GET, Last-Modified)."""
    _ = setup_database_before_tests
    require_http_service("osm_extract", 18099)


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
        "flows": "http://127.0.0.1:9001",
        "rag": "http://127.0.0.1:9002",
        "crm": "http://127.0.0.1:9003",
        "frontend": "http://127.0.0.1:9004",
        "sync": "http://127.0.0.1:9005",
        "office": "http://127.0.0.1:9008",
        "search": "http://127.0.0.1:9010",
        "provider_litserve": "http://127.0.0.1:9014",
        "capability_gateway": "http://127.0.0.1:9016",
        "code_runner_python": "http://127.0.0.1:9017",
        "code_runner_node": "http://127.0.0.1:9018",
        "code_runner_go": "http://127.0.0.1:9019",
        "code_runner_csharp": "http://127.0.0.1:9020",
        "s3_endpoint": "http://127.0.0.1:19002",
    }
