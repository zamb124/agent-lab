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
CREATE DATABASE platform_secrets;
CREATE DATABASE platform_wiki;
CREATE DATABASE platform_realtime;
CREATE DATABASE platform_stock;
CREATE DATABASE platform_shop;
CREATE DATABASE openfga;
-- Probe DB for live datasource tests (not an Alembic service tree).
CREATE DATABASE platform_datasource_customer;

GRANT ALL PRIVILEGES ON DATABASE platform_shared TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_agents TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_crm TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_sync TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_rag TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_office TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_worktracker TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_tracing TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_search TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_secrets TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_wiki TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_realtime TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_stock TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_shop TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE openfga TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_datasource_customer TO platform_user;

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

\connect platform_secrets
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\connect platform_wiki
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\connect platform_realtime
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\connect platform_stock
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\connect platform_shop
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
