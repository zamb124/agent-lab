"""
Строгие тесты для deep_merge.

Проверяем все сценарии переопределений на уровне данных.
"""

from apps.flows.src.utils.merge import deep_merge


class TestDeepMergeBasics:
    """Базовые сценарии deep_merge."""

    def test_empty_base_returns_override(self):
        """Пустой base - возвращается override."""
        base = {}
        override = {"key": "value"}
        result = deep_merge(base, override)
        assert result == {"key": "value"}
        assert result is not override

    def test_empty_override_returns_base_copy(self):
        """Пустой override - возвращается копия base."""
        base = {"key": "value"}
        override = {}
        result = deep_merge(base, override)
        assert result == {"key": "value"}
        assert result is not base

    def test_scalar_override(self):
        """Скалярные значения перезаписываются."""
        base = {"key": "old"}
        override = {"key": "new"}
        result = deep_merge(base, override)
        assert result["key"] == "new"

    def test_none_in_override_does_not_overwrite(self):
        """None в override НЕ перезаписывает base."""
        base = {"key": "value"}
        override = {"key": None}
        result = deep_merge(base, override)
        assert result["key"] == "value"

    def test_list_replaced_entirely(self):
        """Списки заменяются целиком, не мержатся."""
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = deep_merge(base, override)
        assert result["items"] == [4, 5]

    def test_new_keys_added(self):
        """Новые ключи из override добавляются."""
        base = {"existing": "value"}
        override = {"new_key": "new_value"}
        result = deep_merge(base, override)
        assert result["existing"] == "value"
        assert result["new_key"] == "new_value"


class TestDeepMergeNested:
    """Вложенные структуры."""

    def test_nested_dict_merge(self):
        """Вложенные dict мержатся рекурсивно."""
        base = {"llm": {"model": "gpt-4o", "temperature": 0.7}}
        override = {"llm": {"temperature": 0.1}}
        result = deep_merge(base, override)
        assert result["llm"]["model"] == "gpt-4o"
        assert result["llm"]["temperature"] == 0.1

    def test_deeply_nested_merge(self):
        """Глубокая вложенность."""
        base = {"level1": {"level2": {"level3": {"a": 1, "b": 2}}}}
        override = {"level1": {"level2": {"level3": {"b": 99, "c": 3}}}}
        result = deep_merge(base, override)
        assert result["level1"]["level2"]["level3"]["a"] == 1
        assert result["level1"]["level2"]["level3"]["b"] == 99
        assert result["level1"]["level2"]["level3"]["c"] == 3

    def test_mixed_nesting(self):
        """Смешанная вложенность с разными типами."""
        base = {"config": {"settings": {"debug": False, "timeout": 30}, "items": [1, 2, 3]}}
        override = {"config": {"settings": {"debug": True}, "items": [4, 5, 6]}}
        result = deep_merge(base, override)
        assert result["config"]["settings"]["debug"] is True
        assert result["config"]["settings"]["timeout"] == 30
        assert result["config"]["items"] == [4, 5, 6]


class TestDeepMergeExclude:
    """Исключённые ключи."""

    def test_node_id_excluded_by_default(self):
        """node_id исключен по умолчанию."""
        base = {"prompt": "base prompt"}
        override = {"node_id": "some_id", "prompt": "new prompt"}
        result = deep_merge(base, override)
        assert "node_id" not in result
        assert result["prompt"] == "new prompt"

    def test_tool_id_excluded_by_default(self):
        """tool_id исключен по умолчанию."""
        base = {"description": "base"}
        override = {"tool_id": "some_tool", "description": "new"}
        result = deep_merge(base, override)
        assert "tool_id" not in result

    def test_agent_id_excluded_by_default(self):
        """flow_id исключен по умолчанию."""
        base = {"name": "base"}
        override = {"flow_id": "some_agent", "name": "new"}
        result = deep_merge(base, override)
        assert "flow_id" not in result

    def test_custom_exclude_set(self):
        """Кастомный набор исключений."""
        base = {"a": 1, "b": 2}
        override = {"a": 10, "b": 20, "c": 30}
        result = deep_merge(base, override, exclude={"a", "b"})
        assert result["a"] == 1
        assert result["b"] == 2
        assert result["c"] == 30


class TestDeepMergeNodeConfig:
    """Тесты на реальных примерах NodeConfig."""

    def test_llm_node_prompt_override(self):
        """Переопределение prompt в llm_node."""
        base = {
            "type": "llm_node",
            "prompt": "Ты агент компании {company_name}",
            "tools": ["calculator", "ask_user"],
            "llm": {"model": "gpt-4o", "temperature": 0.7},
        }
        override = {
            "node_id": "example_main_agent",
            "prompt": "Новый промпт",
            "llm": {"temperature": 0.1},
        }
        result = deep_merge(base, override)
        assert result["type"] == "llm_node"
        assert result["prompt"] == "Новый промпт"
        assert result["tools"] == ["calculator", "ask_user"]
        assert result["llm"]["model"] == "gpt-4o"
        assert result["llm"]["temperature"] == 0.1
        assert "node_id" not in result

    def test_llm_node_tools_override(self):
        """Переопределение tools полностью заменяет список."""
        base = {"tools": ["calculator", "ask_user", "finish"]}
        override = {"tools": ["only_one_tool"]}
        result = deep_merge(base, override)
        assert result["tools"] == ["only_one_tool"]

    def test_function_node_code_override(self):
        """Переопределение code в function node."""
        base = {"type": "code", "code": "def run(s): return s"}
        override = {"code": "def run(s): s['modified'] = True; return s"}
        result = deep_merge(base, override)
        assert "modified" in result["code"]

    def test_input_mapping_override(self):
        """Переопределение input_mapping."""
        base = {"input_mapping": {"content": "@state:user_query", "user_name": "@state:user.name"}}
        override = {"input_mapping": {"user_name": "@state:custom.name", "new_field": "@state:new"}}
        result = deep_merge(base, override)
        assert result["input_mapping"]["content"] == "@state:user_query"
        assert result["input_mapping"]["user_name"] == "@state:custom.name"
        assert result["input_mapping"]["new_field"] == "@state:new"


