"""Redis lease для (flow_id, node_id)."""

from __future__ import annotations

from datetime import datetime, timezone

from core.clients.redis_client import RedisClient
from core.config.models import GuestRuntimeFarmConfig
from core.guest_runtime.models import GuestLease, GuestLeaseCapError, GuestLogLine
from core.types import JsonValue

_LEASE_PREFIX = "guest:lease:"
_COMPANY_COUNT_PREFIX = "guest:lease_count:company:"
_CLUSTER_COUNT_KEY = "guest:lease_count:cluster"
_TASK_PREFIX = "guest:task:"
_BUILD_LOCK_KEY = "guest:build_lock"
_LOG_PREFIX = "guest:logs:"

_ACQUIRE_LUA = """
local lease_key = KEYS[1]
local company_key = KEYS[2]
local cluster_key = KEYS[3]
local lease_json = ARGV[1]
local ttl = tonumber(ARGV[2])
local max_company = tonumber(ARGV[3])
local max_cluster = tonumber(ARGV[4])
local function expire_at_least(key, wanted)
  local current = redis.call('TTL', key)
  if current < 0 or wanted > current then
    redis.call('EXPIRE', key, wanted)
  end
end
if redis.call('EXISTS', lease_key) == 1 then
  redis.call('SET', lease_key, lease_json, 'EX', ttl)
  return {1, redis.call('GET', company_key) or '0', redis.call('GET', cluster_key) or '0'}
end
local company = tonumber(redis.call('GET', company_key) or '0')
local cluster = tonumber(redis.call('GET', cluster_key) or '0')
if company >= max_company then
  return {0, company, cluster}
end
if cluster >= max_cluster then
  return {0, company, cluster}
end
redis.call('INCR', company_key)
expire_at_least(company_key, ttl)
redis.call('INCR', cluster_key)
expire_at_least(cluster_key, ttl)
redis.call('SET', lease_key, lease_json, 'EX', ttl)
return {1, company + 1, cluster + 1}
"""

_RELEASE_LUA = """
local lease_key = KEYS[1]
local company_key = KEYS[2]
local cluster_key = KEYS[3]
if redis.call('DEL', lease_key) == 0 then
  return 0
end
local company = tonumber(redis.call('GET', company_key) or '0')
if company > 0 then
  redis.call('DECR', company_key)
end
local cluster = tonumber(redis.call('GET', cluster_key) or '0')
if cluster > 0 then
  redis.call('DECR', cluster_key)
end
return 1
"""

_IMAGE_REF_INCR = """
local key = KEYS[1]
local ttl = tonumber(ARGV[1])
local n = redis.call('INCR', key)
local current = redis.call('TTL', key)
if current < 0 or ttl > current then
  redis.call('EXPIRE', key, ttl)
end
return n
"""

_IMAGE_REF_DECR = """
local key = KEYS[1]
local n = tonumber(redis.call('GET', key) or '0')
if n <= 1 then
  redis.call('DEL', key)
  return 0
end
return redis.call('DECR', key)
"""

_LOG_APPEND_LUA = """
local key = KEYS[1]
local payload = ARGV[1]
local max_lines = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
redis.call('LPUSH', key, payload)
redis.call('LTRIM', key, 0, max_lines - 1)
redis.call('EXPIRE', key, ttl)
return redis.call('LLEN', key)
"""

_LOG_LIST_LUA = """
return redis.call('LRANGE', KEYS[1], 0, -1)
"""


def lease_key(flow_id: str, node_id: str) -> str:
    return f"{_LEASE_PREFIX}{flow_id}:{node_id}"


def logs_key(flow_id: str, node_id: str) -> str:
    return f"{_LOG_PREFIX}{flow_id}:{node_id}"


def _lua_int(result: JsonValue, *, label: str) -> int:
    if isinstance(result, bool):
        raise RuntimeError(f"{label} returned bool")
    if isinstance(result, int):
        return result
    if isinstance(result, str) and result.lstrip("-").isdigit():
        return int(result)
    raise RuntimeError(f"{label} returned {type(result).__name__}")


