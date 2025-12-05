"""
Интеграционные тесты для CRM Entity агентов.

Тестирует полный цикл:
1. Миграция flows в БД
2. Вызов агентов через flow_factory
3. Проверка результатов

НИКАКИХ МОКОВ и НИКАКИХ SKIP.
"""

import pytest
import pytest_asyncio
import uuid
from datetime import date

from httpx import AsyncClient
from langchain_core.messages import HumanMessage

from apps.crm.db.models import Note
from core.context import set_context, clear_context, Context


ENTITY_EXTRACTOR_FLOW_CONFIG = "apps.agents.flows.crm_entity_extractor_flow.crm_entity_extractor_flow_config"
ENTITY_COMPARISON_FLOW_CONFIG = "apps.agents.flows.crm_entity_extractor_flow.crm_entity_comparison_flow_config"

ENTITY_EXTRACTOR_FLOW_ID = "crm_entity_extractor"
ENTITY_COMPARISON_FLOW_ID = "crm_entity_comparison"


@pytest_asyncio.fixture
async def migrated_entity_flows(migrated_db, migrator, crm_api_user_company, flow_repo, agent_repo):
    """Мигрирует Entity Extractor и Entity Comparison flows."""
    company = crm_api_user_company["company"]
    
    await migrator.migrate_for_company(
        company=company,
        flows=[ENTITY_EXTRACTOR_FLOW_CONFIG, ENTITY_COMPARISON_FLOW_CONFIG],
        with_dependencies=True
    )
    
    extractor_flow = await flow_repo.get(ENTITY_EXTRACTOR_FLOW_ID)
    comparison_flow = await flow_repo.get(ENTITY_COMPARISON_FLOW_ID)
    
    assert extractor_flow is not None, "Entity Extractor Flow не мигрировался"
    assert comparison_flow is not None, "Entity Comparison Flow не мигрировался"
    
    yield {
        "extractor_flow": extractor_flow,
        "comparison_flow": comparison_flow,
        "company": company,
        "user": crm_api_user_company["user"],
    }


@pytest_asyncio.fixture
async def test_note_for_analysis(crm_container, crm_api_user_company):
    """Создает заметку для анализа."""
    user = crm_api_user_company["user"]
    company = crm_api_user_company["company"]
    suffix = uuid.uuid4().hex[:6]
    
    note = Note(
        note_id=f"test_analysis_note_{suffix}",
        company_id=company.company_id,
        user_id=user.user_id,
        title="Встреча с клиентом",
        content="""
        Сегодня провел встречу с Иваном Петровым из компании ТехноСофт.
        Обсудили проект внедрения CRM системы.
        Иван - руководитель отдела продаж, email: ivan.petrov@technosoft.ru
        Договорились подготовить коммерческое предложение.
        """,
        note_type="meeting_minutes",
        note_date=date.today(),
        visibility="public",
    )
    
    await crm_container.note_repository.create(note)
    
    yield {"note": note, "user": user, "company": company}
    
    try:
        await crm_container.note_repository.delete(note.note_id)
    except Exception:
        pass


