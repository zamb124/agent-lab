"""
Тесты для AmoCRM клиента с использованием mock HTTP клиента
"""

import pytest
import httpx

from backend.app.clients.amo_crm_integration import (
    AmoCRMClient,
    get_amocrm_client,
    register_subdomain,
)
from backend.app.clients.amo_crm_integration.client import (
    _client_cache,
    _subdomain_to_token,
)

# MockServer и MockResponse автоматически доступны из conftest.py
from ..conftest import MockServer, MockResponse


def create_mock_amocrm_server() -> MockServer:
    """Создает и настраивает mock сервер с эндпоинтами AmoCRM"""
    server = MockServer()

    # ==================== LEADS ====================

    @server.get("/api/v4/leads")
    async def get_leads(url: str, params: dict, **kwargs):
        # Проверка на 204
        if params.get("query") == "empty":
            return MockResponse(204)

        return MockResponse(200, {
            "_embedded": {
                "leads": [
                    {"id": 1, "name": "Test Lead 1", "price": 10000},
                    {"id": 2, "name": "Test Lead 2", "price": 20000},
                ]
            }
        })

    @server.get("/api/v4/leads/{lead_id}")
    async def get_lead(url: str, params: dict, path_params: dict, **kwargs):
        lead_id = int(path_params["lead_id"])
        return MockResponse(200, {
            "id": lead_id,
            "name": f"Lead {lead_id}",
            "price": 15000,
            "status_id": 123,
        })

    # ==================== CONTACTS ====================

    @server.get("/api/v4/contacts")
    async def get_contacts(url: str, params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "contacts": [
                    {"id": 10, "name": "John Doe", "first_name": "John"},
                    {"id": 11, "name": "Jane Smith", "first_name": "Jane"},
                ]
            }
        })

    # ==================== TASKS ====================

    @server.get("/api/v4/tasks")
    async def get_tasks(url: str, params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "tasks": [
                    {"id": 100, "text": "Task 1", "is_completed": False},
                    {"id": 101, "text": "Task 2", "is_completed": True},
                ]
            }
        })

    # ==================== ACCOUNT ====================

    @server.get("/api/v4/account")
    async def get_account(url: str, params: dict, **kwargs):
        return MockResponse(200, {
            "id": 12345,
            "name": "Test Company",
            "subdomain": "testcompany",
            "currency": "RUB",
        })

    @server.get("/api/v4/users")
    async def get_users(url: str, params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "users": [
                    {"id": 1000, "name": "Admin User", "email": "admin@test.com"},
                    {"id": 1001, "name": "Manager User", "email": "manager@test.com"},
                ]
            }
        })

    # ==================== NOTES ====================

    @server.get("/api/v4/{entity_type}/{entity_id}/notes")
    async def get_notes(url: str, params: dict, path_params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "notes": [
                    {"id": 5000, "note_type": "common", "params": {"text": "Test note"}},
                ]
            }
        })

    @server.post("/api/v4/{entity_type}/notes")
    async def create_note(url: str, json: dict, path_params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "notes": [
                    {"id": 9999, "created_at": 1234567890},
                ]
            }
        })

    # ==================== TALKS ====================

    @server.get("/api/v4/talks")
    async def get_talks(url: str, params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "talks": [
                    {"talk_id": 2000, "origin": "telegram", "is_in_work": True},
                    {"talk_id": 2001, "origin": "whatsapp", "is_in_work": False},
                ]
            }
        })

    @server.get("/api/v4/talks/{talk_id}")
    async def get_talk(url: str, params: dict, path_params: dict, **kwargs):
        talk_id = int(path_params["talk_id"])
        return MockResponse(200, {
            "talk_id": talk_id,
            "origin": "telegram",
            "is_in_work": True,
            "messages": [],
        })

    @server.post("/api/v4/talks/{talk_id}/close")
    async def close_talk(url: str, json: dict, path_params: dict, **kwargs):
        return MockResponse(200, {"success": True})

    # ==================== LEADS CRUD ====================

    @server.post("/api/v4/leads")
    async def create_lead(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "leads": [{"id": 999, "name": json[0]["name"], "created_at": 1234567890}]
            }
        })

    @server.patch("/api/v4/leads")
    async def update_lead(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "leads": [{"id": json[0]["id"], "updated_at": 1234567890}]
            }
        })

    @server.post("/api/v4/leads/complex")
    async def create_leads_complex(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "leads": [{"id": 1000, "name": "Complex Lead"}]
            }
        })

    # ==================== CONTACTS CRUD ====================

    @server.post("/api/v4/contacts")
    async def create_contact(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "contacts": [{"id": 888, "name": json[0]["name"]}]
            }
        })

    @server.patch("/api/v4/contacts")
    async def update_contact(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "contacts": [{"id": json[0]["id"], "updated_at": 1234567890}]
            }
        })

    # ==================== COMPANIES ====================

    @server.get("/api/v4/companies")
    async def get_companies(url: str, params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "companies": [
                    {"id": 50, "name": "Company A"},
                    {"id": 51, "name": "Company B"},
                ]
            }
        })

    @server.get("/api/v4/companies/{company_id}")
    async def get_company(url: str, path_params: dict, **kwargs):
        return MockResponse(200, {
            "id": int(path_params["company_id"]),
            "name": "Test Company"
        })

    @server.post("/api/v4/companies")
    async def create_company(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "companies": [{"id": 777, "name": json[0]["name"]}]
            }
        })

    @server.patch("/api/v4/companies")
    async def update_company(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "companies": [{"id": json[0]["id"]}]
            }
        })

    # ==================== CUSTOMERS ====================

    @server.get("/api/v4/customers")
    async def get_customers(url: str, params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "customers": [{"id": 60, "name": "Customer 1"}]
            }
        })

    @server.post("/api/v4/customers")
    async def create_customer(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "customers": [{"id": 666, "name": json[0]["name"]}]
            }
        })

    @server.get("/api/v4/customers/{customer_id}/transactions")
    async def get_transactions(url: str, path_params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "transactions": [{"id": 5001, "price": 10000}]
            }
        })

    @server.get("/api/v4/customers/segments")
    async def get_segments(url: str, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "segments": [{"id": 1, "name": "VIP"}]
            }
        })

    # ==================== TASKS CRUD ====================

    @server.post("/api/v4/tasks")
    async def create_task(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "tasks": [{"id": 555, "text": json[0]["text"]}]
            }
        })

    @server.patch("/api/v4/tasks")
    async def update_task(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "tasks": [{"id": json[0]["id"]}]
            }
        })

    # ==================== CATALOGS ====================

    @server.get("/api/v4/catalogs")
    async def get_catalogs(url: str, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "catalogs": [{"id": 1, "name": "Products"}]
            }
        })

    @server.get("/api/v4/catalogs/{catalog_id}")
    async def get_catalog(url: str, path_params: dict, **kwargs):
        return MockResponse(200, {"id": int(path_params["catalog_id"]), "name": "Products"})

    @server.get("/api/v4/catalogs/{catalog_id}/elements")
    async def get_catalog_elements(url: str, path_params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "elements": [{"id": 1001, "name": "iPhone"}]
            }
        })

    @server.post("/api/v4/catalogs/{catalog_id}/elements")
    async def create_catalog_element(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "elements": [{"id": 2001, "name": json[0]["name"]}]
            }
        })

    # ==================== PIPELINES ====================

    @server.get("/api/v4/leads/pipelines")
    async def get_pipelines(url: str, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "pipelines": [{"id": 1, "name": "Sales"}]
            }
        })

    @server.get("/api/v4/leads/pipelines/{pipeline_id}")
    async def get_pipeline(url: str, path_params: dict, **kwargs):
        return MockResponse(200, {
            "id": int(path_params["pipeline_id"]),
            "name": "Sales",
            "_embedded": {
                "statuses": [{"id": 100, "name": "New"}]
            }
        })

    # ==================== CUSTOM FIELDS ====================

    @server.get("/api/v4/{entity_type}/custom_fields")
    async def get_custom_fields(url: str, path_params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "custom_fields": [{"id": 123, "name": "Phone"}]
            }
        })

    # ==================== ENTITY LINKS ====================

    @server.get("/api/v4/{entity_type}/{entity_id}/links")
    async def get_entity_links(url: str, path_params: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "links": [{"to_entity_id": 456, "to_entity_type": "contacts"}]
            }
        })

    @server.post("/api/v4/{entity_type}/{entity_id}/link")
    async def link_entities(url: str, json: dict, **kwargs):
        return MockResponse(200, {"success": True})

    # ==================== UNSORTED ====================

    @server.get("/api/v4/leads/unsorted")
    async def get_unsorted(url: str, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "unsorted": [{"uid": "abc123", "category": "forms"}]
            }
        })

    @server.post("/api/v4/leads/unsorted/{unsorted_id}/accept")
    async def accept_unsorted(url: str, path_params: dict, **kwargs):
        return MockResponse(200, {"lead_id": 9999})

    # ==================== WEBHOOKS ====================

    @server.get("/api/v4/webhooks")
    async def get_webhooks(url: str, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "webhooks": [{"id": 1, "destination": "https://example.com"}]
            }
        })

    @server.post("/api/v4/webhooks")
    async def create_webhook(url: str, json: dict, **kwargs):
        return MockResponse(200, {"id": 999, "destination": json["destination"]})

    @server.delete("/api/v4/webhooks/{webhook_id}")
    async def delete_webhook(url: str, path_params: dict, **kwargs):
        return MockResponse(200, {"success": True})

    # ==================== OTHER ====================

    @server.get("/api/v4/widgets")
    async def get_widgets(url: str, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "widgets": [{"code": "test_widget"}]
            }
        })

    @server.post("/api/v4/calls")
    async def create_call(url: str, json: dict, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "calls": [{"id": 8888}]
            }
        })

    @server.get("/api/v4/sources")
    async def get_sources(url: str, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "sources": [{"id": 1, "name": "Website"}]
            }
        })

    @server.get("/api/v4/roles")
    async def get_roles(url: str, **kwargs):
        return MockResponse(200, {
            "_embedded": {
                "roles": [{"id": 1, "name": "Admin"}]
            }
        })

    @server.post("/api/v4/short_links")
    async def create_short_link(url: str, json: dict, **kwargs):
        return MockResponse(200, {"short_url": "https://short.link/abc"})

    return server


