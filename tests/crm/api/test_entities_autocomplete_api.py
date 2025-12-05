"""
Тесты для API автодополнения сущностей (@mention).
"""

import pytest
from httpx import AsyncClient


class TestEntitiesAutocompleteAPI:
    """Тесты API автодополнения сущностей"""
    
    @pytest.mark.asyncio
    async def test_autocomplete_entities(self, crm_client: AsyncClient, test_entity):
        """Тест автодополнения сущностей"""
        response = await crm_client.get(
            "/crm/api/v1/entities/autocomplete",
            params={"q": test_entity.name[:3]}  # Первые 3 буквы имени
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        # Результаты должны содержать нужные поля
        if len(data) > 0:
            assert "name" in data[0] or "entity_id" in data[0]
    
    @pytest.mark.asyncio
    async def test_autocomplete_empty_query(self, crm_client: AsyncClient):
        """Тест автодополнения с пустым запросом"""
        response = await crm_client.get(
            "/crm/api/v1/entities/autocomplete",
            params={"q": ""}
        )
        
        # Пустой запрос должен вернуть ошибку валидации
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_autocomplete_with_type_filter(self, crm_client: AsyncClient, test_entity):
        """Тест автодополнения с фильтром по типу"""
        response = await crm_client.get(
            "/crm/api/v1/entities/autocomplete",
            params={
                "q": "test",
                "entity_type": test_entity.type
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        for entity in data:
            if "type" in entity:
                assert entity["type"] == test_entity.type
    
    @pytest.mark.asyncio
    async def test_autocomplete_with_limit(self, crm_client: AsyncClient):
        """Тест автодополнения с ограничением результатов"""
        response = await crm_client.get(
            "/crm/api/v1/entities/autocomplete",
            params={
                "q": "a",
                "limit": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) <= 5
    
    @pytest.mark.asyncio
    async def test_autocomplete_limit_validation(self, crm_client: AsyncClient):
        """Тест валидации параметра limit"""
        # limit > 50 должен быть ошибкой
        response = await crm_client.get(
            "/crm/api/v1/entities/autocomplete",
            params={
                "q": "test",
                "limit": 100
            }
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_autocomplete_no_results(self, crm_client: AsyncClient):
        """Тест автодополнения без результатов"""
        response = await crm_client.get(
            "/crm/api/v1/entities/autocomplete",
            params={"q": "xyznonexistent123456"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        # Может быть пустой список
    
    @pytest.mark.asyncio
    async def test_autocomplete_special_characters(self, crm_client: AsyncClient):
        """Тест автодополнения со специальными символами"""
        response = await crm_client.get(
            "/crm/api/v1/entities/autocomplete",
            params={"q": "test@#$%"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_autocomplete_unicode(self, crm_client: AsyncClient):
        """Тест автодополнения с unicode символами"""
        response = await crm_client.get(
            "/crm/api/v1/entities/autocomplete",
            params={"q": "Иван"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_autocomplete_returns_entity_fields(self, crm_client: AsyncClient, test_entity):
        """Тест что автодополнение возвращает нужные поля"""
        response = await crm_client.get(
            "/crm/api/v1/entities/autocomplete",
            params={"q": test_entity.name}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            entity = data[0]
            # Проверяем обязательные поля для @mention
            # entity_id или id
            assert "entity_id" in entity or "id" in entity
            # name для отображения
            assert "name" in entity
            # type для иконки
            assert "type" in entity

