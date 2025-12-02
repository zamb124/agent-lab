"""
Тесты загрузки конфигурации для разных сервисов.
Проверяем что каскадное переопределение работает правильно.
"""
import pytest
import os
from pathlib import Path

from core.config.loader import load_merged_config, merge_configs, load_json_config


@pytest.fixture(autouse=True)
def clean_env_vars():
    """Очищаем env переменные которые могут влиять на загрузку конфига"""
    env_vars_to_clean = [
        "DATABASE__URL", "DATABASE__SHARED_URL",
        "SERVER__ENV", "SERVER__PORT", "SERVER__DOMAIN"
    ]
    saved = {}
    for var in env_vars_to_clean:
        if var in os.environ:
            saved[var] = os.environ.pop(var)
    yield
    # Восстанавливаем
    for var, val in saved.items():
        os.environ[var] = val


class TestConfigLoading:
    """Тесты загрузки и объединения конфигурации"""

    @pytest.fixture
    def project_root(self):
        """Корень проекта"""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def base_config_path(self, project_root):
        """Путь к базовому конфигу"""
        return project_root / "conf.json"

    @pytest.fixture
    def agents_config_path(self, project_root):
        """Путь к конфигу agents сервиса"""
        return project_root / "apps" / "agents" / "conf.json"

    @pytest.fixture
    def frontend_config_path(self, project_root):
        """Путь к конфигу frontend сервиса"""
        return project_root / "apps" / "frontend" / "conf.json"

    def test_base_config_exists(self, base_config_path):
        """Базовый конфиг должен существовать"""
        assert base_config_path.exists(), f"Базовый конфиг не найден: {base_config_path}"

    def test_agents_config_exists(self, agents_config_path):
        """Конфиг agents сервиса должен существовать"""
        assert agents_config_path.exists(), f"Конфиг agents не найден: {agents_config_path}"

    def test_frontend_config_exists(self, frontend_config_path):
        """Конфиг frontend сервиса должен существовать"""
        assert frontend_config_path.exists(), f"Конфиг frontend не найден: {frontend_config_path}"

    def test_base_config_has_database(self, base_config_path):
        """Базовый конфиг должен содержать database секцию"""
        config = load_json_config(base_config_path)
        assert "database" in config, "Базовый конфиг должен содержать database"

    def test_agents_config_overrides_database(self, base_config_path, agents_config_path):
        """Agents конфиг должен переопределять database URL"""
        merged = load_merged_config(
            base_config_path=base_config_path,
            service_config_path=agents_config_path
        )
        
        agents_config = load_json_config(agents_config_path)
        
        if "database" in agents_config and "url" in agents_config["database"]:
            assert merged["database"]["url"] == agents_config["database"]["url"], \
                f"Agents database.url должен переопределить базовый: {merged['database']['url']}"

    def test_frontend_config_overrides_database(self, base_config_path, frontend_config_path):
        """Frontend конфиг должен переопределять database URL"""
        merged = load_merged_config(
            base_config_path=base_config_path,
            service_config_path=frontend_config_path
        )
        
        frontend_config = load_json_config(frontend_config_path)
        
        if "database" in frontend_config and "url" in frontend_config["database"]:
            assert merged["database"]["url"] == frontend_config["database"]["url"], \
                f"Frontend database.url должен переопределить базовый: {merged['database']['url']}"

    def test_agents_config_overrides_server_env(self, base_config_path, agents_config_path):
        """Agents конфиг должен переопределять server.env"""
        merged = load_merged_config(
            base_config_path=base_config_path,
            service_config_path=agents_config_path
        )
        
        agents_config = load_json_config(agents_config_path)
        
        if "server" in agents_config and "env" in agents_config["server"]:
            assert merged["server"]["env"] == agents_config["server"]["env"], \
                f"Agents server.env должен быть: {agents_config['server']['env']}, получили: {merged['server']['env']}"

    def test_frontend_config_overrides_server_env(self, base_config_path, frontend_config_path):
        """Frontend конфиг должен переопределять server.env"""
        merged = load_merged_config(
            base_config_path=base_config_path,
            service_config_path=frontend_config_path
        )
        
        frontend_config = load_json_config(frontend_config_path)
        
        if "server" in frontend_config and "env" in frontend_config["server"]:
            assert merged["server"]["env"] == frontend_config["server"]["env"], \
                f"Frontend server.env должен быть: {frontend_config['server']['env']}, получили: {merged['server']['env']}"


class TestMergeConfigs:
    """Тесты функции merge_configs"""

    def test_merge_simple_override(self):
        """Простое переопределение значений"""
        base = {"key1": "value1", "key2": "value2"}
        override = {"key2": "new_value2"}
        
        result = merge_configs(base, override)
        
        assert result["key1"] == "value1"
        assert result["key2"] == "new_value2"

    def test_merge_nested_override(self):
        """Вложенное переопределение"""
        base = {
            "server": {
                "env": "production",
                "port": 8001,
                "domain": "example.com"
            }
        }
        override = {
            "server": {
                "env": "local",
                "domain": "localhost"
            }
        }
        
        result = merge_configs(base, override)
        
        assert result["server"]["env"] == "local"
        assert result["server"]["port"] == 8001  # Не переопределен
        assert result["server"]["domain"] == "localhost"

    def test_merge_adds_new_keys(self):
        """Добавление новых ключей"""
        base = {"key1": "value1"}
        override = {"key2": "value2"}
        
        result = merge_configs(base, override)
        
        assert result["key1"] == "value1"
        assert result["key2"] == "value2"

    def test_merge_deep_nested(self):
        """Глубоко вложенное переопределение"""
        base = {
            "level1": {
                "level2": {
                    "key1": "value1",
                    "key2": "value2"
                }
            }
        }
        override = {
            "level1": {
                "level2": {
                    "key2": "new_value2"
                }
            }
        }
        
        result = merge_configs(base, override)
        
        assert result["level1"]["level2"]["key1"] == "value1"
        assert result["level1"]["level2"]["key2"] == "new_value2"


class TestAgentsServiceConfig:
    """Тесты конфигурации для agents сервиса"""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).parent.parent.parent.parent

    def test_agents_merged_config(self, project_root):
        """Проверка итоговой конфигурации agents сервиса"""
        merged = load_merged_config(
            base_config_path=project_root / "conf.json",
            service_config_path=project_root / "apps" / "agents" / "conf.json"
        )
        
        # Проверяем что server.env = local (из agents/conf.json)
        assert merged.get("server", {}).get("env") == "local", \
            f"server.env должен быть 'local', получили: {merged.get('server', {}).get('env')}"
        
        # Проверяем что database.url содержит localhost (из agents/conf.json)
        db_url = merged.get("database", {}).get("url", "")
        assert "localhost" in db_url, \
            f"database.url должен содержать 'localhost', получили: {db_url}"

    def test_agents_database_url_not_docker(self, project_root):
        """Database URL не должен содержать docker хост (postgres)"""
        merged = load_merged_config(
            base_config_path=project_root / "conf.json",
            service_config_path=project_root / "apps" / "agents" / "conf.json"
        )
        
        db_url = merged.get("database", {}).get("url", "")
        
        # Не должен быть docker хост
        assert "@postgres:" not in db_url, \
            f"database.url не должен содержать docker хост '@postgres:', получили: {db_url}"


class TestFrontendServiceConfig:
    """Тесты конфигурации для frontend сервиса"""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).parent.parent.parent.parent

    def test_frontend_merged_config(self, project_root):
        """Проверка итоговой конфигурации frontend сервиса"""
        merged = load_merged_config(
            base_config_path=project_root / "conf.json",
            service_config_path=project_root / "apps" / "frontend" / "conf.json"
        )
        
        # Проверяем что server.env = local (из frontend/conf.json)
        assert merged.get("server", {}).get("env") == "local", \
            f"server.env должен быть 'local', получили: {merged.get('server', {}).get('env')}"
        
        # Проверяем что server.domain = localhost (из frontend/conf.json)
        assert merged.get("server", {}).get("domain") == "localhost", \
            f"server.domain должен быть 'localhost', получили: {merged.get('server', {}).get('domain')}"

    def test_frontend_port_is_8002(self, project_root):
        """Frontend должен быть на порту 8002"""
        merged = load_merged_config(
            base_config_path=project_root / "conf.json",
            service_config_path=project_root / "apps" / "frontend" / "conf.json"
        )
        
        assert merged.get("server", {}).get("port") == 8002, \
            f"server.port должен быть 8002, получили: {merged.get('server', {}).get('port')}"


class TestOAuthRedirectUri:
    """Тесты для OAuth redirect_uri в local окружении"""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).parent.parent.parent.parent

    def test_oauth_redirect_should_use_real_domain_for_local(self, project_root):
        """
        При env=local, OAuth redirect_uri должен использовать PRIMARY_DOMAIN (humanitec.ru),
        а не localhost (т.к. OAuth провайдеры требуют зарегистрированный callback)
        """
        from core.utils.domain import PRIMARY_DOMAIN
        
        merged = load_merged_config(
            base_config_path=project_root / "conf.json",
            service_config_path=project_root / "apps" / "frontend" / "conf.json"
        )
        
        env = merged.get("server", {}).get("env")
        
        # Проверяем что env=local
        assert env == "local", f"Для теста нужен env=local, получили: {env}"
        
        # Логика из core/api/auth.py - всегда используем PRIMARY_DOMAIN
        redirect_uri = f"https://{PRIMARY_DOMAIN}/auth/callback/yandex"
        
        assert redirect_uri == f"https://{PRIMARY_DOMAIN}/auth/callback/yandex", \
            f"redirect_uri должен быть 'https://{PRIMARY_DOMAIN}/auth/callback/yandex', получили: {redirect_uri}"

