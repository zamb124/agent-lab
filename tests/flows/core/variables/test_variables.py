"""
Тесты для VariablesService и VariableResolver.
"""

import pytest
from typing import Any, Dict

from apps.flows.src.container import get_container
from core.db.repositories import Variable
from core.variables import VariablesService, VariableResolver, VariableResolutionError


class TestVariableResolver:
    """Тесты VariableResolver (рендеринг шаблонов)."""

    def test_render_simple_template(self):
        """Простая подстановка переменных."""
        template = "Hello, {name}!"
        variables = {"name": "World"}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Hello, World!"

    def test_render_multiple_variables(self):
        """Несколько переменных."""
        template = "{greeting}, {name}! Welcome to {place}."
        variables = {
            "greeting": "Hi",
            "name": "User",
            "place": "platform"
        }

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Hi, User! Welcome to platform."

    def test_render_optional_missing(self):
        """Опциональная переменная без значения."""
        template = "Name: {?name}"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Name: "

    def test_render_optional_with_default(self):
        """Опциональная переменная со значением по умолчанию."""
        template = "Status: {?status|active}"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Status: active"

    def test_render_optional_with_value(self):
        """Опциональная переменная с заданным значением."""
        template = "Status: {?status|default}"
        variables = {"status": "pending"}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Status: pending"

    def test_render_safe_mode(self):
        """Safe режим сохраняет неизвестные переменные."""
        template = "Hello, {unknown}!"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables, safe=True)

        assert result == "Hello, {unknown}!"

    def test_render_complex_prompt(self):
        """Сложный промпт с разными типами переменных."""
        template = """Ты консультант {company_name}.

Контакты:
- Телефон: {support_phone}
- Email: {?support_email|support@example.com}

Клиент: {?client_name}"""

        variables = {
            "company_name": "TestCorp",
            "support_phone": "+7-999-123-45-67",
        }

        result = VariableResolver.render_template(template, local_vars=variables)

        assert "TestCorp" in result
        assert "+7-999-123-45-67" in result
        assert "support@example.com" in result  # default
        assert "{?client_name}" not in result  # removed

    def test_render_required_with_default(self):
        """Обязательная переменная с default когда переменной нет."""
        template = "Город: {city|Город не указан}"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Город: Город не указан"

    def test_render_required_with_default_none(self):
        """Обязательная переменная с default когда переменная None."""
        template = "Город: {city|Город не указан}"
        variables = {"city": None}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Город: Город не указан"

    def test_render_required_with_default_empty(self):
        """Обязательная переменная с default когда переменная пустая строка."""
        template = "Город: {city|Город не указан}"
        variables = {"city": ""}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Город: Город не указан"

    def test_render_required_with_default_with_value(self):
        """Обязательная переменная с default когда переменная есть."""
        template = "Город: {city|Город не указан}"
        variables = {"city": "Москва"}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Город: Москва"

    def test_render_required_with_default_text(self):
        """Обязательная переменная с default на русском языке."""
        template = "Город: {city|Город не указан}"
        variables = {"city": None}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Город: Город не указан"

    def test_render_optional_nested_with_default(self):
        """Опциональная вложенная переменная с default."""
        template = "Имя города: {?city.name|Имя города не указано}"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Имя города: Имя города не указано"

    def test_render_conditional_block_with_value(self):
        """Условный блок когда переменная есть."""
        template = """Начало
{?has_instructions|
Специальные инструкции:
- Инструкция 1
- Инструкция 2
}
Конец"""
        variables = {"has_instructions": True}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Специальные инструкции" in result
        assert "Инструкция 1" in result
        assert "Инструкция 2" in result

    def test_render_conditional_block_without_value(self):
        """Условный блок когда переменной нет."""
        template = """Начало
{?has_instructions|
Специальные инструкции:
- Инструкция 1
- Инструкция 2
}
Конец"""
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        # По логике: has_instructions не найдена, default содержит \n (условный блок)
        # Условный блок НЕ показывается если переменная не найдена (пустая строка)
        assert "Специальные инструкции" not in result  # Условный блок не показывается
        assert "Инструкция 1" not in result
        assert "Инструкция 2" not in result
        assert "Начало" in result
        assert "Конец" in result

    def test_render_conditional_block_multiline(self):
        """Многострочный условный блок."""
        template = """Текст до блока
{?show_details|
Детали:
Строка 1
Строка 2
Строка 3
}
Текст после блока"""
        variables = {"show_details": True}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Детали:" in result
        assert "Строка 1" in result
        assert "Строка 2" in result
        assert "Строка 3" in result

        variables_empty = {}
        result_empty = VariableResolver.render_template(template, local_vars=variables_empty)

        assert "Детали:" not in result_empty
        assert "Строка 1" not in result_empty

    def test_render_conditional_block_nested_vars(self):
        """Условный блок с переменными внутри."""
        template = """Начало
{?has_user|
Пользователь: {user_name}
Email: {?user_email|не указан}
}
Конец"""
        variables = {"has_user": True, "user_name": "Иван", "user_email": "ivan@example.com"}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Пользователь: Иван" in result
        assert "Email: ivan@example.com" in result

        variables_no_email = {"has_user": True, "user_name": "Иван", "user_email": None}
        result_no_email = VariableResolver.render_template(template, local_vars=variables_no_email)

        assert "Пользователь: Иван" in result_no_email
        assert "Email: не указан" in result_no_email

    def test_render_short_optional_missing(self):
        """Короткий формат опциональной без значения."""
        template = "Компания: ?company_name"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Компания: "

    def test_render_short_optional_with_default(self):
        """Короткий формат опциональной с default."""
        template = "Компания: ?company_name|Не указано"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Компания: Не указано"

    def test_render_short_optional_with_value(self):
        """Короткий формат опциональной со значением."""
        template = "Компания: ?company_name|Не указано"
        variables = {"company_name": "TestCorp"}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Компания: TestCorp"

    def test_render_short_nested_dict(self):
        """Короткий формат с вложенным доступом."""
        template = "Пользователь: ?user.name|Гость"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Пользователь: Гость"

        variables_with_user = {"user": {"name": "Иван"}}
        result_with_user = VariableResolver.render_template(template, local_vars=variables_with_user)

        assert result_with_user == "Пользователь: Иван"

    def test_render_mixed_syntax(self):
        """Смешанное использование всех форматов."""
        template = """Город: {city|Город не указан}
Компания: ?company_name|Не указано
Дата: {current_date}
Пользователь: ?user.name|Гость
Email: {?support_email|support@example.com}
Статус: {status|active}

{?has_instructions|
Специальные инструкции:
- Инструкция 1
- Инструкция 2
}"""
        variables = {
            "city": "Москва",
            "company_name": "TestCorp",
            "user": {"name": "Иван"},
            "support_email": "support@test.com",
            "status": "pending",
            "has_instructions": True,
        }

        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Город: Москва" in result
        assert "Компания: TestCorp" in result
        assert "Пользователь: Иван" in result
        assert "Email: support@test.com" in result
        assert "Статус: pending" in result
        assert "Специальные инструкции" in result

    def test_render_edge_cases(self):
        """Граничные случаи."""
        # Пробелы в default
        template1 = "Значение: {var|значение по умолчанию с пробелами}"
        variables1 = {}
        result1 = VariableResolver.render_template(template1, local_vars=variables1)
        assert "значение по умолчанию с пробелами" in result1

        # Спецсимволы в default
        template2 = "Email: {email|user@example.com}"
        variables2 = {}
        result2 = VariableResolver.render_template(template2, local_vars=variables2)
        assert "user@example.com" in result2

        # False как пустое значение
        template3 = "Статус: {enabled|выключен}"
        variables3 = {"enabled": False}
        result3 = VariableResolver.render_template(template3, local_vars=variables3)
        assert result3 == "Статус: выключен"

    def test_nested_conditional_blocks(self):
        """Вложенные условные блоки."""
        template = """Начало
{?has_outer|
Внешний блок
{?has_inner|
Внутренний блок
}
Конец внешнего блока
}
Конец"""
        variables = {"has_outer": True, "has_inner": True}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Внешний блок" in result
        assert "Внутренний блок" in result
        assert "Конец внешнего блока" in result

        variables_outer_only = {"has_outer": True, "has_inner": False}
        result_outer_only = VariableResolver.render_template(template, local_vars=variables_outer_only)

        # has_outer=True, default содержит {?has_inner|...} (условный блок), обрабатываем рекурсивно
        # has_inner=False, условный блок НЕ показывается (пустая строка)
        assert "Внешний блок" in result_outer_only
        assert "Внутренний блок" not in result_outer_only  # has_inner=False, условный блок не показывается
        assert "Конец внешнего блока" in result_outer_only

        variables_none = {}
        result_none = VariableResolver.render_template(template, local_vars=variables_none)

        assert "Внешний блок" not in result_none
        assert "Внутренний блок" not in result_none

    def test_nested_conditional_blocks_with_variables(self):
        """Вложенные условные блоки с переменными внутри."""
        template = """Начало
{?show_section|
Секция 1
Пользователь: {user_name}
{?show_details|
Детали:
Email: {?user_email|не указан}
Телефон: {user_phone}
}
}
Конец"""
        variables = {
            "show_section": True,
            "show_details": True,
            "user_name": "Иван",
            "user_email": "ivan@example.com",
            "user_phone": "+7-999-123-45-67",
        }
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Секция 1" in result
        assert "Пользователь: Иван" in result
        assert "Детали:" in result
        assert "Email: ivan@example.com" in result
        assert "Телефон: +7-999-123-45-67" in result

        variables_no_details = {
            "show_section": True,
            "show_details": False,
            "user_name": "Иван",
        }
        result_no_details = VariableResolver.render_template(template, local_vars=variables_no_details)

        # show_section=True, default содержит {?show_details|...} (условный блок), обрабатываем рекурсивно
        # show_details=False, условный блок НЕ показывается (пустая строка)
        assert "Пользователь: Иван" in result_no_details
        assert "Детали:" not in result_no_details  # show_details=False, условный блок не показывается

    def test_triple_nested_blocks(self):
        """Тройная вложенность условных блоков."""
        template = """Уровень 0
{?level1|
Уровень 1
{?level2|
Уровень 2
{?level3|
Уровень 3
}
}
}
Конец"""
        variables = {"level1": True, "level2": True, "level3": True}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Уровень 1" in result
        assert "Уровень 2" in result
        assert "Уровень 3" in result

        variables_partial = {"level1": True, "level2": True, "level3": False}
        result_partial = VariableResolver.render_template(template, local_vars=variables_partial)

        # level1=True, level2=True, default содержит {?level3|...} (условный блок), обрабатываем рекурсивно
        # level3=False, условный блок НЕ показывается (пустая строка)
        assert "Уровень 1" in result_partial
        assert "Уровень 2" in result_partial
        assert "Уровень 3" not in result_partial  # level3=False, условный блок не показывается

    def test_conditional_block_with_escaped_braces(self):
        """Условный блок с экранированными скобками."""
        template = """Начало
{?show|
Текст с экранированными скобками: \\{variable\\}
И еще: \\} закрывающая
}
Конец"""
        variables = {"show": True}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Текст с экранированными скобками: {variable}" in result
        assert "И еще: } закрывающая" in result
        assert "\\{" not in result
        assert "\\}" not in result

    def test_conditional_block_with_escaped_braces_and_nested(self):
        """Условный блок с экранированными скобками и вложенными переменными."""
        template = """Начало
{?show|
Текст: \\{escaped\\}
Переменная: {variable}
Еще экранированная: \\}
}
Конец"""
        variables = {"show": True, "variable": "значение"}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Текст: {escaped}" in result
        assert "Переменная: значение" in result
        assert "Еще экранированная: }" in result

    def test_nested_blocks_with_escaped_braces(self):
        """Вложенные блоки с экранированными скобками."""
        template = """Начало
{?outer|
Внешний блок
Экранированная: \\{outer_brace\\}
{?inner|
Внутренний блок
Экранированная: \\}inner_brace
Переменная: {var}
}
}
Конец"""
        variables = {"outer": True, "inner": True, "var": "test"}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Внешний блок" in result
        assert "Экранированная: {outer_brace}" in result
        assert "Внутренний блок" in result
        assert "Экранированная: }inner_brace" in result
        assert "Переменная: test" in result

    def test_default_with_escaped_braces(self):
        """Default значение с экранированными скобками."""
        template = "Текст: {?var|Значение с \\} скобкой}"
        variables = {}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Текст: Значение с } скобкой"

        template2 = "Текст: {?var|Значение с \\{ открывающей}"
        result2 = VariableResolver.render_template(template2, local_vars=variables)

        assert result2 == "Текст: Значение с { открывающей"

    def test_conditional_block_inside_default(self):
        """Условный блок внутри default значения (не показывается если var не найдена)."""
        template = "Текст: {?var|Default с {?nested|вложенным} блоком}"
        variables = {}
        result = VariableResolver.render_template(template, local_vars=variables)

        # По логике: var не найдена, default содержит {?nested|вложенным} (условный блок, т.к. содержит {)
        # Условный блок НЕ показывается если переменная не найдена (пустая строка)
        assert "Default с вложенным блоком" not in result
        assert result == "Текст: "  # Только префикс, условный блок не показывается

    def test_complex_nested_structure(self):
        """Сложная вложенная структура со всеми форматами."""
        template = """Документ
{?has_header|
Заголовок: {title|Без названия}
Автор: ?author|Неизвестен
{?has_metadata|
Метаданные:
Дата: {date|не указана}
Версия: {version|1.0}
{?has_tags|
Теги: {tags|нет}
}
}
}
{?has_content|
Содержание:
{content|Пусто}
}
Конец"""
        variables = {
            "has_header": True,
            "title": "Мой документ",
            "author": "Иван",
            "has_metadata": True,
            "date": "2025-12-17",
            "version": "2.0",
            "has_tags": True,
            "tags": "важно, срочно",
            "has_content": True,
            "content": "Основной текст",
        }
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Заголовок: Мой документ" in result
        assert "Автор: Иван" in result
        assert "Метаданные:" in result
        assert "Дата: 2025-12-17" in result
        assert "Версия: 2.0" in result
        assert "Теги: важно, срочно" in result
        assert "Содержание:" in result
        assert "Основной текст" in result

    def test_nested_blocks_with_mixed_syntax(self):
        """Вложенные блоки со смешанным синтаксисом."""
        template = """Начало
{?section1|
Секция 1
Поле 1: {field1|по умолчанию}
Поле 2: ?field2|default
{?subsection|
Подсекция
Значение: {value}
}
}
{?section2|
Секция 2
Данные: {data}
}
Конец"""
        variables = {
            "section1": True,
            "field1": "значение1",
            "field2": "значение2",
            "subsection": True,
            "value": "test",
            "section2": False,
        }
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Секция 1" in result
        assert "Поле 1: значение1" in result
        assert "Поле 2: значение2" in result
        assert "Подсекция" in result
        assert "Значение: test" in result
        # section2=False, показываем default (содержит \n, обрабатываем рекурсивно)
        assert "Секция 2" not in result  # section2=False, условный блок не показывается

    def test_escaped_backslash(self):
        """Экранированный обратный слэш."""
        template = "Текст: {?var|Путь: C:\\\\Windows\\\\System32}"
        variables = {}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Текст: Путь: C:\\Windows\\System32"

        # {?show|Путь: \\server\\share} когда show=True
        # По логике: если переменная найдена и default не содержит {, возвращаем значение переменной
        template2 = "{?show|Путь: \\\\server\\\\share}"
        variables2 = {"show": True}
        result2 = VariableResolver.render_template(template2, local_vars=variables2)

        # Default не содержит {, поэтому возвращаем значение переменной
        assert result2 == "True"

    def test_multiple_escaped_sequences(self):
        """Множественные экранированные последовательности."""
        template = """{?show|
Текст с \\{первой\\} и \\{второй\\} скобками
И \\} закрывающей
И \\\\ обратным слэшем
}"""
        variables = {"show": True}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "{первой}" in result
        assert "{второй}" in result
        assert "} закрывающей" in result
        assert "\\ обратным слэшем" in result
        assert "\\{" not in result
        assert "\\}" not in result
        assert "\\\\" not in result

    def test_nested_with_all_escape_types(self):
        """Вложенные блоки со всеми типами экранирования."""
        template = """Уровень 0
{?level1|
Уровень 1: \\{escaped1\\}
{?level2|
Уровень 2: \\}escaped2
Переменная: {var}
Еще: \\\\backslash
{?level3|
Уровень 3: \\{escaped3\\}
}
}
}"""
        variables = {"level1": True, "level2": True, "level3": True, "var": "test"}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "Уровень 1: {escaped1}" in result
        assert "Уровень 2: }escaped2" in result
        assert "Переменная: test" in result
        assert "\\backslash" in result
        assert "Уровень 3: {escaped3}" in result

    def test_conditional_block_edge_cases(self):
        """Граничные случаи условных блоков."""
        # Пустой блок - по логике: если переменная найдена и default пустой, возвращаем значение переменной
        template1 = "{?show|}"
        variables1 = {"show": True}
        result1 = VariableResolver.render_template(template1, local_vars=variables1)
        assert result1 == "True"  # Возвращаем значение переменной

        # Блок только с пробелами - default содержит пробелы, но не содержит {, возвращаем значение переменной
        template2 = "{?show|   }"
        variables2 = {"show": True}
        result2 = VariableResolver.render_template(template2, local_vars=variables2)
        assert result2 == "True"  # Возвращаем значение переменной

        # Блок с только экранированными символами - default содержит \\{\\}, но не содержит неэкранированных {
        # Проверяем наличие неэкранированных {
        template3 = "{?show|\\{\\}}"
        variables3 = {"show": True}
        result3 = VariableResolver.render_template(template3, local_vars=variables3)
        # Default не содержит неэкранированных {, возвращаем значение переменной
        assert result3 == "True"

    def test_deep_nesting_four_levels(self):
        """Глубокая вложенность - 4 уровня."""
        template = """L0
{?l1|
L1
{?l2|
L2
{?l3|
L3
{?l4|
L4
}
}
}
}
End"""
        variables = {"l1": True, "l2": True, "l3": True, "l4": True}
        result = VariableResolver.render_template(template, local_vars=variables)

        assert "L1" in result
        assert "L2" in result
        assert "L3" in result
        assert "L4" in result

        variables_partial = {"l1": True, "l2": True, "l3": False, "l4": False}
        result_partial = VariableResolver.render_template(template, local_vars=variables_partial)

        # l1=True, l2=True, default содержит {?l3|...} (условный блок), обрабатываем рекурсивно
        # l3=False, условный блок НЕ показывается (пустая строка)
        assert "L1" in result_partial
        assert "L2" in result_partial
        assert "L3" not in result_partial  # l3=False, условный блок не показывается
        assert "L4" not in result_partial  # l4=False, условный блок не показывается

    def test_all_nesting_scenarios(self):
        """ВСЕ возможные сценарии вложенности."""
        
        # 1. Условный блок внутри условного блока (оба true)
        # {?a|A {?b|B}} когда a=True, b=True
        # default содержит {?b|B}, поэтому это условный блок, обрабатываем рекурсивно
        # Внутри обрабатываем {?b|B}, когда b=True возвращаем значение b (True)
        template1 = "{?a|A {?b|B}}"
        result1 = VariableResolver.render_template(template1, local_vars={"a": True, "b": True})
        # По логике: default содержит {, обрабатываем рекурсивно
        # Внутри {?b|B} когда b=True, default "B" не содержит {, возвращаем значение b (True)
        assert "A" in result1 and "True" in result1

        # 2. Условный блок внутри условного блока (внешний true, внутренний false)
        result2 = VariableResolver.render_template(template1, local_vars={"a": True, "b": False})
        # a=True, default содержит {, обрабатываем рекурсивно
        # b=False, default "B" не содержит { и \n, это простой default, показываем "B"
        assert "A" in result2 and "B" in result2

        # 3. Условный блок внутри условного блока (внешний false)
        result3 = VariableResolver.render_template(template1, local_vars={"a": False, "b": True})
        # a=False, default содержит { (условный блок), НЕ показываем (пустая строка)
        assert result3 == ""  # a=False, условный блок не показывается
        
        # 4. Три уровня вложенности (все true)
        # {?a|A {?b|B {?c|C}}} когда a=True, b=True, c=True
        # default содержит {?b|B {?c|C}}, обрабатываем рекурсивно
        # Внутри {?b|B {?c|C}}, default содержит {?c|C}, обрабатываем рекурсивно
        # Внутри {?c|C}, default "C" не содержит {, возвращаем значение c (True)
        template4 = "{?a|A {?b|B {?c|C}}}"
        result4 = VariableResolver.render_template(template4, local_vars={"a": True, "b": True, "c": True})
        assert "A" in result4 and "B" in result4 and "True" in result4  # c=True возвращает "True"
        
        # 5. Три уровня вложенности (средний false)
        # a=True, default содержит {?b|B {?c|C}} (условный блок), обрабатываем рекурсивно
        # b=False, default "B {?c|C}" содержит { (условный блок), НЕ показываем (пустая строка)
        result5 = VariableResolver.render_template(template4, local_vars={"a": True, "b": False, "c": True})
        assert "A" in result5 and "B" not in result5  # b=False, условный блок не показывается
        
        # 6. Переменные внутри условных блоков
        # {?show|Name: {name}, Age: {age}} когда show=True
        # default содержит {name} и {age}, обрабатываем рекурсивно
        template6 = "{?show|Name: {name}, Age: {age}}"
        result6 = VariableResolver.render_template(template6, local_vars={"show": True, "name": "Ivan", "age": 30})
        assert "Name: Ivan" in result6 and "Age: 30" in result6
        
        # 7. Переменные внутри вложенных условных блоков
        # {?outer|Outer {?inner|Inner: {value}}} когда outer=True, inner=True
        # default содержит {?inner|Inner: {value}}, обрабатываем рекурсивно
        # Внутри {?inner|Inner: {value}}, default содержит {value}, обрабатываем рекурсивно
        template7 = "{?outer|Outer {?inner|Inner: {value}}}"
        result7 = VariableResolver.render_template(template7, local_vars={"outer": True, "inner": True, "value": "test"})
        assert "Outer" in result7 and "Inner: test" in result7
        
        # 8. Default внутри условного блока
        # {?show|Status: {?status|unknown}} когда show=True, status="active"
        # default содержит {?status|unknown}, обрабатываем рекурсивно
        # Внутри {?status|unknown}, status="active", default "unknown" не содержит {, возвращаем значение status ("active")
        template8 = "{?show|Status: {?status|unknown}}"
        result8 = VariableResolver.render_template(template8, local_vars={"show": True, "status": "active"})
        assert "Status: active" in result8
        
        # 9. Default внутри условного блока (переменная не найдена)
        # show=True, default содержит {?status|unknown}, обрабатываем рекурсивно
        # status не найдена, default "unknown" показывается
        result9 = VariableResolver.render_template(template8, local_vars={"show": True})
        assert "Status: unknown" in result9
        
        # 10. Условный блок с экранированными скобками внутри
        template10 = "{?show|Text: \\{escaped\\} and {var}}"
        result10 = VariableResolver.render_template(template10, local_vars={"show": True, "var": "value"})
        assert "{escaped}" in result10 and "value" in result10
        
        # 11. Вложенные блоки с экранированными скобками
        # {?a|A \\{escaped\\} {?b|B \\}escaped}} когда a=True, b=True
        # default содержит {?b|B \\}escaped}, обрабатываем рекурсивно
        # Внутри {?b|B \\}escaped}, default "B \\}escaped" не содержит неэкранированных {, возвращаем значение b (True)
        template11 = "{?a|A \\{escaped\\} {?b|B \\}escaped}}"
        result11 = VariableResolver.render_template(template11, local_vars={"a": True, "b": True})
        assert "A" in result11 and "{escaped}" in result11 and "True" in result11  # b=True возвращает "True"
        
        # 12. Многострочные вложенные блоки
        template12 = """{?a|
Line A
{?b|
Line B
{?c|
Line C
}
}
}"""
        result12 = VariableResolver.render_template(template12, local_vars={"a": True, "b": True, "c": True})
        assert "Line A" in result12 and "Line B" in result12 and "Line C" in result12
        
        # 13. Смешанные форматы: {var}, {?var}, {?var|default} внутри блоков
        template13 = "{?show|Required: {req}, Optional: {?opt}, Default: {?def|default}}"
        result13 = VariableResolver.render_template(template13, local_vars={
            "show": True, "req": "R", "opt": "O"
        })
        assert "Required: R" in result13 and "Optional: O" in result13 and "Default: default" in result13
        
        # 14. Короткий формат ?var|default внутри условного блока
        # {?show|Short: ?var|default, Value: {var}} когда show=True, var="value"
        # Короткий формат обрабатывается первым: ?var|default → value
        # Затем обрабатываются блоки: {var} → value
        template14 = "{?show|Short: ?var|default, Value: {var}}"
        result14 = VariableResolver.render_template(template14, local_vars={"show": True, "var": "value"})
        assert "Short: value" in result14  # Короткий формат заменяется на value
        assert "value" in result14  # {var} тоже заменяется на value
        
        # 15. Вложенные блоки с переменными и default
        # {?a|A: {a_val|default_a} {?b|B: {b_val|default_b}}} когда a=True, b=True, a_val="A1"
        # default содержит {a_val|default_a} и {?b|B: {b_val|default_b}}, обрабатываем рекурсивно
        # {a_val|default_a} когда a_val="A1", возвращаем "A1"
        # {?b|B: {b_val|default_b}} когда b=True, default содержит {b_val|default_b}, обрабатываем рекурсивно
        # {b_val|default_b} когда b_val не найдена, показываем default_b
        template15 = "{?a|A: {a_val|default_a} {?b|B: {b_val|default_b}}}"
        result15 = VariableResolver.render_template(template15, local_vars={"a": True, "b": True, "a_val": "A1"})
        assert "A: A1" in result15 and "B: default_b" in result15
        
        # 16. Глубокая вложенность с переменными на каждом уровне
        template16 = "{?l1|L1: {v1} {?l2|L2: {v2} {?l3|L3: {v3}}}}"
        result16 = VariableResolver.render_template(template16, local_vars={
            "l1": True, "l2": True, "l3": True, "v1": "V1", "v2": "V2", "v3": "V3"
        })
        assert "L1: V1" in result16 and "L2: V2" in result16 and "L3: V3" in result16
        
        # 17. Условный блок с вложенным default (обрабатывается рекурсивно)
        # {?var|Default с {?nested|вложенным} блоком} когда var не найдена
        # Показываем default, default содержит {?nested|вложенным}, обрабатываем рекурсивно
        # 17. Условный блок с вложенным default (не показывается если var не найдена)
        # {?var|Default с {?nested|вложенным} блоком} когда var не найдена
        # default содержит {?nested|вложенным} (условный блок, т.к. содержит {)
        # Условный блок НЕ показывается если переменная не найдена (пустая строка)
        template17 = "{?var|Default с {?nested|вложенным} блоком}"
        result17 = VariableResolver.render_template(template17, local_vars={})
        assert "Default с вложенным блоком" not in result17
        assert result17 == ""  # Условный блок не показывается
        
        # 18. Экранированные обратные слэши в условных блоках
        # {?show|Path: C:\\\\Windows\\\\System32} когда show=True
        # default не содержит { и \n, это простой default, возвращаем значение переменной
        template18 = "{?show|Path: C:\\\\Windows\\\\System32}"
        result18 = VariableResolver.render_template(template18, local_vars={"show": True})
        assert result18 == "True"  # Простой default, возвращаем значение переменной
        
        # 19. Вложенные блоки с обратными слэшами
        # {?a|A: \\\\server {?b|B: \\\\share}} когда a=True, b=True
        # default содержит {?b|B: \\\\share} (условный блок), обрабатываем рекурсивно
        # b=True, default "B: \\\\share" не содержит { и \n, возвращаем значение b (True)
        template19 = "{?a|A: \\\\server {?b|B: \\\\share}}"
        result19 = VariableResolver.render_template(template19, local_vars={"a": True, "b": True})
        assert "A:" in result19 and "server" in result19 and "True" in result19  # b=True возвращает "True"
        
        # 20. Все комбинации: переменные, default, условные блоки, экранирование
        template20 = """{?header|
Header: {title|Untitled}
{?has_meta|
Meta: {meta|none}
{?has_tags|
Tags: {tags|no tags}
}
}
}"""
        result20 = VariableResolver.render_template(template20, local_vars={
            "header": True, "title": "My Title", "has_meta": True, "meta": "info", "has_tags": True
        })
        assert "Header: My Title" in result20
        assert "Meta: info" in result20
        assert "Tags: no tags" in result20


