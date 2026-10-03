"""Чистый парсер GS1-128 / DataMatrix штрихкодов (без IO).

Префиксы символики `]C1` (GS1-128), `]d2` (DataMatrix), `]Q3` (QR).
Разделитель групп — FNC1 (в строках приходит как GS `\\x1d`).
AI: `00` SSCC-18, `01`/`02` GTIN-14, `10` партия, `11`/`15`/`17` даты,
`21` серийный номер (КМ «Честного знака» — пара 01+21), `30`/`37`
количество, `310x` вес нетто в кг с `x` знаками после запятой.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

_GS = "\x1d"
_SYMBOL_PREFIXES = ("]C1", "]d2", "]Q3", "]e0", "]J1")

# AI → (имя поля Gs1Barcode, фиксированная длина; 0 — переменная до FNC1/конца)
_FIXED_AI: dict[str, tuple[str, int]] = {
    "00": ("sscc", 18),
    "01": ("gtin", 14),
    "02": ("gtin", 14),
    "11": ("production_date", 6),
    "15": ("best_before_date", 6),
    "17": ("expiration_date", 6),
}
_VARIABLE_AI: dict[str, str] = {
    "10": "lot_name",
    "21": "serial",
    "30": "quantity",
    "37": "quantity",
    "91": "company_internal_91",
    "92": "company_internal_92",
    "93": "company_internal_93",
    "94": "company_internal_94",
    "95": "company_internal_95",
    "96": "company_internal_96",
    "97": "company_internal_97",
    "98": "company_internal_98",
    "99": "company_internal_99",
}
# Вес нетто: 310n — n знаков после запятой (n=0..5).
_WEIGHT_AI_PREFIX = "310"


@dataclass(frozen=True)
class Gs1Barcode:
    """Разобранный GS1-код: типизированные поля + сырая карта AI."""

    raw: str
    sscc: str | None = None
    gtin: str | None = None
    lot_name: str | None = None
    serial: str | None = None
    quantity: Decimal | None = None
    weight_kg: Decimal | None = None
    production_date: date | None = None
    best_before_date: date | None = None
    expiration_date: date | None = None
    ais: dict[str, str] = field(default_factory=dict)

    @property
    def is_gs1(self) -> bool:
        return bool(self.ais)


def _parse_date(yyMMdd: str) -> date | None:
    """AI-даты: YYMMDD, DD=00 — последний день месяца."""
    if len(yyMMdd) != 6 or not yyMMdd.isdigit():
        return None
    year = 2000 + int(yyMMdd[0:2])
    month = int(yyMMdd[2:4])
    day = int(yyMMdd[4:6])
    if not 1 <= month <= 12:
        return None
    if day == 0:
        day = 31 if month in {1, 3, 5, 7, 8, 10, 12} else 30
        if month == 2:
            day = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _to_decimal(raw: str) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def strip_symbology_prefix(code: str) -> str:
    """Снять префикс символики сканера (`]C1` и прочие), если он есть."""
    for prefix in _SYMBOL_PREFIXES:
        if code.startswith(prefix):
            return code[len(prefix):]
    return code


def parse_gs1(code: str) -> Gs1Barcode:
    """Разобрать строку скана в `Gs1Barcode`; без AI — `is_gs1 == False`.

    Не бросает: неполные или мусорные хвосты просто обрывают разбор —
    извлечённое остаётся доступным.
    """
    raw = code.strip()
    body = strip_symbology_prefix(raw)
    ais: dict[str, str] = {}
    fields: dict[str, object] = {}
    pos = 0
    length = len(body)
    while pos < length:
        if body[pos] == _GS:
            pos += 1
            continue
        matched = False
        for ai, (field_name, fixed_len) in _FIXED_AI.items():
            if body.startswith(ai, pos):
                value = body[pos + len(ai) : pos + len(ai) + fixed_len]
                if len(value) < fixed_len or not value.isdigit():
                    matched = True
                    pos = length
                    break
                ais[ai] = value
                fields[field_name] = value
                pos += len(ai) + fixed_len
                matched = True
                break
        if matched:
            continue
        if body.startswith(_WEIGHT_AI_PREFIX, pos):
            ai = body[pos : pos + 4]
            value = body[pos + 4 : pos + 10]
            if len(value) == 6 and value.isdigit():
                ais[ai] = value
                decimals = int(ai[3])
                fields["weight_kg"] = Decimal(value).scaleb(-decimals)
                pos += 10
                continue
        var = next(
            (ai for ai in _VARIABLE_AI if body.startswith(ai, pos)), None
        )
        if var is None:
            break
        end = body.find(_GS, pos + len(var))
        value = body[pos + len(var) : end if end != -1 else length]
        if not value:
            break
        ais[var] = value
        fields[_VARIABLE_AI[var]] = value
        pos = end if end != -1 else length
    quantity = _to_decimal(str(fields["quantity"])) if "quantity" in fields else None
    sscc = fields.get("sscc")
    gtin = fields.get("gtin")
    lot_name = fields.get("lot_name")
    serial = fields.get("serial")
    weight = fields.get("weight_kg")
    return Gs1Barcode(
        raw=raw,
        sscc=sscc if isinstance(sscc, str) else None,
        gtin=gtin if isinstance(gtin, str) else None,
        lot_name=lot_name if isinstance(lot_name, str) else None,
        serial=serial if isinstance(serial, str) else None,
        quantity=quantity,
        weight_kg=weight if isinstance(weight, Decimal) else None,
        production_date=_parse_date(ais["11"]) if "11" in ais else None,
        best_before_date=_parse_date(ais["15"]) if "15" in ais else None,
        expiration_date=_parse_date(ais["17"]) if "17" in ais else None,
        ais=ais,
    )
