"""Размер пула code runner читается из Settings."""

import pytest

from core.capabilities.runner_pool import code_runner_pool_size
from core.config import get_settings
from core.config.base import BaseSettings


def test_code_runner_python_workers_reads_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_RUNNER__PYTHON_WORKERS", "4")
    assert BaseSettings().code_runner.python_workers == 4


def test_code_runner_pool_size_uses_configured_value() -> None:
    pool = get_settings().code_runner
    previous = pool.python_workers
    pool.python_workers = 3
    try:
        assert code_runner_pool_size("python") == 3
    finally:
        pool.python_workers = previous


def test_code_runner_go_pool_floor_is_two() -> None:
    pool = get_settings().code_runner
    previous = pool.go_workers
    pool.go_workers = 1
    try:
        assert code_runner_pool_size("go") == 2
    finally:
        pool.go_workers = previous


def test_code_runner_pool_size_default_follows_cpu() -> None:
    pool = get_settings().code_runner
    previous = pool.node_workers
    pool.node_workers = None
    try:
        size = code_runner_pool_size("node")
        assert 2 <= size <= 8
    finally:
        pool.node_workers = previous
