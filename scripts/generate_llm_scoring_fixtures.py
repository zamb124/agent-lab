#!/usr/bin/env python3
"""Generate committed fixtures for platform LLM scoring offline tests.

Usage:
    uv run python scripts/generate_llm_scoring_fixtures.py
    uv run python scripts/generate_llm_scoring_fixtures.py --check
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "core" / "ai" / "fixtures" / "scoring"

sys.path.insert(0, str(REPO_ROOT))

from apps.flows.src.services.llm_models_service import LLMModelsService  # noqa: E402
from core.ai.adapters.catalog_base import AIProviderAdapterError  # noqa: E402
from core.ai.free_pool import (  # noqa: E402
    fetch_artificial_analysis_indices,
    platform_free_records_from_model_records,
)
from core.ai.model_catalog_repository import AIModelCatalogRepository  # noqa: E402
from core.ai.models import AIModelRecord  # noqa: E402
from core.ai.providers import AICapability  # noqa: E402
from core.ai.scoring import attach_artificial_analysis  # noqa: E402
from core.clients.redis_client import RedisClient  # noqa: E402
from core.clients.scheduler_client import SchedulerClient  # noqa: E402
from core.clients.service_client import ServiceClient  # noqa: E402
from core.config import get_settings  # noqa: E402
from core.db.storage import Storage  # noqa: E402
from tests.core.ai.scoring_fixture_support import (  # noqa: E402
    POOL_RANKING_PATH,
    PoolRankingSnapshot,
    ScoringFixtureBuildResult,
    catalog_by_key,
    catalog_fixture_path,
    compare_pool_ranking_snapshots,
    load_pool_ranking_snapshot,
    pool_ranking_snapshot_from_rows,
    pool_ranking_snapshot_to_json,
    pool_rows_from_records,
    settings_hash,
)
from tests.core.clients.live_llm_provider_helpers import (  # noqa: E402
    build_scored_free_pool,
    configured_free_pool_providers,
    is_provider_rate_limit,
    provider_api_key_configured,
)

_SKIP_CATALOG_STATUS_CODES = frozenset({401, 403, 410, 429, 500, 502, 503, 504})


def _model_service() -> LLMModelsService:
    settings = get_settings()
    db_url = settings.database.shared_url
    if not db_url:
        raise RuntimeError("database.shared_url не настроен")
    repository = AIModelCatalogRepository(Storage(db_url=db_url))
    scheduler_client = SchedulerClient(ServiceClient())
    redis_client = RedisClient(settings.database.redis_url)
    return LLMModelsService(repository, scheduler_client, redis_client)


def _free_pool_catalog_records(records: list[AIModelRecord], provider: str) -> list[AIModelRecord]:
    _ = provider
    settings = get_settings()
    eligible_ids = {
        record.id
        for record in platform_free_records_from_model_records(records, settings=settings)
    }
    return [
        record
        for record in records
        if record.model_id in eligible_ids
        and AICapability.LLM_CHAT in record.capabilities
    ]


async def _fetch_provider_catalog(
    provider: str,
    service: LLMModelsService,
) -> list[AIModelRecord] | None:
    try:
        records = await service.discover_model_records_by_provider(provider)
    except httpx.HTTPStatusError as status_error:
        if is_provider_rate_limit(provider, status_error):
            print(f"generate_llm_scoring_fixtures: skip {provider} — rate limit")
            return None
        if status_error.response.status_code in _SKIP_CATALOG_STATUS_CODES:
            print(
                "generate_llm_scoring_fixtures: skip "
                f"{provider} — HTTP {status_error.response.status_code}"
            )
            return None
        raise
    except AIProviderAdapterError as adapter_error:
        if adapter_error.status_code in _SKIP_CATALOG_STATUS_CODES:
            print(
                "generate_llm_scoring_fixtures: skip "
                f"{provider} — HTTP {adapter_error.status_code}"
            )
            return None
        raise
    return _free_pool_catalog_records(records, provider)


def _committed_snapshot_for_fetched_providers(
    committed: PoolRankingSnapshot,
    fetched_providers: tuple[str, ...],
) -> PoolRankingSnapshot:
    fetched = set(fetched_providers)
    return PoolRankingSnapshot(
        generated_at=committed.generated_at,
        providers=tuple(provider for provider in committed.providers if provider in fetched),
        settings_hash=committed.settings_hash,
        models=tuple(entry for entry in committed.models if entry.provider in fetched),
    )


async def _build_snapshot() -> ScoringFixtureBuildResult:
    providers = configured_free_pool_providers()
    if not providers:
        raise RuntimeError("Нет провайдеров с настроенным api_key для free pool")

    service = _model_service()
    records_by_provider: dict[str, list[AIModelRecord]] = {}
    for provider in providers:
        fetched = await _fetch_provider_catalog(provider, service)
        if fetched is None:
            continue
        records_by_provider[provider] = fetched

    if not records_by_provider:
        raise RuntimeError("ни один free-pool провайдер не вернул каталог")

    settings = get_settings()
    artificial_analysis = await fetch_artificial_analysis_indices(settings)
    records_by_provider = {
        provider: attach_artificial_analysis(records, artificial_analysis)
        for provider, records in records_by_provider.items()
    }
    fetched_providers = tuple(records_by_provider)
    pool_records = build_scored_free_pool(
        records_by_provider,
        settings,
        providers=fetched_providers,
    )
    catalog_index = catalog_by_key(records_by_provider)
    rows = pool_rows_from_records(pool_records, catalog_index, settings=settings)
    ranking = pool_ranking_snapshot_from_rows(
        generated_at=datetime.now(timezone.utc).isoformat(),
        providers=fetched_providers,
        settings_hash_value=settings_hash(settings),
        rows=rows,
    )
    return ScoringFixtureBuildResult(
        ranking=ranking,
        records_by_provider=records_by_provider,
    )


def _write_catalog_fixtures(records_by_provider: dict[str, list[AIModelRecord]]) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for provider, records in records_by_provider.items():
        path = catalog_fixture_path(provider)
        payload = [record.model_dump(mode="json") for record in records]
        _ = path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _write_pool_ranking(ranking: ScoringFixtureBuildResult) -> None:
    _ = POOL_RANKING_PATH.write_text(
        pool_ranking_snapshot_to_json(ranking.ranking),
        encoding="utf-8",
    )


async def _main_async(check_only: bool) -> int:
    if not any(provider_api_key_configured(provider) for provider in configured_free_pool_providers()):
        print("generate_llm_scoring_fixtures: skip — нет настроенных provider api_key")
        return 0

    build_result = await _build_snapshot()

    if check_only:
        if not POOL_RANKING_PATH.is_file():
            print("generate_llm_scoring_fixtures: pool_ranking.json отсутствует")
            return 1
        committed = _committed_snapshot_for_fetched_providers(
            load_pool_ranking_snapshot(),
            build_result.ranking.providers,
        )
        errors = compare_pool_ranking_snapshots(committed, build_result.ranking)
        if errors:
            for error in errors:
                print(f"generate_llm_scoring_fixtures: {error}")
            return 1
        print("generate_llm_scoring_fixtures: check OK")
        return 0

    _write_catalog_fixtures(build_result.records_by_provider)
    _write_pool_ranking(build_result)
    print(
        "generate_llm_scoring_fixtures: wrote",
        len(build_result.records_by_provider),
        "catalog fixtures and pool_ranking.json",
    )
    return 0


class _GenerateFixtureCliArgs(argparse.Namespace):
    check: bool = False


def _parse_check_only_flag() -> bool:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--check",
        action="store_true",
        help="Compare live snapshot with committed pool_ranking.json",
    )
    parsed = parser.parse_args(namespace=_GenerateFixtureCliArgs())
    return parsed.check


def main() -> int:
    return asyncio.run(_main_async(check_only=_parse_check_only_flag()))


if __name__ == "__main__":
    raise SystemExit(main())
