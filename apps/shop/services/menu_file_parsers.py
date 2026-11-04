"""Парсеры файлового импорта меню: XLSX-шаблон и JSON Яндекс Еды.

``yandex_json`` — ответ ``GET /menu/{restaurantId}/composition``
(``application/vnd.eats.menu.composition.v2+json``): ``categories`` с ``parentId`` и
``items`` с ``price`` в рублях, ``measure``/``measureUnit`` (``г``/``мл``/``g``/``ml``),
``nutrients`` на 100 г, ``modifierGroups`` и ``images``. Посторонние поля спеки
(``vat``, ``schedules``, ``excise``) не читаются.

XLSX — первый лист; строка заголовка ищется в первых строках по синонимам колонок
(``Название``/``Цена`` обязательны; ``Категория``, ``Описание``, ``Вес``, ``Единица``,
``Состав``, ``Ккал``/``Белки``/``Жиры``/``Углеводы``, ``Фото``, ``Модификаторы``).
Ячейка модификаторов: группы через ``|`` или перевод строки, группа —
``Название [N]: опция +цена; опция``, где ``[N]`` — максимум выбора.

Строка, которая не стала блюдом, попадает в ``errors`` с ``error_code``; файл,
который не читается целиком, — ``PlatformConflictError``.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Literal
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.cell.rich_text import CellRichText
from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.shop.models.enums import ShopMeasureUnit
from apps.shop.models.import_api import ShopMenuFileImportError
from apps.shop.models.nutrition import ShopNutrition
from core.errors.boundary import PlatformConflictError
from core.models import StrictBaseModel

DEFAULT_SECTION_NAME = "Меню"
_HEADER_SCAN_ROWS = 10
_MINOR_PER_UNIT = Decimal(100)


class ParsedModifierOption(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)
    price_minor: int = Field(ge=0)
    max_per_option: int = Field(default=1, ge=1)
    external_id: str | None = None


class ParsedModifierGroup(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)
    min_selected: int = Field(default=0, ge=0)
    max_selected: int | None = Field(default=None, ge=1)
    options: list[ParsedModifierOption] = Field(min_length=1)


class ParsedDish(StrictBaseModel):
    """Блюдо файла; ``section_path`` — имена разделов от корня, пустой — раздел по умолчанию."""

    row: int = Field(ge=1)
    section_path: list[str]
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    price_minor: int = Field(gt=0)
    measure: int | None = Field(default=None, ge=0)
    measure_unit: ShopMeasureUnit = ShopMeasureUnit.G
    ingredients: list[str] = Field(default_factory=list)
    nutrition: ShopNutrition | None = None
    photo_url: str | None = None
    modifier_groups: list[ParsedModifierGroup] = Field(default_factory=list)


class ParsedMenuFile(StrictBaseModel):
    dishes: list[ParsedDish]
    errors: list[ShopMenuFileImportError]


class _RowError(Exception):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code: str = error_code


def _invalid_file(detail: str) -> PlatformConflictError:
    return PlatformConflictError(detail, error_code="shop_menu_file_invalid")


def _price_minor(value: Decimal) -> int:
    minor = int((value * _MINOR_PER_UNIT).to_integral_value())
    if minor <= 0:
        raise _RowError("shop_menu_file_price_invalid")
    return minor


_UNIT_BY_TOKEN: dict[str, tuple[ShopMeasureUnit, int]] = {
    "г": (ShopMeasureUnit.G, 1),
    "гр": (ShopMeasureUnit.G, 1),
    "g": (ShopMeasureUnit.G, 1),
    "кг": (ShopMeasureUnit.G, 1000),
    "kg": (ShopMeasureUnit.G, 1000),
    "мл": (ShopMeasureUnit.ML, 1),
    "ml": (ShopMeasureUnit.ML, 1),
    "л": (ShopMeasureUnit.ML, 1000),
    "l": (ShopMeasureUnit.ML, 1000),
    "шт": (ShopMeasureUnit.PCS, 1),
    "pcs": (ShopMeasureUnit.PCS, 1),
}


def _unit(token: str) -> tuple[ShopMeasureUnit, int]:
    key = token.strip().lower().rstrip(".")
    if key not in _UNIT_BY_TOKEN:
        raise _RowError("shop_menu_file_measure_invalid")
    return _UNIT_BY_TOKEN[key]


# --- Яндекс Еда: composition v2 ---


class _YandexModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", str_strip_whitespace=True)


class YandexCategory(_YandexModel):
    id: str = Field(min_length=1)
    parentId: str | None = None
    name: str = Field(min_length=1)
    sortOrder: int = 100


class YandexNutrients(_YandexModel):
    calories: float = Field(ge=0)
    proteins: float = Field(ge=0)
    fats: float = Field(ge=0)
    carbohydrates: float = Field(ge=0)


class YandexModifier(_YandexModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price: Decimal = Field(ge=0)
    minAmount: int = Field(default=0, ge=0)
    maxAmount: int = Field(default=1, ge=0)


class YandexModifierGroup(_YandexModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    modifiers: list[YandexModifier] = Field(default_factory=list)
    minSelectedModifiers: int = Field(default=0, ge=0)
    maxSelectedModifiers: int = Field(default=0, ge=0)
    sortOrder: int = 100


class YandexImage(_YandexModel):
    url: str = Field(min_length=1)


class YandexAdditionalDescriptions(_YandexModel):
    consisting_ingredients: list[str] = Field(default_factory=list)


class YandexItem(_YandexModel):
    id: str = Field(min_length=1)
    categoryId: str | None = None
    name: str = Field(min_length=1)
    description: str = ""
    price: Decimal
    measure: int | None = Field(default=None, ge=0)
    measureUnit: Literal["г", "мл", "g", "ml"] | None = None
    nutrients: YandexNutrients | None = None
    sortOrder: int = 100
    modifierGroups: list[YandexModifierGroup] = Field(default_factory=list)
    images: list[YandexImage] = Field(default_factory=list)
    additional_descriptions: YandexAdditionalDescriptions | None = None


class YandexMenuComposition(_YandexModel):
    categories: list[YandexCategory] = Field(default_factory=list)
    items: list[YandexItem]


def _yandex_section_path(category_id: str | None, by_id: dict[str, YandexCategory]) -> list[str]:
    path: list[str] = []
    seen: set[str] = set()
    node = category_id
    while node is not None:
        if node in seen or node not in by_id:
            raise _RowError("shop_menu_file_section_invalid")
        seen.add(node)
        category = by_id[node]
        path.insert(0, category.name)
        node = category.parentId
    return path


def _yandex_group(group: YandexModifierGroup) -> ParsedModifierGroup:
    if not group.modifiers:
        raise _RowError("shop_menu_file_modifier_invalid")
    return ParsedModifierGroup(
        name=group.name,
        min_selected=group.minSelectedModifiers,
        max_selected=group.maxSelectedModifiers if group.maxSelectedModifiers > 0 else None,
        options=[
            ParsedModifierOption(
                name=modifier.name,
                price_minor=int((modifier.price * _MINOR_PER_UNIT).to_integral_value()),
                max_per_option=max(modifier.maxAmount, 1),
                external_id=modifier.id,
            )
            for modifier in group.modifiers
        ],
    )


def _yandex_dish(row: int, item: YandexItem, by_id: dict[str, YandexCategory]) -> ParsedDish:
    unit = ShopMeasureUnit.G
    if item.measureUnit is not None:
        unit, _ = _unit(item.measureUnit)
    nutrition = None
    if item.nutrients is not None:
        nutrition = ShopNutrition(
            calories_kcal=item.nutrients.calories,
            proteins_g=item.nutrients.proteins,
            fats_g=item.nutrients.fats,
            carbs_g=item.nutrients.carbohydrates,
        )
    groups = sorted(item.modifierGroups, key=lambda g: g.sortOrder)
    ingredients = (
        list(item.additional_descriptions.consisting_ingredients)
        if item.additional_descriptions is not None
        else []
    )
    return ParsedDish(
        row=row,
        section_path=_yandex_section_path(item.categoryId, by_id),
        name=item.name,
        description=item.description,
        price_minor=_price_minor(item.price),
        measure=item.measure,
        measure_unit=unit,
        ingredients=ingredients,
        nutrition=nutrition,
        photo_url=item.images[0].url if item.images else None,
        modifier_groups=[_yandex_group(g) for g in groups],
    )


def parse_yandex_json(data: bytes) -> ParsedMenuFile:
    """Меню Яндекс Еды; ``row`` — 1-based номер позиции в ``items`` по ``sortOrder``."""
    try:
        composition = YandexMenuComposition.model_validate_json(data)
    except ValidationError as exc:
        raise _invalid_file("Yandex menu JSON does not match composition v2") from exc
    by_id = {c.id: c for c in composition.categories}
    dishes: list[ParsedDish] = []
    errors: list[ShopMenuFileImportError] = []
    ordered = sorted(enumerate(composition.items, start=1), key=lambda pair: pair[1].sortOrder)
    for row, item in ordered:
        try:
            dishes.append(_yandex_dish(row, item, by_id))
        except _RowError as exc:
            errors.append(ShopMenuFileImportError(row=row, error_code=exc.error_code))
        except ValidationError:
            errors.append(ShopMenuFileImportError(row=row, error_code="shop_menu_file_row_invalid"))
    return ParsedMenuFile(dishes=dishes, errors=errors)


# --- XLSX ---

type _XlsxCell = (
    bool
    | int
    | float
    | Decimal
    | str
    | CellRichText
    | datetime
    | date
    | time
    | timedelta
    | DataTableFormula
    | ArrayFormula
    | None
)

type _Column = Literal[
    "name",
    "price",
    "section",
    "description",
    "measure",
    "measure_unit",
    "ingredients",
    "calories",
    "proteins",
    "fats",
    "carbs",
    "photo",
    "modifiers",
]

_COLUMN_SYNONYMS: dict[_Column, tuple[str, ...]] = {
    "name": ("название", "наименование", "название позиции", "название блюда", "блюдо", "name"),
    "price": ("цена", "цена, руб", "цена, ₽", "стоимость", "price"),
    "section": ("категория", "раздел", "группа", "category", "section"),
    "description": ("описание", "description"),
    "measure": ("вес", "выход", "вес/объём", "вес/объем", "объём", "объем", "вес, г", "weight", "measure"),
    "measure_unit": ("единица", "единица измерения", "ед. изм.", "ед.изм.", "unit", "measure unit"),
    "ingredients": ("состав", "ингредиенты", "ingredients"),
    "calories": ("ккал", "калории", "калорийность", "calories", "kcal"),
    "proteins": ("белки", "proteins"),
    "fats": ("жиры", "fats"),
    "carbs": ("углеводы", "carbohydrates", "carbs"),
    "photo": ("фото", "фотография", "изображение", "картинка", "photo", "image"),
    "modifiers": ("модификаторы", "добавки", "modifiers"),
}

_HEADER_COLUMN: dict[str, _Column] = {
    synonym: column for column, synonyms in _COLUMN_SYNONYMS.items() for synonym in synonyms
}

_MEASURE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Zа-яА-Я.]*)\s*$")
_OPTION_PRICE_RE = re.compile(r"^(.*?)\s*\+\s*(\d+(?:[.,]\d+)?)\s*(?:₽|руб\.?|р\.?)?\s*$")
_GROUP_HEAD_RE = re.compile(r"^(.*?)\s*(?:\[(\d+)\])?\s*$")
_PRICE_NOISE_RE = re.compile(r"[\s\u00a0₽]|руб\.?|р\.")


def _cell_text(value: _XlsxCell) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _cell_decimal(value: _XlsxCell, error_code: str) -> Decimal:
    if isinstance(value, bool):
        raise _RowError(error_code)
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    text = _PRICE_NOISE_RE.sub("", _cell_text(value)).replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise _RowError(error_code) from exc


def _xlsx_measure(measure: _XlsxCell, unit_cell: _XlsxCell) -> tuple[int | None, ShopMeasureUnit]:
    text = _cell_text(measure)
    unit_text = _cell_text(unit_cell)
    if text == "":
        return None, _unit(unit_text)[0] if unit_text else ShopMeasureUnit.G
    match = _MEASURE_RE.match(text)
    if match is None:
        raise _RowError("shop_menu_file_measure_invalid")
    token = match.group(2) or unit_text
    unit, factor = _unit(token) if token else (ShopMeasureUnit.G, 1)
    amount = Decimal(match.group(1).replace(",", ".")) * factor
    return int(amount.to_integral_value()), unit


def _xlsx_nutrition(
    calories: _XlsxCell, proteins: _XlsxCell, fats: _XlsxCell, carbs: _XlsxCell
) -> ShopNutrition | None:
    cells = (calories, proteins, fats, carbs)
    filled = [_cell_text(c) != "" for c in cells]
    if not any(filled):
        return None
    if not all(filled):
        raise _RowError("shop_menu_file_nutrition_incomplete")
    code = "shop_menu_file_nutrition_invalid"
    return ShopNutrition(
        calories_kcal=float(_cell_decimal(calories, code)),
        proteins_g=float(_cell_decimal(proteins, code)),
        fats_g=float(_cell_decimal(fats, code)),
        carbs_g=float(_cell_decimal(carbs, code)),
    )


def _xlsx_option(text: str) -> ParsedModifierOption:
    match = _OPTION_PRICE_RE.match(text)
    if match is None or match.group(1).strip() == "":
        return ParsedModifierOption(name=text, price_minor=0)
    price = Decimal(match.group(2).replace(",", "."))
    return ParsedModifierOption(
        name=match.group(1).strip(),
        price_minor=int((price * _MINOR_PER_UNIT).to_integral_value()),
    )


def _xlsx_modifier_groups(value: _XlsxCell) -> list[ParsedModifierGroup]:
    text = _cell_text(value)
    if text == "":
        return []
    groups: list[ParsedModifierGroup] = []
    for chunk in re.split(r"[|\n]", text):
        if chunk.strip() == "":
            continue
        head, sep, body = chunk.partition(":")
        if sep == "":
            raise _RowError("shop_menu_file_modifier_invalid")
        head_match = _GROUP_HEAD_RE.match(head.strip())
        if head_match is None or head_match.group(1) == "":
            raise _RowError("shop_menu_file_modifier_invalid")
        options = [_xlsx_option(o.strip()) for o in re.split(r"[;,]", body) if o.strip()]
        if not options:
            raise _RowError("shop_menu_file_modifier_invalid")
        limit = head_match.group(2)
        groups.append(
            ParsedModifierGroup(
                name=head_match.group(1),
                max_selected=int(limit) if limit is not None and int(limit) > 0 else None,
                options=options,
            )
        )
    return groups


def _header_columns(row: tuple[_XlsxCell, ...]) -> dict[_Column, int]:
    columns: dict[_Column, int] = {}
    for index, cell in enumerate(row):
        key = _cell_text(cell).lower().rstrip(":*").strip()
        if key in _HEADER_COLUMN and _HEADER_COLUMN[key] not in columns:
            columns[_HEADER_COLUMN[key]] = index
    return columns


def _xlsx_dish(row_number: int, row: tuple[_XlsxCell, ...], columns: dict[_Column, int]) -> ParsedDish:
    def cell(column: _Column) -> _XlsxCell:
        index = columns.get(column)
        if index is None or index >= len(row):
            return None
        return row[index]

    name = _cell_text(cell("name"))
    if name == "":
        raise _RowError("shop_menu_file_name_missing")
    if _cell_text(cell("price")) == "":
        raise _RowError("shop_menu_file_price_invalid")
    measure, unit = _xlsx_measure(cell("measure"), cell("measure_unit"))
    section = _cell_text(cell("section"))
    ingredients_text = _cell_text(cell("ingredients"))
    photo = _cell_text(cell("photo"))
    return ParsedDish(
        row=row_number,
        section_path=[part.strip() for part in section.split("/") if part.strip()],
        name=name,
        description=_cell_text(cell("description")),
        price_minor=_price_minor(_cell_decimal(cell("price"), "shop_menu_file_price_invalid")),
        measure=measure,
        measure_unit=unit,
        ingredients=[i.strip() for i in ingredients_text.split(",") if i.strip()],
        nutrition=_xlsx_nutrition(cell("calories"), cell("proteins"), cell("fats"), cell("carbs")),
        photo_url=photo if photo.startswith(("http://", "https://")) else None,
        modifier_groups=_xlsx_modifier_groups(cell("modifiers")),
    )


def parse_menu_xlsx(data: bytes) -> ParsedMenuFile:
    """Меню из первого листа; ``row`` — номер строки листа (1-based)."""
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (BadZipFile, OSError, ValueError, KeyError) as exc:
        raise _invalid_file("XLSX file cannot be read") from exc
    try:
        sheet = workbook.worksheets[0]
        rows: list[tuple[_XlsxCell, ...]] = [tuple(r) for r in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()
    header_index: int | None = None
    columns: dict[_Column, int] = {}
    for index, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        found = _header_columns(row)
        if "name" in found and "price" in found:
            header_index, columns = index, found
            break
    if header_index is None:
        raise _invalid_file("XLSX header with name and price columns not found")
    dishes: list[ParsedDish] = []
    errors: list[ShopMenuFileImportError] = []
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if all(_cell_text(c) == "" for c in row):
            continue
        try:
            dishes.append(_xlsx_dish(offset, row, columns))
        except _RowError as exc:
            errors.append(ShopMenuFileImportError(row=offset, error_code=exc.error_code))
        except ValidationError:
            errors.append(ShopMenuFileImportError(row=offset, error_code="shop_menu_file_row_invalid"))
    return ParsedMenuFile(dishes=dishes, errors=errors)
