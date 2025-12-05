"""
Тесты для расширенного функционала TaskRepository.
Тестируем: tags, assignees.
"""

import pytest
from datetime import date, datetime, timezone, timedelta

from apps.crm.db.models import Task


@pytest.mark.asyncio
async def test_create_task_with_tags(task_repo, test_context, unique_crm_id):
    """Тест создания задачи с тегами"""
    task_id = unique_crm_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Tagged Task",
        description="Task with tags",
        priority="high",
        status="pending",
        due_date=date.today() + timedelta(days=7),
        tags=["urgent", "client", "follow-up"],
        assignees=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    created = await task_repo.create(task)
    
    assert "urgent" in created.tags
    assert "client" in created.tags
    assert "follow-up" in created.tags
    assert len(created.tags) == 3
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_create_task_with_assignees(task_repo, test_context, unique_crm_id):
    """Тест создания задачи с соучастниками"""
    task_id = unique_crm_id("task")
    assignee_1 = unique_crm_id("user1")
    assignee_2 = unique_crm_id("user2")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Shared Task",
        description="Task with assignees",
        priority="medium",
        status="pending",
        due_date=date.today() + timedelta(days=3),
        tags=[],
        assignees=[assignee_1, assignee_2],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    created = await task_repo.create(task)
    
    assert assignee_1 in created.assignees
    assert assignee_2 in created.assignees
    assert len(created.assignees) == 2
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_update_task_tags(task_repo, test_context, unique_crm_id):
    """Тест обновления тегов задачи"""
    task_id = unique_crm_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Update Tags Task",
        description="Will update tags",
        priority="low",
        status="pending",
        due_date=date.today(),
        tags=["initial"],
        assignees=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await task_repo.create(task)
    
    task.tags = ["updated", "new-tag"]
    task.updated_at = datetime.now(timezone.utc)
    
    updated = await task_repo.update(task)
    
    assert "updated" in updated.tags
    assert "new-tag" in updated.tags
    assert "initial" not in updated.tags
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_update_task_assignees(task_repo, test_context, unique_crm_id):
    """Тест обновления соучастников задачи"""
    task_id = unique_crm_id("task")
    old_assignee = unique_crm_id("old_user")
    new_assignee = unique_crm_id("new_user")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Update Assignees Task",
        description="Will update assignees",
        priority="medium",
        status="pending",
        due_date=date.today(),
        tags=[],
        assignees=[old_assignee],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await task_repo.create(task)
    
    task.assignees = [new_assignee]
    task.updated_at = datetime.now(timezone.utc)
    
    updated = await task_repo.update(task)
    
    assert new_assignee in updated.assignees
    assert old_assignee not in updated.assignees
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_task_with_tags_and_assignees(task_repo, test_context, unique_crm_id):
    """Тест создания задачи с тегами и соучастниками одновременно"""
    task_id = unique_crm_id("task")
    assignee = unique_crm_id("assignee")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Full Task",
        description="Has both tags and assignees",
        priority="urgent",
        status="in_progress",
        due_date=date.today(),
        tags=["important", "meeting"],
        assignees=[assignee],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    created = await task_repo.create(task)
    
    assert len(created.tags) == 2
    assert len(created.assignees) == 1
    assert "important" in created.tags
    assert assignee in created.assignees
    
    await task_repo.delete(task_id)


@pytest.mark.asyncio
async def test_task_empty_tags_and_assignees(task_repo, test_context, unique_crm_id):
    """Тест создания задачи с пустыми tags и assignees"""
    task_id = unique_crm_id("task")
    
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Empty Arrays Task",
        description="No tags or assignees",
        priority="low",
        status="pending",
        due_date=date.today(),
        tags=[],
        assignees=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    created = await task_repo.create(task)
    
    assert created.tags == []
    assert created.assignees == []
    
    await task_repo.delete(task_id)

