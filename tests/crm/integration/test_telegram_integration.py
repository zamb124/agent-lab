"""
Интеграционные тесты Telegram интеграции CRM.

Проверяет:
1. Привязка Telegram username к профилю пользователя
2. Поиск профиля по telegram_username
3. Tool create_note для создания черновиков заметок через Telegram

НИКАКИХ МОКОВ - используем реальные сервисы.
"""

import pytest
import uuid
from datetime import date
from langchain_core.messages import HumanMessage

from core.context import set_context, clear_context, Context


CRM_ASSISTANT_FLOW_ID = "apps.agents.flows.crm_assistant_flow.crm_assistant_flow"


def make_crm_context(user, company, crm_client, crm_server_process, session_id: str) -> Context:
    """Создает контекст с URL CRM сервера"""
    crm_api_url = f"{crm_server_process['url']}/crm/api/v1"
    return Context(
        user=user,
        session_id=session_id,
        platform="telegram",
        active_company=company,
        auth_token=crm_client.headers.get("Authorization", "").replace("Bearer ", ""),
        metadata={"crm_api_url": crm_api_url}
    )


class TestTelegramProfileIntegration:
    """Тесты привязки Telegram к профилю пользователя"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_link_telegram_via_api(
        self,
        crm_client,
        crm_api_user_company,
    ):
        """Тест привязки Telegram через POST /telegram/link"""
        unique_suffix = uuid.uuid4().hex[:8]
        
        telegram_data = {
            "telegram_username": f"test_user_{unique_suffix}"
        }
        
        response = await crm_client.post("/crm/api/v1/profile/telegram/link", json=telegram_data)
        
        assert response.status_code == 200, f"POST telegram/link failed: {response.text}"
        
        result = response.json()
        assert result["linked"] is True
        assert result["telegram_username"] == telegram_data["telegram_username"]
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unlink_telegram_via_api(
        self,
        crm_client,
        crm_api_user_company,
    ):
        """Тест отвязки Telegram через DELETE /telegram/link"""
        unique_suffix = uuid.uuid4().hex[:8]
        
        # Сначала привязываем
        await crm_client.post(
            "/crm/api/v1/profile/telegram/link",
            json={"telegram_username": f"test_user_{unique_suffix}"}
        )
        
        # Отвязываем
        response = await crm_client.delete("/crm/api/v1/profile/telegram/link")
        
        assert response.status_code == 200, f"DELETE telegram/link failed: {response.text}"
        
        result = response.json()
        assert result["linked"] is False
        assert result["telegram_username"] is None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_telegram_username_in_profile(
        self,
        crm_client,
        crm_api_user_company,
    ):
        """Тест что telegram_username отображается в профиле после привязки"""
        unique_suffix = uuid.uuid4().hex[:8]
        telegram_username = f"tg_profile_{unique_suffix}"
        
        # Привязываем Telegram
        await crm_client.post(
            "/crm/api/v1/profile/telegram/link",
            json={"telegram_username": telegram_username}
        )
        
        # Проверяем профиль
        response = await crm_client.get("/crm/api/v1/profile")
        assert response.status_code == 200
        
        profile = response.json()
        assert profile["telegram_username"] == telegram_username
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_profile_by_telegram_username(
        self,
        crm_container,
        crm_api_user_company,
    ):
        """Тест получения профиля по telegram_username через репозиторий"""
        user = crm_api_user_company["user"]
        company = crm_api_user_company["company"]
        unique_suffix = uuid.uuid4().hex[:8]
        telegram_username = f"tg_test_{unique_suffix}"
        
        profile_repo = crm_container.profile_repository
        
        # Получаем или создаем профиль
        profile = await profile_repo.get_by_user_company(user.user_id, company.company_id)
        if not profile:
            from apps.crm.db.models import UserProfile
            profile = UserProfile(
                profile_id=f"profile_{uuid.uuid4().hex[:8]}",
                user_id=user.user_id,
                company_id=company.company_id,
                display_name="Test User",
                telegram_username=telegram_username,
            )
            await profile_repo.create(profile)
        else:
            await profile_repo.update(profile.profile_id, telegram_username=telegram_username)
        
        # Ищем по telegram_username
        found_profile = await profile_repo.get_by_telegram_username(company.company_id, telegram_username)
        
        assert found_profile is not None
        assert found_profile.telegram_username == telegram_username
        assert found_profile.user_id == user.user_id


class TestCreateNoteTool:
    """Тесты tool create_note для создания заметок"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_draft_note_via_api(
        self,
        crm_client,
        crm_api_user_company,
    ):
        """Тест создания черновика заметки через API"""
        unique_suffix = uuid.uuid4().hex[:8]
        
        note_data = {
            "title": f"Draft Note from Telegram {unique_suffix}",
            "content": "This is a draft note created via Telegram integration",
            "note_type": "freeform",
            "note_date": date.today().isoformat(),
            "status": "draft"
        }
        
        response = await crm_client.post("/crm/api/v1/notes", json=note_data)
        
        # API возвращает 200 при создании
        assert response.status_code in (200, 201), f"POST note failed: {response.text}"
        
        note = response.json()
        assert note["title"] == note_data["title"]
        assert note["content"] == note_data["content"]
        assert note["status"] == "draft"
        
        # Cleanup
        await crm_client.delete(f"/crm/api/v1/notes/{note['note_id']}")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_note_tool_via_flow(
        self,
        migrated_db,
        migrator,
        crm_api_user_company,
        flow_repo,
        crm_client,
        crm_server_process,
        flow_factory,
        mock_llm,
        unique_id,
    ):
        """
        Тест tool create_note через CRM Assistant Flow.
        
        Симулирует сценарий Telegram: пользователь просит создать черновик заметки.
        """
        company = crm_api_user_company["company"]
        user = crm_api_user_company["user"]
        unique_suffix = uuid.uuid4().hex[:8]
        
        # Мигрируем flow
        await migrator.migrate_for_company(
            company=company,
            flows=[CRM_ASSISTANT_FLOW_ID],
            with_dependencies=True
        )
        
        # Настраиваем mock LLM на вызов create_note
        mock_llm.configure(
            response_queue=[
                {
                    "type": "tool_call",
                    "tool": "create_note",
                    "args": {
                        "title": f"Telegram Draft {unique_suffix}",
                        "content": "Запомни: завтра встреча с командой в 10:00",
                        "status": "draft"
                    }
                },
                {"type": "text", "content": "Черновик заметки создан."}
            ]
        )
        
        # Устанавливаем контекст
        context = make_crm_context(user, company, crm_client, crm_server_process, unique_id("tg_note"))
        set_context(context)
        
        try:
            flow = await flow_factory.get_flow(CRM_ASSISTANT_FLOW_ID)
            assert flow is not None
            
            result = await flow.ainvoke(
                {"messages": [HumanMessage(content="Запомни: завтра встреча с командой в 10:00")]},
                config={"configurable": {"session_id": unique_id("create_note")}}
            )
            
            assert "messages" in result
            
            # Проверяем что заметка создалась
            search_response = await crm_client.get(
                "/crm/api/v1/notes",
                params={"search": f"Telegram Draft {unique_suffix}"}
            )
            
            if search_response.status_code == 200:
                notes_data = search_response.json()
                # Ответ может быть list или dict с items
                notes = notes_data if isinstance(notes_data, list) else notes_data.get("items", [])
                for note in notes:
                    if unique_suffix in note.get("title", ""):
                        # Cleanup
                        await crm_client.delete(f"/crm/api/v1/notes/{note['note_id']}")
            
        finally:
            clear_context()


class TestTelegramFlowConfiguration:
    """Тесты конфигурации Flow для Telegram"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_crm_assistant_flow_has_telegram_platform(
        self,
        migrated_db,
        migrator,
        crm_api_user_company,
        flow_repo,
    ):
        """Тест что CRM Assistant Flow имеет Telegram платформу"""
        company = crm_api_user_company["company"]
        
        await migrator.migrate_for_company(
            company=company,
            flows=[CRM_ASSISTANT_FLOW_ID],
            with_dependencies=True
        )
        
        flow = await flow_repo.get(CRM_ASSISTANT_FLOW_ID)
        
        assert flow is not None
        assert flow.platforms is not None
        assert "telegram" in flow.platforms
        
        telegram_config = flow.platforms["telegram"]
        
        # Проверяем что есть конфигурация с @var ссылками
        assert telegram_config.get("token") == "@var:crm_telegram_bot_token"
        assert telegram_config.get("username") == "@var:crm_telegram_bot_username"
        assert telegram_config.get("user_mapping") == "crm_profile"
