# Frontend / Platform — матрица покрытия документационными инструкциями

Статусы: ✅ опубликовано · 🚧 в работе · 📝 запланировано · ⛔ не документируем.

Док-группы: `service="platform"` (оболочка, onboarding, core-поверхности) и
`service="frontend"` (страницы frontend-сервиса). `frontend-app`, `/`, port 9004,
fixture `frontend_ui`. Mail/calendar — модалки из user-menu `platform-user`
(`platform.mail`, calendar) в любом shell → документируем в блоке platform.

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
| 1 | `invite-team-member` | Пригласить коллегу в компанию | новый | 📝 |
| 1 | `profile-and-settings` | Профиль, язык, тема | новый | 📝 |

### mail (новый тег platform)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `mail-connect-and-inbox` | Почта из user-menu: подключение ящика, входящие | проверить IMAP-seed в стеке | 📝 |
| 2 | `calendar-modal` | Календарь из user-menu | новый | 📝 |

### dashboard (новый тег frontend или platform)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `dashboard-tour` | Дашборд: что видит сотрудник | `test_frontend_doc_dashboard.py` | 🚧 |
| 2 | `search-everything` | Поиск по платформе | новый | 📝 |

### settings (frontend)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `company-variables` | Переменные компании | новый | 📝 |
| 3 | `billing-and-limits` | Тариф, лимиты, оплата | новый | 📝 |
| 3 | `api-keys-create` | API-ключ для интеграции | новый | 📝 |
| 3 | `scheduler-tasks` | Расписания фоновых задач | новый | 📝 |

### namespaces — Пространства (frontend)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `console-namespaces` | Управление пространствами | `test_frontend_namespaces.py` | ✅ |

## Долг и заметки

- Сервис `frontend` и `platform` разделены в taxonomy намеренно: platform = shell/user-menu, frontend = страницы компании — уточнить границу при реализации, не плодить дубли.
- Mail: модалка `platform.mail` требует подключённого ящика (core/mail, IMAP) — проверить наличие mail-seed/провайдера в тестовом стеке до написания сценария; без него — только модалка подключения.
- Теги `mail`/`dashboard`/`settings` добавить в taxonomy с первыми сценариями.
