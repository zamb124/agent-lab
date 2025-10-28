-- Миграция 003: Предоставление прав пользователю langfuse в ClickHouse
-- Выполняется после создания пользователя

-- Предоставление прав на базу данных langfuse
GRANT ALL ON langfuse.* TO langfuse;

-- Предоставление прав на системные таблицы
GRANT ALL ON system.* TO langfuse;
