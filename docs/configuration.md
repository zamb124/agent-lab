# Настройка Agent Lab

Руководство по настройке конфигурации платформы.

## Файлы конфигурации

- `conf.example` - шаблон конфигурации с примерами
- `conf.json` - рабочая конфигурация (создается из шаблона, не попадает в git)

## Быстрый старт

1. **Создайте конфигурацию**
   ```bash
   cp conf.example conf.json
   ```

2. **Для локальной разработки** больше ничего не нужно! Система работает с:
   - PostgreSQL (через Docker)
   - Mock LLM (имитация для тестов)
   - Локальными настройками

3. **Запустите систему**
   ```bash
   docker-compose up -d
   # или локально
   uv run python run.py
   ```

## Когда нужно что-то настраивать?

### Если хотите использовать настоящий ИИ
**Проблема**: Mock LLM только имитирует ответы  
**Решение**: Подключите один из провайдеров ИИ ⬇️

### Если нужны Telegram боты  
**Проблема**: Боты не отвечают в Telegram  
**Решение**: Добавьте токены ботов ⬇️

### Если нужны WhatsApp боты
**Проблема**: Боты не отвечают в WhatsApp  
**Решение**: Настройте WhatsApp Business API ⬇️

### Если нужна работа с файлами
**Проблема**: Нельзя загружать/сохранять файлы  
**Решение**: Настройте S3 хранилище ⬇️

## Настройка ИИ (LLM)

### OpenAI (ChatGPT)
**Где взять**: https://platform.openai.com/api-keys  
**Что делать**: 
1. Зарегистрируйтесь на OpenAI
2. Создайте API ключ
3. В `conf.json` найдите секцию `"openai"` и замените:
```json
"openai": {
  "api_key": "sk-ваш-настоящий-ключ-здесь",
  "enabled": true
}
```
4. Измените провайдер по умолчанию:
```json
"llm": {
  "default_provider": "openai"
}
```

### Google Gemini (бесплатный)
**Где взять**: https://aistudio.google.com/app/apikey  
**Что делать**:
1. Перейдите по ссылке, войдите в Google аккаунт
2. Нажмите "Create API Key"
3. В `conf.json`:
```json
"gemini": {
  "api_key": "ваш-ключ-gemini",
  "enabled": true
}
```
```json
"llm": {
  "default_provider": "gemini"
}
```

### Yandex GPT
**Где взять**: https://cloud.yandex.ru/services/yandexgpt  
**Что делать**: Нужен аккаунт Yandex Cloud и настройка сервисного аккаунта

### Ollama (локальный, бесплатный)
**Где взять**: https://ollama.ai  
**Что делать**:
1. Установите Ollama на компьютер
2. Запустите модель: `ollama run llama2`
3. В `conf.json`:
```json
"ollama": {
  "enabled": true
}
```
```json
"llm": {
  "default_provider": "ollama"
}
```

## Telegram боты

### Создание бота
**Где создать**: Напишите @BotFather в Telegram  
**Что делать**:
1. Отправьте `/newbot` боту @BotFather
2. Придумайте имя и username бота
3. Получите токен вида `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
4. В `conf.json`:
```json
"telegram": {
  "enabled": true,
  "bots": {
    "мой_бот": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
  }
}
```

## WhatsApp боты

### Настройка WhatsApp Business API
**Где настроить**: https://developers.facebook.com  
**Что делать**:
1. Создайте Meta for Developers аккаунт
2. Создайте приложение типа "Business"
3. Добавьте продукт "WhatsApp"
4. Получите credentials:
   - Phone Number ID
   - Access Token
   - Business Account ID
5. Создайте verify token (любая случайная строка)
6. В `conf.json`:
```json
"whatsapp": {
  "enabled": true,
  "verify_token": "ваш-verify-token",
  "graph_api_version": "v18.0"
}
```

**Важно**: Для каждого flow настройте WhatsApp через переменные:
- `whatsapp_phone_number_id`
- `whatsapp_access_token`
- `whatsapp_verify_token`
- `whatsapp_business_account_id` (опционально)

Подробная инструкция: [integrations/whatsapp/setup.md](integrations/whatsapp/setup.md)

## Хранилище файлов (S3)

### Зачем нужно?
Для загрузки и обработки файлов пользователями (изображения, документы).

### Yandex Cloud (рекомендуется для РФ)
**Где настроить**: https://console.cloud.yandex.ru/  
**Что делать**:
1. Создайте аккаунт Yandex Cloud
2. Создайте Object Storage bucket
3. Получите ключи доступа
4. В `conf.json`:
```json
"s3": {
  "enabled": true,
  "default_bucket": "имя-вашего-бакета",
  "buckets": {
    "имя-вашего-бакета": {
      "provider": "yandex",
      "access_key_id": "ваш-access-key-id",
      "secret_access_key": "ваш-secret-access-key",
      "region_name": "ru-central1",
      "endpoint_url": "https://storage.yandexcloud.net",
      "enabled": true
    }
  }
}
```

### AWS S3 (для международных проектов)
Аналогично, но с настройками AWS

## Что можно не настраивать (пока не нужно)

- **Yandex OAuth** - только если нужна авторизация через Yandex
- **WhatsApp** - только если нужны WhatsApp боты
- **Cloud Voice** - только для голосовых функций  
- **FASHN API** - только для виртуальной примерки одежды
- **База данных** - Docker сам настроит PostgreSQL

## Важно

- `conf.json` не попадает в git (в .gitignore)
- Не публикуйте API ключи в открытом коде
- Для продакшена смените `secret_key` в секции `auth`

## См. также

- [Архитектура](architecture.md) - общая архитектура
- [API Reference](api.md) - работа через API
- [Deployment](deployment.md) - развертывание
