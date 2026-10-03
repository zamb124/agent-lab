"""Каталоги кэша code runner читаются из Settings."""

import pytest

from core.capabilities.runner_cache import (
    code_runner_lsp_cache_root,
    code_runner_node_sandbox_modules,
    code_runner_python_sandbox_site,
    code_runner_repo_root,
)
from core.config import get_settings
from core.config.base import BaseSettings


def test_code_runner_lsp_cache_reads_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_RUNNER__LSP_CACHE", "/tmp/platform-lsp-cache")
    assert BaseSettings().code_runner.lsp_cache == "/tmp/platform-lsp-cache"


def test_lsp_cache_root_default_is_repo_cache() -> None:
    settings = get_settings().code_runner
    previous = settings.lsp_cache
    settings.lsp_cache = "  "
    try:
        assert code_runner_lsp_cache_root() == code_runner_repo_root() / ".cache"
    finally:
        settings.lsp_cache = previous


def test_python_sandbox_site_uses_configured_dir() -> None:
    settings = get_settings().code_runner
    previous = settings.python_sandbox_site
    settings.python_sandbox_site = "/tmp/python-sandbox-site"
    try:
        assert code_runner_python_sandbox_site().as_posix() == "/tmp/python-sandbox-site"
    finally:
        settings.python_sandbox_site = previous


def test_node_sandbox_modules_default_suffix() -> None:
    settings = get_settings().code_runner
    previous = settings.node_sandbox_modules
    settings.node_sandbox_modules = ""
    try:
        assert code_runner_node_sandbox_modules() == (
            code_runner_repo_root() / ".cache" / "code-runner-node-sandbox-modules"
        )
    finally:
        settings.node_sandbox_modules = previous
