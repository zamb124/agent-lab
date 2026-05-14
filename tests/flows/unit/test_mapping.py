"""
Тесты для MappingResolver - единой логики резолвинга @state:path.

MappingResolver работает с dict представлением ExecutionState (state.model_dump()).

Покрывает все сценарии:
- resolve_value: @state:path, @var:path, константы, вложенные пути
- get_nested_value: простые и сложные пути
- build_mapped_state: маппинг полей state
- resolve_vars_in_string: замена @var: внутри строк
"""

import pytest

from apps.flows.src.mapping import MappingResolver
from core.variables import VariableResolutionError


class TestResolveValue:
    """Тесты для resolve_value - резолвинг одного значения из dict state."""

    def test_resolve_simple_state_path(self):
        """@state:field -> state_dict["field"]"""
        state = {"content": "hello", "user": "John"}

        result = MappingResolver.resolve_value("@state:content", state)

        assert result == "hello"

    def test_resolve_nested_state_path(self):
        """@state:user.name -> state["user"]["name"]"""
        state = {
            "user": {
                "name": "John",
                "profile": {
                    "age": 30,
                    "city": "Moscow"
                }
            }
        }

        assert MappingResolver.resolve_value("@state:user.name", state) == "John"
        assert MappingResolver.resolve_value("@state:user.profile.age", state) == 30
        assert MappingResolver.resolve_value("@state:user.profile.city", state) == "Moscow"

    def test_resolve_deeply_nested_path(self):
        """@state:a.b.c.d.e -> глубоко вложенное значение"""
        state = {
            "a": {
                "b": {
                    "c": {
                        "d": {
                            "e": "deep_value"
                        }
                    }
                }
            }
        }

        result = MappingResolver.resolve_value("@state:a.b.c.d.e", state)

        assert result == "deep_value"

    def test_resolve_constant_string(self):
        """Строка без @state: -> константа"""
        state = {"content": "hello"}

        result = MappingResolver.resolve_value("fixed_value", state)

        assert result == "fixed_value"

    def test_resolve_constant_with_special_chars(self):
        """Константа с @ в середине не является @state:"""
        state = {"content": "hello"}

        result = MappingResolver.resolve_value("email@example.com", state)

        assert result == "email@example.com"

    def test_resolve_integer(self):
        """Число -> константа (не строка)"""
        state = {"content": "hello"}

        result = MappingResolver.resolve_value(42, state)

        assert result == 42

    def test_resolve_boolean(self):
        """Boolean -> константа"""
        state = {"content": "hello"}

        assert MappingResolver.resolve_value(True, state) is True
        assert MappingResolver.resolve_value(False, state) is False

    def test_resolve_none(self):
        """None -> константа"""
        state = {"content": "hello"}

        result = MappingResolver.resolve_value(None, state)

        assert result is None

    def test_resolve_list(self):
        """List -> константа"""
        state = {"content": "hello"}

        result = MappingResolver.resolve_value([1, 2, 3], state)

        assert result == [1, 2, 3]

    def test_resolve_dict(self):
        """Dict -> константа (не резолвится рекурсивно)"""
        state = {"content": "hello"}

        result = MappingResolver.resolve_value({"key": "value"}, state)

        assert result == {"key": "value"}

    def test_resolve_missing_path_returns_none(self):
        """@state:missing_field -> None"""
        state = {"content": "hello"}

        result = MappingResolver.resolve_value("@state:missing_field", state)

        assert result is None

    def test_resolve_missing_nested_path_returns_none(self):
        """@state:user.missing.path -> None"""
        state = {"user": {"name": "John"}}

        result = MappingResolver.resolve_value("@state:user.missing.path", state)

        assert result is None

    def test_resolve_partial_nested_path_returns_none(self):
        """@state:user.name.extra -> None (name - строка, не dict)"""
        state = {"user": {"name": "John"}}

        result = MappingResolver.resolve_value("@state:user.name.extra", state)

        assert result is None

    def test_resolve_empty_state(self):
        """Пустой state -> None для любого пути"""
        state = {}

        result = MappingResolver.resolve_value("@state:any.path", state)

        assert result is None

    def test_resolve_state_value_is_dict(self):
        """@state:user -> целый dict"""
        state = {"user": {"name": "John", "age": 30}}

        result = MappingResolver.resolve_value("@state:user", state)

        assert result == {"name": "John", "age": 30}

    def test_resolve_state_value_is_list(self):
        """@state:items -> list"""
        state = {"items": [1, 2, 3]}

        result = MappingResolver.resolve_value("@state:items", state)

        assert result == [1, 2, 3]

    def test_resolve_empty_string_source(self):
        """Пустая строка -> пустая строка (константа)"""
        state = {"content": "hello"}

        result = MappingResolver.resolve_value("", state)

        assert result == ""

    def test_resolve_state_prefix_only(self):
        """@state: без пути -> пустой путь -> None"""
        state = {"content": "hello"}

        result = MappingResolver.resolve_value("@state:", state)

        assert result is None


