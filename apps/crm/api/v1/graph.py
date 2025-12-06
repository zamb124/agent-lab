"""
API для Knowledge Graph CRM.
"""

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Query

from apps.crm.dependencies import GraphServiceDep

router = APIRouter()


@router.get("", response_model=Dict[str, Any])
async def get_full_graph(
    graph_service: GraphServiceDep,
    entity_types: Optional[str] = Query(None, description="Типы через запятую"),
    limit: int = Query(500, ge=1, le=2000),
):
    """
    Получает полный граф связей.
    
    Returns:
        {
            "nodes": [...],
            "edges": [...],
            "stats": {...}
        }
    """
    types_list = entity_types.split(",") if entity_types else None
    return await graph_service.get_full_graph(
        entity_types=types_list,
        limit=limit,
    )


@router.get("/entity/{entity_id}", response_model=Dict[str, Any])
async def get_entity_graph(
    entity_id: str,
    graph_service: GraphServiceDep,
    depth: int = Query(2, ge=1, le=5),
):
    """
    Получает граф связей для сущности.
    
    Args:
        entity_id: ID центральной сущности
        depth: Глубина обхода (1 = только прямые связи)
    """
    return await graph_service.get_entity_graph(entity_id, depth=depth)


@router.get("/relationship-types", response_model=List[str])
async def get_relationship_types(
    graph_service: GraphServiceDep,
):
    """Получает все уникальные типы связей"""
    return await graph_service.get_relationship_types()



