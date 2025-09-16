-- Инициализация базы данных Agent Platform

-- Создаем расширения
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Основная таблица key-value storage
CREATE TABLE IF NOT EXISTS storage (
    key VARCHAR PRIMARY KEY,
    value JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS ix_storage_key_prefix ON storage (key);
CREATE INDEX IF NOT EXISTS ix_storage_updated_at ON storage (updated_at);
CREATE INDEX IF NOT EXISTS ix_storage_value_gin ON storage USING gin (value);

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггер для автоматического обновления updated_at
CREATE TRIGGER update_storage_updated_at 
    BEFORE UPDATE ON storage 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Вставляем тестовые данные
INSERT INTO storage (key, value) VALUES 
('test:hello', '{"message": "Hello from Agent Platform!"}')
ON CONFLICT (key) DO NOTHING;
