"""Окружение дочернего процесса: копия окружения родителя и точечные замены."""

from __future__ import annotations

import os
from collections.abc import Mapping


def child_process_env(updates: Mapping[str, str] | None = None) -> dict[str, str]:
    """Копия окружения текущего процесса. ``updates`` перекрывают одноимённые ключи."""
    env = dict(os.environ)
    if updates is not None:
        env.update(dict(updates))
    return env


def pod_name_env() -> str | None:
    """``HOSTNAME`` окружения процесса — имя пода в Kubernetes/test-стеке; None, если не задан."""
    return os.environ.get("HOSTNAME")


__all__ = ["child_process_env", "pod_name_env"]
