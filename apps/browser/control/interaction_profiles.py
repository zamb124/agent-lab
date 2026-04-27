"""
Профили имитации действий пользователя для Browser Control.

Зона ответственности:
- описать параметры "human-like" поведения (тайминги, mouse, typing delay);
- дать строгий способ выбрать профиль по имени без неявных фолбеков.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InteractionProfileName = Literal["off", "fast", "human"]


@dataclass(frozen=True)
class InteractionProfile:
    name: InteractionProfileName

    # Движения мыши перед действием: количество move() и диапазон координат.
    pre_action_mouse_moves: int
    mouse_x_range: tuple[int, int]
    mouse_y_range: tuple[int, int]

    # Паузы (в миллисекундах).
    pause_before_action_ms_range: tuple[int, int]
    pause_after_action_ms_range: tuple[int, int]
    pause_after_focus_ms_range: tuple[int, int]

    # Набор текста: задержка между символами.
    typing_delay_ms_range: tuple[int, int]

def get_interaction_profile(name: InteractionProfileName) -> InteractionProfile:
    if name == "off":
        return InteractionProfile(
            name="off",
            pre_action_mouse_moves=0,
            mouse_x_range=(0, 0),
            mouse_y_range=(0, 0),
            pause_before_action_ms_range=(0, 0),
            pause_after_action_ms_range=(0, 0),
            pause_after_focus_ms_range=(0, 0),
            typing_delay_ms_range=(0, 0),
        )
    if name == "fast":
        return InteractionProfile(
            name="fast",
            pre_action_mouse_moves=1,
            mouse_x_range=(120, 520),
            mouse_y_range=(140, 420),
            pause_before_action_ms_range=(15, 45),
            pause_after_action_ms_range=(20, 65),
            pause_after_focus_ms_range=(10, 35),
            typing_delay_ms_range=(8, 20),
        )
    if name == "human":
        return InteractionProfile(
            name="human",
            pre_action_mouse_moves=0,
            mouse_x_range=(0, 0),
            mouse_y_range=(0, 0),
            pause_before_action_ms_range=(0, 15),
            pause_after_action_ms_range=(0, 20),
            pause_after_focus_ms_range=(0, 10),
            typing_delay_ms_range=(3, 9),
        )
    raise ValueError(f"Неизвестный interaction profile: {name!r}")

