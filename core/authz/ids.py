"""Форматирование и разбор OpenFGA object / user id."""

from urllib.parse import quote, unquote

from core.authz.errors import AuthzConfigError
from core.authz.types import AuthzObjectType

# OpenFGA object id forbids `:`, `#`, whitespace; `/` is the platform key separator.
_FGA_OBJECT_ID_SEGMENT_SAFE = "-_.~@+*"

# object_key уже `a/b` с percent-encoded сегментами (format_namespace_key).
# group:admin — исключение без slash; tenant-группы — `{company}/{name}`.
_SLASH_COMPOUND_OBJECT_TYPES: frozenset[AuthzObjectType] = frozenset(
    {
        AuthzObjectType.PLATFORM_NAMESPACE,
        AuthzObjectType.CRM_NAMESPACE,
        AuthzObjectType.FLOW,
        AuthzObjectType.FLOW_BRANCH,
        AuthzObjectType.TOOL,
        AuthzObjectType.GROUP,
    }
)

PLATFORM_ADMIN_GROUP = "admin"


def encode_fga_object_id_segment(segment: str) -> str:
    """Encode one segment of an OpenFGA object id (company_id / namespace / tool_id / …)."""
    if not segment:
        raise AuthzConfigError("empty OpenFGA object id segment")
    return quote(segment, safe=_FGA_OBJECT_ID_SEGMENT_SAFE)


def decode_fga_object_id_segment(segment: str) -> str:
    """Decode a segment produced by encode_fga_object_id_segment."""
    if not segment:
        raise AuthzConfigError("empty OpenFGA object id segment")
    return unquote(segment)


def to_fga_object_id(object_type: AuthzObjectType, object_key: str) -> str:
    """Доменный object_key → OpenFGA object id (без type-префикса)."""
    if not object_key:
        raise AuthzConfigError(f"empty object key for type {object_type}")
    if object_type in _SLASH_COMPOUND_OBJECT_TYPES:
        if ":" in object_key or "#" in object_key:
            raise AuthzConfigError(
                f"compound object key must not contain ':'/'#' for {object_type}: {object_key!r}"
            )
        return object_key
    return encode_fga_object_id_segment(object_key)


def from_fga_object_id(object_type: AuthzObjectType, fga_object_id: str) -> str:
    """OpenFGA object id → доменный object_key."""
    if not fga_object_id:
        raise AuthzConfigError(f"empty OpenFGA object id for type {object_type}")
    if object_type in _SLASH_COMPOUND_OBJECT_TYPES:
        return fga_object_id
    return decode_fga_object_id_segment(fga_object_id)


def format_object_id(object_type: AuthzObjectType, object_key: str) -> str:
    return f"{object_type.value}:{to_fga_object_id(object_type, object_key)}"


def format_namespace_key(company_id: str, namespace: str) -> str:
    if not company_id:
        raise AuthzConfigError("company_id is required for namespace object key")
    if not namespace:
        raise AuthzConfigError("namespace is required for namespace object key")
    if "/" in company_id or "/" in namespace:
        raise AuthzConfigError(
            f"company_id/namespace must not contain '/': {company_id!r}/{namespace!r}"
        )
    return (
        f"{encode_fga_object_id_segment(company_id)}/"
        f"{encode_fga_object_id_segment(namespace)}"
    )


def format_flow_branch_key(company_id: str, flow_id: str, branch_id: str) -> str:
    if not company_id or not flow_id or not branch_id:
        raise AuthzConfigError("company_id, flow_id and branch_id are required")
    if "/" in company_id or "/" in flow_id or "/" in branch_id:
        raise AuthzConfigError(
            f"company_id/flow_id/branch_id must not contain '/': {company_id!r}/{flow_id!r}/{branch_id!r}"
        )
    return (
        f"{encode_fga_object_id_segment(company_id)}/"
        f"{encode_fga_object_id_segment(flow_id)}/"
        f"{encode_fga_object_id_segment(branch_id)}"
    )


def parse_flow_branch_key(object_key: str) -> tuple[str, str, str]:
    """Разбор `company_id/flow_id/branch_id` object_key → доменные id."""
    parts = object_key.split("/")
    if len(parts) != 3:
        raise AuthzConfigError(f"invalid flow_branch object key: {object_key!r}")
    return (
        decode_fga_object_id_segment(parts[0]),
        decode_fga_object_id_segment(parts[1]),
        decode_fga_object_id_segment(parts[2]),
    )


def parse_namespace_key(object_key: str) -> tuple[str, str]:
    """Разбор `company_id/namespace` object_key → доменные id (после percent-decode)."""
    if "/" not in object_key:
        raise AuthzConfigError(f"invalid namespace object key: {object_key!r}")
    company_part, namespace_part = object_key.split("/", 1)
    return (
        decode_fga_object_id_segment(company_part),
        decode_fga_object_id_segment(namespace_part),
    )


def parse_object_id(raw: str) -> tuple[AuthzObjectType, str]:
    if ":" not in raw:
        raise AuthzConfigError(f"invalid OpenFGA object id: {raw!r}")
    type_name, fga_object_id = raw.split(":", 1)
    if not fga_object_id:
        raise AuthzConfigError(f"empty object key in id: {raw!r}")
    try:
        object_type = AuthzObjectType(type_name)
    except ValueError as exc:
        raise AuthzConfigError(f"unknown AuthzObjectType: {type_name!r}") from exc
    return object_type, from_fga_object_id(object_type, fga_object_id)


def is_openfga_user_subject_id(user_id: str) -> bool:
    """True если id можно записать как OpenFGA ``user:<id>`` (без ``:`` в ``<id>``)."""
    return bool(user_id) and ":" not in user_id


def format_user_id(user_id: str) -> str:
    if not user_id:
        raise AuthzConfigError("user_id is required")
    # OpenFGA user id is `user:<id>`; colon in <id> (e.g. guest:…) — malformed.
    if not is_openfga_user_subject_id(user_id):
        raise AuthzConfigError(f"user_id must not contain ':': {user_id!r}")
    return f"user:{user_id}"


def group_member_company_id(group_name: str, company_id: str) -> str | None:
    """company_id для group subject: platform admin без тенанта, иначе company_id."""
    if not group_name:
        raise AuthzConfigError("group_name is required")
    if group_name == PLATFORM_ADMIN_GROUP:
        return None
    if not company_id:
        raise AuthzConfigError("company_id is required for tenant group")
    return company_id


def group_object_key(group_name: str, *, company_id: str | None = None) -> str:
    """Object key группы: `admin` глобальный, иначе `{company}/{name}`."""
    if not group_name:
        raise AuthzConfigError("group_name is required")
    if group_name == PLATFORM_ADMIN_GROUP:
        if company_id is not None:
            raise AuthzConfigError("platform admin group is not company-scoped")
        return PLATFORM_ADMIN_GROUP
    if company_id is None:
        raise AuthzConfigError("company_id is required for tenant group")
    return format_namespace_key(company_id, group_name)


def format_group_id(group_key: str) -> str:
    if not group_key:
        raise AuthzConfigError("group_name is required")
    return format_object_id(AuthzObjectType.GROUP, group_key)


def format_company_member_userset(company_id: str) -> str:
    if not company_id:
        raise AuthzConfigError("company_id is required for company#member userset")
    return f"company:{company_id}#member"


PUBLIC_USER = "user:*"
