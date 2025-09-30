# Настройка Agent Lab

## Что это за файлы?

- `conf.example` - шаблон конфигурации с примерами
- `conf.json` - ваша рабочая конфигурация (создается из шаблона)

## Быстрый старт (минимум для работы)

1. **Создайте конфигурацию**
   ```bash
   cp conf.example conf.json
   ```

2. **Для локальной разработки** - больше ничего не нужно! 
   Система будет работать с:
   - Встроенной базой данных
   - Mock LLM (имитация ИИ для тестов)
   - Локальными настройками

3. **Запустите систему**
   ```bash
   docker-compose up -d
   ```

## Когда нужно что-то настраивать?

### Если хотите использовать настоящий ИИ
**Проблема**: Mock LLM только имитирует ответы  
**Решение**: Подключите один из провайдеров ИИ ⬇️

### Если нужны Telegram боты  
**Проблема**: Боты не отвечают в Telegram  
**Решение**: Добавьте токены ботов ⬇️

### Если нужна работа с файлами
**Проблема**: Нельзя загружать/сохранять файлы  
**Решение**: Настройте S3 хранилище ⬇️

## Настройка ИИ (LLM)

### 🤖 OpenAI (ChatGPT)
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

### 🧠 Google Gemini (бесплатный)
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

### 🇷🇺 Yandex GPT
**Где взять**: https://cloud.yandex.ru/services/yandexgpt  
**Что делать**: Нужен аккаунт Yandex Cloud и настройка сервисного аккаунта

### 🦙 Ollama (локальный, бесплатный)
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

## Дополнительные сервисы

### Telegram боты
```json
"telegram": {
  "enabled": true,
  "bots": {
    "имя_бота": "токен-телеграм-бота"
  }
}
```

### S3 хранилище
Поддерживаются: AWS S3, Yandex Cloud, VK Cloud, MinIO

```json
"s3": {
  "enabled": true,
  "default_bucket": "имя-бакета",
  "buckets": {
    "ваш-бакет": {
      "provider": "yandex|aws|vkcloud|minio",
      "access_key_id": "ваш-access-key",
      "secret_access_key": "ваш-secret-key",
      "region_name": "регион",
      "endpoint_url": "https://endpoint-url",
      "enabled": true
    }
  }
}
```

### Yandex OAuth
```json
"auth": {
  "providers": {
    "yandex": {
      "client_id": "ваш-yandex-oauth-client-id",
      "client_secret": "ваш-yandex-oauth-client-secret",
      "enabled": true
    }
  }
}
```

### Голосовые сервисы (Cloud Voice)
```json
"cloud_voice": {
  "enabled": true,
  "secret_key": "ваш-секретный-ключ",
  "client_id": "ваш-client-id"
}
```

### FASHN API
```json
"fashn": {
  "enabled": true,
  "api_key": "ваш-fashn-api-ключ"
}
```

## Примечания

- Для разработки можно использовать `mock` провайдер LLM (включен по умолчанию)
- Все внешние сервисы по умолчанию отключены (`enabled: false`)
- Включайте только те сервисы, которые планируете использовать
- Не коммитьте файл `conf.json` с реальными ключами в репозиторий