class TestDeepMergeToolReference:
    """Тесты на реальных примерах ToolReference."""

    def test_inline_tool_code_override(self):
        """Переопределение inline кода tool."""
        base = {
            "tool_id": "format_greeting",
            "description": "Форматирует приветствие",
            "code": "async def run(args, state): return 'Hello'",
            "parameters_schema": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Имя"}},
                "required": ["name"],
            },
        }
        override = {
            "tool_id": "format_greeting",
            "code": "async def run(args, state): return f'Hi {args[\"name\"]}'",
            "parameters_schema": {
                "type": "object",
                "properties": {"style": {"type": "string", "description": "Стиль"}},
                "required": ["style"],
            },
        }
        result = deep_merge(base, override)
        assert "Hi" in result["code"]
        assert result["description"] == "Форматирует приветствие"
        assert "name" in result["parameters_schema"]["properties"]
        assert "style" in result["parameters_schema"]["properties"]

    def test_tool_mock_map_override(self):
        """Переопределение mock_map."""
        base = {"mock_map": {"default": 42}}
        override = {"mock_map": {"default": 100, "error_case": "error"}}
        result = deep_merge(base, override)
        assert result["mock_map"]["default"] == 100
        assert result["mock_map"]["error_case"] == "error"


class TestDeepMergeBranchConfig:
    """Тесты на реальных примерах BranchConfig."""

    def test_skill_variables_merge(self):
        """Merge переменных skill."""
        base_variables = {"company_name": "BaseCompany", "max_length": 500}
        skill_variables = {"max_length": 200, "skill_specific": "value"}
        result = deep_merge(base_variables, skill_variables)
        assert result["company_name"] == "BaseCompany"
        assert result["max_length"] == 200
        assert result["skill_specific"] == "value"

    def test_skill_nodes_merge(self):
        """Merge nodes в skill."""
        base_nodes = {
            "main": {"type": "llm_node", "prompt": "Base", "tools": ["t1"]},
            "helper": {"type": "code", "code": "def run(s): return s"},
        }
        skill_nodes = {"main": {"prompt": "Skill prompt", "llm": {"temperature": 0.1}}}
        result = deep_merge(base_nodes, skill_nodes)
        assert result["main"]["type"] == "llm_node"
        assert result["main"]["prompt"] == "Skill prompt"
        assert result["main"]["tools"] == ["t1"]
        assert result["main"]["llm"]["temperature"] == 0.1
        assert "helper" in result

    def test_skill_mock_override(self):
        """Переопределение mock в skill."""
        base_mock = {"enabled": False, "tools": {"calculator": 42}}
        skill_mock = {
            "enabled": True,
            "tools": {"calculator": 100, "ask_user": "response"},
            "llm": [{"type": "text", "content": "Mock"}],
        }
        result = deep_merge(base_mock, skill_mock)
        assert result["enabled"] is True
        assert result["tools"]["calculator"] == 100
        assert result["tools"]["ask_user"] == "response"
        assert result["llm"] == [{"type": "text", "content": "Mock"}]


class TestDeepMergeImmutability:
    """Тесты на иммутабельность."""

    def test_base_not_modified(self):
        """Base не модифицируется."""
        base = {"nested": {"key": "value"}}
        override = {"nested": {"key": "new"}}
        original_base = {"nested": {"key": "value"}}
        deep_merge(base, override)
        assert base == original_base

    def test_override_not_modified(self):
        """Override не модифицируется."""
        base = {"key": "value"}
        override = {"nested": {"deep": "value"}}
        original_override = {"nested": {"deep": "value"}}
        deep_merge(base, override)
        assert override == original_override

    def test_result_is_new_dict(self):
        """Результат - новый dict."""
        base = {"key": "value"}
        override = {"key2": "value2"}
        result = deep_merge(base, override)
        assert result is not base
        assert result is not override


class TestDeepMergeEdgeCases:
    """Граничные случаи."""

    def test_both_empty(self):
        """Оба пустые."""
        result = deep_merge({}, {})
        assert result == {}

    def test_override_with_empty_string(self):
        """Пустая строка в override - перезаписывает."""
        base = {"key": "value"}
        override = {"key": ""}
        result = deep_merge(base, override)
        assert result["key"] == ""

    def test_override_with_zero(self):
        """Ноль в override - перезаписывает."""
        base = {"count": 10}
        override = {"count": 0}
        result = deep_merge(base, override)
        assert result["count"] == 0

    def test_override_with_false(self):
        """False в override - перезаписывает."""
        base = {"enabled": True}
        override = {"enabled": False}
        result = deep_merge(base, override)
        assert result["enabled"] is False

    def test_type_change_scalar_to_dict(self):
        """Смена типа: scalar → dict."""
        base = {"config": "simple"}
        override = {"config": {"nested": True}}
        result = deep_merge(base, override)
        assert result["config"] == {"nested": True}

    def test_type_change_dict_to_scalar(self):
        """Смена типа: dict → scalar."""
        base = {"config": {"nested": True}}
        override = {"config": "simple"}
        result = deep_merge(base, override)
        assert result["config"] == "simple"

    def test_type_change_list_to_dict(self):
        """Смена типа: list → dict."""
        base = {"data": [1, 2, 3]}
        override = {"data": {"a": 1}}
        result = deep_merge(base, override)
        assert result["data"] == {"a": 1}
