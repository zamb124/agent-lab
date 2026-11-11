# RAG — матрица покрытия документационными инструкциями

Статусы: ✅ опубликовано · 🚧 в работе · 📝 запланировано · ⛔ не документируем.

`rag-app`, `/rag/` на `system.<subdomain>:9002`, fixture `rag_ui`
(зависит от `rag_service` → `provider_litserve_service`).

## UI-поверхности

| Страница | Что видит пользователь |
|---|---|
| `namespaces-page` | Список пространств (namespace = Namespace.name) |
| `namespace-page` | Документы/индекс пространства |
| `search-page` | Семантический поиск |
| `settings-page` | Настройки сервиса |

## Блоки и инструкции

### general — Общее

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `rag-shell` | Оболочка сервиса | готовый | ✅ |
| 1 | `rag-first-namespace` | Пространство → загрузка → поиск (featured) | `test_rag_doc_getting_started.py` | ✅ |

### search (новый тег)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `semantic-search-demo` | Найти документ по смыслу, не по словам | `test_rag_doc_search.py` | ✅ |

### documents (новый тег)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `upload-and-index-documents` | Загрузить файл и дождаться индекса | `test_rag_doc_search.py` | ✅ |
| 3 | `index-status-and-reembed` | Статус индекса, переиндексация | — | ⛔ |

## Долг и заметки

- `index-status-and-reembed`: в UI нет контроля переиндексации (только статус в карточке документа) — документировать нечего.
- Индексация может быть долгой — в сценарии ждать статус через UI (не sleep); embedding идёт через provider_litserve (уже в стеке).
- Теги `search`/`documents` добавлены в taxonomy.
- featured_slug: `rag-first-namespace` (после создания).
