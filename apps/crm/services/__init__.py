"""
CRM Services.
"""

from apps.crm.services.attachment_service import AttachmentService
from apps.crm.services.company_init_service import CompanyInitService
from apps.crm.services.entity_service import EntityService
from apps.crm.services.saga import EntityDeletionSaga

__all__ = [
    "EntityService",
    "AttachmentService",
    "CompanyInitService",
    "EntityDeletionSaga",
]
