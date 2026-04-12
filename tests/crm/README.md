# CRM E2E Tests

Полный набор end-to-end тестов для CRM сервиса, покрывающий все пользовательские сценарии.

## Структура тестов

```
tests/crm/
├── conftest.py                          # CRM-специфичные фикстуры
├── README.md                            # Эта документация
└── e2e/
    ├── test_01_entity_lifecycle.py      # CRUD операции с entities
    ├── test_02_entity_types.py          # Кастомные типы и шаблоны
    ├── test_03_markdown_formatting.py   # Markdown в заметках
    ├── test_04_attachments.py           # Вложения через RAG
    ├── test_05_ai_analysis.py           # AI извлечение entities/relationships
    ├── test_06_ai_correction.py         # Корректировка результатов AI
    ├── test_07_relationships.py         # Связи между entities
    ├── test_08_relationship_graph.py    # Граф влияния и навигация
    ├── test_09_tasks_management.py      # Управление задачами
    ├── test_10_daily_summary.py         # Дневной саммари от AI
    ├── test_11_filtering_search.py      # Фильтрация и семантический поиск
    ├── test_12_access_requests.py       # Запросы доступа
    ├── test_13_user_profiles.py         # Профили пользователей
    ├── test_14_historical_notes.py      # Заметки задним числом
    ├── test_15_entity_cards.py          # Карточки сущностей со связями
    ├── test_16_saga_rollback.py         # Saga pattern и rollback
    ├── test_17_company_init.py          # Инициализация компании
    └── test_18_voice_input.py           # Голосовой ввод (опционально)
```

## Используемые фикстуры

Тесты используют фикстуры из `tests/conftest.py`:

- **`app`** - FastAPI приложение со всеми сервисами
- **`unique_id`** - уникальный ID для изоляции тестов
- **`mock_llm_redis`** - мок LLM через Redis для AI тестов
- **`client`** - HTTP клиент для agents API
- **`taskiq_worker`** - реальный TaskIQ worker
- **`rag_worker`** - RAG worker

**CRM-специфичные фикстуры** из `tests/crm/conftest.py`:

- **`crm_client`** - HTTP клиент для CRM API
- **`crm_container`** - CRM container (для прямого доступа к сервисам)

## Запуск тестов

### Все CRM тесты

```bash
uv run pytest tests/crm/ -v
```

### Конкретный файл

```bash
uv run pytest tests/crm/e2e/test_01_entity_lifecycle.py -v
```

### Конкретный тест

```bash
uv run pytest tests/crm/e2e/test_01_entity_lifecycle.py::TestEntityLifecycle::test_create_note -v
```

### Только быстрые тесты (без AI)

```bash
uv run pytest tests/crm/ -v -m "not real_taskiq"
```

### Только AI тесты

```bash
uv run pytest tests/crm/ -v -m "real_taskiq"
```

### С покрытием

```bash
# HTML отчет
uv run pytest tests/crm/ --cov=apps/crm --cov-report=html -v

# Terminal отчет
uv run pytest tests/crm/ --cov=apps/crm --cov-report=term -v

# Открыть HTML отчет
open htmlcov/index.html
```

### Параллельный запуск

```bash
uv run pytest tests/crm/ -n auto -v
```

## Покрытые функции

✅ **CRUD операции** - создание, чтение, обновление, удаление entities  
✅ **Шаблоны и типы** - кастомные типы entities с промптами для AI  
✅ **Markdown** - форматирование текста в заметках  
✅ **Вложения** - файлы разных форматов через RAG сервис  
✅ **AI анализ** - извлечение entities, relationships, задач  
✅ **Корректировка AI** - редактирование результатов AI  
✅ **Связи** - relationships между entities  
✅ **Граф связей** - навигация и поиск по графу  
✅ **Задачи** - управление с приоритетами и дедлайнами  
✅ **Дневной саммари** - обобщенный отчет за день  
✅ **Фильтрация** - по дате, тегам, типам, владельцу  
✅ **Семантический поиск** - через PostgreSQL + pgvector  
✅ **Access Requests** - запросы доступа к entities  
✅ **User Profiles** - профили с настройками  
✅ **Исторические заметки** - заметки задним числом  
✅ **Карточки entities** - с полным контекстом и связями  
✅ **Saga pattern** - каскадное удаление с rollback  
✅ **Company инициализация** - автоматическое создание типов  
✅ **Голосовой ввод** - транскрипция → AI анализ (опционально)

## Изоляция тестов

Каждый тест использует `unique_id` для изоляции данных:

```python
async def test_example(crm_client, unique_id):
    # unique_id уникален для каждого теста
    await crm_client.post("/entities", json={
        "name": f"Test entity {unique_id}"  # ← изоляция
    })
```

Это обеспечивает:
- Параллельный запуск тестов
- Отсутствие конфликтов данных
- Независимость тестов друг от друга

## Mock LLM для AI тестов

AI тесты используют `mock_llm_redis` для мока ответов LLM:

```python
@pytest.mark.real_taskiq
async def test_ai_analysis(crm_client, mock_llm_redis, unique_id):
    # Мокаем ответ LLM
    await mock_llm_redis([{
        "type": "text",
        "content": json.dumps({
            "note": {...},
            "entities": [...],
            "relationships": [...]
        })
    }])
    
    # Создаём заметку и вызываем analyze
    note_resp = await crm_client.post("/crm/api/v1/entities/", json={
        "entity_type": "note",
        "name": "Заметка",
        "description": "Текст для анализа",
    }, headers=auth_headers_system)
    note_id = note_resp.json()["entity_id"]
    response = await crm_client.post(f"/crm/api/v1/entities/notes/{note_id}/analyze", json={})
```

Метка `@pytest.mark.real_taskiq` указывает, что тест использует реальный TaskIQ worker.

## Проверка linter errors

```bash
# Проверить все CRM тесты
uv run ruff check tests/crm/

# Автофикс
uv run ruff check tests/crm/ --fix
```

## Отладка

### Подробный вывод

```bash
uv run pytest tests/crm/ -vv -s
```

### Остановка на первой ошибке

```bash
uv run pytest tests/crm/ -x
```

### Запуск последнего упавшего теста

```bash
uv run pytest tests/crm/ --lf
```

### Дебаг с pdb

```python
async def test_example(crm_client, unique_id):
    import pdb; pdb.set_trace()
    # ...
```

## Требования

- Python 3.12+
- uv (package manager)
- Docker (для тестовых сервисов: PostgreSQL, Redis, MinIO)

## Тестовое окружение

Перед запуском тестов убедитесь, что подняты тестовые сервисы:

```bash
docker compose -f docker-compose-test.yaml up -d
```

## CI/CD

Тесты запускаются автоматически в CI при каждом коммите:

```yaml
- name: Run CRM E2E tests
  run: uv run pytest tests/crm/ -v --cov=apps/crm
```

## Итого

**18 тестовых файлов**  
**~90+ тестовых сценариев**  
**100% покрытие user stories**

Все функции CRM сервиса покрыты end-to-end тестами без моков (кроме MockLLM).

