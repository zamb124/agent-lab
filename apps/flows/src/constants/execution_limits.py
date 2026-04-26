"""
Wall-clock потолки для run flow и нод: значения из FlowSettings (conf.json, services.flows).
"""

from __future__ import annotations


def get_flow_execution_wall_time_cap_seconds() -> int:
    from apps.flows.config import get_settings

    return get_settings().flow_execution_wall_time_cap_seconds


def get_node_execution_wall_time_cap_seconds() -> int:
    from apps.flows.config import get_settings

    return get_settings().node_execution_wall_time_cap_seconds
