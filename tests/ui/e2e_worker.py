"""Изоляция UI E2E по xdist-worker: company, subdomain, MockLLM scope.

Каждый worker (`gw0`…`gw4`) получает свою компанию и test_scope. Браузер шлёт
``X-Test-Scope``; pytest-процесс биндит тот же scope для ``flows_seed_mock_llm``.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

from core.logging import bind_log_context, unbind_log_context
from core.test_scope import LOG_TEST_SCOPE, TEST_SCOPE_HEADER

_ENV_WORKER = "UI_E2E_WORKER"
_ENV_SUBDOMAIN = "UI_E2E_SUBDOMAIN"
_ENV_SUBDOMAIN_C2 = "UI_E2E_SUBDOMAIN_C2"
_ENV_COMPANY_ID = "UI_E2E_COMPANY_ID"
_ENV_COMPANY2_ID = "UI_E2E_COMPANY2_ID"
_ENV_SCOPE = "UI_E2E_TEST_SCOPE"


def ui_e2e_worker_id() -> str:
    """Идентификатор worker: ``gw0``… или ``gw0`` для serial/master."""
    explicit = os.environ.get(_ENV_WORKER, "").strip()
    if explicit:
        return explicit
    xdist = os.environ.get("PYTEST_XDIST_WORKER", "").strip()
    if xdist == "" or xdist == "master":
        return "gw0"
    return xdist


def ui_e2e_company_id() -> str:
    return f"ui_e2e_{ui_e2e_worker_id()}"


def ui_e2e_company2_id() -> str:
    return f"ui_e2e_{ui_e2e_worker_id()}_c2"


def ui_e2e_subdomain() -> str:
    """Host-slug primary company: ``ui-gw0``."""
    return f"ui-{ui_e2e_worker_id()}"


def ui_e2e_subdomain_company2() -> str:
    return f"ui-{ui_e2e_worker_id()}-c2"


def ui_e2e_test_scope() -> str:
    return f"test_e2e_{ui_e2e_worker_id()}"


def ui_e2e_hitl_queue_slug(base_slug: str) -> str:
    return f"{base_slug}_{ui_e2e_worker_id()}"


def publish_ui_e2e_worker_env() -> None:
    """Прописывает env для AppUI.origin и диагностики (вызывать из session fixture)."""
    os.environ[_ENV_WORKER] = ui_e2e_worker_id()
    os.environ[_ENV_COMPANY_ID] = ui_e2e_company_id()
    os.environ[_ENV_COMPANY2_ID] = ui_e2e_company2_id()
    os.environ[_ENV_SUBDOMAIN] = ui_e2e_subdomain()
    os.environ[_ENV_SUBDOMAIN_C2] = ui_e2e_subdomain_company2()
    os.environ[_ENV_SCOPE] = ui_e2e_test_scope()


def ui_e2e_scope_headers() -> dict[str, str]:
    return {TEST_SCOPE_HEADER: ui_e2e_test_scope()}


@contextmanager
def bind_ui_e2e_worker_scope() -> Generator[str, None, None]:
    scope = ui_e2e_test_scope()
    bind_log_context(**{LOG_TEST_SCOPE: scope})
    try:
        yield scope
    finally:
        unbind_log_context(LOG_TEST_SCOPE)


def resolve_ui_e2e_host_subdomain(spec_prefix: str | None) -> str:
    """Какой subdomain в Host для ServiceUiSpec при worker-изоляции."""
    primary = os.environ.get(_ENV_SUBDOMAIN, "").strip()
    company2 = os.environ.get(_ENV_SUBDOMAIN_C2, "").strip()
    if spec_prefix == "company2" and company2:
        return company2
    if primary:
        return primary
    if spec_prefix and spec_prefix.strip():
        return spec_prefix.strip()
    return "system"
