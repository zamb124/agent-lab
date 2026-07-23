"""Matcher триггера platform_event: фильтры по payload и детерминизм run id."""

from __future__ import annotations

import pytest

from apps.flows.src.models import EventFilter, PlatformEventTriggerConfig
from apps.flows.src.triggers.handlers.platform_event import (
    platform_event_matches_filters,
    platform_event_trigger_index_key,
    platform_event_trigger_index_member,
    platform_event_trigger_run_id,
)


def _config(filters: list[EventFilter]) -> PlatformEventTriggerConfig:
    return PlatformEventTriggerConfig(
        event_type="crm/entity/created",
        filters=filters,
    )


def test_no_filters_matches_everything() -> None:
    assert platform_event_matches_filters(_config([]), {"anything": 1}) is True
    assert platform_event_matches_filters(_config([]), None) is True


def test_eq_filter_on_dot_path() -> None:
    config = _config([EventFilter(path="entity_type", op="eq", value="task")])
    assert platform_event_matches_filters(config, {"entity_type": "task"}) is True
    assert platform_event_matches_filters(config, {"entity_type": "note"}) is False
    # отсутствующий путь != значение
    assert platform_event_matches_filters(config, {}) is False


def test_nested_path_and_ne() -> None:
    config = _config(
        [
            EventFilter(path="work_item.kind", op="eq", value="crm_activity"),
            EventFilter(path="work_item.state", op="ne", value="done"),
        ]
    )
    payload = {"work_item": {"kind": "crm_activity", "state": "open"}}
    assert platform_event_matches_filters(config, payload) is True
    payload_done = {"work_item": {"kind": "crm_activity", "state": "done"}}
    assert platform_event_matches_filters(config, payload_done) is False


def test_contains_on_string_and_list() -> None:
    config_str = _config([EventFilter(path="name", op="contains", value="lead")])
    assert platform_event_matches_filters(config_str, {"name": "hot lead #1"}) is True
    assert platform_event_matches_filters(config_str, {"name": "customer"}) is False

    config_list = _config([EventFilter(path="tags", op="contains", value="vip")])
    assert platform_event_matches_filters(config_list, {"tags": ["vip", "b2b"]}) is True
    assert platform_event_matches_filters(config_list, {"tags": ["b2b"]}) is False
    # contains на скаляре не-строке — не матчится
    assert platform_event_matches_filters(config_list, {"tags": 5}) is False


def test_event_type_validated() -> None:
    with pytest.raises(ValueError):
        _ = PlatformEventTriggerConfig(event_type="not-an-event", filters=[])


def test_run_id_deterministic_for_idempotency() -> None:
    run_a = platform_event_trigger_run_id("e_1", "trg_1")
    run_b = platform_event_trigger_run_id("e_1", "trg_1")
    run_other = platform_event_trigger_run_id("e_2", "trg_1")
    assert run_a == run_b
    assert run_a != run_other


def test_index_key_and_member_roundtrip() -> None:
    from apps.flows.src.triggers.handlers.platform_event import (
        parse_platform_event_trigger_index_member,
    )

    assert (
        platform_event_trigger_index_key("crm/entity/created")
        == "flows:event_triggers:crm/entity/created"
    )
    member = platform_event_trigger_index_member(
        company_id="c1", flow_id="f1", trigger_id="t1"
    )
    assert parse_platform_event_trigger_index_member(member) == ("c1", "f1", "t1")
    assert parse_platform_event_trigger_index_member("broken") is None
