"""
Тесты конфигурации: загрузка и переопределение через env переменные.
"""

import os
from unittest.mock import patch

import pytest

from apps.flows.config import FlowSettings
from core.config.loader import merge_configs, remove_env_overridden_values

# Алиас для совместимости с тестами
BaseSettings = FlowSettings


class TestMergeConfigs:
    """Тесты слияния конфигураций"""

    def test_merge_simple(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = merge_configs(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_nested(self):
        base = {"database": {"url": "old", "port": 5432}}
        override = {"database": {"url": "new"}}
        result = merge_configs(base, override)
        assert result == {"database": {"url": "new", "port": 5432}}

    def test_merge_deep_nested(self):
        base = {"llm": {"openai": {"api_key": "old", "base_url": "url"}}}
        override = {"llm": {"openai": {"api_key": "new"}}}
        result = merge_configs(base, override)
        assert result == {"llm": {"openai": {"api_key": "new", "base_url": "url"}}}


class TestEnvOverride:
    """Тесты переопределения через env переменные"""

    def test_env_overrides_top_level(self):
        config = {"server": {"port": 8001}, "debug": True}
        with patch.dict(os.environ, {"DEBUG": "false"}):
            result = remove_env_overridden_values(config)
        assert "debug" not in result
        assert result["server"]["port"] == 8001

    def test_env_overrides_nested(self):
        config = {"database": {"shared_url": "old_url", "redis_url": "redis://localhost"}}
        # Очищаем существующие env vars которые могут влиять на тест
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("DATABASE__")}
        clean_env["DATABASE__SHARED_URL"] = "new_url"
        with patch.dict(os.environ, clean_env, clear=True):
            result = remove_env_overridden_values(config)
        assert "shared_url" not in result.get("database", {})
        assert result["database"]["redis_url"] == "redis://localhost"

    def test_env_overrides_deep_nested(self):
        config = {"llm": {"openai": {"api_key": "json_key", "base_url": "url"}}}
        with patch.dict(os.environ, {"LLM__OPENAI__API_KEY": "env_key"}):
            result = remove_env_overridden_values(config)
        assert "api_key" not in result.get("llm", {}).get("openai", {})
        assert result["llm"]["openai"]["base_url"] == "url"


class TestBaseSettings:
    """Тесты BaseSettings с env переменными"""

    def test_env_override_database_url(self):
        env_url = "postgresql://test:test@testhost:5555/testdb"
        with patch.dict(os.environ, {"DATABASE__SHARED_URL": env_url}, clear=False):
            settings = BaseSettings()
        assert settings.database.shared_url == env_url

    def test_env_override_server_port(self):
        with patch.dict(os.environ, {"SERVER__PORT": "9999"}, clear=False):
            settings = BaseSettings()
        assert settings.server.port == 9999

    def test_env_override_llm_provider(self):
        with patch.dict(os.environ, {"LLM__PROVIDER": "bothub"}, clear=False):
            settings = BaseSettings()
        assert settings.llm.provider == "bothub"

    def test_env_override_nested_llm_openai_api_key(self):
        test_key = "sk-test-env-key-12345"
        env_vars = {"LLM__OPENAI__API_KEY": test_key}
        with patch.dict(os.environ, env_vars, clear=False):
            settings = BaseSettings()
        assert settings.llm.openai is not None
        assert settings.llm.openai.api_key == test_key

    def test_env_override_multiple_values(self):
        env_vars = {
            "DATABASE__SHARED_URL": "postgresql://env:env@envhost:1234/envdb",
            "SERVER__PORT": "7777",
            "SERVER__DEBUG": "true",
            "LLM__TEMPERATURE": "0.5",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = BaseSettings()
        assert settings.database.shared_url == "postgresql://env:env@envhost:1234/envdb"
        assert settings.server.port == 7777
        assert settings.server.debug is True
        assert settings.llm.temperature == 0.5


class TestConfigPriority:
    """Тесты приоритета конфигураций: env > conf.local.json > conf.json"""

    def test_env_has_highest_priority(self):
        """env переменные имеют высший приоритет"""
        env_port = "1111"
        with patch.dict(os.environ, {"SERVER__PORT": env_port}, clear=False):
            settings = BaseSettings()
        assert settings.server.port == int(env_port)

