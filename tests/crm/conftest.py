"""
Фикстуры для CRM тестов.

ВАЖНО: CRM тесты используют общие фикстуры из tests/conftest.py:
- test_context - контекст с test_user и test_company
- test_user - тестовый пользователь
- test_company - тестовая компания
- migrated_db - инициализированная БД
- unique_id - генератор уникальных ID

CRM-специфичные фикстуры здесь:
- crm_db - CRM Database для SQLAlchemy моделей
- crm_container - CRM контейнер зависимостей
- репозитории и сервисы
"""

import pytest
import pytest_asyncio
import uuid
from datetime import date, datetime, timezone

from apps.crm.container import CRMContainer, set_crm_container, reset_crm_container
from apps.crm.db.base import CRMDatabase
from apps.crm.db.models import EntityType, Relationship, Note, Task, CompanyMapping


# === CRM Database & Container ===

@pytest_asyncio.fixture(scope="session")
async def crm_db(migrated_db):
    """
    CRM Database для тестов.
    
    Создает таблицы CRM в отдельной БД crm_db.
    Использует session scope чтобы не пересоздавать каждый тест.
    """
    from core.config import get_settings
    settings = get_settings()
    
    crm_db_url = settings.database.crm_url or settings.database.url
    
    db = CRMDatabase(crm_db_url)
    await db.create_tables()
    
    yield db
    
    CRMDatabase.reset()


@pytest_asyncio.fixture(scope="session")
async def crm_container(crm_db, migrated_db):
    """
    CRM Container для тестов.
    
    Session scope - переиспользуется между тестами.
    """
    from core.config import get_settings
    settings = get_settings()
    
    crm_db_url = settings.database.crm_url or settings.database.url
    
    container = CRMContainer(
        db_url=crm_db_url,
        shared_db_url=settings.database.shared_url
    )
    set_crm_container(container)
    
    yield container
    
    reset_crm_container()


# === Алиасы для использования общих фикстур ===
# CRM тесты могут использовать test_context напрямую,
# но для явности создаём алиас crm_context

@pytest_asyncio.fixture
async def crm_context(test_context):
    """
    Алиас для test_context из общих фикстур.
    
    Используй test_context напрямую в новых тестах.
    """
    return test_context


# === Репозитории ===

@pytest_asyncio.fixture
async def entity_type_repo(crm_container: CRMContainer):
    """EntityTypeRepository"""
    return crm_container.entity_type_repository


@pytest_asyncio.fixture
async def relationship_repo(crm_container: CRMContainer):
    """RelationshipRepository"""
    return crm_container.relationship_repository


@pytest_asyncio.fixture
async def note_repo(crm_container: CRMContainer):
    """NoteRepository"""
    return crm_container.note_repository


@pytest_asyncio.fixture
async def task_repo(crm_container: CRMContainer):
    """TaskRepository"""
    return crm_container.task_repository


@pytest_asyncio.fixture
async def company_mapping_repo(crm_container: CRMContainer):
    """CompanyMappingRepository"""
    return crm_container.company_mapping_repository


# === Сервисы ===

@pytest_asyncio.fixture
async def entity_type_service(crm_container: CRMContainer):
    """EntityTypeService"""
    return crm_container.entity_type_service


@pytest_asyncio.fixture
async def note_service(crm_container: CRMContainer):
    """NoteService"""
    return crm_container.note_service


@pytest_asyncio.fixture
async def task_service(crm_container: CRMContainer):
    """TaskService"""
    return crm_container.task_service


@pytest_asyncio.fixture
async def relationship_service(crm_container: CRMContainer):
    """RelationshipService"""
    return crm_container.relationship_service


@pytest_asyncio.fixture
async def crm_graph_service(crm_container: CRMContainer):
    """GraphService (renamed to avoid conflict)"""
    return crm_container.graph_service


# === Генераторы ID ===

@pytest_asyncio.fixture
def unique_crm_id():
    """Генератор уникальных ID для CRM тестов"""
    def _generate(prefix: str = "crm") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
    return _generate


# === Sample объекты для тестов ===

@pytest_asyncio.fixture
async def sample_entity_type(test_context, entity_type_repo, unique_crm_id) -> EntityType:
    """Создает тестовый тип сущности"""
    type_id = unique_crm_id("type")
    entity_type = EntityType(
        type_id=type_id,
        company_id=test_context.active_company.company_id,
        name="Test Entity Type",
        description="Test description",
        prompt="Test extraction prompt",
        required_attributes=["name"],
        optional_attributes=["email", "phone"],
        icon="ti-test",
        color="#FF0000",
        is_system=False,
        check_duplicates=True,
        is_filtered=False,
    )
    
    await entity_type_repo.create(entity_type)
    yield entity_type
    
    await entity_type_repo.delete(type_id)


@pytest_asyncio.fixture
async def sample_note(test_context, note_repo, unique_crm_id) -> Note:
    """Создает тестовую заметку"""
    note_id = unique_crm_id("note")
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Test Note",
        content="This is a test note content",
        note_type="freeform",
        note_date=date.today(),
        ai_summary=None,
        linked_entity_ids=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await note_repo.create(note)
    yield note
    
    await note_repo.delete(note_id)