class MockHttpClient:
    """Adapter для MockServer, совместимый с httpx.AsyncClient"""

    def __init__(self, server: MockServer):
        self.server = server

    async def get(self, url: str, params: dict = None):
        return await self.server.get_request(url, params)

    async def post(self, url: str, json: dict = None):
        return await self.server.post_request(url, json)

    async def patch(self, url: str, json: dict = None):
        return await self.server.patch_request(url, json)

    async def delete(self, url: str):
        return await self.server.delete_request(url)

    async def aclose(self):
        await self.server.aclose()


@pytest.fixture
def mock_server():
    """Fixture для mock сервера"""
    return create_mock_amocrm_server()


@pytest.fixture
def mock_http_client(mock_server):
    """Fixture для mock HTTP клиента"""
    return MockHttpClient(mock_server)


@pytest.fixture
def amocrm_client(mock_http_client):
    """Fixture для AmoCRM клиента с подмененным HTTP клиентом"""
    client = AmoCRMClient(subdomain="testcompany", access_token="test_token")
    # Подменяем HTTP клиент через dependency injection
    client._client = mock_http_client
    return client


@pytest.fixture(autouse=True)
def clear_caches():
    """Очищаем кеши перед каждым тестом"""
    _client_cache.clear()
    _subdomain_to_token.clear()
    yield
    _client_cache.clear()
    _subdomain_to_token.clear()


