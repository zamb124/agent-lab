-- Миграция 001: Создание базы данных langfuse в ClickHouse
-- Выполняется при инициализации ClickHouse для Langfuse

CREATE DATABASE IF NOT EXISTS langfuse;