class TestResolveValueWithVar:
    """Тесты для resolve_value с @var: - переменные из state_dict["variables"]."""

    def test_resolve_simple_var(self):
        """@var:name -> state_dict["variables"]["name"]"""
        state = {
            "content": "hello",
            "variables": {"company_name": "ACME Corp"}
        }

        result = MappingResolver.resolve_value("@var:company_name", state)

        assert result == "ACME Corp"

    def test_resolve_nested_var(self):
        """@var:config.api_key -> state_dict["variables"]["config"]["api_key"]"""
        state = {
            "variables": {
                "config": {
                    "api_key": "secret123",
                    "base_url": "https://api.example.com"
                }
            }
        }

        assert MappingResolver.resolve_value("@var:config.api_key", state) == "secret123"
        assert MappingResolver.resolve_value("@var:config.base_url", state) == "https://api.example.com"

    def test_resolve_deeply_nested_var(self):
        """@var:a.b.c.d -> глубоко вложенная переменная"""
        state = {
            "variables": {
                "a": {
                    "b": {
                        "c": {
                            "d": "deep_var_value"
                        }
                    }
                }
            }
        }

        result = MappingResolver.resolve_value("@var:a.b.c.d", state)

        assert result == "deep_var_value"

    def test_resolve_missing_var_raises_error(self):
        """@var:missing -> VariableResolutionError"""
        state = {"variables": {"existing": "value"}}

        with pytest.raises(VariableResolutionError):
            MappingResolver.resolve_value("@var:missing", state)

    def test_resolve_var_without_variables_raises_error(self):
        """@var:name без variables -> VariableResolutionError"""
        state = {"content": "hello"}

        with pytest.raises(VariableResolutionError):
            MappingResolver.resolve_value("@var:any_var", state)

    def test_resolve_var_empty_variables_raises_error(self):
        """@var:name с пустым variables -> VariableResolutionError"""
        state = {"variables": {}}

        with pytest.raises(VariableResolutionError):
            MappingResolver.resolve_value("@var:any_var", state)

    def test_resolve_var_numeric_value(self):
        """@var:count -> числовое значение"""
        state = {"variables": {"count": 42, "price": 99.99}}

        assert MappingResolver.resolve_value("@var:count", state) == 42
        assert MappingResolver.resolve_value("@var:price", state) == 99.99

    def test_resolve_var_boolean_value(self):
        """@var:flag -> boolean"""
        state = {"variables": {"enabled": True, "debug": False}}

        assert MappingResolver.resolve_value("@var:enabled", state) is True
        assert MappingResolver.resolve_value("@var:debug", state) is False

    def test_resolve_var_dict_value(self):
        """@var:config -> dict"""
        state = {"variables": {"config": {"key": "value", "nested": {"a": 1}}}}

        result = MappingResolver.resolve_value("@var:config", state)

        assert result == {"key": "value", "nested": {"a": 1}}

    def test_resolve_var_list_value(self):
        """@var:items -> list"""
        state = {"variables": {"items": [1, 2, 3]}}

        result = MappingResolver.resolve_value("@var:items", state)

        assert result == [1, 2, 3]

    def test_resolve_var_prefix_only_raises_error(self):
        """@var: без имени -> VariableResolutionError"""
        state = {"variables": {"x": 1}}

        with pytest.raises(VariableResolutionError):
            MappingResolver.resolve_value("@var:", state)

    def test_mixed_state_and_var(self):
        """@state: и @var: работают независимо"""
        state = {
            "content": "from_state",
            "user": {"name": "John"},
            "variables": {
                "content": "from_var",
                "company": "ACME"
            }
        }

        # @state: берёт из state
        assert MappingResolver.resolve_value("@state:content", state) == "from_state"
        assert MappingResolver.resolve_value("@state:user.name", state) == "John"

        # @var: берёт из variables
        assert MappingResolver.resolve_value("@var:content", state) == "from_var"
        assert MappingResolver.resolve_value("@var:company", state) == "ACME"


