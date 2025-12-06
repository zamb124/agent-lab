"""
Конфигурация для frontend CRM тестов.

Тесты API CRM требуют запущенный CRM сервер.
Используем crm_server_process из основного conftest.py.
"""

import pytest
import pytest_asyncio
import os
import uuid
from datetime import date


@pytest.fixture(autouse=True)
def setup_crm_service_url(crm_server_process):
    """
    Автоматически устанавливает URL CRM сервиса для всех тестов.
    
    Зависит от crm_server_process - CRM сервер будет запущен 
    перед выполнением тестов в этом модуле.
    """
    os.environ["TEST_CRM_SERVICE_URL"] = crm_server_process["url"]
    yield
    os.environ.pop("TEST_CRM_SERVICE_URL", None)


@pytest_asyncio.fixture
async def crm_api_client(frontend_client, setup_crm_service_url):
    """
    Frontend client с настроенным CRM сервисом.
    
    Использует frontend_client + гарантирует что CRM доступен.
    """
    return frontend_client


@pytest_asyncio.fixture
async def test_note(crm_note_repo, session_test_data):
    """Тестовая заметка для frontend CRM тестов"""
    from apps.crm.db.models import Note
    
    user = session_test_data["user"]
    company = session_test_data["company"]
    
    note = Note(
        note_id=f"test_note_{uuid.uuid4().hex[:8]}",
        company_id=company.company_id,
        user_id=user.user_id,
        title="Test Note for Frontend",
        content="This is test content for frontend tests",
        note_type="freeform",
        note_date=date.today(),
        visibility="public",
    )
    
    created = await crm_note_repo.create(note)
    yield created
    
    try:
        await crm_note_repo.delete(created.note_id)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_meeting_note(crm_note_repo, session_test_data):
    """Тестовая заметка meeting_minutes для frontend CRM тестов"""
    from apps.crm.db.models import Note
    
    user = session_test_data["user"]
    company = session_test_data["company"]
    
    note = Note(
        note_id=f"test_meeting_{uuid.uuid4().hex[:8]}",
        company_id=company.company_id,
        user_id=user.user_id,
        title="Test Meeting Note",
        content="Meeting with John and Jane from ACME Corp",
        note_type="meeting_minutes",
        note_date=date.today(),
        visibility="public",
    )
    
    created = await crm_note_repo.create(note)
    yield created
    
    try:
        await crm_note_repo.delete(created.note_id)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_task(crm_task_repo, session_test_data):
    """Тестовая задача для frontend CRM тестов"""
    from apps.crm.db.models import Task
    
    user = session_test_data["user"]
    company = session_test_data["company"]
    
    task = Task(
        task_id=f"test_task_{uuid.uuid4().hex[:8]}",
        company_id=company.company_id,
        user_id=user.user_id,
        title="Test Task for Frontend",
        description="Test description",
        priority="medium",
        status="pending",
        due_date=date.today(),
    )
    
    created = await crm_task_repo.create(task)
    yield created
    
    try:
        await crm_task_repo.delete(created.task_id)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_entity(crm_entity_service, session_test_data):
    """Тестовая сущность для frontend CRM тестов"""
    from apps.crm.models.entity_models import EntityCreate
    
    company = session_test_data["company"]
    
    entity_data = EntityCreate(
        name=f"Test Entity {uuid.uuid4().hex[:6]}",
        type="person",
        attributes={"email": "test@example.com"},
    )
    
    entity = await crm_entity_service.create_entity(
        entity_data, 
        company_id=company.company_id
    )
    yield entity
    
    try:
        await crm_entity_service.delete_entity(
            entity.entity_id, 
            company_id=company.company_id
        )
    except Exception:
        pass

