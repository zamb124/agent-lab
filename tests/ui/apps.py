"""Реестр Lit-SPA сервисов для E2E: порты совпадают со стеком scripts/testing/stack.py."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceUiSpec:
    """Описание UI для поднятого HTTP-сервиса тестов."""

    key: str
    port: int
    spa_path: str
    shell_selector: str
    title: str | None
    subdomain_prefix: str | None = None


# Порты 9001–9005 — см. tests/fixtures/services.py (flows, rag, crm, frontend, sync).
SERVICE_UI_REGISTRY: dict[str, ServiceUiSpec] = {
    "flows": ServiceUiSpec(
        key="flows",
        port=9001,
        spa_path="/flows/example_react",
        shell_selector="flows-app",
        title=None,
    ),
    "rag": ServiceUiSpec(
        key="rag",
        port=9002,
        spa_path="/rag/",
        shell_selector="rag-app",
        title="RAG Service",
        subdomain_prefix="system",
    ),
    "crm": ServiceUiSpec(
        key="crm",
        port=9003,
        spa_path="/crm/",
        shell_selector="crm-app",
        title="NetWorkle - Умная Записная Книжка",
        subdomain_prefix="system",
    ),
    "frontend": ServiceUiSpec(
        key="frontend",
        port=9004,
        spa_path="/",
        shell_selector="frontend-app",
        title=None,
    ),
    "sync": ServiceUiSpec(
        key="sync",
        port=9005,
        spa_path="/sync/",
        shell_selector="sync-app",
        title="Sync Chat",
    ),
    "office": ServiceUiSpec(
        key="office",
        port=9008,
        spa_path="/documents/",
        shell_selector="office-app",
        title=None,
        subdomain_prefix="system",
    ),
    "worktracker": ServiceUiSpec(
        key="worktracker",
        port=9021,
        spa_path="/worktracker/",
        shell_selector="worktracker-app",
        title="Tasks",
    ),
    "wiki": ServiceUiSpec(
        key="wiki",
        port=9023,
        spa_path="/wiki/",
        shell_selector="wiki-app",
        title="Wiki",
        subdomain_prefix="system",
    ),
    "litserve": ServiceUiSpec(
        key="litserve",
        port=9014,
        spa_path="/litserve/",
        shell_selector="litserve-app",
        title=None,
    ),
    "shop": ServiceUiSpec(
        key="shop",
        port=9027,
        spa_path="/shop/",
        shell_selector="shop-app",
        title="Магазин",
    ),
    "geo": ServiceUiSpec(
        key="geo",
        port=9028,
        spa_path="/geo/",
        shell_selector="geo-app",
        title=None,
        subdomain_prefix="system",
    ),
}
