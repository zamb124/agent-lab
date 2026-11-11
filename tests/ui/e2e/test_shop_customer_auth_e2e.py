"""Витрина Shop + `<platform-customer-auth>` end-to-end в браузере.

Продовый путь: реальный Granian :9027, Chromium, анонимный покупатель.
Авторизация идёт через настоящий роутер `/shop/api/v1/public/customer-auth`
на стеке — без моков: эмуляторный метод подтверждается direct-proof,
«SMS»-код читается из реального Redis challenge (`provider_message_id` =
`emu-<code>` — outbox эмулятора доставки).
"""

from __future__ import annotations

import json
import re

import httpx2
import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from playwright.async_api import Page, expect

from tests.ui.e2e.test_shop_storefront_desktop import (
    Storefront,
    _create_storefront,
)
from tests.ui.e2e_worker import ui_e2e_scope_headers


def _page_url(slug: str) -> str:
    """Витрина по прямому маршруту на 127.0.0.1: secure context даёт
    crypto.randomUUID (на *.lvh.me по http его нет), а customer_token —
    host-only cookie, доезжающая до `POST /orders`."""
    return f"http://127.0.0.1:9027/shop/api/v1/public/s/{slug}"

_REDIS_URL = "redis://localhost:63792/0"
_CHALLENGE_KEY_PREFIX = "cust_auth:ch:"


def _phone(unique_id: str) -> str:
    """Уникальный номер на тест — лимит start считается по телефону."""
    return f"+7999{int(unique_id[:8], 16) % 10**7:07d}"


@pytest_asyncio.fixture
async def auth_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> Storefront:
    """Одна категория, один товар — минимальная витрина для чекаута."""
    _ = shop_worker
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    slug = f"e2ea-{unique_id[:8]}"
    return await _create_storefront(
        shop_client_http,
        headers,
        slug,
        categories=("Меню",),
        products_per_category=1,
        shop_patch={
            "delivery_enabled": True,
            "pickup_enabled": True,
        },
    )


async def _open_cart_to_pay(page: Page, storefront: Storefront) -> None:
    """Анонимный покупатель: блюдо в корзину → sheet оплаты."""
    _ = await page.goto(_page_url(storefront.slug), wait_until="load")
    await expect(page.locator(".item").first).to_be_visible()
    await page.locator(f".item[data-pid='{storefront.plain_product_id}'] .add").click()
    await expect(page.locator("#cart.show")).to_be_visible()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    # Способ выдачи по умолчанию — доставка: адрес обязателен.
    await page.locator("#ca").fill("Тверская, 1")


def _auth(page: Page):
    return page.locator("platform-customer-auth")


async def _enter_phone(page: Page, phone: str) -> None:
    """Шаг телефона внутри shadow root (playwright CSS pierces shadow)."""
    await expect(_auth(page).locator("input[type=tel]")).to_be_visible()
    await _auth(page).locator("input[type=tel]").fill(phone)
    await _auth(page).locator("button.primary").click()


async def _challenge_code(phone: str) -> str:
    """Читаем «доставленный» код из реального Redis challenge по номеру.

    `EmulatorCodeSender` кладёт `provider_message_id=emu-<code>` — это
    outbox канала доставки на тестовом стенде.
    """
    client = aioredis.from_url(_REDIS_URL)
    try:
        keys = [k async for k in client.scan_iter(f"{_CHALLENGE_KEY_PREFIX}phc_*")]
        best: tuple[int, str] | None = None
        for key in keys:
            raw = await client.get(key)
            if raw is None:
                continue
            data = json.loads(raw)
            if data.get("phone_e164") != phone:
                continue
            msg_id = data.get("provider_data", {}).get("provider_message_id", "")
            match = re.fullmatch(r"emu-(\d+)", msg_id)
            if not match:
                continue
            created = int(data.get("created_ts", 0))
            if best is None or created > best[0]:
                best = (created, match.group(1))
        if best is None:
            raise AssertionError(f"challenge с кодом для {phone} не найден в Redis")
        return best[1]
    finally:
        await client.aclose()


