"""
Unit тесты для проверок (checkers) в TestRunner.

Тестирует все типы checker:
- contains: проверка наличия слов
- not_contains: проверка отсутствия слов
- regex: регулярные выражения
- length: проверка длины
- state: проверка полей state
- Python функции
"""

from datetime import date

import pytest

from apps.flows.src.evaluation.runners.test_runner import TestRunner
from core.state import ExecutionState


async def _noop_callable(state: ExecutionState) -> ExecutionState:
    return state


@pytest.fixture
def runner():
    """Создает TestRunner для тестов."""
    return TestRunner(
        target_id="test_flow:default",
        target_callable=_noop_callable,
        run_date=date.today(),
        iteration=1,
    )


class TestContainsChecker:
    """Тесты для contains: checker."""

    def test_contains_single_word_match(self, runner):
        """Одно слово - найдено."""
        result = runner._execute_string_checker("contains:привет", {}, "Привет, как дела?")
        assert result is True

    def test_contains_single_word_no_match(self, runner):
        """Одно слово - не найдено."""
        result = runner._execute_string_checker("contains:goodbye", {}, "Привет, как дела?")
        assert result is False

    def test_contains_multiple_words_first_match(self, runner):
        """Несколько слов - первое найдено."""
        result = runner._execute_string_checker("contains:привет|hello|hi", {}, "Привет!")
        assert result is True

    def test_contains_multiple_words_last_match(self, runner):
        """Несколько слов - последнее найдено."""
        result = runner._execute_string_checker("contains:goodbye|bye|пока", {}, "Пока!")
        assert result is True

    def test_contains_case_insensitive(self, runner):
        """Регистронезависимый поиск."""
        result = runner._execute_string_checker("contains:ПРИВЕТ", {}, "привет")
        assert result is True

    def test_contains_with_spaces(self, runner):
        """Слова с пробелами."""
        result = runner._execute_string_checker(
            "contains:добро пожаловать|welcome", {}, "Добро пожаловать на сайт!"
        )
        assert result is True


class TestNotContainsChecker:
    """Тесты для not_contains: checker."""

    def test_not_contains_word_absent(self, runner):
        """Слово отсутствует - passed."""
        result = runner._execute_string_checker("not_contains:ошибка", {}, "Всё хорошо!")
        assert result is True

    def test_not_contains_word_present(self, runner):
        """Слово присутствует - failed."""
        result = runner._execute_string_checker("not_contains:ошибка", {}, "Произошла ошибка!")
        assert result is False

    def test_not_contains_multiple_words_all_absent(self, runner):
        """Все слова отсутствуют - passed."""
        result = runner._execute_string_checker(
            "not_contains:ошибка|error|fail", {}, "Операция выполнена успешно"
        )
        assert result is True

    def test_not_contains_multiple_words_one_present(self, runner):
        """Одно слово присутствует - failed."""
        result = runner._execute_string_checker("not_contains:ошибка|error|fail", {}, "Operation failed")
        assert result is False


class TestRegexChecker:
    """Тесты для regex: checker."""

    def test_regex_number_match(self, runner):
        """Число в тексте."""
        result = runner._execute_string_checker("regex:\\b42\\b", {}, "Ответ: 42")
        assert result is True

    def test_regex_number_no_match(self, runner):
        """Число не найдено."""
        result = runner._execute_string_checker("regex:\\b42\\b", {}, "Ответ: 43")
        assert result is False

    def test_regex_pattern_with_groups(self, runner):
        """Паттерн с группами."""
        result = runner._execute_string_checker("regex:ORD-\\d+", {}, "Ваш заказ ORD-12345 создан")
        assert result is True

    def test_regex_case_insensitive(self, runner):
        """Regex регистронезависимый."""
        result = runner._execute_string_checker("regex:hello", {}, "HELLO world")
        assert result is True

    def test_regex_complex_pattern(self, runner):
        """Сложный regex."""
        result = runner._execute_string_checker("regex:^\\[.*\\]", {}, "[ORDER] Заказ создан")
        assert result is True


