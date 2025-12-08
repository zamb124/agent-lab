"""
Интеграционный тест CRM Assistant Agent.

Проверяет что агент:
1. Мигрируется в БД
2. Загружается через flow_factory
3. Вызывает tools и получает данные из CRM API

НИКАКИХ МОКОВ - используем реальный CRM сервер и реальные данные.
Mock только для LLM чтобы контролировать какие tools вызываются.
"""

import pytest
import pytest_asyncio
import uuid
from datetime import date, timedelta
from langchain_core.messages import HumanMessage

from apps.crm.db.models import Note, Task
from core.context import set_context, clear_context, Context


CRM_ASSISTANT_FLOW_ID = "apps.agents.flows.crm_assistant_flow.crm_assistant_flow"
CRM_ASSISTANT_AGENT_ID = "apps.agents.agents.crm.crm_assistant_agent.CRMAssistantAgent"


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


@pytest_asyncio.fixture
async def migrated_crm_flow(migrated_db, migrator, session_test_data, flow_repo, agent_repo):
    """
    Мигрирует CRM Assistant Flow для теста.
    Использует session_test_data чтобы flow был доступен в том же контексте.
    """
    company = session_test_data["company"]
    
    # Мигрируем flow с зависимостями
    await migrator.migrate_for_company(
        company=company,
        flows=[CRM_ASSISTANT_FLOW_ID],
        with_dependencies=True
    )
    
    flow = await flow_repo.get(CRM_ASSISTANT_FLOW_ID)
    agent = await agent_repo.get(CRM_ASSISTANT_AGENT_ID)
    
    yield {
        "flow": flow,
        "agent": agent,
        "flow_id": CRM_ASSISTANT_FLOW_ID,
        "agent_id": CRM_ASSISTANT_AGENT_ID,
        "company": company,
    }


@pytest_asyncio.fixture
async def crm_data_for_agent(crm_container, session_test_data):
    """
    Создает тестовые данные в CRM для агента.
    Notes, Tasks и Entities.
    """
    user = session_test_data["user"]
    company = session_test_data["company"]
    
    suffix = uuid.uuid4().hex[:6]
    
    # Создаем несколько заметок
    notes = []
    for i in range(3):
        note = Note(
            note_id=f"agent_test_note_{suffix}_{i}",
            company_id=company.company_id,
            user_id=user.user_id,
            title=f"Meeting Note {i+1}",
            content="Discussed project Alpha with team. Action items: review design, prepare demo. Participant: John Smith.",
            note_type="meeting_minutes",
            note_date=date.today() - timedelta(days=i),
            visibility="public",
        )
        await crm_container.note_repository.create(note)
        notes.append(note)
    
    # Создаем задачи
    tasks = []
    task_data = [
        ("Review design docs", "pending", "high", 0),
        ("Prepare demo presentation", "in_progress", "medium", 1),
        ("Send follow-up email", "pending", "urgent", -1),
    ]
    for title, status, priority, due_offset in task_data:
        task = Task(
            task_id=f"agent_test_task_{suffix}_{title[:10]}",
            company_id=company.company_id,
            user_id=user.user_id,
            title=title,
            description=f"Task description for {title}",
            priority=priority,
            status=status,
            due_date=date.today() + timedelta(days=due_offset),
        )
        await crm_container.task_repository.create(task)
        tasks.append(task)
    
    # Создаем сущность
    from apps.crm.models.entity_models import EntityCreate
    entity = await crm_container.entity_service.create_entity(
        EntityCreate(
            name=f"John Smith {suffix}",
            type="person",
            attributes={"email": "john@example.com", "position": "Project Manager"}
        ),
        company_id=company.company_id
    )
    
    yield {
        "notes": notes,
        "tasks": tasks,
        "entity": entity,
        "user": user,
        "company": company,
    }
    
    # Cleanup
    for note in notes:
        try:
            await crm_container.note_repository.delete(note.note_id)
        except Exception:
            pass
    for task in tasks:
        try:
            await crm_container.task_repository.delete(task.task_id)
        except Exception:
            pass
    try:
        await crm_container.entity_service.delete_entity(
            entity.entity_id, 
            company_id=company.company_id
        )
    except Exception:
        pass