class TestGetNestedValue:
    """Тесты для get_nested_value - получение значения по пути."""

    def test_simple_path(self):
        """Простой путь: field"""
        data = {"field": "value"}

        result = MappingResolver.get_nested_value(data, "field")

        assert result == "value"

    def test_two_level_path(self):
        """Двухуровневый путь: a.b"""
        data = {"a": {"b": "value"}}

        result = MappingResolver.get_nested_value(data, "a.b")

        assert result == "value"

    def test_multi_level_path(self):
        """Многоуровневый путь: a.b.c.d"""
        data = {"a": {"b": {"c": {"d": "deep"}}}}

        result = MappingResolver.get_nested_value(data, "a.b.c.d")

        assert result == "deep"

    def test_missing_key_returns_none(self):
        """Отсутствующий ключ -> None"""
        data = {"a": {"b": "value"}}

        result = MappingResolver.get_nested_value(data, "a.c")

        assert result is None

    def test_path_through_non_dict_returns_none(self):
        """Путь через не-dict -> None"""
        data = {"a": "string_value"}

        result = MappingResolver.get_nested_value(data, "a.b")

        assert result is None

    def test_empty_path_returns_none(self):
        """Пустой путь -> None"""
        data = {"a": "value"}

        result = MappingResolver.get_nested_value(data, "")

        assert result is None

    def test_empty_data(self):
        """Пустые данные -> None"""
        result = MappingResolver.get_nested_value({}, "any.path")

        assert result is None

    def test_numeric_value(self):
        """Числовое значение"""
        data = {"count": 42, "nested": {"value": 3.14}}

        assert MappingResolver.get_nested_value(data, "count") == 42
        assert MappingResolver.get_nested_value(data, "nested.value") == 3.14

    def test_boolean_value(self):
        """Boolean значение"""
        data = {"flag": True, "nested": {"active": False}}

        assert MappingResolver.get_nested_value(data, "flag") is True
        assert MappingResolver.get_nested_value(data, "nested.active") is False

    def test_none_value(self):
        """None как значение (не отсутствие ключа)"""
        data = {"value": None}

        result = MappingResolver.get_nested_value(data, "value")

        assert result is None

    def test_list_value(self):
        """List как значение"""
        data = {"items": [1, 2, 3]}

        result = MappingResolver.get_nested_value(data, "items")

        assert result == [1, 2, 3]

    def test_dict_value(self):
        """Dict как значение"""
        data = {"config": {"key": "value"}}

        result = MappingResolver.get_nested_value(data, "config")

        assert result == {"key": "value"}


