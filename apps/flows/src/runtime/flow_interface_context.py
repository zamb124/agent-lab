"""ContextVar с design-time интерфейсом flow, который сейчас исполняется.

Интерфейс нужен только для проверки целей ui-событий (slot_id / page_id) в tools
``ui_render``/``ui_navigate`` и в effects sandbox-кода. В state он не хранится:
``Flow`` открывает scope на время исполнения графа.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from core.ui_document.document import FlowUIDocument

_FLOW_INTERFACE: ContextVar[FlowUIDocument | None] = ContextVar(
    "flows_current_flow_interface",
    default=None,
)


def current_flow_interface() -> FlowUIDocument:
    interface = _FLOW_INTERFACE.get()
    if interface is None:
        raise RuntimeError("flow interface is not available outside Flow execution")
    return interface


@contextmanager
def flow_interface_scope(interface: FlowUIDocument) -> Generator[None, None, None]:
    token = _FLOW_INTERFACE.set(interface)
    try:
        yield
    finally:
        _FLOW_INTERFACE.reset(token)


__all__ = ["current_flow_interface", "flow_interface_scope"]
