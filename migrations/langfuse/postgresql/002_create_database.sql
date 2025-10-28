-- Миграция 002: Создание базы данных langfuse в PostgreSQL
-- Выполняется после создания роли

SELECT 'CREATE DATABASE langfuse OWNER langfuse'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec
