# Sync UI: маршруты и покрытие E2E

Справочник для Playwright E2E (`tests/ui/e2e/test_sync_*.py`). Полный перечень WS/REST-операций — `SYNC_OPERATIONS` в `apps/sync/realtime/command_router.py`; дублировать все операции в Playwright не требуется.

## Маршруты `sync-app` (`apps/sync/ui/app/sync-app.js`)

| routeKey | path | Smoke / сценарии в E2E |
|----------|------|-------------------------|
| shell | `/sync/` | `test_sync_smoke.py`, создание space/channel в нескольких тестах |
| channel | `/sync/c/:channelId` | `test_sync_channels_and_chat.py`, `test_sync_threads_and_actions.py`, `test_sync_forward_pin.py`, … |
| settings | `/sync/settings` | `test_sync_routes_smoke.py` |
| calls_scheduled | `/sync/calls/scheduled` | `test_sync_routes_smoke.py` |
| call_join | `/sync/join/:linkToken` | `test_sync_calls.py` (неверный токен и др.) |

## Уже существующие `test_sync_*.py` (кратко)

| Файл | Назначение |
|------|------------|
| `test_sync_smoke.py` | Загрузка `sync-app` |
| `test_sync_create_space.py` | Создание пространства |
| `test_sync_spaces.py` | Пространства |
| `test_sync_channels_and_chat.py` | Topic-канал, отправка сообщения |
| `test_sync_navigation.py` | Deep link `?channel=` |
| `test_sync_direct.py` | Direct-чаты |
| `test_sync_threads_and_actions.py` | Reply, треды, реакция, редактирование, удаление |
| `test_sync_files.py` | Вложение PNG |
| `test_sync_mentions.py` | Упоминания |
| `test_sync_mobile.py` | Мобильная вёрстка |
| `test_sync_settings_and_profile.py` | Мьют канала, профиль из пузырька |
| `test_sync_calls.py` | Звонки, оверлей, join |

## Добавлено в этой волне

| Файл | Назначение |
|------|------------|
| `test_sync_channel_edit.py` | Редактирование канала (имя, сохранение из шапки/футера, добавление участников) |
| `test_sync_forward_pin.py` | Пересылка сообщения, закрепление, pin-strip |
| `test_sync_routes_smoke.py` | `/sync/settings`, `/sync/calls/scheduled` |
| `test_sync_namespace.py` | Селектор namespace в сайдбаре, список каналов не ломается |

Создание канала и открытие чата: `sync_e2e_helpers.sync_e2e_click_create_channel`, `sync_e2e_create_topic_channel_and_open`, `sync_e2e_create_topic_channel_in_current_space` (кнопка «+» в сайдбаре, модалка `sync-channel-create-modal`).

## Второй пользователь / LiveKit

Сценарии с двумя браузерами и реальным входящим звонком не включены: зависят от стабильности LiveKit в CI. При необходимости смотреть фикстуры `ui_page_system_member` и `test_sync_calls.py`.
