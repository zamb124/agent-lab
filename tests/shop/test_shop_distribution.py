"""Строгие тесты распространения витрины: QR, sitemap, Telegram webhook, инвалидация."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from apps.shop.models.shop import Shop
from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX

_SHOPS = f"{API_PREFIX}/shops"


async def _published_shop(client: AsyncClient, slug: str) -> dict[str, object]:
    resp = await client.post(
        _SHOPS, json={"slug": slug, "name": f"Shop {slug}", "kind": "restaurant"}
    )
    assert resp.status_code == 200, resp.text
    shop = resp.json()
    await client.post(
        f"{_SHOPS}/{shop['shop_id']}/products",
        json={"name": "Маргарита", "price_minor": 50000},
    )
    resp = await client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
    assert resp.status_code == 200, resp.text
    return shop


class TestStorefrontQr:
    async def test_qr_svg_and_etag(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"qr-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/qr.svg"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/svg")
        assert "<svg" in resp.text
        etag = resp.headers.get("etag")
        assert etag and etag.startswith('W/"shop-qr-')
        second = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/qr.svg",
            headers={"If-None-Match": etag},
        )
        assert second.status_code == 304

    async def test_qr_404_for_draft(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"qrd-{unique_id[:8]}"
        resp = await shop_client.post(
            _SHOPS, json={"slug": slug, "name": "Draft", "kind": "restaurant"}
        )
        assert resp.status_code == 200
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/qr.svg"
        )
        assert resp.status_code == 404


class TestSitemap:
    async def test_sitemap_lists_only_published(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        pub = f"sm-{unique_id[:8]}"
        await _published_shop(shop_client, pub)
        draft = f"smd-{unique_id[:8]}"
        await shop_client.post(
            _SHOPS, json={"slug": draft, "name": "Draft", "kind": "restaurant"}
        )
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/sitemap.xml")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/xml")
        assert f"https://{pub}.linnex.io" in resp.text
        assert draft not in resp.text


class TestTelegramWebhook:
    async def _shop_with_bot(
        self, client: AsyncClient, slug: str
    ) -> tuple[dict[str, object], str]:
        shop = await _published_shop(client, slug)
        row = await Shop.get_by_id(str(shop["shop_id"]))
        assert row is not None
        row.telegram_bot_token = "test-bot-token"
        row.telegram_webhook_secret = f"sec-{slug}"
        await row.save()
        return shop, row.telegram_webhook_secret

    async def test_webhook_rejects_wrong_secret(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"tg-{unique_id[:8]}"
        shop, _ = await self._shop_with_bot(shop_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/telegram/webhook/{shop['shop_id']}",
            json={"message": {"chat": {"id": 42}, "text": "/start"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert resp.status_code == 404
        row = await Shop.get_by_id(str(shop["shop_id"]))
        assert row is not None and row.telegram_chat_id is None

    async def test_webhook_start_binds_chat(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"tgb-{unique_id[:8]}"
        shop, secret = await self._shop_with_bot(shop_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/telegram/webhook/{shop['shop_id']}",
            json={
                "update_id": 1,
                "message": {
                    "chat": {"id": 777001},
                    "from": {"id": 777001},
                    "text": "/start",
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": secret},
        )
        assert resp.status_code == 200
        row = await Shop.get_by_id(str(shop["shop_id"]))
        assert row is not None and row.telegram_chat_id == "777001"

    async def test_webhook_non_message_ignored(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"tgn-{unique_id[:8]}"
        shop, secret = await self._shop_with_bot(shop_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/telegram/webhook/{shop['shop_id']}",
            json={"update_id": 2, "callback_query": {"id": "x"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": secret},
        )
        assert resp.status_code == 200


class TestSnapshotInvalidation:
    async def test_product_update_visible_immediately(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"inv-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        snapshot = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}"
        )
        assert snapshot.status_code == 200
        assert "Маргарита" in snapshot.text
        products = (
            await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/products")
        ).json()["items"]
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/products/{products[0]['shop_product_id']}",
            json={"is_available": False},
        )
        assert resp.status_code == 200
        fresh = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert fresh.status_code == 200
        assert "Маргарита" not in fresh.text

    async def test_suspend_hides_storefront_immediately(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"sus-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        warm = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert warm.status_code == 200
        resp = await shop_client.post(f"{_SHOPS}/{shop['shop_id']}/suspend")
        assert resp.status_code == 200
        gone = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert gone.status_code == 404


class TestAiOperations:
    async def test_ai_describe_returns_text_or_clean_error(
        self, shop_client: AsyncClient, shop_di, unique_id: str
    ) -> None:
        """AI-описание: MockLLM в TESTING или честная ошибка провайдера."""
        slug = f"ai-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/describe",
            json={"name": "Пицца четыре сыра"},
        )
        assert resp.status_code in (200, 400, 409, 503)
        if resp.status_code == 200:
            assert resp.json()["text"]
        else:
            assert resp.json().get("error_code")

    async def test_ai_ops_require_shop(
        self, shop_client: AsyncClient
    ) -> None:
        resp = await shop_client.post(
            f"{_SHOPS}/shop_missing/ai/describe", json={"name": "x"}
        )
        assert resp.status_code in (404, 400)