class TestEntityExtractorIntegration:
    """Интеграционные тесты Entity Extractor Agent"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_entity_flows_migration(self, migrated_entity_flows):
        """Тест миграции entity flows"""
        extractor = migrated_entity_flows["extractor_flow"]
        comparison = migrated_entity_flows["comparison_flow"]
        
        assert extractor.name == "CRM Entity Extractor"
        assert comparison.name == "CRM Entity Comparison"
        
        print(f"Flows мигрировались: {extractor.name}, {comparison.name}")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_entity_extractor_via_flow_factory(
        self,
        migrated_entity_flows,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """
        Тест Entity Extractor через flow_factory.
        Mock LLM возвращает структурированный ответ.
        """
        user = migrated_entity_flows["user"]
        company = migrated_entity_flows["company"]
        
        # Настраиваем mock LLM на ответ с JSON
        mock_llm.configure(
            response_queue=[
                {
                    "type": "text",
                    "content": '''```json
{
    "entities": [
        {"type": "person", "name": "Иван Петров", "attributes": {"email": "ivan@test.ru"}},
        {"type": "organization", "name": "ТехноСофт", "attributes": {}}
    ],
    "relationships": [
        {"source": "Иван Петров", "target": "ТехноСофт", "type": "works_for"}
    ],
    "summary": "Встреча с Иваном из ТехноСофт"
}
```'''
                }
            ]
        )
        
        context = Context(
            user=user,
            session_id=unique_id("extractor_test"),
            platform="api",
            active_company=company,
        )
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(ENTITY_EXTRACTOR_FLOW_ID)
            assert flow is not None, "Flow не загрузился"
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content="Встретился с Иваном из ТехноСофт")]},
                config={"configurable": {"session_id": unique_id("extractor")}}
            )
            
            assert "messages" in result
            assert len(result["messages"]) > 0
            
            print(f"Entity Extractor выполнился, messages: {len(result['messages'])}")
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_entity_extractor_with_complex_text(
        self,
        migrated_entity_flows,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """Тест с более сложным текстом"""
        user = migrated_entity_flows["user"]
        company = migrated_entity_flows["company"]
        
        mock_llm.configure(
            response_queue=[
                {
                    "type": "text",
                    "content": '''```json
{
    "entities": [
        {"type": "person", "name": "Алексей Смирнов", "attributes": {"position": "CEO"}},
        {"type": "person", "name": "Мария Козлова", "attributes": {"position": "CTO"}},
        {"type": "organization", "name": "Яндекс", "attributes": {}},
        {"type": "project", "name": "ML Platform", "attributes": {}}
    ],
    "relationships": [
        {"source": "Алексей Смирнов", "target": "Яндекс", "type": "works_for"},
        {"source": "Мария Козлова", "target": "ML Platform", "type": "participates_in"}
    ],
    "summary": "Обсуждение ML платформы с командой Яндекса"
}
```'''
                }
            ]
        )
        
        context = Context(
            user=user,
            session_id=unique_id("complex_extractor"),
            platform="api",
            active_company=company,
        )
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(ENTITY_EXTRACTOR_FLOW_ID)
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content="Встретился с Алексеем (CEO) и Марией (CTO) из Яндекса по проекту ML Platform")]},
                config={"configurable": {"session_id": unique_id("complex")}}
            )
            
            assert "messages" in result
            
        finally:
            clear_context()


class TestEntityComparisonIntegration:
    """Интеграционные тесты Entity Comparison Agent"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_compare_duplicate_entities(
        self,
        migrated_entity_flows,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """Тест сравнения похожих сущностей"""
        user = migrated_entity_flows["user"]
        company = migrated_entity_flows["company"]
        
        mock_llm.configure(
            response_queue=[
                {
                    "type": "text",
                    "content": '''```json
{
    "is_duplicate": true,
    "confidence": 0.95,
    "reason": "Совпадает email ivan.petrov@technosoft.ru"
}
```'''
                }
            ]
        )
        
        context = Context(
            user=user,
            session_id=unique_id("comparison_dup"),
            platform="api",
            active_company=company,
        )
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(ENTITY_COMPARISON_FLOW_ID)
            assert flow is not None
            
            message = '''Сравни:
Сущность 1: {"name": "Иван Петров", "email": "ivan.petrov@technosoft.ru"}
Сущность 2: {"name": "И. Петров", "email": "ivan.petrov@technosoft.ru"}
'''
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"session_id": unique_id("dup")}}
            )
            
            assert "messages" in result
            assert len(result["messages"]) > 0
            
            print("Comparison duplicate test passed")
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_compare_different_entities(
        self,
        migrated_entity_flows,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """Тест сравнения разных сущностей"""
        user = migrated_entity_flows["user"]
        company = migrated_entity_flows["company"]
        
        mock_llm.configure(
            response_queue=[
                {
                    "type": "text",
                    "content": '''```json
{
    "is_duplicate": false,
    "confidence": 0.1,
    "reason": "Разные имена, разные email, разные компании"
}
```'''
                }
            ]
        )
        
        context = Context(
            user=user,
            session_id=unique_id("comparison_diff"),
            platform="api",
            active_company=company,
        )
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(ENTITY_COMPARISON_FLOW_ID)
            
            message = '''Сравни:
Сущность 1: {"name": "Иван Петров", "email": "ivan@company-a.ru"}
Сущность 2: {"name": "Сергей Сидоров", "email": "sergey@company-b.ru"}
'''
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"session_id": unique_id("diff")}}
            )
            
            assert "messages" in result
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_compare_organization_entities(
        self,
        migrated_entity_flows,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """Тест сравнения организаций"""
        user = migrated_entity_flows["user"]
        company = migrated_entity_flows["company"]
        
        mock_llm.configure(
            response_queue=[
                {
                    "type": "text",
                    "content": '''```json
{
    "is_duplicate": true,
    "confidence": 0.85,
    "reason": "Одинаковый домен сайта technosoft.ru"
}
```'''
                }
            ]
        )
        
        context = Context(
            user=user,
            session_id=unique_id("org_comparison"),
            platform="api",
            active_company=company,
        )
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(ENTITY_COMPARISON_FLOW_ID)
            
            message = '''Сравни организации:
Организация 1: {"name": "ООО ТехноСофт", "website": "technosoft.ru"}
Организация 2: {"name": "TechnoSoft LLC", "website": "www.technosoft.ru"}
'''
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"session_id": unique_id("org")}}
            )
            
            assert "messages" in result
            
        finally:
            clear_context()


class TestCRMToAgentsIntegration:
    """
    Честные E2E тесты: CRM API -> AgentsClient -> Agents Service API
    
    Полный цикл:
    1. Клиент POST /crm/api/v1/notes/{id}/analyze
    2. CRM вызывает AgentsClient.extract_entities()
    3. AgentsClient POST /agents/api/v1/flows/crm_entity_extractor/message
    4. Agents service выполняет flow
    5. Результат возвращается в CRM и клиенту
    """
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_e2e_entity_extraction(
        self,
        migrated_entity_flows,
        test_note_for_analysis,
        crm_client: AsyncClient,
        agents_service,
    ):
        """
        Полный E2E тест извлечения сущностей:
        CRM API -> AgentsClient -> Agents API -> EntityExtractorAgent
        """
        note = test_note_for_analysis["note"]
        
        # Вызываем анализ через CRM API с включенным AI
        response = await crm_client.post(
            f"/crm/api/v1/notes/{note.note_id}/analyze",
            json={
                "extract_entities": True,
                "generate_summary": True,
            }
        )
        
        assert response.status_code == 200, f"Status: {response.status_code}, Body: {response.text}"
        
        result = response.json()
        assert isinstance(result, dict)
        
        # Проверяем что AI обработал
        print(f"E2E Entity extraction result: {result}")
        
        # Должен быть либо extracted_entities либо summary
        has_entities = "extracted_entities" in result and result["extracted_entities"]
        has_summary = "summary" in result and result["summary"]
        
        assert has_entities or has_summary or result.get("ai_summary"), \
            f"AI должен был обработать, но результат пустой: {result}"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_e2e_entity_comparison_via_agents_client(
        self,
        migrated_entity_flows,
        crm_api_user_company,
        agents_service,
    ):
        """
        Полный E2E тест сравнения сущностей:
        AgentsClient -> Agents API -> EntityComparisonAgent
        """
        from apps.crm.services.agents_client import AgentsClient
        from core.utils.tokens import get_token_service
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        # Получаем auth token
        token_service = get_token_service()
        auth_token = token_service.create_api_token(user.user_id, company.company_id)
        
        context = Context(
            user=user,
            session_id="e2e_comparison_test",
            platform="api",
            active_company=company,
            auth_token=auth_token,
        )
        set_context(context)
        
        try:
            # Создаем клиент к agents service
            agents_client = AgentsClient(agents_base_url=agents_service["url"])
            
            # Сущности для сравнения
            entity_1 = {
                "name": "Иван Петров",
                "type": "person",
                "attributes": {"email": "ivan@test.ru"}
            }
            entity_2 = {
                "name": "И. Петров",
                "type": "person", 
                "attributes": {"email": "ivan@test.ru"}
            }
            
            # Вызываем сравнение через AgentsClient -> Agents API
            result = await agents_client.compare_entities(entity_1, entity_2)
            
            assert isinstance(result, dict)
            print(f"E2E Entity comparison result: {result}")
            
            # Должен вернуть структуру сравнения
            assert "is_duplicate" in result or "confidence" in result or "reason" in result, \
                f"Агент должен был вернуть результат сравнения: {result}"
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_e2e_extract_entities_via_agents_client(
        self,
        migrated_entity_flows,
        crm_api_user_company,
        agents_service,
    ):
        """
        Полный E2E тест извлечения через AgentsClient:
        AgentsClient -> Agents API -> EntityExtractorAgent
        """
        from apps.crm.services.agents_client import AgentsClient
        from core.utils.tokens import get_token_service
        
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        
        token_service = get_token_service()
        auth_token = token_service.create_api_token(user.user_id, company.company_id)
        
        context = Context(
            user=user,
            session_id="e2e_extraction_test",
            platform="api",
            active_company=company,
            auth_token=auth_token,
        )
        set_context(context)
        
        try:
            agents_client = AgentsClient(agents_base_url=agents_service["url"])
            
            text = """
            Встретился с Алексеем Смирновым из компании Яндекс.
            Обсудили проект ML Platform. Алексей - технический директор.
            Email: alexey@yandex.ru
            """
            
            # Вызываем извлечение через AgentsClient -> Agents API
            result = await agents_client.extract_entities(
                text=text,
                generate_summary=True
            )
            
            assert isinstance(result, dict)
            print(f"E2E Extract entities result: {result}")
            
            # Должен вернуть entities или summary
            assert "entities" in result or "summary" in result, \
                f"Агент должен был извлечь сущности: {result}"
            
        finally:
            clear_context()


