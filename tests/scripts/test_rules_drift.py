"""Проверки гейта scripts/gates/repo/rules_drift.py."""

from __future__ import annotations

from pathlib import Path

from scripts.gates.repo.rules_drift import (
    command_errors,
    dead_path_errors,
    expand_service_names,
    js_mask_errors,
    numbering_errors,
    pair_errors,
    rule_frontmatter_errors,
    section_errors,
    stop_word_errors,
    symbol_errors,
    table_errors,
)

REPO = Path(__file__).resolve().parents[2]


def test_frontmatter_description_limit() -> None:
    meta = {"description": "x" * 201}
    errors = rule_frontmatter_errors(REPO, "shop.mdc", "body", meta)
    assert any("description 201" in error for error in errors)


def test_frontmatter_globs_missing(tmp_path: Path) -> None:
    meta = {"description": "d", "globs": ["apps/nosuch/**"]}
    errors = rule_frontmatter_errors(tmp_path, "shop.mdc", "body", meta)
    assert any("glob без совпадений" in error for error in errors)


def test_dead_path() -> None:
    text = "сервис собирает `apps/voice/container.py` и `apps/shop/main.py`"
    errors = dead_path_errors(REPO, "x.mdc", text)
    assert len(errors) == 1 and "apps/voice/container.py" in errors[0]


def test_stop_words_outside_backticks() -> None:
    assert stop_word_errors("x.mdc", "`legacy` слой убран — правило legacy")
    assert not stop_word_errors("x.mdc", "`legacy` слой убран")


def test_numbering_gap() -> None:
    text = "## Канон\n1. а\n2. б\n4. в\n"
    errors = numbering_errors("x.mdc", text)
    assert errors and "нумерация 4 после 2" in errors[0]


def test_section_template() -> None:
    domain = "## Модель\n## Инварианты\n## Запреты\n## Интеграции\n"
    assert any("порядок разделов" in error for error in section_errors("shop.mdc", domain))
    cross = "## Канон\n## Нарезка\n"
    assert any("вне шаблона" in error for error in section_errors("events.mdc", cross))


def test_symbols() -> None:
    idents = frozenset({"RealClassName", "existing_func"})
    text = "метод `existing_func` и `ghost_service_client`"
    errors = symbol_errors("x.mdc", text, idents)
    assert len(errors) == 1 and "ghost_service_client" in errors[0]


def test_symbol_pair() -> None:
    text = "`ShopOrderService` (`apps/shop/services/order_service.py`) и `Ghost` (`apps/shop/main.py`)"
    errors = pair_errors(REPO, "x.mdc", text)
    assert len(errors) == 1 and "Ghost" in errors[0]


def test_js_mask() -> None:
    text = "спек `*.spec.js`"
    errors = js_mask_errors("x.mdc", text, frozenset(), frozenset({"x.spec.ts"}))
    assert errors and ".ts" in errors[0]
    assert not js_mask_errors("x.mdc", text, frozenset({"x.spec.js"}), frozenset())


def test_commands(tmp_path: Path) -> None:
    targets = frozenset({"lint", "test-ui"})
    errors = command_errors(tmp_path, "x.mdc", "`make lint` и `make nosuch`", targets)
    assert len(errors) == 1 and "nosuch" in errors[0]


def test_expand_service_names() -> None:
    assert expand_service_names("code_runner_python, _node, _go") == [
        "code_runner_python", "code_runner_node", "code_runner_go",
    ]


def test_table_check() -> None:
    main_text = "## Сервисы и стек\n\n| Сервис | Порт | Роль |\n|---|---|---|\n| shop | 8027 | витрина |\n"
    errors = table_errors(main_text, {"shop": 8027, "stock": 8026}, ["customers"], ["shop.mdc"])
    assert any("`stock`" in error and "Сервисы" in error for error in errors)
    assert any("shop.mdc" in error and "Навигации" in error for error in errors)
