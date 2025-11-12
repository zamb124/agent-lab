---
trigger: model_decision
description: "Правила работы с конфигурацией"
globs:
---
# Правила работы с конфигурацией

## Порядок приоритетов

Запомни навсегда:
1. **ENV переменные** (высший приоритет)
2. **conf.json** / **conf.local.json**
3. **Значения по умолчанию**

ENV переменные ВСЕГДА побеждают JSON!

## Формат ENV переменных

Используй двойное подчеркивание `__` для вложенных полей:

<good_example>
# Правильный формат
DATABASE__URL=postgresql+asyncpg://user:pass@host:5432/db
LLM__PROVIDERS__OPENAI__API_KEY=sk-...
SERVER__PORT=8001
</good_example>

<bad_example>
# Неправильный формат
DATABASE_URL=...           # Одинарное подчеркивание
database__url=...          # Нижний регистр
DATABASE.URL=...           # Точка вместо подчеркивания
</bad_example>

## Работа с конфигурацией

### Чтение настроек

<good_example>
from app.core.config import settings

# Читаем настройки
db_url = settings.database.url
api_key = settings.llm.providers["openai"].api_key
</good_example>

<bad_example>
# НЕ читай напрямую из JSON
import json
with open("conf.json") as f:
    config = json.load(f)  # НЕ ТАК
</bad_example>

### Добавление новых настроек

1. Добавь в модель конфигурации (`app/core/config.py`):

<good_example>
class MyServiceConfig(BaseModel):
    enabled: bool = False
    api_key: Optional[str] = None
    timeout: int = 30

class Settings(BaseSettings):
    my_service: MyServiceConfig = Field(default_factory=MyServiceConfig)
</good_example>

2. Добавь в `conf.json`:

<good_example>
{
  "my_service": {
    "enabled": true,
    "api_key": "key-...",
    "timeout": 60
  }
}
</good_example>

3. Используй в коде:

<good_example>
from app.core.config import settings

if settings.my_service.enabled:
    client = MyClient(
        api_key=settings.my_service.api_key,
        timeout=settings.my_service.timeout
    )
</good_example>

## Docker и ENV переменные

При работе с Docker ВСЕГДА переопределяй хосты через ENV:

<good_example>
# docker-compose.yml
services:
  app:
    environment:
      # Переопределяем localhost на имя сервиса
      - DATABASE__URL=postgresql+asyncpg://user:pass@postgres:5432/db
      - REDIS__HOST=redis
      - RABBITMQ__HOST=rabbitmq
</good_example>

<bad_example>
# НЕ создавай отдельный conf.docker.json
# НЕ меняй conf.json для Docker
# НЕ хардкодь хосты в коде
</bad_example>

## Чувствительные данные

НИКОГДА не храни секреты в `conf.json`:

<good_example>
# .env (не коммитится)
DATABASE__URL=postgresql+asyncpg://prod_user:SecurePass123@prod.db.com:5432/prod
LLM__PROVIDERS__OPENAI__API_KEY=sk-prod-key-...
AUTH__SECRET_KEY=super-secret-key-...
</good_example>

<good_example>
# conf.json (коммитится)
{
  "database": {
    "url": "postgresql+asyncpg://agent_user:agent_password@localhost:5432/agent_platform"
  }
}
</good_example>

<bad_example>
# conf.json - НЕ ТАК
{
  "database": {
    "url": "postgresql+asyncpg://prod_user:SuperSecretPassword@prod-db.company.com:5432/production"
  }
}
</bad_example>

## Локальная разработка

Создай `conf.local.json` для локальных экспериментов:

<good_example>
# Скопируй пример и отредактируй
cp conf.local.json.example conf.local.json

# conf.local.json (в .gitignore, не коммитится)
{
  "server": {
    "port": 8002
  },
  "llm": {
    "default_provider": "ollama"
  },
  "database": {
    "url": "postgresql+asyncpg://dev:dev@localhost:5433/dev_db"
  }
}
</good_example>

## Проверка конфигурации

Перед использованием проверь что значение корректное:

<good_example>
from app.core.config import settings

def init_database():
    if not settings.database.url:
        raise ValueError("DATABASE__URL не настроен")
    
    engine = create_engine(settings.database.url)
    return engine
</good_example>

## Типичные ошибки

### Ошибка 1: Неправильный формат ENV

```bash
# Неправильно
DATABASE_URL=postgres://...

# Правильно
DATABASE__URL=postgresql+asyncpg://...
```

### Ошибка 2: ENV не переопределяет JSON

Причина: используется одинарное подчеркивание или неправильный регистр.

Решение: проверь имя переменной в `docker-compose.yml` или `.env`.

### Ошибка 3: Секреты в Git

Причина: `conf.json` с паролями попал в коммит.

Решение:
1. Удали пароли из `conf.json`
2. Добавь их в `.env` или ENV переменные
3. Используй `git rm --cached conf.json` если нужно

## Отладка

Логируй конфигурацию при старте (без секретов):

<good_example>
from app.core.config import settings

logger.info(f"Database host: {settings.database.url.split('@')[1].split('/')[0]}")
logger.info(f"LLM provider: {settings.llm.default_provider}")
logger.info(f"Server port: {settings.server.port}")
</good_example>

<bad_example>
# НЕ логируй полные URL с паролями
logger.info(f"Database URL: {settings.database.url}")  # НЕ ТАК
</bad_example>

## Документация

При изменении конфигурации обновляй:
- `docs/configuration.md` - документацию
- Примеры в `conf.example` если он есть
- README.md если меняется запуск
