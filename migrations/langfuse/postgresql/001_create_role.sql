-- Миграция 001: Создание роли langfuse в PostgreSQL
-- Выполняется при инициализации PostgreSQL для Langfuse

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'langfuse') THEN
      CREATE ROLE langfuse LOGIN PASSWORD 'langfuse_password';
   END IF;
END
$$;
