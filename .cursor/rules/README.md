# Cursor Rules для Agent Lab

Набор правил для AI-ассистента Cursor, сгенерированных на основе документации проекта.

## Структура правил

### Всегда применяемые (alwaysApply: true)

Эти правила применяются автоматически ко всем файлам:

- **comments.mdc** - Правила написания чистого кода (DDD)
- **exception.mdc** - Правила обработки исключений
- **architecture.mdc** - Архитектурные принципы (Database-First, асинхронность)
- **langgraph.mdc** - Работа с LangGraph (State, agents, checkpointer)
- **database.mdc** - Работа с базой данных (Storage, изоляция по компаниям)
- **tools.mdc** - Создание инструментов (@tool decorator, типизация)
- **project.mdc** - Общие правила проекта (UV, импорты, обработка ошибок)
- **main.mdc** - Конфигурация чтения README файлов

### Контекстные (alwaysApply: false)

Эти правила применяются только для релевантных файлов:

- **configuration.mdc** - Работа с конфигурацией (ENV переменные, приоритеты)
- **documentation.mdc** - Работа с документацией (MkDocs, структура, стиль)
- **makefile.mdc** - Работа с Makefile (команды, модули)
- **frontend.mdc** - Фронтенд (рекурсивный рендеринг, HTMX, модули)
- **testing.mdc** - Тестирование (реальная БД, фикстуры, изоляция)

## Ключевые принципы

### Database-First
Вся конфигурация в БД, код только для поведения.

### LangGraph-Native
Используй современные возможности LangGraph, не изобретай велосипеды.

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

Каждое правило основано на документации:
- `architecture.mdc` ← `docs/architecture.md`
- `configuration.mdc` ← `docs/configuration.md`
- `documentation.mdc` ← `mkdocs.yml` + правила работы с MkDocs
- `makefile.mdc` ← `docs/makefile.md`
- `langgraph.mdc` ← `docs/architecture.md` + LangGraph docs
- `database.mdc` ← `docs/architecture.md`
- `frontend.mdc` ← `docs/frontend.md`
- `testing.mdc` ← опыт разработки + memories

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

