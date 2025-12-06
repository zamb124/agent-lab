"""
Тесты системы расчета релевантности и весов сущностей.

Тестирует:
- Формулу расчета score
- Расчет size
- Подсчет degree
"""

import pytest
import pytest_asyncio

from apps.crm.services.graph_service import GraphService
from apps.crm.models.entity_models import EntityCreate
from apps.crm.models.relationship_models import RelationshipCreate


class TestScoreCalculationFormula:
    """Точные тесты формулы: score = relevance * (1 + degree) * type_coefficient"""
    
    @pytest.mark.asyncio
    async def test_formula_zero_degree_coef_1(self, crm_graph_service):
        """relevance=0.5, degree=0, coef=1.0 -> score=0.5"""
        score, _ = crm_graph_service._calculate_entity_score(0.5, 0, 1.0)
        assert score == 0.5
    
    @pytest.mark.asyncio
    async def test_formula_zero_degree_coef_12(self, crm_graph_service):
        """relevance=0.5, degree=0, coef=1.2 -> score=0.6"""
        score, _ = crm_graph_service._calculate_entity_score(0.5, 0, 1.2)
        assert score == 0.6
    
    @pytest.mark.asyncio
    async def test_formula_degree_1(self, crm_graph_service):
        """relevance=0.5, degree=1, coef=1.0 -> score=1.0"""
        score, _ = crm_graph_service._calculate_entity_score(0.5, 1, 1.0)
        assert score == 1.0
    
    @pytest.mark.asyncio
    async def test_formula_degree_2(self, crm_graph_service):
        """relevance=0.5, degree=2, coef=1.0 -> score=1.5"""
        score, _ = crm_graph_service._calculate_entity_score(0.5, 2, 1.0)
        assert score == 1.5
    
    @pytest.mark.asyncio
    async def test_formula_degree_4_coef_11(self, crm_graph_service):
        """relevance=0.6, degree=4, coef=1.1 -> score=3.3"""
        score, _ = crm_graph_service._calculate_entity_score(0.6, 4, 1.1)
        # 0.6 * (1+4) * 1.1 = 0.6 * 5 * 1.1 = 3.3
        assert score == 3.3
    
    @pytest.mark.asyncio
    async def test_formula_high_relevance(self, crm_graph_service):
        """relevance=1.0, degree=3, coef=1.2 -> score=4.8"""
        score, _ = crm_graph_service._calculate_entity_score(1.0, 3, 1.2)
        # 1.0 * (1+3) * 1.2 = 1.0 * 4 * 1.2 = 4.8
        assert score == 4.8
    
    @pytest.mark.asyncio
    async def test_formula_low_relevance(self, crm_graph_service):
        """relevance=0.2, degree=2, coef=0.8 -> score=0.48"""
        score, _ = crm_graph_service._calculate_entity_score(0.2, 2, 0.8)
        # 0.2 * (1+2) * 0.8 = 0.2 * 3 * 0.8 = 0.48
        assert score == 0.48
    
    @pytest.mark.asyncio
    async def test_formula_fractional_coef(self, crm_graph_service):
        """relevance=0.8, degree=1, coef=0.9 -> score=1.44"""
        score, _ = crm_graph_service._calculate_entity_score(0.8, 1, 0.9)
        # 0.8 * (1+1) * 0.9 = 0.8 * 2 * 0.9 = 1.44
        assert score == 1.44


