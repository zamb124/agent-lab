"""Private OpenFGA SDK wrapper. Apps must not import this module."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping, Sequence
from typing import Final, Protocol

from openfga_sdk import ClientConfiguration, OpenFgaClient, ReadRequestTupleKey
from openfga_sdk.client.models import (
    ClientBatchCheckItem,
    ClientBatchCheckRequest,
    ClientBatchCheckResponse,
    ClientCheckRequest,
    ClientExpandRequest,
    ClientListObjectsRequest,
    ClientTuple,
    ClientWriteRequest,
)
from openfga_sdk.client.models.list_users_request import ClientListUsersRequest
from openfga_sdk.client.models.write_conflict_opts import (
    ClientWriteRequestOnDuplicateWrites,
    ClientWriteRequestOnMissingDeletes,
    ConflictOptions,
)
from openfga_sdk.credentials import CredentialConfiguration, Credentials
from openfga_sdk.exceptions import ApiException, OpenApiException
from openfga_sdk.models import ConsistencyPreference, FgaObject, UserTypeFilter
from openfga_sdk.models.expand_response import ExpandResponse

from core.authz.errors import AuthzConfigError, AuthzUnavailable
from core.authz.ids import to_fga_object_id
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzConsistency, AuthzObjectType, AuthzRelation
from core.imports import typed_view
from core.logging import get_logger

logger = get_logger(__name__)

_OpenFgaTransportError: Final = (ApiException, OpenApiException, OSError, TimeoutError)
_WRITE_RETRY_ATTEMPTS: Final = 5
_WRITE_CONFLICT_MARKER: Final = "transactional write failed due to conflict"
_WRITE_RETRYABLE_STATUSES: Final = frozenset({409, 429, 500, 502, 503, 504})
# OpenFGA default OPENFGA_MAX_CHECKS_PER_BATCH_CHECK is 50. Chunk=10 turns a
# 500-id list page into 50 sequential RPCs (and a leftover catalog into hundreds);
# that HOL saturates the shared store so CRM/A2A Checks stall. One RPC of 50 is
# the designed batch size.
_BATCH_CHECK_CHUNK: Final = 50


def _is_openfga_write_retryable(exc: BaseException) -> bool:
    """Retryable OpenFGA write: concurrent 409, overload 5xx, rate-limit.

    ``deadline_exceeded`` is not retried: repeating a 30s timed-out write
    amplifies store overload (xdist + large BatchCheck).
    """
    message = str(exc).lower()
    if "deadline_exceeded" in message or "request deadline exceeded" in message:
        return False
    if isinstance(exc, ApiException):
        status = _api_exception_view(exc).status
        if isinstance(status, int) and status in _WRITE_RETRYABLE_STATUSES:
            return True
        if exc.is_retryable():
            return True
    return _WRITE_CONFLICT_MARKER in message


def _consistency_options(
    consistency: AuthzConsistency | None,
) -> dict[str, int | str | dict[str, int | str]] | None:
    if consistency is None:
        return None
    preference = (
        ConsistencyPreference.HIGHER_CONSISTENCY
        if consistency is AuthzConsistency.HIGHER_CONSISTENCY
        else ConsistencyPreference.MINIMIZE_LATENCY
    )
    return {"consistency": str(preference)}


class _CheckResponseView(Protocol):
    allowed: bool | None


class _ListObjectsResponseView(Protocol):
    objects: list[str] | None


class _FgaObjectView(Protocol):
    type: str | None
    id: str | None


class _UsersetUserView(Protocol):
    type: str | None
    id: str | None
    relation: str | None


class _TypedWildcardView(Protocol):
    type: str | None


class _ListUserEntryView(Protocol):
    object: _FgaObjectView | None
    userset: _UsersetUserView | None
    wildcard: _TypedWildcardView | None


class _ListUsersResponseView(Protocol):
    users: list[_ListUserEntryView] | None


class _TupleKeyView(Protocol):
    user: str | None
    relation: str | None
    object: str | None


class _TupleView(Protocol):
    key: _TupleKeyView | None


class _ReadResponseView(Protocol):
    tuples: list[_TupleView] | None
    continuation_token: str | None


_FgaCallOptions = Mapping[str, int | str | dict[str, int | str] | ConflictOptions]


class _OpenFgaSdk(Protocol):
    def check(
        self,
        body: ClientCheckRequest,
        *,
        options: _FgaCallOptions | None,
    ) -> Awaitable[_CheckResponseView]: ...

    def list_objects(
        self,
        body: ClientListObjectsRequest,
        *,
        options: _FgaCallOptions | None,
    ) -> Awaitable[_ListObjectsResponseView]: ...

    def list_users(
        self,
        body: ClientListUsersRequest,
        *,
        options: _FgaCallOptions | None,
    ) -> Awaitable[_ListUsersResponseView]: ...

    def write(
        self,
        body: ClientWriteRequest,
        *,
        options: _FgaCallOptions | None,
    ) -> Awaitable[None]: ...

    def expand(
        self,
        body: ClientExpandRequest,
        *,
        options: _FgaCallOptions | None,
    ) -> Awaitable[ExpandResponse]: ...

    def read(
        self,
        body: ReadRequestTupleKey,
        *,
        options: _FgaCallOptions | None,
    ) -> Awaitable[_ReadResponseView]: ...


class _ApiExceptionView(Protocol):
    status: int | None
    body: bytes | str | None


def _openfga_sdk(client: OpenFgaClient) -> _OpenFgaSdk:
    return typed_view(client, OpenFgaClient, _OpenFgaSdk)


def _api_exception_view(exc: ApiException) -> _ApiExceptionView:
    return typed_view(exc, ApiException, _ApiExceptionView)


def _fga_context(
    context: Mapping[str, str | int] | None,
) -> dict[str, str | int] | None:
    if context is None:
        return None
    return dict(context)


class OpenFgaAuthzClient:
    """Thin async wrapper around OpenFgaClient."""

    _api_url: Final[str]
    _store_id: Final[str]
    _authorization_model_id: Final[str]
    _api_token: Final[str | None]
    _timeout_ms: Final[int]
    _configuration: Final[ClientConfiguration]
    _client: OpenFgaClient | None

    def __init__(
        self,
        *,
        api_url: str,
        store_id: str,
        authorization_model_id: str,
        api_token: str | None,
        timeout_ms: int,
    ) -> None:
        if not api_url:
            raise AuthzConfigError("openfga.api_url is required")
        self._api_url = api_url
        self._store_id = store_id
        self._authorization_model_id = authorization_model_id
        self._api_token = api_token
        self._timeout_ms = timeout_ms
        credentials = Credentials(method="none")
        if api_token:
            credentials = Credentials(
                method="api_token",
                configuration=CredentialConfiguration(api_token=api_token),
            )
        self._configuration = ClientConfiguration(
            api_url=api_url,
            store_id=store_id or None,
            authorization_model_id=authorization_model_id or None,
            credentials=credentials,
            timeout_millisec=timeout_ms,
        )
        self._client = None

    def _assert_configured(self) -> None:
        if not self._store_id or not self._authorization_model_id:
            raise AuthzUnavailable(
                "OpenFGA store_id/authorization_model_id are not configured"
            )

    async def _get_client(self) -> OpenFgaClient:
        self._assert_configured()
        if self._client is None:
            self._client = OpenFgaClient(self._configuration)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

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
        client = _openfga_sdk(await self._get_client())
        request = ClientCheckRequest(
            user=subject.fga_user,
            relation=relation.value,
            object=obj.fga_id,
            contextual_tuples=_to_client_tuples(contextual_tuples),
            context=_fga_context(context),
        )
        try:
            response = await client.check(request, options=_consistency_options(consistency))
        except _OpenFgaTransportError as exc:
            raise AuthzUnavailable(f"OpenFGA check failed: {exc}") from exc
        if not isinstance(response.allowed, bool):
            raise AuthzUnavailable("OpenFGA check response missing allowed:bool")
        return response.allowed

    async def batch_check(
        self,
        items: Sequence[AuthzCheckItem],
        *,
        consistency: AuthzConsistency | None = None,
    ) -> list[bool]:
        if not items:
            return []
        ordered: list[bool] = []
        for start in range(0, len(items), _BATCH_CHECK_CHUNK):
            chunk = items[start : start + _BATCH_CHECK_CHUNK]
            ordered.extend(
                await self._batch_check_chunk(chunk, consistency=consistency)
            )
        return ordered

    async def _batch_check_chunk(
        self,
        items: Sequence[AuthzCheckItem],
        *,
        consistency: AuthzConsistency | None,
    ) -> list[bool]:
        client = await self._get_client()
        # OpenFGA BatchCheckItem.correlation_id: ^[\w\d-]{1,36}$ — object ids
        # платформы длиннее; ordinal index — стабильный ключ порядка ответа.
        request = ClientBatchCheckRequest(
            checks=[
                ClientBatchCheckItem(
                    user=item.subject.fga_user,
                    relation=item.relation.value,
                    object=item.obj.fga_id,
                    correlation_id=str(index),
                )
                for index, item in enumerate(items)
            ]
        )
        try:
            response: ClientBatchCheckResponse = await client.batch_check(
                request, options=_consistency_options(consistency)
            )
        except _OpenFgaTransportError as exc:
            raise AuthzUnavailable(f"OpenFGA batch_check failed: {exc}") from exc
        result_by_id: dict[str, bool] = {}
        for entry in response.result:
            if entry.error is not None:
                raise AuthzUnavailable(
                    f"OpenFGA batch_check item error correlation_id={entry.correlation_id}: {entry.error}"
                )
            result_by_id[entry.correlation_id] = entry.allowed
        ordered: list[bool] = []
        for index, item in enumerate(items):
            key = str(index)
            if key not in result_by_id:
                raise AuthzUnavailable(
                    f"OpenFGA batch_check missing correlation_id={key} (item={item.correlation_id})"
                )
            ordered.append(result_by_id[key])
        return ordered

    async def list_objects(
        self,
        subject: AuthzSubject,
        relation: AuthzRelation,
        object_type: AuthzObjectType,
        *,
        consistency: AuthzConsistency | None = None,
    ) -> list[AuthzObject]:
        client = _openfga_sdk(await self._get_client())
        request = ClientListObjectsRequest(
            user=subject.fga_user,
            relation=relation.value,
            type=object_type.value,
        )
        try:
            response = await client.list_objects(
                request, options=_consistency_options(consistency)
            )
        except _OpenFgaTransportError as exc:
            raise AuthzUnavailable(f"OpenFGA list_objects failed: {exc}") from exc
        if response.objects is None:
            raise AuthzUnavailable("OpenFGA list_objects response missing objects")
        objects: list[AuthzObject] = []
        for raw in response.objects:
            try:
                objects.append(AuthzObject.from_fga_id(raw))
            except AuthzConfigError as exc:
                raise AuthzUnavailable(
                    f"OpenFGA list_objects returned invalid object id: {raw!r}"
                ) from exc
        return objects

    async def list_users(
        self,
        obj: AuthzObject,
        relation: AuthzRelation,
        *,
        user_filters: Sequence[AuthzObjectType] | None = None,
        consistency: AuthzConsistency | None = None,
    ) -> list[str]:
        client = _openfga_sdk(await self._get_client())
        filters = [
            (
                UserTypeFilter(type=t.value, relation="member")
                if t in (AuthzObjectType.COMPANY, AuthzObjectType.GROUP)
                else UserTypeFilter(type=t.value)
            )
            for t in (user_filters if user_filters is not None else (AuthzObjectType.USER,))
        ]
        request = ClientListUsersRequest(
            object=FgaObject(
                type=obj.object_type.value,
                id=to_fga_object_id(obj.object_type, obj.object_key),
            ),
            relation=relation.value,
            user_filters=list(filters),
        )
        try:
            response = await client.list_users(
                request, options=_consistency_options(consistency)
            )
        except _OpenFgaTransportError as exc:
            detail = str(exc).strip()
            if not detail and isinstance(exc, ApiException):
                viewed = _api_exception_view(exc)
                detail = f"status={viewed.status!r} body={viewed.body!r}"
            if not detail:
                detail = repr(exc)
            raise AuthzUnavailable(f"OpenFGA list_users failed: {detail}") from exc
        if response.users is None:
            raise AuthzUnavailable("OpenFGA list_users response missing users")
        users: list[str] = []
        for entry in response.users:
            if entry.object is not None:
                users.append(_format_list_user_object(entry.object))
                continue
            if entry.userset is not None:
                users.append(_format_list_user_userset(entry.userset))
                continue
            if entry.wildcard is not None:
                users.append(_format_list_user_wildcard(entry.wildcard))
                continue
            raise AuthzUnavailable(f"unsupported list_users entry: {entry!r}")
        return users

    async def write_and_delete(
        self,
        writes: Sequence[AuthzTuple],
        deletes: Sequence[AuthzTuple],
    ) -> None:
        write_keys = {
            (item.subject.fga_user, item.relation.value, item.obj.fga_id): item
            for item in writes
        }
        delete_keys = {
            (item.subject.fga_user, item.relation.value, item.obj.fga_id): item
            for item in deletes
        }
        overlap = set(write_keys) & set(delete_keys)
        for key in overlap:
            del write_keys[key]
            del delete_keys[key]
        writes_unique = list(write_keys.values())
        deletes_unique = list(delete_keys.values())
        if not writes_unique and not deletes_unique:
            return
        client = _openfga_sdk(await self._get_client())
        request = ClientWriteRequest(
            writes=_to_client_tuples(writes_unique),
            deletes=_to_client_tuples(deletes_unique),
        )
        write_options = {
            "conflict": ConflictOptions(
                on_duplicate_writes=ClientWriteRequestOnDuplicateWrites.IGNORE,
                on_missing_deletes=ClientWriteRequestOnMissingDeletes.IGNORE,
            )
        }
        for attempt_index in range(_WRITE_RETRY_ATTEMPTS):
            try:
                _ = await client.write(request, options=write_options)
                return
            except _OpenFgaTransportError as exc:
                if (
                    attempt_index + 1 >= _WRITE_RETRY_ATTEMPTS
                    or not _is_openfga_write_retryable(exc)
                ):
                    raise AuthzUnavailable(f"OpenFGA write failed: {exc}") from exc
                delay_sec = 0.05 * (1 << attempt_index)
                await asyncio.sleep(delay_sec)

    async def expand(
        self,
        obj: AuthzObject,
        relation: AuthzRelation,
        *,
        consistency: AuthzConsistency | None = None,
    ) -> ExpandResponse:
        client = _openfga_sdk(await self._get_client())
        request = ClientExpandRequest(relation=relation.value, object=obj.fga_id)
        try:
            return await client.expand(request, options=_consistency_options(consistency))
        except _OpenFgaTransportError as exc:
            raise AuthzUnavailable(f"OpenFGA expand failed: {exc}") from exc

    async def list_tuples(
        self,
        obj: AuthzObject | None = None,
        *,
        object_type: AuthzObjectType | None = None,
        relation: AuthzRelation | None = None,
        subject: AuthzSubject | None = None,
        page_size: int = 100,
        consistency: AuthzConsistency | None = None,
    ) -> list[AuthzTuple]:
        """Прямые tuples (OpenFGA Read), без TTU-развёртки.

        Конкретный объект — ``obj``. Type + subject — Read ``type:`` + user
        (OpenFGA 1.18 требует object id или user). Type без subject — полный
        Read store и фильтр по типу (backfill / admin), не ``object="type:"``.
        """
        if obj is None and object_type is None:
            raise AuthzConfigError("list_tuples requires obj or object_type")
        client = _openfga_sdk(await self._get_client())
        type_filter: AuthzObjectType | None = None
        relation_filter: AuthzRelation | None = None
        if obj is not None:
            key_fields: dict[str, str] = {"object": obj.fga_id}
            if subject is not None:
                key_fields["user"] = subject.fga_user
            if relation is not None:
                key_fields["relation"] = relation.value
            body = ReadRequestTupleKey(**key_fields)
        elif subject is not None:
            if object_type is None:
                raise AuthzConfigError("list_tuples requires obj or object_type")
            key_fields = {"object": f"{object_type.value}:", "user": subject.fga_user}
            if relation is not None:
                key_fields["relation"] = relation.value
            body = ReadRequestTupleKey(**key_fields)
        else:
            type_filter = object_type
            relation_filter = relation
            body = ReadRequestTupleKey()
        collected: list[AuthzTuple] = []
        continuation_token: str | None = None
        while True:
            options: dict[str, int | str | dict[str, int | str]] = {
                "page_size": page_size,
            }
            consistency_opts = _consistency_options(consistency)
            if consistency_opts is not None:
                options.update(consistency_opts)
            if continuation_token is not None:
                options["continuation_token"] = continuation_token
            try:
                response = await client.read(body, options=options)
            except _OpenFgaTransportError as exc:
                raise AuthzUnavailable(f"OpenFGA read failed: {exc}") from exc
            raw_tuples = response.tuples
            if raw_tuples is None:
                raise AuthzUnavailable("OpenFGA read response missing tuples")
            for entry in raw_tuples:
                key = entry.key
                if key is None:
                    raise AuthzUnavailable(f"OpenFGA read tuple missing key: {entry!r}")
                if (
                    not isinstance(key.user, str)
                    or not isinstance(key.relation, str)
                    or not isinstance(key.object, str)
                ):
                    raise AuthzUnavailable(f"OpenFGA read tuple key incomplete: {key!r}")
                parsed = AuthzTuple(
                    subject=AuthzSubject.from_fga_user(key.user),
                    relation=AuthzRelation(key.relation),
                    obj=AuthzObject.from_fga_id(key.object),
                )
                if type_filter is not None and parsed.obj.object_type is not type_filter:
                    continue
                if (
                    relation_filter is not None
                    and parsed.relation is not relation_filter
                ):
                    continue
                collected.append(parsed)
            continuation_token = response.continuation_token
            if continuation_token is None or continuation_token == "":
                break
        return collected


def _format_list_user_object(raw: _FgaObjectView) -> str:
    if not isinstance(raw.type, str) or not isinstance(raw.id, str):
        raise AuthzUnavailable(f"unsupported list_users object entry: {raw!r}")
    return f"{raw.type}:{raw.id}"


def _format_list_user_userset(raw: _UsersetUserView) -> str:
    if (
        not isinstance(raw.type, str)
        or not isinstance(raw.id, str)
        or not isinstance(raw.relation, str)
    ):
        raise AuthzUnavailable(f"unsupported list_users userset entry: {raw!r}")
    return f"{raw.type}:{raw.id}#{raw.relation}"


def _format_list_user_wildcard(raw: _TypedWildcardView) -> str:
    if isinstance(raw.type, str):
        return f"{raw.type}:*"
    return "user:*"


def _to_client_tuples(
    tuples: Sequence[AuthzTuple] | None,
) -> list[ClientTuple] | None:
    if tuples is None:
        return None
    return [
        ClientTuple(
            user=item.subject.fga_user,
            relation=item.relation.value,
            object=item.obj.fga_id,
        )
        for item in tuples
    ]
