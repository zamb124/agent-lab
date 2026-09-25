"""Live Centrifugo RPC + REST identity для всех WIKI_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /wiki/api/internal/realtime/command` → тот же `op_*`.
REST — Granian :9023. Namespace — `X-Platform-Namespace` и `meta.namespace`.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote

import pytest
from httpx import AsyncClient, Response

from apps.wiki.realtime.command_router import WIKI_OPERATIONS
from core.di.platform import PlatformDi
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event
from tests.sync.api._helpers import seed_namespace_via_repo

_API = "/wiki/api/v1"
_NAMESPACE = "default"
_ORIGIN = "http://localhost:9023"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"-(?:ws|rest)(?=$|\W)")
_VOLATILE_KEYS = frozenset(
    {
        "wiki_page_id",
        "wiki_revision_id",
        "wiki_comment_id",
        "root_page_id",
        "parent_page_id",
        "position",
        "created_at",
        "updated_at",
        "published_at",
        "deleted_at",
        "resolved_at",
        "request_id",
        "trace_id",
        "service",
        "observability",
        "url",
    }
)

CompareMode = Literal["exact", "normalized", "named_title", "named_name"]
PayloadStrategy = Literal["body_minus_path", "query", "none"]
SetupFn = Callable[["LiveCtx"], Awaitable[JsonObject]]


@dataclass(frozen=True)
class RestMirror:
    method: str
    url: str
    strategy: PayloadStrategy
    text_body: bool = False
    """REST отдаёт файл (text/markdown + Content-Disposition), WS — `{body, file_name}`."""


@dataclass(frozen=True)
class OpCase:
    rest: RestMirror
    setup: SetupFn
    same_resource: bool
    compare: CompareMode


@dataclass
class LiveCtx:
    client: AsyncClient
    headers: dict[str, str]
    unique_id: str
    suffix: str
    system_user2_id: str
    di: PlatformDi
    marker: str | None = None


def _json(response: Response, label: str) -> JsonObject:
    return require_json_object(response.json(), label)


def _str_field(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{key} is required, got {value!r}")
    return value


def _strip_transport_marker(text: str) -> str:
    return _TRANSPORT_MARKER.sub("", text)


def _normalize(value: JsonValue | None) -> JsonValue | None:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _strip_transport_marker(value)
    return value


def _event_payload(event: JsonObject) -> JsonObject:
    raw = event.get("payload")
    if raw is None:
        return {}
    return require_json_object(raw, "event.payload")


async def _expect_json(response: Response, *, ok: tuple[int, ...], label: str) -> JsonObject:
    assert response.status_code in ok, f"{label} {response.status_code}: {response.text}"
    if response.status_code == 204:
        return {}
    return _json(response, label)


async def _create_page(ctx: LiveCtx, title: str, extra: JsonObject | None = None) -> JsonObject:
    body: JsonObject = {"title": title}
    if extra is not None:
        body.update(extra)
    response = await ctx.client.post(f"{_API}/pages", headers=ctx.headers, json=body)
    wrapper = await _expect_json(response, ok=(201,), label="create_page")
    return require_json_object(wrapper.get("page"), "create_page.page")


async def _setup_tree(ctx: LiveCtx) -> JsonObject:
    title = f"Wiki tree {ctx.unique_id}-{ctx.suffix}"
    _ = await _create_page(ctx, title)
    ctx.marker = title
    return {}


async def _setup_deleted_tree(ctx: LiveCtx) -> JsonObject:
    title = f"Wiki trash {ctx.unique_id}-{ctx.suffix}"
    page = await _create_page(ctx, title)
    wiki_page_id = _str_field(page, "wiki_page_id")
    deleted = await ctx.client.delete(f"{_API}/pages/{wiki_page_id}", headers=ctx.headers)
    assert deleted.status_code == 204, deleted.text
    ctx.marker = title
    return {}


async def _setup_namespaces(ctx: LiveCtx) -> JsonObject:
    name = f"0wiki-ns-{ctx.unique_id}-{ctx.suffix}"
    ctx.marker = await seed_namespace_via_repo(ctx.di, "system", name)
    return {"limit": 200, "offset": 0}


async def _setup_page_get(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki get {ctx.unique_id}-{ctx.suffix}")
    return {"wiki_page_id": _str_field(page, "wiki_page_id")}


async def _setup_page_create(ctx: LiveCtx) -> JsonObject:
    return {"title": f"Wiki create {ctx.unique_id}-{ctx.suffix}"}


async def _setup_content(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki content {ctx.unique_id}-{ctx.suffix}")
    return {
        "wiki_page_id": _str_field(page, "wiki_page_id"),
        "markdown": f"Текст {ctx.unique_id}-{ctx.suffix}",
        "create_revision": True,
    }


async def _setup_properties(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki props {ctx.unique_id}-{ctx.suffix}")
    return {
        "wiki_page_id": _str_field(page, "wiki_page_id"),
        "title": f"Wiki props done {ctx.unique_id}-{ctx.suffix}",
    }


async def _setup_move(ctx: LiveCtx) -> JsonObject:
    parent = await _create_page(ctx, f"Wiki parent {ctx.unique_id}-{ctx.suffix}")
    child = await _create_page(ctx, f"Wiki child {ctx.unique_id}-{ctx.suffix}")
    return {
        "wiki_page_id": _str_field(child, "wiki_page_id"),
        "parent_page_id": _str_field(parent, "wiki_page_id"),
        "position": 0,
    }


async def _create_workspace(ctx: LiveCtx, name: str) -> str:
    response = await ctx.client.post(
        "http://localhost:9004/frontend/api/namespaces",
        headers=ctx.headers,
        json={"name": name},
    )
    assert response.status_code == 201, f"create_workspace {response.status_code}: {response.text}"
    body = _json(response, "create_workspace")
    return _str_field(body, "name")


async def _setup_move_namespace(ctx: LiveCtx) -> JsonObject:
    target = await _create_workspace(ctx, f"wiki-move-{ctx.unique_id}-{ctx.suffix}")
    page = await _create_page(ctx, f"Wiki ns {ctx.unique_id}-{ctx.suffix}")
    return {
        "wiki_page_id": _str_field(page, "wiki_page_id"),
        "target_namespace": target,
    }


async def _setup_remove(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki del {ctx.unique_id}-{ctx.suffix}")
    return {"wiki_page_id": _str_field(page, "wiki_page_id")}


async def _setup_restore(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki rst {ctx.unique_id}-{ctx.suffix}")
    wiki_page_id = _str_field(page, "wiki_page_id")
    deleted = await ctx.client.delete(f"{_API}/pages/{wiki_page_id}", headers=ctx.headers)
    assert deleted.status_code == 204, deleted.text
    return {"wiki_page_id": wiki_page_id}


async def _setup_markdown(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(
        ctx,
        f"Wiki md {ctx.unique_id}-{ctx.suffix}",
        {"markdown": f"# {ctx.unique_id}"},
    )
    return {"wiki_page_id": _str_field(page, "wiki_page_id")}


async def _setup_markdown_parse(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"markdown": "# Заголовок\n\nТекст"}


async def _setup_markdown_create(ctx: LiveCtx) -> JsonObject:
    return {
        "markdown": f"# Import {ctx.unique_id}-{ctx.suffix}\n\nТело",
        "apply_front_matter": True,
    }


async def _setup_markdown_import(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki imp {ctx.unique_id}-{ctx.suffix}")
    return {
        "wiki_page_id": _str_field(page, "wiki_page_id"),
        "markdown": f"# Import {ctx.unique_id}-{ctx.suffix}\n\nТело",
        "apply_front_matter": True,
    }


async def _setup_children(ctx: LiveCtx) -> JsonObject:
    parent = await _create_page(ctx, f"Wiki kids {ctx.unique_id}-{ctx.suffix}")
    _ = await _create_page(
        ctx,
        f"Wiki kid {ctx.unique_id}-{ctx.suffix}",
        {"parent_page_id": _str_field(parent, "wiki_page_id")},
    )
    return {"wiki_page_id": _str_field(parent, "wiki_page_id"), "include_self": False}


async def _setup_access(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki access {ctx.unique_id}-{ctx.suffix}")
    return {"wiki_page_id": _str_field(page, "wiki_page_id")}


async def _setup_company_visible(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki vis {ctx.unique_id}-{ctx.suffix}")
    return {
        "wiki_page_id": _str_field(page, "wiki_page_id"),
        "company_visible": False,
    }


async def _setup_member_add(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki mem {ctx.unique_id}-{ctx.suffix}")
    wiki_page_id = _str_field(page, "wiki_page_id")
    restricted = await ctx.client.patch(
        f"{_API}/pages/{wiki_page_id}/access/company-visible",
        headers=ctx.headers,
        json={"company_visible": False},
    )
    assert restricted.status_code == 200, restricted.text
    return {
        "wiki_page_id": wiki_page_id,
        "user_id": ctx.system_user2_id,
        "relation": "viewer",
    }


async def _setup_member_remove(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_member_add(ctx)
    added = await ctx.client.post(
        f"{_API}/pages/{_str_field(payload, 'wiki_page_id')}/access/members",
        headers=ctx.headers,
        json={"user_id": ctx.system_user2_id, "relation": "viewer"},
    )
    assert added.status_code == 200, added.text
    return {
        "wiki_page_id": _str_field(payload, "wiki_page_id"),
        "member_user_id": ctx.system_user2_id,
    }


async def _setup_public_link(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki link {ctx.unique_id}-{ctx.suffix}")
    return {
        "wiki_page_id": _str_field(page, "wiki_page_id"),
        "enabled": True,
        "permission": "viewer",
        "origin": _ORIGIN,
    }


async def _setup_revisions(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki rev {ctx.unique_id}-{ctx.suffix}")
    wiki_page_id = _str_field(page, "wiki_page_id")
    updated = await ctx.client.put(
        f"{_API}/pages/{wiki_page_id}/content",
        headers=ctx.headers,
        json={"markdown": f"Rev {ctx.unique_id}-{ctx.suffix}"},
    )
    assert updated.status_code == 200, updated.text
    return {"wiki_page_id": wiki_page_id, "limit": 50}


async def _setup_revision_get(ctx: LiveCtx) -> JsonObject:
    listed = await _setup_revisions(ctx)
    response = await ctx.client.get(
        f"{_API}/pages/{_str_field(listed, 'wiki_page_id')}/revisions",
        headers=ctx.headers,
    )
    body = await _expect_json(response, ok=(200,), label="revisions")
    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise AssertionError("revisions.items required")
    first = require_json_object(items[0], "revision")
    return {"wiki_revision_id": _str_field(first, "wiki_revision_id")}


async def _setup_comments_list(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki cmt {ctx.unique_id}-{ctx.suffix}")
    return {"wiki_page_id": _str_field(page, "wiki_page_id")}


async def _setup_comment_create(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki cadd {ctx.unique_id}-{ctx.suffix}")
    return {
        "wiki_page_id": _str_field(page, "wiki_page_id"),
        "body_markdown": f"Комментарий {ctx.unique_id}-{ctx.suffix}",
        "anchor_text": "",
    }


async def _setup_comment_resolve(ctx: LiveCtx) -> JsonObject:
    created_payload = await _setup_comment_create(ctx)
    created = await ctx.client.post(
        f"{_API}/pages/{_str_field(created_payload, 'wiki_page_id')}/comments",
        headers=ctx.headers,
        json={"body_markdown": _str_field(created_payload, "body_markdown")},
    )
    body = await _expect_json(created, ok=(201,), label="create_comment")
    return {
        "wiki_comment_id": _str_field(body, "wiki_comment_id"),
        "resolved": True,
    }


async def _setup_comment_remove(ctx: LiveCtx) -> JsonObject:
    created_payload = await _setup_comment_create(ctx)
    created = await ctx.client.post(
        f"{_API}/pages/{_str_field(created_payload, 'wiki_page_id')}/comments",
        headers=ctx.headers,
        json={"body_markdown": _str_field(created_payload, "body_markdown")},
    )
    body = await _expect_json(created, ok=(201,), label="create_comment")
    return {"wiki_comment_id": _str_field(body, "wiki_comment_id")}


async def _setup_search(ctx: LiveCtx) -> JsonObject:
    title = f"Wiki search {ctx.unique_id}-{ctx.suffix}"
    _ = await _create_page(ctx, title, {"markdown": f"Найти {ctx.unique_id}"})
    return {"query": title, "mode": "lexical", "limit": 20}


async def _setup_backlinks(ctx: LiveCtx) -> JsonObject:
    page = await _create_page(ctx, f"Wiki bl {ctx.unique_id}-{ctx.suffix}")
    return {
        "target_kind": "wiki_page",
        "target_id": _str_field(page, "wiki_page_id"),
        "limit": 50,
    }


_CASES: dict[str, OpCase] = {
    "wiki/pages/list_requested": OpCase(
        RestMirror("GET", f"{_API}/pages", "none"), _setup_tree, True, "named_title"
    ),
    "wiki/pages/deleted_list_requested": OpCase(
        RestMirror("GET", f"{_API}/pages/deleted", "none"),
        _setup_deleted_tree,
        True,
        "named_title",
    ),
    "wiki/pages/item_requested": OpCase(
        RestMirror("GET", f"{_API}/pages/{{wiki_page_id}}", "none"),
        _setup_page_get,
        True,
        "normalized",
    ),
    "wiki/pages/create_requested": OpCase(
        RestMirror("POST", f"{_API}/pages", "body_minus_path"),
        _setup_page_create,
        False,
        "normalized",
    ),
    "wiki/pages/content_update_requested": OpCase(
        RestMirror("PUT", f"{_API}/pages/{{wiki_page_id}}/content", "body_minus_path"),
        _setup_content,
        False,
        "normalized",
    ),
    "wiki/pages/properties_update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/pages/{{wiki_page_id}}", "body_minus_path"),
        _setup_properties,
        False,
        "normalized",
    ),
    "wiki/pages/move_requested": OpCase(
        RestMirror("POST", f"{_API}/pages/{{wiki_page_id}}/move", "body_minus_path"),
        _setup_move,
        False,
        "normalized",
    ),
    "wiki/pages/move_namespace_requested": OpCase(
        RestMirror("POST", f"{_API}/pages/{{wiki_page_id}}/move-namespace", "body_minus_path"),
        _setup_move_namespace,
        False,
        "normalized",
    ),
    "wiki/pages/remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/pages/{{wiki_page_id}}", "none"),
        _setup_remove,
        False,
        "normalized",
    ),
    "wiki/pages/restore_requested": OpCase(
        RestMirror("POST", f"{_API}/pages/{{wiki_page_id}}/restore", "none"),
        _setup_restore,
        False,
        "normalized",
    ),
    "wiki/pages/markdown_requested": OpCase(
        RestMirror("GET", f"{_API}/pages/{{wiki_page_id}}/markdown", "none"),
        _setup_markdown,
        True,
        "normalized",
    ),
    "wiki/pages/markdown_file_requested": OpCase(
        RestMirror("GET", f"{_API}/pages/{{wiki_page_id}}/markdown/file", "none", text_body=True),
        _setup_markdown,
        True,
        "normalized",
    ),
    "wiki/pages/markdown_parse_requested": OpCase(
        RestMirror("POST", f"{_API}/pages/markdown/parse", "body_minus_path"),
        _setup_markdown_parse,
        True,
        "normalized",
    ),
    "wiki/pages/markdown_create_requested": OpCase(
        RestMirror("POST", f"{_API}/pages/import/markdown", "body_minus_path"),
        _setup_markdown_create,
        False,
        "normalized",
    ),
    "wiki/pages/markdown_import_requested": OpCase(
        RestMirror("POST", f"{_API}/pages/{{wiki_page_id}}/import/markdown", "body_minus_path"),
        _setup_markdown_import,
        False,
        "normalized",
    ),
    "wiki/pages/children_list_requested": OpCase(
        RestMirror("GET", f"{_API}/pages/{{wiki_page_id}}/children", "query"),
        _setup_children,
        True,
        "normalized",
    ),
    "wiki/pages/access_requested": OpCase(
        RestMirror("GET", f"{_API}/pages/{{wiki_page_id}}/access", "none"),
        _setup_access,
        True,
        "normalized",
    ),
    "wiki/pages/company_visible_requested": OpCase(
        RestMirror("PATCH", f"{_API}/pages/{{wiki_page_id}}/access/company-visible", "body_minus_path"),
        _setup_company_visible,
        False,
        "normalized",
    ),
    "wiki/pages/member_add_requested": OpCase(
        RestMirror("POST", f"{_API}/pages/{{wiki_page_id}}/access/members", "body_minus_path"),
        _setup_member_add,
        False,
        "normalized",
    ),
    "wiki/pages/member_remove_requested": OpCase(
        RestMirror(
            "DELETE",
            f"{_API}/pages/{{wiki_page_id}}/access/members/{{member_user_id}}",
            "none",
        ),
        _setup_member_remove,
        False,
        "normalized",
    ),
    "wiki/pages/public_link_requested": OpCase(
        RestMirror("POST", f"{_API}/pages/{{wiki_page_id}}/access/link", "body_minus_path"),
        _setup_public_link,
        False,
        "normalized",
    ),
    "wiki/pages/revisions_list_requested": OpCase(
        RestMirror("GET", f"{_API}/pages/{{wiki_page_id}}/revisions", "query"),
        _setup_revisions,
        True,
        "normalized",
    ),
    "wiki/pages/comments_list_requested": OpCase(
        RestMirror("GET", f"{_API}/pages/{{wiki_page_id}}/comments", "none"),
        _setup_comments_list,
        True,
        "normalized",
    ),
    "wiki/pages/comment_create_requested": OpCase(
        RestMirror("POST", f"{_API}/pages/{{wiki_page_id}}/comments", "body_minus_path"),
        _setup_comment_create,
        False,
        "normalized",
    ),
    "wiki/revisions/item_requested": OpCase(
        RestMirror("GET", f"{_API}/revisions/{{wiki_revision_id}}", "none"),
        _setup_revision_get,
        True,
        "normalized",
    ),
    "wiki/revisions/restore_requested": OpCase(
        RestMirror("POST", f"{_API}/revisions/{{wiki_revision_id}}/restore", "none"),
        _setup_revision_get,
        False,
        "normalized",
    ),
    "wiki/comments/resolve_requested": OpCase(
        RestMirror("POST", f"{_API}/comments/{{wiki_comment_id}}/resolve", "body_minus_path"),
        _setup_comment_resolve,
        False,
        "normalized",
    ),
    "wiki/comments/remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/comments/{{wiki_comment_id}}", "none"),
        _setup_comment_remove,
        False,
        "normalized",
    ),
    "wiki/search/run_requested": OpCase(
        RestMirror("POST", f"{_API}/search", "body_minus_path"),
        _setup_search,
        True,
        "normalized",
    ),
    "wiki/backlinks/list_requested": OpCase(
        RestMirror("GET", f"{_API}/backlinks", "query"),
        _setup_backlinks,
        True,
        "normalized",
    ),
    "wiki/namespaces/list_requested": OpCase(
        RestMirror("GET", f"{_API}/namespaces", "query"),
        _setup_namespaces,
        True,
        "named_name",
    ),
}


async def _ws_command(
    *,
    auth_token: str,
    realtime_session_client: AsyncClient,
    canonical_type: str,
    payload: JsonObject,
    timeout_sec: float = 20.0,
) -> JsonObject:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("SESSION JWT is required")
    event_id = uuid.uuid4().hex
    succeeded = canonical_type[: -len("_requested")] + "_succeeded"
    failed = canonical_type[: -len("_requested")] + "_failed"
    async with connect_centrifugo(auth_token) as ws:
        accepted = await rpc_platform_event(
            ws,
            event_type=canonical_type,
            payload=payload,
            company_id=token_data.company_id,
            event_id=event_id,
            namespace=_NAMESPACE,
        )
        assert accepted.get("accepted") is True
        assert accepted.get("event_id") == event_id
        deadline = asyncio.get_running_loop().time() + timeout_sec
        terminal_ws: JsonObject | None = None
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            event = await ws.recv_platform_event(timeout=remaining)
            event_type = event.get("type")
            if event_type not in (succeeded, failed):
                continue
            meta = event.get("meta")
            if not isinstance(meta, dict) or meta.get("causation_id") != event_id:
                continue
            terminal_ws = event
            break
    if terminal_ws is None:
        raise AssertionError(f"WS reply для {canonical_type!r} event_id={event_id} не получен")
    stored = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
    assert stored.status_code == 200, stored.text
    assert stored.json()["type"] == canonical_type
    terminal_http = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}/terminal")
    assert terminal_http.status_code == 200, terminal_http.text
    terminal = require_json_object(terminal_http.json(), "terminal")
    assert terminal["type"] == terminal_ws["type"]
    assert terminal["meta"]["causation_id"] == event_id
    return terminal_ws


async def _rest_command(
    *,
    client: AsyncClient,
    headers: dict[str, str],
    rest: RestMirror,
    payload: JsonObject,
) -> JsonObject:
    path_params: dict[str, str] = {}
    for key in _PATH_PLACEHOLDER.findall(rest.url):
        path_params[key] = _str_field(payload, key)
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    if rest.strategy == "body_minus_path":
        body = {
            k: v
            for k, v in payload.items()
            if k not in path_params and k != "origin" and v is not None
        }
        json_body = body if body else None
    elif rest.strategy == "query":
        query = {k: v for k, v in payload.items() if k not in path_params and v is not None}
    elif rest.strategy == "none":
        pass
    else:
        raise AssertionError(f"unknown REST strategy {rest.strategy!r}")
    response = await client.request(
        rest.method,
        url,
        headers=headers,
        json=json_body,
        params=query,
    )
    if rest.text_body:
        assert response.status_code == 200, f"REST {rest.method} {url}: {response.text}"
        disposition = response.headers["content-disposition"]
        encoded_name = disposition.split("filename*=UTF-8''", 1)[1]
        return {"body": response.text, "file_name": unquote(encoded_name)}
    return await _expect_json(
        response,
        ok=(200, 201, 204),
        label=f"REST {rest.method} {url}",
    )


def _row_by_name(payload: JsonObject, name: str) -> JsonObject:
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("list payload must have items[]")
    matched: list[JsonObject] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("name") == name:
            matched.append(require_json_object(item, "namespace.row"))
    if len(matched) != 1:
        raise AssertionError(f"expected one namespace name={name!r}, got {len(matched)}")
    return matched[0]


def _row_by_title(payload: JsonObject, title: str) -> JsonObject:
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("list payload must have items[]")
    matched: list[JsonObject] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("title") == title:
            matched.append(require_json_object(item, "tree.row"))
    if len(matched) != 1:
        raise AssertionError(f"expected one page titled {title!r}, got {len(matched)}")
    return matched[0]


def test_every_wiki_operation_has_live_case() -> None:
    missing = sorted(set(WIKI_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(WIKI_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(45)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_wiki_op_ws_rest_identical(
    canonical_type: str,
    wiki_service_http: None,
    realtime_service: None,
    frontend_service: None,
    wiki_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user2_id: str,
    unique_id: str,
    frontend_di,
) -> None:
    _ = wiki_service_http, realtime_service, frontend_service
    headers = {**auth_headers_system, "X-Platform-Namespace": _NAMESPACE}
    case = _CASES[canonical_type]
    ws_ctx = LiveCtx(
        client=wiki_client_http,
        headers=headers,
        unique_id=unique_id,
        suffix="ws",
        system_user2_id=system_user2_id,
        di=frontend_di,
    )
    ws_payload = await case.setup(ws_ctx)
    ws_event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type=canonical_type,
        payload=ws_payload,
    )
    assert str(ws_event["type"]).endswith("_succeeded"), (
        f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
    )
    ws_result = _event_payload(ws_event)
    if case.same_resource:
        rest_payload = ws_payload
        rest_marker = ws_ctx.marker
    else:
        rest_ctx = LiveCtx(
            client=wiki_client_http,
            headers=headers,
            unique_id=unique_id,
            suffix="rest",
            system_user2_id=system_user2_id,
        di=frontend_di,
        )
        rest_payload = await case.setup(rest_ctx)
        rest_marker = rest_ctx.marker
    rest_result = await _rest_command(
        client=wiki_client_http,
        headers=headers,
        rest=case.rest,
        payload=rest_payload,
    )
    if case.compare == "named_title":
        if rest_marker is None:
            raise AssertionError("named_title compare requires marker")
        assert _row_by_title(ws_result, rest_marker) == _row_by_title(rest_result, rest_marker), (
            f"WS != REST row для {canonical_type}"
        )
        return
    if case.compare == "named_name":
        if rest_marker is None:
            raise AssertionError("named_name compare requires marker")
        assert _normalize(_row_by_name(ws_result, rest_marker)) == _normalize(
            _row_by_name(rest_result, rest_marker)
        ), f"WS != REST row для {canonical_type}"
        return
    assert _normalize(ws_result) == _normalize(rest_result), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_wiki_get_missing_failed_terminal(
    wiki_service_http: None,
    realtime_service: None,
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = wiki_service_http, realtime_service
    event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type="wiki/pages/item_requested",
        payload={"wiki_page_id": f"wpg_missing_{unique_id}"},
    )
    assert event["type"] == "wiki/pages/item_failed"
    payload = _event_payload(event)
    assert payload["error_code"] == "not_found"
