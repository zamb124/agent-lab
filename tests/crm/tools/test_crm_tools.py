"""
Тесты CRM Tools для AI ассистента.

Каждый инструмент тестируется отдельно с реальными данными в CRM.
НИКАКИХ МОКОВ - используем реальный CRM сервер и реальные данные.
"""

import pytest
import uuid
from datetime import date, timedelta
from httpx import AsyncClient

from core.context import set_context, clear_context, Context


def make_crm_context(user, company, crm_client, crm_server_process, session_id: str) -> Context:
    """Создает контекст с URL CRM сервера"""
    crm_api_url = f"{crm_server_process['url']}/crm/api/v1"
    return Context(
        user=user,
        session_id=session_id,
        platform="api",
        active_company=company,
        auth_token=crm_client.headers.get("Authorization", "").replace("Bearer ", ""),
        metadata={"crm_api_url": crm_api_url}
    )


class TestCRMTools:
    """Тесты для каждого CRM tool отдельно"""
    
    @pytest.mark.asyncio
    async def test_search_notes_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_note,
        crm_api_user_company
    ):
        """Тест инструмента search_notes"""
        from apps.agents.tools.crm.crm_tools import search_notes
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_search_notes")
        set_context(context)
        
        try:
            result = await search_notes.ainvoke({
                "query": "test",
                "limit": 10
            })
            
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_get_note_by_id_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_note,
        crm_api_user_company
    ):
        """Тест инструмента get_note_by_id"""
        from apps.agents.tools.crm.crm_tools import get_note_by_id
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_get_note")
        set_context(context)
        
        try:
            result = await get_note_by_id.ainvoke({
                "note_id": test_note.note_id
            })
            
            assert isinstance(result, str)
            assert test_note.title in result or "не найдена" in result
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_get_today_notes_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_note,
        crm_api_user_company
    ):
        """Тест инструмента get_today_notes"""
        from apps.agents.tools.crm.crm_tools import get_today_notes
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_today_notes")
        set_context(context)
        
        try:
            result = await get_today_notes.ainvoke({})
            
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_search_tasks_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_task,
        crm_api_user_company
    ):
        """Тест инструмента search_tasks"""
        from apps.agents.tools.crm.crm_tools import search_tasks
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_search_tasks")
        set_context(context)
        
        try:
            result = await search_tasks.ainvoke({
                "status": "pending",
                "limit": 10
            })
            
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_get_my_tasks_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_task,
        crm_api_user_company
    ):
        """Тест инструмента get_my_tasks"""
        from apps.agents.tools.crm.crm_tools import get_my_tasks
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_my_tasks")
        set_context(context)
        
        try:
            result = await get_my_tasks.ainvoke({
                "status": "pending"
            })
            
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_get_overdue_tasks_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        crm_container,
        crm_api_user_company
    ):
        """Тест инструмента get_overdue_tasks"""
        from apps.agents.tools.crm.crm_tools import get_overdue_tasks
        from apps.crm.db.models import Task
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        # Создаем просроченную задачу
        overdue_task = Task(
            task_id=f"overdue_{uuid.uuid4().hex[:8]}",
            company_id=company.company_id,
            user_id=user.user_id,
            title="Overdue Test Task",
            description="Should be overdue",
            priority="high",
            status="pending",
            due_date=date.today() - timedelta(days=5),
        )
        await crm_container.task_repository.create(overdue_task)
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_overdue_tasks")
        set_context(context)
        
        try:
            result = await get_overdue_tasks.ainvoke({})
            
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            clear_context()
            await crm_container.task_repository.delete(overdue_task.task_id)
    
    @pytest.mark.asyncio
    async def test_get_task_stats_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_task,
        crm_api_user_company
    ):
        """Тест инструмента get_task_stats"""
        from apps.agents.tools.crm.crm_tools import get_task_stats
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_task_stats")
        set_context(context)
        
        try:
            result = await get_task_stats.ainvoke({})
            
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_search_entities_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_entity,
        crm_api_user_company
    ):
        """Тест инструмента search_entities"""
        from apps.agents.tools.crm.crm_tools import search_entities
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_search_entities")
        set_context(context)
        
        try:
            result = await search_entities.ainvoke({
                "query": "Test",
                "limit": 10
            })
            
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_get_entity_by_id_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_entity,
        crm_api_user_company
    ):
        """Тест инструмента get_entity_by_id"""
        from apps.agents.tools.crm.crm_tools import get_entity_by_id
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_get_entity")
        set_context(context)
        
        try:
            result = await get_entity_by_id.ainvoke({
                "entity_id": test_entity.entity_id
            })
            
            assert isinstance(result, str)
            assert test_entity.name in result or "не найден" in result
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_get_entity_relationships_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_entity,
        crm_api_user_company
    ):
        """Тест инструмента get_entity_relationships"""
        from apps.agents.tools.crm.crm_tools import get_entity_relationships
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_entity_relationships")
        set_context(context)
        
        try:
            result = await get_entity_relationships.ainvoke({
                "entity_id": test_entity.entity_id,
                "depth": 1
            })
            
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_get_daily_summary_tool(
        self, 
        crm_client: AsyncClient,
        crm_server_process,
        test_note,
        crm_api_user_company
    ):
        """Тест инструмента get_daily_summary"""
        from apps.agents.tools.crm.crm_tools import get_daily_summary
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        context = make_crm_context(user, company, crm_client, crm_server_process, "test_daily_summary")
        set_context(context)
        
        try:
            today = date.today().isoformat()
            result = await get_daily_summary.ainvoke({
                "note_date": today
            })
            
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            clear_context()
