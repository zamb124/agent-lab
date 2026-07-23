"""Unit tests for scripts/check_platform_events_canon gate honesty."""

from __future__ import annotations

from pathlib import Path

import scripts.check_platform_events_canon as gate


def test_local_command_reply_allows_succeeded_not_domain_updated() -> None:
    assert gate.LOCAL_COMMAND_REPLY_RE.search("crm/entity_card/succeeded")
    assert gate.LOCAL_COMMAND_REPLY_RE.search("crm/notes_list/loaded")
    assert gate.LOCAL_COMMAND_REPLY_RE.search("crm/note/updated") is None
    assert gate.LOCAL_COMMAND_REPLY_RE.search("sync/call/accepted") is None


def test_ui_factory_resource_path() -> None:
    assert gate._is_ui_factory_resource_path(
        "apps/crm/ui/events/resources/notes.resource.js"
    )
    assert gate._is_ui_factory_resource_path(
        "core/frontend/static/lib/events/resources/foo.resource.js"
    )
    assert not gate._is_ui_factory_resource_path("apps/crm/ui/pages/note-page.js")
    assert not gate._is_ui_factory_resource_path("apps/sync/realtime/events.py")


def test_handler_reaches_http_via_method_graph() -> None:
    text = """
    connectedCallback() {
        this.useEvent('crm/note/updated', (event) => {
            this._onNotePush(event);
        });
    }
    _onNotePush(event) {
        this._reloadCardOnly();
    }
    _reloadCardOnly() {
        this._cardOp.run({ entity_id: 'x' });
    }
    """
    bodies = gate._extract_method_bodies(text)
    handler = "(event) => { this._onNotePush(event); }"
    resolved = handler + "\n" + bodies["_onNotePush"]
    assert gate._handler_reaches_http(resolved, bodies) is True


def test_handler_ui_flags_only_no_http() -> None:
    text = """
    _patchFromPush(payload) {
        this._markdownFormatting = false;
        this.requestUpdate();
    }
    """
    bodies = gate._extract_method_bodies(text)
    handler = "(event) => { this._patchFromPush(event.payload); }"
    resolved = handler + "\n" + bodies["_patchFromPush"]
    assert gate._handler_reaches_http(resolved, bodies) is False


def test_collect_ui_factory_ignores_pages(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    page = root / "apps" / "crm" / "ui" / "pages" / "note-page.js"
    page.parent.mkdir(parents=True)
    page.write_text(
        "this.useEvent('crm/note/updated', () => {});",
        encoding="utf-8",
    )
    resource = root / "apps" / "crm" / "ui" / "events" / "resources" / "notes.resource.js"
    resource.parent.mkdir(parents=True)
    resource.write_text(
        "case 'crm/note/updated': return state;",
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "ROOT", root)
    files = [page, resource]
    consumed = gate._collect_ui_factory_consumed_types(files)
    assert "crm/note/updated" in consumed
    # page path alone would not be enough if only page existed
    page_only = gate._collect_ui_factory_consumed_types([page])
    assert "crm/note/updated" not in page_only