class TestSizeCalculation:
    """Тесты формулы size: min(50, max(15, 15 + score * 10))"""
    
    @pytest.mark.asyncio
    async def test_size_minimum_bound(self, crm_graph_service):
        """При очень низком score size >= 15"""
        _, size = crm_graph_service._calculate_entity_score(0.01, 0, 0.5)
        assert size >= 15.0
        assert size <= 16.0  # Близко к минимуму
    
    @pytest.mark.asyncio
    async def test_size_maximum_bound(self, crm_graph_service):
        """При очень высоком score size = 50"""
        _, size = crm_graph_service._calculate_entity_score(1.0, 100, 2.0)
        assert size == 50.0
    
    @pytest.mark.asyncio
    async def test_size_score_05(self, crm_graph_service):
        """score=0.5 -> size=15+5=20"""
        score, size = crm_graph_service._calculate_entity_score(0.5, 0, 1.0)
        assert score == 0.5
        assert size == 20.0
    
    @pytest.mark.asyncio
    async def test_size_score_1(self, crm_graph_service):
        """score=1.0 -> size=15+10=25"""
        score, size = crm_graph_service._calculate_entity_score(0.5, 1, 1.0)
        assert score == 1.0
        assert size == 25.0
    
    @pytest.mark.asyncio
    async def test_size_score_2(self, crm_graph_service):
        """score=2.0 -> size=15+20=35"""
        score, size = crm_graph_service._calculate_entity_score(1.0, 1, 1.0)
        assert score == 2.0
        assert size == 35.0
    
    @pytest.mark.asyncio
    async def test_size_score_35(self, crm_graph_service):
        """score=3.5 -> size=15+35=50 (capped)"""
        score, size = crm_graph_service._calculate_entity_score(1.0, 2.5, 1.0)
        # 1.0 * (1+2.5) * 1.0 = 3.5
        assert score == 3.5
        assert size == 50.0  # 15 + 35 = 50 (max)


class TestCountDegrees:
    """Тесты подсчета связей _count_degrees"""
    
    @pytest.mark.asyncio
    async def test_empty_list(self, crm_graph_service):
        """Пустой список -> пустой dict"""
        result = crm_graph_service._count_degrees([])
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_single_relationship(self, crm_container, test_context, unique_crm_id):
        """Одна связь учитывается для обоих концов"""
        entity_service = crm_container.entity_service
        relationship_service = crm_container.relationship_service
        graph_service = crm_container.graph_service
        
        # Создаем 2 сущности
        e1 = await entity_service.create_entity(EntityCreate(
            type="person",
            name=f"Degree Test 1 {unique_crm_id('deg')}",
            attributes={},
        ))
        e2 = await entity_service.create_entity(EntityCreate(
            type="person",
            name=f"Degree Test 2 {unique_crm_id('deg')}",
            attributes={},
        ))
        
        # Создаем связь
        rel = await relationship_service.create_relationship(RelationshipCreate(
            source_entity_id=e1.entity_id,
            target_entity_id=e2.entity_id,
            relationship_type="knows",
            weight=1.0,
        ))
        
        try:
            # Получаем связи
            relationships = await relationship_service.list_relationships(limit=100)
            our_rel = [r for r in relationships if r.relationship_id == rel.relationship_id]
            
            degrees = graph_service._count_degrees(our_rel)
            
            assert degrees[e1.entity_id] == 1
            assert degrees[e2.entity_id] == 1
        finally:
            await relationship_service.delete_relationship(rel.relationship_id)
            await entity_service.delete_entity(e1.entity_id)
            await entity_service.delete_entity(e2.entity_id)
    
    @pytest.mark.asyncio
    async def test_hub_entity_multiple_connections(self, crm_container, test_context, unique_crm_id):
        """Центральная сущность с несколькими связями"""
        entity_service = crm_container.entity_service
        relationship_service = crm_container.relationship_service
        graph_service = crm_container.graph_service
        
        # Создаем hub и 3 спутника
        hub = await entity_service.create_entity(EntityCreate(
            type="person",
            name=f"Hub {unique_crm_id('hub')}",
            attributes={},
        ))
        satellites = []
        relationships = []
        
        for i in range(3):
            sat = await entity_service.create_entity(EntityCreate(
                type="person",
                name=f"Satellite {i} {unique_crm_id('sat')}",
                attributes={},
            ))
            satellites.append(sat)
            
            rel = await relationship_service.create_relationship(RelationshipCreate(
                source_entity_id=hub.entity_id,
                target_entity_id=sat.entity_id,
                relationship_type="knows",
                weight=1.0,
            ))
            relationships.append(rel)
        
        try:
            all_rels = await relationship_service.list_relationships(limit=100)
            our_rels = [r for r in all_rels if r.relationship_id in [rel.relationship_id for rel in relationships]]
            
            degrees = graph_service._count_degrees(our_rels)
            
            # Hub имеет 3 связи
            assert degrees[hub.entity_id] == 3
            # Каждый спутник имеет 1 связь
            for sat in satellites:
                assert degrees[sat.entity_id] == 1
        finally:
            for rel in relationships:
                await relationship_service.delete_relationship(rel.relationship_id)
            for sat in satellites:
                await entity_service.delete_entity(sat.entity_id)
            await entity_service.delete_entity(hub.entity_id)


