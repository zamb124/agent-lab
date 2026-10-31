"""Строгие тесты распространения витрины: QR, sitemap, Telegram webhook, инвалидация."""

from __future__ import annotations

from httpx2 import AsyncClient

from apps.shop.models.shop import Shop
from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX

_SHOPS = f"{API_PREFIX}/shops"

# Минимальный валидный PNG 1x1 — реальные байты через FilesService → A2A Part.raw.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c626001000000ffff030000060005"
    "57bfabd40000000049454e44ae426082"
)


async def _create_image_file(shop_di, name: str) -> str:
    """Реальный FileRecord с PNG-байтами через FilesService (company=system)."""
    from core.context import clear_context, set_context
    from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
    from core.files.registry import default_retention_for_source
    from core.models.context_models import Context
    from core.models.identity_models import User
    from tests.fixtures.ai_provider_defaults import make_test_company

    spec = FileCreateSpec.model_validate(
        {
            "source_kind": FileSourceKind.PLATFORM_AUXILIARY.value,
            "source_ref": FileSourceRef.model_validate({}).model_dump(),
            "retention": default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
        }
    )
    set_context(
        Context(
            user=User(user_id="test_user", name="Test User"),
            active_company=make_test_company(company_id="system", name="System"),
            session_id="test_session",
            channel="test",
        )
    )
    try:
        record = await shop_di.files_service.create(
            spec, _PNG_BYTES, original_name=name, content_type="image/png"
        )
    finally:
        clear_context()
    return record.file_id


async def _reset_shop_flow() -> None:
    """Сносит компанийскую копию flow ``shop``: следующий A2A-вызов лениво
    материализует актуальный bundle со всеми ветками."""
    from apps.flows.src.models.flow_config import FlowConfig
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.identity_models import User
    from tests.fixtures.ai_provider_defaults import make_test_company

    set_context(
        Context(
            user=User(user_id="test_user", name="Test User"),
            active_company=make_test_company(company_id="system", name="System"),
            session_id="test_session",
            channel="test",
        )
    )
    try:
        _ = await FlowConfig.delete_by_flow_id("shop")
    finally:
        clear_context()


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
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}/qr.svg")
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
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}/qr.svg")
        assert resp.status_code == 404


class TestSitemap:
    async def test_sitemap_lists_only_published(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        pub = f"sm-{unique_id[:8]}"
        await _published_shop(shop_client, pub)
        draft = f"smd-{unique_id[:8]}"
        await shop_client.post(_SHOPS, json={"slug": draft, "name": "Draft", "kind": "restaurant"})
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/sitemap.xml")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/xml")
        assert f"https://{pub}.linnex.io" in resp.text
        assert draft not in resp.text