class GuestLeaseStore:
    def __init__(self, redis: RedisClient, farm: GuestRuntimeFarmConfig) -> None:
        self._redis: RedisClient = redis
        self._farm: GuestRuntimeFarmConfig = farm

    async def get(self, flow_id: str, node_id: str) -> GuestLease | None:
        raw = await self._redis.get(lease_key(flow_id, node_id))
        if raw is None:
            return None
        return GuestLease.model_validate_json(raw)

    async def put_existing(self, lease: GuestLease, *, ttl_seconds: int) -> None:
        ok = await self._redis.set(
            lease_key(lease.flow_id, lease.node_id),
            lease.model_dump_json(),
            ttl=ttl_seconds,
        )
        if not ok:
            raise RuntimeError("Redis set failed for guest lease")

    async def acquire_new(self, lease: GuestLease, *, ttl_seconds: int) -> None:
        if await self._try_acquire(lease, ttl_seconds=ttl_seconds):
            return
        await self.rebuild_counts()
        if await self._try_acquire(lease, ttl_seconds=ttl_seconds):
            return
        raise GuestLeaseCapError("guest lease cap exceeded")

    async def _try_acquire(self, lease: GuestLease, *, ttl_seconds: int) -> bool:
        result = await self._redis.eval(
            _ACQUIRE_LUA,
            3,
            lease_key(lease.flow_id, lease.node_id),
            f"{_COMPANY_COUNT_PREFIX}{lease.company_id}",
            _CLUSTER_COUNT_KEY,
            lease.model_dump_json(),
            ttl_seconds,
            self._farm.max_leases_per_company,
            self._farm.max_leases_cluster,
        )
        if not isinstance(result, list) or len(result) != 3:
            raise RuntimeError(f"guest lease acquire lua returned {type(result).__name__}")
        flag = result[0]
        if flag == 0 or flag == "0":
            return False
        if flag not in {1, "1"}:
            raise RuntimeError(f"guest lease acquire unexpected flag: {flag!r}")
        return True

    async def rebuild_counts(self) -> None:
        leases = await self.list_all()
        by_company: dict[str, int] = {}
        for lease in leases:
            company_id = lease.company_id
            if company_id not in by_company:
                by_company[company_id] = 0
            by_company[company_id] += 1
        ttl = self._farm.max_lifetime_seconds
        count_keys = await self._redis.scan_keys(f"{_COMPANY_COUNT_PREFIX}*")
        live_company_keys = {
            f"{_COMPANY_COUNT_PREFIX}{company_id}" for company_id in by_company
        }
        stale = [key for key in count_keys if key not in live_company_keys]
        if stale:
            deleted = await self._redis.delete(*stale)
            _ = deleted
        if not leases:
            deleted_cluster = await self._redis.delete(_CLUSTER_COUNT_KEY)
            _ = deleted_cluster
            return
        cluster_ok = await self._redis.set(_CLUSTER_COUNT_KEY, str(len(leases)), ttl=ttl)
        if not cluster_ok:
            raise RuntimeError("Redis set failed for guest cluster lease count")
        for company_id, n in by_company.items():
            company_ok = await self._redis.set(
                f"{_COMPANY_COUNT_PREFIX}{company_id}",
                str(n),
                ttl=ttl,
            )
            if not company_ok:
                raise RuntimeError(f"Redis set failed for guest company lease count {company_id}")

    async def release(self, lease: GuestLease) -> None:
        _ = await self._redis.eval(
            _RELEASE_LUA,
            3,
            lease_key(lease.flow_id, lease.node_id),
            f"{_COMPANY_COUNT_PREFIX}{lease.company_id}",
            _CLUSTER_COUNT_KEY,
        )

    async def list_all(self) -> list[GuestLease]:
        keys = await self._redis.scan_keys(f"{_LEASE_PREFIX}*")
        leases: list[GuestLease] = []
        for key in keys:
            raw = await self._redis.get(key)
            if raw is None:
                continue
            leases.append(GuestLease.model_validate_json(raw))
        return leases

    async def store_task(self, task_id: str, payload: str, *, ttl_seconds: int) -> None:
        ok = await self._redis.set(f"{_TASK_PREFIX}{task_id}", payload, ttl=ttl_seconds)
        if not ok:
            raise RuntimeError("Redis set failed for guest A2A task")

    async def get_task(self, task_id: str) -> str | None:
        return await self._redis.get(f"{_TASK_PREFIX}{task_id}")

    async def incr_image_ref(self, digest: str, *, ttl_seconds: int) -> int:
        result: JsonValue = await self._redis.eval(
            _IMAGE_REF_INCR,
            1,
            f"guest:image_ref:{digest}",
            ttl_seconds,
        )
        return _lua_int(result, label="image ref incr")

    async def decr_image_ref(self, digest: str) -> int:
        result: JsonValue = await self._redis.eval(
            _IMAGE_REF_DECR,
            1,
            f"guest:image_ref:{digest}",
        )
        return _lua_int(result, label="image ref decr")

    async def acquire_build_lock(self, digest: str, *, ttl_seconds: int) -> bool:
        return await self._redis.set_nx(_BUILD_LOCK_KEY, digest, ttl_seconds)

    async def release_build_lock(self) -> None:
        deleted = await self._redis.delete(_BUILD_LOCK_KEY)
        _ = deleted

    async def acquire_slot_lock(self, flow_id: str, node_id: str, *, ttl_seconds: int) -> bool:
        return await self._redis.set_nx(
            f"guest:slot_lock:{flow_id}:{node_id}",
            "1",
            ttl_seconds,
        )

    async def release_slot_lock(self, flow_id: str, node_id: str) -> None:
        deleted = await self._redis.delete(f"guest:slot_lock:{flow_id}:{node_id}")
        _ = deleted

    async def append_log(
        self,
        flow_id: str,
        node_id: str,
        line: GuestLogLine,
    ) -> None:
        ttl = self._farm.max_lifetime_seconds * 24
        result = await self._redis.eval(
            _LOG_APPEND_LUA,
            1,
            logs_key(flow_id, node_id),
            line.model_dump_json(),
            self._farm.log_lines_max,
            ttl,
        )
        _ = _lua_int(result, label="guest log append")

    async def list_logs(self, flow_id: str, node_id: str) -> list[GuestLogLine]:
        raw = await self._redis.eval(_LOG_LIST_LUA, 1, logs_key(flow_id, node_id))
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise RuntimeError(f"guest logs LRANGE returned {type(raw).__name__}")
        items: list[GuestLogLine] = []
        for entry in reversed(raw):
            if not isinstance(entry, str) or entry.strip() == "":
                raise RuntimeError("guest log line must be a JSON string")
            items.append(GuestLogLine.model_validate_json(entry))
        return items

    def remaining_ttl(self, lease: GuestLease) -> int:
        now = datetime.now(timezone.utc)
        lifetime_left = self._farm.max_lifetime_seconds - int(
            (now - lease.started_at).total_seconds()
        )
        if lifetime_left < 1:
            if lease.in_flight > 0:
                raise RuntimeError("guest lease lifetime expired while in-flight")
            raise RuntimeError("guest lease TTL already expired")
        return lifetime_left
