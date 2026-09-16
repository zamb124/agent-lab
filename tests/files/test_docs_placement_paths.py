"""DocsPlacement path matrix + auto-placement registry."""

from __future__ import annotations

import pytest

from core.context import clear_context, set_context
from core.documents.placement import DocsPlacementAnchor
from core.documents.placement_paths import build_path_segments
from core.files.create_spec import FileSourceKind, FileSourceRef
from core.files.registry import (
    DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS,
    SOURCE_KIND_TO_DOCS_PLACEMENT,
    default_docs_placement,
    is_docs_placement_exempt,
)
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus


def test_all_file_source_kinds_have_placement_policy() -> None:
    for kind in FileSourceKind:
        if kind in DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS:
            assert kind not in SOURCE_KIND_TO_DOCS_PLACEMENT
            assert is_docs_placement_exempt(kind)
            continue
        assert kind in SOURCE_KIND_TO_DOCS_PLACEMENT


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        (
            DocsPlacementAnchor(
                source_kind="mail_message",
                mailbox_email="user@example.com",
                mail_subject="Hello World",
                mail_uid="42",
            ),
            ["Mail", "user@example.com", "hello-world"],
        ),
        (
            DocsPlacementAnchor(
                source_kind="mail_message",
                mailbox_email="user@example.com",
                mail_uid="99",
            ),
            ["Mail", "user@example.com", "99"],
        ),
        (
            DocsPlacementAnchor(source_kind="sync_message", channel_id="ch1"),
            ["Sync", "ch1"],
        ),
        (
            DocsPlacementAnchor(source_kind="sync_channel_asset", channel_id="ch1"),
            ["Sync", "ch1", "assets"],
        ),
        (
            DocsPlacementAnchor(source_kind="sync_call_recording", call_id="call1"),
            ["Sync", "calls", "call1"],
        ),
        (
            DocsPlacementAnchor(
                source_kind="flow_session",
                flow_id="my_flow",
                session_id="sess1",
            ),
            ["Flows", "my-flow", "sess1"],
        ),
        (
            DocsPlacementAnchor(source_kind="flow_asset", flow_id="my_flow"),
            ["Flows", "my-flow"],
        ),
        (
            DocsPlacementAnchor(
                source_kind="crm_entity",
                entity_type="person",
                entity_id="e1",
                entity_title="Ada Lovelace",
            ),
            ["Networkle", "person", "ada-lovelace"],
        ),
        (
            DocsPlacementAnchor(source_kind="work_item", work_item_id="wi1"),
            ["Worktracker", "queues", "boards", "wi1"],
        ),
        (
            DocsPlacementAnchor(
                source_kind="work_item",
                work_item_id="wi1",
                work_queue_id="q1",
                board_id="b1",
            ),
            ["Worktracker", "q1", "b1", "wi1"],
        ),
        (
            DocsPlacementAnchor(source_kind="calendar_event", event_id="ev1"),
            ["Calendar", "ev1"],
        ),
        (
            DocsPlacementAnchor(
                source_kind="browser_artifact",
                browser_session_id="bs1",
            ),
            ["Browser", "bs1"],
        ),
        (
            DocsPlacementAnchor(source_kind="rag_document", namespace_id="ns1"),
            ["RAG", "ns1"],
        ),
        (
            DocsPlacementAnchor(
                source_kind="wiki_page",
                namespace_id="knowledge",
                wiki_page_id="page-1",
            ),
            ["Wiki", "knowledge", "page-1"],
        ),
        (
            DocsPlacementAnchor(
                source_kind="code_agent_source",
                flow_id="my_flow",
                node_id="n1",
            ),
            ["Flows", "my-flow", "code_agent", "n1"],
        ),
        (
            DocsPlacementAnchor(
                source_kind="code_agent_source",
                flow_id="my_flow",
                node_id="n1",
                relative_dir="src/lib",
            ),
            ["Flows", "my-flow", "code_agent", "n1", "src", "lib"],
        ),
    ],
)
def test_build_path_segments(anchor: DocsPlacementAnchor, expected: list[str]) -> None:
    assert build_path_segments(anchor) == expected


def test_default_docs_placement_exempt_returns_none() -> None:
    assert (
        default_docs_placement(
            FileSourceKind.PLATFORM_AUXILIARY,
            FileSourceRef(),
            title="x",
        )
        is None
    )


def test_default_docs_placement_uses_context_namespace() -> None:
    user = User(
        user_id="u1",
        name="U",
        status=UserStatus.ACTIVE,
        companies={"c1": ["member"]},
        active_company_id="c1",
    )
    company = Company(company_id="c1", name="C", subdomain="c1", owner_user_id="u1")
    set_context(
        Context(
            user=user,
            host="localhost",
            active_company=company,
            user_companies=[company],
            active_namespace="docs-ns",
        )
    )
    try:
        placement = default_docs_placement(
            FileSourceKind.SYNC_MESSAGE,
            FileSourceRef(channel_id="ch-a"),
            title="attach.pdf",
        )
        assert placement is not None
        assert placement.namespace == "docs-ns"
        assert placement.anchor is not None
        assert placement.anchor.source_kind == "sync_message"
        assert build_path_segments(placement.anchor) == ["Sync", "ch-a"]
    finally:
        clear_context()
