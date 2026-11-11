"""Пути источников в дереве Документов любой глубины."""

from __future__ import annotations

import pytest

from core.documents.paths import source_catalog_path
from core.files.create_spec import FileSourceKind, FileSourceRef
from core.files.registry import (
    DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS,
    PLACED_SOURCE_KINDS,
    is_docs_placement_exempt,
)


def test_every_source_kind_is_placed_or_exempt() -> None:
    for kind in FileSourceKind:
        assert (kind in DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS) != (kind in PLACED_SOURCE_KINDS)
        assert is_docs_placement_exempt(kind) is (kind in DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS)


@pytest.mark.parametrize(
    ("kind", "source_ref", "expected"),
    [
        (
            FileSourceKind.MAIL_MESSAGE,
            FileSourceRef(mailbox_email="user@example.com", mail_subject="Hello World", mail_uid="42"),
            ["Mail", "user@example.com", "hello-world"],
        ),
        (
            FileSourceKind.MAIL_MESSAGE,
            FileSourceRef(mailbox_email="user@example.com", mail_uid="99"),
            ["Mail", "user@example.com", "99"],
        ),
        (
            FileSourceKind.SYNC_MESSAGE,
            FileSourceRef(channel_id="ch1"),
            ["Sync", "ch1"],
        ),
        (
            FileSourceKind.SYNC_CHANNEL_ASSET,
            FileSourceRef(channel_id="ch1"),
            ["Sync", "ch1", "assets"],
        ),
        (
            FileSourceKind.SYNC_CALL_RECORDING,
            FileSourceRef(channel_id="ch1", call_id="call1"),
            ["Sync", "ch1", "calls", "call1"],
        ),
        (
            FileSourceKind.SYNC_SPEECH_SEGMENT,
            FileSourceRef(channel_id="ch1", call_id="call1"),
            ["Sync", "ch1", "calls", "call1", "speech"],
        ),
        (
            FileSourceKind.FLOW_SESSION,
            FileSourceRef(flow_id="my_flow", session_id="sess1"),
            ["Flows", "my-flow", "sess1"],
        ),
        (
            FileSourceKind.FLOW_ASSET,
            FileSourceRef(flow_id="my_flow"),
            ["Flows", "my-flow"],
        ),
        (
            FileSourceKind.CRM_ENTITY,
            FileSourceRef(entity_type="person", entity_id="e1", entity_title="Ada Lovelace"),
            ["Networkle", "person", "ada-lovelace"],
        ),
        (
            FileSourceKind.WORK_ITEM,
            FileSourceRef(work_item_id="wi1"),
            ["Worktracker", "queues", "boards", "wi1"],
        ),
        (
            FileSourceKind.WORK_ITEM,
            FileSourceRef(work_item_id="wi1", work_queue_id="q1", board_id="b1"),
            ["Worktracker", "q1", "b1", "wi1"],
        ),
        (
            FileSourceKind.CALENDAR_EVENT,
            FileSourceRef(event_id="ev1"),
            ["Calendar", "ev1"],
        ),
        (
            FileSourceKind.BROWSER_ARTIFACT,
            FileSourceRef(browser_session_id="bs1"),
            ["Browser", "bs1"],
        ),
        (
            FileSourceKind.RAG_DOCUMENT,
            FileSourceRef(namespace_id="ns1"),
            ["RAG", "ns1"],
        ),
        (
            FileSourceKind.WIKI_PAGE,
            FileSourceRef(namespace_id="knowledge", wiki_page_id="page-1"),
            ["Wiki", "knowledge", "page-1"],
        ),
        (
            FileSourceKind.PRODUCT,
            FileSourceRef(shop_id="shop_1"),
            ["Shop", "shop_1"],
        ),
        (
            FileSourceKind.PRODUCT,
            FileSourceRef(shop_id="shop_1", product_id="prd_1"),
            ["Products", "prd_1"],
        ),
        (
            FileSourceKind.CODE_AGENT_SOURCE,
            FileSourceRef(flow_id="my_flow", node_id="n1"),
            ["Flows", "my-flow", "code_agent", "n1"],
        ),
        (
            FileSourceKind.CODE_AGENT_SOURCE,
            FileSourceRef(flow_id="my_flow", node_id="n1", relative_dir="src/lib"),
            ["Flows", "my-flow", "code_agent", "n1", "src", "lib"],
        ),
    ],
)
def test_source_catalog_path(kind: FileSourceKind, source_ref: FileSourceRef, expected: list[str]) -> None:
    assert source_catalog_path(kind, source_ref) == expected