# ==================== ТЕСТЫ СДЕЛОК (LEADS) ====================


@pytest.mark.asyncio
async def test_get_leads(amocrm_client, mock_server):
    """Тест получения списка сделок"""
    leads = await amocrm_client.get_leads(limit=50, query="test")

    assert len(leads) == 2
    assert leads[0] == {"id": 1, "name": "Test Lead 1", "price": 10000}
    assert leads[1] == {"id": 2, "name": "Test Lead 2", "price": 20000}

    # Проверяем что запрос был сделан
    assert len(mock_server.requests) == 1
    assert mock_server.requests[0] == {
        "method": "GET",
        "url": "https://testcompany.amocrm.ru/api/v4/leads",
        "params": {"limit": 50, "query": "test", "page": 1},
        "json": None,
    }


@pytest.mark.asyncio
async def test_get_lead_by_id(amocrm_client):
    """Тест получения сделки по ID"""
    lead = await amocrm_client.get_lead(lead_id=123)

    assert lead == {
        "id": 123,
        "name": "Lead 123",
        "price": 15000,
        "status_id": 123,
    }


@pytest.mark.asyncio
async def test_get_leads_204_raises_error(amocrm_client):
    """Тест что 204 No Content выбрасывает ошибку"""
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await amocrm_client.get_leads(limit=50, query="empty")

    assert "204" in str(exc_info.value)


