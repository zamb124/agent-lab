"""
Shared color palette for CRM entity types.

Палитра цветов для типов сущностей.
Используется при создании типов и при backfill для типов без цвета.
Синхронизирована с core/frontend/static/lib/utils/color-palette.js.
"""

ENTITY_COLOR_PALETTE = [
    "#a2affb",
    "#34c38f",
    "#4ea8ff",
    "#8f7bff",
    "#f5b14c",
    "#ef6f98",
    "#8f96a3",
    "#607D8B",
    "#FF9800",
    "#D32F2F",
    "#1976D2",
    "#7E57C2",
    "#00897B",
    "#EF6C00",
]


def assign_color_from_palette(used_colors: set[str]) -> str:
    """Назначает первый свободный цвет из палитры, либо первый если все заняты."""
    normalized_used = {color.strip().lower() for color in used_colors}
    for palette_color in ENTITY_COLOR_PALETTE:
        if palette_color.lower() not in normalized_used:
            return palette_color
    return ENTITY_COLOR_PALETTE[0]
