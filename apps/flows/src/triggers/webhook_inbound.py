"""
Проверки для входящих HTTP webhooks (generic) до исполнения триггера.
"""

import ipaddress
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple

_webhook_hits: Dict[Tuple[str, str, str], Deque[float]] = {}


def check_webhook_rate_limit(
    flow_id: str,
    trigger_id: str,
    client_ip: str,
    *,
    max_per_minute: int = 120,
    window_seconds: float = 60.0,
) -> bool:
    """True если запрос в пределах лимита, False если слишком часто (429)."""
    key = (flow_id, trigger_id, client_ip)
    now = time.monotonic()
    q = _webhook_hits.setdefault(key, deque())
    while q and q[0] < now - window_seconds:
        q.popleft()
    if len(q) >= max_per_minute:
        return False
    q.append(now)
    return True


def client_ip_allowed(client_host: str, allowed: Any) -> bool:
    """
    allowed: строка с IP/CIDR через запятую, список строк, или пусто = без ограничения.
    """
    if not allowed:
        return True
    if isinstance(allowed, str):
        parts = [p.strip() for p in allowed.split(",") if p.strip()]
    elif isinstance(allowed, list):
        parts = [str(p).strip() for p in allowed if str(p).strip()]
    else:
        return True
    if not parts:
        return True
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    for rule in parts:
        try:
            if "/" in rule:
                net = ipaddress.ip_network(rule, strict=False)
                if client_ip in net:
                    return True
            else:
                if client_ip == ipaddress.ip_address(rule):
                    return True
        except ValueError:
            continue
    return False


__all__ = [
    "check_webhook_rate_limit",
    "client_ip_allowed",
]
