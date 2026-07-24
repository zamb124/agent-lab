"""
Проверки для входящих HTTP webhooks (generic) до исполнения триггера.
"""

import ipaddress
import time
from collections import deque

from starlette.requests import Request

from core.types import JsonObject, JsonValue, parse_json_object

_webhook_hits: dict[tuple[str, str, str], deque[float]] = {}

DEFAULT_WEBHOOK_SECRET_HEADER = "X-Trigger-Secret"


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
        _ = q.popleft()
    if len(q) >= max_per_minute:
        return False
    q.append(now)
    return True


def client_ip_allowed(client_host: str, allowed: JsonValue) -> bool:
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


def webhook_secret_from_request(request: Request, secret_header: str) -> str | None:
    """Секрет из настроенного заголовка, иначе query ?secret=."""
    header_name = secret_header.strip()
    if not header_name:
        raise ValueError("secret_header is required")
    header_value = request.headers.get(header_name)
    if header_value is not None and str(header_value).strip() != "":
        return str(header_value)
    query_secret = request.query_params.get("secret")
    if query_secret is not None and str(query_secret).strip() != "":
        return str(query_secret)
    return None


def build_webhook_trigger_payload(request: Request, body: JsonObject) -> JsonObject:
    """Envelope для InputMapper: body / headers / query."""
    headers: JsonObject = {
        str(name): str(value) for name, value in request.headers.items()
    }
    query: JsonObject = {key: value for key, value in request.query_params.items()}
    return {
        "body": body,
        "headers": headers,
        "query": query,
    }


async def parse_webhook_json_body(request: Request) -> JsonObject:
    """JSON object из тела запроса."""
    return parse_json_object(await request.body(), "Webhook payload")


__all__ = [
    "DEFAULT_WEBHOOK_SECRET_HEADER",
    "build_webhook_trigger_payload",
    "check_webhook_rate_limit",
    "client_ip_allowed",
    "parse_webhook_json_body",
    "webhook_secret_from_request",
]
