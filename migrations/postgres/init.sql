-- Создание БД сервисов и расширений pgvector.
-- Список имён БД дублирует migrations/services.json (postgres.databases / vector_extensions).
-- База platform_shared создаётся через POSTGRES_DB образа Postgres; здесь — остальные сервисные БД.

CREATE DATABASE platform_agents;
CREATE DATABASE platform_crm;
CREATE DATABASE platform_sync;
CREATE DATABASE platform_rag;
CREATE DATABASE platform_office;
CREATE DATABASE platform_worktracker;
CREATE DATABASE platform_tracing;
CREATE DATABASE platform_search;

GRANT ALL PRIVILEGES ON DATABASE platform_shared TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_agents TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_crm TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_sync TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_rag TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_office TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_worktracker TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_tracing TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_search TO platform_user;

\connect platform_shared
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS vector;

\connect platform_agents
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\connect platform_crm
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS vector;

\connect platform_sync
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\connect platform_rag
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS vector;

\connect platform_office
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\connect platform_worktracker
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\connect platform_tracing
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\connect platform_search
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