class TestEntityRelevance:
    """Тесты сохранения relevance в Entity"""
    
    @pytest.mark.asyncio
    async def test_default_relevance_05(self, crm_container, test_context, unique_crm_id):
        """Без указания relevance -> 0.5"""
        entity_service = crm_container.entity_service
        
        entity = await entity_service.create_entity(EntityCreate(
            type="person",
            name=f"Default Rel {unique_crm_id('rel')}",
            attributes={},
        ))
        
        try:
            assert entity.relevance == 0.5
        finally:
            await entity_service.delete_entity(entity.entity_id)
    
    @pytest.mark.asyncio
    async def test_custom_relevance_095(self, crm_container, test_context, unique_crm_id):
        """relevance=0.95 сохраняется"""
        entity_service = crm_container.entity_service
        
        entity = await entity_service.create_entity(EntityCreate(
            type="person",
            name=f"High Rel {unique_crm_id('rel')}",
            attributes={},
            relevance=0.95,
        ))
        
        try:
            assert entity.relevance == 0.95
            
            # Проверяем что сохраняется в БД
            fetched = await entity_service.get_entity(entity.entity_id)
            assert fetched.relevance == 0.95
        finally:
            await entity_service.delete_entity(entity.entity_id)
    
    @pytest.mark.asyncio
    async def test_custom_relevance_02(self, crm_container, test_context, unique_crm_id):
        """relevance=0.2 сохраняется"""
        entity_service = crm_container.entity_service
        
        entity = await entity_service.create_entity(EntityCreate(
            type="person",
            name=f"Low Rel {unique_crm_id('rel')}",
            attributes={},
            relevance=0.2,
        ))
        
        try:
            assert entity.relevance == 0.2
        finally:
            await entity_service.delete_entity(entity.entity_id)


