"""
Главный роутер CRM API v1.

Все роутеры собираются здесь с правильными prefix.
Общий prefix /crm/api/v1 добавляется через create_service_app.
"""

from fastapi import APIRouter

from apps.crm.api.v1 import entities, entity_types, relationships, notes, tasks, graph

router = APIRouter()

router.include_router(entities.router, prefix="/entities", tags=["Entities"])
router.include_router(entity_types.router, prefix="/entity-types", tags=["Entity Types"])
router.include_router(relationships.router, prefix="/relationships", tags=["Relationships"])
router.include_router(notes.router, prefix="/notes", tags=["Notes"])
router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
router.include_router(graph.router, prefix="/graph", tags=["Knowledge Graph"])

