# Клиенты внешних сервисов

Интеграции с внешними API и сервисами.

## FASHN Client

Интеграция с FASHN API — сервис виртуальной примерки одежды и аксессуаров.

### Возможности

- Виртуальная примерка сумок, одежды, аксессуаров
- Масштабирование продуктов по физическим размерам
- Интеграция с `FileProcessor` платформы
- Автоматическое сохранение в БД
- Асинхронная обработка с polling результатов

### Конфигурация

Добавьте в `conf.json`:

```json
{
  "fashn": {
    "enabled": true,
    "api_key": "your-fashn-api-key",
    "base_url": "https://api.fashn.ai/v1",
    "timeout": 60,
    "poll_interval": 2.0,
    "poll_timeout": 180
  }
}
```

### Использование

```python
from app.clients.fashn_client import get_fashn_client

client = get_fashn_client()
result = await client.try_on(
    model_image_bytes=model_bytes,
    product_image_bytes=product_bytes,
    model_height_cm=170,
    product_width_mm=300,
    item_kind="bag",
    placement="left_shoulder"
)

await client.close()
```

### Инструменты для агентов

Доступны через `app/tools/fashn_tools.py`:

- `virtual_try_on` - виртуальная примерка
- `upload_image_for_try_on` - загрузка изображений  
- `get_fashn_help` - справка

Автоматически доступны при включенном FASHN в конфигурации.

### API Endpoint

`POST /api/v1/fashn/try-on` - HTTP API для виртуальной примерки.

Подробнее: [API Reference](api_links.md)

## См. также

- [Конфигурация](configuration.md) - настройка FASHN
- [AmoCRM](integrations/amocrm/) - интеграция с CRM
