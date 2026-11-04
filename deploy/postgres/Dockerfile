# Образ Postgres платформы: pgvector + PostGIS + pgRouting.
# Базовый образ несёт PGDG apt-репозиторий — пакеты ставятся под ту же major-версию PG.
FROM pgvector/pgvector:0.8.7-pg18

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-18-postgis-3 \
        postgresql-18-postgis-3-scripts \
        postgresql-18-pgrouting \
        postgresql-18-pgrouting-scripts \
    && rm -rf /var/lib/apt/lists/*
