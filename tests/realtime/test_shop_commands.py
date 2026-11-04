"""Live Centrifugo RPC + REST identity для всех SHOP_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /shop/api/internal/realtime/command` → тот же `op_*`. REST — Granian :9027.

AI-команды идут через A2A во flows :9001 под `MockLLM` без очереди ответов: исход
(успех или ошибка) задаёт стек, тест требует одинаковый исход WS и REST. Команды,
которым live-стек не даёт успеха (Telegram Bot API без сети), сверяют тождество
ошибки: `error_code` и `error_detail`.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest
from httpx2 import AsyncClient, Response

from apps.shop.realtime.command_router import SHOP_OPERATIONS
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    platform_auxiliary_upload_spec_json,
)
from tests.fixtures.shop import (
    PUBLIC_PREFIX,
    SHOPS_PREFIX,
    add_menu_item,
    make_active_menu_item,
    make_product,
    make_shop,
    publish_shop,
    shop_with_sellable_item,
)
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_SHOPS = SHOPS_PREFIX
_SHOP = f"{SHOPS_PREFIX}/{{shop_id}}"
_FILES_API = "/shop/api/v1/files"
_WORK_ITEMS = "/worktracker/api/v1/work-items"
_MENU_TEMPLATE_XLSX = (
    Path(__file__).resolve().parents[1] / "shop" / "fixtures" / "menu_template.xlsx"
)
_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    + "1f15c4890000000d49444154789c6360f8cfc0f01f0005000201e2b1d9"
    + "0e0000000049454e44ae426082"
)
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"-(?:ws|rest)\b")
_VOLATILE_KEYS = frozenset(
    {"public_code", "url", "request_id", "trace_id", "service", "observability"}
)
_VOLATILE_SUFFIXES = ("_id", "_ids", "_at", "_url")
_OK_STATUSES = (200, 201, 202)

PayloadStrategy = Literal["body", "body_minus_path", "query", "none"]
CompareMode = Literal["normalized", "marker_row"]
Expectation = Literal["succeeded", "failed", "either"]
SetupFn = Callable[["LiveCtx"], Awaitable[JsonObject]]


@dataclass
class LiveCtx:
    client: AsyncClient
    worktracker: AsyncClient
    headers: dict[str, str]
    unique_id: str
    suffix: str
    marker: str | None = None


@dataclass(frozen=True)
class RestMirror:
    method: str
    url: str
    strategy: PayloadStrategy


@dataclass(frozen=True)
class OpCase:
    rest: RestMirror
    setup: SetupFn
    same_resource: bool
    compare: CompareMode = "normalized"
    expect: Expectation = "succeeded"


def _ctx_headers(auth_headers: Mapping[str, str], unique_id: str, suffix: str) -> dict[str, str]:
    """IP-лимит заказов считается по `X-Forwarded-For`: свой адрес на тест и транспорт."""
    n = int(unique_id[:8], 16)
    last_octet = 7 if suffix == "ws" else 8
    return {
        **auth_headers,
        "X-Platform-Namespace": "default",
        "X-Forwarded-For": f"10.{(n >> 8) % 254 + 1}.{n % 254 + 1}.{last_octet}",
    }


def _slug(ctx: LiveCtx) -> str:
    return f"lv-{ctx.unique_id}-{ctx.suffix}"


def _str(body: Mapping[str, JsonValue], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or value == "":
        raise AssertionError(f"{key} required, got {body!r}")
    return value


async def _expect_json(response: Response, *, ok: tuple[int, ...], label: str) -> JsonObject:
    assert response.status_code in ok, f"{label} {response.status_code}: {response.text}"
    return require_json_object(response.json(), label)


async def _shop_id(ctx: LiveCtx) -> str:
    shop = await make_shop(ctx.client, _slug(ctx))
    return _str(shop, "shop_id")


async def _product_id(
    ctx: LiveCtx, shop_id: str, name: str = "Маргарита", **overrides: JsonValue
) -> str:
    product = await make_product(ctx.client, shop_id, name, 50000, **overrides)
    return _str(product, "shop_product_id")


async def _menu_id(ctx: LiveCtx, shop_id: str, name: str = "Меню") -> str:
    response = await ctx.client.post(
        f"{_SHOPS}/{shop_id}/menus", headers=ctx.headers, json={"name": name}
    )
    return _str(await _expect_json(response, ok=(200,), label="create menu"), "shop_menu_id")


async def _section_id(ctx: LiveCtx, shop_id: str, shop_menu_id: str, name: str = "Раздел") -> str:
    response = await ctx.client.post(
        f"{_SHOPS}/{shop_id}/menus/{shop_menu_id}/sections",
        headers=ctx.headers,
        json={"name": name},
    )
    return _str(
        await _expect_json(response, ok=(200,), label="create section"), "shop_menu_section_id"
    )


async def _menu_item_id(
    ctx: LiveCtx, shop_id: str, shop_menu_id: str, section_id: str, product_id: str
) -> str:
    item = await add_menu_item(ctx.client, shop_id, shop_menu_id, section_id, product_id)
    return _str(item, "shop_menu_item_id")


async def _modifier_group_id(ctx: LiveCtx, shop_id: str) -> str:
    response = await ctx.client.post(
        f"{_SHOPS}/{shop_id}/modifier-groups",
        headers=ctx.headers,
        json={"name": "Соусы", "max_selected": 3},
    )
    return _str(
        await _expect_json(response, ok=(200,), label="create modifier group"),
        "shop_modifier_group_id",
    )


async def _modifier_option_id(ctx: LiveCtx, shop_id: str, group_id: str) -> str:
    response = await ctx.client.post(
        f"{_SHOPS}/{shop_id}/modifier-groups/{group_id}/options",
        headers=ctx.headers,
        json={"name": "Сырный", "price_minor": 5000},
    )
    return _str(
        await _expect_json(response, ok=(200,), label="create modifier option"),
        "shop_modifier_option_id",
    )


def _promo_body() -> JsonObject:
    return {
        "name": "Скидка 10%",
        "condition": {"type": "always"},
        "action": {"type": "percent_order", "pct": 10},
    }


async def _promo_id(ctx: LiveCtx, shop_id: str) -> str:
    response = await ctx.client.post(
        f"{_SHOPS}/{shop_id}/promos", headers=ctx.headers, json=_promo_body()
    )
    return _str(await _expect_json(response, ok=(200,), label="create promo"), "shop_promo_id")


async def _domain_id(ctx: LiveCtx, shop_id: str) -> str:
    response = await ctx.client.post(
        f"{_SHOPS}/{shop_id}/domains", headers=ctx.headers, params={"domain": _domain(ctx)}
    )
    return _str(await _expect_json(response, ok=(200,), label="add domain"), "shop_domain_id")


def _domain(ctx: LiveCtx) -> str:
    return f"lv-{ctx.unique_id}-{ctx.suffix}.invalid"


async def _sellable(ctx: LiveCtx) -> tuple[str, str, str]:
    """Опубликованное заведение с активной позицией: slug, shop_id, shop_menu_item_id."""
    shop, _, item = await shop_with_sellable_item(ctx.client, _slug(ctx))
    return _str(shop, "slug"), _str(shop, "shop_id"), _str(item, "shop_menu_item_id")


def _order_body(shop_menu_item_id: str) -> JsonObject:
    return {
        "items": [{"shop_menu_item_id": shop_menu_item_id, "qty": 2}],
        "customer_name": "Иван",
        "customer_phone": "+79991112233",
        "delivery_type": "pickup",
    }


async def _order(ctx: LiveCtx) -> tuple[str, str, str]:
    """Заказ с витрины: shop_id, shop_order_id, public_code."""
    slug, shop_id, item_id = await _sellable(ctx)
    response = await ctx.client.post(
        f"{PUBLIC_PREFIX}/storefront/{slug}/orders", headers=ctx.headers, json=_order_body(item_id)
    )
    public_code = _str(await _expect_json(response, ok=(200,), label="create order"), "public_code")
    page = await _expect_json(
        await ctx.client.get(f"{_SHOPS}/{shop_id}/orders", headers=ctx.headers),
        ok=(200,),
        label="list orders",
    )
    items = page.get("items")
    if not isinstance(items, list) or len(items) != 1:
        raise AssertionError(f"expected one order, got {page!r}")
    order = require_json_object(items[0], "orders.item")
    return shop_id, _str(order, "shop_order_id"), public_code


async def _upload(ctx: LiveCtx, *, content: bytes, original_name: str, content_type: str) -> str:
    response = await chunked_upload_file(
        ctx.client,
        ctx.headers,
        content=content,
        original_name=original_name,
        content_type=content_type,
        spec_json=platform_auxiliary_upload_spec_json(is_public=False),
        files_api_prefix=_FILES_API,
    )
    return _str(await _expect_json(response, ok=(200, 201), label="upload file"), "file_id")


async def _shop_work_item(ctx: LiveCtx, shop_id: str, variables: Mapping[str, JsonValue]) -> str:
    """WorkItem импорта без назначения агенту: фоновый shop_menu_agent его не трогает."""
    response = await ctx.worktracker.post(
        _WORK_ITEMS,
        headers=ctx.headers,
        json={
            "title": f"Импорт меню {_slug(ctx)}",
            "links": [{"link_kind": "shop", "shop_id": shop_id}],
            "variables": {key: {"value": value} for key, value in variables.items()},
        },
    )
    return _str(await _expect_json(response, ok=(201,), label="create work item"), "work_item_id")


# --- Заведения ---


async def _setup_empty(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {}


async def _setup_shops_list(ctx: LiveCtx) -> JsonObject:
    _ = await _shop_id(ctx)
    ctx.marker = _slug(ctx)
    return {}


async def _setup_shop_create(ctx: LiveCtx) -> JsonObject:
    return {"slug": _slug(ctx), "name": f"Shop {_slug(ctx)}", "kind": "restaurant"}


async def _setup_shop(ctx: LiveCtx) -> JsonObject:
    return {"shop_id": await _shop_id(ctx)}


async def _setup_shop_update(ctx: LiveCtx) -> JsonObject:
    return {
        "shop_id": await _shop_id(ctx),
        "description": "Пиццерия у дома",
        "city": "Москва",
        "delivery_fee_minor": 15000,
    }


async def _setup_published_shop(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    _ = await publish_shop(ctx.client, shop_id)
    return {"shop_id": shop_id}


async def _setup_telegram_connect(ctx: LiveCtx) -> JsonObject:
    return {"shop_id": await _shop_id(ctx), "bot_token": "123456789:AAH-live-identity-token-0000"}


# --- Каталог блюд ---


async def _setup_product_create(ctx: LiveCtx) -> JsonObject:
    return {
        "shop_id": await _shop_id(ctx),
        "name": "Карбонара",
        "price_minor": 64000,
        "description": "Паста",
    }


async def _setup_products_list(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    _ = await _product_id(ctx, shop_id, "Маргарита")
    _ = await _product_id(ctx, shop_id, "Пепперони")
    return {"shop_id": shop_id}


async def _setup_product(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    return {"shop_id": shop_id, "shop_product_id": await _product_id(ctx, shop_id)}


async def _setup_product_unverified(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    return {
        "shop_id": shop_id,
        "shop_product_id": await _product_id(ctx, shop_id, ai_unverified=True),
    }


async def _setup_product_update(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_product(ctx)
    return {**payload, "price_minor": 52000, "description": "Томаты, моцарелла"}


async def _setup_products_reorder(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    first = await _product_id(ctx, shop_id, "Маргарита")
    second = await _product_id(ctx, shop_id, "Пепперони")
    return {"shop_id": shop_id, "product_ids": [second, first]}


async def _similar_pair(ctx: LiveCtx) -> tuple[str, str, str]:
    """Блюдо и похожее на него (pg_trgm): shop_id, исходное, похожее."""
    shop_id = await _shop_id(ctx)
    original = await _product_id(ctx, shop_id, "Пицца Маргарита")
    similar = await _product_id(ctx, shop_id, "Пицца Маргарита большая")
    return shop_id, original, similar


async def _setup_similar_list(ctx: LiveCtx) -> JsonObject:
    shop_id, _, similar = await _similar_pair(ctx)
    return {"shop_id": shop_id, "shop_product_id": similar}


async def _setup_merge(ctx: LiveCtx) -> JsonObject:
    shop_id, original, similar = await _similar_pair(ctx)
    return {
        "shop_id": shop_id,
        "shop_product_id": similar,
        "into_shop_product_id": original,
        "fields": ["price_minor"],
    }


async def _setup_dismiss_similar(ctx: LiveCtx) -> JsonObject:
    shop_id, _, similar = await _similar_pair(ctx)
    return {"shop_id": shop_id, "shop_product_id": similar}


# --- Меню, разделы, позиции ---


async def _setup_menus_list(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    product_id = await _product_id(ctx, shop_id)
    _ = await make_active_menu_item(ctx.client, shop_id, product_id)
    return {"shop_id": shop_id}


async def _setup_menu_create(ctx: LiveCtx) -> JsonObject:
    return {"shop_id": await _shop_id(ctx), "name": "Завтраки"}


async def _setup_menu(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    return {"shop_id": shop_id, "shop_menu_id": await _menu_id(ctx, shop_id)}


async def _setup_menu_update(ctx: LiveCtx) -> JsonObject:
    return {**await _setup_menu(ctx), "name": "Летнее меню"}


async def _setup_menus_reorder(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    first = await _menu_id(ctx, shop_id, "Основное")
    second = await _menu_id(ctx, shop_id, "Бар")
    return {"shop_id": shop_id, "shop_menu_ids": [second, first]}


async def _setup_menu_set_status(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    product_id = await _product_id(ctx, shop_id)
    menu_id = await _menu_id(ctx, shop_id)
    section_id = await _section_id(ctx, shop_id, menu_id)
    _ = await _menu_item_id(ctx, shop_id, menu_id, section_id, product_id)
    return {"shop_id": shop_id, "shop_menu_id": menu_id, "status": "active"}


async def _setup_section_create(ctx: LiveCtx) -> JsonObject:
    return {**await _setup_menu(ctx), "name": "Десерты"}


async def _setup_section(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    menu_id = await _menu_id(ctx, shop_id)
    return {"shop_id": shop_id, "shop_menu_section_id": await _section_id(ctx, shop_id, menu_id)}


async def _setup_section_update(ctx: LiveCtx) -> JsonObject:
    return {**await _setup_section(ctx), "name": "Горячее"}


async def _setup_sections_reorder(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    menu_id = await _menu_id(ctx, shop_id)
    first = await _section_id(ctx, shop_id, menu_id, "Супы")
    second = await _section_id(ctx, shop_id, menu_id, "Салаты")
    return {
        "shop_id": shop_id,
        "shop_menu_id": menu_id,
        "items": [
            {"shop_menu_section_id": second, "parent_id": None},
            {"shop_menu_section_id": first, "parent_id": None},
        ],
    }


async def _setup_menu_item_add(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    product_id = await _product_id(ctx, shop_id)
    menu_id = await _menu_id(ctx, shop_id)
    section_id = await _section_id(ctx, shop_id, menu_id)
    return {
        "shop_id": shop_id,
        "shop_menu_id": menu_id,
        "shop_menu_section_id": section_id,
        "shop_product_id": product_id,
    }


async def _menu_item(ctx: LiveCtx) -> tuple[str, str, str, str]:
    """Позиция в черновом меню: shop_id, shop_menu_id, shop_menu_section_id, shop_menu_item_id."""
    shop_id = await _shop_id(ctx)
    product_id = await _product_id(ctx, shop_id)
    menu_id = await _menu_id(ctx, shop_id)
    section_id = await _section_id(ctx, shop_id, menu_id)
    item_id = await _menu_item_id(ctx, shop_id, menu_id, section_id, product_id)
    return shop_id, menu_id, section_id, item_id


async def _setup_menu_item(ctx: LiveCtx) -> JsonObject:
    shop_id, _, _, item_id = await _menu_item(ctx)
    return {"shop_id": shop_id, "shop_menu_item_id": item_id}


async def _setup_menu_item_update(ctx: LiveCtx) -> JsonObject:
    return {**await _setup_menu_item(ctx), "price_minor_override": 45000, "is_available": False}


async def _setup_menu_item_move(ctx: LiveCtx) -> JsonObject:
    shop_id, menu_id, _, item_id = await _menu_item(ctx)
    target_section_id = await _section_id(ctx, shop_id, menu_id, "Новинки")
    return {
        "shop_id": shop_id,
        "shop_menu_item_id": item_id,
        "shop_menu_section_id": target_section_id,
    }


async def _setup_menu_items_reorder(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    first_product = await _product_id(ctx, shop_id, "Маргарита")
    second_product = await _product_id(ctx, shop_id, "Пепперони")
    menu_id = await _menu_id(ctx, shop_id)
    section_id = await _section_id(ctx, shop_id, menu_id)
    first = await _menu_item_id(ctx, shop_id, menu_id, section_id, first_product)
    second = await _menu_item_id(ctx, shop_id, menu_id, section_id, second_product)
    return {
        "shop_id": shop_id,
        "shop_menu_section_id": section_id,
        "shop_menu_item_ids": [second, first],
    }


# --- Заказы и витрина ---


async def _setup_orders_list(ctx: LiveCtx) -> JsonObject:
    shop_id, _, _ = await _order(ctx)
    return {"shop_id": shop_id, "limit": 50, "offset": 0}


async def _setup_order(ctx: LiveCtx) -> JsonObject:
    shop_id, order_id, _ = await _order(ctx)
    return {"shop_id": shop_id, "shop_order_id": order_id}


async def _setup_order_set_status(ctx: LiveCtx) -> JsonObject:
    return {**await _setup_order(ctx), "status": "accepted"}


async def _setup_cart_price(ctx: LiveCtx) -> JsonObject:
    slug, _, item_id = await _sellable(ctx)
    return {
        "slug": slug,
        "items": [{"shop_menu_item_id": item_id, "qty": 3}],
        "delivery_type": "pickup",
    }


async def _setup_order_create(ctx: LiveCtx) -> JsonObject:
    slug, _, item_id = await _sellable(ctx)
    return {"slug": slug, **_order_body(item_id)}


async def _setup_order_status(ctx: LiveCtx) -> JsonObject:
    _, _, public_code = await _order(ctx)
    return {"public_code": public_code}


# --- Домены ---


async def _setup_domain_add(ctx: LiveCtx) -> JsonObject:
    return {"shop_id": await _shop_id(ctx), "domain": _domain(ctx)}


async def _setup_domain(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    return {"shop_id": shop_id, "shop_domain_id": await _domain_id(ctx, shop_id)}


# --- AI ---


async def _setup_ai_describe(ctx: LiveCtx) -> JsonObject:
    return {"shop_id": await _shop_id(ctx), "name": "Пицца четыре сыра", "category_name": "Пицца"}


async def _setup_ai_brief(ctx: LiveCtx) -> JsonObject:
    return {
        "shop_id": await _shop_id(ctx),
        "name": "Пиццерия Луиджи",
        "description": "Неаполитанская пицца",
    }


async def _setup_ai_enhance_photo(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    file_id = await _upload(
        ctx, content=_PNG_1PX, original_name="dish.png", content_type="image/png"
    )
    return {"shop_id": shop_id, "file_id": file_id}


async def _setup_ai_suggest_options(ctx: LiveCtx) -> JsonObject:
    return {"shop_id": await _shop_id(ctx), "product_name": "Бургер", "group_name": "Соусы"}


# --- Модификаторы ---


async def _setup_modifier_group_create(ctx: LiveCtx) -> JsonObject:
    return {"shop_id": await _shop_id(ctx), "name": "Добавки", "max_selected": 2}


async def _setup_modifier_groups_list(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    group_id = await _modifier_group_id(ctx, shop_id)
    _ = await _modifier_option_id(ctx, shop_id, group_id)
    return {"shop_id": shop_id}


async def _setup_modifier_group(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    return {"shop_id": shop_id, "shop_modifier_group_id": await _modifier_group_id(ctx, shop_id)}


async def _setup_modifier_group_update(ctx: LiveCtx) -> JsonObject:
    return {**await _setup_modifier_group(ctx), "name": "Фирменные соусы", "min_selected": 1}


async def _setup_modifier_option_create(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    group_id = await _modifier_group_id(ctx, shop_id)
    return {"shop_id": shop_id, "group_id": group_id, "name": "Чесночный", "price_minor": 3000}


async def _setup_modifier_option(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    group_id = await _modifier_group_id(ctx, shop_id)
    return {
        "shop_id": shop_id,
        "shop_modifier_option_id": await _modifier_option_id(ctx, shop_id, group_id),
    }


async def _setup_modifier_option_update(ctx: LiveCtx) -> JsonObject:
    return {**await _setup_modifier_option(ctx), "price_minor": 7000, "is_default": True}


async def _product_with_group(ctx: LiveCtx) -> tuple[str, str, str]:
    shop_id = await _shop_id(ctx)
    product_id = await _product_id(ctx, shop_id)
    group_id = await _modifier_group_id(ctx, shop_id)
    return shop_id, product_id, group_id


async def _setup_modifier_attach(ctx: LiveCtx) -> JsonObject:
    shop_id, product_id, group_id = await _product_with_group(ctx)
    return {
        "shop_id": shop_id,
        "product_id": product_id,
        "group_id": group_id,
        "min_selected": 0,
        "max_selected": 2,
    }


async def _setup_modifier_detach(ctx: LiveCtx) -> JsonObject:
    shop_id, product_id, group_id = await _product_with_group(ctx)
    response = await ctx.client.post(
        f"{_SHOPS}/{shop_id}/products/{product_id}/modifier-groups/{group_id}",
        headers=ctx.headers,
        json={},
    )
    _ = await _expect_json(response, ok=(200,), label="attach modifier group")
    return {"shop_id": shop_id, "product_id": product_id, "group_id": group_id}


# --- Промо ---


async def _setup_promo_create(ctx: LiveCtx) -> JsonObject:
    return {"shop_id": await _shop_id(ctx), **_promo_body()}


async def _setup_promos_list(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    _ = await _promo_id(ctx, shop_id)
    return {"shop_id": shop_id}


async def _setup_promo(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    return {"shop_id": shop_id, "shop_promo_id": await _promo_id(ctx, shop_id)}


async def _setup_promo_update(ctx: LiveCtx) -> JsonObject:
    return {**await _setup_promo(ctx), "name": "Скидка выходного дня", "is_active": False}


# --- Импорт меню агентом и из файла ---


async def _setup_menu_import_start(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    file_id = await _upload(
        ctx, content=_PNG_1PX, original_name="menu.png", content_type="image/png"
    )
    return {"shop_id": shop_id, "target": "catalog", "file_ids": [file_id]}


async def _setup_menu_imports_list(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    _ = await _shop_work_item(
        ctx, shop_id, {"mode": "import", "shop_id": shop_id, "target": "catalog"}
    )
    return {"shop_id": shop_id}


async def _setup_menu_import_apply(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    work_item_id = await _shop_work_item(
        ctx,
        shop_id,
        {"mode": "import", "shop_id": shop_id, "target": "new_menu", "menu_name": "Импорт"},
    )
    return {
        "shop_id": shop_id,
        "work_item_id": work_item_id,
        "sections": [
            {
                "name": "Пицца",
                "items": [
                    {"name": "Маргарита", "price_minor": 50000},
                    {"name": "Пепперони", "price_minor": 59000},
                ],
            }
        ],
    }


async def _setup_menu_template_build(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    _ = await _product_id(ctx, shop_id)
    return {"shop_id": shop_id, "menu_name": "Бизнес-ланч", "brief": "Обеденное меню из каталога"}


async def _setup_products_enrich(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_product(ctx)
    return {"shop_id": payload["shop_id"], "shop_product_ids": [payload["shop_product_id"]]}


async def _setup_products_enrich_apply(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    product_id = await _product_id(ctx, shop_id)
    work_item_id = await _shop_work_item(
        ctx, shop_id, {"mode": "enrich", "shop_id": shop_id, "shop_product_ids": [product_id]}
    )
    return {
        "shop_id": shop_id,
        "work_item_id": work_item_id,
        "updates": [{"shop_product_id": product_id, "description": "Томаты, моцарелла, базилик"}],
    }


async def _setup_menu_file_import(ctx: LiveCtx) -> JsonObject:
    shop_id = await _shop_id(ctx)
    file_id = await _upload(
        ctx,
        content=await asyncio.to_thread(_MENU_TEMPLATE_XLSX.read_bytes),
        original_name="menu_template.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return {"shop_id": shop_id, "target": "catalog", "file_id": file_id, "format": "xlsx"}


def _case(
    method: str,
    url: str,
    strategy: PayloadStrategy,
    setup: SetupFn,
    same_resource: bool,
    *,
    compare: CompareMode = "normalized",
    expect: Expectation = "succeeded",
) -> OpCase:
    return OpCase(RestMirror(method, url, strategy), setup, same_resource, compare, expect)


_CASES: dict[str, OpCase] = {
    # Заведения
    "shop/shops/list_requested": _case(
        "GET", _SHOPS, "none", _setup_shops_list, True, compare="marker_row"
    ),
    "shop/badge_icons/list_requested": _case(
        "GET", f"{_SHOPS}/badge-icons", "none", _setup_empty, True
    ),
    "shop/shops/create_requested": _case("POST", _SHOPS, "body", _setup_shop_create, False),
    "shop/shops/item_requested": _case("GET", _SHOP, "none", _setup_shop, True),
    "shop/shops/update_requested": _case(
        "PATCH", _SHOP, "body_minus_path", _setup_shop_update, True
    ),
    "shop/shops/publish_requested": _case("POST", f"{_SHOP}/publish", "none", _setup_shop, True),
    "shop/shops/suspend_requested": _case(
        "POST", f"{_SHOP}/suspend", "none", _setup_published_shop, False
    ),
    "shop/shops/remove_requested": _case("DELETE", _SHOP, "none", _setup_shop, False),
    "shop/telegram/connect_requested": _case(
        "POST",
        f"{_SHOP}/telegram/connect",
        "body_minus_path",
        _setup_telegram_connect,
        True,
        expect="failed",
    ),
    "shop/telegram/disconnect_requested": _case(
        "POST", f"{_SHOP}/telegram/disconnect", "none", _setup_shop, True
    ),
    # Каталог блюд
    "shop/products/list_requested": _case(
        "GET", f"{_SHOP}/products", "none", _setup_products_list, True
    ),
    "shop/products/create_requested": _case(
        "POST", f"{_SHOP}/products", "body_minus_path", _setup_product_create, False
    ),
    "shop/products/reorder_requested": _case(
        "POST", f"{_SHOP}/products/reorder", "body_minus_path", _setup_products_reorder, True
    ),
    "shop/products/update_requested": _case(
        "PATCH",
        f"{_SHOP}/products/{{shop_product_id}}",
        "body_minus_path",
        _setup_product_update,
        True,
    ),
    "shop/products/remove_requested": _case(
        "DELETE", f"{_SHOP}/products/{{shop_product_id}}", "none", _setup_product, False
    ),
    "shop/products/verify_requested": _case(
        "POST",
        f"{_SHOP}/products/{{shop_product_id}}/verify",
        "none",
        _setup_product_unverified,
        True,
    ),
    "shop/products/similar_list_requested": _case(
        "GET", f"{_SHOP}/products/{{shop_product_id}}/similar", "none", _setup_similar_list, True
    ),
    "shop/products/merge_requested": _case(
        "POST",
        f"{_SHOP}/products/{{shop_product_id}}/merge",
        "body_minus_path",
        _setup_merge,
        False,
    ),
    "shop/products/dismiss_similar_requested": _case(
        "POST",
        f"{_SHOP}/products/{{shop_product_id}}/dismiss-similar",
        "none",
        _setup_dismiss_similar,
        False,
    ),
    # Меню
    "shop/menus/list_requested": _case("GET", f"{_SHOP}/menus", "none", _setup_menus_list, True),
    "shop/menus/create_requested": _case(
        "POST", f"{_SHOP}/menus", "body_minus_path", _setup_menu_create, False
    ),
    "shop/menus/reorder_requested": _case(
        "POST", f"{_SHOP}/menus/reorder", "body_minus_path", _setup_menus_reorder, True
    ),
    "shop/menus/update_requested": _case(
        "PATCH", f"{_SHOP}/menus/{{shop_menu_id}}", "body_minus_path", _setup_menu_update, True
    ),
    "shop/menus/set_status_requested": _case(
        "POST",
        f"{_SHOP}/menus/{{shop_menu_id}}/status",
        "body_minus_path",
        _setup_menu_set_status,
        True,
    ),
    "shop/menus/remove_requested": _case(
        "DELETE", f"{_SHOP}/menus/{{shop_menu_id}}", "none", _setup_menu, False
    ),
    # Разделы меню
    "shop/menu_sections/create_requested": _case(
        "POST",
        f"{_SHOP}/menus/{{shop_menu_id}}/sections",
        "body_minus_path",
        _setup_section_create,
        False,
    ),
    "shop/menu_sections/reorder_requested": _case(
        "POST",
        f"{_SHOP}/menus/{{shop_menu_id}}/sections/reorder",
        "body_minus_path",
        _setup_sections_reorder,
        True,
    ),
    "shop/menu_sections/update_requested": _case(
        "PATCH",
        f"{_SHOP}/menu-sections/{{shop_menu_section_id}}",
        "body_minus_path",
        _setup_section_update,
        True,
    ),
    "shop/menu_sections/remove_requested": _case(
        "DELETE", f"{_SHOP}/menu-sections/{{shop_menu_section_id}}", "none", _setup_section, False
    ),
    # Позиции меню
    "shop/menu_items/add_requested": _case(
        "POST",
        f"{_SHOP}/menus/{{shop_menu_id}}/items",
        "body_minus_path",
        _setup_menu_item_add,
        False,
    ),
    "shop/menu_items/reorder_requested": _case(
        "POST", f"{_SHOP}/menu-items/reorder", "body_minus_path", _setup_menu_items_reorder, True
    ),
    "shop/menu_items/update_requested": _case(
        "PATCH",
        f"{_SHOP}/menu-items/{{shop_menu_item_id}}",
        "body_minus_path",
        _setup_menu_item_update,
        True,
    ),
    "shop/menu_items/move_requested": _case(
        "POST",
        f"{_SHOP}/menu-items/{{shop_menu_item_id}}/move",
        "body_minus_path",
        _setup_menu_item_move,
        False,
    ),
    "shop/menu_items/remove_requested": _case(
        "DELETE", f"{_SHOP}/menu-items/{{shop_menu_item_id}}", "none", _setup_menu_item, False
    ),
    # Заказы
    "shop/orders/list_requested": _case(
        "GET", f"{_SHOP}/orders", "query", _setup_orders_list, True
    ),
    "shop/orders/item_requested": _case(
        "GET", f"{_SHOP}/orders/{{shop_order_id}}", "none", _setup_order, True
    ),
    "shop/orders/set_status_requested": _case(
        "POST", f"{_SHOP}/orders/{{shop_order_id}}/status", "query", _setup_order_set_status, False
    ),
    # Публичная витрина
    "shop/public/cart_price_requested": _case(
        "POST",
        f"{PUBLIC_PREFIX}/storefront/{{slug}}/cart/price",
        "body_minus_path",
        _setup_cart_price,
        True,
    ),
    "shop/public/order_create_requested": _case(
        "POST",
        f"{PUBLIC_PREFIX}/storefront/{{slug}}/orders",
        "body_minus_path",
        _setup_order_create,
        True,
    ),
    "shop/public/order_status_requested": _case(
        "GET", f"{PUBLIC_PREFIX}/orders/{{public_code}}", "none", _setup_order_status, True
    ),
    # Домены
    "shop/domains/add_requested": _case(
        "POST", f"{_SHOP}/domains", "query", _setup_domain_add, False
    ),
    "shop/domains/remove_requested": _case(
        "DELETE", f"{_SHOP}/domains/{{shop_domain_id}}", "none", _setup_domain, False
    ),
    "shop/domains/provision_requested": _case(
        "POST", f"{_SHOP}/domains/{{shop_domain_id}}/provision", "none", _setup_domain, False
    ),
    # AI
    "shop/ai/describe_requested": _case(
        "POST", f"{_SHOP}/ai/describe", "body_minus_path", _setup_ai_describe, True, expect="either"
    ),
    "shop/ai/enhance_photo_requested": _case(
        "POST",
        f"{_SHOP}/ai/enhance-photo",
        "body_minus_path",
        _setup_ai_enhance_photo,
        True,
        expect="either",
    ),
    "shop/ai/generate_photo_requested": _case(
        "POST",
        f"{_SHOP}/ai/generate-photo",
        "body_minus_path",
        _setup_ai_brief,
        True,
        expect="either",
    ),
    "shop/ai/describe_shop_requested": _case(
        "POST",
        f"{_SHOP}/ai/describe-shop",
        "body_minus_path",
        _setup_ai_brief,
        True,
        expect="either",
    ),
    "shop/ai/generate_cover_requested": _case(
        "POST",
        f"{_SHOP}/ai/generate-cover",
        "body_minus_path",
        _setup_ai_brief,
        True,
        expect="either",
    ),
    "shop/ai/generate_logo_requested": _case(
        "POST",
        f"{_SHOP}/ai/generate-logo",
        "body_minus_path",
        _setup_ai_brief,
        True,
        expect="either",
    ),
    "shop/ai/autofill_requested": _case(
        "POST", f"{_SHOP}/ai/autofill", "none", _setup_shop, False, expect="either"
    ),
    "shop/ai/suggest_options_requested": _case(
        "POST",
        f"{_SHOP}/ai/suggest-options",
        "body_minus_path",
        _setup_ai_suggest_options,
        True,
        expect="either",
    ),
    # Модификаторы
    "shop/modifiers/groups/list_requested": _case(
        "GET", f"{_SHOP}/modifier-groups", "none", _setup_modifier_groups_list, True
    ),
    "shop/modifiers/groups/create_requested": _case(
        "POST", f"{_SHOP}/modifier-groups", "body_minus_path", _setup_modifier_group_create, False
    ),
    "shop/modifiers/groups/update_requested": _case(
        "PATCH",
        f"{_SHOP}/modifier-groups/{{shop_modifier_group_id}}",
        "body_minus_path",
        _setup_modifier_group_update,
        True,
    ),
    "shop/modifiers/groups/remove_requested": _case(
        "DELETE",
        f"{_SHOP}/modifier-groups/{{shop_modifier_group_id}}",
        "none",
        _setup_modifier_group,
        False,
    ),
    "shop/modifiers/options/create_requested": _case(
        "POST",
        f"{_SHOP}/modifier-groups/{{group_id}}/options",
        "body_minus_path",
        _setup_modifier_option_create,
        False,
    ),
    "shop/modifiers/options/update_requested": _case(
        "PATCH",
        f"{_SHOP}/modifier-options/{{shop_modifier_option_id}}",
        "body_minus_path",
        _setup_modifier_option_update,
        True,
    ),
    "shop/modifiers/options/remove_requested": _case(
        "DELETE",
        f"{_SHOP}/modifier-options/{{shop_modifier_option_id}}",
        "none",
        _setup_modifier_option,
        False,
    ),
    "shop/products/modifiers/attach_requested": _case(
        "POST",
        f"{_SHOP}/products/{{product_id}}/modifier-groups/{{group_id}}",
        "body_minus_path",
        _setup_modifier_attach,
        False,
    ),
    "shop/products/modifiers/detach_requested": _case(
        "DELETE",
        f"{_SHOP}/products/{{product_id}}/modifier-groups/{{group_id}}",
        "none",
        _setup_modifier_detach,
        False,
    ),
    # Промо
    "shop/promos/list_requested": _case("GET", f"{_SHOP}/promos", "none", _setup_promos_list, True),
    "shop/promos/create_requested": _case(
        "POST", f"{_SHOP}/promos", "body_minus_path", _setup_promo_create, False
    ),
    "shop/promos/update_requested": _case(
        "PATCH", f"{_SHOP}/promos/{{shop_promo_id}}", "body_minus_path", _setup_promo_update, True
    ),
    "shop/promos/remove_requested": _case(
        "DELETE", f"{_SHOP}/promos/{{shop_promo_id}}", "none", _setup_promo, False
    ),
    # Импорт меню: REST-тело — полный payload команды
    "shop/menu_imports/start_requested": _case(
        "POST", f"{_SHOP}/menu-imports", "body", _setup_menu_import_start, False
    ),
    "shop/menu_imports/list_requested": _case(
        "GET", f"{_SHOP}/menu-imports", "none", _setup_menu_imports_list, True
    ),
    "shop/menu_imports/apply_requested": _case(
        "POST",
        f"{_SHOP}/menu-imports/{{work_item_id}}/apply",
        "body",
        _setup_menu_import_apply,
        True,
    ),
    "shop/menu_templates/build_requested": _case(
        "POST", f"{_SHOP}/menu-templates", "body", _setup_menu_template_build, False
    ),
    "shop/products/enrich_requested": _case(
        "POST", f"{_SHOP}/products/enrich", "body", _setup_products_enrich, False
    ),
    "shop/products/enrich_apply_requested": _case(
        "POST",
        f"{_SHOP}/products/enrich/{{work_item_id}}/apply",
        "body",
        _setup_products_enrich_apply,
        True,
    ),
    "shop/menu_file_imports/run_requested": _case(
        "POST", f"{_SHOP}/menu-file-imports", "body", _setup_menu_file_import, False
    ),
}


def _is_volatile(key: str) -> bool:
    return key in _VOLATILE_KEYS or key.endswith(_VOLATILE_SUFFIXES)


def _normalize(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if not _is_volatile(k)}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _TRANSPORT_MARKER.sub("-x", value)
    return value


def _row_by_marker(payload: JsonObject, marker: str) -> JsonObject:
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("list payload must have items[]")
    matched = [item for item in items if isinstance(item, dict) and item.get("slug") == marker]
    if len(matched) != 1:
        raise AssertionError(f"expected one row slug={marker!r}, got {len(matched)}")
    return require_json_object(matched[0], "list.row")


def _event_payload(event: JsonObject) -> JsonObject:
    raw = event.get("payload")
    if raw is None:
        return {}
    return require_json_object(raw, "event.payload")


async def _ws_command(
    *,
    auth_token: str,
    realtime_session_client: AsyncClient,
    canonical_type: str,
    payload: JsonObject,
    timeout_sec: float = 60.0,
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
    terminal_http = await realtime_session_client.get(
        f"/realtime/api/v1/events/{event_id}/terminal"
    )
    assert terminal_http.status_code == 200, terminal_http.text
    assert require_json_object(terminal_http.json(), "terminal")["type"] == terminal_ws["type"]
    return terminal_ws


async def _rest_command(
    *, client: AsyncClient, headers: dict[str, str], rest: RestMirror, payload: JsonObject
) -> tuple[int, JsonObject]:
    path_params = {key: str(payload[key]) for key in _PATH_PLACEHOLDER.findall(rest.url)}
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, str | int | float | bool] | None = None
    if rest.strategy == "body":
        json_body = payload
    elif rest.strategy == "body_minus_path":
        json_body = {k: v for k, v in payload.items() if k not in path_params}
    elif rest.strategy == "query":
        query = {}
        for key, value in payload.items():
            if key in path_params or value is None:
                continue
            if not isinstance(value, str | int | float | bool):
                raise AssertionError(f"query param {key} must be scalar, got {value!r}")
            query[key] = value
    response = await client.request(rest.method, url, headers=headers, json=json_body, params=query)
    return response.status_code, require_json_object(response.json(), f"REST {rest.method} {url}")


def test_every_shop_operation_has_live_case() -> None:
    missing = sorted(set(SHOP_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(SHOP_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_shop_op_ws_rest_identical(
    canonical_type: str,
    shop_service: None,
    realtime_service: None,
    flows_service: None,
    shop_client_http: AsyncClient,
    worktracker_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = shop_service, realtime_service, flows_service
    case = _CASES[canonical_type]

    def live_ctx(suffix: str) -> LiveCtx:
        return LiveCtx(
            client=shop_client_http,
            worktracker=worktracker_client_http,
            headers=_ctx_headers(auth_headers_system, unique_id, suffix),
            unique_id=unique_id,
            suffix=suffix,
        )

    ws_ctx = live_ctx("ws")
    ws_payload = await case.setup(ws_ctx)
    ws_event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type=canonical_type,
        payload=ws_payload,
    )
    ws_succeeded = str(ws_event["type"]).endswith("_succeeded")
    ws_result = _event_payload(ws_event)
    if case.expect != "either":
        assert ws_succeeded == (case.expect == "succeeded"), (
            f"WS {canonical_type} вернул {ws_event['type']}, ожидался {case.expect}: {ws_result}"
        )
    if case.same_resource:
        rest_ctx = ws_ctx
        rest_payload = ws_payload
    else:
        rest_ctx = live_ctx("rest")
        rest_payload = await case.setup(rest_ctx)
    rest_status, rest_result = await _rest_command(
        client=shop_client_http, headers=rest_ctx.headers, rest=case.rest, payload=rest_payload
    )
    if not ws_succeeded:
        assert rest_status >= 400, (
            f"REST {canonical_type} {rest_status} при WS failed: {rest_result}"
        )
        ws_error_code = ws_result.get("error_code")
        assert isinstance(ws_error_code, str) and ws_error_code != "", (
            f"WS failed без error_code: {ws_result}"
        )
        assert rest_result.get("error_code") == ws_error_code, (
            f"WS != REST error_code для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
        )
        if case.same_resource:
            assert rest_result.get("error_detail") == ws_result.get("error_detail"), (
                f"WS != REST error_detail для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
            )
        return
    assert rest_status in _OK_STATUSES, (
        f"REST {canonical_type} {rest_status} при WS succeeded: {rest_result}"
    )
    if case.compare == "marker_row":
        if rest_ctx.marker is None:
            raise AssertionError("marker_row compare requires marker")
        assert _normalize(_row_by_marker(ws_result, rest_ctx.marker)) == _normalize(
            _row_by_marker(rest_result, rest_ctx.marker)
        ), f"WS != REST row для {canonical_type}"
        return
    assert _normalize(ws_result) == _normalize(rest_result), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )
