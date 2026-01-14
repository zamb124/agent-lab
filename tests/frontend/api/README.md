# Интеграционные тесты создания компании

## Описание

Полные интеграционные тесты создания компании и автоматической инициализации агентов.

## Что тестируется

### 1. `test_company_creation_with_agents_initialization`

Полный E2E flow создания компании:

1. **Frontend API**: Создание компании через `POST /api/companies`
2. **Agents API**: Автоматический вызов `POST /agents/api/v1/company/init`
3. **TaskIQ**: Выполнение фоновой задачи `init_company_resources`
4. **DB Verification**: Проверка что public агенты загружены в namespace компании
5. **Filtering**: Проверка что internal агенты НЕ загружены

**Требования**: Реальный TaskIQ worker (маркер `@pytest.mark.real_taskiq`)

### 2. `test_company_init_endpoint_directly`

Прямое тестирование endpoint инициализации:

- Защита system namespace от инициализации через API
- Корректный запуск TaskIQ задачи для обычных компаний
- Возврат task_id для отслеживания

### 3. `test_check_slug_availability`

Проверка уникальности subdomain:

- Проверка доступности slug
- Создание компании
- Проверка что slug теперь занят

### 4. `test_company_creation_without_agents_service`

Отказоустойчивость:

- Компания создается даже если agents сервис недоступен
- Graceful degradation - ошибка только логируется

## Запуск тестов

### Предварительные требования

```bash
# Поднять тестовые зависимости
docker-compose -f docker-compose-test.yaml up -d

# Убедиться что Redis, PostgreSQL и MinIO запущены
docker ps | grep platform
```

### Запуск всех тестов

```bash
# Все тесты frontend API
pytest tests/frontend/api/ -v

# Конкретный тест
pytest tests/frontend/api/test_company_creation.py::test_company_creation_with_agents_initialization -v

# С логами
pytest tests/frontend/api/ -v -s
```

### Запуск с реальным TaskIQ

Тесты с маркером `@pytest.mark.real_taskiq` требуют запущенный TaskIQ worker:

```bash
# Терминал 1: Запустить worker
uv run python -m apps.broker.run_worker

# Терминал 2: Запустить тесты
pytest tests/frontend/api/test_company_creation.py::test_company_creation_with_agents_initialization -v
```

### Параллельный запуск

```bash
# С pytest-xdist
pytest tests/frontend/api/ -n auto -v
```

## Отладка

### Проверка логов

```bash
# Логи в реальном времени
pytest tests/frontend/api/ -v -s --log-cli-level=INFO

# Только ошибки
pytest tests/frontend/api/ -v -s --log-cli-level=ERROR
```

### Проверка TaskIQ задач

```bash
# Подключиться к Redis
redis-cli -p 6380

# Посмотреть очередь задач
KEYS taskiq:*

# Проверить статус задачи
GET taskiq:result:<task_id>
```

### Проверка БД

```bash
# Подключиться к PostgreSQL
psql -h localhost -p 5434 -U platform_user -d platform_test

# Посмотреть компании
SELECT * FROM companies;

# Посмотреть subdomain mapping (в Redis)
redis-cli -p 6380
KEYS subdomain:*
```

## Архитектура

```
┌─────────────┐
│  Frontend   │
│   Service   │
└──────┬──────┘
       │ POST /api/companies
       │ {name, slug}
       ▼
┌─────────────────────┐
│  Company Created    │
│  - company_id       │
│  - subdomain mapped │
│  - user assigned    │
└──────┬──────────────┘
       │ ServiceClient.post()
       │ POST /agents/api/v1/company/init
       ▼
┌─────────────┐
│   Agents    │
│   Service   │
└──────┬──────┘
       │ TaskIQ.kiq()
       │ init_company_resources(company_id)
       ▼
┌──────────────────────┐
│   TaskIQ Worker      │
│                      │
│  1. Load registry    │
│  2. Filter public    │
│  3. Load agents      │
│  4. Load tools       │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Redis DB            │
│  company:<id>:agent  │
│  company:<id>:tool   │
└──────────────────────┘
```

## Фикстуры

Все фикстуры определены в `tests/conftest.py`:

- `agents_app` - FastAPI app для agents сервиса
- `frontend_app` - FastAPI app для frontend сервиса
- `agents_client` - HTTP клиент для agents API
- `frontend_client` - HTTP клиент для frontend API
- `auth_token` - Токен авторизации для тестового пользователя
- `unique_id` - Уникальный ID для изоляции тестовых данных

## Troubleshooting

### Тест зависает на ожидании агентов

**Причина**: TaskIQ worker не запущен или задача упала

**Решение**:
```bash
# Проверить worker
ps aux | grep worker

# Запустить вручную
uv run python -m apps.broker.run_worker
```

### Агенты не загружаются

**Причина**: Некорректный registry.yaml или ошибка в AgentsLoader

**Решение**:
```bash
# Проверить registry
cat apps/agents/registry.yaml

# Проверить логи TaskIQ
pytest -v -s --log-cli-level=DEBUG
```

### 401 Unauthorized

**Причина**: Фикстура `auth_token` не создала пользователя

**Решение**:
```bash
# Проверить что container доступен
pytest tests/frontend/api/ -v -k "auth" --setup-show
```

## CI/CD

Тесты автоматически запускаются в CI:

```yaml
test:
  script:
    - docker-compose -f docker-compose-test.yaml up -d
    - uv run python -m apps.broker.run_worker &
    - pytest tests/frontend/api/ -v --junitxml=junit.xml
  artifacts:
    reports:
      junit: junit.xml
```

