"""
Integration тесты для API настроек.

Тесты БЕЗ моков - проверяем реальные HTTP запросы с реальной БД.
Проверяем управление настройками компании, безопасностью и интеграциями.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSettingsAPI:
    """Тесты для API настроек"""

    async def test_get_company_settings_success(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container,
        unique_id: str,
    ):
        """Получение профиля компании и снимка AI-провайдеров (раздельные роутеры)."""
        from core.ai.models import AIModelRecord
        from core.ai.providers import AICapability

        openrouter_model_id = f"unit/openrouter-settings-{unique_id}"
        groq_model_id = f"unit-groq-settings-{unique_id}"
        vision_model_id = f"unit/vision-settings-{unique_id}"
        image_model_id = f"unit/image-settings-{unique_id}"
        embedding_model_id = f"unit/embedding-settings-{unique_id}"
        rerank_model_id = f"unit/rerank-settings-{unique_id}"
        await frontend_container.ai_model_catalog_repository.set(
            AIModelRecord(
                model_id=openrouter_model_id,
                provider="openrouter",
                capabilities=(
                    AICapability.LLM_CHAT,
                    AICapability.LLM_SUMMARIZE,
                    AICapability.LLM_FORMAT_MARKDOWN,
                    AICapability.LLM_CODEGEN,
                ),
            )
        )
        await frontend_container.ai_model_catalog_repository.set(
            AIModelRecord(
                model_id=groq_model_id,
                provider="groq",
                capabilities=(
                    AICapability.LLM_CHAT,
                    AICapability.LLM_SUMMARIZE,
                    AICapability.LLM_FORMAT_MARKDOWN,
                    AICapability.LLM_CODEGEN,
                ),
            )
        )
        await frontend_container.ai_model_catalog_repository.set(
            AIModelRecord(
                model_id=vision_model_id,
                provider="openrouter",
                capabilities=(AICapability.LLM_VISION,),
                input_modalities=("text", "image"),
                output_modalities=("text",),
            )
        )
        await frontend_container.ai_model_catalog_repository.set(
            AIModelRecord(
                model_id=image_model_id,
                provider="openrouter",
                capabilities=(AICapability.IMAGE_GEN,),
                input_modalities=("text",),
                output_modalities=("image",),
            )
        )
        await frontend_container.ai_model_catalog_repository.set(
            AIModelRecord(
                model_id=embedding_model_id,
                provider="provider_litserve",
                capabilities=(AICapability.EMBEDDING,),
                input_modalities=("text",),
                output_modalities=("embeddings",),
                native_dimension=1024,
                storage_dimension=1024,
                metadata_status="verified",
            )
        )
        await frontend_container.ai_model_catalog_repository.set(
            AIModelRecord(
                model_id=rerank_model_id,
                provider="openrouter",
                capabilities=(AICapability.RERANK,),
                input_modalities=("text",),
                output_modalities=("scores",),
            )
        )

        response = await frontend_client.get(
            "/frontend/api/settings/company",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "company_id" in data
        assert "name" in data
        assert "monthly_budget" in data

        ai = await frontend_client.get(
            "/frontend/api/settings/ai-providers",
            headers=auth_headers,
        )
        assert ai.status_code == 200
        body = ai.json()
        caps = {item["capability"]: item for item in body["capabilities"]}
        assert caps["embedding"]["kind"] == "embedding"
        assert caps["rerank"]["kind"] == "rerank"
        summarize = caps["llm_summarize"]
        assert summarize["kind"] == "llm"
        assert "llm_summarize" in body["catalog"]
        assert "embedding" in body["catalog"]
        prov_items = body["catalog"]["llm_summarize"]
        from core.ai.providers import (
            HUMANITEC_LLM_PROVIDER,
            HUMANITEC_LLMS_DISPLAY_LABEL,
            PLATFORM_LLM_PROVIDER_ORDER,
        )

        provider_values = [item["value"] for item in prov_items]
        assert provider_values[: len(PLATFORM_LLM_PROVIDER_ORDER)] == list(
            PLATFORM_LLM_PROVIDER_ORDER
        )
        humanitec_item = next(
            item for item in prov_items if item["value"] == HUMANITEC_LLM_PROVIDER
        )
        assert humanitec_item["kind"] == "virtual"
        assert humanitec_item["label"] == HUMANITEC_LLMS_DISPLAY_LABEL
        assert humanitec_item["models"][0] == {
            "value": "auto",
            "label": "auto",
            "kind": "auto",
        }
        openrouter_item = next(item for item in prov_items if item["value"] == "openrouter")
        assert {"value": openrouter_model_id, "label": openrouter_model_id, "kind": "provider_model"} in openrouter_item["models"]
        assert {"value": vision_model_id, "label": vision_model_id, "kind": "provider_model"} not in openrouter_item["models"]
        groq_item = next(item for item in prov_items if item["value"] == "groq")
        assert {"value": groq_model_id, "label": groq_model_id, "kind": "provider_model"} in groq_item["models"]
        assert any(p.get("kind") == "platform" for p in prov_items)
        vision_providers = body["catalog"]["llm_vision"]
        vision_openrouter = next(item for item in vision_providers if item["value"] == "openrouter")
        assert {"value": vision_model_id, "label": vision_model_id, "kind": "provider_model"} in vision_openrouter["models"]
        assert {"value": openrouter_model_id, "label": openrouter_model_id, "kind": "provider_model"} not in vision_openrouter["models"]
        image_providers = body["catalog"]["image_gen"]
        image_openrouter = next(item for item in image_providers if item["value"] == "openrouter")
        assert {"value": image_model_id, "label": image_model_id, "kind": "provider_model"} in image_openrouter["models"]
        rerank_providers = body["catalog"]["rerank"]
        rerank_openrouter = next(item for item in rerank_providers if item["value"] == "openrouter")
        assert {"value": rerank_model_id, "label": rerank_model_id, "kind": "provider_model"} in rerank_openrouter["models"]
        embedding_providers = body["catalog"]["embedding"]
        embedding_provider_values = {item["value"] for item in embedding_providers}
        assert "provider_litserve" in embedding_provider_values
        embedding_litserve = next(
            item for item in embedding_providers if item["value"] == "provider_litserve"
        )
        assert embedding_litserve["label"] == "Humanitec"
        assert {
            "value": embedding_model_id,
            "label": embedding_model_id,
            "kind": "embedding_model",
            "native_dimension": 1024,
            "dimension": 1024,
            "mrl_output_dimension": None,
            "metadata_status": "verified",
            "source": "provider_catalog",
        } in embedding_litserve["models"]
        from core.config import get_settings

        settings = get_settings()
        voice_tts = body["catalog"]["voice_tts"]
        voice_tts_values = {item["value"] for item in voice_tts}
        assert "litserve" in voice_tts_values
        assert "cloud_ru" in voice_tts_values
        humanitec_voice_tts = next(item for item in voice_tts if item["value"] == "litserve")
        assert humanitec_voice_tts["label"] == "Humanitec Voice"
        assert humanitec_voice_tts["byok_allowed"] is False
        assert {
            "value": settings.provider_litserve.infra.tts_default_api_model_id,
            "label": settings.provider_litserve.infra.tts_default_api_model_id,
            "kind": "voice_model",
        } in humanitec_voice_tts["models"]
        cloud_ru_tts = next(item for item in voice_tts if item["value"] == "cloud_ru")
        assert {
            "value": "openai/tts-1",
            "label": "openai/tts-1",
            "kind": "voice_model",
        } in cloud_ru_tts["models"]

        voice_vad = body["catalog"]["voice_vad"]
        assert [item["value"] for item in voice_vad] == ["litserve"]
        humanitec_voice_vad = voice_vad[0]
        assert humanitec_voice_vad["label"] == "Humanitec Voice"
        assert humanitec_voice_vad["byok_allowed"] is False
        assert {
            "value": settings.provider_litserve.infra.vad_default_api_model_id,
            "label": settings.provider_litserve.infra.vad_default_api_model_id,
            "kind": "voice_model",
        } in humanitec_voice_vad["models"]
        assert body["llm_context"]["configured"] is False
        assert body["llm_context"]["config"] == {}
        assert body["llm_context"]["resolved"]["profile"] == "off"
        assert body["llm_context"]["resolved"]["mode"] == "off"
        assert body["llm_context"]["resolved"]["retrieval"]["mode"] == "off"
        assert body["llm_context"]["resolved"]["budget"]["max_input_tokens"] > 0
        assert "standard" in body["llm_context"]["profiles"]
        assert "large" in body["llm_context"]["budgets"]

    async def test_update_ai_provider_llm_context_default(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container
    ):
        """Company default контекстного слоя сохраняется в реальной БД и снимается DELETE."""
        from core.ai.company_settings import CompanyAIProviders
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id

        payload = {
            "profile": "agent",
            "memory": "session",
            "retrieval": {"mode": "hybrid", "top_k": 24, "rerank": True},
            "budget": "large",
            "cache": "provider_hints",
        }
        response = await frontend_client.put(
            "/frontend/api/settings/ai-providers/llm-context",
            headers=auth_headers,
            json=payload,
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        company = await frontend_container.company_repository.get(company_id)
        aip = CompanyAIProviders.from_metadata(company.metadata or {})
        assert aip.llm_context is not None
        assert aip.llm_context.profile == "agent"
        assert aip.llm_context.retrieval is not None
        assert aip.llm_context.retrieval.top_k == 24

        snapshot = await frontend_client.get(
            "/frontend/api/settings/ai-providers",
            headers=auth_headers,
        )
        assert snapshot.status_code == 200
        body = snapshot.json()["llm_context"]
        assert body["configured"] is True
        assert body["config"]["profile"] == "agent"
        assert body["config"]["retrieval"]["rerank"] is True
        assert body["resolved"]["profile"] == "agent"
        assert body["resolved"]["retrieval"]["top_k"] == 24

        cleared = await frontend_client.delete(
            "/frontend/api/settings/ai-providers/llm-context",
            headers=auth_headers,
        )
        assert cleared.status_code == 200
        company = await frontend_container.company_repository.get(company_id)
        aip = CompanyAIProviders.from_metadata(company.metadata or {})
        assert aip.llm_context is None

    async def test_update_ai_provider_llm_context_rejects_unknown_profile(
        self,
        frontend_client: AsyncClient,
        auth_headers,
    ):
        """Company default валидируется против platform profiles сразу в Settings API."""
        response = await frontend_client.put(
            "/frontend/api/settings/ai-providers/llm-context",
            headers=auth_headers,
            json={"profile": "missing-profile"},
        )

        assert response.status_code == 400
        assert "missing-profile" in response.json()["detail"]

    async def test_ai_provider_platform_llm_requires_explicit_model(
        self,
        frontend_client: AsyncClient,
        auth_headers,
    ):
        """Обычный provider не принимает implicit auto: auto живёт только в Humanitec LLMs."""
        response = await frontend_client.put(
            "/frontend/api/settings/ai-providers/llm_chat",
            headers=auth_headers,
            json={"provider": "openrouter"},
        )

        assert response.status_code == 400
        assert "model обязателен" in response.json()["detail"]

    async def test_ai_provider_embedding_saves_catalog_model_with_dimension(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container,
    ):
        """Embedding override stores provider, model and storage dimension from the shared catalog."""
        from core.ai.company_settings import CompanyAIProviders
        from core.ai.models import AIModelRecord
        from core.ai.providers import AICapability
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        model_id = "qwen/qwen3-embedding-0.6b"
        await frontend_container.ai_model_catalog_repository.set(
            AIModelRecord(
                model_id=model_id,
                provider="provider_litserve",
                capabilities=(AICapability.EMBEDDING,),
                native_dimension=1024,
                storage_dimension=1024,
                metadata_status="verified",
            )
        )

        response = await frontend_client.put(
            "/frontend/api/settings/ai-providers/embedding",
            headers=auth_headers,
            json={
                "provider": "provider_litserve",
                "model": model_id,
                "dimension": 1024,
            },
        )

        assert response.status_code == 200
        company = await frontend_container.company_repository.get(company_id)
        aip = CompanyAIProviders.from_metadata(company.metadata or {})
        assert aip.embedding is not None
        assert aip.embedding.provider == "provider_litserve"
        assert aip.embedding.model == model_id
        assert aip.embedding.dimension == 1024
        assert aip.embedding.mrl_output_dimension is None

    async def test_ai_provider_embedding_rejects_dimension_mismatch(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container,
    ):
        """Embedding models cannot be saved with dimensions that differ from pgvector storage policy."""
        from core.ai.models import AIModelRecord
        from core.ai.providers import AICapability

        model_id = "qwen/qwen3-embedding-0.6b"
        await frontend_container.ai_model_catalog_repository.set(
            AIModelRecord(
                model_id=model_id,
                provider="provider_litserve",
                capabilities=(AICapability.EMBEDDING,),
                native_dimension=1024,
                storage_dimension=1024,
                metadata_status="verified",
            )
        )
        response = await frontend_client.put(
            "/frontend/api/settings/ai-providers/embedding",
            headers=auth_headers,
            json={
                "provider": "provider_litserve",
                "model": model_id,
                "dimension": 768,
            },
        )

        assert response.status_code == 400
        assert "dimension=768" in response.json()["detail"]

    async def test_ai_provider_rerank_saves_provider_model_override(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container,
    ):
        """Rerank override is a provider/model capability override, not a policy string."""
        from core.ai.company_settings import CompanyAIProviders
        from core.ai.models import AIModelRecord
        from core.ai.providers import AICapability
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        model_id = "unit/rerank-model"
        await frontend_container.ai_model_catalog_repository.set(
            AIModelRecord(
                model_id=model_id,
                provider="openrouter",
                capabilities=(AICapability.RERANK,),
                output_modalities=("scores",),
            )
        )

        response = await frontend_client.put(
            "/frontend/api/settings/ai-providers/rerank",
            headers=auth_headers,
            json={
                "provider": "openrouter",
                "model": model_id,
            },
        )

        assert response.status_code == 200
        company = await frontend_container.company_repository.get(company_id)
        aip = CompanyAIProviders.from_metadata(company.metadata or {})
        assert aip.rerank is not None
        assert aip.rerank.provider == "openrouter"
        assert aip.rerank.model == model_id

    async def test_ai_provider_catalog_exposes_custom_provider_model_options(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        unique_id: str,
    ):
        """Custom provider model_by_capability is part of the same backend catalog payload."""
        provider_id = f"custom_{unique_id}"
        model_id = f"custom-model-{unique_id}"

        created = await frontend_client.post(
            "/frontend/api/settings/ai-providers/custom",
            headers=auth_headers,
            json={
                "id": provider_id,
                "label": "Custom Chat",
                "base_url": "https://custom-ai.test/v1",
                "api_key": "test-key",
                "capabilities": ["llm_chat"],
                "model_by_capability": {"llm_chat": model_id},
            },
        )
        assert created.status_code == 200

        snapshot = await frontend_client.get(
            "/frontend/api/settings/ai-providers",
            headers=auth_headers,
        )
        assert snapshot.status_code == 200
        body = snapshot.json()
        chat_catalog = body["catalog"]["llm_chat"]
        custom_item = next(item for item in chat_catalog if item["value"] == f"custom:{provider_id}")
        assert custom_item["models"] == [
            {"value": model_id, "label": model_id, "kind": "custom_model"}
        ]

    async def test_ai_providers_accept_user_company_admin_role_when_company_members_stale(
        self,
        frontend_client: AsyncClient,
        frontend_container,
    ):
        """AI providers не падает 403, если admin роль есть в user.companies, но company.members устарел."""
        import uuid

        from core.models.identity_models import Company, User
        from core.utils.tokens import get_token_service

        company_id = f"ai_roles_{uuid.uuid4().hex[:8]}"
        user_id = f"ai_admin_{uuid.uuid4().hex[:8]}"
        company = Company(
            company_id=company_id,
            name="AI Roles Company",
            owner_user_id="other_user",
            members={},
        )
        user = User(
            user_id=user_id,
            name="AI Admin",
            groups=["user"],
            companies={company_id: ["admin"]},
            active_company_id=company_id,
        )
        await frontend_container.company_repository.set(company)
        await frontend_container.user_repository.set(user)

        token = get_token_service().create_token(user_id, company_id=company_id)
        headers = {"Authorization": f"Bearer {token}"}

        snapshot = await frontend_client.get(
            "/frontend/api/settings/ai-providers",
            headers=headers,
        )
        assert snapshot.status_code == 200

        updated = await frontend_client.put(
            "/frontend/api/settings/ai-providers/llm-context",
            headers=headers,
            json={"profile": "standard"},
        )
        assert updated.status_code == 200

    async def test_search_providers_company_key_crud(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container,
    ):
        """Search provider BYOK сохраняется за компанией, шифруется и отдаётся в UI только маской."""
        from core.ai.company_settings import decrypt_secret
        from core.company_search import COMPANY_SEARCH_METADATA_KEY, CompanySearchProviders
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id

        snapshot = await frontend_client.get(
            "/frontend/api/settings/search-providers",
            headers=auth_headers,
        )
        assert snapshot.status_code == 200
        body = snapshot.json()
        assert body["provider_order"] == ["tinyfish", "linkup", "serper", "tavily"]
        assert [item["id"] for item in body["providers"]] == ["tinyfish", "linkup", "serper", "tavily"]

        response = await frontend_client.put(
            "/frontend/api/settings/search-providers/tavily",
            headers=auth_headers,
            json={
                "enabled": True,
                "credential_source": "company",
                "api_key": "tvly-company-secret",
                "base_url": "https://api.tavily.com",
                "timeout_seconds": 14,
                "search_depth": "advanced",
                "topic": "news",
                "include_answer": True,
            },
        )
        assert response.status_code == 200

        company = await frontend_container.company_repository.get(company_id)
        assert company is not None
        settings = CompanySearchProviders.from_metadata(company.metadata)
        assert settings.tavily.credential_source == "company"
        assert settings.tavily.api_key_encrypted is not None
        assert decrypt_secret(settings.tavily.api_key_encrypted) == "tvly-company-secret"
        assert settings.tavily.search_depth == "advanced"
        assert settings.tavily.topic == "news"
        assert settings.tavily.include_answer is True

        changed = await frontend_client.get(
            "/frontend/api/settings/search-providers",
            headers=auth_headers,
        )
        assert changed.status_code == 200
        tavily = next(item for item in changed.json()["providers"] if item["id"] == "tavily")
        assert tavily["credential_source"] == "company"
        assert tavily["configured"] is True
        assert tavily["key_masked"] == "**** cret"

        reset = await frontend_client.delete(
            "/frontend/api/settings/search-providers/tavily",
            headers=auth_headers,
        )
        assert reset.status_code == 200
        company = await frontend_container.company_repository.get(company_id)
        assert company is not None
        assert COMPANY_SEARCH_METADATA_KEY not in company.metadata

    async def test_search_provider_order_is_company_scoped(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container,
    ):
        """Порядок Search providers хранится в metadata активной компании."""
        from core.company_search import CompanySearchProviders
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id

        response = await frontend_client.put(
            "/frontend/api/settings/search-providers/order",
            headers=auth_headers,
            json={"provider_order": ["tavily", "serper"]},
        )
        assert response.status_code == 200

        company = await frontend_container.company_repository.get(company_id)
        assert company is not None
        settings = CompanySearchProviders.from_metadata(company.metadata)
        assert settings.provider_order == ["tavily", "serper", "tinyfish", "linkup"]

        snapshot = await frontend_client.get(
            "/frontend/api/settings/search-providers",
            headers=auth_headers,
        )
        assert snapshot.status_code == 200
        assert snapshot.json()["provider_order"] == ["tavily", "serper", "tinyfish", "linkup"]

    async def test_get_company_settings_unauthorized(self, frontend_client: AsyncClient):
        """Попытка получить настройки без авторизации"""
        response = await frontend_client.get("/frontend/api/settings/company")

        assert response.status_code == 401

    async def test_update_company_settings_name(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container
    ):
        """Обновление названия компании"""
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id

        new_name = "Updated Company Name"

        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={"name": new_name}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["company"]["name"] == new_name

        # Проверяем что изменение сохранилось в БД
        company = await frontend_container.company_repository.get(company_id)
        assert company.name == new_name

    async def test_update_company_settings_monthly_budget(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container
    ):
        """Обновление месячного лимита"""
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id

        new_budget = 5000.0

        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={"monthly_budget": new_budget}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["company"]["monthly_budget"] == new_budget

        # Проверяем БД
        company = await frontend_container.company_repository.get(company_id)
        assert company.monthly_budget == new_budget

    async def test_update_company_settings_negative_budget(
        self,
        frontend_client: AsyncClient,
        auth_headers
    ):
        """Попытка установить отрицательный лимит"""
        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={"monthly_budget": -1000.0}
        )

        assert response.status_code == 400
        assert "отрицательным" in response.json()["detail"].lower()

    async def test_update_company_settings_metadata(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container
    ):
        """Обновление метаданных компании"""
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id

        metadata = {
            "custom_field": "value",
            "feature_flags": {"new_ui": True}
        }

        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={"metadata": metadata}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Проверяем БД
        company = await frontend_container.company_repository.get(company_id)
        assert "custom_field" in company.metadata
        assert company.metadata["custom_field"] == "value"

    async def test_update_company_settings_as_viewer_forbidden(
        self,
        frontend_client: AsyncClient,
        frontend_container
    ):
        """Попытка обновить настройки с ролью viewer"""
        import uuid

        from core.models.identity_models import Company, User
        from core.utils.tokens import get_token_service

        company_id = f"test_company_{uuid.uuid4().hex[:8]}"
        company = Company(
            company_id=company_id,
            name="Test Company",
            owner_id="owner_user",
            members={"viewer_user": ["viewer"]}
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id="viewer_user",
            name="Viewer User",
            companies={company_id: ["viewer"]},
            active_company_id=company_id
        )
        await frontend_container.user_repository.set(user)

        token_service = get_token_service()
        token = token_service.create_token("viewer_user", company_id=company_id)

        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "New Name"}
        )

        assert response.status_code == 403

    async def test_settings_isolation_between_companies(
        self,
        frontend_client: AsyncClient,
        frontend_container
    ):
        """Проверка изоляции настроек между компаниями"""
        import uuid

        from core.models.identity_models import Company, User
        from core.utils.tokens import get_token_service

        # Создаем две компании с разными настройками
        company1_id = f"company1_{uuid.uuid4().hex[:8]}"
        company2_id = f"company2_{uuid.uuid4().hex[:8]}"

        company1 = Company(
            company_id=company1_id,
            name="Company 1",
            subdomain="company1",
            owner_id="user1",
            members={"user1": ["owner"]},
            monthly_budget=1000.0,
            metadata={"feature": "value1"}
        )
        company2 = Company(
            company_id=company2_id,
            name="Company 2",
            subdomain="company2",
            owner_id="user2",
            members={"user2": ["owner"]},
            monthly_budget=5000.0,
            metadata={"feature": "value2"}
        )

        await frontend_container.company_repository.set(company1)
        await frontend_container.company_repository.set(company2)

        user1 = User(
            user_id="user1",
            name="User 1",
            companies={company1_id: ["owner"]},
            active_company_id=company1_id
        )
        user2 = User(
            user_id="user2",
            name="User 2",
            companies={company2_id: ["owner"]},
            active_company_id=company2_id
        )

        await frontend_container.user_repository.set(user1)
        await frontend_container.user_repository.set(user2)

        token_service = get_token_service()
        token1 = token_service.create_token("user1", company_id=company1_id)
        token2 = token_service.create_token("user2", company_id=company2_id)

        # Получаем настройки для каждой компании
        response1 = await frontend_client.get(
            "/frontend/api/settings/company",
            headers={"Authorization": f"Bearer {token1}"}
        )
        response2 = await frontend_client.get(
            "/frontend/api/settings/company",
            headers={"Authorization": f"Bearer {token2}"}
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Данные должны быть разными
        assert data1["name"] == "Company 1"
        assert data2["name"] == "Company 2"
        assert data1["subdomain"] == "company1"
        assert data2["subdomain"] == "company2"
        assert data1["monthly_budget"] == 1000.0
        assert data2["monthly_budget"] == 5000.0
        assert data1["metadata"]["feature"] == "value1"
        assert data2["metadata"]["feature"] == "value2"

    async def test_update_all_settings_together(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container
    ):
        """Обновление всех настроек одновременно"""
        from core.utils.tokens import get_token_service

        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id

        response = await frontend_client.patch(
            "/frontend/api/settings/company",
            headers=auth_headers,
            json={
                "name": "Fully Updated Company",
                "monthly_budget": 3000.0,
                "metadata": {"updated": True}
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Проверяем БД
        company = await frontend_container.company_repository.get(company_id)
        assert company.name == "Fully Updated Company"
        assert company.monthly_budget == 3000.0
        assert "updated" in company.metadata
        assert company.metadata["updated"] is True
