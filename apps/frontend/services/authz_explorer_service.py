"""Access Explorer: явные гранты и why-path для company admin через AuthzService."""

from __future__ import annotations

from collections.abc import Sequence

from apps.frontend.services.authz_explorer_hydrate import (
    AuthzExplorerHydrator,
    AuthzHydratedObject,
)
from core.authz.explorer import (
    AuthzExplorerByObjectResponse,
    AuthzExplorerByUserResponse,
    AuthzExplorerObjectHit,
    AuthzExplorerRevokeRequest,
    AuthzExplorerRevokeResponse,
    AuthzExplorerSummary,
    AuthzExplorerWhyResponse,
    AuthzGrantRow,
    AuthzGrantSource,
    AuthzWhyReason,
)
from core.authz.models import AuthzExpandNode, AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import (
    AuthzConsistency,
    AuthzObjectType,
    AuthzRelation,
    AuthzSubjectKind,
)
from core.errors.boundary import PlatformNotFoundError
from core.websocket import WsCommandError

EXPLORER_OBJECT_TYPES: tuple[AuthzObjectType, ...] = (
    AuthzObjectType.WIKI_PAGE,
    AuthzObjectType.DOCUMENT_CATALOG,
    AuthzObjectType.DOCUMENT_FILE,
    AuthzObjectType.CRM_ENTITY,
    AuthzObjectType.CRM_NAMESPACE,
    AuthzObjectType.FLOW,
    AuthzObjectType.TOOL,
    AuthzObjectType.SYNC_CHANNEL,
    AuthzObjectType.WORK_QUEUE,
    AuthzObjectType.MAILBOX_BINDING,
    AuthzObjectType.PLATFORM_NAMESPACE,
    AuthzObjectType.AGENT_DEVICE,
    AuthzObjectType.FLOW_UI_SHARE,
    AuthzObjectType.FLOW_BRANCH,
)

_DISPLAY_RELATIONS: frozenset[AuthzRelation] = frozenset(
    {
        AuthzRelation.OWNER,
        AuthzRelation.ADMIN,
        AuthzRelation.EDITOR,
        AuthzRelation.VIEWER,
        AuthzRelation.MEMBER,
        AuthzRelation.MANAGER,
        AuthzRelation.COMPANY_VIEWER,
    }
)

_REVOKE_SUBJECTS: frozenset[AuthzSubjectKind] = frozenset(
    {AuthzSubjectKind.USER, AuthzSubjectKind.GROUP}
)

_INHERIT_RELATIONS: frozenset[AuthzRelation] = frozenset(
    {
        AuthzRelation.PARENT,
        AuthzRelation.CATALOG,
        AuthzRelation.NAMESPACE,
        AuthzRelation.FLOW,
    }
)

_CONSISTENCY = AuthzConsistency.HIGHER_CONSISTENCY


