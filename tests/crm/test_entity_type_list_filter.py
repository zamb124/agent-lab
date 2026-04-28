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
        resolve_list_entity_query_pair("a", m)


def test_leaf_missing_from_map_raises() -> None:
    m = {"note": None}
    with pytest.raises(ValueError, match="not in parent map"):
        resolve_list_entity_query_pair("call", m)


def test_parent_missing_from_map_raises() -> None:
    m = {"call": "note", "note": None}
    # 'note' is in map; valid
    assert resolve_list_entity_query_pair("call", m) == ("note", "call")
