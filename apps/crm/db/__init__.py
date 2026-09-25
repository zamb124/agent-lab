"""Регистрация моделей CRM."""

from apps.crm.models.access_request import AccessRequest
from apps.crm.models.company_mapping import CompanyMapping
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.entity_type import EntityType, EntityTypeCatalogRevision
from apps.crm.models.namespace_template import NamespaceTemplate, NamespaceTemplateType
from apps.crm.models.relationship import Relationship
from apps.crm.models.relationship_type import RelationshipType
from apps.crm.models.suggest import CRMSuggest
from apps.crm.models.task import CRMTask

__all__ = [
    "CRMEntity",
    "EntityType",
    "EntityTypeCatalogRevision",
    "RelationshipType",
    "Relationship",
    "CompanyMapping",
    "AccessRequest",
    "CRMSuggest",
    "CRMTask",
    "NamespaceTemplate",
    "NamespaceTemplateType",
]