# ==================== ТЕСТЫ КОНТАКТОВ (CONTACTS) ====================


@pytest.mark.asyncio
async def test_get_contacts(amocrm_client, mock_server):
    """Тест получения списка контактов"""
    contacts = await amocrm_client.get_contacts(limit=50)

    assert len(contacts) == 2
    assert contacts[0] == {"id": 10, "name": "John Doe", "first_name": "John"}
    assert contacts[1] == {"id": 11, "name": "Jane Smith", "first_name": "Jane"}

    assert mock_server.requests[0] == {
        "method": "GET",
        "url": "https://testcompany.amocrm.ru/api/v4/contacts",
        "params": {"limit": 50, "page": 1},
        "json": None,
    }


# ==================== ТЕСТЫ ЗАДАЧ (TASKS) ====================


@pytest.mark.asyncio
async def test_get_tasks(amocrm_client, mock_server):
    """Тест получения списка задач"""
    tasks = await amocrm_client.get_tasks(
        limit=50, filter_entity_type="leads", filter_entity_id=123
    )

    assert len(tasks) == 2
    assert tasks[0] == {"id": 100, "text": "Task 1", "is_completed": False}
    assert tasks[1] == {"id": 101, "text": "Task 2", "is_completed": True}

    assert mock_server.requests[0] == {
        "method": "GET",
        "url": "https://testcompany.amocrm.ru/api/v4/tasks",
        "params": {
            "limit": 50,
            "filter[entity_type]": "leads",
            "filter[entity_id]": 123,
            "page": 1,
        },
        "json": None,
    }


# ==================== ТЕСТЫ АККАУНТА ====================


@pytest.mark.asyncio
async def test_get_account_info(amocrm_client):
    """Тест получения информации об аккаунте"""
    account = await amocrm_client.get_account_info()

    assert account == {
        "id": 12345,
        "name": "Test Company",
        "subdomain": "testcompany",
        "currency": "RUB",
    }


@pytest.mark.asyncio
async def test_get_users(amocrm_client):
    """Тест получения списка пользователей"""
    users = await amocrm_client.get_users(limit=50)

    assert len(users) == 2
    assert users[0] == {"id": 1000, "name": "Admin User", "email": "admin@test.com"}
    assert users[1] == {"id": 1001, "name": "Manager User", "email": "manager@test.com"}


# ==================== ТЕСТЫ ПРИМЕЧАНИЙ (NOTES) ====================


@pytest.mark.asyncio
async def test_get_notes(amocrm_client):
    """Тест получения примечаний"""
    notes = await amocrm_client.get_notes(entity_type="leads", entity_id=123, limit=50)

    assert len(notes) == 1
    assert notes[0] == {
        "id": 5000,
        "note_type": "common",
        "params": {"text": "Test note"},
    }


@pytest.mark.asyncio
async def test_create_note(amocrm_client, mock_server):
    """Тест создания примечания"""
    result = await amocrm_client.create_note(
        entity_type="leads", entity_id=123, note_type="common", text="New note"
    )

    assert result == {
        "_embedded": {
            "notes": [{"id": 9999, "created_at": 1234567890}]
        }
    }

    # Проверяем POST запрос
    assert mock_server.requests[0] == {
        "method": "POST",
        "url": "https://testcompany.amocrm.ru/api/v4/leads/notes",
        "params": None,
        "json": [
            {
                "entity_id": 123,
                "note_type": "common",
                "params": {"text": "New note"},
            }
        ],
    }


