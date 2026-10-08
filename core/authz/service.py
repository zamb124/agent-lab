"""AuthzService — единственный публичный PDP фасад платформы."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, Protocol

from core.authz.client import OpenFgaAuthzClient
from core.authz.errors import AuthzConfigError, AuthzDenied, AuthzUnavailable
from core.authz.models import (
    AuthzCheckItem,
    AuthzExpandNode,
    AuthzExpandTree,
    AuthzObject,
    AuthzSubject,
    AuthzTuple,
)
from core.authz.types import AuthzConsistency, AuthzObjectType, AuthzRelation
from core.context import get_context, require_active_company
from core.imports import typed_view
from core.logging import get_logger

logger = get_logger(__name__)


class _UsersView(Protocol):
    users: list[str] | None


class _LeafView(Protocol):
    users: _UsersView | None


class _NodesView(Protocol):
    nodes: list[_ExpandNodeView] | None


class _ExpandNodeView(Protocol):
    name: str | None
    leaf: _LeafView | None
    union: _NodesView | None


class _UsersetTreeView(Protocol):
    root: _ExpandNodeView | None


class _ExpandResponseView(Protocol):
    tree: _UsersetTreeView | None


class AuthzService:
    """Единые check / list / write методы для всех сервисов."""

    _client: Final[OpenFgaAuthzClient]
    _enabled: Final[bool]
    _default_consistency: Final[AuthzConsistency]

    def __init__(
        self,
        client: OpenFgaAuthzClient,
        *,
        enabled: bool,
        default_consistency: AuthzConsistency = AuthzConsistency.MINIMIZE_LATENCY,
    ) -> None:
        self._client = client
        self._enabled = enabled
        self._default_consistency = default_consistency

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _assert_enabled(self) -> None:
        if not self._enabled:
            raise AuthzUnavailable("OpenFGA is disabled (openfga.enabled=false)")

    def _resolve_consistency(
        self, consistency: AuthzConsistency | None
    ) -> AuthzConsistency:
        if consistency is not None:
            return consistency
        return self._default_consistency

    def _subject_from_context(
        self,
        user_id: str | None,
        *,
        allow_public: bool,
    ) -> AuthzSubject:
        """Subject: явный user_id → context.user → public (только allow_public)."""
        if user_id:
            return AuthzSubject.user(user_id)
        ctx = get_context()
        if ctx is not None:
            resolved = ctx.user.user_id
            if resolved:
                return AuthzSubject.user(resolved)
        if allow_public:
            return AuthzSubject.public()
        raise AuthzUnavailable("user subject required for authz check")

    async def check(
        self,
        subject: AuthzSubject,
        relation: AuthzRelation,
        obj: AuthzObject,
        *,
        contextual_tuples: Sequence[AuthzTuple] | None = None,
        context: Mapping[str, str | int] | None = None,
        consistency: AuthzConsistency | None = None,
    ) -> bool:
        self._assert_enabled()
        return await self._client.check(
            subject,
            relation,
            obj,
            contextual_tuples=contextual_tuples,
            context=context,
            consistency=self._resolve_consistency(consistency),
        )

    async def require(
        self,
        subject: AuthzSubject,
        relation: AuthzRelation,
        obj: AuthzObject,
        *,
        contextual_tuples: Sequence[AuthzTuple] | None = None,
        context: Mapping[str, str | int] | None = None,
        consistency: AuthzConsistency | None = None,
    ) -> None:
        allowed = await self.check(
            subject,
            relation,
            obj,
            contextual_tuples=contextual_tuples,
            context=context,
            consistency=consistency,
        )
        if not allowed:
            raise AuthzDenied(
                f"denied {subject.fga_user} {relation.value} {obj.fga_id}"
            )

    async def can_view(self, obj: AuthzObject, *, user_id: str | None = None) -> bool:
        return await self.check(
            self._subject_from_context(user_id, allow_public=True),
            AuthzRelation.CAN_VIEW,
            obj,
        )

    async def can_edit(self, obj: AuthzObject, *, user_id: str | None = None) -> bool:
        return await self.check(
            self._subject_from_context(user_id, allow_public=False),
            AuthzRelation.CAN_EDIT,
            obj,
        )

    async def can_admin(self, obj: AuthzObject, *, user_id: str | None = None) -> bool:
        return await self.check(
            self._subject_from_context(user_id, allow_public=False),
            AuthzRelation.CAN_ADMIN,
            obj,
        )

    async def require_can_view(
        self, obj: AuthzObject, *, user_id: str | None = None
    ) -> None:
        await self.require(
            self._subject_from_context(user_id, allow_public=True),
            AuthzRelation.CAN_VIEW,
            obj,
        )

    async def require_can_edit(
        self, obj: AuthzObject, *, user_id: str | None = None
    ) -> None:
        await self.require(
            self._subject_from_context(user_id, allow_public=False),
            AuthzRelation.CAN_EDIT,
            obj,
        )

    async def require_can_admin(
        self, obj: AuthzObject, *, user_id: str | None = None
    ) -> None:
        await self.require(
            self._subject_from_context(user_id, allow_public=False),
            AuthzRelation.CAN_ADMIN,
            obj,
        )

    async def require_can_share(
        self, obj: AuthzObject, *, user_id: str | None = None
    ) -> None:
        await self.require(
            self._subject_from_context(user_id, allow_public=False),
            AuthzRelation.CAN_SHARE,
            obj,
        )

    async def require_relation(
        self,
        relation: AuthzRelation,
        obj: AuthzObject,
        *,
        user_id: str | None = None,
        consistency: AuthzConsistency | None = None,
    ) -> None:
        allow_public = relation is AuthzRelation.CAN_VIEW
        await self.require(
            self._subject_from_context(user_id, allow_public=allow_public),
            relation,
            obj,
            consistency=consistency,
        )

    async def check_company_admin(
        self,
        *,
        company_id: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        resolved_company_id = company_id
        if resolved_company_id is None:
            resolved_company_id = require_active_company().company_id
        return await self.can_admin(
            AuthzObject.company(resolved_company_id), user_id=user_id
        )

    async def require_company_admin(
        self,
        *,
        company_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        resolved_company_id = company_id
        if resolved_company_id is None:
            resolved_company_id = require_active_company().company_id
        await self.require_can_admin(
            AuthzObject.company(resolved_company_id), user_id=user_id
        )

    async def batch_check(
        self,
        items: Sequence[AuthzCheckItem],
        *,
        consistency: AuthzConsistency | None = None,
    ) -> list[bool]:
        if not items:
            return []
        self._assert_enabled()
        return await self._client.batch_check(
            items, consistency=self._resolve_consistency(consistency)
        )

    async def list_objects(
        self,
        subject: AuthzSubject,
        relation: AuthzRelation,
        object_type: AuthzObjectType,
        *,
        consistency: AuthzConsistency | None = None,
    ) -> list[AuthzObject]:
        self._assert_enabled()
        return await self._client.list_objects(
            subject,
            relation,
            object_type,
            consistency=self._resolve_consistency(consistency),
        )

    async def list_users(
        self,
        obj: AuthzObject,
        relation: AuthzRelation,
        *,
        user_filters: Sequence[AuthzObjectType] | None = None,
        consistency: AuthzConsistency | None = None,
    ) -> list[AuthzSubject]:
        self._assert_enabled()
        raw_users = await self._client.list_users(
            obj,
            relation,
            user_filters=user_filters,
            consistency=self._resolve_consistency(consistency),
        )
        subjects: list[AuthzSubject] = []
        for raw in raw_users:
            try:
                subjects.append(AuthzSubject.from_fga_user(raw))
            except ValueError as exc:
                raise AuthzConfigError(f"unsupported list_users subject: {raw!r}") from exc
        return subjects

    async def list_tuples(
        self,
        obj: AuthzObject | None = None,
        *,
        object_type: AuthzObjectType | None = None,
        relation: AuthzRelation | None = None,
        subject: AuthzSubject | None = None,
        consistency: AuthzConsistency | None = None,
    ) -> list[AuthzTuple]:
        self._assert_enabled()
        return await self._client.list_tuples(
            obj,
            object_type=object_type,
            relation=relation,
            subject=subject,
            consistency=self._resolve_consistency(consistency),
        )

    async def write(self, tuples: Sequence[AuthzTuple]) -> None:
        if not tuples:
            return
        self._assert_enabled()
        await self._client.write_and_delete(tuples, ())

    async def delete(self, tuples: Sequence[AuthzTuple]) -> None:
        if not tuples:
            return
        self._assert_enabled()
        await self._client.write_and_delete((), tuples)

    async def write_and_delete(
        self,
        writes: Sequence[AuthzTuple],
        deletes: Sequence[AuthzTuple],
    ) -> None:
        if writes or deletes:
            self._assert_enabled()
        await self._client.write_and_delete(writes, deletes)

    async def expand(
        self,
        obj: AuthzObject,
        relation: AuthzRelation,
        *,
        consistency: AuthzConsistency | None = None,
    ) -> AuthzExpandTree:
        self._assert_enabled()
        raw = await self._client.expand(
            obj,
            relation,
            consistency=self._resolve_consistency(consistency),
        )
        response = typed_view(raw, type(raw), _ExpandResponseView)
        tree = response.tree
        if tree is None or tree.root is None:
            raise AuthzUnavailable("OpenFGA expand response missing tree.root")
        return AuthzExpandTree(
            obj=obj,
            relation=relation,
            root=_parse_expand_node(tree.root),
        )

    async def close(self) -> None:
        await self._client.close()


def _parse_expand_node(raw: _ExpandNodeView) -> AuthzExpandNode:
    relation = raw.name if isinstance(raw.name, str) else ""
    users: list[str] = []
    leaf = raw.leaf
    if leaf is not None and leaf.users is not None and leaf.users.users is not None:
        users.extend(leaf.users.users)
    children: tuple[AuthzExpandNode, ...] = ()
    union = raw.union
    if union is not None and union.nodes is not None:
        children = tuple(_parse_expand_node(child) for child in union.nodes)
    return AuthzExpandNode(relation=relation, users=tuple(users), children=children)
