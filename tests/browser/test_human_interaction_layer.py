import random

import pytest

from apps.browser.interaction.human_interaction import HumanInteraction, InteractionRng
from apps.browser.interaction.interaction_profiles import get_interaction_profile
from apps.browser.observe.observe_store import ControlObserveStore


class _FakeMouse:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self._calls = calls

    async def move(self, x: int, y: int) -> None:
        self._calls.append(("mouse.move", (x, y)))

    async def wheel(self, dx: int, dy: int) -> None:
        self._calls.append(("mouse.wheel", (dx, dy)))


class _FakeKeyboard:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self._calls = calls

    async def press(self, key: str) -> None:
        self._calls.append(("keyboard.press", key))


class _FakePage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.mouse = _FakeMouse(self.calls)
        self.keyboard = _FakeKeyboard(self.calls)

    async def wait_for_timeout(self, ms: int) -> None:
        self.calls.append(("wait_for_timeout", ms))


class _FakeLocator:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self._calls = calls

    async def scroll_into_view_if_needed(self) -> None:
        self._calls.append(("locator.scroll", None))

    async def evaluate(self, expr: str) -> None:
        self._calls.append(("locator.evaluate", expr))

    async def click(self, *, timeout: int, force: bool = False) -> None:
        self._calls.append(("locator.click", {"timeout": timeout, "force": force}))

    async def fill(self, text: str, *, timeout: int) -> None:
        self._calls.append(("locator.fill", {"text": text, "timeout": timeout}))

    async def type(self, text: str, *, delay: int, timeout: int) -> None:
        self._calls.append(("locator.type", {"text": text, "delay": delay}))


@pytest.mark.asyncio
async def test_human_interaction_off_uses_fill() -> None:
    page = _FakePage()
    loc = _FakeLocator(page.calls)
    inter = HumanInteraction()
    profile = get_interaction_profile("off")
    rnd = InteractionRng(random.Random(0))

    await inter.type_text(page, loc, "hello", profile=profile, rnd=rnd, timeout_ms=5_000)

    assert ("locator.fill", {"text": "hello", "timeout": 5_000}) in page.calls
    assert not any(c[0] == "locator.type" for c in page.calls)


@pytest.mark.asyncio
async def test_human_interaction_human_types_with_delay_and_signals() -> None:
    page = _FakePage()
    loc = _FakeLocator(page.calls)
    inter = HumanInteraction()
    profile = get_interaction_profile("human")
    rnd = InteractionRng(random.Random(1))

    await inter.type_text(page, loc, "playwright", profile=profile, rnd=rnd, timeout_ms=5_000)

    # Профиль human должен сохранять type с delay в диапазоне профиля.
    assert not any(c[0] == "mouse.wheel" for c in page.calls)
    typed = [c for c in page.calls if c[0] == "locator.type"]
    assert len(typed) == 1
    delay = typed[0][1]["delay"]
    assert profile.typing_delay_ms_range[0] <= delay <= profile.typing_delay_ms_range[1]


def test_observe_store_interaction_nonce_increments() -> None:
    store = ControlObserveStore()
    store.set_interaction_config("sess-1", profile="human", seed=123)

    seed1, step1 = store.next_interaction_nonce("sess-1")
    seed2, step2 = store.next_interaction_nonce("sess-1")

    assert seed1 == 123
    assert seed2 == 123
    assert step1 == 0
    assert step2 == 1


def test_observe_store_refs_roundtrip_and_forget() -> None:
    store = ControlObserveStore()
    store.set_interaction_config("sess-2", profile="human", seed=321)
    refs = {"1": {"role": "combobox", "name": "Search", "nth": 0}}

    store.update_refs("sess-2", refs)
    assert store.get_refs("sess-2") == refs

    store.forget("sess-2")
    with pytest.raises(KeyError):
        store.get_refs("sess-2")

