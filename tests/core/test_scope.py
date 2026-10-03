from __future__ import annotations

import pytest

from core.config import get_settings
from core.logging import bind_log_context, unbind_log_context
from core.test_scope import (
    LOG_TEST_SCOPE,
    MOCK_LLM_SIDE_EFFECT_CRM_SUMMARY,
    MOCK_LLM_SIDE_EFFECT_NOTE_MARKDOWN,
    mock_llm_side_effect_enqueue_labels,
    resolve_test_scope,
    side_effect_test_scope,
)


def test_side_effect_test_scope_appends_kind() -> None:
    assert (
        side_effect_test_scope("test_deadbeef", MOCK_LLM_SIDE_EFFECT_CRM_SUMMARY)
        == "test_deadbeef:crm_summary"
    )
    assert (
        side_effect_test_scope("test_deadbeef", MOCK_LLM_SIDE_EFFECT_NOTE_MARKDOWN)
        == "test_deadbeef:note_markdown"
    )


def test_side_effect_test_scope_rejects_colon_in_kind() -> None:
    with pytest.raises(ValueError, match="must not contain"):
        _ = side_effect_test_scope("test_deadbeef", "crm:summary")


def test_mock_llm_side_effect_enqueue_labels_none_without_scope() -> None:
    settings = get_settings()
    previous = settings.test_scope_default
    settings.test_scope_default = ""
    unbind_log_context(LOG_TEST_SCOPE)
    try:
        assert mock_llm_side_effect_enqueue_labels(MOCK_LLM_SIDE_EFFECT_CRM_SUMMARY) is None
    finally:
        settings.test_scope_default = previous


def test_resolve_test_scope_uses_settings_default_without_log_context() -> None:
    settings = get_settings()
    previous = settings.test_scope_default
    settings.test_scope_default = " test_e2e_static "
    unbind_log_context(LOG_TEST_SCOPE)
    try:
        assert resolve_test_scope() == "test_e2e_static"
    finally:
        settings.test_scope_default = previous


def test_mock_llm_side_effect_enqueue_labels_overrides_parent_scope() -> None:
    bind_log_context(**{LOG_TEST_SCOPE: "test_deadbeef"})
    try:
        assert mock_llm_side_effect_enqueue_labels(MOCK_LLM_SIDE_EFFECT_CRM_SUMMARY) == {
            LOG_TEST_SCOPE: "test_deadbeef:crm_summary"
        }
    finally:
        unbind_log_context(LOG_TEST_SCOPE)
