"""Small guards for anonymous public embed-session issuance."""

from __future__ import annotations

import hashlib
import uuid

from fastapi import HTTPException, Request

from core.clients.redis_client import RedisClient
from core.logging import get_logger

logger = get_logger(__name__)

PUBLIC_SESSION_RATE_LIMIT_REDIS_PREFIX = "public_embed_session:issue"
PUBLIC_SESSION_CLIENT_HOURLY_LIMIT = 20
PUBLIC_SESSION_CLIENT_DAILY_LIMIT = 80
PUBLIC_SESSION_SCOPE_DAILY_LIMIT = 1000

PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT = 20
PUBLIC_SEARCH_QUOTA_REDIS_PREFIX = "public_search:quota:client_day"
PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL = "search_quota_exhausted"

_RATE_LIMIT_LUA = """
for i = 1, #KEYS do
  local cur = tonumber(redis.call("GET", KEYS[i]) or "0")
  local maxn = tonumber(ARGV[i * 2])
  if cur >= maxn then
    return -i
  end
end
for i = 1, #KEYS do
  local n = redis.call("INCR", KEYS[i])
  if n == 1 then
    redis.call("EXPIRE", KEYS[i], tonumber(ARGV[(i * 2) - 1]))
  end
end
return 1
"""

_SEARCH_RUN_QUOTA_LUA = """
local cur = tonumber(redis.call("GET", KEYS[1]) or "0")
if cur >= tonumber(ARGV[1]) then
  return 0
end
local n = redis.call("INCR", KEYS[1])
if n == 1 then
  redis.call("EXPIRE", KEYS[1], tonumber(ARGV[2]))
end
return n
"""


def new_embed_session_id() -> str:
    return f"embsess_{uuid.uuid4().hex}"


def _key_part(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _client_identity(request: Request) -> str:
    if request.client is not None and request.client.host:
        return request.client.host.strip()
    return "unknown"


async def enforce_public_session_issue_rate_limit(
    *,
    redis_client: RedisClient,
    request: Request,
    scope: str,
) -> None:
    scope_key = _key_part(scope.strip() or "public")
    client_key = _key_part(_client_identity(request))
    keys = [
        f"{PUBLIC_SESSION_RATE_LIMIT_REDIS_PREFIX}:client_hour:{scope_key}:{client_key}",
        f"{PUBLIC_SESSION_RATE_LIMIT_REDIS_PREFIX}:client_day:{scope_key}:{client_key}",
        f"{PUBLIC_SESSION_RATE_LIMIT_REDIS_PREFIX}:scope_day:{scope_key}",
    ]
    try:
        raw = await redis_client.eval(
            _RATE_LIMIT_LUA,
            len(keys),
            *keys,
            "3600",
            str(PUBLIC_SESSION_CLIENT_HOURLY_LIMIT),
            "86400",
            str(PUBLIC_SESSION_CLIENT_DAILY_LIMIT),
            "86400",
            str(PUBLIC_SESSION_SCOPE_DAILY_LIMIT),
        )
    except Exception:
        logger.exception("public_session_rate_limit_unavailable", scope=scope)
        raise HTTPException(status_code=503, detail="Публичные сессии временно недоступны")

    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        logger.error("public_session_rate_limit_bad_reply", scope=scope, raw=raw)
        raise HTTPException(status_code=503, detail="Публичные сессии временно недоступны")
    if int(raw) < 0:
        raise HTTPException(status_code=429, detail="Слишком много публичных сессий. Попробуйте позже")


async def enforce_public_search_run_quota(
    *,
    redis_client: RedisClient,
    request: Request,
) -> None:
    scope_key = _key_part("public_search")
    client_key = _key_part(_client_identity(request))
    quota_key = f"{PUBLIC_SEARCH_QUOTA_REDIS_PREFIX}:{scope_key}:{client_key}"
    try:
        raw = await redis_client.eval(
            _SEARCH_RUN_QUOTA_LUA,
            1,
            quota_key,
            str(PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT),
            "86400",
        )
    except Exception:
        logger.exception("public_search_run_quota_unavailable")
        raise HTTPException(status_code=503, detail="Публичные сессии временно недоступны")

    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        logger.error("public_search_run_quota_bad_reply", raw=raw)
        raise HTTPException(status_code=503, detail="Публичные сессии временно недоступны")
    if int(raw) == 0:
        raise HTTPException(status_code=429, detail=PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL)
