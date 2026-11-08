"""Сид контента для маркетинговых кадров — реальные API, worker-компания.

Shop: декларативный ``ShopSeedService.seed_company`` (4 витрины, ~70 фото).
Остальные сервисы — REST на origin воркер-компании, как e2e-хелперы.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx2

from core.context import clear_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User
from core.types import JsonObject
from tests.office.helpers import upload_office_file_bytes
from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.e2e_worker import (
    ui_e2e_scope_headers,
    ui_e2e_worker_id,
)
from tests.ui.harness import AppUI

SHOP_ADMIN_API = "/shop/api/v1"
SHOP_PUBLIC_API = f"{SHOP_ADMIN_API}/public"
SHOP_HOST_ORIGIN = "http://127.0.0.1:9027"

OFFICE_EXAMPLE_DOCS_DIR = (
    Path(__file__).resolve().parents[2] / "core/files/example-docs"
)


def owner_user_id() -> str:
    return f"ui_owner_{ui_e2e_worker_id()}"


def member_user_id() -> str:
    return f"ui_member_{ui_e2e_worker_id()}"


def api_origin(service_key: str) -> str:
    return AppUI(SERVICE_UI_REGISTRY[service_key]).origin


def api_client(service_key: str, token: str) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=api_origin(service_key),
        cookies={"auth_token": token},
        headers=ui_e2e_scope_headers(),
        timeout=60.0,
        trust_env=False,
    )


def bearer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **ui_e2e_scope_headers()}


async def _post(client: httpx2.AsyncClient, path: str, json: object) -> dict[str, Any]:
    resp = await client.post(path, json=json)
    if resp.status_code >= 400:
        raise AssertionError(f"POST {path} -> {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    if not isinstance(body, dict):
        raise AssertionError(f"POST {path}: response not object")
    return body


async def _get(client: httpx2.AsyncClient, path: str, **kw: Any) -> dict[str, Any]:
    resp = await client.get(path, **kw)
    if resp.status_code >= 400:
        raise AssertionError(f"GET {path} -> {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    if not isinstance(body, dict):
        raise AssertionError(f"GET {path}: response not object")
    return body


# === Shop: демо-витрины ===


async def _wait_storefront_snapshot(
    client: httpx2.AsyncClient, slug: str, timeout_s: float = 90.0
) -> JsonObject:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        resp = await client.get(f"{SHOP_PUBLIC_API}/storefront/{slug}")
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict):
                snapshot = body.get("snapshot", body)
                if isinstance(snapshot, dict) and (
                    snapshot.get("products") or snapshot.get("categories")
                ):
                    return body
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(f"снапшот витрины {slug} не собран за {timeout_s}s")
        await asyncio.sleep(2.0)


async def seed_demo_shops(
    shop_di, *, company_id: str, token: str
) -> dict[str, dict[str, str]]:
    """{tpl_key: {"id": shop_id, "slug": slug}} для витрин demo:{tpl}:{company}."""
    company = await Company.get(company_id)
    if company is None:
        raise AssertionError(f"worker company {company_id} не найдена")
    owner_id = owner_user_id()
    user = await User.get(owner_id)
    if user is None:
        raise AssertionError(f"worker owner {owner_id} не найден")

    ctx = build_job_context(
        company=company,
        user=user,
        host=f"{company.subdomain}.lvh.me",
        trace_id=f"shots-seed:{company_id}",
        session_id=f"shots-seed:{company_id}",
        channel="test",
    )
    _ = set_context(ctx)
    try:
        await shop_di.seed_service.seed_company(
            company=company, owner_user_id=owner_id
        )
    finally:
        clear_context()

    async with api_client("shop", token) as client:
        body = await _get(client, f"{SHOP_ADMIN_API}/shops")
    items = body.get("items")
    if not isinstance(items, list):
        raise AssertionError(f"/shops response без items: {list(body)}")

    shops: dict[str, dict[str, str]] = {}
    foreign: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        shop_id = str(item.get("shop_id", ""))
        slug = str(item.get("slug", ""))
        if not shop_id.startswith("demo:"):
            if shop_id:
                foreign.append(shop_id)
            continue
        tpl_key = shop_id.split(":")[1]
        shops[tpl_key] = {"id": shop_id, "slug": slug}
    if not shops:
        raise AssertionError(f"demo-витрины не найдены в /shops: {items}")

    # Кадр админки без витрин прошлых e2e-прогонов.
    if foreign:
        async with api_client("shop", token) as client:
            await asyncio.gather(
                *(
                    client.delete(f"{SHOP_ADMIN_API}/shops/{shop_id}")
                    for shop_id in foreign
                )
            )

    async with api_client("shop", token) as pub_client:
        for s in shops.values():
            resp = await pub_client.post(
                f"{SHOP_ADMIN_API}/shops/{s['id']}/publish"
            )
            if resp.status_code >= 400:
                raise AssertionError(
                    f"publish {s['id']} -> {resp.status_code}: {resp.text[:300]}"
                )

    ctx = build_job_context(
        company=company,
        user=user,
        host=f"{company.subdomain}.lvh.me",
        trace_id=f"shots-seed:{company_id}",
        session_id=f"shots-seed:{company_id}",
        channel="test",
    )
    _ = set_context(ctx)
    try:
        for s in shops.values():
            snapshot = await shop_di.storefront_service.rebuild_snapshot(s["slug"])
            if snapshot is None:
                raise AssertionError(f"rebuild_snapshot {s['slug']} вернул None")
    finally:
        clear_context()

    async with httpx2.AsyncClient(
        base_url=SHOP_HOST_ORIGIN, timeout=30.0, trust_env=False
    ) as public_client:
        await asyncio.gather(
            *(
                _wait_storefront_snapshot(public_client, s["slug"])
                for s in shops.values()
            )
        )
    return shops


# === CRM ===


async def _seed_crm(token: str) -> dict[str, Any]:
    async with api_client("crm", token) as client:
        ns = "sales"
        try:
            await _post(
                client,
                "/crm/api/v1/namespaces",
                {"name": ns, "description": "Воронка продаж", "template_id": "sales"},
            )
        except AssertionError:
            pass  # пространство уже есть при повторном прогоне

        types_body = await _get(
            client, "/crm/api/v1/entity-types", params={"namespace": ns, "limit": 500}
        )
        type_ids = [
            str(t["type_id"])
            for t in types_body.get("items", [])
            if isinstance(t, dict) and t.get("type_id")
        ]

        def pick(*needles: str) -> str | None:
            for tid in needles:
                if tid in type_ids:
                    return tid
            for tid in type_ids:
                if any(n in tid for n in needles):
                    return tid
            return None

        company_t = pick("company", "account", "organization")
        contact_t = pick("contact", "person")
        deal_t = pick("deal", "opportunity", "lead")
        note_t = pick("note")
        missing = [
            label
            for label, tid in (
                ("company", company_t),
                ("contact", contact_t),
                ("deal", deal_t),
                ("note", note_t),
            )
            if tid is None
        ]
        if missing:
            raise AssertionError(
                f"CRM {ns}: нет типов {missing} в namespace: {type_ids}"
            )

        existing_body = await _post(
            client,
            "/crm/api/v1/entities/query",
            {"namespace": ns, "limit": 1000},
        )
        existing_by_name: dict[str, str] = {}
        existing_rel: set[tuple[str, str, str]] = set()
        for it in existing_body.get("items", []):
            if isinstance(it, dict) and it.get("name"):
                eid = str(it.get("entity_id") or it.get("id") or "")
                if eid:
                    existing_by_name[str(it["name"])] = eid

        ids_by_name: dict[str, str] = dict(existing_by_name)

        async def ensure_entity(
            entity_type: str | None,
            name: str,
            desc: str,
            *,
            attributes: dict[str, Any] | None = None,
            entity_subtype: str | None = None,
            note_date: str | None = None,
        ) -> str | None:
            if entity_type is None:
                return None
            if name in ids_by_name:
                return ids_by_name[name]
            payload: dict[str, Any] = {
                "entity_type": entity_type,
                "namespace": ns,
                "name": name,
                "description": desc,
            }
            if attributes is not None:
                payload["attributes"] = attributes
            if entity_subtype is not None:
                payload["entity_subtype"] = entity_subtype
            if note_date is not None:
                payload["note_date"] = note_date
            e = await _post(client, "/crm/api/v1/entities", payload)
            eid = str(e.get("entity_id") or e.get("id") or "")
            ids_by_name[name] = eid
            return eid

        await ensure_entity(company_t, "ООО «Аврора Ритейл»", "Сеть из 24 магазинов, Pilot по подписке")
        await ensure_entity(company_t, "ИП Смирнова А.В.", "Кофейня у метро, интересует витрина + заказы")
        await ensure_entity(company_t, "ООО «ТехноДар»", "Дистрибьютор электроники, 120 сотрудников")

        await ensure_entity(contact_t, "Анна Смирнова", "Владелец кофейни, принимает решение по подписке")
        await ensure_entity(contact_t, "Дмитрий Козлов", "Директор по закупкам, Аврора Ритейл")
        await ensure_entity(contact_t, "Мария Орлова", "Операционный директор, ТехноДар")
        await ensure_entity(contact_t, "Игорь Савельев", "IT-директор, Аврора Ритейл")

        if deal_t:
            is_lead = "lead" in deal_t
            stages = ("qualified", "working", "new") if is_lead else ("negotiation", "proposal", "contract", "discovery")
            deals = (
                ("Подписка Linnex Pro — Аврора", "24 точки, годовой контракт", 2_880_000),
                ("Витрина + заказы — Кофейня", "Пилот на 2 месяца, 1 точка", 120_000),
                ("CRM + агенты — ТехноДар", "Внедрение на отдел продаж, 15 мест", 950_000),
                ("Расширение — Аврора", "Добавление склада и доставки", 800_000),
            )
            for i, (name, desc, amount) in enumerate(deals):
                await ensure_entity(
                    deal_t,
                    name,
                    desc,
                    attributes={
                        "stage": stages[i % len(stages)],
                        "source": "inbound",
                        "amount": amount,
                        "currency": "RUB",
                    },
                )

        today = datetime.now(timezone.utc).date()
        notes = (
            ("Звонок с Анной — кофейня", 0,
             "Обсудили витрину: хочет онлайн-заказы и программу лояльности. Прислать демо-ссылку."),
            ("Демо для Авроры — итоги", 0,
             "Показали CRM, Sync и витрину. Просят расчёт на 24 точки и кейс ритейла."),
            ("Возражение по цене", 1,
             "ТехноДар сравнивает с самописной связкой. Аргумент: единая платформа, агенты из коробки."),
            ("Встреча с ТехноДар — план внедрения", 2,
             "Пилот на 15 мест отдела продаж. Старт — импорт базы, затем агенты поверх данных."),
        )
        for name, days_ago, desc in notes:
            await ensure_entity(
                note_t,
                name,
                desc,
                note_date=(today - timedelta(days=days_ago)).isoformat(),
            )

        rel_specs = (
            ("Анна Смирнова", "ИП Смирнова А.В.", "belongs_to"),
            ("Дмитрий Козлов", "ООО «Аврора Ритейл»", "belongs_to"),
            ("Игорь Савельев", "ООО «Аврора Ритейл»", "belongs_to"),
            ("Мария Орлова", "ООО «ТехноДар»", "belongs_to"),
            ("Подписка Linnex Pro — Аврора", "ООО «Аврора Ритейл»", "belongs_to"),
            ("Витрина + заказы — Кофейня", "ИП Смирнова А.В.", "belongs_to"),
            ("CRM + агенты — ТехноДар", "ООО «ТехноДар»", "belongs_to"),
            ("Расширение — Аврора", "ООО «Аврора Ритейл»", "belongs_to"),
            ("Звонок с Анной — кофейня", "Анна Смирнова", "mentions"),
            ("Демо для Авроры — итоги", "ООО «Аврора Ритейл»", "mentions"),
            ("Возражение по цене", "ООО «ТехноДар»", "mentions"),
            ("Встреча с ТехноДар — план внедрения", "ООО «ТехноДар»", "mentions"),
            ("Подписка Linnex Pro — Аврора", "Дмитрий Козлов", "assigned_to"),
            ("Игорь Савельев", "Дмитрий Козлов", "reports_to"),
            ("Расширение — Аврора", "Подписка Linnex Pro — Аврора", "follows_up"),
        )
        rel_body = await _get(
            client,
            "/crm/api/v1/relationships",
            params={"namespace": ns, "limit": 1000},
        )
        for r in rel_body.get("items", []):
            if isinstance(r, dict):
                existing_rel.add(
                    (
                        str(r.get("source_entity_id")),
                        str(r.get("target_entity_id")),
                        str(r.get("relationship_type")),
                    )
                )
        for src_name, dst_name, rel_type in rel_specs:
            src_id = ids_by_name.get(src_name)
            dst_id = ids_by_name.get(dst_name)
            if not src_id or not dst_id:
                continue
            if (src_id, dst_id, rel_type) in existing_rel:
                continue
            await _post(
                client,
                "/crm/api/v1/relationships",
                {
                    "source_entity_id": src_id,
                    "target_entity_id": dst_id,
                    "relationship_type": rel_type,
                    "namespace": ns,
                    "weight": 1.0,
                },
            )

        tasks_body = await _get(
            client, "/crm/api/v1/activity-tasks", params={"namespace": ns, "limit": 200}
        )
        existing_tasks = {
            str(w.get("title"))
            for w in tasks_body.get("items", [])
            if isinstance(w, dict) and w.get("title")
        }
        for title, priority, days in (
            ("Позвонить Анне — демо витрины", "high", 1),
            ("Подготовить КП для Авроры (24 точки)", "urgent", 2),
            ("Встреча с ТехноДар — подписание", "high", 3),
            ("Отправить кейс ритейла Дмитрию", "normal", 5),
        ):
            if title in existing_tasks:
                continue
            await _post(
                client,
                "/crm/api/v1/activity-tasks",
                {
                    "title": title,
                    "namespace": ns,
                    "priority": priority,
                    "due_date": (today + timedelta(days=days)).isoformat(),
                    "assignees": [owner_user_id()],
                },
            )

    return {"namespace": ns, "entity_ids": list(ids_by_name.values())}


# === Sync ===


async def _seed_sync(token: str, member_token: str | None) -> dict[str, Any]:
    wanted = (
        ("Команда продукта", False),
        ("Запуск лендинга", False),
        ("Руководители", True),
    )
    channels: dict[str, str] = {}
    needed_members = {owner_user_id(), member_user_id()}
    async with api_client("sync", token) as client:
        existing = await _get(client, "/sync/api/v1/channels/", params={"limit": 200})
        for ch in existing.get("items", []):
            if isinstance(ch, dict) and isinstance(ch.get("name"), str):
                cid = ch.get("channel_id") or ch.get("id")
                if isinstance(cid, str) and cid:
                    channels[ch["name"]] = cid
        for name, is_private in wanted:
            if name in channels:
                continue
            body = await _post(
                client,
                "/sync/api/v1/channels/",
                {
                    "type": "group",
                    "name": name,
                    "namespace": "default",
                    "is_private": is_private,
                    "member_ids": sorted(needed_members),
                },
            )
            channel_id = body.get("channel_id")
            if not isinstance(channel_id, str) or not channel_id:
                raise AssertionError(f"POST /channels без channel_id: {list(body)}")
            channels[name] = channel_id

        # Каналы прошлых прогонов могли создаться без нужных участников.
        for cid in channels.values():
            members = await _get(client, f"/sync/api/v1/channels/{cid}/members")
            have = {
                str(m.get("user_id"))
                for m in members.get("items", [])
                if isinstance(m, dict)
            }
            for uid in sorted(needed_members - have):
                resp = await client.post(
                    f"/sync/api/v1/channels/{cid}/members",
                    json={"user_id": uid, "role": "member"},
                )
                if resp.status_code >= 400:
                    raise AssertionError(
                        f"POST /channels/{cid}/members -> {resp.status_code}: {resp.text[:300]}"
                    )

    convo = [
        ("owner", "Коллеги, обновила макеты главной — посмотрите секцию «Возможности платформы»"),
        ("member", "Выглядит отлично. Скриншоты витрин реально продают продукт"),
        ("owner", "Согласна. Добавлю ещё кадры CRM и доски задач — там теперь живые демо-данные"),
        ("member", "Для Shop сделаю подборку: витрина, корзина, админка. Высокое разрешение"),
        ("owner", "И не забудьте мобильный кадр — половина трафика лендинга с телефонов"),
        ("member", "Принято. К пятнице соберём финальные PNG и отдадим в вёрстку"),
        ("owner", "Ещё идея: кадр графа связей в CRM — он очень эффектно выглядит"),
        ("member", "Да, и карту Geo с маршрутами доставки. Обе в тёмной теме"),
    ]
    main_channel = channels["Команда продукта"]
    async with api_client("sync", token) as client:
        history = await _get(
            client,
            f"/sync/api/v1/channels/{main_channel}/messages",
            params={"limit": 50},
        )
    already = len(history.get("items", []))
    if already < len(convo):
        for who, text in convo:
            tok = token if who == "owner" else (member_token or token)
            async with api_client("sync", tok) as c:
                await _post(
                    c,
                    f"/sync/api/v1/channels/{main_channel}/messages",
                    {
                        "thread_id": None,
                        "parent_message_id": None,
                        "contents": [
                            {"type": "text/plain", "data": {"body": text}, "order": 0}
                        ],
                    },
                )
            await asyncio.sleep(0.05)

        async with api_client("sync", token) as client:
            for text in (
                "Финальные PNG витрин готовы — 2880px, все в одном стиле",
                "Предлагаю hero-кадр: витрина кофейни в светлой теме",
            ):
                await _post(
                    client,
                    f"/sync/api/v1/channels/{channels['Запуск лендинга']}/messages",
                    {
                        "thread_id": None,
                        "parent_message_id": None,
                        "contents": [
                            {"type": "text/plain", "data": {"body": text}, "order": 0}
                        ],
                    },
                )
    return {"channels": channels, "main_channel_id": main_channel}


# === Worktracker ===


async def _seed_worktracker(token: str) -> dict[str, Any]:
    async with api_client("worktracker", token) as client:
        boards = await _get(
            client, "/worktracker/api/v1/boards", params={"limit": 200}
        )
        board_id = ""
        for b in boards.get("items", []):
            if isinstance(b, dict) and b.get("name") == "Запуск Linnex 2.0":
                board_id = str(b.get("id") or b.get("board_id") or "")
                break
        if not board_id:
            board = await _post(
                client,
                "/worktracker/api/v1/boards",
                {
                    "name": "Запуск Linnex 2.0",
                    "board_key": "generic",
                    "columns": [
                        {"board_column_id": "backlog", "label": "Бэклог", "state": "open", "position": 0},
                        {"board_column_id": "doing", "label": "В работе", "state": "in_progress", "position": 1},
                        {"board_column_id": "review", "label": "На ревью", "state": "in_progress", "position": 2},
                        {"board_column_id": "done", "label": "Готово", "state": "done", "position": 3},
                    ],
                },
            )
            board_id = str(board.get("id") or board.get("board_id"))

        owner = {"assignee_kind": "users", "user_ids": [owner_user_id()]}
        member = {"assignee_kind": "users", "user_ids": [member_user_id()]}
        items = [
            ("Собрать маркетинговые скриншоты продуктов", "doing", "high", ["marketing", "launch"], owner),
            ("Обновить секцию «Возможности платформы»", "doing", "urgent", ["landing"], owner),
            ("Локализовать подписи кадров на EN", "backlog", "normal", ["i18n"], member),
            ("Проверить мобильные кадры витрин", "review", "high", ["shop", "mobile"], member),
            ("Сгенерировать optimized-ассеты через sips", "review", "normal", ["assets"], owner),
            ("Написать кейс: внедрение CRM в ритейле", "backlog", "low", ["content"], member),
            ("Прогнать UI-тесты параллельно и починить падения", "doing", "urgent", ["testing"], owner),
            ("Опубликовать релизные заметки 2.0", "done", "high", ["release"], member),
            ("Настроить demo-окружение для продаж", "done", "normal", ["sales"], owner),
        ]
        existing = await _get(
            client,
            "/worktracker/api/v1/work-items",
            params={"board_id": board_id, "limit": 1000},
        )
        existing_titles = {
            str(w.get("title"))
            for w in existing.get("items", [])
            if isinstance(w, dict) and w.get("title")
        }
        for i, (title, col, priority, labels, assignment) in enumerate(items):
            if title in existing_titles:
                continue
            await _post(
                client,
                "/worktracker/api/v1/work-items",
                {
                    "title": title,
                    "board_id": board_id,
                    "board_column_id": col,
                    "priority": priority,
                    "labels": labels,
                    "due_date": (
                        datetime.now(timezone.utc) + timedelta(days=i + 1)
                    ).isoformat(),
                    "assignment": assignment,
                },
            )
    return {"board_id": board_id}


# === Wiki ===


WIKI_PAGES: list[dict[str, str]] = [
    {
        "title": "База знаний Linnex",
        "icon": "📚",
        "markdown": (
            "# База знаний Linnex\n\n"
            "Единое место для регламентов, гайдов и решений команды.\n\n"
            "- [[Гайд по витрине Shop]] — как поднять онлайн-продажи за час\n"
            "- [[Playbook продаж]] — скрипты и возражения\n"
            "- [[Архитектура платформы]] — как устроены сервисы\n\n"
            "> Страницы индексируются в RAG — агенты отвечают по этой базе.\n"
        ),
    },
    {
        "title": "Гайд по витрине Shop",
        "icon": "🛍",
        "markdown": (
            "# Гайд по витрине Shop\n\n"
            "## Запуск\n\n"
            "1. Создайте витрину из шаблона (кафе, пекарня, магазин, пиццерия).\n"
            "2. Загрузите фото товаров — сид уже содержит ~70 изображений.\n"
            "3. Опубликуйте slug — витрина доступна на `<slug>.linnex.io`.\n\n"
            "## Возможности\n\n"
            "- Корзина и оформление заказа без регистрации\n"
            "- Модификаторы: размеры, добавки, составы\n"
            "- Программа лояльности «N-я покупка — награда»\n"
            "- Баннеры, акции и промокоды\n"
        ),
    },
    {
        "title": "Playbook продаж",
        "icon": "🎯",
        "markdown": (
            "# Playbook продаж\n\n"
            "## Первое касание\n\n"
            "Короткое видео-дено 2 минуты → ссылка на демо-витрину → звонок 15 минут.\n\n"
            "## Возражения\n\n"
            "| Возражение | Ответ |\n"
            "|---|---|\n"
            "| «Дорого» | Один подписочный контур вместо пяти SaaS |\n"
            "| «Уже есть CRM» | Миграция импортом + агенты поверх данных |\n"
            "| «Сложно внедрить» | Запуск витрины за час, CRM — из шаблона |\n"
        ),
    },
    {
        "title": "Архитектура платформы",
        "icon": "🏗",
        "markdown": (
            "# Архитектура платформы\n\n"
            "Один аккаунт — все сервисы: Flows, CRM, Sync, Documents, Wiki, "
            "Worktracker, Shop, Geo.\n\n"
            "```\n"
            "SPA → REST/WS → op_* → service → model (company_id scope)\n"
            "                ↘ platform:events → realtime → Centrifugo\n"
            "```\n\n"
            "Всё, за что платит платформа (LLM, embeddings, voice) — через "
            "billing span → settlement → баланс компании.\n"
        ),
    },
]


async def _seed_wiki(token: str) -> dict[str, Any]:
    page_ids: list[str] = []
    async with api_client("wiki", token) as client:
        tree = await _get(client, "/wiki/api/v1/pages")
        by_title: dict[str, str] = {}
        for item in tree.get("items", []):
            if isinstance(item, dict) and isinstance(item.get("title"), str):
                pid = item.get("wiki_page_id")
                if isinstance(pid, str) and pid:
                    by_title[item["title"]] = pid
        for spec in WIKI_PAGES:
            if spec["title"] in by_title:
                page_ids.append(by_title[spec["title"]])
                continue
            body = await _post(
                client,
                "/wiki/api/v1/pages",
                {
                    "title": spec["title"],
                    "icon": spec["icon"],
                    "markdown": spec["markdown"],
                },
            )
            page = body.get("page")
            if not isinstance(page, dict) or not page.get("wiki_page_id"):
                raise AssertionError(f"/pages response без page.wiki_page_id: {list(body)}")
            page_ids.append(str(page["wiki_page_id"]))
    return {"page_ids": page_ids}


# === Office ===


OFFICE_UPLOADS: tuple[tuple[str, str], ...] = (
    ("handbook-1p.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("2023-half-year-analyses-by-segment.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("sample-presentation.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
)


async def _seed_office(token: str) -> dict[str, Any]:
    file_ids: list[str] = []
    headers = bearer_headers(token)
    async with httpx2.AsyncClient(
        base_url=api_origin("office"), timeout=120.0, trust_env=False
    ) as client:
        ensured = await client.post(
            "/documents/api/v1/catalogs/ensure-path",
            headers=headers,
            json={"catalog_path": ["Documents"], "company_visible": True},
        )
        ensured.raise_for_status()
        documents_catalog_id = str(ensured.json().get("catalog_id") or "")
        if not documents_catalog_id:
            raise AssertionError(
                f"office: ensure-path не вернул catalog_id: {ensured.json()}"
            )

        items = await client.get(
            f"/documents/api/v1/catalogs/{documents_catalog_id}/items",
            headers=headers,
        )
        items.raise_for_status()
        existing: dict[str, str] = {}
        for it in items.json().get("documents", []):
            if isinstance(it, dict) and it.get("title") and it.get("file_id"):
                existing[str(it["title"])] = str(it["file_id"])
        for filename, content_type in OFFICE_UPLOADS:
            path = OFFICE_EXAMPLE_DOCS_DIR / filename
            if not path.exists():
                raise AssertionError(f"example-doc не найден: {path}")
            stem = path.stem
            hit = existing.get(filename) or existing.get(stem)
            if hit is None:
                for title, fid in existing.items():
                    if title == filename or title.startswith(stem):
                        hit = fid
                        break
            if hit is not None:
                file_ids.append(hit)
                continue
            payload = await upload_office_file_bytes(
                client,
                headers,
                filename=filename,
                content=path.read_bytes(),
                content_type=content_type,
                namespace="default",
            )
            file_ids.append(str(payload.get("file_id") or payload.get("id") or ""))
    return {"file_ids": [f for f in file_ids if f]}


# === Flows ===


def _marketing_flow_payload() -> dict[str, Any]:
    return {
        "flow_id": "sales_assistant",
        "name": "Ассистент продаж",
        "description": "Квалифицирует лид, ищет ответ в базе знаний и готовит письмо.",
        "entry": "intake",
        "nodes": {
            "intake": {
                "type": "llm_node",
                "name": "Разбор обращения",
                "prompt": "Ты ассистент продаж. Разбери входящее обращение клиента: тема, срочность, имя и контакт. Спроси недостающее через ask_user.",
                "tools": [{"tool_id": "ask_user"}],
                "agent_skills": [],
                "llm": {"model": "auto", "temperature": 0.3, "provider": "linnex_llm", "max_tokens": 1024},
                "pos_x": 120,
                "pos_y": 260,
            },
            "search_kb": {
                "type": "code",
                "name": "Поиск по базе знаний",
                "code": "async def run(args, state):\n    state['kb_context'] = state.get('kb_context', '')\n    return state",
                "language": "python",
                "pos_x": 420,
                "pos_y": 120,
            },
            "qualify": {
                "type": "code",
                "name": "Квалификация лида",
                "code": "async def run(args, state):\n    state['qualified'] = bool(state.get('contact'))\n    return state",
                "language": "python",
                "pos_x": 420,
                "pos_y": 400,
            },
            "draft_reply": {
                "type": "llm_node",
                "name": "Черновик ответа",
                "prompt": "Подготовь вежливый черновик ответа клиенту по данным обращения и базе знаний.",
                "tools": [{"tool_id": "ask_user"}],
                "agent_skills": [],
                "llm": {"model": "auto", "temperature": 0.4, "provider": "linnex_llm", "max_tokens": 1024},
                "pos_x": 720,
                "pos_y": 180,
            },
            "create_deal": {
                "type": "code",
                "name": "Создать сделку в CRM",
                "code": "async def run(args, state):\n    state['deal_created'] = True\n    return state",
                "language": "python",
                "pos_x": 720,
                "pos_y": 420,
            },
            "notify": {
                "type": "code",
                "name": "Уведомить в Sync",
                "code": "async def run(args, state):\n    state['notified'] = True\n    return state",
                "language": "python",
                "pos_x": 1020,
                "pos_y": 300,
            },
        },
        "edges": [
            {"from_node": "intake", "to_node": "search_kb"},
            {"from_node": "intake", "to_node": "qualify"},
            {"from_node": "search_kb", "to_node": "draft_reply"},
            {
                "from_node": "qualify",
                "to_node": "create_deal",
                "condition": {
                    "type": "simple",
                    "variable": "qualified",
                    "operator": "==",
                    "value": True,
                },
            },
            {"from_node": "qualify", "to_node": "draft_reply"},
            {"from_node": "draft_reply", "to_node": "notify"},
            {"from_node": "create_deal", "to_node": "notify"},
        ],
        "variables": {},
        "tags": ["sales", "marketing"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


async def _seed_flows(token: str) -> dict[str, Any]:
    async with api_client("flows", token) as client:
        await client.delete("/flows/api/v1/flows/sales_assistant")
        await _post(client, "/flows/api/v1/flows", _marketing_flow_payload())
    return {"flow_id": "sales_assistant"}


# === Orchestrator ===


async def seed_service_content(*, token: str, member_token: str | None = None) -> dict[str, Any]:
    seeds: dict[str, Any] = {}
    results = await asyncio.gather(
        _seed_crm(token),
        _seed_sync(token, member_token),
        _seed_worktracker(token),
        _seed_wiki(token),
        _seed_office(token),
        _seed_flows(token),
        return_exceptions=True,
    )
    keys = ("crm", "sync", "worktracker", "wiki", "office", "flows")
    for key, res in zip(keys, results):
        if isinstance(res, BaseException):
            seeds[key] = {"error": f"{type(res).__name__}: {res}"}
        else:
            seeds[key] = res
    return seeds
