# CRM (NetWorkle) — матрица покрытия документационными инструкциями

Статусы: ✅ опубликовано · 🚧 в работе · 📝 запланировано · ⛔ не документируем.

`crm-app`, `/crm/` на `system.<subdomain>:9003`, fixture `crm_ui`
(зависит от `crm_service` + `rag_service`).

## UI-поверхности (16 страниц)

| Страница | Что видит пользователь |
|---|---|
| `namespaces-page`, `crm-namespace-page`, `namespace-detail-page` | Пространства — контейнеры сущностей |
| `entities-page`, `entity-create-page`, `entity-detail-page` | Записи CRM и их карточки |
| `graph-page` | Граф связей сущностей |
| `daily-notes-page`, `note-page` | Ежедневные заметки |
| `tasks-page`, `namespace-tasks-page` | Задачи |
| `suggests-page` | Быстрые предложения/разбор |
| `templates-page` | Шаблоны пространств |
| `relationship-types-page` | Типы связей |
| `access-requests-page` | Заявки на доступ |
| `namespace-integrations-page` | Интеграции пространства |
| `settings-hub-page` | Хаб настроек |

## Блоки и инструкции

### general — Общее

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `crm-shell` | Оболочка сервиса | готовый | ✅ |
| 1 | `crm-settings-hub` | Хаб настроек | готовый | ✅ |
| 1 | `crm-first-entity` | Пространство → тип → первая запись (featured) | `test_crm_doc_getting_started.py` | ✅ |
| 1 | `crm-namespaces-tour` | Пространства и что в них живёт | `test_crm_doc_getting_started.py` | ✅ |

### entities (новый тег)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `entity-detail-and-links` | Карточка записи и связи | `test_crm_doc_entities.py` | 📝 |
| 2 | `graph-explore` | Граф связей: навигация и фильтры | `test_crm_graph_workspace.py` | 📝 |
| 3 | `relationship-types` | Свои типы связей | новый | 📝 |

### notes (новый тег)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `daily-notes` | Ежедневные заметки и привязка к записям | `test_crm_doc_notes.py` | ✅ |
| 2 | `suggests-quick-add` | Быстрый разбор предложений | `test_crm_doc_notes.py` | 📝 |
| 3 | `ai-note-analysis` | AI-анализ заметки | проверить стабильность MockLLM | 📝 |

### tasks — Задачи

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `hitl-open-from-crm` | Открыть задачу из CRM | `test_hitl_operator_matrix.py` | ✅ |
| 2 | `tasks-in-crm` | Задачи пространства | `test_crm_tasks_workspace.py` | ✅ |

### setup (новый тег)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 3 | `templates-library` | Пространство из шаблона | новый | 📝 |
| 3 | `access-requests` | Заявки и гранты доступа | новый | 📝 |
| 3 | `namespace-integrations` | Подключения пространства | новый | 📝 |

## Долг и заметки

- Существующие e2e: `test_crm_graph_workspace.py`, `test_crm_tasks_workspace.py` — часть маршрутов уже прогнана, добавить маркеры.
- featured_slug: `crm-first-entity` (после создания; до него — `crm-shell`).
- Теги `entities`/`notes`/`setup` добавить в taxonomy по мере появления первых сценариев (иначе warning unused-tag).