# ==================== ТЕСТЫ БЕСЕД (TALKS) ====================


@pytest.mark.asyncio
async def test_get_talks(amocrm_client):
    """Тест получения списка бесед"""
    talks = await amocrm_client.get_talks(limit=50, filter_is_in_work=True)

    assert len(talks) == 2
    assert talks[0] == {"talk_id": 2000, "origin": "telegram", "is_in_work": True}
    assert talks[1] == {"talk_id": 2001, "origin": "whatsapp", "is_in_work": False}


@pytest.mark.asyncio
async def test_get_talk_by_id(amocrm_client):
    """Тест получения беседы по ID"""
    talk = await amocrm_client.get_talk_by_id(talk_id=2000)

    assert talk == {
        "talk_id": 2000,
        "origin": "telegram",
        "is_in_work": True,
        "messages": [],
    }


@pytest.mark.asyncio
async def test_close_talk(amocrm_client, mock_server):
    """Тест закрытия беседы"""
    result = await amocrm_client.close_talk(talk_id=2000, force_close=False)

    assert result is True

    assert mock_server.requests[0] == {
        "method": "POST",
        "url": "https://testcompany.amocrm.ru/api/v4/talks/2000/close",
        "params": None,
        "json": {"force_close": False},
    }


# ==================== ТЕСТЫ МАППИНГА subdomain -> token ====================


@pytest.mark.asyncio
async def test_register_subdomain():
    """Тест регистрации маппинга subdomain -> token"""
    register_subdomain("testcompany", "secret_token")

    # Клиент должен получить токен из маппинга
    client = get_amocrm_client(subdomain="testcompany")

    assert client.subdomain == "testcompany"
    assert client.access_token == "secret_token"


@pytest.mark.asyncio
async def test_different_subdomains_different_clients():
    """Тест что разные поддомены создают разные клиенты"""
    register_subdomain("company1", "token1")
    register_subdomain("company2", "token2")

    client1 = get_amocrm_client(subdomain="company1")
    client2 = get_amocrm_client(subdomain="company2")

    assert client1 is not client2
    assert client1.subdomain == "company1"
    assert client2.subdomain == "company2"


# ==================== ТЕСТЫ CRUD ДЛЯ СДЕЛОК ====================


@pytest.mark.asyncio
async def test_create_lead(amocrm_client):
    """Тест создания сделки"""
    result = await amocrm_client.create_lead({"name": "New Lead", "price": 50000})

    assert result["_embedded"]["leads"][0]["id"] == 999
    assert result["_embedded"]["leads"][0]["name"] == "New Lead"


@pytest.mark.asyncio
async def test_update_lead(amocrm_client):
    """Тест обновления сделки"""
    result = await amocrm_client.update_lead(123, {"price": 60000})

    assert result["_embedded"]["leads"][0]["id"] == 123


@pytest.mark.asyncio
async def test_create_leads_complex(amocrm_client):
    """Тест создания сделок с привязкой"""
    result = await amocrm_client.create_leads_complex([{"name": "Complex Lead"}])

    assert result["_embedded"]["leads"][0]["id"] == 1000


# ==================== ТЕСТЫ CRUD ДЛЯ КОНТАКТОВ ====================


@pytest.mark.asyncio
async def test_create_contact(amocrm_client):
    """Тест создания контакта"""
    result = await amocrm_client.create_contact({"name": "John Doe"})

    assert result["_embedded"]["contacts"][0]["id"] == 888
    assert result["_embedded"]["contacts"][0]["name"] == "John Doe"


@pytest.mark.asyncio
async def test_update_contact(amocrm_client):
    """Тест обновления контакта"""
    result = await amocrm_client.update_contact(10, {"name": "Jane Doe"})

    assert result["_embedded"]["contacts"][0]["id"] == 10


# ==================== ТЕСТЫ КОМПАНИЙ ====================


@pytest.mark.asyncio
async def test_get_companies(amocrm_client):
    """Тест получения списка компаний"""
    companies = await amocrm_client.get_companies()

    assert len(companies) == 2
    assert companies[0]["name"] == "Company A"


@pytest.mark.asyncio
async def test_get_company(amocrm_client):
    """Тест получения компании по ID"""
    company = await amocrm_client.get_company(50)

    assert company["id"] == 50
    assert company["name"] == "Test Company"


