"""Import crawl domains from Tranco top list."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, datetime, timedelta

from apps.search.db.crawl_repositories import CrawlDomainRepository
from core.crawl.models import CrawlDomainSeed, SeedImportResult
from core.http import get_httpx_client
from core.http.client import SmartProxyClient
from core.types import JsonObject, parse_json_object

_TRANCO_LATEST_LIST_API = "https://tranco-list.eu/api/lists/date/latest"

_DOMAIN_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gov", (".gov.ru", ".gov.", "government", "gosuslugi", "kremlin.", "duma.", "minjust.", "nalog.", "cbr.ru")),
    ("wiki", ("wikipedia.org", "wikimedia.", "wiki.", "fandom.com")),
    ("docs", ("docs.", "documentation", "developer.", "dev.", "api.", "readme.", "manual.")),
    ("forum", ("forum.", "forums.", "community.", "discourse.", "pikabu.ru", "reddit.com")),
    ("blog", ("blog.", "medium.com", "livejournal.com", "habr.com", "vc.ru", "teletype.in")),
    ("media", (
        "news", "ria.", "tass.", "lenta.", "rbc.", "kommersant.", "vedomosti.", "gazeta.",
        "interfax.", "mk.ru", "kp.ru", "aif.ru", "fontanka.", "meduza.", "snob.", "thebell.",
        "tv", "radio", "journal", "press", "media", "rt.com", "sputnik",
    )),
    ("tech", (
        "github.", "gitlab.", "stackoverflow.", "stackexchange.", "npmjs.", "pypi.org",
        "docker.", "kubernetes.", "habr.", "ixbt.", "3dnews.", "serverfault.",
        "digitalocean.", "cloudflare.", "aws.", "azure.", "googlecloud.",
    )),
    ("finance", (
        "bank", "finance", "invest", "broker", "trading", "moex.", "bcs.", "sber.", "vtb.",
        "alfabank.", "tinkoff.", "finam.", "quote.", "market.", "crypto", "binance.", "bybit.",
    )),
    ("ecommerce", ("shop", "market", "store", "ozon", "wildberries", "aliexpress", "lamoda", "avito.")),
    ("social", ("vk.com", "ok.ru", "instagram", "facebook", "twitter", "t.me", "telegram.", "tiktok.")),
    ("sport", ("sport", "championat.", "sports.ru", "matchtv.", "eurofootball.", "fifa.", "uefa.", "khl.")),
    ("education", ("edu.", "university", "school", "academy", "coursera.", "stepik.", "netology.", "skillbox.")),
    ("health", ("med", "health", "clinic", "hospital", "apteka", "doctor", "pharmacy", "medportal.")),
    ("travel", ("travel", "booking.", "trip.", "tutu.", "aviasales.", "ostrovok.", "tourism", "hotel.")),
    ("auto", ("auto.", "cars.", "drive.", "drom.", "autonews.", "kolesa.", "car.", "motor.")),
    ("real_estate", ("realty", "real-estate", "cian.", "dom.", "m2.", "yard.", "property.")),
    ("law", ("law", "legal", "pravo.", "consultant.", "garant.", "sud.", "notariat.")),
    ("culture", ("culture", "theatre", "museum", "art.", "kino.", "kinopoisk.", "music.", "afisha.")),
    ("science", ("science", "nature.", "elementy.", "nplus1.", "scientific.", "research.", "arxiv.")),
    ("reference", ("dictionary", "translate.", "maps.", "weather.", "calendar.", "catalog.", "directory.")),
    ("jobs", ("job.", "jobs.", "hh.ru", "superjob.", "career.", "rabota.", "work.")),
    ("food", ("food", "restaurant", "delivery", "eda.", "menu.", "povar.", "gotovim.")),
    ("lifestyle", ("beauty", "fashion", "style", "woman.", "cosmo.", "elle.", "vogue.", "lifestyle.")),
    ("gaming", ("game", "games.", "steam.", "playstation.", "xbox.", "stopgame.", "dtf.ru")),
    ("tools", ("calc.", "converter.", "generator.", "online-tool", "utility.")),
)


async def _resolve_tranco_download_url(client: SmartProxyClient) -> str:
    api_response = await client.get(_TRANCO_LATEST_LIST_API)
    _ = api_response.raise_for_status()
    payload: JsonObject = parse_json_object(api_response.text, "tranco latest list api")
    download_url_value = payload.get("download")
    if not isinstance(download_url_value, str) or not download_url_value.strip():
        raise ValueError("tranco latest list api: download url is missing")
    return download_url_value.strip()


def _domain_category(domain: str) -> str:
    lowered = domain.lower()
    for category, tokens in _DOMAIN_CATEGORY_RULES:
        if any(token in lowered for token in tokens):
            return category
    return "unknown"


def _matches_ru_filter(domain: str, *, ru_tlds: tuple[str, ...], com_whitelist: tuple[str, ...]) -> bool:
    lowered = domain.lower()
    if any(lowered.endswith(tld) for tld in ru_tlds):
        return True
    if lowered.endswith(".com"):
        return lowered in com_whitelist or any(lowered.endswith(f".{item}") for item in com_whitelist)
    return False


async def import_tranco_domains(
    crawl_profile_id: str,
    *,
    crawl_domain_repository: CrawlDomainRepository,
    limit: int,
    ru_com_whitelist: tuple[str, ...],
    skip_categories: tuple[str, ...],
) -> SeedImportResult:
    ru_tlds = (".ru", ".рф", ".su")
    async with get_httpx_client(timeout=60.0, follow_redirects=True) as client:
        download_url = await _resolve_tranco_download_url(client)
        response = await client.get(download_url)
        _ = response.raise_for_status()
        raw = response.content
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            csv_name = next(name for name in archive.namelist() if name.endswith(".csv"))
            csv_text = archive.read(csv_name).decode("utf-8")
    else:
        csv_text = raw.decode("utf-8")

    seeds: list[CrawlDomainSeed] = []
    skipped = 0
    reader = csv.reader(io.StringIO(csv_text))
    for row in reader:
        if len(row) < 2:
            continue
        rank_raw = row[0].strip()
        domain_raw = row[1].strip()
        if domain_raw.lower() in {"domain", "domain_name"}:
            continue
        domain = domain_raw.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if not _matches_ru_filter(domain, ru_tlds=ru_tlds, com_whitelist=ru_com_whitelist):
            skipped += 1
            continue
        category = _domain_category(domain)
        if category in skip_categories:
            skipped += 1
            continue
        rank: int | None = None
        if rank_raw.isdigit():
            rank = int(rank_raw)
        seeds.append(
            CrawlDomainSeed(
                domain=domain,
                domain_rank=rank,
                category=category,
            )
        )
        if len(seeds) >= limit:
            break

    next_crawl = datetime.now(UTC) + timedelta(minutes=5)
    imported = await crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        seeds,
        next_crawl_after=next_crawl,
    )
    return SeedImportResult(imported=imported, skipped=skipped)
