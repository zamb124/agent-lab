"""Канонические типы объектов и relations OpenFGA / AuthzService."""

from enum import StrEnum


class AuthzObjectType(StrEnum):
    USER = "user"
    GROUP = "group"
    COMPANY = "company"
    PLATFORM = "platform"
    PLATFORM_NAMESPACE = "platform_namespace"
    CRM_NAMESPACE = "crm_namespace"
    CRM_ENTITY = "crm_entity"
    WIKI_PAGE = "wiki_page"
    OFFICE_CATALOG = "office_catalog"
    OFFICE_DOCUMENT = "office_document"
    SYNC_CHANNEL = "sync_channel"
    WORK_QUEUE = "work_queue"
    MAILBOX_BINDING = "mailbox_binding"
    FLOW = "flow"
    FLOW_BRANCH = "flow_branch"
    TOOL = "tool"
    FLOW_UI_SHARE = "flow_ui_share"
    AGENT_DEVICE = "agent_device"


class AuthzConsistency(StrEnum):
    """OpenFGA query consistency preference (Check/List/Expand/Read)."""

    MINIMIZE_LATENCY = "MINIMIZE_LATENCY"
    HIGHER_CONSISTENCY = "HIGHER_CONSISTENCY"


class AuthzRelation(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    MEMBER = "member"
    MANAGER = "manager"
    PARENT = "parent"
    COMPANY = "company"
    PLATFORM = "platform"
    NAMESPACE = "namespace"
    CATALOG = "catalog"
    FLOW = "flow"
    COMPANY_VIEWER = "company_viewer"
    CAN_SHARE = "can_share"
    CAN_VIEW = "can_view"
    CAN_EDIT = "can_edit"
    CAN_ADMIN = "can_admin"


class AuthzSubjectKind(StrEnum):
    USER = "user"
    PUBLIC = "public"
    COMPANY_MEMBER = "company_member"
    GROUP = "group"
    API_KEY = "api_key"
    OBJECT = "object"
