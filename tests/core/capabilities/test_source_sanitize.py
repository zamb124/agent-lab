"""Source sanitizer hard-rejects platform imports."""

from __future__ import annotations

import pytest

from core.capabilities.source_sanitize import reject_forbidden_platform_imports


def test_reject_forbidden_platform_imports_allows_clean_source() -> None:
    code = "async def run(args, state):\n    return {'ok': True}\n"
    assert reject_forbidden_platform_imports(code) == code


def test_reject_forbidden_platform_imports_raises_with_lines() -> None:
    code = (
        "from apps.flows.src.runtime.nodes import NodeConstructor\n"
        "import core.context\n"
        "async def run(args, state):\n"
        "    return {}\n"
    )
    with pytest.raises(ValueError, match="Forbidden lines") as exc_info:
        _ = reject_forbidden_platform_imports(code)
    message = str(exc_info.value)
    assert "1: from apps.flows.src.runtime.nodes import NodeConstructor" in message
    assert "2: import core.context" in message
