"""In-memory состояние control-сессии для refs и interaction nonce."""

from __future__ import annotations

import hashlib

from apps.browser.interaction.interaction_profiles import InteractionProfileName


class ControlObserveStore:
    """
    In-memory память control-состояния между шагами для каждой session.

    Связи:
    - Используется endpoint-ами `/control/sessions/{id}/observe|click|fill|press`.
    - Хранит refs последнего observe и параметры interaction nonce.

    Инварианты:
    - `forget` полностью очищает следы сессии.
    - `next_interaction_nonce` инкрементирует step монотонно.
    """

    def __init__(self) -> None:
        self._last_refs: dict[str, dict[str, dict[str, object]]] = {}
        self._interaction_profile: dict[str, InteractionProfileName] = {}
        self._interaction_seed: dict[str, int] = {}
        self._interaction_step: dict[str, int] = {}

    def forget(self, session_id: str) -> None:
        self._last_refs.pop(session_id, None)
        self._interaction_profile.pop(session_id, None)
        self._interaction_seed.pop(session_id, None)
        self._interaction_step.pop(session_id, None)

    @staticmethod
    def _seed_from_session_id(session_id: str) -> int:
        if not session_id:
            raise ValueError("session_id обязателен")
        raw = hashlib.sha256(session_id.encode("utf-8")).digest()
        return int.from_bytes(raw[:8], "big", signed=False)

    def set_interaction_config(
        self,
        session_id: str,
        *,
        profile: InteractionProfileName,
        seed: int | None,
    ) -> None:
        if not session_id:
            raise ValueError("session_id обязателен")
        if not profile:
            raise ValueError("profile обязателен")
        self._interaction_profile[session_id] = profile
        self._interaction_seed[session_id] = seed if seed is not None else self._seed_from_session_id(session_id)
        self._interaction_step[session_id] = 0

    def get_interaction_profile(self, session_id: str) -> InteractionProfileName:
        p = self._interaction_profile.get(session_id)
        if p is None:
            raise KeyError(f"Нет interaction_profile для session_id={session_id}")
        return p

    def next_interaction_nonce(self, session_id: str) -> tuple[int, int]:
        """
        Вернуть (seed, step) для детерминированного RNG и инкрементировать step.
        """
        if session_id not in self._interaction_seed:
            raise KeyError(f"Нет interaction_seed для session_id={session_id}")
        seed = self._interaction_seed[session_id]
        step = self._interaction_step.get(session_id)
        if step is None:
            raise KeyError(f"Нет interaction_step для session_id={session_id}")
        self._interaction_step[session_id] = step + 1
        return seed, step

    def update_refs(self, session_id: str, refs: dict[str, dict[str, object]]) -> None:
        self._last_refs[session_id] = refs

    def clear_refs(self, session_id: str) -> None:
        self._last_refs.pop(session_id, None)

    def get_refs(self, session_id: str) -> dict[str, dict[str, object]]:
        refs = self._last_refs.get(session_id)
        if refs is None:
            raise KeyError(f"Нет refs для session_id={session_id}")
        return refs
