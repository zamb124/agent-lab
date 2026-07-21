"""UI E2E perf-collector (always-on для tests/ui/e2e)."""

from tests.ui.perf.collector import (
    UiPerfCollector,
    get_current_collector,
    reset_current_collector,
    set_current_collector,
)

__all__ = [
    "UiPerfCollector",
    "get_current_collector",
    "reset_current_collector",
    "set_current_collector",
]
