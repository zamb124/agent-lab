"""
Тесты для расширенного функционала TaskService.
Тестируем: tags, assignees.
"""

import pytest
from datetime import date, timedelta

from apps.crm.models.task_models import TaskCreate, TaskUpdate, TaskPriority


@pytest.mark.asyncio
async def test_create_task_with_tags(task_service, test_context, unique_crm_id):
    """Тест создания задачи с тегами"""
    data = TaskCreate(
        title="Tagged Task",
        description="Task with tags",
        priority=TaskPriority.HIGH,
        due_date=date.today() + timedelta(days=7),
        tags=["urgent", "client", "follow-up"],
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert "urgent" in result.tags
    assert "client" in result.tags
    assert "follow-up" in result.tags
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_create_task_with_assignees(task_service, test_context, unique_crm_id):
    """Тест создания задачи с соучастниками"""
    assignee_1 = unique_crm_id("user1")
    assignee_2 = unique_crm_id("user2")
    
    data = TaskCreate(
        title="Shared Task",
        description="Task with assignees",
        priority=TaskPriority.MEDIUM,
        due_date=date.today() + timedelta(days=3),
        assignees=[assignee_1, assignee_2],
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert assignee_1 in result.assignees
    assert assignee_2 in result.assignees
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_update_task_tags(task_service, test_context, unique_crm_id):
    """Тест обновления тегов задачи"""
    data = TaskCreate(
        title="Update Tags",
        description="Will update tags",
        priority=TaskPriority.LOW,
        due_date=date.today(),
        tags=["initial"],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    update_data = TaskUpdate(tags=["updated", "new-tag"])
    updated = await task_service.update_task(created.task_id, update_data)
    
    assert "updated" in updated.tags
    assert "new-tag" in updated.tags
    assert "initial" not in updated.tags
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_update_task_assignees(task_service, test_context, unique_crm_id):
    """Тест обновления соучастников задачи"""
    old_assignee = unique_crm_id("old_user")
    new_assignee = unique_crm_id("new_user")
    
    data = TaskCreate(
        title="Update Assignees",
        description="Will update assignees",
        priority=TaskPriority.MEDIUM,
        due_date=date.today(),
        assignees=[old_assignee],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    update_data = TaskUpdate(assignees=[new_assignee])
    updated = await task_service.update_task(created.task_id, update_data)
    
    assert new_assignee in updated.assignees
    assert old_assignee not in updated.assignees
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_add_tag_to_task(task_service, test_context, unique_crm_id):
    """Тест добавления тега к задаче через add_tag"""
    data = TaskCreate(
        title="Add Tag",
        description="Will add tag",
        priority=TaskPriority.MEDIUM,
        due_date=date.today(),
        tags=["existing"],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    updated = await task_service.add_tag(created.task_id, "new-tag")
    
    assert "existing" in updated.tags
    assert "new-tag" in updated.tags
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_add_tag_idempotent(task_service, test_context, unique_crm_id):
    """Тест что add_tag идемпотентен - не дублирует тег"""
    data = TaskCreate(
        title="Idempotent Tag",
        description="Will add same tag twice",
        priority=TaskPriority.MEDIUM,
        due_date=date.today(),
        tags=["existing"],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    await task_service.add_tag(created.task_id, "existing")
    updated = await task_service.add_tag(created.task_id, "existing")
    
    # Тег не должен дублироваться
    assert updated.tags.count("existing") == 1
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_remove_tag_from_task(task_service, test_context, unique_crm_id):
    """Тест удаления тега из задачи через remove_tag"""
    data = TaskCreate(
        title="Remove Tag",
        description="Will remove tag",
        priority=TaskPriority.MEDIUM,
        due_date=date.today(),
        tags=["keep", "remove"],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    updated = await task_service.remove_tag(created.task_id, "remove")
    
    assert "keep" in updated.tags
    assert "remove" not in updated.tags
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_remove_nonexistent_tag(task_service, test_context, unique_crm_id):
    """Тест удаления несуществующего тега - не должно ломаться"""
    data = TaskCreate(
        title="Remove Nonexistent",
        description="Remove tag that does not exist",
        priority=TaskPriority.MEDIUM,
        due_date=date.today(),
        tags=["existing"],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    updated = await task_service.remove_tag(created.task_id, "nonexistent")
    
    assert "existing" in updated.tags
    assert len(updated.tags) == 1
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_add_assignee_to_task(task_service, test_context, unique_crm_id):
    """Тест добавления соучастника через add_assignee"""
    existing_assignee = unique_crm_id("existing")
    new_assignee = unique_crm_id("new")
    
    data = TaskCreate(
        title="Add Assignee",
        description="Will add assignee",
        priority=TaskPriority.MEDIUM,
        due_date=date.today(),
        assignees=[existing_assignee],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    updated = await task_service.add_assignee(created.task_id, new_assignee)
    
    assert existing_assignee in updated.assignees
    assert new_assignee in updated.assignees
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_add_assignee_idempotent(task_service, test_context, unique_crm_id):
    """Тест что add_assignee идемпотентен"""
    assignee = unique_crm_id("assignee")
    
    data = TaskCreate(
        title="Idempotent Assignee",
        description="Will add same assignee twice",
        priority=TaskPriority.MEDIUM,
        due_date=date.today(),
        assignees=[assignee],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    await task_service.add_assignee(created.task_id, assignee)
    updated = await task_service.add_assignee(created.task_id, assignee)
    
    assert updated.assignees.count(assignee) == 1
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_remove_assignee_from_task(task_service, test_context, unique_crm_id):
    """Тест удаления соучастника через remove_assignee"""
    keep_assignee = unique_crm_id("keep")
    remove_assignee = unique_crm_id("remove")
    
    data = TaskCreate(
        title="Remove Assignee",
        description="Will remove assignee",
        priority=TaskPriority.MEDIUM,
        due_date=date.today(),
        assignees=[keep_assignee, remove_assignee],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    updated = await task_service.remove_assignee(created.task_id, remove_assignee)
    
    assert keep_assignee in updated.assignees
    assert remove_assignee not in updated.assignees
    
    await task_service.delete_task(created.task_id)


@pytest.mark.asyncio
async def test_get_tasks_by_tag(task_service, test_context, unique_crm_id):
    """Тест получения задач по тегу"""
    unique_tag = unique_crm_id("tag")
    created_ids = []
    
    for i in range(2):
        data = TaskCreate(
            title=f"Tagged Task {i}",
            description="Has specific tag",
            priority=TaskPriority.MEDIUM,
            due_date=date.today(),
            tags=[unique_tag, "common"],
        )
        result = await task_service.create_task(
            data,
            company_id=test_context.active_company.company_id,
            user_id=test_context.user.user_id
        )
        created_ids.append(result.task_id)
    
    tasks = await task_service.get_tasks_by_tag(
        unique_tag,
        company_id=test_context.active_company.company_id
    )
    
    task_ids = [t.task_id for t in tasks]
    for created_id in created_ids:
        assert created_id in task_ids
    
    for task_id in created_ids:
        await task_service.delete_task(task_id)


@pytest.mark.asyncio
async def test_get_tasks_by_assignee(task_service, test_context, unique_crm_id):
    """Тест получения задач по соучастнику"""
    assignee = unique_crm_id("assignee")
    created_ids = []
    
    for i in range(2):
        data = TaskCreate(
            title=f"Assigned Task {i}",
            description="Assigned to specific user",
            priority=TaskPriority.MEDIUM,
            due_date=date.today(),
            assignees=[assignee],
        )
        result = await task_service.create_task(
            data,
            company_id=test_context.active_company.company_id,
            user_id=test_context.user.user_id
        )
        created_ids.append(result.task_id)
    
    tasks = await task_service.get_tasks_by_assignee(
        assignee,
        company_id=test_context.active_company.company_id
    )
    
    task_ids = [t.task_id for t in tasks]
    for created_id in created_ids:
        assert created_id in task_ids
    
    for task_id in created_ids:
        await task_service.delete_task(task_id)


@pytest.mark.asyncio
async def test_task_with_both_tags_and_assignees(task_service, test_context, unique_crm_id):
    """Тест создания задачи с тегами и соучастниками"""
    assignee = unique_crm_id("assignee")
    
    data = TaskCreate(
        title="Full Task",
        description="Has tags and assignees",
        priority=TaskPriority.URGENT,
        due_date=date.today(),
        tags=["important", "meeting"],
        assignees=[assignee],
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert "important" in result.tags
    assert "meeting" in result.tags
    assert assignee in result.assignees
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_empty_tags_default(task_service, test_context, unique_crm_id):
    """Тест что tags по умолчанию пустой список"""
    data = TaskCreate(
        title="No Tags Task",
        description="Without tags",
        priority=TaskPriority.LOW,
        due_date=date.today(),
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert result.tags == []
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_empty_assignees_default(task_service, test_context, unique_crm_id):
    """Тест что assignees по умолчанию пустой список"""
    data = TaskCreate(
        title="No Assignees Task",
        description="Without assignees",
        priority=TaskPriority.LOW,
        due_date=date.today(),
    )
    
    result = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert result.assignees == []
    
    await task_service.delete_task(result.task_id)


@pytest.mark.asyncio
async def test_update_preserves_other_fields(task_service, test_context, unique_crm_id):
    """Тест что обновление tags/assignees не влияет на другие поля"""
    assignee = unique_crm_id("assignee")
    
    data = TaskCreate(
        title="Preserve Fields",
        description="Original description",
        priority=TaskPriority.HIGH,
        due_date=date.today() + timedelta(days=5),
        tags=["original"],
        assignees=[assignee],
    )
    
    created = await task_service.create_task(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    updated = await task_service.add_tag(created.task_id, "new-tag")
    
    assert updated.title == "Preserve Fields"
    assert updated.description == "Original description"
    assert updated.priority == "high"
    assert assignee in updated.assignees
    assert "original" in updated.tags
    assert "new-tag" in updated.tags
    
    await task_service.delete_task(created.task_id)
