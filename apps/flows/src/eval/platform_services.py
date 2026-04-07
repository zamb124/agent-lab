"""
Узкие точки входа к сервисам платформы для inline-кода и платформенных тулов.

Контейнер целиком в namespace не передаётся: только явно перечисленные сервисы.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.flows.src.services.operator_handoff_service import OperatorHandoffService
    from apps.flows.src.services.schedule_service import ScheduleService


def get_operator_handoff_service() -> "OperatorHandoffService":
    from apps.flows.src.container import get_container

    return get_container().operator_handoff_service


def get_schedule_service() -> "ScheduleService":
    from apps.flows.src.container import get_container

    return get_container().schedule_service
