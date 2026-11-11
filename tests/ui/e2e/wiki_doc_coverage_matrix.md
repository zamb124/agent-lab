# Wiki — матрица покрытия документационными инструкциями

Статусы: ✅ опубликовано · 🚧 в работе · 📝 запланировано · ⛔ не документируем.

`wiki-app`, `/wiki/` на `system.<subdomain>:9023`, fixture `wiki_ui`.
Helpers: `wiki_e2e_helpers.py` (namespace через API, open_page, title_input, tree_row, locale).

## UI-поверхности

| Страница/фича | Что видит пользователь |
|---|---|
| Дерево страниц (sidebar) | Иерархия разделов пространства |
| `wiki-page-view` + ProseMirror-редактор | Чтение и редактирование страницы |
| `/wiki/search` | Поиск по тексту и по смыслу |
| `wiki-page-access-modal` | Доступ и публичные ссылки |
| `wiki-public-preview-page` | Публичный сайт раздела |

## Блоки и инструкции

### pages — Страницы

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `create-and-edit-page` | Создать и отредактировать страницу | `test_wiki_workspace.py` | ✅ |
| 1 | `navigate-tree` | Навигация по дереву | `test_wiki_workspace.py` | ✅ |
| 1 | `wiki-complete-guide` | Полный маршрут: дерево → страница → блоки → публикация (featured) | `test_wiki_doc_complete_guide.py` | ✅ |
| 2 | `editor-blocks` | Блочный редактор: заголовки, списки, вставки | `test_wiki_doc_editor.py` | ✅ |
| 2 | `page-move-and-reorder` | Перемещение и порядок в дереве | `test_wiki_workspace.py` | ✅ |

### search — Поиск

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `search-pages` | Поиск по тексту | `test_wiki_workspace.py` | ✅ |
| 2 | `semantic-vs-text-search` | Поиск по смыслу (RAG) | новый — нужен `rag_service` | 📝 |

### access — Доступ

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `public-link` | Публичная ссылка на раздел | `test_wiki_workspace.py` | ✅ |
| 3 | `access-roles` | Роли читатель/редактор в пространстве | новый | 📝 |

## Долг и заметки

- Существующие 4 инструкции тонкие (3–4 шага, без `details`) — при углублении поднять до контракта documentator: details, демонстрация, итог. label_en/screenshot_name добавлены в Wave 0.
- featured_slug: `create-and-edit-page` → после появления `wiki-complete-guide` переключить.
