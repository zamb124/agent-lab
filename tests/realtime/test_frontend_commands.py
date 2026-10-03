"""Live Centrifugo RPC + REST identity для всех FRONTEND_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /frontend/api/internal/realtime/command` → тот же `op_*`. REST — Granian :9004.

Мутации настроек компании (AI-провайдеры, тариф, embed, LinnexAgent, roster) идут от
одноразового principal со своей компанией, чтобы не трогать `system`, на котором
держатся остальные тесты стека.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

import pytest
from httpx import AsyncClient, Response

from apps.frontend.di import FrontendDi
from apps.frontend.realtime.command_router import FRONTEND_OPERATIONS
from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation
from core.files.company_storage_service import CompanyStorageService
from core.models.identity_models import Company, User
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.agent._helpers import create_pairing_via_http, register_device_via_http
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.fixtures.auth import set_test_company_member_roles
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_API = "/frontend/api"
_FLOWS_API = "/flows/api/v1"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"[\s\-_](?:ws|rest|WS|REST)[-_]")
_VOLATILE_KEYS = frozenset(
    {
        "created_at",
        "updated_at",
        "created_by",
        "expires_at",
        "last_seen_at",
        "paired_at",
        "last_used",
        "request_id",
        "trace_id",
    }
)
_PUBLIC_HOST = "localhost:9004"
_PUBLIC_ORIGIN = f"http://{_PUBLIC_HOST}"

PayloadStrategy = Literal["body", "body_minus_path", "query", "none", "body_key"]
CompareMode = Literal["normalized", "marker_row", "succeeded_only"]
PrincipalKind = Literal["system", "throwaway"]


@dataclass
class Principal:
    token: str
    headers: dict[str, str]
    user_id: str
    company_id: str


@dataclass
class LiveCtx:
    frontend: AsyncClient
    flows: AsyncClient
    frontend_di: FrontendDi
    principal: Principal
    unique_id: str
    suffix: str
    marker: str | None = None

    @property
    def headers(self) -> dict[str, str]:
        return self.principal.headers

    def token(self) -> str:
        return f"{self.suffix}-{self.unique_id}"


SetupFn = Callable[[LiveCtx], Awaitable[JsonObject]]


@dataclass(frozen=True)
class RestMirror:
    method: str
    url: str
    strategy: PayloadStrategy
    body_key: str | None = None
    drop: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class OpCase:
    rest: RestMirror
    setup: SetupFn
    same_resource: bool
    compare: CompareMode = "normalized"
    principal: PrincipalKind = "system"
    marker_key: str = "name"
    volatile: frozenset[str] = field(default_factory=frozenset)
    expect: Literal["succeeded", "failed"] = "succeeded"


async def _expect_json(response: Response, *, ok: tuple[int, ...], label: str) -> JsonObject:
    assert response.status_code in ok, f"{label} {response.status_code}: {response.text}"
    return require_json_object(response.json(), label)


async def _empty(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {}


def _payload(**values: JsonValue) -> SetupFn:
    async def setup(ctx: LiveCtx) -> JsonObject:
        _ = ctx
        return dict(values)

    return setup


# --- seeding -------------------------------------------------------------------------


async def seed_principal(frontend_di, *, unique_id: str) -> Principal:
    """Отдельная компания + admin для мутаций, которые нельзя делать на `system`."""
    user_id = f"live-frontend-user-{unique_id}"
    company_id = f"live-frontend-co-{unique_id}"
    roles = ["owner", "admin"]
    user = User(
        user_id=user_id,
        name=f"Live frontend {unique_id}",
        emails=[f"{user_id}@test.local"],
        companies={company_id: roles},
        active_company_id=company_id,
    )
    _ = await User.set(user)
    company = make_test_company(
        company_id=company_id,
        name=f"Live frontend company {unique_id}",
        owner_user_id=user_id,
        members={user_id: roles},
    )
    company.subdomain = company_id
    _ = await Company.set(company)
    await set_test_company_member_roles(
        frontend_di.authz_service, company_id=company_id, user_id=user_id, roles=roles
    )
    token = get_token_service().create_token(user_id, company_id=company_id, roles=roles)
    return Principal(token=token, headers={"Authorization": f"Bearer {token}"}, user_id=user_id, company_id=company_id)


async def _seed_member(ctx: LiveCtx, *, roles: list[str]) -> str:
    user_id = f"live-member-{ctx.token()}"
    member = User(
        user_id=user_id,
        name=f"Live member {ctx.token()}",
        emails=[f"{user_id}@test.local"],
        companies={ctx.principal.company_id: roles},
        active_company_id=ctx.principal.company_id,
    )
    _ = await User.set(member)
    await set_test_company_member_roles(
        ctx.frontend_di.authz_service,
        company_id=ctx.principal.company_id,
        user_id=user_id,
        roles=roles,
    )
    return user_id


async def _seed_target_company(ctx: LiveCtx) -> Company:
    company_id = f"live-target-{ctx.token()}"
    company = make_test_company(
        company_id=company_id,
        name=f"Live target {ctx.token()}",
        owner_user_id="seed_owner",
        members={"seed_owner": ["owner", "admin"]},
    )
    company.subdomain = company_id
    _ = await Company.set(company)
    return company


async def _create_flow(ctx: LiveCtx) -> str:
    flow_id = f"live-frontend-flow-{ctx.token()}"
    body: JsonObject = {
        "flow_id": flow_id,
        "name": f"Live frontend flow {ctx.token()}",
        "entry": "echo",
        "nodes": {
            "echo": {
                "type": "code",
                "code": "async def run(args, state):\n    state['answer'] = '42'\n    return state\n",
            }
        },
        "edges": [{"from_node": "echo", "to_node": None}],
    }
    response = await ctx.flows.post(f"{_FLOWS_API}/flows/", headers=ctx.headers, json=body)
    _ = await _expect_json(response, ok=(200, 201), label="flow_create")
    return flow_id


def _embed_body(ctx: LiveCtx, flow_id: str) -> JsonObject:
    return {
        "name": f"Live embed {ctx.token()}",
        "flow_id": flow_id,
        "branch_id": "default",
        "allowed_origins": [],
    }


async def _create_embed(ctx: LiveCtx) -> JsonObject:
    flow_id = await _create_flow(ctx)
    response = await ctx.frontend.post(f"{_API}/embed/configs", headers=ctx.headers, json=_embed_body(ctx, flow_id))
    created = await _expect_json(response, ok=(200,), label="embed_create")
    ctx.marker = str(created["embed_id"])
    return created


async def _create_api_key(ctx: LiveCtx) -> str:
    response = await ctx.frontend.post(
        f"{_API}/api-keys", headers=ctx.headers, json={"name": f"Live key {ctx.token()}", "scopes": ["agents:read"]}
    )
    created = await _expect_json(response, ok=(200,), label="api_key_create")
    key_id = str(created["key_id"])
    ctx.marker = key_id
    return key_id


async def _create_namespace(ctx: LiveCtx, *, name: str | None = None) -> str:
    resolved_name = name if name is not None else f"live-ns-{ctx.token()}"
    response = await ctx.frontend.post(
        f"{_API}/namespaces", headers=ctx.headers, json={"name": resolved_name, "description": "identity"}
    )
    _ = await _expect_json(response, ok=(200, 201), label="namespace_create")
    ctx.marker = resolved_name
    return resolved_name


async def _register_device(ctx: LiveCtx) -> str:
    pairing = await create_pairing_via_http(ctx.frontend, auth_cookie=ctx.principal.token)
    pairing_code = pairing["pairing_code"]
    device_id = f"live-device-{ctx.token()}"
    _ = await register_device_via_http(
        ctx.frontend,
        pairing_code=str(pairing_code),
        device_id=device_id,
        device_name=f"Live device {ctx.token()}",
        os_name="darwin",
        hostname=f"host-{ctx.token()}",
    )
    return device_id


async def _custom_provider_body(ctx: LiveCtx) -> JsonObject:
    """Тело custom-провайдера; id уникален на transport, чтобы create шёл дважды."""
    return {
        "id": f"live-{ctx.token()}",
        "label": f"Live custom {ctx.token()}",
        "base_url": "https://example.invalid/v1",
        "api_key": "live-secret",
        "capabilities": ["llm_chat"],
        "model_by_capability": {"llm_chat": "live-model"},
    }


async def _create_custom_provider(ctx: LiveCtx) -> str:
    body = await _custom_provider_body(ctx)
    response = await ctx.frontend.post(f"{_API}/settings/ai-providers/custom", headers=ctx.headers, json=body)
    _ = await _expect_json(response, ok=(200,), label="custom_provider_create")
    return str(body["id"])


async def _get(ctx: LiveCtx, path: str) -> JsonObject:
    response = await ctx.frontend.get(f"{_API}{path}", headers=ctx.headers)
    return await _expect_json(response, ok=(200,), label=f"GET {path}")


# --- setups ----------------------------------------------------------------------------


async def _setup_company_settings_update(ctx: LiveCtx) -> JsonObject:
    return {"name": f"Live frontend company {ctx.unique_id}"}


async def _setup_team_list(ctx: LiveCtx) -> JsonObject:
    ctx.marker = ctx.principal.user_id
    return {}


async def _setup_team_update(ctx: LiveCtx) -> JsonObject:
    if ctx.marker is None:
        ctx.marker = await _seed_member(ctx, roles=["viewer"])
    return {"user_id": ctx.marker, "roles": ["developer"]}


async def _setup_team_remove(ctx: LiveCtx) -> JsonObject:
    return {"user_id": await _seed_member(ctx, roles=["viewer"])}


async def _setup_api_keys_list(ctx: LiveCtx) -> JsonObject:
    _ = await _create_api_key(ctx)
    return {"limit": 200, "offset": 0}


async def _setup_api_key_create(ctx: LiveCtx) -> JsonObject:
    return {"name": f"Live key {ctx.token()}", "scopes": ["agents:read"]}


async def _setup_api_key_update(ctx: LiveCtx) -> JsonObject:
    return {"key_id": await _create_api_key(ctx), "name": "Live key renamed"}


async def _setup_api_key_remove(ctx: LiveCtx) -> JsonObject:
    return {"key_id": await _create_api_key(ctx)}


async def _setup_namespaces_list(ctx: LiveCtx) -> JsonObject:
    _ = await _create_namespace(ctx, name=f"0live-ns-{ctx.token()}")
    return {"limit": 200, "offset": 0}


async def _setup_namespace_create(ctx: LiveCtx) -> JsonObject:
    return {"name": f"live-ns-{ctx.token()}", "description": "identity"}


async def _setup_slug_check(ctx: LiveCtx) -> JsonObject:
    return {"slug": f"live-slug-{ctx.unique_id}"}



async def _setup_company_create(ctx: LiveCtx) -> JsonObject:
    return {"name": f"Live created {ctx.token()}", "slug": f"live-created-{ctx.token()}", "public_host": _PUBLIC_HOST}


async def _setup_system_access_grant(ctx: LiveCtx) -> JsonObject:
    company = await _seed_target_company(ctx)
    return {"company_id": company.company_id, "role": "viewer"}


async def _setup_system_access_revoke(ctx: LiveCtx) -> JsonObject:
    company = await _seed_target_company(ctx)
    response = await ctx.frontend.post(
        f"{_API}/companies/{company.company_id}/system-access", headers=ctx.headers, json={"role": "viewer"}
    )
    _ = await _expect_json(response, ok=(200,), label="system_access_grant")
    return {"company_id": company.company_id}


async def _setup_explorer_by_user(ctx: LiveCtx) -> JsonObject:
    return {"user_id": ctx.principal.user_id}


def _flow_object_key(ctx: LiveCtx, flow_id: str) -> str:
    return AuthzObject.flow(flow_id, company_id=ctx.principal.company_id).object_key


async def _setup_explorer_by_object(ctx: LiveCtx) -> JsonObject:
    return {"object_type": "flow", "object_key": _flow_object_key(ctx, await _create_flow(ctx))}


async def _setup_explorer_why(ctx: LiveCtx) -> JsonObject:
    return {
        "user_id": ctx.principal.user_id,
        "object_type": "flow",
        "object_key": _flow_object_key(ctx, await _create_flow(ctx)),
    }


async def _setup_explorer_revoke(ctx: LiveCtx) -> JsonObject:
    flow_id = await _create_flow(ctx)
    subject_id = f"live-explorer-{ctx.token()}"
    await ctx.frontend_di.authz_service.write(
        [
            AuthzTuple(
                subject=AuthzSubject.user(subject_id),
                relation=AuthzRelation.VIEWER,
                obj=AuthzObject.flow(flow_id, company_id=ctx.principal.company_id),
            )
        ]
    )
    return {
        "object_type": "flow",
        "object_key": _flow_object_key(ctx, flow_id),
        "relation": "viewer",
        "subject_kind": "user",
        "subject_id": subject_id,
    }


async def _setup_plan_change(ctx: LiveCtx) -> JsonObject:
    """Смена на другой тариф: повтор текущего отклоняется как ws_invalid_payload."""
    subscription = await _get(ctx, "/billing/subscription")
    current = str(subscription["plan"])
    return {"plan": "basic" if current != "basic" else "premium"}


async def _setup_balance_grant(ctx: LiveCtx) -> JsonObject:
    company = await _seed_target_company(ctx)
    return {"company_id": company.company_id, "amount": 1.0, "note": "identity"}


async def _setup_company_resolve(ctx: LiveCtx) -> JsonObject:
    return {"q": ctx.principal.company_id}


def _price_catalog_without_tools(catalog: JsonObject) -> JsonObject:
    return {category: prices for category, prices in catalog.items() if category != "tool"}


async def _setup_prices_update(ctx: LiveCtx) -> JsonObject:
    prices = await _get(ctx, "/platform-billing/prices")
    return {"catalog": _price_catalog_without_tools(require_json_object(prices["effective"], "prices.effective"))}


async def _setup_company_id(ctx: LiveCtx) -> JsonObject:
    return {"company_id": ctx.principal.company_id}


async def _setup_settlement_rules_update(ctx: LiveCtx) -> JsonObject:
    rules = await _get(ctx, f"/platform-billing/settlement-rules/{ctx.principal.company_id}")
    return {"company_id": ctx.principal.company_id, "document": require_json_object(rules["document"], "rules")}


async def _setup_company_prices_update(ctx: LiveCtx) -> JsonObject:
    prices = await _get(ctx, f"/platform-billing/prices/company/{ctx.principal.company_id}")
    return {
        "company_id": ctx.principal.company_id,
        "catalog": _price_catalog_without_tools(require_json_object(prices["effective"], "prices.effective")),
    }


async def _setup_trace_tree(ctx: LiveCtx) -> JsonObject:
    return {"trace_id": f"{ctx.unique_id}{uuid.uuid4().hex}"[:32]}


async def _seed_catalog_model(ctx: LiveCtx) -> str:
    model_id = f"live/identity-{ctx.unique_id}"
    await AIModelRecord.set(
        AIModelRecord(
            provider="openrouter",
            model_id=model_id,
            capabilities=(AICapability.LLM_CHAT,),
            input_modalities=("text",),
            output_modalities=("text",),
            context_length=262144,
            supported_parameters=("tools",),
            is_free=True,
            free_reason="zero_price_catalog",
            raw={"name": "Live identity model"},
        )
    )
    return model_id


async def _setup_score_upsert(ctx: LiveCtx) -> JsonObject:
    return {
        "provider": "openrouter",
        "model_id": await _seed_catalog_model(ctx),
        "capability": "llm_chat",
        "enabled": True,
        "editorial_prior": 0.0,
        "note": "identity",
    }


async def _setup_score_delete(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_score_upsert(ctx)
    response = await ctx.frontend.put(f"{_API}/platform/llm-model-scores", headers=ctx.headers, json=payload)
    _ = await _expect_json(response, ok=(200,), label="score_upsert")
    return {"capability": payload["capability"], "provider": payload["provider"], "model_id": payload["model_id"]}


_VOICE_CAPABILITY_PAYLOAD: JsonObject = {"capability": "voice_tts", "provider": "litserve"}


async def _setup_capability_remove(ctx: LiveCtx) -> JsonObject:
    response = await ctx.frontend.put(
        f"{_API}/settings/ai-providers/voice_tts", headers=ctx.headers, json={"provider": "litserve"}
    )
    _ = await _expect_json(response, ok=(200,), label="capability_put")
    return {"capability": "voice_tts"}


async def _setup_llm_context_remove(ctx: LiveCtx) -> JsonObject:
    response = await ctx.frontend.put(f"{_API}/settings/ai-providers/llm-context", headers=ctx.headers, json={"mode": "window"})
    _ = await _expect_json(response, ok=(200,), label="llm_context_put")
    return {}


async def _setup_custom_update(ctx: LiveCtx) -> JsonObject:
    return {"provider_id": await _create_custom_provider(ctx), "label": "Live custom renamed"}


async def _setup_custom_remove(ctx: LiveCtx) -> JsonObject:
    return {"provider_id": await _create_custom_provider(ctx)}


async def _setup_embed_create(ctx: LiveCtx) -> JsonObject:
    return _embed_body(ctx, await _create_flow(ctx))


async def _setup_embed_list(ctx: LiveCtx) -> JsonObject:
    _ = await _create_embed(ctx)
    return {"limit": 200, "offset": 0}


async def _setup_embed_id(ctx: LiveCtx) -> JsonObject:
    created = await _create_embed(ctx)
    return {"embed_id": created["embed_id"]}


async def _setup_embed_update(ctx: LiveCtx) -> JsonObject:
    created = await _create_embed(ctx)
    return {"embed_id": created["embed_id"], "name": "Live embed renamed"}


async def _setup_embed_code(ctx: LiveCtx) -> JsonObject:
    created = await _create_embed(ctx)
    return {"embed_id": created["embed_id"], "public_origin": _PUBLIC_ORIGIN}


async def _setup_device_revoke(ctx: LiveCtx) -> JsonObject:
    return {"device_id": await _register_device(ctx)}


async def _setup_device_policy(ctx: LiveCtx) -> JsonObject:
    return {"device_id": await _register_device(ctx), "policy": {"allowed_roots": ["/tmp/live"], "exec_whitelist": []}}


async def _setup_lead_requests(ctx: LiveCtx) -> JsonObject:
    response = await ctx.frontend.post(
        f"{_API}/leads",
        json={
            "contact_name": f"Live {ctx.token()}",
            "email": f"live-{ctx.unique_id}@test.local",
            "headcount_range": "50_199",
            "interested_products": ["agents"],
        },
    )
    created = await _expect_json(response, ok=(200,), label="lead_create")
    ctx.marker = str(created["lead_request_id"])
    return {"limit": 200}


_EXT_S3 = "http://127.0.0.1:19003"
_EXT_KEY = "extadmin"
_EXT_SECRET = "extadminsecret"


async def _ensure_ext_bucket(bucket: str) -> None:
    import aioboto3

    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=_EXT_S3,
        aws_access_key_id=_EXT_KEY,
        aws_secret_access_key=_EXT_SECRET,
        region_name="us-east-1",
    ) as client:
        try:
            await client.head_bucket(Bucket=bucket)
        except Exception:
            await client.create_bucket(Bucket=bucket)


def _storage_body(*, name: str, bucket: str) -> JsonObject:
    return {
        "name": name,
        "provider": "seaweedfs",
        "endpoint_url": _EXT_S3,
        "region_name": "us-east-1",
        "bucket_name": bucket,
        "path_style": True,
        "access_key_id": _EXT_KEY,
        "secret_access_key": _EXT_SECRET,
    }


async def _setup_storage_probe(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    await _ensure_ext_bucket("ext-a")
    body = _storage_body(name="probe", bucket="ext-a")
    body.pop("name")
    return body


async def _setup_storage_create(ctx: LiveCtx) -> JsonObject:
    await _ensure_ext_bucket("ext-a")
    return _storage_body(name=f"live-{ctx.token()}", bucket="ext-a")


async def _create_live_storage(ctx: LiveCtx, *, bucket: str, name: str) -> str:
    await _ensure_ext_bucket(bucket)
    row = await CompanyStorageService().create(
        ctx.principal.company_id,
        name=name,
        provider="seaweedfs",
        endpoint_url=_EXT_S3,
        region_name="us-east-1",
        bucket_name=bucket,
        path_style=True,
        access_key_id=_EXT_KEY,
        secret_access_key=_EXT_SECRET,
    )
    return row.storage_id


async def _setup_storage_rotate(ctx: LiveCtx) -> JsonObject:
    storage_id = await _create_live_storage(ctx, bucket="ext-a", name=f"rotate-{ctx.token()}")
    return {
        "storage_id": storage_id,
        "access_key_id": _EXT_KEY,
        "secret_access_key": _EXT_SECRET,
    }


async def _setup_storage_delete(ctx: LiveCtx) -> JsonObject:
    storage_id = await _create_live_storage(ctx, bucket="ext-a", name=f"delete-{ctx.token()}")
    return {"storage_id": storage_id}


async def _setup_storage_route(ctx: LiveCtx) -> JsonObject:
    storage_id = await _create_live_storage(ctx, bucket="ext-a", name=f"route-{ctx.unique_id}")
    return {"storage_id": storage_id, "source_kind": "mail_message"}


async def _setup_storage_migration_start(ctx: LiveCtx) -> JsonObject:
    source = await _create_live_storage(ctx, bucket="ext-a", name=f"src-{ctx.token()}")
    target = await _create_live_storage(ctx, bucket="ext-b", name=f"dst-{ctx.token()}")
    return {"source_storage_id": source, "target_storage_id": target}


async def _setup_storage_migration_get(ctx: LiveCtx) -> JsonObject:
    source = await _create_live_storage(ctx, bucket="ext-a", name=f"src-get-{ctx.unique_id}")
    target = await _create_live_storage(ctx, bucket="ext-b", name=f"dst-get-{ctx.unique_id}")
    migration = await CompanyStorageService().start_migration(
        ctx.principal.company_id,
        source_storage_id=source,
        target_storage_id=target,
    )
    return {"storage_migration_id": migration.storage_migration_id}


_CASES: dict[str, OpCase] = {
    "frontend/dashboard/stats_requested": OpCase(
        RestMirror("GET", f"{_API}/dashboard/stats", "none"), _empty, True, "succeeded_only"
    ),
    "frontend/company_settings/get_requested": OpCase(
        RestMirror("GET", f"{_API}/settings/company", "none"), _empty, True, principal="throwaway"
    ),
    "frontend/company_settings/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/settings/company", "body"),
        _setup_company_settings_update,
        True,
        principal="throwaway",
    ),
    "frontend/team/list_requested": OpCase(
        RestMirror("GET", f"{_API}/team/members", "none"), _setup_team_list, True, "marker_row", marker_key="user_id"
    ),
    "frontend/team/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/team/members/{{user_id}}", "body_minus_path"),
        _setup_team_update,
        True,
        principal="throwaway",
    ),
    "frontend/team/remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/team/members/{{user_id}}", "none"),
        _setup_team_remove,
        False,
        principal="throwaway",
        volatile=frozenset({"user_id", "message"}),
    ),
    "frontend/invites/generate_requested": OpCase(
        RestMirror("POST", f"{_API}/invites/generate", "body"), _payload(role="developer"), True, "succeeded_only"
    ),
    "frontend/api_keys/list_requested": OpCase(
        RestMirror("GET", f"{_API}/api-keys", "query"),
        _setup_api_keys_list,
        True,
        "marker_row",
        principal="throwaway",
        marker_key="key_id",
    ),
    "frontend/api_keys/create_requested": OpCase(
        RestMirror("POST", f"{_API}/api-keys", "body"),
        _setup_api_key_create,
        False,
        principal="throwaway",
        volatile=frozenset({"key_id", "secret", "key_prefix"}),
    ),
    "frontend/api_keys/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/api-keys/{{key_id}}", "body_minus_path"),
        _setup_api_key_update,
        True,
        principal="throwaway",
    ),
    "frontend/api_keys/remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/api-keys/{{key_id}}", "none"),
        _setup_api_key_remove,
        False,
        principal="throwaway",
        volatile=frozenset({"key_id"}),
    ),
    "frontend/namespaces/list_requested": OpCase(
        RestMirror("GET", f"{_API}/namespaces", "query"), _setup_namespaces_list, True, "marker_row"
    ),
    "frontend/namespaces/create_requested": OpCase(
        RestMirror("POST", f"{_API}/namespaces", "body"), _setup_namespace_create, False
    ),
    "frontend/namespaces/personal_requested": OpCase(
        RestMirror("GET", f"{_API}/namespaces/me/personal", "none"), _empty, True
    ),
    "frontend/companies/slug_check_requested": OpCase(
        RestMirror("POST", f"{_API}/companies/check-slug", "body"), _setup_slug_check, True
    ),
    "frontend/companies/create_requested": OpCase(
        RestMirror("POST", f"{_API}/companies", "body", drop=frozenset({"public_host"})),
        _setup_company_create,
        False,
        principal="throwaway",
        volatile=frozenset({"company_id"}),
    ),
    "frontend/companies/system_access_grant_requested": OpCase(
        RestMirror("POST", f"{_API}/companies/{{company_id}}/system-access", "body_minus_path"),
        _setup_system_access_grant,
        True,
    ),
    "frontend/companies/system_access_revoke_requested": OpCase(
        RestMirror("DELETE", f"{_API}/companies/{{company_id}}/system-access", "none"),
        _setup_system_access_revoke,
        False,
        volatile=frozenset({"company_id"}),
    ),
    "frontend/authz_explorer/by_user_requested": OpCase(
        RestMirror("GET", f"{_API}/authz/explorer/by-user", "query"), _setup_explorer_by_user, True, "succeeded_only"
    ),
    "frontend/authz_explorer/by_object_requested": OpCase(
        RestMirror("GET", f"{_API}/authz/explorer/by-object", "query"),
        _setup_explorer_by_object,
        True,
        "succeeded_only",
    ),
    "frontend/authz_explorer/why_requested": OpCase(
        RestMirror("GET", f"{_API}/authz/explorer/why", "query"), _setup_explorer_why, True
    ),
    "frontend/authz_explorer/objects_requested": OpCase(
        RestMirror("GET", f"{_API}/authz/explorer/objects", "query"), _payload(q="live", object_type=None), True, "succeeded_only"
    ),
    "frontend/authz_explorer/revoke_requested": OpCase(
        RestMirror("POST", f"{_API}/authz/explorer/revoke", "body"), _setup_explorer_revoke, False
    ),
    "frontend/billing/subscription_requested": OpCase(
        RestMirror("GET", f"{_API}/billing/subscription", "none"), _empty, True, principal="throwaway"
    ),
    "frontend/billing/usage_requested": OpCase(
        RestMirror("GET", f"{_API}/billing/usage", "none"), _empty, True, principal="throwaway"
    ),
    "frontend/billing/plan_change_requested": OpCase(
        RestMirror("PATCH", f"{_API}/billing/plan", "body"),
        _setup_plan_change,
        False,
        "succeeded_only",
        principal="throwaway",
    ),
    # Платёжный провайдер в тестовом стеке не настроен: сверяем одинаковый исход `unavailable`.
    "frontend/billing/topup_requested": OpCase(
        RestMirror("POST", f"{_API}/billing/topup", "body"),
        _payload(amount=100.0, public_host=_PUBLIC_HOST),
        True,
        principal="throwaway",
        expect="failed",
    ),
    "frontend/billing/payment_history_requested": OpCase(
        RestMirror("GET", f"{_API}/billing/history", "none"), _empty, True, principal="throwaway"
    ),
    "frontend/platform_billing/companies_overview_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/companies-billing-overview", "query"),
        _payload(limit=50, offset=0),
        True,
        "succeeded_only",
    ),
    "frontend/platform_billing/balance_grant_requested": OpCase(
        RestMirror("POST", f"{_API}/platform-billing/balance-grant", "body"),
        _setup_balance_grant,
        True,
        "succeeded_only",
    ),
    "frontend/platform_billing/company_resolve_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/company-resolve", "query"), _setup_company_resolve, True
    ),
    "frontend/platform_billing/facet_companies_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/facets/billing-companies", "query"),
        _payload(q="sys", limit=20),
        True,
        "succeeded_only",
    ),
    "frontend/platform_billing/prices_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/prices", "none"), _empty, True
    ),
    "frontend/platform_billing/prices_update_requested": OpCase(
        RestMirror("PUT", f"{_API}/platform-billing/prices", "body_key", body_key="catalog"),
        _setup_prices_update,
        True,
    ),
    "frontend/platform_billing/default_settlement_rules_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/default-settlement-rules", "none"), _empty, True
    ),
    "frontend/platform_billing/settlement_rules_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/settlement-rules/{{company_id}}", "none"), _setup_company_id, True
    ),
    "frontend/platform_billing/settlement_rules_update_requested": OpCase(
        RestMirror("PUT", f"{_API}/platform-billing/settlement-rules/{{company_id}}", "body_key", body_key="document"),
        _setup_settlement_rules_update,
        True,
    ),
    "frontend/platform_billing/company_prices_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/prices/company/{{company_id}}", "none"),
        _setup_company_id,
        True,
        # storage_override — shared Redis state: параллельный company_prices_update
        # на другом xdist-воркере может записать его между WS и REST вызовами.
        volatile=frozenset({"storage_override"}),
    ),
    "frontend/platform_billing/company_prices_update_requested": OpCase(
        RestMirror("PUT", f"{_API}/platform-billing/prices/company/{{company_id}}", "body_key", body_key="catalog"),
        _setup_company_prices_update,
        True,
    ),
    "frontend/platform_billing/facet_usage_types_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/facets/usage-types", "query"),
        _payload(q="ll", limit=20),
        True,
        "succeeded_only",
    ),
    "frontend/platform_billing/facet_resource_names_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/facets/resource-names", "query"),
        _payload(q="gp", limit=20),
        True,
        "succeeded_only",
    ),
    "frontend/platform_billing/usage_report_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-billing/usage-report", "query"),
        _payload(limit=20, offset=0),
        True,
        "succeeded_only",
    ),
    "frontend/platform_tracing/facet_companies_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-tracing/facets/companies", "query"), _payload(q="sys", limit=20), True, "succeeded_only"
    ),
    "frontend/platform_tracing/facet_users_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-tracing/facets/users", "query"), _payload(q="test", limit=20), True, "succeeded_only"
    ),
    "frontend/platform_tracing/facet_services_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-tracing/facets/services", "query"), _payload(q="fr", limit=20), True, "succeeded_only"
    ),
    "frontend/platform_tracing/facet_event_types_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-tracing/facets/event-types", "query"), _payload(q="fl", limit=20), True, "succeeded_only"
    ),
    "frontend/platform_tracing/facet_namespaces_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-tracing/facets/namespaces", "query"), _payload(q="li", limit=20), True, "succeeded_only"
    ),
    "frontend/platform_tracing/facet_operations_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-tracing/facets/operations", "query"), _payload(q="op", limit=20), True, "succeeded_only"
    ),
    "frontend/platform_tracing/spans_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-tracing/spans", "query"), _payload(limit=5), True, "succeeded_only"
    ),
    "frontend/platform_tracing/trace_tree_requested": OpCase(
        RestMirror("GET", f"{_API}/platform-tracing/traces/{{trace_id}}", "none"), _setup_trace_tree, True
    ),
    "frontend/llm_model_scores/list_requested": OpCase(
        RestMirror("GET", f"{_API}/platform/llm-model-scores", "none"), _empty, True, "succeeded_only"
    ),
    "frontend/llm_model_scores/upsert_requested": OpCase(
        RestMirror("PUT", f"{_API}/platform/llm-model-scores", "body"),
        _setup_score_upsert,
        True,
        volatile=frozenset({"cache_rescore", "cooldown_seconds", "availability", "error_class", "error_text", "http_status"}),
    ),
    "frontend/llm_model_scores/delete_requested": OpCase(
        RestMirror("DELETE", f"{_API}/platform/llm-model-scores/{{capability}}/{{provider}}/{{model_id}}", "none"),
        _setup_score_delete,
        False,
        volatile=frozenset({"cache_rescore"}),
    ),
    # Обход внешних провайдеров зависит от сети: сверяем границу — не-system компания получает `forbidden`.
    "frontend/llm_model_scores/refresh_cache_requested": OpCase(
        RestMirror("POST", f"{_API}/platform/llm-model-scores/refresh-cache", "none"),
        _empty,
        True,
        principal="throwaway",
        expect="failed",
    ),
    "frontend/llm_model_scores/probe_providers_requested": OpCase(
        RestMirror("POST", f"{_API}/platform/llm-model-scores/probe-providers", "none"),
        _empty,
        True,
        principal="throwaway",
        expect="failed",
    ),
    "frontend/ai_providers/snapshot_requested": OpCase(
        RestMirror("GET", f"{_API}/settings/ai-providers", "none"), _payload(public_host=_PUBLIC_HOST), True, principal="throwaway"
    ),
    "frontend/ai_providers/llm_context_update_requested": OpCase(
        RestMirror("PUT", f"{_API}/settings/ai-providers/llm-context", "body"), _payload(mode="window"), True, principal="throwaway"
    ),
    "frontend/ai_providers/llm_context_remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/settings/ai-providers/llm-context", "none"),
        _setup_llm_context_remove,
        False,
        principal="throwaway",
    ),
    "frontend/ai_providers/capability_update_requested": OpCase(
        RestMirror("PUT", f"{_API}/settings/ai-providers/{{capability}}", "body_minus_path"),
        _payload(**_VOICE_CAPABILITY_PAYLOAD),
        True,
        principal="throwaway",
    ),
    "frontend/ai_providers/capability_remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/settings/ai-providers/{{capability}}", "none"),
        _setup_capability_remove,
        False,
        principal="throwaway",
    ),
    "frontend/ai_providers/custom_create_requested": OpCase(
        RestMirror("POST", f"{_API}/settings/ai-providers/custom", "body"),
        _custom_provider_body,
        False,
        principal="throwaway",
    ),
    "frontend/ai_providers/custom_update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/settings/ai-providers/custom/{{provider_id}}", "body_minus_path"),
        _setup_custom_update,
        True,
        principal="throwaway",
    ),
    "frontend/ai_providers/custom_remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/settings/ai-providers/custom/{{provider_id}}", "none"),
        _setup_custom_remove,
        False,
        principal="throwaway",
    ),
    "frontend/ai_providers/resolved_requested": OpCase(
        RestMirror("GET", f"{_API}/settings/ai-providers/resolved", "none"), _empty, True, principal="throwaway"
    ),
    "frontend/embed_configs/create_requested": OpCase(
        RestMirror("POST", f"{_API}/embed/configs", "body"),
        _setup_embed_create,
        False,
        principal="throwaway",
        volatile=frozenset({"embed_id"}),
    ),
    "frontend/embed_configs/list_requested": OpCase(
        RestMirror("GET", f"{_API}/embed/configs", "query"),
        _setup_embed_list,
        True,
        "marker_row",
        principal="throwaway",
        marker_key="embed_id",
    ),
    "frontend/embed_configs/item_requested": OpCase(
        RestMirror("GET", f"{_API}/embed/configs/{{embed_id}}", "none"), _setup_embed_id, True, principal="throwaway"
    ),
    "frontend/embed_configs/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/embed/configs/{{embed_id}}", "body_minus_path"),
        _setup_embed_update,
        True,
        principal="throwaway",
    ),
    "frontend/embed_configs/remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/embed/configs/{{embed_id}}", "none"),
        _setup_embed_id,
        False,
        principal="throwaway",
    ),
    "frontend/embed_configs/code_requested": OpCase(
        RestMirror("GET", f"{_API}/embed/configs/{{embed_id}}/code", "none"), _setup_embed_code, True, principal="throwaway"
    ),
    "frontend/agent/pairing_create_requested": OpCase(
        RestMirror("POST", f"{_API}/agent/pairing", "none"), _empty, True, "succeeded_only", principal="throwaway"
    ),
    "frontend/agent/devices_list_requested": OpCase(
        RestMirror("GET", f"{_API}/agent/devices", "query"), _payload(mine=False), True, principal="throwaway"
    ),
    "frontend/agent/device_revoke_requested": OpCase(
        RestMirror("DELETE", f"{_API}/agent/devices/{{device_id}}", "none"),
        _setup_device_revoke,
        False,
        principal="throwaway",
        volatile=frozenset({"device_id"}),
    ),
    "frontend/agent/device_policy_update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/agent/devices/{{device_id}}/policy", "body_minus_path"),
        _setup_device_policy,
        True,
        principal="throwaway",
        volatile=frozenset({"is_tunnel_online"}),
    ),
    "frontend/agent/audit_list_requested": OpCase(
        RestMirror("GET", f"{_API}/agent/audit", "query"), _payload(limit=50), True, "succeeded_only"
    ),
    "frontend/company_storages/list_requested": OpCase(
        RestMirror("GET", f"{_API}/company-storages", "none"),
        _empty,
        True,
        "succeeded_only",
        principal="throwaway",
    ),
    "frontend/company_storages/probe_requested": OpCase(
        RestMirror("POST", f"{_API}/company-storages/probe", "body"),
        _setup_storage_probe,
        True,
        "succeeded_only",
        principal="throwaway",
    ),
    "frontend/company_storages/create_requested": OpCase(
        RestMirror("POST", f"{_API}/company-storages", "body"),
        _setup_storage_create,
        False,
        "succeeded_only",
        principal="throwaway",
    ),
    "frontend/company_storages/rotate_credentials_requested": OpCase(
        RestMirror("POST", f"{_API}/company-storages/rotate", "body"),
        _setup_storage_rotate,
        True,
        "succeeded_only",
        principal="throwaway",
    ),
    "frontend/company_storages/delete_requested": OpCase(
        RestMirror("POST", f"{_API}/company-storages/delete", "body"),
        _setup_storage_delete,
        False,
        "succeeded_only",
        principal="throwaway",
    ),
    "frontend/company_storage_routes/set_requested": OpCase(
        RestMirror("POST", f"{_API}/company-storages/routes", "body"),
        _setup_storage_route,
        True,
        principal="throwaway",
        volatile=frozenset({"updated_at"}),
    ),
    "frontend/company_storage_migrations/start_requested": OpCase(
        RestMirror("POST", f"{_API}/company-storages/migrations", "body"),
        _setup_storage_migration_start,
        False,
        "succeeded_only",
        principal="throwaway",
    ),
    "frontend/company_storage_migrations/get_requested": OpCase(
        RestMirror("POST", f"{_API}/company-storages/migrations/get", "body"),
        _setup_storage_migration_get,
        True,
        "succeeded_only",
        principal="throwaway",
    ),
    "frontend/lead_requests/list_requested": OpCase(
        RestMirror("GET", f"{_API}/lead-requests", "query"),
        _setup_lead_requests,
        True,
        "marker_row",
        marker_key="lead_request_id",
    ),
}


# --- runner -----------------------------------------------------------------------------


def _normalize(value: JsonValue, volatile: frozenset[str]) -> JsonValue:
    if isinstance(value, dict):
        return {k: _normalize(v, volatile) for k, v in value.items() if k not in _VOLATILE_KEYS and k not in volatile}
    if isinstance(value, list):
        return [_normalize(item, volatile) for item in value]
    if isinstance(value, str):
        return _TRANSPORT_MARKER.sub("-x-", value)
    return value


def _row_by_marker(payload: JsonObject, *, marker_key: str, marker: str) -> JsonObject:
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("list payload must have items[]")
    matched = [item for item in items if isinstance(item, dict) and item.get(marker_key) == marker]
    if len(matched) != 1:
        raise AssertionError(f"expected one row {marker_key}={marker!r}, got {len(matched)}")
    return require_json_object(matched[0], "list.row")


def _event_payload(event: JsonObject) -> JsonObject:
    raw = event.get("payload")
    if raw is None:
        return {}
    return require_json_object(raw, "event.payload")


async def _ws_command(
    *,
    principal: Principal,
    canonical_type: str,
    payload: JsonObject,
    timeout_sec: float = 60.0,
) -> JsonObject:
    token_data = get_token_service().validate_token(principal.token)
    if token_data is None:
        raise AssertionError("SESSION JWT is required")
    event_id = uuid.uuid4().hex
    succeeded = canonical_type[: -len("_requested")] + "_succeeded"
    failed = canonical_type[: -len("_requested")] + "_failed"
    async with connect_centrifugo(principal.token) as ws:
        accepted = await rpc_platform_event(
            ws,
            event_type=canonical_type,
            payload=payload,
            company_id=token_data.company_id,
            event_id=event_id,
        )
        assert accepted.get("accepted") is True
        deadline = asyncio.get_running_loop().time() + timeout_sec
        terminal_ws: JsonObject | None = None
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            event = await ws.recv_platform_event(timeout=remaining)
            if event.get("type") not in (succeeded, failed):
                continue
            meta = event.get("meta")
            if not isinstance(meta, dict) or meta.get("causation_id") != event_id:
                continue
            terminal_ws = event
            break
    if terminal_ws is None:
        raise AssertionError(f"WS reply для {canonical_type!r} event_id={event_id} не получен")
    async with AsyncClient(base_url="http://localhost:9025", headers=principal.headers, timeout=30.0) as realtime:
        terminal_http = await realtime.get(f"/realtime/api/v1/events/{event_id}/terminal")
    assert terminal_http.status_code == 200, terminal_http.text
    assert require_json_object(terminal_http.json(), "terminal")["type"] == terminal_ws["type"]
    return terminal_ws


def _query_value(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise AssertionError(f"query param must be scalar, got {type(value).__name__}")


def _error_identity(payload: JsonObject) -> tuple[JsonValue, JsonValue]:
    return payload.get("error_code"), payload.get("error_detail")


async def _rest_command(
    *, client: AsyncClient, principal: Principal, rest: RestMirror, payload: JsonObject, expect_error: bool = False
) -> JsonObject:
    path_params = {key: _query_value(payload[key]) for key in _PATH_PLACEHOLDER.findall(rest.url)}
    url = rest.url.format(**path_params)
    json_body: JsonValue | None = None
    query: dict[str, str] | None = None
    if rest.strategy == "body":
        json_body = {k: v for k, v in payload.items() if k not in rest.drop}
    elif rest.strategy == "body_minus_path":
        json_body = {k: v for k, v in payload.items() if k not in path_params and k not in rest.drop}
    elif rest.strategy == "body_key":
        if rest.body_key is None:
            raise AssertionError("body_key strategy requires body_key")
        json_body = payload[rest.body_key]
    elif rest.strategy == "query":
        query = {k: _query_value(v) for k, v in payload.items() if k not in path_params and v is not None}
    response = await client.request(rest.method, url, headers=principal.headers, json=json_body, params=query)
    if expect_error:
        assert response.status_code >= 400, f"REST {rest.method} {url} ожидал ошибку, получил {response.status_code}"
        return require_json_object(response.json(), f"REST error {rest.method} {url}")
    return await _expect_json(response, ok=(200, 201, 202), label=f"REST {rest.method} {url}")


def test_every_frontend_operation_has_live_case() -> None:
    missing = sorted(set(FRONTEND_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(FRONTEND_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_frontend_op_ws_rest_identical(
    canonical_type: str,
    frontend_service: None,
    flows_service: None,
    realtime_service: None,
    frontend_client_http: AsyncClient,
    flows_client_http: AsyncClient,
    frontend_di,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    unique_id: str,
) -> None:
    _ = frontend_service, flows_service, realtime_service
    case = _CASES[canonical_type]
    if case.principal == "system":
        principal = Principal(token=auth_token_system, headers=auth_headers_system, user_id=system_user_id, company_id="system")
    else:
        principal = await seed_principal(frontend_di, unique_id=unique_id)

    def make_ctx(suffix: str) -> LiveCtx:
        return LiveCtx(
            frontend=frontend_client_http,
            flows=flows_client_http,
            frontend_di=frontend_di,
            principal=principal,
            unique_id=unique_id,
            suffix=suffix,
        )

    ws_ctx = make_ctx("ws")
    ws_payload = await case.setup(ws_ctx)
    ws_event = await _ws_command(principal=principal, canonical_type=canonical_type, payload=ws_payload)
    ws_result = _event_payload(ws_event)
    if case.expect == "failed":
        assert str(ws_event["type"]).endswith("_failed"), f"WS {canonical_type} ожидал _failed, получил {ws_event['type']}"
        rest_error = await _rest_command(
            client=frontend_client_http, principal=principal, rest=case.rest, payload=ws_payload, expect_error=True
        )
        assert _error_identity(ws_result) == _error_identity(rest_error), (
            f"WS != REST failure для {canonical_type}\nWS: {ws_result}\nREST: {rest_error}"
        )
        return
    assert str(ws_event["type"]).endswith("_succeeded"), (
        f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
    )
    if case.same_resource:
        rest_payload = ws_payload
        rest_marker = ws_ctx.marker
    else:
        rest_ctx = make_ctx("rest")
        rest_payload = await case.setup(rest_ctx)
        rest_marker = rest_ctx.marker
    rest_result = await _rest_command(
        client=frontend_client_http, principal=principal, rest=case.rest, payload=rest_payload
    )
    if case.compare == "succeeded_only":
        return
    if case.compare == "marker_row":
        if rest_marker is None:
            raise AssertionError("marker_row compare requires marker")
        assert _normalize(
            _row_by_marker(ws_result, marker_key=case.marker_key, marker=rest_marker), case.volatile
        ) == _normalize(
            _row_by_marker(rest_result, marker_key=case.marker_key, marker=rest_marker), case.volatile
        ), f"WS != REST row для {canonical_type}"
        return
    assert _normalize(ws_result, case.volatile) == _normalize(rest_result, case.volatile), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )
