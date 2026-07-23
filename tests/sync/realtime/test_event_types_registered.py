"""Все sync EventType зарегистрированы в каталоге platform events."""

from __future__ import annotations

from typing import get_args

import apps.sync.realtime.events as sync_events
from apps.sync.realtime.events import EventType
from core.events import is_registered_platform_event

_ = sync_events


def test_all_sync_event_types_are_registered() -> None:
    for event_type in get_args(EventType):
        assert is_registered_platform_event(event_type), event_type
