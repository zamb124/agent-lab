-- Миграция 003: Предоставление прав роли langfuse в PostgreSQL
-- Выполняется после создания базы данных

GRANT ALL PRIVILEGES ON DATABASE langfuse TO langfuse;
