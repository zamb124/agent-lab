import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from core.config import get_settings
from core.db.repositories.company_repository import CompanyRepository
from core.db.storage import Storage


@dataclass(frozen=True)
class TopupResult:
    company_id: str
    subdomain: str | None
    name: str
    balance_before: float
    balance_after: float


def _iter_pages(*, page_size: int) -> Iterable[tuple[int, int]]:
    if page_size <= 0:
        raise ValueError("page_size должен быть > 0")
    offset = 0
    while True:
        yield offset, page_size
        offset += page_size


def _is_company_root_key(key: str) -> bool:
    if not key.startswith("company:"):
        return False
    parts = key.split(":")
    return len(parts) == 2 and parts[0] == "company" and parts[1] != ""


async def _run(*, amount: float, apply: bool, page_size: int) -> list[TopupResult]:
    if amount <= 0:
        raise ValueError("amount должен быть > 0")

    settings = get_settings()
    shared_url = settings.database.shared_url
    if not shared_url:
        raise RuntimeError("settings.database.shared_url не задан (проверьте conf.local.json)")

    storage = Storage(db_url=shared_url)
    repo = CompanyRepository(storage=storage)

    results: list[TopupResult] = []
    now = datetime.now(timezone.utc)

    for offset, limit in _iter_pages(page_size=page_size):
        raw = await storage._get_all_by_prefix_and_table("company:", "storage", limit, offset)
        if not raw:
            break

        for key, value_json in raw.items():
            if not _is_company_root_key(key):
                continue
            company_id = key.split(":", 1)[1]
            company = await repo.get(company_id)
            if company is None:
                continue
            before = float(company.balance)
            after = before + float(amount)
            results.append(
                TopupResult(
                    company_id=company.company_id,
                    subdomain=company.subdomain,
                    name=company.name,
                    balance_before=before,
                    balance_after=after,
                )
            )

            if apply:
                company.balance = after
                company.updated_at = now
                await repo.set(company)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Пополнить баланс всех компаний в shared БД.")
    parser.add_argument("--amount", type=float, default=1000.0, help="Сумма пополнения (RUB).")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Если указан — применить изменения. Без флага — только dry-run.",
    )
    parser.add_argument("--page-size", type=int, default=1000, help="Размер страницы при обходе компаний.")
    args = parser.parse_args()

    results = asyncio.run(
        _run(amount=float(args.amount), apply=bool(args.apply), page_size=int(args.page_size))
    )

    total = len(results)
    delta = float(args.amount) * total
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] companies={total} amount={float(args.amount):.2f} total_delta={delta:.2f}")
    for r in results:
        sub = r.subdomain if r.subdomain else "-"
        print(f"{r.company_id} subdomain={sub} {r.balance_before:.2f} -> {r.balance_after:.2f} name={r.name}")


if __name__ == "__main__":
    main()

