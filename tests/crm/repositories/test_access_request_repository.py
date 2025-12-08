"""
Тесты для AccessRequestRepository.
"""

import pytest
import uuid

from apps.crm.db.models import AccessRequest


@pytest.fixture
def access_request_repository(crm_container):
    """Fixture для AccessRequestRepository"""
    return crm_container.access_request_repository


@pytest.fixture
async def sample_access_request(access_request_repository, test_company_id, test_user_id):
    """Создает тестовый запрос на доступ"""
    request = AccessRequest(
        request_id=str(uuid.uuid4()),
        company_id=test_company_id,
        requester_id=test_user_id,
        owner_id="owner_user_123",
        resource_type="note",
        resource_id="note_123",
        message="Мне нужен доступ для работы",
        status="pending"
    )
    return await access_request_repository.create(request)


class TestAccessRequestRepository:
    """Тесты AccessRequestRepository"""
    
    @pytest.mark.asyncio
    async def test_create_access_request(self, access_request_repository, test_company_id, test_user_id):
        """Тест создания запроса на доступ"""
        request = AccessRequest(
            request_id=str(uuid.uuid4()),
            company_id=test_company_id,
            requester_id=test_user_id,
            owner_id="owner_456",
            resource_type="note",
            resource_id="note_456",
            message="Тестовый запрос",
            status="pending"
        )
        
        created = await access_request_repository.create(request)
        
        assert created.request_id == request.request_id
        assert created.requester_id == test_user_id
        assert created.status == "pending"
    
    @pytest.mark.asyncio
    async def test_get_access_request(self, access_request_repository, sample_access_request):
        """Тест получения запроса по ID"""
        fetched = await access_request_repository.get(sample_access_request.request_id)
        
        assert fetched is not None
        assert fetched.request_id == sample_access_request.request_id
        assert fetched.message == sample_access_request.message
    
    @pytest.mark.asyncio
    async def test_get_by_owner(self, access_request_repository, test_company_id, test_user_id):
        """Тест получения запросов по владельцу"""
        owner_id = "test_owner_789"
        
        # Создаем несколько запросов для этого владельца
        for i in range(3):
            request = AccessRequest(
                request_id=str(uuid.uuid4()),
                company_id=test_company_id,
                requester_id=test_user_id,
                owner_id=owner_id,
                resource_type="note",
                resource_id=f"note_{i}",
                status="pending"
            )
            await access_request_repository.create(request)
        
        requests = await access_request_repository.get_by_owner(owner_id)
        
        assert len(requests) >= 3
        for req in requests:
            assert req.owner_id == owner_id
    
    @pytest.mark.asyncio
    async def test_get_by_owner_with_status_filter(self, access_request_repository, test_company_id, test_user_id):
        """Тест фильтрации запросов владельца по статусу"""
        owner_id = "filter_owner_123"
        
        # Создаем запросы с разными статусами
        for status in ["pending", "approved", "pending"]:
            request = AccessRequest(
                request_id=str(uuid.uuid4()),
                company_id=test_company_id,
                requester_id=test_user_id,
                owner_id=owner_id,
                resource_type="note",
                resource_id=str(uuid.uuid4()),
                status=status
            )
            await access_request_repository.create(request)
        
        pending_requests = await access_request_repository.get_by_owner(owner_id, status="pending")
        
        assert len(pending_requests) >= 2
        for req in pending_requests:
            assert req.status == "pending"
    
    @pytest.mark.asyncio
    async def test_get_by_requester(self, access_request_repository, test_company_id):
        """Тест получения запросов по отправителю"""
        requester_id = "requester_xyz"
        
        for i in range(2):
            request = AccessRequest(
                request_id=str(uuid.uuid4()),
                company_id=test_company_id,
                requester_id=requester_id,
                owner_id=f"owner_{i}",
                resource_type="entity",
                resource_id=f"entity_{i}",
                status="pending"
            )
            await access_request_repository.create(request)
        
        requests = await access_request_repository.get_by_requester(requester_id)
        
        assert len(requests) >= 2
        for req in requests:
            assert req.requester_id == requester_id
    
    @pytest.mark.asyncio
    async def test_get_by_resource(self, access_request_repository, test_company_id, test_user_id):
        """Тест получения запросов по ресурсу"""
        resource_id = "shared_resource_123"
        
        # Несколько пользователей запрашивают доступ к одному ресурсу
        for i in range(2):
            request = AccessRequest(
                request_id=str(uuid.uuid4()),
                company_id=test_company_id,
                requester_id=f"user_{i}",
                owner_id="owner_abc",
                resource_type="note",
                resource_id=resource_id,
                status="pending"
            )
            await access_request_repository.create(request)
        
        requests = await access_request_repository.get_by_resource("note", resource_id)
        
        assert len(requests) >= 2
        for req in requests:
            assert req.resource_id == resource_id
    
    @pytest.mark.asyncio
    async def test_get_pending_count(self, access_request_repository, test_company_id, test_user_id):
        """Тест подсчета ожидающих запросов"""
        owner_id = "count_test_owner"
        
        # Создаем 3 pending и 1 approved
        for i in range(3):
            request = AccessRequest(
                request_id=str(uuid.uuid4()),
                company_id=test_company_id,
                requester_id=test_user_id,
                owner_id=owner_id,
                resource_type="note",
                resource_id=str(uuid.uuid4()),
                status="pending"
            )
            await access_request_repository.create(request)
        
        approved = AccessRequest(
            request_id=str(uuid.uuid4()),
            company_id=test_company_id,
            requester_id=test_user_id,
            owner_id=owner_id,
            resource_type="note",
            resource_id=str(uuid.uuid4()),
            status="approved"
        )
        await access_request_repository.create(approved)
        
        count = await access_request_repository.get_pending_count(owner_id)
        
        assert count >= 3
    
    @pytest.mark.asyncio
    async def test_exists(self, access_request_repository, sample_access_request):
        """Тест проверки существования запроса"""
        exists = await access_request_repository.exists(
            requester_id=sample_access_request.requester_id,
            resource_type=sample_access_request.resource_type,
            resource_id=sample_access_request.resource_id,
            status="pending"
        )
        
        assert exists is True
        
        # Несуществующий запрос
        not_exists = await access_request_repository.exists(
            requester_id="nonexistent_user",
            resource_type="note",
            resource_id="nonexistent_note",
            status="pending"
        )
        
        assert not_exists is False
    
    @pytest.mark.asyncio
    async def test_update_status(self, access_request_repository, sample_access_request):
        """Тест обновления статуса запроса"""
        updated = await access_request_repository.update_status(
            sample_access_request.request_id,
            "approved"
        )
        
        assert updated is not None
        assert updated.status == "approved"
        
        # Проверяем что изменение сохранилось
        fetched = await access_request_repository.get(sample_access_request.request_id)
        assert fetched.status == "approved"
    
    @pytest.mark.asyncio
    async def test_update_status_nonexistent(self, access_request_repository):
        """Тест обновления статуса несуществующего запроса"""
        result = await access_request_repository.update_status(
            "nonexistent_request_id",
            "approved"
        )
        
        assert result is None

