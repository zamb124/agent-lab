"""
Тесты биллинга для Embedding операций.

Проверяет что после генерации embeddings создаются usage записи.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.models.billing_models import UsageType, UsageRecord
from core.rag.services.embedding_service import EmbeddingService
from core.context import set_context, clear_context, Context


class TestEmbeddingBilling:
    """Тесты биллинга для EmbeddingService"""
    
    @pytest.mark.asyncio
    async def test_embedding_cost_calculation(self):
        """Тест расчёта стоимости embedding"""
        service = EmbeddingService(
            api_key="test-key",
            models=["openai/text-embedding-3-small"],
            cost_per_1m_tokens=5.0,
            platform_markup=1.1,
        )
        
        # 1000 токенов
        cost = service.calculate_cost(1000)
        expected = (1000 / 1_000_000) * 5.0 * 1.1
        assert abs(cost - expected) < 0.0001, f"Expected {expected}, got {cost}"
        
        # 1M токенов
        cost = service.calculate_cost(1_000_000)
        expected = 5.0 * 1.1
        assert abs(cost - expected) < 0.0001, f"Expected {expected}, got {cost}"
    
    @pytest.mark.asyncio
    async def test_token_counting(self):
        """Тест подсчёта токенов"""
        service = EmbeddingService(
            api_key="test-key",
            models=["openai/text-embedding-3-small"],
        )
        
        texts = ["Hello world", "This is a test"]
        tokens = service.count_tokens(texts)
        
        assert tokens > 0
        assert isinstance(tokens, int)
    
    @pytest.mark.asyncio
    async def test_embedding_records_usage(
        self, 
        billing_service, 
        usage_repo,
        test_user, 
        test_company,
        save_test_company,
        unique_id,
    ):
        """Тест что embedding записывает usage"""
        from core.config import get_settings
        
        settings = get_settings()
        chromadb_cfg = settings.rag.providers.get("chromadb")
        emb_cfg = settings.rag.embedding
        
        if not chromadb_cfg or not chromadb_cfg.embedding_api_key:
            pytest.skip("ChromaDB не настроен")
        
        # Настраиваем баланс компании
        test_company.balance = 1000.0
        
        # Устанавливаем контекст
        context = Context(
            user=test_user,
            platform="test",
            active_company=test_company,
            session_id=unique_id("emb_billing"),
        )
        set_context(context)
        
        try:
            # Создаём EmbeddingService с billing
            service = EmbeddingService(
                api_key=chromadb_cfg.embedding_api_key,
                models=emb_cfg.get_preferred_models(),
                cost_per_1m_tokens=chromadb_cfg.embedding_cost_per_1m_tokens,
                platform_markup=chromadb_cfg.embedding_platform_markup,
                billing_service=billing_service,
            )
            
            # Генерируем embeddings
            texts = ["Test embedding billing", "Second test text for billing"]
            result = await service.generate_embeddings(texts)
            
            assert len(result) == 2
            
            # Проверяем что usage записан
            all_usage = await usage_repo.list_all(limit=1000)
            embedding_usage = [
                u for u in all_usage 
                if u.usage_type == UsageType.EMBEDDING_REQUEST
                and u.company_id == test_company.company_id
            ]
            
            assert len(embedding_usage) > 0, "Usage записи для embedding не найдены"
            
            # Проверяем структуру записи
            usage_record = embedding_usage[-1]  # Последняя запись
            assert usage_record.user_id == test_user.user_id
            assert usage_record.company_id == test_company.company_id
            assert usage_record.cost > 0
            assert usage_record.quantity > 0  # токены
            assert "embedding:" in usage_record.resource_name
            assert "model" in usage_record.metadata
            assert "tokens" in usage_record.metadata
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_embedding_billing_updates_company_balance(
        self,
        billing_service,
        usage_repo,
        company_repo,
        test_user,
        test_company,
        save_test_company,
        unique_id,
    ):
        """Тест что embedding billing обновляет баланс компании"""
        from core.config import get_settings
        
        settings = get_settings()
        chromadb_cfg = settings.rag.providers.get("chromadb")
        emb_cfg = settings.rag.embedding
        
        if not chromadb_cfg or not chromadb_cfg.embedding_api_key:
            pytest.skip("ChromaDB не настроен")
        
        # Устанавливаем начальный баланс
        initial_balance = 1000.0
        test_company.balance = initial_balance
        test_company.current_month_spent = 0.0
        await company_repo.set(test_company)
        
        # Устанавливаем контекст
        context = Context(
            user=test_user,
            platform="test",
            active_company=test_company,
            session_id=unique_id("emb_balance"),
        )
        set_context(context)
        
        try:
            service = EmbeddingService(
                api_key=chromadb_cfg.embedding_api_key,
                models=emb_cfg.get_preferred_models(),
                cost_per_1m_tokens=chromadb_cfg.embedding_cost_per_1m_tokens,
                platform_markup=chromadb_cfg.embedding_platform_markup,
                billing_service=billing_service,
            )
            
            # Генерируем embeddings
            texts = ["Billing balance test"] * 10  # 10 текстов для заметной стоимости
            await service.generate_embeddings(texts)
            
            # Проверяем обновление баланса
            updated_company = await company_repo.get(test_company.company_id)
            
            assert updated_company.balance < initial_balance, \
                f"Баланс должен уменьшиться: {initial_balance} -> {updated_company.balance}"
            assert updated_company.current_month_spent > 0, \
                f"current_month_spent должен увеличиться: {updated_company.current_month_spent}"
            
        finally:
            clear_context()
    
    @pytest.mark.asyncio
    async def test_embedding_no_billing_without_context(self, usage_repo, unique_id):
        """Тест что без контекста billing не записывается"""
        from core.config import get_settings
        from unittest.mock import AsyncMock
        
        settings = get_settings()
        chromadb_cfg = settings.rag.providers.get("chromadb")
        emb_cfg = settings.rag.embedding
        
        if not chromadb_cfg or not chromadb_cfg.embedding_api_key:
            pytest.skip("ChromaDB не настроен")
        
        # Очищаем контекст
        clear_context()
        
        # Создаём mock billing service
        mock_billing = AsyncMock()
        
        service = EmbeddingService(
            api_key=chromadb_cfg.embedding_api_key,
            models=emb_cfg.get_preferred_models(),
            cost_per_1m_tokens=chromadb_cfg.embedding_cost_per_1m_tokens,
            platform_markup=chromadb_cfg.embedding_platform_markup,
            billing_service=mock_billing,
        )
        
        # Генерируем embeddings без контекста
        texts = ["Test without context"]
        result = await service.generate_embeddings(texts)
        
        assert len(result) == 1
        
        # record_usage не должен вызываться без контекста
        mock_billing.record_usage.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_embedding_metadata_structure(
        self,
        billing_service,
        usage_repo,
        test_user,
        test_company,
        save_test_company,
        unique_id,
    ):
        """Тест структуры metadata в usage записи"""
        from core.config import get_settings
        
        settings = get_settings()
        chromadb_cfg = settings.rag.providers.get("chromadb")
        emb_cfg = settings.rag.embedding
        
        if not chromadb_cfg or not chromadb_cfg.embedding_api_key:
            pytest.skip("ChromaDB не настроен")
        
        test_company.balance = 1000.0
        
        context = Context(
            user=test_user,
            platform="test",
            active_company=test_company,
            session_id=unique_id("emb_meta"),
        )
        set_context(context)
        
        try:
            service = EmbeddingService(
                api_key=chromadb_cfg.embedding_api_key,
                models=emb_cfg.get_preferred_models(),
                cost_per_1m_tokens=chromadb_cfg.embedding_cost_per_1m_tokens,
                platform_markup=chromadb_cfg.embedding_platform_markup,
                billing_service=billing_service,
            )
            
            texts = ["Metadata structure test"]
            await service.generate_embeddings(texts)
            
            # Получаем записи
            all_usage = await usage_repo.list_all(limit=1000)
            embedding_usage = [
                u for u in all_usage
                if u.usage_type == UsageType.EMBEDDING_REQUEST
                and u.company_id == test_company.company_id
            ]
            
            assert len(embedding_usage) > 0
            
            metadata = embedding_usage[-1].metadata
            
            # Проверяем наличие всех полей в metadata
            assert "model" in metadata
            assert "tokens" in metadata
            assert "cost_per_1m_tokens" in metadata
            assert "platform_markup" in metadata
            
            # Проверяем значения
            assert metadata["cost_per_1m_tokens"] == chromadb_cfg.embedding_cost_per_1m_tokens
            assert metadata["platform_markup"] == chromadb_cfg.embedding_platform_markup
            assert metadata["tokens"] > 0
            
        finally:
            clear_context()