@pytest.mark.asyncio
async def test_create_company(amocrm_client):
    """Тест создания компании"""
    result = await amocrm_client.create_company({"name": "New Company"})

    assert result["_embedded"]["companies"][0]["id"] == 777


@pytest.mark.asyncio
async def test_update_company(amocrm_client):
    """Тест обновления компании"""
    result = await amocrm_client.update_company(50, {"name": "Updated Company"})

    assert result["_embedded"]["companies"][0]["id"] == 50


# ==================== ТЕСТЫ ПОКУПАТЕЛЕЙ ====================


@pytest.mark.asyncio
async def test_get_customers(amocrm_client):
    """Тест получения списка покупателей"""
    customers = await amocrm_client.get_customers()

    assert len(customers) == 1
    assert customers[0]["name"] == "Customer 1"


@pytest.mark.asyncio
async def test_create_customer(amocrm_client):
    """Тест создания покупателя"""
    result = await amocrm_client.create_customer({"name": "New Customer"})

    assert result["_embedded"]["customers"][0]["id"] == 666


@pytest.mark.asyncio
async def test_get_customer_transactions(amocrm_client):
    """Тест получения транзакций покупателя"""
    transactions = await amocrm_client.get_customer_transactions(60)

    assert len(transactions) == 1
    assert transactions[0]["price"] == 10000


@pytest.mark.asyncio
async def test_get_customer_segments(amocrm_client):
    """Тест получения сегментов покупателей"""
    segments = await amocrm_client.get_customer_segments()

    assert len(segments) == 1
    assert segments[0]["name"] == "VIP"


# ==================== ТЕСТЫ ЗАДАЧ ====================


@pytest.mark.asyncio
async def test_create_task(amocrm_client):
    """Тест создания задачи"""
    result = await amocrm_client.create_task({"text": "Call customer", "entity_id": 123})

    assert result["_embedded"]["tasks"][0]["id"] == 555
    assert result["_embedded"]["tasks"][0]["text"] == "Call customer"


@pytest.mark.asyncio
async def test_update_task(amocrm_client):
    """Тест обновления задачи"""
    result = await amocrm_client.update_task(100, {"is_completed": True})

    assert result["_embedded"]["tasks"][0]["id"] == 100


@pytest.mark.asyncio
async def test_complete_task(amocrm_client):
    """Тест завершения задачи"""
    result = await amocrm_client.complete_task(100, "Task completed")

    assert result["_embedded"]["tasks"][0]["id"] == 100


# ==================== ТЕСТЫ КАТАЛОГОВ ====================


@pytest.mark.asyncio
async def test_get_catalogs(amocrm_client):
    """Тест получения списка каталогов"""
    catalogs = await amocrm_client.get_catalogs()

    assert len(catalogs) == 1
    assert catalogs[0]["name"] == "Products"


@pytest.mark.asyncio
async def test_get_catalog(amocrm_client):
    """Тест получения каталога по ID"""
    catalog = await amocrm_client.get_catalog(1)

    assert catalog["id"] == 1
    assert catalog["name"] == "Products"


@pytest.mark.asyncio
async def test_get_catalog_elements(amocrm_client):
    """Тест получения элементов каталога"""
    elements = await amocrm_client.get_catalog_elements(1)

    assert len(elements) == 1
    assert elements[0]["name"] == "iPhone"


@pytest.mark.asyncio
async def test_create_catalog_element(amocrm_client):
    """Тест создания элемента каталога"""
    result = await amocrm_client.create_catalog_element(1, {"name": "New Product"})

    assert result["_embedded"]["elements"][0]["id"] == 2001
    assert result["_embedded"]["elements"][0]["name"] == "New Product"


# ==================== ТЕСТЫ ВОРОНОК ====================


@pytest.mark.asyncio
async def test_get_pipelines(amocrm_client):
    """Тест получения списка воронок"""
    pipelines = await amocrm_client.get_pipelines()

    assert len(pipelines) == 1
    assert pipelines[0]["name"] == "Sales"


