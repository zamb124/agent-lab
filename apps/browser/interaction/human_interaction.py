"""
Human-like слой действий для Browser Control.

Зона ответственности:
- имитировать "пользовательские" сигналы (mouse move / паузы);
- обеспечивать "человеческий" ввод (type-by-char с delay);
- НЕ хранить состояние сессии; state (profile/seed) хранится внешним store.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from apps.browser.engine.types import BrowserLocator, BrowserPage
from apps.browser.interaction.interaction_profiles import InteractionProfile


@dataclass(frozen=True)
class InteractionRng:
    rng: random.Random

    def randint_range(self, bounds: tuple[int, int]) -> int:
        lo, hi = bounds
        if lo > hi:
            raise ValueError("Некорректный диапазон")
        if lo == hi:
            return lo
        return self.rng.randint(lo, hi)


class HumanInteraction:
    """
    Stateless исполнитель действий, параметризованный профилем и RNG.
    """

    @staticmethod
    async def _ensure_in_viewport(locator: BrowserLocator) -> None:
        """
        Довести элемент до viewport перед кликом/вводом.

        Причина:
        - Playwright может успешно завершить `scroll_into_view_if_needed()`, но всё равно
          считать элемент "outside of the viewport" (особенно на страницах со сложной
          раскладкой и sticky-элементами).
        """
        await locator.scroll_into_view_if_needed()
        # Центрируем элемент в viewport, чтобы стабилизировать hit target.
        await locator.evaluate(
            "(el) => el.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'})"
        )

    @staticmethod
    async def _pause_ms(page: BrowserPage, ms: int) -> None:
        if ms <= 0:
            return
        # Playwright: page.wait_for_timeout(ms)
        await page.wait_for_timeout(ms)

    async def pre_action_signals(
        self,
        page: BrowserPage,
        *,
        profile: InteractionProfile,
        rnd: InteractionRng,
    ) -> None:
        if profile.name == "off":
            return

        await self._pause_ms(page, rnd.randint_range(profile.pause_before_action_ms_range))

        # Mouse moves (без кликов по координатам).
        for _ in range(profile.pre_action_mouse_moves):
            x = rnd.randint_range(profile.mouse_x_range)
            y = rnd.randint_range(profile.mouse_y_range)
            await page.mouse.move(x, y)

    async def click(
        self,
        page: BrowserPage,
        locator: BrowserLocator,
        *,
        profile: InteractionProfile,
        rnd: InteractionRng,
        timeout_ms: int,
    ) -> None:
        if profile.name != "off":
            await self.pre_action_signals(page, profile=profile, rnd=rnd)
        await self._ensure_in_viewport(locator)
        try:
            await locator.click(timeout=timeout_ms)
        except PlaywrightTimeoutError:
            # Playwright может оставаться в состоянии "outside of the viewport" даже после scrollIntoView.
            # В этом случае разрешаем форсированный клик как last resort для целевых контролов (input/button).
            await locator.click(timeout=timeout_ms, force=True)
        if profile.name != "off":
            await self._pause_ms(page, rnd.randint_range(profile.pause_after_action_ms_range))

    async def type_text(
        self,
        page: BrowserPage,
        locator: BrowserLocator,
        text: str,
        *,
        profile: InteractionProfile,
        rnd: InteractionRng,
        timeout_ms: int,
        typing_delay_ms: int | None = None,
    ) -> None:
        if text == "":
            raise ValueError("text должен быть непустой строкой")
        if typing_delay_ms is not None and typing_delay_ms < 0:
            raise ValueError("typing_delay_ms должен быть >= 0")
        if profile.name == "off":
            # Быстрый путь: программное заполнение.
            if typing_delay_ms is None:
                await locator.fill(text, timeout=timeout_ms)
                return
            await self._ensure_in_viewport(locator)
            await locator.fill("", timeout=timeout_ms)
            await locator.type(text, delay=typing_delay_ms, timeout=timeout_ms)
            return

        await self.pre_action_signals(page, profile=profile, rnd=rnd)
        await self._ensure_in_viewport(locator)
        try:
            await locator.click(timeout=timeout_ms)
        except PlaywrightTimeoutError:
            # Если клик не проходит (viewport), фокусируем элемент и используем fill+type.
            await locator.evaluate("(el) => el.focus()")
            await locator.fill("", timeout=timeout_ms)
        await self._pause_ms(page, rnd.randint_range(profile.pause_after_focus_ms_range))

        delay = typing_delay_ms if typing_delay_ms is not None else rnd.randint_range(profile.typing_delay_ms_range)
        # Playwright: locator.type(text, delay=ms)
        await locator.type(text, delay=delay, timeout=timeout_ms)
        await self._pause_ms(page, rnd.randint_range(profile.pause_after_action_ms_range))

    async def press(self, page: BrowserPage, key: str, *, profile: InteractionProfile, rnd: InteractionRng) -> None:
        if not key:
            raise ValueError("key обязателен")
        if profile.name != "off":
            await self.pre_action_signals(page, profile=profile, rnd=rnd)
        await page.keyboard.press(key)
        if profile.name != "off":
            await self._pause_ms(page, rnd.randint_range(profile.pause_after_action_ms_range))

    async def post_navigate_signals(self, page: BrowserPage, *, profile: InteractionProfile, rnd: InteractionRng) -> None:
        """
        Имитация "чтения" и лёгкой прокрутки после navigate.

        Используется как best-effort поведенческий шум (crawl4ai-like) и не должен
        ломать контрольный поток выполнения: только простые actions и паузы.
        """
        if profile.name == "off":
            return

        await self._pause_ms(page, rnd.randint_range(profile.post_navigate_pause_ms_range))

        steps = rnd.randint_range(profile.post_navigate_scroll_steps_range)
        for _ in range(steps):
            dx = rnd.randint_range((-2, 2))
            dy = rnd.randint_range(profile.post_navigate_scroll_px_per_step_range)
            # Playwright: page.mouse.wheel(delta_x, delta_y)
            await page.mouse.wheel(dx, dy)
            await self._pause_ms(
                page,
                rnd.randint_range(profile.post_navigate_pause_between_scroll_steps_ms_range),
            )
