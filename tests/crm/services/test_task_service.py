"""
Тесты для TaskService.
"""

import pytest
from datetime import date, timedelta

from apps.crm.models.task_models import TaskCreate, TaskUpdate, TaskPriority, TaskStatus


@pytest.mark.asyncio
async def test_create_task(task_service, test_context, unique_crm_id):
    """Тест создания задачи через сервис"""
    data = TaskCreate(
        title="Service Test Task",
        description="Created via TaskService",
        priority=TaskPriority.HIGH,
        due_date=date.today() + timedelta(days=7),
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert result.title == "Service Test Task"
    assert result.priority == "high"
    assert result.status == "pending"
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_get_task(task_service, test_context, unique_crm_id):
    """Тест получения задачи"""
    data = TaskCreate(
        title="Get Test Task",
        description="Description",
        priority=TaskPriority.MEDIUM,
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    fetched = await task_service.get_task(created.task_id)
    
    assert fetched is not None
    assert fetched.task_id == created.task_id
    assert fetched.title == "Get Test Task"
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_update_task(task_service, test_context, unique_crm_id):
    """Тест обновления задачи"""
    data = TaskCreate(
        title="Update Test Task",
        description="Original description",
        priority=TaskPriority.LOW,
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    update_data = TaskUpdate(
        title="Updated Task Title",
        status=TaskStatus.IN_PROGRESS,
    )
    
    updated = await task_service.update_task(created.task_id, update_data)
    
    assert updated.title == "Updated Task Title"
    assert updated.status == "in_progress"
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_delete_task(task_service, test_context, unique_crm_id):
    """Тест удаления задачи"""
    data = TaskCreate(
        title="Delete Test Task",
        priority=TaskPriority.MEDIUM,
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    success = await task_service.delete_task(created.task_id)
    assert success is True
    
    fetched = await task_service.get_task(created.task_id)
    assert fetched is None


@pytest.mark.asyncio
async def test_list_tasks(task_service, test_context, unique_crm_id):
    """Тест получения списка задач"""
    created_ids = []
    
    for i in range(5):
        data = TaskCreate(
            title=f"List Task {i}",
            priority=TaskPriority.MEDIUM,
        )
        result = await task_service.create_task(
            data,
            company_id=test_context.active_company.company_id,
            user_id=test_context.user.user_id
        )
        created_ids.append(result.task_id)
    
    tasks = await task_service.list_tasks(
        company_id=test_context.active_company.company_id
    )
    
    assert len(tasks) >= 5
    
    for task_id in created_ids:
        await task_service.delete_task(task_id)


@pytest.mark.asyncio
async def test_get_my_tasks(task_service, test_context, unique_crm_id):
    """Тест получения задач текущего пользователя"""
    data = TaskCreate(
        title="My Task",
        priority=TaskPriority.HIGH,
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    my_tasks = await task_service.get_my_tasks(
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    task_ids = [t.task_id for t in my_tasks]
    assert result.task_id in task_ids
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_get_overdue_tasks(task_service, test_context, unique_crm_id):
    """Тест получения просроченных задач"""
    data = TaskCreate(
        title="Overdue Task",
        priority=TaskPriority.HIGH,
        due_date=date.today() - timedelta(days=1),
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    overdue = await task_service.get_overdue_tasks(
        company_id=test_context.active_company.company_id
    )
    
    task_ids = [t.task_id for t in overdue]
    assert result.task_id in task_ids
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_get_due_this_week(task_service, test_context, unique_crm_id):
    """Тест получения задач на этой неделе"""
    data = TaskCreate(
        title="Due This Week Task",
        priority=TaskPriority.MEDIUM,
        due_date=date.today() + timedelta(days=3),
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    this_week = await task_service.get_due_this_week(
        company_id=test_context.active_company.company_id
    )
    
    task_ids = [t.task_id for t in this_week]
    assert result.task_id in task_ids
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_complete_task(task_service, test_context, unique_crm_id):
    """Тест завершения задачи"""
    data = TaskCreate(
        title="Complete Test Task",
        priority=TaskPriority.MEDIUM,
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    update_data = TaskUpdate(status=TaskStatus.COMPLETED)
    updated = await task_service.update_task(result.task_id, update_data)
    
    assert updated.status == "completed"
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_link_task_to_entity(task_service, test_context, unique_crm_id):
    """Тест связывания задачи с сущностью"""
    entity_id = unique_crm_id("entity")
    
    data = TaskCreate(
        title="Entity Task",
        priority=TaskPriority.MEDIUM,
        linked_entity_id=entity_id,
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert result.linked_entity_id == entity_id
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_get_tasks_by_entity(task_service, test_context, unique_crm_id):
    """Тест получения задач по связанной сущности"""
    entity_id = unique_crm_id("entity")
    
    data = TaskCreate(
        title="Entity Related Task",
        priority=TaskPriority.MEDIUM,
        linked_entity_id=entity_id,
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    tasks = await task_service.get_tasks_by_entity(
        entity_id,
        company_id=test_context.active_company.company_id
    )
    
    task_ids = [t.task_id for t in tasks]
    assert result.task_id in task_ids
    
    await task_service.delete_task(result.task_id)