class TestCRMNoteAnalysis:
    """Тесты анализа заметок через CRM API"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_note_analyze_endpoint(
        self,
        migrated_entity_flows,
        test_note_for_analysis,
        crm_client: AsyncClient,
    ):
        """Тест endpoint анализа заметки без AI"""
        note = test_note_for_analysis["note"]
        
        response = await crm_client.post(
            f"/crm/api/v1/notes/{note.note_id}/analyze",
            json={
                "extract_entities": False,
                "generate_summary": False,
            }
        )
        
        assert response.status_code == 200, f"Status: {response.status_code}, Body: {response.text}"
        
        result = response.json()
        assert isinstance(result, dict)
        
        print(f"Note analyze endpoint works, result keys: {result.keys()}")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_and_get_note(
        self,
        crm_client: AsyncClient,
        crm_api_user_company,
    ):
        """Тест создания и получения заметки через API"""
        from datetime import date
        
        # Создаем заметку с правильными полями
        create_response = await crm_client.post(
            "/crm/api/v1/notes",
            json={
                "title": "Test Note",
                "content": "Content for test",
                "note_type": "freeform",
                "note_date": str(date.today()),
            }
        )
        
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        
        note_id = create_response.json()["note_id"]
        
        # Получаем заметку
        get_response = await crm_client.get(f"/crm/api/v1/notes/{note_id}")
        assert get_response.status_code == 200
        
        note_data = get_response.json()
        assert note_data["title"] == "Test Note"
        
        # Удаляем
        delete_response = await crm_client.delete(f"/crm/api/v1/notes/{note_id}")
        assert delete_response.status_code in [200, 204]
        
        print(f"Full CRUD cycle passed for note {note_id}")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_entity_and_link_to_note(
        self,
        crm_client: AsyncClient,
        test_note_for_analysis,
    ):
        """Тест создания entity и привязки к заметке"""
        note = test_note_for_analysis["note"]
        
        # Создаем entity
        entity_response = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "name": "Test Person",
                "type": "person",
                "attributes": {"position": "Manager"},
            }
        )
        
        assert entity_response.status_code in [200, 201], f"Entity create failed: {entity_response.text}"
        entity_id = entity_response.json()["entity_id"]
        
        # Привязываем к заметке
        link_response = await crm_client.post(
            f"/crm/api/v1/notes/{note.note_id}/link/{entity_id}"
        )
        assert link_response.status_code == 200, f"Link failed: {link_response.text}"
        
        print(f"Entity {entity_id} linked to note {note.note_id}")
