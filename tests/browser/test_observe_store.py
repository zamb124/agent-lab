"""ControlObserveStore: refs и interaction nonce."""

from __future__ import annotations

import pytest

from apps.browser.observe.observe_store import ControlObserveStore
from apps.browser.observe.snapshot_refs import RefMap


def test_get_refs_raises_without_observe() -> None:
    store = ControlObserveStore()
    with pytest.raises(KeyError):
        store.get_refs("s1")


def test_refs_saved_and_cleared_with_forget() -> None:
    store = ControlObserveStore()
    store.set_interaction_config("s1", profile="human", seed=101)
    refs: RefMap = {"0": {"role": "combobox", "name": "Search", "nth": 0}}

    store.update_refs("s1", refs)
    assert store.get_refs("s1") == refs

    store.forget("s1")
    with pytest.raises(KeyError):
        store.get_refs("s1")
