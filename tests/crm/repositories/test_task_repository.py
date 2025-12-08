"""
Тесты для TaskRepository.
"""

import pytest
from datetime import date, datetime, timezone, timedelta

from apps.crm.db.models import Task


@pytest.mark.asyncio
async def test_create_task(task_repo, test_context, unique_id):
    """Тест создания задачи"""
    task_id = unique_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Complete project",
        description="Finish the CRM project",
        priority="high",
        status="pending",
        due_date=date.today() + timedelta(days=7),
        linked_entity_id=None,
        source_note_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    created = await task_repo.create(task)
    
    assert created.task_id == task_id
    assert created.title == "Complete project"
    assert created.priority == "high"
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_get_task(task_repo, sample_task):
    """Тест получения задачи по ID"""
    fetched = await task_repo.get(sample_task.task_id)
    
    assert fetched is not None
    assert fetched.task_id == sample_task.task_id
    assert fetched.title == sample_task.title


@pytest.mark.asyncio
async def test_update_task(task_repo, sample_task):
    """Тест обновления задачи"""
    sample_task.title = "Updated Task Title"
    sample_task.status = "in_progress"
    sample_task.updated_at = datetime.now(timezone.utc)
    
    updated = await task_repo.update(sample_task)
    
    assert updated.title == "Updated Task Title"
    assert updated.status == "in_progress"


@pytest.mark.asyncio
async def test_delete_task(task_repo, test_context, unique_id):
    """Тест удаления задачи"""
    task_id = unique_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="To Delete",
        priority="low",
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await task_repo.create(task)
    
    success = await task_repo.delete(task_id)
    assert success is True
    
    fetched = await task_repo.get(task_id)
    assert fetched is None


@pytest.mark.asyncio
async def test_get_by_status(task_repo, test_context, unique_id):
    """Тест получения задач по статусу"""
    task_id = unique_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="In Progress Task",
        priority="medium",
        status="in_progress",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await task_repo.create(task)
    
    tasks = await task_repo.get_by_status(
        test_context.active_company.company_id,
        "in_progress"
    )
    
    task_ids = [t.task_id for t in tasks]
    assert task_id in task_ids
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_get_by_priority(task_repo, test_context, unique_id):
    """Тест получения задач по приоритету"""
    task_id = unique_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Urgent Task",
        priority="urgent",
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await task_repo.create(task)
    
    tasks = await task_repo.get_by_priority(
        test_context.active_company.company_id,
        "urgent"
    )
    
    task_ids = [t.task_id for t in tasks]
    assert task_id in task_ids
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_get_by_user(task_repo, test_context, unique_id):
    """Тест получения задач пользователя"""
    task_id = unique_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="My Task",
        priority="medium",
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await task_repo.create(task)
    
    tasks = await task_repo.get_by_user(
        test_context.active_company.company_id,
        test_context.user.user_id
    )
    
    task_ids = [t.task_id for t in tasks]
    assert task_id in task_ids
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_get_overdue(task_repo, test_context, unique_id):
    """Тест получения просроченных задач"""
    task_id = unique_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Overdue Task",
        priority="high",
        status="pending",
        due_date=date.today() - timedelta(days=1),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await task_repo.create(task)
    
    tasks = await task_repo.get_overdue(test_context.active_company.company_id)
    
    task_ids = [t.task_id for t in tasks]
    assert task_id in task_ids
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_get_due_this_week(task_repo, test_context, unique_id):
    """Тест получения задач с дедлайном на этой неделе"""
    task_id = unique_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Due This Week Task",
        priority="medium",
        status="pending",
        due_date=date.today() + timedelta(days=2),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await task_repo.create(task)
    
    tasks = await task_repo.get_due_this_week(
        test_context.active_company.company_id
    )
    
    task_ids = [t.task_id for t in tasks]
    assert task_id in task_ids
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_get_by_entity(task_repo, test_context, unique_id):
    """Тест получения задач, связанных с сущностью"""
    task_id = unique_id("task")
    entity_id = unique_id("entity")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Entity Task",
        priority="medium",
        status="pending",
        linked_entity_id=entity_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await task_repo.create(task)
    
    tasks = await task_repo.get_by_entity(
        test_context.active_company.company_id,
        entity_id
    )
    
    task_ids = [t.task_id for t in tasks]
    assert task_id in task_ids
    
    await task_repo.delete(task_id)