@pytest.mark.asyncio
async def test_get_pipeline(amocrm_client):
    """Тест получения воронки по ID"""
    pipeline = await amocrm_client.get_pipeline(1)

    assert pipeline["id"] == 1
    assert pipeline["name"] == "Sales"


@pytest.mark.asyncio
async def test_get_pipeline_statuses(amocrm_client):
    """Тест получения статусов воронки"""
    statuses = await amocrm_client.get_pipeline_statuses(1)

    assert len(statuses) == 1
    assert statuses[0]["name"] == "New"


# ==================== ТЕСТЫ КАСТОМНЫХ ПОЛЕЙ ====================


@pytest.mark.asyncio
async def test_get_custom_fields(amocrm_client):
    """Тест получения кастомных полей"""
    fields = await amocrm_client.get_custom_fields("leads")

    assert len(fields) == 1
    assert fields[0]["name"] == "Phone"


# ==================== ТЕСТЫ СВЯЗЕЙ СУЩНОСТЕЙ ====================


@pytest.mark.asyncio
async def test_get_entity_links(amocrm_client):
    """Тест получения связей сущности"""
    links = await amocrm_client.get_entity_links("leads", 123)

    assert len(links) == 1
    assert links[0]["to_entity_type"] == "contacts"


@pytest.mark.asyncio
async def test_link_entities(amocrm_client):
    """Тест привязки сущностей"""
    result = await amocrm_client.link_entities(
        "leads", 123, [{"to_entity_id": 456, "to_entity_type": "contacts"}]
    )

    assert result["success"] is True


# ==================== ТЕСТЫ НЕРАЗОБРАННОГО ====================


@pytest.mark.asyncio
async def test_get_unsorted(amocrm_client):
    """Тест получения неразобранных заявок"""
    unsorted = await amocrm_client.get_unsorted()

    assert len(unsorted) == 1
    assert unsorted[0]["category"] == "forms"


@pytest.mark.asyncio
async def test_accept_unsorted(amocrm_client):
    """Тест принятия неразобранной заявки"""
    result = await amocrm_client.accept_unsorted("abc123", user_id=1, status_id=100)

    assert result["lead_id"] == 9999


# ==================== ТЕСТЫ ВЕБХУКОВ ====================


@pytest.mark.asyncio
async def test_get_webhooks(amocrm_client):
    """Тест получения списка вебхуков"""
    webhooks = await amocrm_client.get_webhooks()

    assert len(webhooks) == 1
    assert webhooks[0]["destination"] == "https://example.com"


@pytest.mark.asyncio
async def test_create_webhook(amocrm_client):
    """Тест создания вебхука"""
    result = await amocrm_client.create_webhook("https://test.com", ["add_lead"])

    assert result["id"] == 999
    assert result["destination"] == "https://test.com"


@pytest.mark.asyncio
async def test_delete_webhook(amocrm_client):
    """Тест удаления вебхука"""
    result = await amocrm_client.delete_webhook(1)

    assert result is True


# ==================== ТЕСТЫ ПРОЧИХ МЕТОДОВ ====================


@pytest.mark.asyncio
async def test_get_widgets(amocrm_client):
    """Тест получения виджетов"""
    widgets = await amocrm_client.get_widgets()

    assert len(widgets) == 1
    assert widgets[0]["code"] == "test_widget"


@pytest.mark.asyncio
async def test_create_call(amocrm_client):
    """Тест создания звонка"""
    result = await amocrm_client.create_call({"phone": "+79991234567", "duration": 120})

    assert result["_embedded"]["calls"][0]["id"] == 8888


@pytest.mark.asyncio
async def test_get_sources(amocrm_client):
    """Тест получения источников"""
    sources = await amocrm_client.get_sources()

    assert len(sources) == 1
    assert sources[0]["name"] == "Website"


@pytest.mark.asyncio
async def test_get_roles(amocrm_client):
    """Тест получения ролей"""
    roles = await amocrm_client.get_roles()

    assert len(roles) == 1
    assert roles[0]["name"] == "Admin"


@pytest.mark.asyncio
async def test_create_short_link(amocrm_client):
    """Тест создания короткой ссылки"""
    result = await amocrm_client.create_short_link("https://example.com/long/url")

    assert result["short_url"] == "https://short.link/abc"

