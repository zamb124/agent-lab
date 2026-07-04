# Deploy scripts

## Redis observability

Мониторинг Redis — Grafana dashboard **Redis** (папка Platform). Метрики пишет idle-задача `redis_inventory_tick` каждые 15 мин (structured logs в Loki).

Панели: `used_memory`, `DBSIZE` db0/db1, `XLEN` TaskIQ streams, ключи без TTL, top prefixes, `platform_schedules`.

Retention в коде:

- TaskIQ streams — `TasksConfig.stream_maxlen_by_queue` в `create_broker()`
- `platform_schedules:*` — GC `platform_schedules_gc_tick` (cron `0 4 * * *`)
- Доменные ключи — обязательный TTL в `RedisClient.set()`

## Алерт памяти Redis pod (>75% limit)

Grafana Explore (kube-state-metrics / cAdvisor):

```promql
container_memory_working_set_bytes{namespace="platform",pod="redis-0",container="redis"}
/
container_spec_memory_limit_bytes{namespace="platform",pod="redis-0",container="redis"}
> 0.75
```

Helm: `maxmemory 3gb` + `allkeys-lru` в StatefulSet.

## Два Redis URL

| DB | ENV | Назначение |
|----|-----|------------|
| 0 | `DATABASE__REDIS_URL` | Доменный кэш, session lock, presence |
| 1 | `TASKS__BROKER_URL` | TaskIQ streams, results, `platform_schedules` |
