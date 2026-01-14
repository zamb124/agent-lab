"""
Тесты для циклов {for...}...{endfor} в VariableResolver.
"""

import pytest
from core.variables.resolver import VariableResolver


class TestForLoops:
    """Тесты для синтаксиса {for item in list}...{endfor}"""
    
    def test_simple_for_loop(self):
        """Простой цикл по списку"""
        template = "{for item in items}{item}\n{endfor}"
        result = VariableResolver.render_template(
            template,
            local_vars={"items": ["a", "b", "c"]},
            include_system=False
        )
        assert result == "a\nb\nc\n"
    
    def test_for_loop_with_dict_access(self):
        """Цикл с доступом к полям объектов"""
        template = "{for user in users}- {user.name}: {user.role}\n{endfor}"
        result = VariableResolver.render_template(
            template,
            local_vars={
                "users": [
                    {"name": "Иван", "role": "admin"},
                    {"name": "Петр", "role": "user"}
                ]
            },
            include_system=False
        )
        assert result == "- Иван: admin\n- Петр: user\n"
    
    def test_for_loop_empty_list(self):
        """Цикл по пустому списку"""
        template = "{for item in items}X{endfor}"
        result = VariableResolver.render_template(
            template,
            local_vars={"items": []},
            include_system=False
        )
        assert result == ""
    
    def test_for_loop_with_text_before_after(self):
        """Цикл с текстом до и после"""
        template = "Start:\n{for item in items}- {item}\n{endfor}End"
        result = VariableResolver.render_template(
            template,
            local_vars={"items": ["A", "B"]},
            include_system=False
        )
        assert result == "Start:\n- A\n- B\nEnd"
    
    def test_nested_field_access(self):
        """Доступ к вложенным полям"""
        template = "{for entity in entities}Type: {entity.type}, Prompt: {entity.prompt}\n{endfor}"
        result = VariableResolver.render_template(
            template,
            local_vars={
                "entities": [
                    {"type": "contact", "prompt": "Extract contacts"},
                    {"type": "task", "prompt": "Extract tasks"}
                ]
            },
            include_system=False
        )
        assert "Type: contact, Prompt: Extract contacts" in result
        assert "Type: task, Prompt: Extract tasks" in result
    
    def test_for_loop_nonexistent_variable(self):
        """Цикл по несуществующей переменной"""
        template = "{for item in missing}X{endfor}"
        result = VariableResolver.render_template(
            template,
            local_vars={},
            include_system=False,
            safe=True
        )
        assert result == ""
    
    def test_for_loop_not_a_list(self):
        """Цикл по не-списку"""
        template = "{for item in value}X{endfor}"
        result = VariableResolver.render_template(
            template,
            local_vars={"value": "string"},
            include_system=False,
            safe=True
        )
        assert result == ""
    
    def test_crm_entity_types_loop(self):
        """Реальный пример для CRM - цикл по entity_types"""
        template = """## ТИПЫ ENTITIES

{for entity_type in entity_types}
- **{entity_type.type}**: {entity_type.prompt}
{endfor}

## ТИПЫ RELATIONSHIPS

{for rel_type in relationship_types}
- **{rel_type.type}**: {rel_type.prompt}
{endfor}"""
        
        result = VariableResolver.render_template(
            template,
            local_vars={
                "entity_types": [
                    {"type": "contact", "prompt": "Извлекай контакты"},
                    {"type": "organization", "prompt": "Извлекай организации"}
                ],
                "relationship_types": [
                    {"type": "works_for", "prompt": "Связь работает в"},
                    {"type": "knows", "prompt": "Связь знаком с"}
                ]
            },
            include_system=False
        )
        
        assert "- **contact**: Извлекай контакты" in result
        assert "- **organization**: Извлекай организации" in result
        assert "- **works_for**: Связь работает в" in result
        assert "- **knows**: Связь знаком с" in result
    
    def test_for_loop_with_regular_variables(self):
        """Цикл в сочетании с обычными переменными"""
        template = "User: {user}\nItems:\n{for item in items}- {item}\n{endfor}Total: {total}"
        result = VariableResolver.render_template(
            template,
            local_vars={
                "user": "John",
                "items": ["A", "B"],
                "total": 2
            },
            include_system=False
        )
        assert "User: John" in result
        assert "- A" in result
        assert "- B" in result
        assert "Total: 2" in result
    
    def test_for_loop_multiline_body(self):
        """Цикл с многострочным телом"""
        template = """{for user in users}
Name: {user.name}
Role: {user.role}
---
{endfor}"""
        result = VariableResolver.render_template(
            template,
            local_vars={
                "users": [
                    {"name": "Alice", "role": "admin"},
                    {"name": "Bob", "role": "user"}
                ]
            },
            include_system=False
        )
        assert "Name: Alice" in result
        assert "Role: admin" in result
        assert "Name: Bob" in result
        assert "Role: user" in result


class TestForLoopsEdgeCases:
    """Граничные случаи для циклов"""
    
    def test_for_loop_with_special_characters(self):
        """Цикл с спецсимволами в данных"""
        template = "{for item in items}{item}\n{endfor}"
        result = VariableResolver.render_template(
            template,
            local_vars={"items": ["test@email.com", "path/to/file", "10%"]},
            include_system=False
        )
        assert "test@email.com" in result
        assert "path/to/file" in result
        assert "10%" in result
    
    def test_for_loop_with_numbers(self):
        """Цикл со числовыми значениями"""
        template = "{for num in numbers}{num}, {endfor}"
        result = VariableResolver.render_template(
            template,
            local_vars={"numbers": [1, 2, 3]},
            include_system=False
        )
        assert "1, 2, 3," in result
    
    def test_for_loop_with_none_values(self):
        """Цикл с None значениями в полях"""
        template = "{for item in items}{item.name}\n{endfor}"
        result = VariableResolver.render_template(
            template,
            local_vars={
                "items": [
                    {"name": "Test"},
                    {"name": None}
                ]
            },
            include_system=False,
            safe=True
        )
        assert "Test" in result

