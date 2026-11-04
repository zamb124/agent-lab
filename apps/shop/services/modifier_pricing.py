"""Валидация выбора модификаторов и расчёт цены позиции.

Чистые функции без DI — единый алгоритм для заказа и preview корзины:

- ``load_modifier_tree_by_sort_asc`` — батч-загрузка дерева групп/опций продуктов,
  включая вложенные группы (option.nested_group_id), с лимитом глубины.
- ``validate_and_price`` — проверяет выбор (min/max, single, max_per_option,
  доступность, вложенность) и возвращает цену единицы + снапшот для кухни.

Цены считает только сервер: клиент присылает ``option_id`` + ``qty``.
``price_mode='absolute'`` — опция замещает базовую цену товара (варианты);
``delta`` — прибавляет к итогу. Несколько absolute-групп суммируются.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.shop.models.api import ShopOrderItemSelection
from apps.shop.models.enums import ModifierPriceMode, ModifierSelectionMode
from apps.shop.models.modifier_group import ShopModifierGroup
from apps.shop.models.modifier_option import ShopModifierOption
from apps.shop.models.product_modifier_group import ShopProductModifierGroup
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError

MAX_NESTED_DEPTH = 5


@dataclass
class AttachedGroup:
    """Группа, прикреплённая к товару, с опциями и overrides лимитов."""

    group: ShopModifierGroup
    options: list[ShopModifierOption]
    min_selected: int
    max_selected: int | None


async def load_modifier_tree_by_sort_asc(
    product_ids: list[str],
) -> dict[str, list[AttachedGroup]]:
    """Дерево модификаторов для набора товаров: прямые + nested-группы.

    Возвращает ``product_id -> [AttachedGroup]``. Nested-группы попадают
    в специальный ключ ``"__nested__"`` — используются при проверке
    вложенных выборов рекурсивно.
    """
    links = await ShopProductModifierGroup.list_by_products(product_ids)
    direct_group_ids = {link.group_id for link in links}
    nested_groups: dict[str, AttachedGroup] = {}
    # Транзитивно подгружаем прямые и nested-группы с лимитом глубины.
    known: set[str] = set(direct_group_ids)
    queue = list(direct_group_ids)
    groups_by_id: dict[str, ShopModifierGroup] = {}
    options_by_group: dict[str, list[ShopModifierOption]] = {}
    depth = 0
    while queue and depth < MAX_NESTED_DEPTH:
        depth += 1
        rows = await ShopModifierGroup.objects.filter(shop_modifier_group_id__in=queue).all()
        for g in rows:
            groups_by_id[g.shop_modifier_group_id] = g
        opts = await ShopModifierOption.objects.filter(group_id__in=queue).all()
        next_queue: list[str] = []
        for o in opts:
            options_by_group.setdefault(o.group_id, []).append(o)
            if o.nested_group_id and o.nested_group_id not in known:
                known.add(o.nested_group_id)
                next_queue.append(o.nested_group_id)
        queue = next_queue
    for gid, g in groups_by_id.items():
        if gid not in direct_group_ids:
            nested_groups[gid] = AttachedGroup(
                group=g,
                options=sorted(options_by_group.get(gid, []), key=lambda o: o.sort),
                min_selected=g.min_selected,
                max_selected=g.max_selected,
            )
    result: dict[str, list[AttachedGroup]] = {"__nested__": list(nested_groups.values())}
    for link in links:
        g = groups_by_id.get(link.group_id)
        if g is None or not g.is_active:
            continue
        attached = AttachedGroup(
            group=g,
            options=sorted(
                options_by_group.get(g.shop_modifier_group_id, []), key=lambda o: o.sort
            ),
            min_selected=link.min_selected if link.min_selected is not None else g.min_selected,
            max_selected=link.max_selected if link.max_selected is not None else g.max_selected,
        )
        result.setdefault(link.product_id, []).append(attached)
    sort_map = {link.group_id: link.sort for link in links}
    for attached_list in result.values():
        attached_list.sort(key=lambda a: sort_map.get(a.group.shop_modifier_group_id, 0))
    return result


def nested_lookup(nested: list[AttachedGroup]) -> dict[str, AttachedGroup]:
    return {a.group.shop_modifier_group_id: a for a in nested}


def _validate_group(
    ag: AttachedGroup,
    picked: dict[str, int],
    snapshot: list[dict[str, object]],
    sums: dict[str, int],
) -> None:
    """Лимиты группы + начисление цены выбранных опций в ``sums``."""
    selected_qty = 0
    distinct = 0
    for opt in ag.options:
        qty = picked.get(opt.shop_modifier_option_id, 0)
        if qty == 0:
            continue
        if not opt.is_available:
            raise PlatformConflictError(
                f"Option {opt.name} is unavailable",
                error_code="modifier_unavailable",
            )
        if qty > opt.max_per_option:
            raise PlatformConflictError(
                f"Option {opt.name} exceeds per-option limit",
                error_code="modifiers_invalid",
            )
        selected_qty += qty
        distinct += 1
        if ag.group.price_mode == ModifierPriceMode.ABSOLUTE:
            sums["absolute"] += opt.price_minor * qty
        else:
            sums["delta"] += opt.price_minor * qty
        snapshot.append(
            {
                "group_name": ag.group.name,
                "option_name": opt.name,
                "price_minor": opt.price_minor,
                "qty": qty,
            }
        )
    if ag.group.selection_mode == ModifierSelectionMode.SINGLE and (
        distinct > 1 or selected_qty > 1
    ):
        raise PlatformConflictError(
            f"Group {ag.group.name} allows a single option",
            error_code="modifiers_invalid",
        )
    if selected_qty < ag.min_selected:
        raise PlatformConflictError(
            f"Group {ag.group.name} requires at least {ag.min_selected} option(s)",
            error_code="modifier_required",
        )
    if ag.max_selected is not None and selected_qty > ag.max_selected:
        raise PlatformConflictError(
            f"Group {ag.group.name} allows at most {ag.max_selected}",
            error_code="modifiers_invalid",
        )


def validate_and_price(
    base_price_minor: int,
    selections: list[ShopOrderItemSelection],
    attached: list[AttachedGroup],
    nested: dict[str, AttachedGroup],
    *,
    _depth: int = 0,
) -> tuple[int, list[dict[str, object]]]:
    """Проверяет выбор и возвращает (unit_price_minor, modifiers_snapshot).

    ``base_price_minor`` — итоговая цена позиции меню без модификаторов.
    ``unit_price`` — итог за единицу с модификаторами. Снапшот —
    список ``{group_name, option_name, price_minor, qty}`` для кухни/чека.
    """
    if _depth > MAX_NESTED_DEPTH:
        raise PlatformConflictError(
            "Modifier selection is too deep", error_code="modifiers_invalid"
        )
    by_option: dict[str, tuple[AttachedGroup, ShopModifierOption]] = {}
    for ag in attached:
        for opt in ag.options:
            by_option[opt.shop_modifier_option_id] = (ag, opt)
    nested_by_option: dict[str, tuple[AttachedGroup, ShopModifierOption]] = {}
    for nag in nested.values():
        for opt in nag.options:
            nested_by_option[opt.shop_modifier_option_id] = (nag, opt)
    unknown = [
        s.option_id
        for s in selections
        if s.option_id not in by_option and s.option_id not in nested_by_option
    ]
    if unknown:
        raise PlatformNotFoundError("Modifier option not found", error_code="modifier_not_found")
    picked: dict[str, int] = {}
    for s in selections:
        picked[s.option_id] = picked.get(s.option_id, 0) + s.qty
    snapshot: list[dict[str, object]] = []
    sums = {"absolute": 0, "delta": 0}
    activated: set[str] = set()
    for ag in attached:
        _validate_group(ag, picked, snapshot, sums)
        for opt in ag.options:
            if (
                opt.nested_group_id
                and picked.get(opt.shop_modifier_option_id, 0) > 0
                and opt.nested_group_id in nested
            ):
                activated.add(opt.nested_group_id)
    nested_selected = [oid for oid in picked if oid in nested_by_option]
    for oid in nested_selected:
        nag = nested_by_option[oid][0]
        if nag.group.shop_modifier_group_id not in activated:
            raise PlatformConflictError(
                "Nested modifier requires its parent option",
                error_code="modifiers_invalid",
            )
    for gid in activated:
        _validate_group(nested[gid], picked, snapshot, sums)
    base = sums["absolute"] if sums["absolute"] else base_price_minor
    return base + sums["delta"], snapshot


def min_price_minor(base_price_minor: int, attached: list[AttachedGroup]) -> int:
    """Минимальная валидная цена «от N ₽» для карточки на витрине."""
    absolute_min: list[int] = []
    delta_min = 0
    for ag in attached:
        if ag.min_selected == 0:
            continue
        available = sorted(o.price_minor for o in ag.options if o.is_available)
        if not available:
            continue
        if ag.group.price_mode == ModifierPriceMode.ABSOLUTE:
            absolute_min.append(available[0] * ag.min_selected)
        else:
            delta_min += sum(available[: ag.min_selected])
    base = sum(absolute_min) if absolute_min else base_price_minor
    return base + delta_min