class TestVariablesService:
    """Тесты VariablesService (резолвинг @var:key)."""

    @pytest.mark.asyncio
    async def test_resolve_simple_value(self, app):
        """Простое значение возвращается как есть."""
        container = get_container()
        service = container.variables_service

        result = await service.resolve("simple_string")
        assert result == "simple_string"

    @pytest.mark.asyncio
    async def test_resolve_var_reference(self, app):
        """@var:key загружает переменную из БД."""
        container = get_container()
        service = container.variables_service

        # Создаём переменную
        var = Variable(key="test_resolve_var", value="resolved_value")
        await container.variable_repository.set(var)

        result = await service.resolve("@var:test_resolve_var")

        assert result == "resolved_value"

        # Cleanup
        await container.variable_repository.delete("test_resolve_var")

    @pytest.mark.asyncio
    async def test_resolve_dict_with_vars(self, app):
        """Резолвинг словаря с @var:key."""
        container = get_container()
        service = container.variables_service

        # Создаём переменные
        await container.variable_repository.set(Variable(key="company", value="TestCorp"))
        await container.variable_repository.set(Variable(key="phone", value="123-456"))

        data = {
            "company_name": "@var:company",
            "phone": "@var:phone",
            "static": "value"
        }

        result = await service.resolve(data)

        assert result["company_name"] == "TestCorp"
        assert result["phone"] == "123-456"
        assert result["static"] == "value"

        # Cleanup
        await container.variable_repository.delete("company")
        await container.variable_repository.delete("phone")

    @pytest.mark.asyncio
    async def test_resolve_nested_dict(self, app):
        """Резолвинг вложенного словаря."""
        container = get_container()
        service = container.variables_service

        await container.variable_repository.set(Variable(key="nested_var", value="nested_value"))

        data = {
            "level1": {
                "level2": "@var:nested_var"
            }
        }

        result = await service.resolve(data)

        assert result["level1"]["level2"] == "nested_value"

        await container.variable_repository.delete("nested_var")

    @pytest.mark.asyncio
    async def test_resolve_list(self, app):
        """Резолвинг списка."""
        container = get_container()
        service = container.variables_service

        await container.variable_repository.set(Variable(key="list_var", value="item"))

        data = ["static", "@var:list_var", "another"]

        result = await service.resolve(data)

        assert result == ["static", "item", "another"]

        await container.variable_repository.delete("list_var")

    @pytest.mark.asyncio
    async def test_resolve_missing_var_raises_error(self, app):
        """Несуществующая переменная вызывает VariableResolutionError."""
        container = get_container()
        service = container.variables_service

        with pytest.raises(VariableResolutionError):
            await service.resolve("@var:nonexistent_var_xyz")

    @pytest.mark.asyncio
    async def test_resolve_preserves_non_var_strings(self, app):
        """Строки без @var: сохраняются."""
        container = get_container()
        service = container.variables_service

        result = await service.resolve("regular string without var")

        assert result == "regular string without var"

