# Deploy scripts — Redis runbook

Операции на кластере `platform/redis-0`. Требуют `kubectl` или SSH + `microk8s kubectl`.

## Инвентаризация

```bash
bash deploy/scripts/redis_key_inventory.sh
# или еженедельно:
bash deploy/scripts/redis_weekly_inventory.sh
```

Артефакт: `deploy/scripts/redis_inventory_latest.txt`.

## Smoke после деплоя TTL-фиксов

```bash
bash deploy/scripts/redis_smoke_projection_ttl.sh
```

Проверяет, что sample `flows:workflow_projection:*` на db0 имеют `TTL > 0`.

## Очистка легаси db0

```bash
DRY_RUN=1 bash deploy/scripts/redis_cleanup_domain_db0.sh
bash deploy/scripts/redis_cleanup_domain_db0.sh
```

Удаляет бессрочные `flows:workflow_projection:*` и orphan `platform_schedules:*` на db0.

## TaskIQ stream trim (db1)

```bash
DRY_RUN=1 bash deploy/scripts/redis_trim_taskiq_streams.sh
bash deploy/scripts/redis_trim_taskiq_streams.sh
```

Одноразовый `XTRIM` по политике: search=50k, idle/crm/rag=20k, flows_worker=10k.

Постоянный retention — `TasksConfig.stream_maxlen_by_queue` в `create_broker()`.

## Алерт памяти Redis (>75% limit)

Grafana Explore (метрики kube-state-metrics / cAdvisor):

```promql
container_memory_working_set_bytes{namespace="platform",pod="redis-0",container="redis"}
/
container_spec_memory_limit_bytes{namespace="platform",pod="redis-0",container="redis"}
> 0.75
```

Helm: `maxmemory 3gb` + `allkeys-lru` в StatefulSet (страховка при OOM).

## Два Redis URL

| DB | ENV | Назначение |
|----|-----|------------|
| 0 | `DATABASE__REDIS_URL` | Доменный кэш, session lock, presence |
| 1 | `TASKS__BROKER_URL` | TaskIQ streams, results, `platform_schedules` |
