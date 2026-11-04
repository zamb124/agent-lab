"""Парсеры файлового импорта меню: XLSX-шаблон и composition v2 Яндекс Еды."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.shop.models import ShopMeasureUnit
from apps.shop.services.menu_file_parsers import parse_menu_xlsx, parse_yandex_json
from core.errors.boundary import PlatformConflictError

FIXTURES = Path(__file__).parent / "fixtures"


def test_yandex_composition_dishes_sections_modifiers_and_row_errors() -> None:
    parsed = parse_yandex_json((FIXTURES / "yandex_menu.json").read_bytes())

    assert [d.name for d in parsed.dishes] == ["Маргарита", "Лимонад"]
    pizza, lemonade = parsed.dishes
    assert pizza.section_path == ["Горячее", "Пицца"]
    assert pizza.price_minor == 59000
    assert (pizza.measure, pizza.measure_unit) == (450, ShopMeasureUnit.G)
    assert pizza.nutrition is not None and pizza.nutrition.carbs_g == 30
    assert pizza.ingredients == ["тесто", "томаты", "моцарелла"]
    assert pizza.photo_url == "https://example.com/margherita.jpg"
    [size] = pizza.modifier_groups
    assert (size.name, size.min_selected, size.max_selected) == ("Размер", 1, 1)
    assert [(o.name, o.price_minor, o.external_id) for o in size.options] == [
        ("30 см", 0, "mod-30"),
        ("40 см", 20000, "mod-40"),
    ]
    assert lemonade.price_minor == 14990
    assert (lemonade.measure, lemonade.measure_unit) == (500, ShopMeasureUnit.ML)
    assert [(e.row, e.error_code) for e in parsed.errors] == [
        (3, "shop_menu_file_price_invalid"),
        (4, "shop_menu_file_section_invalid"),
    ]


def test_yandex_json_without_items_is_invalid_file() -> None:
    with pytest.raises(PlatformConflictError) as exc_info:
        _ = parse_yandex_json(b'{"categories": []}')
    assert exc_info.value.error_code == "shop_menu_file_invalid"


def test_xlsx_template_header_synonyms_units_and_row_errors() -> None:
    parsed = parse_menu_xlsx((FIXTURES / "menu_template.xlsx").read_bytes())

    assert [d.name for d in parsed.dishes] == ["Борщ", "Морс"]
    borsch, mors = parsed.dishes
    assert borsch.row == 3
    assert borsch.section_path == ["Супы"]
    assert borsch.price_minor == 35000
    assert (borsch.measure, borsch.measure_unit) == (300, ShopMeasureUnit.G)
    assert borsch.ingredients == ["свёкла", "капуста", "говядина"]
    assert borsch.nutrition is not None and borsch.nutrition.fats_g == 2.5
    assert borsch.photo_url == "https://example.com/borsch.jpg"
    [bread] = borsch.modifier_groups
    assert bread.max_selected == 1
    assert [(o.name, o.price_minor) for o in bread.options] == [("Белый", 0), ("Бородинский", 2000)]
    assert mors.price_minor == 12050
    assert (mors.measure, mors.measure_unit) == (500, ShopMeasureUnit.ML)
    assert [(o.name, o.price_minor) for o in mors.modifier_groups[0].options] == [
        ("Лёд", 0),
        ("Мята", 1500),
    ]
    assert [(e.row, e.error_code) for e in parsed.errors] == [
        (6, "shop_menu_file_price_invalid"),
        (7, "shop_menu_file_name_missing"),
        (8, "shop_menu_file_nutrition_incomplete"),
    ]


def test_xlsx_without_name_and_price_header_is_invalid_file() -> None:
    with pytest.raises(PlatformConflictError) as exc_info:
        _ = parse_menu_xlsx(b"not an xlsx")
    assert exc_info.value.error_code == "shop_menu_file_invalid"