class AuthzExplorerService:
    def __init__(
        self,
        *,
        authz: AuthzService,
        hydrator: AuthzExplorerHydrator,
    ) -> None:
        self._authz: AuthzService = authz
        self._hydrator: AuthzExplorerHydrator = hydrator

    async def by_user(
        self, *, user_id: str, company_id: str
    ) -> AuthzExplorerByUserResponse:
        if user_id.strip() == "":
            raise WsCommandError(
                "ws_invalid_payload",
                "user_id is required",
                error_code="user_id_required",
            )
        user_subject = AuthzSubject.user(user_id)
        group_subjects = await self._user_group_subjects(user_id)
        rows: list[AuthzGrantRow] = []
        for object_type in EXPLORER_OBJECT_TYPES:
            direct = await self._authz.list_tuples(
                object_type=object_type,
                subject=user_subject,
                consistency=_CONSISTENCY,
            )
            rows.extend(
                await self._rows_from_tuples(
                    direct,
                    company_id=company_id,
                    grant_source=AuthzGrantSource.DIRECT,
                    axis="user",
                )
            )
            for group_subject in group_subjects:
                group_tuples = await self._authz.list_tuples(
                    object_type=object_type,
                    subject=group_subject,
                    consistency=_CONSISTENCY,
                )
                rows.extend(
                    await self._rows_from_tuples(
                        group_tuples,
                        company_id=company_id,
                        grant_source=AuthzGrantSource.GROUP,
                        axis="user",
                    )
                )
        summary = _summary(rows, company_visible=True)
        return AuthzExplorerByUserResponse(
            user_id=user_id,
            company_visible=True,
            items=rows,
            summary=summary,
        )

    async def by_object(
        self,
        *,
        object_type: AuthzObjectType,
        object_key: str,
        company_id: str,
    ) -> AuthzExplorerByObjectResponse:
        if object_type not in EXPLORER_OBJECT_TYPES:
            raise WsCommandError(
                "ws_invalid_payload",
                "object_type is not supported",
                error_code="object_type_unsupported",
            )
        if object_key.strip() == "":
            raise WsCommandError(
                "ws_invalid_payload",
                "object_key is required",
                error_code="object_key_required",
            )
        obj = AuthzObject(object_type, object_key)
        hydrated = await self._hydrator.hydrate(
            object_type, object_key, company_id=company_id
        )
        if not await self._object_in_company(obj, hydrated, company_id):
            raise PlatformNotFoundError(
                "object not found in company",
                error_code="authz_object_not_found",
            )
        tuples = await self._authz.list_tuples(obj, consistency=_CONSISTENCY)
        rows: list[AuthzGrantRow] = []
        company_visible = False
        for tuple_row in tuples:
            if tuple_row.relation not in _DISPLAY_RELATIONS:
                continue
            source = _source_for_subject(tuple_row.subject)
            if source is AuthzGrantSource.COMPANY_VISIBLE:
                company_visible = True
                continue
            rows.append(
                _grant_row(
                    tuple_row,
                    hydrated=hydrated,
                    grant_source=source,
                    axis="object",
                )
            )
        summary = _summary(rows, company_visible=company_visible)
        return AuthzExplorerByObjectResponse(
            object_type=object_type,
            object_key=object_key,
            title=hydrated.title,
            title_status=hydrated.title_status,
            href=hydrated.href,
            manage_href=hydrated.manage_href,
            namespace=hydrated.namespace,
            company_visible=company_visible,
            items=rows,
            summary=summary,
        )

    async def why(
        self,
        *,
        user_id: str,
        object_type: AuthzObjectType,
        object_key: str,
        company_id: str,
    ) -> AuthzExplorerWhyResponse:
        if user_id.strip() == "":
            raise WsCommandError(
                "ws_invalid_payload",
                "user_id is required",
                error_code="user_id_required",
            )
        if object_key.strip() == "":
            raise WsCommandError(
                "ws_invalid_payload",
                "object_key is required",
                error_code="object_key_required",
            )
        if object_type not in EXPLORER_OBJECT_TYPES:
            raise WsCommandError(
                "ws_invalid_payload",
                "object_type is not supported",
                error_code="object_type_unsupported",
            )
        obj = AuthzObject(object_type, object_key)
        hydrated = await self._hydrator.hydrate(
            object_type, object_key, company_id=company_id
        )
        if not await self._object_in_company(obj, hydrated, company_id):
            raise PlatformNotFoundError(
                "object not found in company",
                error_code="authz_object_not_found",
            )
        allowed = await self._authz.can_view(obj, user_id=user_id)
        tuples = await self._authz.list_tuples(obj, consistency=_CONSISTENCY)
        group_keys = {
            subject.value for subject in await self._user_group_subjects(user_id)
        }
        reasons = _classify_why_from_tuples(
            tuples,
            user_id=user_id,
            company_id=company_id,
            group_keys=group_keys,
        )
        if AuthzWhyReason.COMPANY_VISIBLE in reasons:
            company_member = await self._authz.can_view(
                AuthzObject.company(company_id), user_id=user_id
            )
            if not company_member:
                reasons.discard(AuthzWhyReason.COMPANY_VISIBLE)
        for tuple_row in tuples:
            if tuple_row.relation not in _INHERIT_RELATIONS:
                continue
            if tuple_row.subject.kind is not AuthzSubjectKind.OBJECT:
                continue
            inherited_obj = AuthzObject.from_fga_id(tuple_row.subject.value)
            if await self._authz.can_view(inherited_obj, user_id=user_id):
                reasons.add(AuthzWhyReason.PARENT_INHERIT)
        tree = await self._authz.expand(
            obj, AuthzRelation.CAN_VIEW, consistency=_CONSISTENCY
        )
        reasons.update(
            _classify_why_expand(tree.root, user_id=user_id)
        )
        return AuthzExplorerWhyResponse(
            user_id=user_id,
            object_type=object_type,
            object_key=object_key,
            allowed=allowed,
            reasons=sorted(reasons, key=lambda reason: reason.value),
        )

    async def search_objects(
        self,
        *,
        company_id: str,
        query: str,
        object_type: AuthzObjectType | None,
    ) -> list[AuthzExplorerObjectHit]:
        if object_type is not None and object_type not in EXPLORER_OBJECT_TYPES:
            raise WsCommandError(
                "ws_invalid_payload",
                "object_type is not supported",
                error_code="object_type_unsupported",
            )
        return await self._hydrator.search_objects(
            company_id=company_id,
            query=query,
            object_type=object_type,
        )

    async def revoke(
        self,
        request: AuthzExplorerRevokeRequest,
        *,
        company_id: str,
    ) -> AuthzExplorerRevokeResponse:
        object_type = AuthzObjectType(request.object_type)
        relation = AuthzRelation(request.relation)
        subject_kind = AuthzSubjectKind(request.subject_kind)
        if object_type not in EXPLORER_OBJECT_TYPES:
            raise WsCommandError(
                "ws_invalid_payload",
                "object_type is not supported",
                error_code="object_type_unsupported",
            )
        if relation not in _DISPLAY_RELATIONS:
            raise WsCommandError(
                "ws_invalid_payload",
                "relation cannot be revoked",
                error_code="relation_not_revocable",
            )
        if subject_kind not in _REVOKE_SUBJECTS:
            raise WsCommandError(
                "ws_invalid_payload",
                "subject cannot be revoked",
                error_code="subject_not_revocable",
            )
        if request.object_key.strip() == "" or request.subject_id.strip() == "":
            raise WsCommandError(
                "ws_invalid_payload",
                "object_key and subject_id are required",
                error_code="revoke_ids_required",
            )
        hydrated = await self._hydrator.hydrate(
            object_type, request.object_key, company_id=company_id
        )
        obj = AuthzObject(object_type, request.object_key)
        if not await self._object_in_company(obj, hydrated, company_id):
            raise PlatformNotFoundError(
                "object not found in company",
                error_code="authz_object_not_found",
            )
        subject = _subject_from_row(subject_kind, request.subject_id)
        existing = await self._authz.list_tuples(
            obj,
            relation=relation,
            subject=subject,
            consistency=_CONSISTENCY,
        )
        if len(existing) == 0:
            raise PlatformNotFoundError(
                "grant tuple not found",
                error_code="authz_grant_not_found",
            )
        await self._authz.delete(
            [
                AuthzTuple(
                    subject=subject,
                    relation=relation,
                    obj=obj,
                )
            ]
        )
        return AuthzExplorerRevokeResponse(revoked=True)

    async def _user_group_subjects(self, user_id: str) -> list[AuthzSubject]:
        group_tuples = await self._authz.list_tuples(
            object_type=AuthzObjectType.GROUP,
            subject=AuthzSubject.user(user_id),
            relation=AuthzRelation.MEMBER,
            consistency=_CONSISTENCY,
        )
        subjects: list[AuthzSubject] = []
        for tuple_row in group_tuples:
            subjects.append(
                AuthzSubject(AuthzSubjectKind.GROUP, tuple_row.obj.object_key)
            )
        return subjects

    async def _rows_from_tuples(
        self,
        tuples: Sequence[AuthzTuple],
        *,
        company_id: str,
        grant_source: AuthzGrantSource,
        axis: str,
    ) -> list[AuthzGrantRow]:
        rows: list[AuthzGrantRow] = []
        for tuple_row in tuples:
            if tuple_row.relation not in _DISPLAY_RELATIONS:
                continue
            hydrated = await self._hydrator.hydrate(
                tuple_row.obj.object_type,
                tuple_row.obj.object_key,
                company_id=company_id,
            )
            if not await self._object_in_company(tuple_row.obj, hydrated, company_id):
                continue
            rows.append(
                _grant_row(
                    tuple_row,
                    hydrated=hydrated,
                    grant_source=grant_source,
                    axis=axis,
                )
            )
        return rows

    async def _object_in_company(
        self,
        obj: AuthzObject,
        hydrated: AuthzHydratedObject,
        company_id: str,
    ) -> bool:
        if hydrated.company_id == company_id:
            return True
        if hydrated.company_id is not None:
            return False
        if obj.object_type is AuthzObjectType.DOCUMENT_FILE:
            return False
        company_tuples = await self._authz.list_tuples(
            obj,
            relation=AuthzRelation.COMPANY,
            consistency=_CONSISTENCY,
        )
        expected = f"company:{company_id}"
        for tuple_row in company_tuples:
            if (
                tuple_row.subject.kind is AuthzSubjectKind.OBJECT
                and tuple_row.subject.value == expected
            ):
                return True
        return False


