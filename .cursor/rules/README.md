# Cursor Rules для Humanitec

Набор правил для AI-ассистента Cursor, сгенерированных на основе документации проекта.

## Структура правил

### Всегда применяемые (alwaysApply: true)

Эти правила применяются автоматически ко всем файлам:

- **comments.mdc** - Правила написания чистого кода (DDD)
- **exception.mdc** - Правила обработки исключений
- **architecture.mdc** - Архитектурные принципы (Database-First, асинхронность)
- **container.mdc** - Контейнер зависимостей (DI, доступ к сущностям)
- **agent_architecture.mdc** - Архитектура агентов (StateGraph, ReAct, субагенты)
- **state_manager.mdc** - Работа с StateManager и персистентностью состояния
- **session.mdc** - Правила работы с сессиями и session_id
- **database_architecture.mdc** - Архитектура БД и репозиториев
- **repository_pattern.mdc** - Repository Pattern и изоляция данных
- **tools.mdc** - Создание инструментов (@tool decorator)
- **project.mdc** - Общие правила проекта (UV, импорты)
- **http_client.mdc** - Правила работы с HTTP клиентами
- **crud_api.mdc** - Автоматические CRUD роутеры
- **main.mdc** - Конфигурация чтения README файлов
- **code_quality.mdc** - Качество кода, лаконичность

### Контекстные (alwaysApply: false)

Эти правила применяются только для релевантных файлов:

- **configuration.mdc** - Работа с конфигурацией (ENV переменные, приоритеты)
- **makefile.mdc** - Работа с Makefile (команды, модули)
- **frontend.mdc** - Фронтенд (рекурсивный рендеринг, HTMX, модули)
- **frontend_plugins.mdc** - Плагинная система фронтенда
- **javascript.mdc** - Архитектура JavaScript Frontend
- **testing.mdc** - Тестирование (структура тестов, фикстуры)
- **testing_fixtures.mdc** - Фикстуры и best practices
- **mcp.mdc** - MCP серверы и интеграция
- **variables.mdc** - Переменные и Session Store
- **tracing.mdc** - OpenTelemetry Tracing
- **monorepo_architecture.mdc** - Архитектура монорепозитория
- **taskiq.mdc** - TaskIQ задачи и очереди
- **domain_utils.mdc** - Утилиты для работы с доменами (humanitec.ru, agents-lab.ru)

## Ключевые принципы

### Database-First
Вся конфигурация в БД, код только для поведения.

### Graph-based execution
Используй графы состояний для построения сложной логики, не изобретай велосипеды.

### Асинхронность
Вся архитектура полностью асинхронная (async/await).

### Модульность
Каждый компонент независим и заменяем.

### Прозрачность
Никаких скрытых фолбэков - если что-то не работает, бросай исключение.

## Обновление правил

При изменении документации в `docs/`:
1. Обнови соответствующий `.mdc` файл
2. Убедись что примеры актуальны
3. Проверь что правила не противоречат друг другу

## Связь с документацией

Каждое правило основано на документации и коде:
- `architecture.mdc` ← `docs/architecture.md`
- `container.mdc` ← `core/container/base.py` + `apps/agents/container.py`
- `configuration.mdc` ← `core/config/`
- `monorepo_architecture.mdc` ← `docs/architecture.md`
- `state_manager.mdc` ← `apps/agents/services/state_manager.py`
- `session.mdc` ← `docs/state_and_variables.md`
- `database_architecture.mdc` ← `core/db/`
- `http_client.mdc` ← `core/http/`
- `frontend.mdc` ← `apps/frontend/`
- `testing.mdc` ← `tests/`
- `taskiq.mdc` ← `core/tasks/` + `apps/*/tasks/`
- `domain_utils.mdc` ← `core/utils/domain.py` + `deploy/`

## Формат правил

```markdown
---
alwaysApply: true/false
---
# Заголовок

## Секция

Описание правила

<good_example>
Правильный пример кода
</good_example>

<bad_example>
Неправильный пример кода
</bad_example>
```

## Использование

Cursor автоматически загружает эти правила и применяет при генерации кода.
Правила с `alwaysApply: true` работают везде, остальные - по контексту.

