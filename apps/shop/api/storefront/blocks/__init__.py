"""Реестр блоков витрины — сборка css/js shell из модулей `blocks/*`.

Shell — каркас (`<head>`, тема, DOM-скелет, точки монтажа); контент —
именованные блоки, каждый владеет своим CSS и JS и редактируется
независимо. Порядок реестра — порядок сборки: `base` первым (состояние
и токены), `boot` последним (инициализация).

Мерчант-кастомизация — ``theme.custom`` (`custom_injections`), слоты:

- ``custom_head``   — в ``<head>``: метрики, шрифты;
- ``custom_css``    — в конец ``<style>``, после всех блоков;
- ``custom_top``    — ``<div class="wrap">`` перед каталогом;
- ``custom_bottom`` — после каталога;
- ``custom_js``     — в конец основного ``<script>``, видит глобалы
  блоков (S, cart, esc, ic).

``theme.custom.blocks`` — карта ``slot → html``. Статические слоты
``top``/``bottom`` монтирует сервер в DOM shell; якоря внутри витрины
``<anchor>:before``/``<anchor>:after`` (``hero``, ``meta``, ``catalog``)
монтирует клиентский ``slot()`` (``blocks/ui.py``) — карта едет
в snapshot как есть. Неизвестные имена резервируются под
переопределение отдельных блоков в редакторе витрины.
"""

from apps.shop.api.storefront.blocks import (
    base,
    boot,
    cart,
    catalog,
    checkout,
    hero,
    product,
    responsive,
    sheets,
    tracking,
    ui,
)
from core.types import JsonObject

# Порядок сборки — порядок имён: состояние → хелперы → каталог → корзина →
# чекаут → трекинг → товар → шиты → инициализация. account — отдельный
# tail-блок (account_tail в shell). Имена — ключи для редактора витрины.
STOREFRONT_BLOCKS = (
    "base",
    "hero",
    "catalog",
    "cart",
    "sheets",
    "product",
    "checkout",
    "tracking",
    "responsive",
    "ui",
    "boot",
    "account",
)

_BLOCK_CSS: tuple[str, ...] = (
    base.CSS,
    hero.CSS,
    catalog.CSS,
    cart.CSS,
    sheets.CSS,
    product.CSS,
    checkout.CSS,
    tracking.CSS,
    responsive.CSS,
)

_BLOCK_JS: tuple[str, ...] = (
    base.JS,
    ui.JS,
    catalog.JS,
    cart.JS,
    checkout.JS,
    tracking.JS,
    product.JS,
    sheets.JS,
    boot.JS,
)


def page_css() -> str:
    """CSS всех блоков реестра — одной секцией после токенов темы."""
    return "\n".join(_BLOCK_CSS)


def page_js() -> str:
    """JS всех блоков реестра — одним <script>, в порядке реестра."""
    return "\n".join(_BLOCK_JS)


_BLOCK_SLOT_IDS = ("top", "bottom")

_CUSTOM_SLOT_NAMES = ("custom_head", "custom_css", "custom_top", "custom_bottom", "custom_js")


def custom_injections(snapshot: JsonObject) -> dict[str, str]:
    """Собрать мерчант-инъекции ``theme.custom`` для слотов shell.

    Пустая тема → пустые слоты, страница не меняется. Сервер монтирует
    только ``top``/``bottom``; якоря ``<name>:before``/``<name>:after``
    доезжают до клиента в snapshot и монтируются ``slot()`` в точках
    рендера блоков.
    """
    slots = {name: "" for name in _CUSTOM_SLOT_NAMES}
    theme = snapshot.get("theme")
    custom = theme.get("custom") if isinstance(theme, dict) else None
    if not isinstance(custom, dict):
        return slots
    for src, dst in (
        ("head_html", "custom_head"),
        ("css", "custom_css"),
        ("js", "custom_js"),
    ):
        value = custom.get(src)
        if isinstance(value, str):
            slots[dst] = value
    blocks = custom.get("blocks")
    if isinstance(blocks, dict):
        for slot_id in _BLOCK_SLOT_IDS:
            value = blocks.get(slot_id)
            if isinstance(value, str) and value.strip():
                # пустой слот не рендерится: пустой .wrap дал бы мёртвый отступ
                slots[f"custom_{slot_id}"] = (
                    f'<div class="wrap" id="custom-{slot_id}">{value}</div>'
                )
    return slots