class TestBuildMappedState:
    """Тесты для build_mapped_state - построение нового dict state на основе маппинга."""

    def test_simple_mapping(self):
        """Простой маппинг без вложенности"""
        mapping = {
            "content": "@state:user_query",
            "name": "@state:user_name"
        }
        state = {
            "user_query": "Hello!",
            "user_name": "John"
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["content"] == "Hello!"
        assert result["name"] == "John"

    def test_nested_path_mapping(self):
        """Маппинг с вложенными путями"""
        mapping = {
            "name": "@state:user.profile.name",
            "city": "@state:user.address.city"
        }
        state = {
            "user": {
                "profile": {"name": "John"},
                "address": {"city": "Moscow"}
            }
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["name"] == "John"
        assert result["city"] == "Moscow"

    def test_constant_values(self):
        """Маппинг с константами"""
        mapping = {
            "content": "@state:query",
            "fixed_field": "constant_value",
            "number": 42
        }
        state = {"query": "Hello!"}

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["content"] == "Hello!"
        assert result["fixed_field"] == "constant_value"
        assert result["number"] == 42

    def test_empty_mapping(self):
        """Пустой маппинг -> пустой результат."""
        mapping = {}
        state = {
            "query": "Hello!",
            "variables": {"x": 1}
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result == {}

    def test_missing_source_returns_none(self):
        """Отсутствующий источник -> None в результате"""
        mapping = {
            "content": "@state:missing_field",
            "name": "@state:user.missing"
        }
        state = {"user": {"name": "John"}}

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["content"] is None
        assert result["name"] is None

    def test_mixed_mapping(self):
        """Смешанный маппинг: @state, константы, разные типы"""
        mapping = {
            "content": "@state:user_query",
            "user_name": "@state:user.profile.name",
            "default_lang": "ru",
            "max_items": 10,
            "debug": False
        }
        state = {
            "user_query": "Привет!",
            "user": {"profile": {"name": "Иван"}},
            "variables": {"api_key": "secret"}
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["content"] == "Привет!"
        assert result["user_name"] == "Иван"
        assert result["default_lang"] == "ru"
        assert result["max_items"] == 10
        assert result["debug"] is False

    def test_overwrites_service_field_if_mapped(self):
        """Если служебное поле в маппинге - перезаписывается"""
        mapping = {
            "variables": {"new_var": "new_value"}
        }
        state = {
            "variables": {"old_var": "old_value"}
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["variables"] == {"new_var": "new_value"}

    def test_complex_nested_state(self):
        """Сложная вложенная структура state"""
        mapping = {
            "order_id": "@state:order.id",
            "customer_name": "@state:order.customer.personal.name",
            "delivery_city": "@state:order.delivery.address.city",
            "items_count": "@state:order.items_count"
        }
        state = {
            "order": {
                "id": "ORD-123",
                "customer": {
                    "personal": {"name": "Иван Петров", "phone": "+7999"}
                },
                "delivery": {
                    "address": {"city": "Москва", "street": "Ленина"}
                },
                "items_count": 5
            },
            "variables": {}
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["order_id"] == "ORD-123"
        assert result["customer_name"] == "Иван Петров"
        assert result["delivery_city"] == "Москва"
        assert result["items_count"] == 5


class TestBuildMappedStateWithVar:
    """Тесты для build_mapped_state с @var: - использование переменных из state_dict["variables"]."""

    def test_mapping_with_var(self):
        """Маппинг с @var:"""
        mapping = {
            "company": "@var:company_name",
            "api_key": "@var:api_key"
        }
        state = {
            "variables": {
                "company_name": "ACME Corp",
                "api_key": "secret123"
            }
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["company"] == "ACME Corp"
        assert result["api_key"] == "secret123"

    def test_mapping_with_nested_var(self):
        """Маппинг с вложенными @var:"""
        mapping = {
            "url": "@var:config.api.base_url",
            "timeout": "@var:config.api.timeout"
        }
        state = {
            "variables": {
                "config": {
                    "api": {
                        "base_url": "https://api.example.com",
                        "timeout": 30
                    }
                }
            }
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["url"] == "https://api.example.com"
        assert result["timeout"] == 30

    def test_mixed_state_var_and_constants(self):
        """Смешанный маппинг: @state:, @var:, константы"""
        mapping = {
            "content": "@state:user_query",
            "user_name": "@state:user.name",
            "company": "@var:company_name",
            "api_key": "@var:config.api_key",
            "default_lang": "ru",
            "max_retries": 3
        }
        state = {
            "user_query": "Привет!",
            "user": {"name": "Иван"},
            "variables": {
                "company_name": "ACME",
                "config": {"api_key": "secret"}
            }
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["content"] == "Привет!"
        assert result["user_name"] == "Иван"
        assert result["company"] == "ACME"
        assert result["api_key"] == "secret"
        assert result["default_lang"] == "ru"
        assert result["max_retries"] == 3

    def test_missing_var_raises_error(self):
        """Отсутствующая переменная -> VariableResolutionError"""
        mapping = {
            "existing": "@var:existing",
            "missing": "@var:missing"
        }
        state = {"variables": {"existing": "value"}}

        with pytest.raises(VariableResolutionError):
            MappingResolver.build_mapped_state(mapping, state)

    def test_headers_with_var(self):
        """Реальный сценарий: HTTP headers с @var:"""
        mapping = {
            "Authorization": "@var:api_token",
            "X-API-Key": "@var:config.keys.primary"
        }
        state = {
            "variables": {
                "api_token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                "config": {
                    "keys": {
                        "primary": "pk_live_123456",
                        "secondary": "pk_test_789"
                    }
                }
            }
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["Authorization"] == "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        assert result["X-API-Key"] == "pk_live_123456"

    def test_parameter_source_with_var(self):
        """Реальный сценарий: параметры API с @var:"""
        mapping = {
            "city": "@state:user.address.city",
            "api_key": "@var:weather_api_key",
            "units": "@var:settings.units"
        }
        state = {
            "user": {
                "address": {"city": "Moscow", "country": "RU"}
            },
            "variables": {
                "weather_api_key": "abc123",
                "settings": {"units": "metric"}
            }
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["city"] == "Moscow"
        assert result["api_key"] == "abc123"
        assert result["units"] == "metric"

    def test_url_construction_with_var(self):
        """Реальный сценарий: построение URL с переменными"""
        mapping = {
            "base_url": "@var:api.base_url",
            "endpoint": "@state:request.endpoint",
            "version": "@var:api.version"
        }
        state = {
            "request": {"endpoint": "/users/123"},
            "variables": {
                "api": {
                    "base_url": "https://api.example.com",
                    "version": "v2"
                }
            }
        }

        result = MappingResolver.build_mapped_state(mapping, state)

        assert result["base_url"] == "https://api.example.com"
        assert result["endpoint"] == "/users/123"
        assert result["version"] == "v2"


class TestResolveVarsInString:
    """Тесты для resolve_vars_in_string - замена @var: внутри строки."""

    def test_simple_var_replacement(self):
        """Простая замена @var:name"""
        variables = {"token": "abc123"}

        result = MappingResolver.resolve_vars_in_string("Bearer @var:token", variables)

        assert result == "Bearer abc123"

    def test_nested_var_replacement(self):
        """Замена @var: с вложенным путём"""
        variables = {
            "config": {
                "api_key": "secret123",
                "base_url": "https://api.example.com"
            }
        }

        result = MappingResolver.resolve_vars_in_string(
            "Key: @var:config.api_key", variables
        )

        assert result == "Key: secret123"

    def test_deeply_nested_var(self):
        """Глубоко вложенный путь"""
        variables = {
            "a": {
                "b": {
                    "c": {
                        "d": "deep_value"
                    }
                }
            }
        }

        result = MappingResolver.resolve_vars_in_string(
            "Value: @var:a.b.c.d", variables
        )

        assert result == "Value: deep_value"

    def test_multiple_vars_in_string(self):
        """Несколько @var: в одной строке"""
        variables = {
            "host": "api.example.com",
            "version": "v2"
        }

        result = MappingResolver.resolve_vars_in_string(
            "https://@var:host/@var:version/users", variables
        )

        assert result == "https://api.example.com/v2/users"

    def test_multiple_nested_vars(self):
        """Несколько вложенных @var: в одной строке"""
        variables = {
            "auth": {
                "type": "Bearer",
                "token": "xyz789"
            }
        }

        result = MappingResolver.resolve_vars_in_string(
            "@var:auth.type @var:auth.token", variables
        )

        assert result == "Bearer xyz789"

    def test_no_vars_returns_unchanged(self):
        """Строка без @var: возвращается без изменений"""
        variables = {"key": "value"}

        result = MappingResolver.resolve_vars_in_string(
            "Just a regular string", variables
        )

        assert result == "Just a regular string"

    def test_missing_var_raises_error(self):
        """Отсутствующая переменная вызывает VariableResolutionError"""
        variables = {"existing": "value"}

        with pytest.raises(VariableResolutionError):
            MappingResolver.resolve_vars_in_string(
                "Found: @var:existing, Missing: @var:missing", variables
            )

    def test_missing_nested_var_raises_error(self):
        """Отсутствующий вложенный путь вызывает VariableResolutionError"""
        variables = {"config": {"key": "value"}}

        with pytest.raises(VariableResolutionError):
            MappingResolver.resolve_vars_in_string(
                "@var:config.key @var:config.missing", variables
            )

    def test_empty_string(self):
        """Пустая строка"""
        variables = {"key": "value"}

        result = MappingResolver.resolve_vars_in_string("", variables)

        assert result == ""

    def test_none_value(self):
        """None как входное значение"""
        variables = {"key": "value"}

        result = MappingResolver.resolve_vars_in_string(None, variables)

        assert result is None

    def test_non_string_value(self):
        """Не-строка возвращается без изменений"""
        variables = {"key": "value"}

        assert MappingResolver.resolve_vars_in_string(42, variables) == 42
        assert MappingResolver.resolve_vars_in_string(True, variables) is True
        assert MappingResolver.resolve_vars_in_string([1, 2], variables) == [1, 2]

    def test_empty_variables_raises_error(self):
        """Пустой словарь переменных приводит к ошибке."""
        with pytest.raises(VariableResolutionError):
            MappingResolver.resolve_vars_in_string("@var:key", {})

    def test_var_only_string(self):
        """Строка состоящая только из @var:"""
        variables = {"token": "secret"}

        result = MappingResolver.resolve_vars_in_string("@var:token", variables)

        assert result == "secret"

    def test_numeric_var_value_converted_to_string(self):
        """Числовое значение конвертируется в строку"""
        variables = {"count": 42, "price": 99.99}

        result = MappingResolver.resolve_vars_in_string(
            "Count: @var:count, Price: @var:price", variables
        )

        assert result == "Count: 42, Price: 99.99"

    def test_boolean_var_value_converted_to_string(self):
        """Boolean конвертируется в строку"""
        variables = {"enabled": True, "debug": False}

        result = MappingResolver.resolve_vars_in_string(
            "Enabled: @var:enabled, Debug: @var:debug", variables
        )

        assert result == "Enabled: True, Debug: False"

    def test_auth_header_bearer_token(self):
        """Реальный сценарий: Bearer token в auth header"""
        variables = {
            "auth": {
                "bearer_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxx"
            }
        }

        result = MappingResolver.resolve_vars_in_string(
            "Bearer @var:auth.bearer_token", variables
        )

        assert result == "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxx"

    def test_api_key_header(self):
        """Реальный сценарий: API key в header"""
        variables = {
            "api": {
                "keys": {
                    "production": "pk_live_ABC123"
                }
            }
        }

        result = MappingResolver.resolve_vars_in_string(
            "@var:api.keys.production", variables
        )

        assert result == "pk_live_ABC123"

    def test_url_with_vars(self):
        """Реальный сценарий: URL с переменными"""
        variables = {
            "api": {
                "host": "api.weather.com",
                "version": "v3"
            }
        }

        result = MappingResolver.resolve_vars_in_string(
            "https://@var:api.host/@var:api.version/forecast", variables
        )

        assert result == "https://api.weather.com/v3/forecast"

    def test_special_chars_in_var_name(self):
        """Переменные с подчёркиванием и цифрами"""
        variables = {
            "api_key_v2": "secret",
            "config_123": {"value": "test"}
        }

        result = MappingResolver.resolve_vars_in_string(
            "@var:api_key_v2 @var:config_123.value", variables
        )

        assert result == "secret test"

    def test_var_at_start_middle_end(self):
        """@var: в начале, середине и конце строки"""
        variables = {
            "start": "START",
            "middle": "MIDDLE",
            "end": "END"
        }

        result = MappingResolver.resolve_vars_in_string(
            "@var:start text @var:middle text @var:end", variables
        )

        assert result == "START text MIDDLE text END"

