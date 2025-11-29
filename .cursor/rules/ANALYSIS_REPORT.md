# Отчет по анализу правил .cursor/rules

## Найденные проблемы

### 1. ДУБЛИРОВАНИЕ ФАЙЛОВ

#### ❌ container.mdc и container_di.mdc
- **container.mdc** - актуальный, использует `@lazy` декоратор (соответствует коду)
- **container_di.mdc** - устаревший, использует `__getattr__` (не соответствует коду)
- **Решение**: Удалить `container_di.mdc`, оставить только `container.mdc`

#### ❌ repository.mdc и repository_pattern.mdc
- Оба файла описывают Repository Pattern
- **repository_pattern.mdc** - более полный и актуальный
- **repository.mdc** - дублирует информацию
- **Решение**: Удалить `repository.mdc`, оставить `repository_pattern.mdc`

#### ❌ database.mdc и database_architecture.mdc
- **database.mdc** - краткая версия
- **database_architecture.mdc** - полная версия с деталями
- **Решение**: Удалить `database.mdc`, оставить `database_architecture.mdc` (он помечен как "ОСНОВНОЙ REFERENCE")

#### ❌ javascript.mdc - дублирование внутри файла
- Файл содержит идентичный контент дважды (строки 1-536 и 537-1070)
- **Решение**: Удалить дублирование, оставить одну версию

### 2. НЕСООТВЕТСТВИЯ С КОДОМ

#### ❌ http_client.mdc - неправильный путь импорта
- **В правиле**: `from core.http_utils import get_httpx_client`
- **В коде**: `from core.http import get_httpx_client`
- **Решение**: Исправить в `http_client.mdc` на `core.http`

### 3. ПРОТИВОРЕЧИЯ В ПРАВИЛАХ

#### ⚠️ agent_architecture.mdc - упоминание кастомного StateGraph
- Говорит: "Система построена на базе кастомного `StateGraph` (не библиотека LangGraph)"
- Но в других местах используется LangGraph
- **Решение**: Проверить актуальность, возможно обновить описание

#### ⚠️ container_di.mdc - устаревший подход
- Использует `__getattr__` вместо `@lazy`
- Не соответствует реальной реализации
- **Решение**: Удалить файл (см. пункт 1)

### 4. ЛИШНИЕ ФАЙЛЫ

#### ❌ context_chat.mdc
- Содержит только общие правила документирования
- Дублирует информацию из `project.mdc`
- **Решение**: Удалить или объединить с `project.mdc`

#### ❌ tracing.mdc
- Правила для OpenTelemetry Tracing
- Не используется в основных правилах (alwaysApply: false)
- **Решение**: Оставить, но проверить актуальность

### 5. РЕКОМЕНДАЦИИ ПО ОРГАНИЗАЦИИ

#### ✅ Хорошо структурированные файлы:
- `code_quality.mdc` - четкие правила качества
- `session.mdc` - детальные правила работы с сессиями
- `state_manager.mdc` - подробное описание StateManager
- `crud_api.mdc` - правила автоматических CRUD роутеров

#### ⚠️ Файлы требующие проверки:
- `quick_reference.mdc` - может дублировать `database_architecture.mdc`
- `monorepo_architecture.mdc` - может пересекаться с `architecture.mdc`

## План действий

### Приоритет 1 (Критично):
1. ✅ Исправить `http_client.mdc` - путь импорта
2. ✅ Удалить `container_di.mdc` (устаревший)
3. ✅ Удалить `repository.mdc` (дубликат)
4. ✅ Удалить `database.mdc` (дубликат)
5. ✅ Исправить `javascript.mdc` (удалить дублирование)

### Приоритет 2 (Важно):
6. ⚠️ Проверить актуальность `agent_architecture.mdc` (кастомный StateGraph vs LangGraph)
7. ⚠️ Проверить необходимость `context_chat.mdc`
8. ⚠️ Проверить пересечения `quick_reference.mdc` и `database_architecture.mdc`

### Приоритет 3 (Опционально):
9. 📝 Обновить `README.md` в `.cursor/rules` с актуальным списком файлов

