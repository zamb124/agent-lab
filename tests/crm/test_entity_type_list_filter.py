"""Unit-тесты resolve_list_entity_query_pair (пара фильтра списка сущностей)."""

import pytest

from apps.crm.entity_type_list_filter import resolve_list_entity_query_pair


def test_note_root() -> None:
    m = {"note": None, "call": "note", "meeting": "note"}
    assert resolve_list_entity_query_pair("note", m) == ("note", None)


def test_call_under_note() -> None:
    m = {"note": None, "call": "note", "meeting": "note"}
    assert resolve_list_entity_query_pair("call", m) == ("note", "call")


def test_company_and_subcompany() -> None:
    m = {"company": None, "subCompany": "company", "note": None}
    assert resolve_list_entity_query_pair("company", m) == ("company", None)
    assert resolve_list_entity_query_pair("subCompany", m) == ("subCompany", None)


def test_deep_non_note_chain() -> None:
    m = {"a": None, "b": "a", "c": "b"}
    assert resolve_list_entity_query_pair("c", m) == ("c", None)


def test_cycle_raises() -> None:
    m = {"a": "b", "b": "a"}
    with pytest.raises(ValueError, match="cycle"):
        _ = resolve_list_entity_query_pair("a", m)


def test_leaf_missing_from_map_raises() -> None:
    m = {"note": None}
    with pytest.raises(ValueError, match="not in parent map"):
        _ = resolve_list_entity_query_pair("call", m)


def test_call_under_note_when_root_row_present() -> None:
    m = {"call": "note", "note": None}
    assert resolve_list_entity_query_pair("call", m) == ("note", "call")


def test_implicit_note_root_when_row_missing_from_map() -> None:
    m = {"call": "note", "meeting": "note"}
    assert resolve_list_entity_query_pair("call", m) == ("note", "call")


def test_implicit_task_root_when_row_missing_from_map() -> None:
    m = {"subtask_under_task": "task"}
    assert resolve_list_entity_query_pair("subtask_under_task", m) == ("task", "subtask_under_task")


def test_task_root_leaf() -> None:
    m = {"task": None}
    assert resolve_list_entity_query_pair("task", m) == ("task", None)


def test_task_child_when_task_row_present() -> None:
    m = {"ticket": "task", "task": None}
    assert resolve_list_entity_query_pair("ticket", m) == ("task", "ticket")
