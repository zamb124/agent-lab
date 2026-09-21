"""
Профили имитации действий пользователя для Browser Control.

Зона ответственности:
- описать параметры "human-like" поведения (тайминги, mouse, typing delay);
- дать строгий способ выбрать профиль по имени без неявных фолбеков.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, assert_never

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

    # Post-navigate имитация "чтения" и прокрутки (crawl4ai-like).
    post_navigate_pause_ms_range: tuple[int, int]
    post_navigate_scroll_steps_range: tuple[int, int]
    post_navigate_scroll_px_per_step_range: tuple[int, int]
    post_navigate_pause_between_scroll_steps_ms_range: tuple[int, int]

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
            post_navigate_pause_ms_range=(0, 0),
            post_navigate_scroll_steps_range=(0, 0),
            post_navigate_scroll_px_per_step_range=(0, 0),
            post_navigate_pause_between_scroll_steps_ms_range=(0, 0),
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
            post_navigate_pause_ms_range=(120, 450),
            post_navigate_scroll_steps_range=(0, 2),
            post_navigate_scroll_px_per_step_range=(120, 280),
            post_navigate_pause_between_scroll_steps_ms_range=(120, 350),
        )
    if name == "human":
        return InteractionProfile(
            name="human",
            pre_action_mouse_moves=2,
            mouse_x_range=(80, 920),
            mouse_y_range=(80, 620),
            pause_before_action_ms_range=(120, 520),
            pause_after_action_ms_range=(150, 650),
            pause_after_focus_ms_range=(80, 260),
            typing_delay_ms_range=(15, 55),
            post_navigate_pause_ms_range=(900, 2600),
            post_navigate_scroll_steps_range=(1, 6),
            post_navigate_scroll_px_per_step_range=(120, 420),
            post_navigate_pause_between_scroll_steps_ms_range=(450, 1400),
        )
    assert_never(name)
