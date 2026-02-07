# RAG Service

RAG Service - микросервис для управления документами и семантического поиска с поддержкой множественных провайдеров.

## Возможности

- 🔄 **Переключение между провайдерами** (pgvector, Agentset)
- 📁 **Управление namespaces** (создание, удаление, список)
- 📄 **Загрузка документов** (PDF, TXT, DOCX и др.)
- 🔍 **Семантический поиск** по документам
- 💎 **Glassmorphism UI** с поддержкой светлой и темной темы
- ⚡ **Реактивный интерфейс** на Lit 3 + Zustand

## Архитектура

```
apps/rag/
├── main.py                  # FastAPI приложение
├── config.py                # Настройки сервиса
├── container.py             # DI контейнер
├── conf.json                # Конфигурация
├── api/                     # REST API endpoints
│   ├── providers.py         # Управление провайдерами
│   ├── namespaces.py        # Управление namespaces
│   ├── documents.py         # Управление документами
│   └── search.py            # Семантический поиск
└── ui/                      # Micro-frontend
    ├── index.html
    ├── index.js
    ├── app/
    │   └── rag-app.js       # Главный компонент
    ├── components/
    │   ├── provider-selector.js
    │   ├── provider-badge.js
    │   └── namespace-card.js
    ├── features/
    │   ├── sidebar.js
    │   └── namespace-list.js
    ├── services/
    │   ├── rag-api.service.js
    │   └── store.js         # Zustand Store
    └── styles/
        └── rag.css
```

## API Endpoints

### Providers

```
GET    /rag/api/v1/providers
POST   /rag/api/v1/providers/switch
```

### Namespaces

```
GET    /rag/api/v1/namespaces?provider={name}
POST   /rag/api/v1/namespaces?provider={name}
DELETE /rag/api/v1/namespaces/{id}?provider={name}
```

### Documents

```
GET    /rag/api/v1/namespaces/{id}/documents?provider={name}
POST   /rag/api/v1/namespaces/{id}/documents?provider={name}
DELETE /rag/api/v1/namespaces/{id}/documents/{doc_id}?provider={name}
```

### Search

```
POST   /rag/api/v1/namespaces/{id}/search?provider={name}
POST   /rag/api/v1/search?provider={name}
```

## Конфигурация

```json
{
  "rag": {
    "enabled": true,
    "default_provider": "pgvector",
    "providers": {
      "pgvector": {
        "enabled": true,
        "host": "localhost",
        "port": 5433
      },
      "agentset": {
        "enabled": true,
        "api_key": "your_key",
        "base_url": "https://api.agentset.ai"
      }
    }
  }
}
```

## Запуск

### Development

```bash
make run-rag
```

Или напрямую:

```bash
uv run python scripts/run_rag.py
```

Сервис запустится на `http://localhost:8004`

### Production

```bash
make deploy-rag
```

## UI

Micro-frontend доступен по адресу: `http://localhost:8004/rag/ui`

### Архитектура UI

- **Lit 3** - веб-компоненты
- **Zustand** - state management
- **Core Frontend** - общая библиотека компонентов и стилей
- **Glassmorphism** - дизайн-система

### Компоненты

- `rag-app` - главный компонент
- `rag-sidebar` - боковая панель навигации
- `provider-selector` - dropdown для выбора провайдера
- `provider-badge` - индикатор текущего провайдера
- `namespace-card` - карточка namespace
- `namespace-list` - список namespaces

## Провайдеры

### pgvector

PostgreSQL с расширением pgvector для векторного поиска.

```bash
docker run -p 5433:5432 pgvector/pgvector:pg16
```

### Agentset

Облачный RAG сервис.

Требуется API ключ в конфигурации.

## Testing

```bash
# Providers API
curl http://localhost:8004/rag/api/v1/providers

# Switch provider
curl -X POST http://localhost:8004/rag/api/v1/providers/switch \
  -H "Content-Type: application/json" \
  -d '{"provider_name": "agentset"}'

# Namespaces
curl http://localhost:8004/rag/api/v1/namespaces

# Create namespace
curl -X POST http://localhost:8004/rag/api/v1/namespaces \
  -H "Content-Type: application/json" \
  -d '{"name": "my_docs", "description": "My documents"}'
```

## Интеграция с Agents

RAG Service интегрирован с Agents через `core/rag`:

```python
from core.rag.factory import get_rag_provider

provider = get_rag_provider("pgvector")
results = await provider.search(
    namespace_id="my_docs",
    query="How to use RAG?",
    limit=5
)
```

## Troubleshooting

### PostgreSQL + pgvector не подключается

Убедитесь что PostgreSQL с pgvector запущен:

```bash
docker ps | grep postgres
```

### Agentset API ошибка

Проверьте API ключ в `conf.json`:

```json
{
  "rag": {
    "providers": {
      "agentset": {
        "api_key": "your_valid_key"
      }
    }
  }
}
```

## Roadmap

- [ ] Document viewer
- [ ] Advanced search filters
- [ ] Batch document upload
- [ ] Document versioning
- [ ] Analytics dashboard
- [ ] Multi-language support


