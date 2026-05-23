"""Реестр Lit-SPA сервисов для E2E: порты совпадают с tests/fixtures/services.py (SessionServerManager)."""

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
}