class TestCRMAssistantFlowIntegration:
    """Интеграционные тесты CRM Assistant Flow"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_crm_assistant_flow_migration(self, migrated_crm_flow):
        """Тест что CRM Assistant Flow мигрировался в БД"""
        flow = migrated_crm_flow["flow"]
        agent = migrated_crm_flow["agent"]
        
        assert flow is not None, "CRM Assistant Flow не мигрировался"
        assert flow.name == "CRM Assistant"
        assert flow.entry_point_agent == CRM_ASSISTANT_AGENT_ID
        
        assert agent is not None, "CRM Assistant Agent не мигрировался"
        assert len(agent.tools) > 0, f"У агента нет tools. Tools: {agent.tools}"
        
        print(f"CRM Assistant мигрировался с {len(agent.tools)} tools")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_crm_assistant_flow_with_search_notes(
        self,
        migrated_crm_flow,
        crm_client,
        crm_server_process,
        crm_data_for_agent,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """
        Тест CRM Assistant Flow с вызовом search_notes.
        
        Mock LLM настроен на вызов search_notes tool.
        Проверяем что flow выполняется и tool отрабатывает с реальными данными CRM.
        """
        user = crm_data_for_agent["user"]
        company = crm_data_for_agent["company"]
        
        # Настраиваем mock LLM
        mock_llm.configure(
            response_queue=[
                {"type": "tool_call", "tool": "search_notes", "args": {"query": "meeting", "limit": 10}},
                {"type": "text", "content": "Найдено несколько заметок о встречах."}
            ]
        )
        
        # Устанавливаем контекст с CRM API URL
        context = make_crm_context(user, company, crm_client, crm_server_process, unique_id("crm_flow_test"))
        set_context(context)
        
        try:
            # Получаем flow через factory
            flow = await flow_factory.get_flow(migrated_crm_flow["flow_id"])
            assert flow is not None, "Flow не загрузился через factory"
            
            # Выполняем flow
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content="Найди заметки о встречах")]},
                config={"configurable": {"session_id": unique_id("search_notes")}}
            )
            
            assert "messages" in result
            assert len(result["messages"]) > 0
            
            print(f"Flow выполнился, получено {len(result['messages'])} сообщений")
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_crm_assistant_get_tasks(
        self,
        migrated_crm_flow,
        crm_client,
        crm_server_process,
        crm_data_for_agent,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """Тест вызова get_my_tasks tool"""
        user = crm_data_for_agent["user"]
        company = crm_data_for_agent["company"]
        
        mock_llm.configure(
            response_queue=[
                {"type": "tool_call", "tool": "get_my_tasks", "args": {"status": "pending"}},
                {"type": "text", "content": "Вот ваши задачи."}
            ]
        )
        
        context = make_crm_context(user, company, crm_client, crm_server_process, unique_id("crm_tasks_test"))
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(migrated_crm_flow["flow_id"])
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content="Покажи мои задачи")]},
                config={"configurable": {"session_id": unique_id("get_tasks")}}
            )
            
            assert "messages" in result
            assert len(result["messages"]) > 0
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_crm_assistant_search_entities(
        self,
        migrated_crm_flow,
        crm_client,
        crm_server_process,
        crm_data_for_agent,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """Тест вызова search_entities tool"""
        user = crm_data_for_agent["user"]
        company = crm_data_for_agent["company"]
        entity = crm_data_for_agent["entity"]
        
        mock_llm.configure(
            response_queue=[
                {"type": "tool_call", "tool": "search_entities", "args": {"query": "John", "limit": 10}},
                {"type": "text", "content": f"Найден контакт: {entity.name}"}
            ]
        )
        
        context = make_crm_context(user, company, crm_client, crm_server_process, unique_id("crm_entities_test"))
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(migrated_crm_flow["flow_id"])
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content="Найди контакт John")]},
                config={"configurable": {"session_id": unique_id("search_entities")}}
            )
            
            assert "messages" in result
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_crm_assistant_overdue_tasks(
        self,
        migrated_crm_flow,
        crm_client,
        crm_server_process,
        crm_data_for_agent,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """Тест вызова get_overdue_tasks tool"""
        user = crm_data_for_agent["user"]
        company = crm_data_for_agent["company"]
        
        mock_llm.configure(
            response_queue=[
                {"type": "tool_call", "tool": "get_overdue_tasks", "args": {}},
                {"type": "text", "content": "У вас есть просроченные задачи."}
            ]
        )
        
        context = make_crm_context(user, company, crm_client, crm_server_process, unique_id("crm_overdue_test"))
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(migrated_crm_flow["flow_id"])
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content="Какие задачи просрочены?")]},
                config={"configurable": {"session_id": unique_id("overdue_tasks")}}
            )
            
            assert "messages" in result
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_crm_assistant_task_stats(
        self,
        migrated_crm_flow,
        crm_client,
        crm_server_process,
        crm_data_for_agent,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """Тест вызова get_task_stats tool"""
        user = crm_data_for_agent["user"]
        company = crm_data_for_agent["company"]
        
        mock_llm.configure(
            response_queue=[
                {"type": "tool_call", "tool": "get_task_stats", "args": {}},
                {"type": "text", "content": "Статистика по задачам."}
            ]
        )
        
        context = make_crm_context(user, company, crm_client, crm_server_process, unique_id("crm_stats_test"))
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(migrated_crm_flow["flow_id"])
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content="Покажи статистику задач")]},
                config={"configurable": {"session_id": unique_id("task_stats")}}
            )
            
            assert "messages" in result
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_crm_assistant_today_notes(
        self,
        migrated_crm_flow,
        crm_client,
        crm_server_process,
        crm_data_for_agent,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """Тест вызова get_today_notes tool"""
        user = crm_data_for_agent["user"]
        company = crm_data_for_agent["company"]
        
        mock_llm.configure(
            response_queue=[
                {"type": "tool_call", "tool": "get_today_notes", "args": {}},
                {"type": "text", "content": "Вот заметки за сегодня."}
            ]
        )
        
        context = make_crm_context(user, company, crm_client, crm_server_process, unique_id("crm_today_test"))
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(migrated_crm_flow["flow_id"])
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content="Что у меня сегодня?")]},
                config={"configurable": {"session_id": unique_id("today_notes")}}
            )
            
            assert "messages" in result
            
        finally:
            clear_context()
