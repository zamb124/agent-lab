# Тесты Sync Service

## Принципы

- Реальная PostgreSQL (`DATABASE__SYNC_URL` / `tests/fixtures/test_database_env.py`), миграции Alembic для сервиса `sync`.
- Без моков репозиториев, `op_*` (`apps/sync/realtime/operations.py`), Redis Pub/Sub и WebSocket.
- TaskIQ: очередь `sync` — для heavy-задач (`messages.transcribe_*`, `sync_finalize_recording_task`); для них нужен **реальный** `sync_worker` ([`tests/fixtures/workers.py`](../fixtures/workers.py)). Все остальные mutating-команды исполняются in-process в `op_*`.
- Redis: `DATABASE__REDIS_URL` / `TASKS__BROKER_URL` как в корневом [`tests/conftest.py`](../conftest.py).
- STT: без патча `STTClientFactory`. В корневом `tests/conftest.py`, [`tests/fixtures/services.py`](../fixtures/services.py) и env процесса **`sync_worker`** заданы `STT__PROVIDER=mock` и `STT__MOCK_TRANSCRIPT_TEXT` (см. [`tests/fixtures/workers.py`](../fixtures/workers.py)).

Единственное явно разрешённое исключение для моков — внешний Web Push к FCM/APN
(`@patch("core.push.service.webpush")` в [`test_sync_notification_delivery.py`](test_sync_notification_delivery.py)):
без device tokens и VAPID-ключей в CI его нельзя вызвать «по-настоящему». Зафиксировано
в [`.cursor/rules/testing.mdc`](../../.cursor/rules/testing.mdc).

Подробнее: `.cursor/rules/sync.mdc` (раздел «Тестирование»), `.cursor/rules/testing.mdc`.

## Запуск

```bash
uv run pytest tests/sync/ -v
```

В тестовом окружении MinIO и bucket обязательны. Корневой [`tests/conftest.py`](../conftest.py) задаёт `S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL=http://localhost:19002`, чтобы совпадать с `minio-test` из `docker-compose-test.yaml`.

## Критерии готовности (green)

1. `uv run pytest tests/sync/ -v` проходит целиком при поднятой инфраструктуре: Postgres (порты из `TEST_DATABASE_ENV`), Redis (`63792`), MinIO с bucket из конфига, процесс **Sync HTTP** на `9005` для WebSocket-тестов, **sync_worker** в фикстурах.
2. `uv run pytest tests/sync/integration -v --cov=apps/sync/realtime --cov-fail-under=95` — coverage реестра/операций ≥95%.
3. Нет подмены внутренних компонентов: реальные БД, Redis, TaskIQ, LiveKit (через `livekit-cli-test` контейнер).

## Архитектура операций (источник правды)

Реестр операций — `apps/sync/realtime/command_router.py::SYNC_OPERATIONS`
(49 записей). Один handler — оба транспорта:

- **WS** — фрейм `{request_id, type: 'sync/<entity>/<verb>_requested', payload}` →
  `_make_ws_handler(op)` валидирует payload через Pydantic и зовёт `op.fn(...)`.
- **REST** — route в `apps/sync/api/**` собирает Pydantic payload и зовёт ту же
  `op.fn(...)`. `WsCommandError` маппится в `HTTPException` через
  `@app.exception_handler` в `apps/sync/main.py`.

TaskIQ остаётся ТОЛЬКО для heavy-операций (`sync_transcribe_*_message_task`,
`sync_finalize_recording_task`).

## Матрица покрытия

