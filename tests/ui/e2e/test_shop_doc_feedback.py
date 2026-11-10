"""Документационный сценарий Shop: отзыв покупателя и лента отзывов.

Маршрут покупателя: заказ выполнен → карточка «Оценить заказ» →
звёзды, чипы, комментарий → отзыв в публичной ленте.
"""

from __future__ import annotations

import httpx2
import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.test_shop_customer_auth_e2e import (
    _auth,
    _enter_phone,
    _page_url,
    _phone,
)
from tests.ui.e2e.test_shop_feedback_e2e import (
    _mark_done,
    feedback_storefront,  # noqa: F401 — фикстура
)
from tests.ui.e2e.test_shop_feed_e2e import _PHONE
from tests.ui.e2e.test_shop_storefront_desktop import Storefront
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="shop",
    tag="customer",
    doc_slug="customer-feedback",
    title="Отзывы покупателей: оценка и публичная лента",
    title_en="Customer feedback: rating and the public feed",
    description=(
        "**Для чего:** после выполненного заказа покупатель ставит "
        "оценку — отзывы собираются в ленту «Отзывы» на витрине и "
        "работают на репутацию.\n\n"
        "**Какие проблемы решает:** не нужно просить отзыв в мессенджере "
        "— карточка оценки появляется сама в кабинете покупателя; "
        "быстрые чипы («вкусно», «быстро») заменяют длинный текст.\n\n"
        "**Результат:** оценка и комментарий видны всем посетителям "
        "витрины со сводным рейтингом."
    ),
    description_en=(
        "**Purpose:** after a completed order the customer leaves a "
        "rating — reviews collect into the Reviews feed on the "
        "storefront and build reputation.\n\n"
        "**Problems solved:** no need to ask for a review in a "
        "messenger — the rating card appears in the customer's account "
        "by itself; quick chips replace long text.\n\n"
        "**Result:** rating and comment are visible to all storefront "
        "visitors with an aggregate score."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_customer_feedback(
    page: Page,
    feedback_storefront: Storefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
    scenario: ScenarioRecorder,
) -> None:
    sf = feedback_storefront
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(f"{_page_url(sf.slug)}?tmode=light", wait_until="load")
    await expect(page.locator(".item").first).to_be_visible(timeout=30_000)

    await page.locator(
        f".item[data-pid='{sf.plain_product_id}'] .add"
    ).click()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    await page.locator("#panel button", has_text="Самовывоз").click()
    await page.locator("#payBtn").click()
    await expect(_auth(page).locator(".sheet")).to_be_visible()
    await _enter_phone(page, _phone(unique_id))
    methods = _auth(page).locator("button.method")
    await expect(methods.first).to_be_visible()
    await methods.filter(has_text="Эмулятор").click()
    code_el = page.locator(".done .code")
    await expect(code_el).to_be_visible(timeout=20_000)
    code = ((await code_el.text_content()) or "").lstrip("#").strip()

    await _mark_done(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        sf.shop_id,
        code,
    )

    await page.keyboard.press("Escape")
    await page.locator(".acctnav [data-tab='orders']").click()
    card = page.locator(".acard", has_text=code)
    await expect(card).to_be_visible(timeout=15_000)
    await card.click()
    fb = page.locator(".acard.fb")
    await expect(fb).to_be_visible()
    stars = fb.locator(".fstar")
    await stars.nth(4).click()
    await expect(fb.locator(".fchip").first).to_be_visible()
    await fb.locator(".fchip").first.click()
    await fb.locator(".fbtext").fill("Очень вкусно и быстро")
    await scenario.step(
        "Оценка заказа",
        page,
        screenshot_name="feedback-form",
        label_en="Rating the order",
        details=(
            "В кабинете покупателя у выполненного заказа появляется "
            "карточка «Оценить заказ»: звёзды, быстрые чипы и поле "
            "комментария. Достаточно трёх нажатий."
        ),
        details_en=(
            "A completed order shows a Rate card in the customer's "
            "account: stars, quick chips and a comment field. Three "
            "taps are enough."
        ),
    )

    await fb.locator("[data-role='send']").click()
    await expect(fb.locator(".fbt")).to_have_text("Ваша оценка", timeout=10_000)

    await page.locator(".acctnav [data-tab='reviews']").click()
    await expect(page.locator(".rsum .rnum")).to_be_visible(timeout=15_000)
    ritem = page.locator(".ritem").first
    await expect(ritem.locator(".rcomment")).to_have_text(
        "Очень вкусно и быстро"
    )
    await scenario.step(
        "Лента отзывов",
        page,
        screenshot_name="reviews-feed",
        label_en="Reviews feed",
        details=(
            "Вкладка «Отзывы» открыта всем посетителям витрины: сводный "
            "рейтинг и карточки отзывов с комментариями. Честные "
            "оценки продают лучше любого текста."
        ),
        details_en=(
            "The Reviews tab is open to every storefront visitor: an "
            "aggregate score and review cards with comments. Honest "
            "ratings sell better than any copy."
        ),
    )
