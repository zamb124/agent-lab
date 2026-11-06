"""Блочная композиция витрины.

Shell собирается из именованных блоков (hero, каталог, корзина, чекаут,
трекинг, кабинет). Мерчант расширяет витрину через ``theme.custom`` —
аналог Shopify Custom Liquid: код владельца магазина в его же витрине,
поэтому рендерится без санитизации (тот же trust-уровень, что и
``accent_color``/``preset``).

Точки монтажа (слоты):

- ``custom_head``   — в ``<head>`` после SEO/PWA-тегов: метрики, шрифты;
- ``custom_css``    — в конец ``<style>``: переопределения темы;
- ``custom_top``    — ``<div class="wrap">`` перед каталогом;
- ``custom_bottom`` — ``<div class="wrap">`` после каталога;
- ``custom_js``     — в конец основного ``<script>``: обработчики и
  интеграции, видят глобалы shell (S, cart, esc, ic).

``theme.custom.blocks`` — карта ``slot → html``: ключи ``top``/``bottom``
монтируются в DOM-слоты; остальные имена резервируются под внутренние
слоты блоков (появятся вместе с визуальным редактором блоков).
"""

from core.types import JsonObject

_BLOCK_SLOT_IDS = ("top", "bottom")

_CUSTOM_SLOT_NAMES = ("custom_head", "custom_css", "custom_top", "custom_bottom", "custom_js")

_BLOCK_DOC = """Блоки shell по порядку монтажа — единая карта для редактора:

| Блок            | Регион                         | Владеет |
|-----------------|--------------------------------|---------|
| seo/pwa         | <head> метаданные              | shell   |
| theme           | <style> токены + layout        | shell   |
| custom_top      | wrap перед каталогом           | мерчант |
| catalog         | #app: hero, меню, карточки     | shell   |
| custom_bottom   | wrap после каталога            | мерчант |
| cart_sheet      | #sheet: корзина и чекаут       | shell   |
| product_sheet   | #csheet: карточка модификаторов| shell   |
| tracking        | done-панель статуса заказа     | shell   |
| account         | кабинет покупателя (account.py)| shell   |
| custom_js       | конец <script>                 | мерчант |
"""

__all__ = ["_BLOCK_DOC", "custom_injections"]


def custom_injections(snapshot: JsonObject) -> dict[str, str]:
    """Собрать мерчант-инъекции ``theme.custom`` для слотов shell.

    Пустая тема → пустые слоты, страница не меняется. Ключи blocks
    вне ``top``/``bottom`` игнорируются — их монтаж определит редактор
    блоков, а не произвольный HTML в неизвестной точке DOM.
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
            if isinstance(value, str):
                slots[f"custom_{slot_id}"] = value
    return slots