class TestTelegramWebhook:
    async def _shop_with_bot(self, client: AsyncClient, slug: str) -> tuple[dict[str, object], str]:
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
        snapshot = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snapshot.status_code == 200
        assert "Маргарита" in snapshot.text
        products = (await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/products")).json()["items"]
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

    async def test_ai_ops_require_shop(self, shop_client: AsyncClient) -> None:
        resp = await shop_client.post(f"{_SHOPS}/shop_missing/ai/describe", json={"name": "x"})
        assert resp.status_code in (404, 400)

    async def test_ai_describe_batch_enqueues_pending_count(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Batch AI: считает позиции без описания и ставит задачу в очередь."""
        slug = f"aib-{unique_id[:8]}"
        resp = await shop_client.post(_SHOPS, json={"slug": slug, "name": f"Shop {slug}"})
        assert resp.status_code == 200, resp.text
        shop = resp.json()
        await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={"name": "Без описания", "price_minor": 100},
        )
        await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={
                "name": "С описанием",
                "price_minor": 100,
                "description": "Уже написано",
            },
        )
        resp = await shop_client.post(f"{_SHOPS}/{shop['shop_id']}/ai/describe-all")
        assert resp.status_code == 200, resp.text
        assert resp.json()["enqueued"] == 1

    async def test_ai_describe_batch_requires_shop(self, shop_client: AsyncClient) -> None:
        resp = await shop_client.post(f"{_SHOPS}/shop_missing/ai/describe-all")
        assert resp.status_code in (404, 400)

    async def test_ai_describe_photo_vision_branch(
        self,
        shop_client: AsyncClient,
        shop_di,
        mock_llm_redis,
        mock_llm_capture,
        unique_id: str,
    ) -> None:
        """describe по фото: A2A → ветка describe_photo (llm_vision), файл → state.files → vision-сообщение."""
        shop = await _published_shop(shop_client, f"aiv-{unique_id[:8]}")
        file_id = await _create_image_file(shop_di, "dish.png")
        await mock_llm_redis([{"type": "text", "content": "Сочная маргарита на тонком тесте"}])
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/describe",
            json={"name": "Маргарита", "photo_file_id": file_id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["text"] == "Сочная маргарита на тонком тесте"

        calls = await mock_llm_capture()
        file_parts = [
            part
            for call in calls
            for message in call.get("messages", [])
            for part in message.get("parts", [])
            if part.get("type") == "file"
        ]
        assert file_parts and all(part.get("mime_type") == "image/png" for part in file_parts)

    async def test_ai_describe_photo_unknown_file_404(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """describe по несуществующему фото — fail-closed file_not_found до LLM."""
        shop = await _published_shop(shop_client, f"aix-{unique_id[:8]}")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/describe",
            json={"name": "Маргарита", "photo_file_id": "file_0000000000aa"},
        )
        assert resp.status_code == 404
        assert resp.json().get("error_code") == "file_not_found"

    async def test_ai_enhance_photo_image_gen_branch(
        self,
        shop_client: AsyncClient,
        shop_di,
        mock_llm_redis,
        unique_id: str,
    ) -> None:
        """enhance: Part.raw → state.files → image_gen (is_editing) → {"file_ids": [...]} → file_id."""
        shop = await _published_shop(shop_client, f"aie-{unique_id[:8]}")
        source_id = await _create_image_file(shop_di, "raw.png")
        generated_id = await _create_image_file(shop_di, "enhanced.png")
        await mock_llm_redis(
            [
                {
                    "type": "text",
                    "content": f"enhanced image stored as {generated_id}",
                }
            ]
        )
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/enhance-photo",
            json={"file_id": source_id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["file_id"] == generated_id

    async def test_ai_generate_photo_image_gen_branch(
        self,
        shop_client: AsyncClient,
        shop_di,
        mock_llm_redis,
        unique_id: str,
    ) -> None:
        """generate: без референсов image_gen → {"file_ids": [...]} → file_id."""
        shop = await _published_shop(shop_client, f"aig-{unique_id[:8]}")
        generated_id = await _create_image_file(shop_di, "generated.png")
        await mock_llm_redis([{"type": "text", "content": f"new image stored: {generated_id}"}])
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/generate-photo",
            json={"name": "Том ям", "description": "Острый суп с креветками"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["file_id"] == generated_id

    async def test_ai_generate_photo_empty_result_fails_closed(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """image_gen без file_id в ответе LLM — fail-closed ai_upstream, выдумок нет."""
        shop = await _published_shop(shop_client, f"aif-{unique_id[:8]}")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/generate-photo",
            json={"name": "Том ям"},
        )
        assert resp.status_code == 503
        assert resp.json().get("error_code") == "ai_upstream"

    async def test_ai_enhance_photo_unknown_file_404(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """enhance несуществующего файла — file_not_found до обращения к LLM."""
        shop = await _published_shop(shop_client, f"aiu-{unique_id[:8]}")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/enhance-photo",
            json={"file_id": "file_0000000000aa"},
        )
        assert resp.status_code == 404
        assert resp.json().get("error_code") == "file_not_found"

    async def test_ai_describe_shop_flow_branch(
        self,
        shop_client: AsyncClient,
        mock_llm_redis,
        mock_llm_capture,
        unique_id: str,
    ) -> None:
        """describe-shop: ветка describe_shop flow — промпт магазина с variables доходит до LLM."""
        await _reset_shop_flow()
        shop = await _published_shop(shop_client, f"aid-{unique_id[:8]}")
        await mock_llm_redis([{"type": "text", "content": "Уютная пиццерия у парка"}])
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/describe-shop",
            json={"name": "Пицца Парк", "description": "пицца и всё"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["text"] == "Уютная пиццерия у парка"

        calls = await mock_llm_capture()
        rendered = "\n".join(
            str(part.get("text", ""))
            for call in calls
            for message in call.get("messages", [])
            for part in message.get("parts", [])
        )
        assert "локального бизнеса" in rendered
        assert "Пицца Парк" in rendered

    async def test_ai_generate_cover_image_gen_branch(
        self,
        shop_client: AsyncClient,
        shop_di,
        mock_llm_redis,
        unique_id: str,
    ) -> None:
        """generate-cover: ветка generate_cover flow (image_gen) → file_id обложки."""
        await _reset_shop_flow()
        shop = await _published_shop(shop_client, f"aic-{unique_id[:8]}")
        generated_id = await _create_image_file(shop_di, "cover.png")
        await mock_llm_redis([{"type": "text", "content": f"cover stored: {generated_id}"}])
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/generate-cover",
            json={"name": "Пицца Парк", "description": "Семейная пиццерия"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["file_id"] == generated_id
