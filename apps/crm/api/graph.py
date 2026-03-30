"""
API для работы с графами связей.

Endpoints:
- /entities/{entity_id}/influence-graph - построение графа влияния
- /entities/{entity_id}/related - прямо связанные entities
"""

from typing import List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from datetime import datetime
from pydantic import BaseModel, Field

from apps.crm.models.graph import (
    InfluenceGraphResponse,
    RelatedEntitiesResponse
)
from apps.crm.services.graph_service import GraphService
from apps.crm.dependencies import get_graph_service
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/entities", tags=["Graph"])


class OverviewGraphRequest(BaseModel):
    entity_ids: List[str] = Field(description="Список seed entity ID")
    max_depth: int = Field(default=3, ge=1, le=5)
    relationship_types: Optional[str] = Field(default=None, description="Comma-separated типы связей")
    created_at_from: Optional[datetime] = None
    created_at_to: Optional[datetime] = None


@router.post("/overview-graph", response_model=InfluenceGraphResponse)
async def get_overview_graph(
    request: OverviewGraphRequest,
    service: GraphService = Depends(get_graph_service),
):
    """Объединённый граф влияния по нескольким seed-сущностям за один запрос."""
    if not request.entity_ids:
        raise HTTPException(status_code=422, detail="entity_ids must not be empty")

    rel_types_list = None
    if request.relationship_types:
        rel_types_list = [rt.strip() for rt in request.relationship_types.split(",")]

    try:
        graph = await service.build_overview_graph(
            entity_ids=request.entity_ids,
            max_depth=request.max_depth,
            relationship_types=rel_types_list,
            created_at_from=request.created_at_from,
            created_at_to=request.created_at_to,
        )
        return graph
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error building overview graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/{entity_id}/influence-graph", response_model=InfluenceGraphResponse)
async def get_influence_graph(
    entity_id: str,
    max_depth: int = Query(3, ge=1, le=5, description="Максимальная глубина обхода"),
    relationship_types: Optional[str] = Query(None, description="Comma-separated типы связей"),
    created_at_from: Optional[datetime] = Query(None, description="Фильтр created_at >= value"),
    created_at_to: Optional[datetime] = Query(None, description="Фильтр created_at <= value"),
    service: GraphService = Depends(get_graph_service)
):
    """
    Построение графа влияния от entity.
    
    Учитывает:
    - Направленность связей (is_directed, inverse_type_id)
    - Показывает узлы без доступа как placeholders
    - Ограничение: max_depth <= 5 (производительность)
    
    Args:
        entity_id: ID корневой entity
        max_depth: Глубина обхода (1-5)
        relationship_types: Фильтр по типам связей (например: "manages,works_on")
    
    Returns:
        Граф с nodes и edges
    
    Raises:
        404: Entity не найдена
        403: Нет доступа к корневой entity
    """
    rel_types_list = None
    if relationship_types:
        rel_types_list = [rt.strip() for rt in relationship_types.split(",")]
    
    try:
        graph = await service.build_influence_graph(
            entity_id=entity_id,
            max_depth=max_depth,
            relationship_types=rel_types_list,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )
        return graph
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error building influence graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/{entity_id}/related", response_model=RelatedEntitiesResponse)
async def get_related_entities(
    entity_id: str,
    direction: str = Query("both", regex="^(incoming|outgoing|both)$"),
    relationship_type: Optional[str] = Query(None),
    created_at_from: Optional[datetime] = Query(None, description="Фильтр created_at >= value"),
    created_at_to: Optional[datetime] = Query(None, description="Фильтр created_at <= value"),
    service: GraphService = Depends(get_graph_service)
):
    """
    Получить прямо связанные entities (1 уровень).
    
    Args:
        entity_id: ID центральной entity
        direction: "incoming" | "outgoing" | "both"
        relationship_type: Фильтр по типу связи
    
    Returns:
        Связанные entities разделенные по направлению
    
    Raises:
        404: Entity не найдена
    """
    try:
        related = await service.get_related_entities(
            entity_id=entity_id,
            direction=direction,
            relationship_type=relationship_type,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )
        return related
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting related entities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

