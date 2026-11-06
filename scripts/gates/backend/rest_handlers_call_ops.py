#!/usr/bin/env python3
"""
CI-gate: REST-хендлер сервиса из COMMAND_WS_SERVICES — тонкое зеркало `op_*`.

Каждый `@router.<method>(...)` в `apps/<svc>/api/**` (и `apps/flows/src/api/**`)
обязан вызывать `op_<entity>_<verb>` из каталога. Без `op_*` допустимы только
протокольные хендлеры из `PROTOCOL_HANDLERS`: байты/HTML наружу (download, screenshot,
viewer, certificate), внешние протоколы (A2A JSON-RPC/SSE/WS, MCP JSON-RPC, LSP WS,
OnlyOffice callback, webhooks) и анонимные публичные страницы wiki/office.
Новый хендлер без `op_*` — FAIL; протокольный хендлер, которого больше нет, — тоже FAIL.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT

APPS_ROOT = REPO_ROOT / "apps"
COMMAND_WS_SERVICES: tuple[str, ...] = (
    "sync", "worktracker", "wiki", "rag", "office", "crm", "flows", "search", "secrets", "scheduler", "frontend", "stock", "shop"
)
HTTP_METHODS: frozenset[str] = frozenset({"get", "post", "put", "patch", "delete", "websocket", "api_route"})

PROTOCOL_HANDLERS: frozenset[str] = frozenset(
    {
        # A2A 1.0: agent card, JSON-RPC (+embed), interface, WS
        "apps/flows/src/api/a2a.py::get_agent_card",
        "apps/flows/src/api/a2a.py::get_agent_card_well_known",
        "apps/flows/src/api/a2a.py::get_embed_interface",
        "apps/flows/src/api/a2a.py::get_flow_interface",
        "apps/flows/src/api/a2a.py::json_rpc_embed_handler",
        "apps/flows/src/api/a2a.py::json_rpc_handler",
        "apps/flows/src/api/websocket.py::websocket_a2a",
        "apps/flows/src/api/v1/tasks.py::submit_task",
        # байты и HTML наружу
        "apps/flows/src/api/v1/browser_preview.py::browser_preview_screenshot",
        "apps/flows/src/api/v1/browser_preview.py::browser_preview_viewer",
        "apps/flows/src/api/v1/certificate.py::download_certificate",
        "apps/office/api/bff.py::office_download",
        "apps/office/api/viewer_routes.py::viewer_frame",
        "apps/office/api/viewer_routes.py::viewer_save",
        "apps/office/api/viewer_routes.py::viewer_stream",
        # LSP: bootstrap сессии + JSON-RPC кадры по WS
        "apps/flows/src/api/v1/code_lsp.py::code_lsp_websocket",
        "apps/flows/src/api/v1/code_lsp.py::create_code_lsp_session",
        # обмен share-токена на сессию (pre-WS)
        "apps/flows/src/api/v1/flow_ui_shares.py::exchange_flow_ui_share",
        # входящие webhooks и OnlyOffice callback
        "apps/flows/src/api/v1/triggers.py::generic_webhook",
        "apps/flows/src/api/v1/triggers.py::telegram_webhook",
        "apps/shop/api/public.py::telegram_webhook",
        "apps/shop/api/public.py::get_storefront_qr",
        "apps/shop/api/public.py::get_table_qr",
        "apps/shop/api/public.py::get_sitemap",
        "apps/shop/api/public.py::get_robots",
        # анонимная витрина и агрегатор: HTML/JSON снапшоты без сессии
        "apps/shop/api/public.py::get_storefront",
        "apps/shop/api/public.py::get_storefront_page",
        "apps/shop/api/public.py::get_host_storefront_page",
        "apps/shop/api/public.py::get_market_page",
        "apps/shop/api/public.py::list_aggregate_shops_by_score_desc",
        "apps/shop/api/public.py::search_aggregate",
        "apps/shop/api/public.py::aggregate_geocode",
        "apps/shop/api/public.py::delivery_check",
        "apps/shop/api/public.py::address_suggest",
        # внутренний резолв Host → slug для прокси/shell слоя
        "apps/shop/api/public.py::resolve_host",
        # SSE-стрим статусов заказа: внешний протокол, не REST-команда
        "apps/shop/api/public.py::stream_order_events",
        # geo-прокси тайлов карты на витринных хостах: сырые байты, не команда
        "apps/shop/api/public.py::proxy_geo",
        # PWA-ассеты витрины: статические байты без команды
        "apps/shop/api/public.py::get_storefront_manifest",
        "apps/shop/api/public.py::get_storefront_sw",
        "apps/shop/api/public.py::get_storefront_icon",
        "apps/shop/api/public.py::get_host_manifest",
        "apps/shop/api/public.py::get_host_sw",
        "apps/shop/api/public.py::get_host_icon",
        "apps/office/api/bff.py::onlyoffice_callback",
        # анонимные публичные ссылки Documents и Wiki
        "apps/office/api/bff.py::public_catalog_binding_open",
        "apps/office/api/bff.py::public_catalog_items",
        "apps/office/api/bff.py::public_open",
        "apps/office/api/bff.py::public_resolve",
        "apps/wiki/api/public.py::get_public_page",
        "apps/wiki/api/public.py::get_public_page_markdown",
        "apps/wiki/api/public.py::get_public_site_file",
        "apps/wiki/api/public.py::get_public_site_page",
        "apps/wiki/api/public.py::get_public_site_page_markdown",
        "apps/wiki/api/public.py::get_public_site_tree",
        # MCP JSON-RPC поиска
        "apps/search/api/mcp.py::mcp_jsonrpc",
        # OpenAI-compatible LLM proxy (не команда)
        "apps/flows/src/api/v1/llm_proxy.py::llm_proxy_chat_completions",
        "apps/flows/src/api/v1/llm_proxy.py::llm_proxy_images_generations",
        "apps/flows/src/api/v1/llm_proxy.py::llm_proxy_models",
        "apps/flows/src/api/v1/llm_proxy.py::llm_proxy_onlyoffice_proxy",
        "apps/frontend/api/services.py::get_services_status",
        # frontend: OAuth callback, платёжный webhook, embed-session по API-ключу, инвайты pre-session
        "apps/frontend/api/auth.py::auth_callback",
        "apps/frontend/api/payments_webhook.py::payment_webhook",
        "apps/frontend/api/embed_configs.py::issue_embed_session_token",
        "apps/frontend/api/invites.py::accept_invite",
        "apps/frontend/api/invites.py::preview_invite",
        # frontend: анонимный публичный сайт, лендинг, гостевые сессии и design-system каталог
        "apps/frontend/api/design_system.py::design_system_preview",
        "apps/frontend/api/design_system.py::get_design_system_catalog",
        "apps/frontend/api/leads.py::create_lead",
        "apps/frontend/api/public_docs_assistant.py::issue_public_docs_assistant_session",
        "apps/frontend/api/public_embed_page.py::issue_embed_page_session",
        "apps/frontend/api/public_landing_agents.py::issue_public_landing_session",
        "apps/frontend/api/public_landing_agents.py::list_public_landing_agents",
        "apps/frontend/api/public_search.py::issue_public_search_session",
        "apps/frontend/api/public_search.py::public_search_favicon",
        "apps/frontend/api/public_search.py::public_search_serp_click",
        "apps/frontend/api/public_search.py::public_search_serp_more",
        "apps/frontend/api/public_site.py::get_public_blog_post",
        "apps/frontend/api/public_site.py::get_site_bundle",
        "apps/frontend/api/public_site.py::get_startup_card",
        "apps/frontend/api/public_site.py::list_public_blog_posts",
        "apps/frontend/api/public_site.py::record_cookie_consent",
    }
)


def _api_roots(service: str) -> list[Path]:
    return [p for p in (APPS_ROOT / service / "api", APPS_ROOT / service / "src" / "api") if p.is_dir()]


def _is_route_decorator(decorator: ast.expr) -> bool:
    call = decorator if isinstance(decorator, ast.Call) else None
    target = call.func if call is not None else decorator
    return isinstance(target, ast.Attribute) and target.attr in HTTP_METHODS


def _calls_operation(function: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = callee.id if isinstance(callee, ast.Name) else callee.attr if isinstance(callee, ast.Attribute) else ""
        if name.startswith("op_"):
            return True
    return False


def collect_handlers_without_op() -> set[str]:
    offenders: set[str] = set()
    for service in COMMAND_WS_SERVICES:
        for api_root in _api_roots(service):
            for path in sorted(api_root.rglob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                        continue
                    if not any(_is_route_decorator(d) for d in node.decorator_list):
                        continue
                    if _calls_operation(node):
                        continue
                    offenders.add(f"{path.relative_to(REPO_ROOT).as_posix()}::{node.name}")
    return offenders


def main() -> int:
    offenders = collect_handlers_without_op()
    introduced = sorted(offenders - PROTOCOL_HANDLERS)
    stale = sorted(PROTOCOL_HANDLERS - offenders)
    if introduced:
        print("check_rest_handlers_call_ops: FAIL — REST-хендлеры без op_* (добавь op_* в каталог сервиса):")
        for item in introduced:
            print(f"  {item}")
    if stale:
        print("check_rest_handlers_call_ops: FAIL — PROTOCOL_HANDLERS содержит несуществующие хендлеры, удали их:")
        for item in stale:
            print(f"  {item}")
    if introduced or stale:
        return 1
    print(f"check_rest_handlers_call_ops: OK (протокольных хендлеров: {len(PROTOCOL_HANDLERS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
