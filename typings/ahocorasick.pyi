"""Typed surface used by pyahocorasick integrations."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, TypeVar

_T = TypeVar("_T")

AHOCORASICK: int
EMPTY: int
KEY_SEQUENCE: int
KEY_STRING: int
MATCH_AT_LEAST_PREFIX: int
MATCH_AT_MOST_PREFIX: int
MATCH_EXACT_LENGTH: int
STORE_ANY: int
STORE_INTS: int
STORE_LENGTH: int
TRIE: int


class Automaton(Generic[_T]):
    def __init__(self, value_type: int = ..., key_type: int = ...) -> None: ...

    def add_word(self, word: str, value: _T) -> bool: ...

    def make_automaton(self) -> None: ...

    def iter(self, string: str, start: int = ..., end: int = ...) -> Iterator[tuple[int, _T]]: ...