class TestGraphIntegration:
    """Интеграционные тесты графа с расчетом score"""
    
    @pytest_asyncio.fixture
    async def score_test_data(self, crm_container, test_context, unique_crm_id):
        """
        Создает данные для проверки расчета score:
        - main: relevance=0.8, 2 связи
        - secondary: relevance=0.4, 1 связь
        """
        entity_service = crm_container.entity_service
        relationship_service = crm_container.relationship_service
        
        main = await entity_service.create_entity(EntityCreate(
            type="person",
            name=f"Main {unique_crm_id('score')}",
            attributes={},
            relevance=0.8,
        ))
        
        secondary = await entity_service.create_entity(EntityCreate(
            type="person", 
            name=f"Secondary {unique_crm_id('score')}",
            attributes={},
            relevance=0.4,
        ))
        
        third = await entity_service.create_entity(EntityCreate(
            type="person",
            name=f"Third {unique_crm_id('score')}",
            attributes={},
            relevance=0.6,
        ))
        
        # main -> secondary, main -> third
        rel1 = await relationship_service.create_relationship(RelationshipCreate(
            source_entity_id=main.entity_id,
            target_entity_id=secondary.entity_id,
            relationship_type="knows",
            weight=1.0,
        ))
        
        rel2 = await relationship_service.create_relationship(RelationshipCreate(
            source_entity_id=main.entity_id,
            target_entity_id=third.entity_id,
            relationship_type="knows",
            weight=1.0,
        ))
        
        yield {
            "main": main,
            "secondary": secondary,
            "third": third,
            "relationships": [rel1, rel2],
        }
        
        await relationship_service.delete_relationship(rel1.relationship_id)
        await relationship_service.delete_relationship(rel2.relationship_id)
        await entity_service.delete_entity(main.entity_id)
        await entity_service.delete_entity(secondary.entity_id)
        await entity_service.delete_entity(third.entity_id)
    
    @pytest.mark.asyncio
    async def test_graph_nodes_contain_score_fields(self, crm_graph_service, score_test_data, test_context):
        """Узлы графа содержат все поля для score"""
        result = await crm_graph_service.get_full_graph(limit=100)
        
        main_id = score_test_data["main"].entity_id
        main_node = next((n for n in result["nodes"] if n["id"] == main_id), None)
        
        assert main_node is not None
        assert "score" in main_node
        assert "size" in main_node
        assert "relevance" in main_node
        assert "degree" in main_node
    
    @pytest.mark.asyncio
    async def test_main_has_degree_2(self, crm_graph_service, score_test_data, test_context):
        """Main entity имеет degree=2"""
        result = await crm_graph_service.get_full_graph(limit=100)
        
        main_id = score_test_data["main"].entity_id
        main_node = next((n for n in result["nodes"] if n["id"] == main_id), None)
        
        assert main_node["degree"] == 2
    
    @pytest.mark.asyncio
    async def test_secondary_has_degree_1(self, crm_graph_service, score_test_data, test_context):
        """Secondary entity имеет degree=1"""
        result = await crm_graph_service.get_full_graph(limit=100)
        
        secondary_id = score_test_data["secondary"].entity_id
        secondary_node = next((n for n in result["nodes"] if n["id"] == secondary_id), None)
        
        assert secondary_node["degree"] == 1
    
    @pytest.mark.asyncio
    async def test_relevance_preserved_in_graph(self, crm_graph_service, score_test_data, test_context):
        """Relevance сохраняется в графе"""
        result = await crm_graph_service.get_full_graph(limit=100)
        
        main_id = score_test_data["main"].entity_id
        secondary_id = score_test_data["secondary"].entity_id
        
        main_node = next((n for n in result["nodes"] if n["id"] == main_id), None)
        secondary_node = next((n for n in result["nodes"] if n["id"] == secondary_id), None)
        
        assert main_node["relevance"] == 0.8
        assert secondary_node["relevance"] == 0.4
    
    @pytest.mark.asyncio
    async def test_main_has_higher_score_than_secondary(self, crm_graph_service, score_test_data, test_context):
        """Main (rel=0.8, deg=2) имеет больший score чем secondary (rel=0.4, deg=1)"""
        result = await crm_graph_service.get_full_graph(limit=100)
        
        main_id = score_test_data["main"].entity_id
        secondary_id = score_test_data["secondary"].entity_id
        
        main_node = next((n for n in result["nodes"] if n["id"] == main_id), None)
        secondary_node = next((n for n in result["nodes"] if n["id"] == secondary_id), None)
        
        # main: 0.8 * 3 * coef vs secondary: 0.4 * 2 * coef
        # При одинаковом coef: 2.4 > 0.8
        assert main_node["score"] > secondary_node["score"]
    
    @pytest.mark.asyncio
    async def test_main_has_larger_size_than_secondary(self, crm_graph_service, score_test_data, test_context):
        """Main имеет больший size чем secondary"""
        result = await crm_graph_service.get_full_graph(limit=100)
        
        main_id = score_test_data["main"].entity_id
        secondary_id = score_test_data["secondary"].entity_id
        
        main_node = next((n for n in result["nodes"] if n["id"] == main_id), None)
        secondary_node = next((n for n in result["nodes"] if n["id"] == secondary_id), None)
        
        assert main_node["size"] > secondary_node["size"]


class TestWeightCoefficient:
    """Тесты наличия weight_coefficient в EntityType"""
    
    @pytest.mark.asyncio
    async def test_entity_types_have_weight_coefficient(self, entity_type_service, test_context):
        """Все типы должны иметь weight_coefficient"""
        types = await entity_type_service.get_all_types()
        
        for entity_type in types:
            assert hasattr(entity_type, "weight_coefficient")
            assert entity_type.weight_coefficient is not None
            assert isinstance(entity_type.weight_coefficient, (int, float))
    
    @pytest.mark.asyncio
    async def test_weight_coefficient_in_valid_range(self, entity_type_service, test_context):
        """weight_coefficient должен быть в разумном диапазоне"""
        types = await entity_type_service.get_all_types()
        
        for entity_type in types:
            assert 0.1 <= entity_type.weight_coefficient <= 5.0