async def _order_phone_and_id(
    shop_client_http: httpx2.AsyncClient,
    headers: dict[str, str],
    storefront: Storefront,
    public_code: str,
) -> tuple[str, str]:
    """Заказ через админское REST-зеркало: phone/customer_id — из сессии."""
    resp = await shop_client_http.get(
        f"/shop/api/v1/shops/{storefront.shop_id}/orders", headers=headers
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    order = next(o for o in items if o["public_code"] == public_code)
    return str(order["customer_phone"]), str(order["customer_id"])


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_checkout_auth_emulator_auto_and_order_identity(
    page: Page,
    auth_storefront: Storefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Эмулятор (ui=auto): метод → direct-verify → заказ с identity из сессии."""
    phone = _phone(unique_id)
    await _open_cart_to_pay(page, auth_storefront)
    await page.locator("#payBtn").click()
    # Лист авторизации: телефон → методы.
    await expect(_auth(page).locator(".sheet")).to_be_visible()
    await _enter_phone(page, phone)
    methods = _auth(page).locator("button.method")
    await expect(methods.first).to_be_visible()
    await methods.filter(has_text="Эмулятор").click()
    # Авто-подтверждение → заказ уходит, экран «Заказ принят».
    await expect(page.locator(".done .code")).to_be_visible(timeout=15_000)
    code = await page.locator(".done .code").inner_text()
    public_code = code.lstrip("#")
    cookies = await page.context.cookies()
    assert any(c["name"] == "customer_token" for c in cookies)
    order_phone, customer_id = await _order_phone_and_id(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        auth_storefront,
        public_code,
    )
    assert order_phone == phone
    assert customer_id.startswith("cust_")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_checkout_auth_sms_code_flow(
    page: Page,
    auth_storefront: Storefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """«Код по SMS»: код из Redis-challenge эмулятора → verify → заказ."""
    phone = _phone(unique_id)
    await _open_cart_to_pay(page, auth_storefront)
    await page.locator("#payBtn").click()
    await _enter_phone(page, phone)
    methods = _auth(page).locator("button.method")
    await expect(methods.first).to_be_visible()
    await methods.filter(has_text="SMS").click()
    # Шаг кода: читаем реально «отправленный» код из Redis challenge.
    code_input = _auth(page).locator("input[inputmode=numeric]")
    await expect(code_input).to_be_visible()
    code = await _challenge_code(phone)
    await code_input.fill(code)
    await _auth(page).locator("button.primary").click()
    await expect(page.locator(".done .code")).to_be_visible(timeout=15_000)
    public_code = (await page.locator(".done .code").inner_text()).lstrip("#")
    order_phone, customer_id = await _order_phone_and_id(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        auth_storefront,
        public_code,
    )
    assert order_phone == phone
    assert customer_id


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_checkout_auth_cancel_blocks_order(
    page: Page, auth_storefront: Storefront, unique_id: str
) -> None:
    """Закрыли лист без подтверждения → заказ не создан."""
    await _open_cart_to_pay(page, auth_storefront)
    await page.locator("#payBtn").click()
    await expect(_auth(page).locator(".sheet")).to_be_visible()
    await _enter_phone(page, _phone(unique_id))
    # Клик по overlay (не по sheet) → customer-auth-cancelled → submit обрывается.
    await _auth(page).locator(".overlay").click(position={"x": 10, "y": 10})
    await expect(_auth(page).locator(".sheet")).to_be_hidden()
    await page.wait_for_timeout(500)
    assert await page.locator(".done .code").count() == 0


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_second_checkout_reuses_customer_session(
    page: Page, auth_storefront: Storefront, unique_id: str
) -> None:
    """Повторный заказ: сессия жива → лист не открывается, заказ сразу."""
    await _open_cart_to_pay(page, auth_storefront)
    await page.locator("#payBtn").click()
    await _enter_phone(page, _phone(unique_id))
    methods = _auth(page).locator("button.method")
    await methods.filter(has_text="Эмулятор").click()
    await expect(page.locator(".done .code")).to_be_visible(timeout=15_000)
    # Второй заказ: /me 200 → ensureAuth резолвится мгновенно, без UI.
    await page.keyboard.press("Escape")
    await expect(page.locator("#sheet.show")).to_be_hidden()
    # data-qty не перерисовывается после cart.clear(): кнопка «+» в stepper.
    await page.locator(
        f".item[data-pid='{auth_storefront.plain_product_id}'] .stepper button:not(.ghost)"
    ).click()
    await expect(page.locator("#cart.show")).to_be_visible()
    await page.locator("#cart").click()
    await page.locator("#ca").fill("Тверская, 1")
    await page.locator("#payBtn").click()
    await expect(page.locator(".done .code")).to_be_visible(timeout=15_000)
    # Лист авторизации так и не открылся.
    assert await _auth(page).locator(".sheet").count() == 0


@pytest.mark.scenario(
    service="shop",
    tag="customer",
    doc_slug="customer-auth-phone",
    title="Вход покупателя по номеру телефона",
    title_en="Customer sign-in by phone number",
    description=(
        "**Для чего:** покупателю не нужны пароли и регистрация — "
        "номер телефона и код из SMS открывают заказы, адреса и "
        "лояльность.\n\n"
        "**Какие проблемы решает:** вход всплывает только там, где он "
        "нужен — при оформлении заказа или в личном кабинете. Покупатель "
        "не заполняет анкету и ничего не запоминает.\n\n"
        "**Результат:** покупатель вошёл — заказ оформлен и привязан "
        "к его номеру."
    ),
    description_en=(
        "**Purpose:** customers need no passwords or registration — a "
        "phone number and an SMS code unlock orders, addresses and "
        "loyalty.\n\n"
        "**Problems solved:** sign-in pops up only where needed — at "
        "checkout or in the account. The customer fills no forms and "
        "memorizes nothing.\n\n"
        "**Result:** the customer is signed in — the order is placed "
        "and bound to their number."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_customer_auth_phone_scenario(
    page: Page,
    auth_storefront: Storefront,
    unique_id: str,
    scenario,
) -> None:
    phone = _phone(unique_id)
    await _open_cart_to_pay(page, auth_storefront)
    await page.locator("#payBtn").click()

    await expect(_auth(page).locator(".sheet")).to_be_visible()
    await scenario.step(
        "Введите номер телефона",
        page,
        screenshot_name="auth-phone",
        label_en="Enter the phone number",
        details=(
            "При оформлении заказа витрина просит номер телефона — это "
            "и есть вход. Отдельной регистрации нет: номер — ваш "
            "аккаунт."
        ),
        details_en=(
            "At checkout the storefront asks for a phone number — that "
            "is the sign-in. There is no separate registration: the "
            "number is your account."
        ),
    )

    await _enter_phone(page, phone)
    methods = _auth(page).locator("button.method")
    await expect(methods.first).to_be_visible()
    await scenario.step(
        "Выберите способ подтверждения",
        page,
        screenshot_name="auth-methods",
        label_en="Choose a confirmation method",
        details=(
            "Витрина предлагает способы подтверждения номера — "
            "например, код по SMS. Выбирайте удобный: ничего "
            "запоминать не нужно."
        ),
        details_en=(
            "The storefront offers ways to confirm the number — for "
            "example, an SMS code. Pick whichever is convenient: "
            "nothing to memorize."
        ),
    )

    await methods.filter(has_text="SMS").click()
    code_input = _auth(page).locator("input[inputmode=numeric]")
    await expect(code_input).to_be_visible()
    code = await _challenge_code(phone)
    await code_input.fill(code)
    await scenario.step(
        "Введите код из SMS",
        page,
        screenshot_name="auth-code",
        label_en="Enter the SMS code",
        details=(
            "На номер приходит короткий код — впишите его в поле. "
            "Код одноразовый и живёт несколько минут."
        ),
        details_en=(
            "A short code arrives by SMS — type it into the field. "
            "The code is one-time and lives for a few minutes."
        ),
    )

    await _auth(page).locator("button.primary").click()
    await expect(page.locator(".done .code")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Вход выполнен — заказ принят",
        page,
        screenshot_name="auth-done",
        label_en="Signed in — order accepted",
        details=(
            "После подтверждения номера заказ уходит в работу и "
            "получает номер. В следующий раз вход уже не понадобится — "
            "витрина вас помнит.\n\n"
            "**Итог.** Телефон — это и аккаунт, и подтверждение: "
            "покупатель заходит без пароля, а заказ сразу привязан "
            "к нему."
        ),
        details_en=(
            "After the number is confirmed the order goes to work and "
            "gets a number. Next time no sign-in is needed — the "
            "storefront remembers you.\n\n"
            "**Summary.** The phone is both the account and the "
            "confirmation: the customer signs in passwordless and the "
            "order is bound to them right away."
        ),
    )