@pytest_asyncio.fixture
async def sample_task(test_context, task_repo, unique_crm_id) -> Task:
    """Создает тестовую задачу"""
    task_id = unique_crm_id("task")
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Test Task",
        description="Test task description",
        priority="medium",
        status="pending",
        due_date=date.today(),
        linked_entity_id=None,
        source_note_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await task_repo.create(task)
    yield task
    
    await task_repo.delete(task_id)


@pytest_asyncio.fixture
async def sample_relationship(test_context, relationship_repo, unique_crm_id) -> Relationship:
    """Создает тестовую связь"""
    rel_id = unique_crm_id("rel")
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=f"entity_{unique_crm_id('src')}",
        target_entity_id=f"entity_{unique_crm_id('tgt')}",
        relationship_type="connected_to",
        weight=1.0,
        attributes={},
        created_at=datetime.now(timezone.utc),
    )
    
    await relationship_repo.create(relationship)
    yield relationship
    
    await relationship_repo.delete(rel_id)


# === Session-scoped user/company для API тестов ===

@pytest_asyncio.fixture(scope="session")
async def crm_api_user_company(migrated_db):
    """
    Session-scoped пользователь и компания для CRM API тестов.
    
    Сохраняются в shared_db чтобы CRM сервер в subprocess мог их найти.
    """
    from core.models import User, Company
    from core.models.billing_models import TariffPlan
    from core.config import get_settings
    from core.db.storage import Storage
    from core.context import get_context
    from core.db.repositories.company_repository import CompanyRepository
    from core.db.repositories.user_repository import UserRepository
    
    settings = get_settings()
    storage = Storage(db_url=settings.database.shared_url, get_context_func=get_context)
    company_repo = CompanyRepository(storage=storage)
    user_repo = UserRepository(storage=storage)
    
    unique_suffix = uuid.uuid4().hex[:8]
    
    company = Company(
        company_id=f"crm_api_company_{unique_suffix}",
        subdomain=f"crm_api_{unique_suffix}",
        name="CRM API Test Company",
        tariff_plan=TariffPlan.ENTERPRISE,
        balance=100000.0,
        status="active"
    )
    
    user = User(
        user_id=f"crm_api_user_{unique_suffix}",
        provider="test",
        provider_user_id=f"crm_api_{unique_suffix}",
        email=f"crm_api_{unique_suffix}@example.com",
        name="CRM API Test User",
        status="active",
        groups=["user"],
        companies={company.company_id: ["admin"]},
        active_company_id=company.company_id
    )
    
    await company_repo.set(company)
    await user_repo.set(user)
    
    yield {"user": user, "company": company}
    
    await user_repo.delete(user.user_id)
    await company_repo.delete(company.company_id)


# === CRM Server для API тестов ===

@pytest.fixture(scope="session")
def crm_server_process(crm_db, migrated_db, crm_api_user_company):
    """
    Запускает CRM сервер в subprocess для E2E тестов.
    
    Зависит от crm_api_user_company чтобы user/company были в БД
    до запуска сервера.
    """
    import subprocess
    import sys
    import socket
    import time
    import os
    from pathlib import Path
    
    def get_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]
    
    def wait_for_server(host: str, port: int, timeout: float = 45.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection((host, port), timeout=2):
                    return True
            except OSError:
                time.sleep(0.5)
        return False
    
    port = get_free_port()
    host = "127.0.0.1"
    project_root = Path(__file__).parent.parent.parent
    
    cmd = [
        sys.executable, "-m", "uvicorn",
        "apps.crm.main:app",
        "--host", host,
        "--port", str(port),
        "--log-level", "warning"
    ]
    
    process = subprocess.Popen(
        cmd,
        cwd=str(project_root),
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    
    if not wait_for_server(host, port, timeout=45):
        process.terminate()
        raise RuntimeError(f"CRM сервер не запустился на {host}:{port}")
    
    yield {"host": host, "port": port, "url": f"http://{host}:{port}"}
    
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest_asyncio.fixture
async def crm_client(crm_server_process, crm_api_user_company):
    """
    HTTP клиент для тестирования CRM API.
    
    Использует session-scoped user/company для консистентности.
    """
    import httpx
    from core.utils.tokens import get_token_service
    from core.context import set_context, clear_context
    from core.models import Context
    
    user = crm_api_user_company["user"]
    company = crm_api_user_company["company"]
    
    # Устанавливаем контекст для текущего теста
    context = Context(
        user=user,
        session_id=f"crm_api_session_{uuid.uuid4().hex[:8]}",
        platform="api",
        active_company=company,
        metadata={}
    )
    set_context(context)
    
    token_service = get_token_service()
    token = token_service.create_token(
        user_id=user.user_id,
        company_id=company.company_id,
        roles=["admin"],
    )
    
    async with httpx.AsyncClient(
        base_url=crm_server_process["url"],
        headers={
            "Authorization": f"Bearer {token}",
            "X-Company-Id": company.company_id,
        }
    ) as client:
        client.test_user = user
        client.test_company = company
        yield client
    
    clear_context()
