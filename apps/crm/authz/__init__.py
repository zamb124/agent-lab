"""CRM OpenFGA helpers (не shared — только CRM domain)."""

from apps.crm.authz.tuples import (
    crm_entity_namespace_link,
    crm_entity_owner_tuple,
    crm_grant_tuple,
    crm_namespace_company_editor_tuple,
    crm_namespace_company_link,
    crm_namespace_company_viewer_tuple,
)

__all__ = [
    "crm_entity_namespace_link",
    "crm_entity_owner_tuple",
    "crm_grant_tuple",
    "crm_namespace_company_editor_tuple",
    "crm_namespace_company_link",
    "crm_namespace_company_viewer_tuple",
]
