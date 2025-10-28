-- Миграция 002: Создание пользователя langfuse в ClickHouse
-- Выполняется после создания базы данных

CREATE USER IF NOT EXISTS langfuse IDENTIFIED WITH sha256_password BY 'langfuse_password';
