# Frontend / Platform — матрица покрытия документационными инструкциями

Статусы: ✅ опубликовано · 🚧 в работе · 📝 запланировано · ⛔ не документируем.

Док-группы: `service="platform"` (оболочка, onboarding, core-поверхности) и
`service="frontend"` (страницы frontend-сервиса). `frontend-app`, `/`, port 9004,
fixture `frontend_ui`. Mail/calendar — модалки из user-menu `platform-user`
(`platform.mail`, `platform.calendar`) в любом shell → документируем в блоке
platform, тег `tools`.

## UI-поверхности

| Страница | Что видит пользователь |
|---|---|
| `dashboard-page` | Дашборд компании |
| `team/` | Команда и участники |
| `access/` | Доступ и роли |
| `settings/` | Настройки компании |
| `namespaces/` | Пространства |
| `billing/` | Тариф и лимиты |
| `api-keys/` | API-ключи |
| `company-variables/` | Переменные компании |
| `company-voice-providers/` | Голосовые провайдеры |
| `scheduler-tasks-page` | Расписания |
| `search-page` | Поиск по платформе |
| `embed-configs-page` | Встраивания |
| User-menu | Профиль, mail, календарь, документация, язык |
| `select-company`, `join`, `login` | Вход и выбор компании |

## Блоки и инструкции

### onboarding — Первые шаги (platform)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `main-dashboard-user-menu` | Вход, дашборд, user-menu | `test_platform_onboarding_scenarios.py` | ✅ |

### tools — Инструменты (platform)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `profile-and-settings` | Профиль и настройки компании | `test_frontend_doc_console.py` | 🚧 |
| 2 | `mail-connect-and-inbox` | Почта из user-menu: ящик, входящие, чтение | `test_frontend_doc_console.py` | 🚧 |
| 2 | `calendar-modal` | Календарь из user-menu | `test_frontend_doc_console.py` | 🚧 |

### getting-started — С чего начать (frontend)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `dashboard-tour` | Дашборд: что видит сотрудник | `test_frontend_doc_dashboard.py` | ✅ |

### general — Общее (frontend)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `invite-team-member` | Пригласить коллегу по ссылке | `test_frontend_doc_console.py` | 🚧 |
| 2 | `search-everything` | Поиск встроенным движком | `test_frontend_doc_console.py` | 🚧 |
| 3 | `company-variables` | Переменные компании | `test_frontend_doc_console.py` | 🚧 |
| 3 | `billing-and-limits` | Тариф, расход, счета | `test_frontend_doc_console.py` | 🚧 |
| 3 | `api-keys-create` | API-ключ для интеграции | `test_frontend_doc_console.py` | 🚧 |
| 3 | `scheduler-tasks` | Расписания фоновых задач | `test_frontend_doc_console.py` | 🚧 |
| 3 | `embed-widget` | Чат-виджет агента на сайте | `test_frontend_doc_console.py` | 🚧 |

### namespaces — Пространства (frontend)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `console-namespaces` | Управление пространствами | `test_frontend_namespaces.py` | ✅ |

## Покрытие вне этой матрицы

- `access/`, `company-voice-providers/`, `login`/`select-company` — проверить, покрыты ли существующими сценариями (`test_frontend_access.py` и др.), иначе добавить.
- Mail: сид — `flows_seed_ui_mail_mailbox` (ACTIVE connection + USER binding) + `StoredMailMessage` в `INBOX`. Живой IMAP-синк в стеке недоступен — показывается local-first состояние (папки/письма из общей БД).
- Search: `public_search_run` идёт через flow → runet-индекс. Если SERP в стеке пуст — документируем страницу и честное состояние результатов.