def _source_for_subject(subject: AuthzSubject) -> AuthzGrantSource:
    if subject.kind is AuthzSubjectKind.COMPANY_MEMBER:
        return AuthzGrantSource.COMPANY_VISIBLE
    if subject.kind is AuthzSubjectKind.GROUP:
        return AuthzGrantSource.GROUP
    if subject.kind is AuthzSubjectKind.USER:
        return AuthzGrantSource.DIRECT
    return AuthzGrantSource.INHERITED


def _grant_row(
    tuple_row: AuthzTuple,
    *,
    hydrated: AuthzHydratedObject,
    grant_source: AuthzGrantSource,
    axis: str,
) -> AuthzGrantRow:
    can_revoke = (
        grant_source in {AuthzGrantSource.DIRECT, AuthzGrantSource.GROUP}
        and tuple_row.subject.kind in _REVOKE_SUBJECTS
        and tuple_row.relation in _DISPLAY_RELATIONS
    )
    _ = axis
    return AuthzGrantRow(
        subject_kind=tuple_row.subject.kind,
        subject_id=tuple_row.subject.value,
        relation=tuple_row.relation,
        object_type=tuple_row.obj.object_type,
        object_key=tuple_row.obj.object_key,
        title=hydrated.title,
        title_status=hydrated.title_status,
        href=hydrated.href,
        manage_href=hydrated.manage_href,
        grant_source=grant_source,
        namespace=hydrated.namespace,
        can_revoke=can_revoke,
        why_reasons=[],
    )


