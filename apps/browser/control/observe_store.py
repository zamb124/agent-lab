"""
In-memory снимки для шагового diff visibility между вызовами observe.
"""

from __future__ import annotations

from typing import Any


class ControlObserveStore:
    """
    In-memory память observe-состояния между шагами для каждой session.

    Связи:
    - Используется endpoint-ом `/control/sessions/{id}/observe`.
    - Хранит базу для diff visibility и проверки изменения HTML.

    Состояние:
    - `_last_visibility`: fingerprint узлов по `ref -> (role, name)`.
    - `_last_html_fingerprint`: последний sha256 HTML.

    Инварианты:
    - Первый diff после создания сессии возвращает `None`.
    - `diff_visibility` требует список `visibility.nodes`.
    - `forget` полностью очищает следы сессии.

    Мотивация:
    - Нужна дешёвая in-process память для step-by-step diff без внешнего хранилища.

    Переиспользование:
    - Стоит: для одиночного процесса runtime и быстрой диагностики observe-потока.
    - Не стоит: для межпроцессного шаринга состояния между инстансами.
    """

    def __init__(self) -> None:
        self._last_visibility: dict[str, dict[str, tuple[str, str]]] = {}
        self._last_html_fingerprint: dict[str, str] = {}
        self._last_refs: dict[str, dict[str, dict[str, object]]] = {}

    def forget(self, session_id: str) -> None:
        self._last_visibility.pop(session_id, None)
        self._last_html_fingerprint.pop(session_id, None)
        self._last_refs.pop(session_id, None)

    def update_html_fingerprint(self, session_id: str, fingerprint: str) -> None:
        self._last_html_fingerprint[session_id] = fingerprint

    def update_refs(self, session_id: str, refs: dict[str, dict[str, object]]) -> None:
        self._last_refs[session_id] = refs

    def get_refs(self, session_id: str) -> dict[str, dict[str, object]]:
        refs = self._last_refs.get(session_id)
        if refs is None:
            raise KeyError(f"Нет refs для session_id={session_id}")
        return refs

    def diff_visibility(self, session_id: str, visibility: dict[str, Any]) -> dict[str, Any] | None:
        """
        Сравнение ref -> (role, name) между текущим visibility и предыдущим observe.
        Первый вызов после создания сессии возвращает None (нет базы).
        """
        nodes = visibility.get("nodes")
        if not isinstance(nodes, list):
            raise ValueError("visibility.nodes должен быть list")
        current: dict[str, tuple[str, str]] = {}
        for n in nodes:
            if not isinstance(n, dict):
                continue
            ref = n.get("ref")
            if not isinstance(ref, str):
                continue
            role = n.get("role")
            name = n.get("name")
            current[ref] = (
                role if isinstance(role, str) else "",
                name if isinstance(name, str) else "",
            )
        prev = self._last_visibility.get(session_id)
        self._last_visibility[session_id] = current
        if prev is None:
            return None
        prev_keys = set(prev)
        cur_keys = set(current)
        added = sorted(cur_keys - prev_keys)
        removed = sorted(prev_keys - cur_keys)
        changed: list[dict[str, Any]] = []
        for k in sorted(prev_keys & cur_keys):
            if prev[k] != current[k]:
                changed.append(
                    {
                        "ref": k,
                        "before": {"role": prev[k][0], "name": prev[k][1]},
                        "after": {"role": current[k][0], "name": current[k][1]},
                    }
                )
        return {
            "added_refs": added,
            "removed_refs": removed,
            "changed": changed,
        }

    def html_changed(self, session_id: str, fingerprint: str) -> bool | None:
        """None если предыдущего отпечатка не было."""
        prev = self._last_html_fingerprint.get(session_id)
        self._last_html_fingerprint[session_id] = fingerprint
        if prev is None:
            return None
        return prev != fingerprint
