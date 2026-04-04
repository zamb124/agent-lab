-- Дополнение к init.sql: безопасно применять к уже инициализированному кластеру,
-- если entrypoint-initdb.d не отработал (битый mount, прерванный первый старт).
-- CREATE DATABASE через psql \gexec — только если базы ещё нет.

SELECT 'CREATE DATABASE platform_agents'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'platform_agents')
\gexec

SELECT 'CREATE DATABASE platform_crm'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'platform_crm')
\gexec

SELECT 'CREATE DATABASE platform_sync'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'platform_sync')
\gexec

SELECT 'CREATE DATABASE platform_rag'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'platform_rag')
\gexec

SELECT 'CREATE DATABASE platform_office'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'platform_office')
\gexec

GRANT ALL PRIVILEGES ON DATABASE platform_shared TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_agents TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_crm TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_sync TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_rag TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE platform_office TO platform_user;

\connect platform_shared
CREATE EXTENSION IF NOT EXISTS vector;

\connect platform_crm
CREATE EXTENSION IF NOT EXISTS vector;

\connect platform_rag
CREATE EXTENSION IF NOT EXISTS vector;
