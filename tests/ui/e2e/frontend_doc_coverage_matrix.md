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
| 1 | `profile-and-settings` | Профиль и настройки компании | `test_frontend_doc_console.py` | ✅ |
| 2 | `mail-connect-and-inbox` | Почта из user-menu: ящик, входящие, чтение | `test_frontend_doc_console.py` | ✅ |
| 2 | `calendar-modal` | Календарь из user-menu | `test_frontend_doc_console.py` | ✅ |

### getting-started — С чего начать (frontend)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `dashboard-tour` | Дашборд: что видит сотрудник | `test_frontend_doc_dashboard.py` | ✅ |

### general — Общее (frontend)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `sign-in` | Вход в платформу | `test_frontend_doc_console.py` | ✅ |
| 1 | `select-company` | Выбор компании для работы | `test_frontend_doc_console.py` | ✅ |
| 1 | `invite-team-member` | Пригласить коллегу по ссылке | `test_frontend_doc_console.py` | ✅ |
| 1 | `join-company` | Вход по приглашению (вход + принятие) | `test_frontend_doc_console.py` | ✅ |
| 2 | `company-settings` | Настройки компании: имя, бюджет, подключения | `test_frontend_doc_console.py` | ✅ |
| 2 | `support` | Публичная страница поддержки | `test_frontend_doc_console.py` | ✅ |
| 2 | `search-everything` | Поиск встроенным движком | `test_frontend_doc_console.py` | ✅ |
| 2 | `access-explorer` | Кто и почему имеет доступ | `test_frontend_doc_console.py` | ✅ |
| 3 | `company-variables` | Переменные компании | `test_frontend_doc_console.py` | ✅ |
| 3 | `billing-and-limits` | Тариф, расход, счета | `test_frontend_doc_console.py` | ✅ |
| 3 | `api-keys-create` | API-ключ для интеграции | `test_frontend_doc_console.py` | ✅ |
| 3 | `scheduler-tasks` | Расписания фоновых задач | `test_frontend_doc_console.py` | ✅ |
| 3 | `embed-widget` | Чат-виджет агента на сайте | `test_frontend_doc_console.py` | ✅ |
| 3 | `voice-providers` | Голосовые провайдеры и произношение | `test_frontend_doc_console.py` | ✅ |

### namespaces — Пространства (frontend)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `console-namespaces` | Управление пространствами | `test_frontend_namespaces.py` | ✅ |

## Покрытие вне этой матрицы

- Все страницы из таблицы поверхностей покрыты сценариями выше. `join` покрыт
  `join-company`: аноним видит превью и OAuth-кнопки, вошедший — кнопку принятия.
- Worktracker `my-tasks` («Мои задачи» сотрудника) покрыт в
  `test_worktracker_operators.py`, сервис `worktracker`, тег `general`.
- Access: OpenFGA-грант сеется напрямую через `authz_service.write`; фильтр чипа `platform_namespace` оставляет в кадре только понятные права на пространства (в общей БД копятся технические гранты ящиков/документов).
- Voice: карточки только STT/TTS (`KINDS`), VAD на странице нет; словарь произношения — реальные правила + dry-run подмена текста.
- Login/select-company: cookie-баннер на /login лежит под auth-модалкой — снятие через `dispatch_event('click')` на кнопке «OK»; PWA-промпт скрыт состоянием «вернувшийся пользователь» (`localStorage` dismissed-ключ).
- Mail: сид — `flows_seed_ui_mail_mailbox` (ACTIVE connection + USER binding) + `StoredMailMessage` в `INBOX`. Живой IMAP-синк в стеке недоступен — показывается local-first состояние (папки/письма из общей БД).
- Search: `public_search_run` идёт через flow → runet-индекс. Если SERP в стеке пуст — документируем страницу и честное состояние результатов.
