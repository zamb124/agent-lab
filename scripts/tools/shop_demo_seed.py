"""Досев demo-витрин shop в существующие компании.

``python -m scripts.tools.shop_demo_seed [--company ID ...] [--dry-run]``

Ставит задачу ``shop_seed_demo_company`` (очередь ``shop``) на каждую
целевую компанию: сама задача идемпотентна — шаблоны, чьи строки уже
существуют или удалены владельцем, пропускаются, повторный запуск
ничего не дублирует. ``--dry-run`` печатает план без постановки задач.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from apps.shop.config import ShopSettings
from apps.shop.di import ShopDi
from apps.shop.models.shop import Shop
from apps.shop.tasks.task_names import SHOP_SEED_DEMO_COMPANY
from core.app.factory import prepare_service_settings
from core.di.kit import ProcessIdentity
from core.di.process import open_di
from core.models.identity_models import Company
from core.tasks import enqueue

_DEMO_PREFIX = "demo:"


async def _all_companies() -> list[Company]:
    companies: list[Company] = []
    offset = 0
    while True:
        page, has_more = (
            await Company.page_named_after_system_by_name_and_company_id_asc(
                limit=500, offset=offset
            )
        )
        companies.extend(page)
        if not has_more:
            return companies
        offset += len(page)


async def _existing_demo_templates(company_id: str) -> set[str]:
    rows = await Shop.list_alive_by_company_by_updated_desc(company_id)
    return {row.demo_template for row in rows if row.demo_template}


class _CliArgs(argparse.Namespace):
    company_ids: list[str] | None = None
    dry_run: bool = False


async def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Enqueue shop demo-shop seed for existing companies"
    )
    _ = parser.add_argument(
        "--company",
        action="append",
        dest="company_ids",
        help="Target only these company_id (repeatable); default — all companies",
    )
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without enqueuing tasks",
    )
    args = parser.parse_args(namespace=_CliArgs())

    settings, _project_root, files_segment = prepare_service_settings(
        "shop", ShopSettings, documentation_gateway_prefix=None
    )
    async with open_di(
        ShopDi,
        settings=settings,
        identity=ProcessIdentity(
            service_name="shop", files_route_segment=files_segment
        ),
        database="shop_url",
    ):
        if args.company_ids:
            companies: list[Company] = []
            for company_id in args.company_ids:
                company = await Company.get(company_id)
                if company is None:
                    raise ValueError(f"company {company_id!r} not found")
                companies.append(company)
        else:
            companies = await _all_companies()

        enqueued = 0
        for company in companies:
            existing = await _existing_demo_templates(company.company_id)
            if args.dry_run:
                print(
                    f"{company.company_id} {company.name!r}: seeded={sorted(existing) or 'none'}"
                )
                continue
            task = await enqueue(
                SHOP_SEED_DEMO_COMPANY,
                company_id=company.company_id,
                owner_user_id="",
            )
            enqueued += 1
            print(
                f"{company.company_id} {company.name!r}: task_id={task.task_id} seeded={sorted(existing) or 'none'}"
            )
        print(f"done: {enqueued} task(s) enqueued")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