class TestLengthChecker:
    """Тесты для length: checker."""

    def test_length_minimum_pass(self, runner):
        """Минимальная длина - passed."""
        result = runner._execute_string_checker("length:10", {}, "Это достаточно длинный ответ")
        assert result is True

    def test_length_minimum_fail(self, runner):
        """Минимальная длина - failed."""
        result = runner._execute_string_checker("length:100", {}, "Короткий ответ")
        assert result is False

    def test_length_maximum_pass(self, runner):
        """Максимальная длина - passed."""
        result = runner._execute_string_checker("length:-20", {}, "Короткий ответ")
        assert result is True

    def test_length_maximum_fail(self, runner):
        """Максимальная длина - failed."""
        result = runner._execute_string_checker("length:-5", {}, "Слишком длинный ответ")
        assert result is False

    def test_length_range_pass(self, runner):
        """Диапазон длины - passed."""
        result = runner._execute_string_checker("length:5-50", {}, "Ответ средней длины")
        assert result is True

    def test_length_range_too_short(self, runner):
        """Диапазон длины - слишком короткий."""
        result = runner._execute_string_checker("length:20-100", {}, "Короткий")
        assert result is False

    def test_length_range_too_long(self, runner):
        """Диапазон длины - слишком длинный."""
        result = runner._execute_string_checker(
            "length:1-10", {}, "Этот ответ точно длиннее десяти символов"
        )
        assert result is False


class TestStateChecker:
    """Тесты для state: checker."""

    def test_state_equality_string(self, runner):
        """Равенство строке."""
        result = runner._execute_string_checker("state:route == 'order'", {"route": "order"}, "")
        assert result is True

    def test_state_equality_string_fail(self, runner):
        """Равенство строке - не равно."""
        result = runner._execute_string_checker("state:route == 'order'", {"route": "complaint"}, "")
        assert result is False

    def test_state_not_equal(self, runner):
        """Неравенство."""
        result = runner._execute_string_checker("state:route != 'error'", {"route": "order"}, "")
        assert result is True

    def test_state_equality_number(self, runner):
        """Равенство числу."""
        result = runner._execute_string_checker("state:count == 42", {"count": 42}, "")
        assert result is True

    def test_state_greater_than(self, runner):
        """Больше чем."""
        result = runner._execute_string_checker("state:count > 10", {"count": 42}, "")
        assert result is True

    def test_state_less_than(self, runner):
        """Меньше чем."""
        result = runner._execute_string_checker("state:count < 100", {"count": 42}, "")
        assert result is True

    def test_state_greater_equal(self, runner):
        """Больше или равно."""
        result = runner._execute_string_checker("state:count >= 42", {"count": 42}, "")
        assert result is True

    def test_state_less_equal(self, runner):
        """Меньше или равно."""
        result = runner._execute_string_checker("state:count <= 42", {"count": 42}, "")
        assert result is True

    def test_state_nested_field(self, runner):
        """Вложенное поле."""
        result = runner._execute_string_checker(
            "state:user.name == 'John'", {"user": {"name": "John", "age": 30}}, ""
        )
        assert result is True

    def test_state_null_check(self, runner):
        """Проверка на null."""
        result = runner._execute_string_checker("state:response != null", {"response": "some value"}, "")
        assert result is True

    def test_state_null_check_is_null(self, runner):
        """Поле равно null."""
        result = runner._execute_string_checker("state:error == null", {"error": None}, "")
        assert result is True

    def test_state_boolean_true(self, runner):
        """Проверка true."""
        result = runner._execute_string_checker("state:processed == true", {"processed": True}, "")
        assert result is True

    def test_state_boolean_false(self, runner):
        """Проверка false."""
        result = runner._execute_string_checker("state:failed == false", {"failed": False}, "")
        assert result is True

    def test_state_field_exists(self, runner):
        """Проверка существования поля (без оператора)."""
        result = runner._execute_string_checker("state:response", {"response": "value"}, "")
        assert result is True

    def test_state_field_not_exists(self, runner):
        """Поле не существует."""
        result = runner._execute_string_checker("state:missing_field", {"response": "value"}, "")
        assert result is False

    def test_state_deeply_nested(self, runner):
        """Глубоко вложенное поле."""
        result = runner._execute_string_checker(
            "state:data.user.profile.name == 'Alice'",
            {"data": {"user": {"profile": {"name": "Alice"}}}},
            "",
        )
        assert result is True


class TestPythonFunctionChecker:
    """Тесты для Python функций как checker."""

    def test_function_checker_pass(self, runner):
        """Python функция - passed."""
        result = runner._execute_string_checker(
            "apps.flows.bundles.example_react.checks.check_greeting", {}, "Привет! Рад вас видеть!"
        )
        assert result is True

    def test_function_checker_fail(self, runner):
        """Python функция - failed."""
        result = runner._execute_string_checker("apps.flows.bundles.example_react.checks.check_greeting", {}, "Пока!")
        assert result is False

    def test_function_with_state(self, runner):
        """Python функция использует state."""
        result = runner._execute_string_checker(
            "apps.flows.bundles.example_graph.checks.check_order_route", {"route": "order"}, "Заказ создан"
        )
        assert result is True
