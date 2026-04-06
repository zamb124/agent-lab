"""
Main router для CRM API.

Чистая архитектура без версий.
"""

from fastapi import APIRouter

from apps.crm.api.entities import router as entities_router
from apps.crm.api.entity_types import router as entity_types_router
from apps.crm.api.relationships import router as relationships_router
from apps.crm.api.attachments import router as attachments_router
from apps.crm.api.access_requests import router as access_requests_router
from apps.crm.api.namespaces import router as namespaces_router
from apps.crm.api.entity_grants import router as entity_grants_router
from apps.crm.api.namespace_grants import router as namespace_grants_router
from apps.crm.api.grants import router as grants_router
from apps.crm.api.graph import router as graph_router
from apps.crm.api.knowledge_imports import router as knowledge_imports_router

router = APIRouter()

router.include_router(entities_router)
router.include_router(entity_types_router)
router.include_router(relationships_router)
router.include_router(attachments_router)
router.include_router(access_requests_router)
router.include_router(namespaces_router)
router.include_router(entity_grants_router)
router.include_router(namespace_grants_router)
router.include_router(grants_router)
router.include_router(graph_router)
router.include_router(knowledge_imports_router)

