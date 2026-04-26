"""ControlObserveStore: diff visibility refs."""

from __future__ import annotations

from apps.browser.control.observe_store import ControlObserveStore


def test_diff_visibility_first_call_returns_none() -> None:
    st = ControlObserveStore()
    vis = {
        "schema": "browser.control.visibility.v1",
        "nodes": [
            {"ref": "0", "role": "button", "name": "A"},
        ],
    }
    assert st.diff_visibility("s1", vis) is None
    d2 = st.diff_visibility(
        "s1",
        {
            "nodes": [
                {"ref": "0", "role": "button", "name": "B"},
                {"ref": "1", "role": "link", "name": "C"},
            ],
        },
    )
    assert d2 is not None
    assert "1" in d2["added_refs"]
    assert len(d2["changed"]) >= 1
