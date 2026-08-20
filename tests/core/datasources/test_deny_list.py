from __future__ import annotations

from urllib.parse import urlparse

import pytest

from core.config import get_settings
from core.datasources.deny_list import assert_datasource_host_allowed


def test_blocked_k8s_hosts() -> None:
    with pytest.raises(ValueError, match="platform database"):
        assert_datasource_host_allowed("postgres.platform.svc", 5432, "anything")
    with pytest.raises(ValueError, match="platform database"):
        assert_datasource_host_allowed("postgres", 5432, "anything")


def test_exact_platform_dsn_is_denied() -> None:
    raw = get_settings().database.shared_url
    parsed = urlparse(raw)
    if parsed.hostname is None:
        raise AssertionError("shared_url must have hostname")
    port = parsed.port if parsed.port is not None else 5432
    database_name = parsed.path.lstrip("/")
    with pytest.raises(ValueError, match="matches platform DSN"):
        assert_datasource_host_allowed(parsed.hostname, port, database_name)


def test_same_host_other_database_is_allowed() -> None:
    raw = get_settings().database.shared_url
    parsed = urlparse(raw)
    if parsed.hostname is None:
        raise AssertionError("shared_url must have hostname")
    port = parsed.port if parsed.port is not None else 5432
    database_name = parsed.path.lstrip("/")
    other = f"{database_name}_ds_probe"
    if other == database_name:
        raise AssertionError("probe database name must differ")
    assert_datasource_host_allowed(parsed.hostname, port, other)
