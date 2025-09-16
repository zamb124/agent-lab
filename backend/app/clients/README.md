# Клиенты внешних сервисов

## FASHN Client

Клиент для интеграции с FASHN API - сервисом виртуальной примерки одежды и аксессуаров.

### Возможности

- Виртуальная примерка сумок с точным позиционированием
- Виртуальная примерка одежды с автоматическим размещением
- Масштабирование продуктов по физическим размерам
- **Интеграция с FileProcessor платформы** - использует единую систему загрузки файлов
- **Автоматическое сохранение в БД** - все загруженные файлы отслеживаются
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
from backend.app.clients.fashn_client import get_fashn_client

# Клиент автоматически использует FileProcessor и S3 платформы
client = get_fashn_client()
result = await client.try_on(
    model_image_bytes=model_bytes,
    product_image_bytes=product_bytes,
    model_height_cm=170,
    product_width_mm=300,
    item_kind="bag",
    placement="left_shoulder"
)

# Не забудьте закрыть ресурсы
await client.close()
```

### Инструменты для агентов

- `virtual_try_on` - основная виртуальная примерка
- `upload_image_for_try_on` - загрузка изображений
- `get_fashn_help` - справка по использованию

Инструменты автоматически доступны для всех агентов при включенном FASHN в конфигурации.
