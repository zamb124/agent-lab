"""Legacy browser action не исполняет произвольный код в процессе."""

import pytest

from apps.browser.adapters.playwright_control_adapter import PlaywrightAdapter
from apps.browser.contracts.control_types import BrowserCapabilityError


@pytest.mark.asyncio
async def test_browser_action_disabled() -> None:
    adapter = PlaywrightAdapter(interactor=object())  # pyright: ignore[reportArgumentType]

    with pytest.raises(BrowserCapabilityError, match="Arbitrary in-process browser actions are disabled"):
        await adapter.run_action(page=object(), code="print(1)", timeout_ms=1000)  # pyright: ignore[reportArgumentType]
