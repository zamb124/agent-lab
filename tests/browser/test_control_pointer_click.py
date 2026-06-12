from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi import HTTPException

from apps.browser.api import control
from apps.browser.contracts.control_types import ControlPointerClickBody, ControlPointerTextBody


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests() -> Iterator[None]:
    yield


class _FakeMouse:
    def __init__(self) -> None:
        self.clicks: list[dict[str, object]] = []

    async def click(self, x: float, y: float, *, button: str, click_count: int) -> None:
        self.clicks.append(
            {
                "x": x,
                "y": y,
                "button": button,
                "click_count": click_count,
            }
        )


class _FakeKeyboard:
    def __init__(self) -> None:
        self.typed: list[str] = []

    async def type(self, text: str) -> None:
        self.typed.append(text)


class _FakePage:
    def __init__(self) -> None:
        self.url = "https://example.test/page"
        self.viewport_size = {"width": 1000, "height": 500}
        self.mouse = _FakeMouse()
        self.keyboard = _FakeKeyboard()

    async def evaluate(self, expression: str) -> object:
        raise AssertionError(f"viewport_size should be used before evaluate: {expression}")


class _FakeLeaseManager:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    def session_navigate_exclusive(self, session_id: str) -> object:
        raise AssertionError(f"pointer click must not wait for navigate lock: {session_id}")

    async def get_page_for_session(self, session_id: str) -> _FakePage:
        assert session_id == "sess-1"
        return self._page


class _HumanTakeoverLeaseManager:
    async def human_takeover_for_session(self, session_id: str) -> SimpleNamespace:
        assert session_id == "sess-1"
        return SimpleNamespace(owner="flows.browser_preview")

    def session_navigate_exclusive(self, session_id: str) -> object:
        raise AssertionError(f"agent control must fail before navigate lock: {session_id}")


@pytest.mark.asyncio
async def test_control_pointer_click_bypasses_navigate_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _FakePage()
    container = SimpleNamespace(
        browser_runtime=SimpleNamespace(
            lease_manager=_FakeLeaseManager(page),
        )
    )
    monkeypatch.setattr(control, "_write_session_event", lambda **kwargs: Path("event.json"))
    monkeypatch.setattr(control, "_write_console_sidecars", lambda **kwargs: None)

    result = await control.control_pointer_click(
        "sess-1",
        ControlPointerClickBody(
            x=640,
            y=360,
            image_width=1280,
            image_height=720,
            button="left",
            click_count=1,
        ),
        container,  # pyright: ignore[reportArgumentType]
    )

    assert result == {
        "ok": True,
        "x": 500.0,
        "y": 250.0,
        "viewport_width": 1000.0,
        "viewport_height": 500.0,
        "url": "https://example.test/page",
    }
    assert page.mouse.clicks == [
        {
            "x": 500.0,
            "y": 250.0,
            "button": "left",
            "click_count": 1,
        }
    ]


@pytest.mark.asyncio
async def test_control_pointer_text_bypasses_navigate_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _FakePage()
    container = SimpleNamespace(
        browser_runtime=SimpleNamespace(
            lease_manager=_FakeLeaseManager(page),
        )
    )
    monkeypatch.setattr(control, "_write_session_event", lambda **kwargs: Path("event.json"))
    monkeypatch.setattr(control, "_write_console_sidecars", lambda **kwargs: None)

    result = await control.control_pointer_text(
        "sess-1",
        ControlPointerTextBody(text="captcha-123"),
        container,  # pyright: ignore[reportArgumentType]
    )

    assert result == {"ok": True}
    assert page.keyboard.typed == ["captcha-123"]


@pytest.mark.asyncio
async def test_control_click_times_out_during_human_takeover(monkeypatch: pytest.MonkeyPatch) -> None:
    container = SimpleNamespace(
        browser_runtime=SimpleNamespace(
            lease_manager=_HumanTakeoverLeaseManager(),
        )
    )
    monkeypatch.setattr(control, "AGENT_CONTROL_TAKEOVER_WAIT_SEC", 0.0)

    with pytest.raises(HTTPException) as exc_info:
        await control.control_click(
            "sess-1",
            control.ControlClickBody(ref="@e1"),
            container,  # pyright: ignore[reportArgumentType]
        )

    assert exc_info.value.status_code == 423
    assert "under human control" in str(exc_info.value.detail)