| Слой | Файлы | Что проверяется |
|------|--------|-----------------|
| Репозитории (база) | `db/test_*_repository.py` | Space, Channel, Message, Thread, File, GitResourceRef |
| Репозитории (расширение) | `db/test_message_repository_extended.py`, `db/test_channel_repository_extended.py` | `get_by_id_for_company`, замена контента, удаление, реакции, `max_root_lane_sent_at`, `get_thread_root`, пагинация; `list_for_user` + `space_id`, `is_member`, `set_pinned_message_ids` |
| Пространства | `db/test_space_repository.py` | В т.ч. `get_by_name` при одинаковом имени в разных компаниях |
| Хелперы чтения | `test_read_helpers_integration.py` | `channel_read_from_entity`, `message_read_from_entity` |
| WS command-router | `realtime/test_command_router.py` | `register_sync_ws_commands()`: каждая запись `SYNC_OPERATIONS` зарегистрирована, `canonical_type` совпадает с ключом, `_requested` суффикс |
| Presence hooks | `realtime/test_presence_hooks.py` | Connect/disconnect: online/offline в Redis presence |
| Finalize recording | `realtime/test_finalize_recording_platform_file.py` | Регистрация platform `FileRecord` после записи звонка |
| **WS=REST identity (49 op)** | `integration/test_ops_ws_rest_identical.py` | Каждая op из `SYNC_OPERATIONS` даёт одинаковый result через WS и REST |
| **Zero-fallback red-tests** | `integration/test_ops_zero_fallback.py` | Missing field → `ws_invalid_payload`, no company → `ws_no_company`, not_found → 404/`not_found` |
| **AST-сканер** | `integration/test_no_silent_except_in_ops.py` | Запрет `except Exception: pass`, `or default` фолбеков в `operations.py` |
| **Push-events** | `integration/test_op_publish_realtime_events.py` | После op в `platform:ui_events` опубликован нужный фрейм с правильным `recipient_user_ids` |
| **op_messages_*** | `integration/test_op_messages_send.py`, `_edit_delete_forward.py`, `_react_pin.py` | Send + auto-transcribe; edit/delete/forward; react/pin |
| **op_channels_*** | `integration/test_op_channels_lifecycle.py`, `_notification_settings.py` | direct/topic/calendar_meeting; mute/unmute |
| **op_calls_*** | `integration/test_op_calls_lifecycle.py`, `_links.py` | invite/accept/hangup + recording; calendar links + join |
| **op_threads_*** | `integration/test_op_threads.py` | Create/list/item, изоляция по company |
| **op_git_resources_*** | `integration/test_op_git_resources.py` | upsert/get + изоляция |
| **op_spaces_*** namespace | `integration/test_op_spaces_namespace_uniqueness.py` | namespace 1:1 с SyncSpace, конфликт между компаниями |
| HTTP (smoke) | `api/test_sync_http.py` | Список/создание space, patch, каналы |
| HTTP (матрица) | `api/test_sync_http_matrix.py` | 401, 403/404, цепочка сообщений + read |
| HTTP (вложения) | `api/test_sync_messages_attachments.py` | Загрузка multipart + сообщение с file/* |
| WebSocket | `api/test_sync_websocket.py` | `spaces.create` через WS, 403 без cookie, ошибка команды |
| WebSocket (broadcast) | `api/test_sync_websocket_broadcast.py` | Два пользователя получают `message.created` |
| Голос / флаг канала | `api/test_channel_voice_transcribe_flag.py` | `transcribe_voice_messages` через **`sync_service` + sync_worker** |
| STT REST + звонок | `api/test_transcribe_video_and_call_http.py` | `transcribe-video`, `transcribe-call` через worker |
| Платформенные уведомления | `test_sync_notification_delivery.py` | `deliver_channel_message_notification`: presence/mute/payload, Redis `platform:notifications`, Web Push (с моком `webpush` — внешняя FCM) |
| Файлы | `api/test_sync_files_upload.py`, `api/test_sync_files_negative.py` | Загрузка при S3; пустой файл 400; 503 при S3 disabled (через fixture-runtime, без `monkeypatch`) |
| Маршруты | `test_route_config.py` | Публичные/защищённые пути AuthMiddleware |
| Unit | `unit/test_sync_commands_pydantic.py` | Валидация Pydantic payload-моделей операций |

## Фикстуры

- [`conftest.py`](conftest.py): `sync_database`, `sync_db_clean`, репозитории, `company_id`, `unique_id`, `sync_user_repository`.
- [`integration/conftest.py`](integration/conftest.py): `op_caller` (REST/WS обёртка), `redis_pubsub_listener`, `_normalize_result`, `_s3_disabled_settings`.
- [`realtime/conftest.py`](realtime/conftest.py): autouse `get_context()` для тестов helpers.
- [`tests/fixtures/clients.py`](../fixtures/clients.py): `sync_app`, `sync_client`.
- [`tests/fixtures/services.py`](../fixtures/services.py): `sync_service` (порт 9005) для WebSocket.
- [`tests/fixtures/workers.py`](../fixtures/workers.py): `sync_worker` (TaskIQ для transcribe_*).
