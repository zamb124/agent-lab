"""
Wall-clock потолки для run flow и нод: значения из FlowSettings (conf.json, services.flows).
"""

from __future__ import annotations

from apps.flows.config import get_settings
from core.config.testing import is_testing

_REMOTE_CODE_RUNNER_HTTP_TIMEOUT_TESTING_SECONDS = 60


def get_graph_max_iterations() -> int:
    return get_settings().graph_max_iterations


def get_flow_execution_wall_time_cap_seconds() -> int:
    return get_settings().flow_execution_wall_time_cap_seconds


def get_node_execution_wall_time_cap_seconds() -> int:
    return get_settings().node_execution_wall_time_cap_seconds


def get_remote_code_runner_http_timeout_seconds() -> float:
    cap_seconds = get_node_execution_wall_time_cap_seconds()
    if is_testing():
        return float(min(cap_seconds, _REMOTE_CODE_RUNNER_HTTP_TIMEOUT_TESTING_SECONDS))
    return float(cap_seconds)
