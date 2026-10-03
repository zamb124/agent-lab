"""Доменные модели AuthzService (не OpenFGA SDK types)."""

from dataclasses import dataclass

from core.authz.ids import (
    PUBLIC_USER,
    format_company_member_userset,
    format_flow_branch_key,
    format_group_id,
    format_namespace_key,
    format_object_id,
    format_user_id,
    group_object_key,
    parse_object_id,
)
from core.authz.types import AuthzObjectType, AuthzRelation, AuthzSubjectKind

PLATFORM_GLOBAL_OBJECT_KEY = "global"


@dataclass(frozen=True, slots=True)
class AuthzObject:
    object_type: AuthzObjectType
    object_key: str

    @property
    def fga_id(self) -> str:
        return format_object_id(self.object_type, self.object_key)

    @classmethod
    def from_fga_id(cls, raw: str) -> "AuthzObject":
        object_type, object_key = parse_object_id(raw)
        return cls(object_type=object_type, object_key=object_key)

    @classmethod
    def company(cls, company_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.COMPANY, company_id)

    @classmethod
    def platform(cls) -> "AuthzObject":
        return cls(AuthzObjectType.PLATFORM, PLATFORM_GLOBAL_OBJECT_KEY)

    @classmethod
    def group(cls, group_name: str, *, company_id: str | None = None) -> "AuthzObject":
        return cls(AuthzObjectType.GROUP, group_object_key(group_name, company_id=company_id))

    @classmethod
    def platform_namespace(cls, company_id: str, namespace: str) -> "AuthzObject":
        return cls(
            AuthzObjectType.PLATFORM_NAMESPACE,
            format_namespace_key(company_id, namespace),
        )

    @classmethod
    def crm_namespace(cls, company_id: str, namespace: str) -> "AuthzObject":
        return cls(
            AuthzObjectType.CRM_NAMESPACE,
            format_namespace_key(company_id, namespace),
        )

    @classmethod
    def crm_entity(cls, entity_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.CRM_ENTITY, entity_id)

    @classmethod
    def wiki_page(cls, wiki_page_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.WIKI_PAGE, wiki_page_id)

    @classmethod
    def document_catalog(cls, catalog_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.DOCUMENT_CATALOG, catalog_id)

    @classmethod
    def document_file(cls, file_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.DOCUMENT_FILE, file_id)

    @classmethod
    def sync_channel(cls, channel_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.SYNC_CHANNEL, channel_id)

    @classmethod
    def work_queue(cls, work_queue_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.WORK_QUEUE, work_queue_id)

    @classmethod
    def mailbox_binding(cls, mailbox_binding_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.MAILBOX_BINDING, mailbox_binding_id)

    @classmethod
    def flow(cls, flow_id: str, *, company_id: str) -> "AuthzObject":
        return cls(
            AuthzObjectType.FLOW,
            format_namespace_key(company_id, flow_id),
        )

    @classmethod
    def flow_branch(
        cls, flow_id: str, branch_id: str, *, company_id: str
    ) -> "AuthzObject":
        return cls(
            AuthzObjectType.FLOW_BRANCH,
            format_flow_branch_key(company_id, flow_id, branch_id),
        )

    @classmethod
    def tool(cls, tool_id: str, *, company_id: str) -> "AuthzObject":
        return cls(
            AuthzObjectType.TOOL,
            format_namespace_key(company_id, tool_id),
        )

    @classmethod
    def flow_ui_share(cls, share_grant_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.FLOW_UI_SHARE, share_grant_id)

    @classmethod
    def agent_device(cls, device_id: str) -> "AuthzObject":
        return cls(AuthzObjectType.AGENT_DEVICE, device_id)

    @classmethod
    def datasource(cls, datasource_id: str, *, company_id: str) -> "AuthzObject":
        return cls(
            AuthzObjectType.DATASOURCE,
            format_namespace_key(company_id, datasource_id),
        )

    @classmethod
    def stock_warehouse(cls, warehouse_id: str, *, company_id: str) -> "AuthzObject":
        return cls(
            AuthzObjectType.STOCK_WAREHOUSE,
            format_namespace_key(company_id, warehouse_id),
        )


@dataclass(frozen=True, slots=True)
class AuthzSubject:
    kind: AuthzSubjectKind
    value: str

    @property
    def fga_user(self) -> str:
        if self.kind is AuthzSubjectKind.USER:
            return format_user_id(self.value)
        if self.kind is AuthzSubjectKind.PUBLIC:
            return PUBLIC_USER
        if self.kind is AuthzSubjectKind.COMPANY_MEMBER:
            return format_company_member_userset(self.value)
        if self.kind is AuthzSubjectKind.GROUP:
            return f"{format_group_id(self.value)}#member"
        if self.kind is AuthzSubjectKind.API_KEY:
            return f"api_key:{self.value}"
        if self.kind is AuthzSubjectKind.OBJECT:
            # TTU tupleset: user field is another object id (e.g. crm_namespace:acme/default)
            if ":" not in self.value:
                raise ValueError(f"object subject must be type:id, got {self.value!r}")
            return self.value
        raise ValueError(f"unsupported AuthzSubjectKind: {self.kind}")

    @classmethod
    def user(cls, user_id: str) -> "AuthzSubject":
        return cls(AuthzSubjectKind.USER, user_id)

    @classmethod
    def public(cls) -> "AuthzSubject":
        return cls(AuthzSubjectKind.PUBLIC, "*")

    @classmethod
    def company_member(cls, company_id: str) -> "AuthzSubject":
        return cls(AuthzSubjectKind.COMPANY_MEMBER, company_id)

    @classmethod
    def group_member(
        cls, group_name: str, *, company_id: str | None = None
    ) -> "AuthzSubject":
        return cls(
            AuthzSubjectKind.GROUP,
            group_object_key(group_name, company_id=company_id),
        )

    @classmethod
    def object_ref(cls, obj: "AuthzObject") -> "AuthzSubject":
        return cls(AuthzSubjectKind.OBJECT, obj.fga_id)

    @classmethod
    def from_fga_user(cls, raw: str) -> "AuthzSubject":
        if raw == PUBLIC_USER or raw == "user:*":
            return cls.public()
        if raw.startswith("user:"):
            return cls.user(raw.removeprefix("user:"))
        if raw.startswith("company:") and raw.endswith("#member"):
            return cls.company_member(raw.removeprefix("company:").removesuffix("#member"))
        if raw.startswith("group:") and raw.endswith("#member"):
            return cls(
                AuthzSubjectKind.GROUP,
                raw.removeprefix("group:").removesuffix("#member"),
            )
        if raw.startswith("api_key:"):
            return cls(AuthzSubjectKind.API_KEY, raw.removeprefix("api_key:"))
        if ":" in raw:
            return cls(AuthzSubjectKind.OBJECT, raw)
        raise ValueError(f"unsupported fga user subject: {raw!r}")


@dataclass(frozen=True, slots=True)
class AuthzTuple:
    subject: AuthzSubject
    relation: AuthzRelation
    obj: AuthzObject


@dataclass(frozen=True, slots=True)
class AuthzCheckItem:
    subject: AuthzSubject
    relation: AuthzRelation
    obj: AuthzObject
    correlation_id: str


@dataclass(frozen=True, slots=True)
class AuthzExpandNode:
    relation: str
    users: tuple[str, ...]
    children: tuple["AuthzExpandNode", ...]


@dataclass(frozen=True, slots=True)
class AuthzExpandTree:
    obj: AuthzObject
    relation: AuthzRelation
    root: AuthzExpandNode