def _subject_from_row(kind: AuthzSubjectKind, subject_id: str) -> AuthzSubject:
    resolved = AuthzSubjectKind(kind)
    if resolved is AuthzSubjectKind.USER:
        return AuthzSubject.user(subject_id)
    if resolved is AuthzSubjectKind.GROUP:
        return AuthzSubject(AuthzSubjectKind.GROUP, subject_id)
    raise WsCommandError(
        "ws_invalid_payload",
        "subject_kind cannot be revoked",
        error_code="subject_kind_not_revocable",
    )


def _summary(rows: Sequence[AuthzGrantRow], *, company_visible: bool) -> AuthzExplorerSummary:
    counts_by_type: dict[str, int] = {}
    counts_by_relation: dict[str, int] = {}
    groups: set[str] = set()
    for row in rows:
        type_key = str(row.object_type)
        counts_by_type[type_key] = counts_by_type.get(type_key, 0) + 1
        rel_key = str(row.relation)
        counts_by_relation[rel_key] = counts_by_relation.get(rel_key, 0) + 1
        if row.grant_source == AuthzGrantSource.GROUP:
            groups.add(row.subject_id)
    return AuthzExplorerSummary(
        explicit_grant_count=len(rows),
        company_visible=company_visible,
        group_count=len(groups),
        counts_by_type=counts_by_type,
        counts_by_relation=counts_by_relation,
    )


def _classify_why_from_tuples(
    tuples: Sequence[AuthzTuple],
    *,
    user_id: str,
    company_id: str,
    group_keys: set[str],
) -> set[AuthzWhyReason]:
    reasons: set[AuthzWhyReason] = set()
    for tuple_row in tuples:
        if tuple_row.relation not in _DISPLAY_RELATIONS:
            continue
        subject = tuple_row.subject
        if subject.kind is AuthzSubjectKind.USER and subject.value == user_id:
            reasons.add(AuthzWhyReason.DIRECT_GRANT)
        elif subject.kind is AuthzSubjectKind.GROUP and subject.value in group_keys:
            reasons.add(AuthzWhyReason.GROUP_MEMBERSHIP)
        elif (
            subject.kind is AuthzSubjectKind.COMPANY_MEMBER
            and subject.value == company_id
        ):
            reasons.add(AuthzWhyReason.COMPANY_VISIBLE)
    return reasons


def _classify_why_expand(node: AuthzExpandNode, *, user_id: str) -> set[AuthzWhyReason]:
    """Leaf users из expand: только прямой user:id, без model-level #parent."""
    reasons: set[AuthzWhyReason] = set()
    user_fga = f"user:{user_id}"
    for raw in node.users:
        if raw == user_fga:
            reasons.add(AuthzWhyReason.DIRECT_GRANT)
    for child in node.children:
        reasons.update(_classify_why_expand(child, user_id=user_id))
    return reasons
