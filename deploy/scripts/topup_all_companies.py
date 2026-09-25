import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from core.config import get_settings
from core.db.oxyde_runtime import close_oxyde_databases, init_oxyde_databases
from core.models.identity_models import Company


@dataclass(frozen=True)
class TopupResult:
    company_id: str
    subdomain: str | None
    name: str
    balance_before: float
    balance_after: float


async def _run(*, amount: float, apply: bool, page_size: int) -> list[TopupResult]:
    if amount <= 0:
        raise ValueError("amount must be > 0")
    if page_size <= 0:
        raise ValueError("page_size must be > 0")

    settings = get_settings()
    shared_url = settings.database.shared_url
    if shared_url is None or shared_url == "":
        raise RuntimeError("database.shared_url is required")

    await init_oxyde_databases(default_url=shared_url, shared_url=shared_url)
    results: list[TopupResult] = []
    now = datetime.now(timezone.utc)
    offset = 0
    try:
        while True:
            companies = await Company.list(limit=page_size, offset=offset)
            if len(companies) == 0:
                break
            for company in companies:
                before = company.balance
                after = before + amount
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
                    _ = await Company.set(company)
            if len(companies) < page_size:
                break
            offset += page_size
    finally:
        await close_oxyde_databases()
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
    for result in results:
        subdomain = result.subdomain if result.subdomain else "-"
        print(
            f"{result.company_id} subdomain={subdomain} "
            f"{result.balance_before:.2f} -> {result.balance_after:.2f} name={result.name}"
        )


if __name__ == "__main__":
    main()
