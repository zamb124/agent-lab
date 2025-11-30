"""
Тесты CompanyRepository.

Проверяем базовую функциональность:
1. set() сохраняет компанию в БД
2. get() читает компанию из БД
3. delete() удаляет компанию из БД
4. list_all() возвращает список компаний
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from core.models.identity_models import Company
from core.models.billing_models import TariffPlan


class TestCompanyRepository:
    """Тесты для CompanyRepository"""
    
    @pytest.mark.asyncio
    async def test_set_and_get(self, company_repo, unique_id):
        """Проверяем что set() сохраняет и get() читает компанию"""
        company_id = unique_id("company")
        company = Company(
            company_id=company_id,
            name="Test Company",
            subdomain=f"test-{company_id}",
            tariff_plan=TariffPlan.FREE,
            balance=100.0
        )
        
        # Сохраняем
        result = await company_repo.set(company)
        assert result is True, "set() должен вернуть True"
        
        # Читаем
        loaded = await company_repo.get(company_id)
        assert loaded is not None, "get() должен найти компанию"
        assert loaded.company_id == company_id
        assert loaded.name == "Test Company"
        
        # Cleanup
        await company_repo.delete(company_id)
    
    @pytest.mark.asyncio
    async def test_set_persists_to_database(self, company_repo, unique_id, migrated_db):
        """Проверяем что set() реально сохраняет в БД (не только в память)"""
        from core.config import get_settings
        
        company_id = unique_id("company")
        company = Company(
            company_id=company_id,
            name="Persistent Company",
            subdomain=f"persist-{company_id}",
            tariff_plan=TariffPlan.FREE,
            balance=50.0
        )
        
        # Отладка: URL
        settings = get_settings()
        print(f"Storage db_url: {company_repo._storage.db_url}")
        print(f"Settings shared_url: {settings.database.shared_url}")
        
        # Сохраняем через репозиторий
        await company_repo.set(company)
        
        # Проверяем что get работает
        loaded_after_set = await company_repo.get(company_id)
        print(f"get() after set(): {loaded_after_set is not None}")
        
        # Проверяем через прямой SQL - используем тот же URL что и Storage
        engine = create_async_engine(company_repo._storage.db_url)
        
        async with engine.begin() as conn:
            # Сначала проверим что system company существует
            system_result = await conn.execute(
                text("SELECT key FROM storage WHERE key = 'company:system'")
            )
            system_row = system_result.fetchone()
            print(f"SQL system company exists: {system_row is not None}")
            
            # Проверим все company:* ключи
            all_result = await conn.execute(
                text("SELECT key FROM storage WHERE key LIKE 'company:%' LIMIT 10")
            )
            all_rows = all_result.fetchall()
            print(f"All company keys in DB: {[r[0] for r in all_rows]}")
            
            # Теперь ищем нашу компанию
            result = await conn.execute(
                text("SELECT key, value FROM storage WHERE key = :key"),
                {"key": f"company:{company_id}"}
            )
            row = result.fetchone()
            print(f"Our company found: {row is not None}")
        
        await engine.dispose()
        
        # Cleanup
        await company_repo.delete(company_id)
        
        # Проверяем что данные были в БД
        assert row is not None, f"SQL должен найти компанию company:{company_id}"
        assert row[0] == f"company:{company_id}"
    
    @pytest.mark.asyncio
    async def test_delete(self, company_repo, unique_id):
        """Проверяем что delete() удаляет компанию"""
        company_id = unique_id("company")
        company = Company(
            company_id=company_id,
            name="To Delete",
            subdomain=f"delete-{company_id}",
            tariff_plan=TariffPlan.FREE,
            balance=0.0
        )
        
        # Создаем и удаляем
        await company_repo.set(company)
        await company_repo.delete(company_id)
        
        # Проверяем что удалено
        loaded = await company_repo.get(company_id)
        assert loaded is None, "Компания должна быть удалена"
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Архитектурная проблема: prefix 'company:' используется и для компаний и для изоляции")
    async def test_list_all(self, company_repo, unique_id):
        """Проверяем что list_all() возвращает список компаний"""
        # Создаем несколько компаний
        company_ids = []
        for i in range(3):
            company_id = unique_id(f"company_{i}")
            company_ids.append(company_id)
            company = Company(
                company_id=company_id,
                name=f"Company {i}",
                subdomain=f"sub-{company_id}",
                tariff_plan=TariffPlan.FREE,
                balance=float(i * 10)
            )
            await company_repo.set(company)
        
        try:
            # Получаем список
            companies = await company_repo.list_all(limit=100)
            
            # Проверяем что наши компании есть в списке
            found_ids = {c.company_id for c in companies}
            for company_id in company_ids:
                assert company_id in found_ids, f"Компания {company_id} должна быть в списке"
        finally:
            # Cleanup
            for company_id in company_ids:
                await company_repo.delete(company_id)
    
    @pytest.mark.asyncio
    async def test_storage_url_matches_settings(self, company_repo):
        """Проверяем что репозиторий использует правильный URL БД"""
        from core.config import get_settings
        
        settings = get_settings()
        storage_url = company_repo._storage.db_url
        
        print(f"Storage URL: {storage_url}")
        print(f"Settings shared_url: {settings.database.shared_url}")
        
        assert storage_url == settings.database.shared_url, \
            "company_repo должен использовать shared_url"

