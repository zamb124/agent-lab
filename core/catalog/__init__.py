"""Единый каталог товаров платформы (core/catalog).

Мастер-карточка товара компании + наследуемые overlay'ы сервисов.
Таблицы живут в ``platform_shared``; читать модели может любой
процесс (алиас ``shared`` открыт всегда), запись — только через
``CatalogService`` из op_* сервисов-владельцев фасетов (stock, shop).
"""

from core.catalog.service import CatalogService

__all__ = ["CatalogService"]
