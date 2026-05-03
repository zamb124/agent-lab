# Тесты Sync Service

## Принципы

- Реальная PostgreSQL (`DATABASE__SYNC_URL` / `tests/fixtures/test_database_env.py`), миграции Alembic для сервиса `sync`.
- Без моков репозиториев, `op_*` (`apps/sync/realtime/operations.py`), Redis Pub/Sub и WebSocket.
- TaskIQ: очередь `sync` — для heavy-задач (`messages.transcribe_*`, `sync_finalize_recording_task`); для них нужен **реальный** `sync_worker` ([`tests/fixtures/workers.py`](../fixtures/workers.py)). Все остальные mutating-команды исполняются in-process в `op_*`.
- Redis: `DATABASE__REDIS_URL` / `TASKS__BROKER_URL` как в корневом [`tests/conftest.py`](../conftest.py).
- STT: без патча фабрик клиентов. В корневом `tests/conftest.py`, [`tests/fixtures/services.py`](../fixtures/services.py) и env процесса **`sync_worker`** заданы `VOICE__STT__PROVIDER=mock` и `VOICE__STT__MOCK_TRANSCRIPT_TEXT` (см. [`tests/fixtures/workers.py`](../fixtures/workers.py)).

Запрещено:

- `unittest.mock.*`, `AsyncMock`, `MagicMock`, `@patch` в любых тестах sync.
- `monkeypatch` для подмены внутренностей. Подмена внешних настроек (например `s3.enabled`) — через `_temporary_settings` ([`integration/conftest.py`](integration/conftest.py)).

Внешний Web Push (`webpush` к FCM/APN) проверяется в [`tests/core/push/test_push_service.py`](../core/push/test_push_service.py); в sync-тестах он не используется.

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
| Репозитории (база) | `db/test_*_repository.py` | Channel, Message, Thread, File, GitResourceRef |
| Репозитории (расширение) | `db/test_message_repository_extended.py`, `db/test_channel_repository_extended.py` | `get_by_id_for_company`, замена контента, удаление, реакции, `max_root_lane_sent_at`, `get_thread_root`, пагинация; `list_for_user` + `namespace`, `is_member`, `set_pinned_message_ids` |
| Хелперы чтения | `test_read_helpers_integration.py` | `channel_read_from_entity`, `message_read_from_entity` |
| WS command-router | `realtime/test_command_router.py` | `register_sync_ws_commands()`: каждая запись `SYNC_OPERATIONS` зарегистрирована, `canonical_type` совпадает с ключом, `_requested` суффикс |
| Presence hooks | `realtime/test_presence_hooks.py` | Connect/disconnect: online/offline в Redis presence |
| Finalize recording | `realtime/test_finalize_recording_platform_file.py` | Регистрация platform `FileRecord` после записи звонка |
| **WS=REST identity** | `integration/test_ops_ws_rest_identical.py` | Каждая op из `SYNC_OPERATIONS` даёт одинаковый result через WS и REST |
| **Zero-fallback red-tests** | `integration/test_ops_zero_fallback.py` | Missing field → `ws_invalid_payload`, no company → `ws_no_company`, not_found → 404/`not_found` |
| **AST-сканер** | `integration/test_no_silent_except_in_ops.py` | Запрет `except Exception: pass`, `or default` фолбеков в `operations.py` |
| **Push-events** | `integration/test_op_publish_realtime_events.py` | После op в `platform:ui_events` опубликован нужный фрейм с правильным `recipient_user_ids` |
| **op_messages_*** | `integration/test_op_messages_send.py`, `_edit_delete_forward.py`, `_react_pin.py` | Send + auto-transcribe; edit/delete/forward; react/pin |
| **op_channels_*** | `integration/test_op_channels_lifecycle.py`, `_notification_settings.py` | direct/topic/calendar_meeting; mute/unmute |
| **op_calls_*** | `integration/test_op_calls_lifecycle.py`, `_links.py` | invite/accept/hangup + recording; calendar links + join |
| **op_threads_*** | `integration/test_op_threads.py` | Create/list/item, изоляция по company |
| **op_git_resources_*** | `integration/test_op_git_resources.py` | upsert/get + изоляция |
| HTTP (smoke) | `api/test_sync_http.py` | GET namespaces (default), PUT sync_settings, список каналов |
| HTTP (матрица) | `api/test_sync_http_matrix.py` | 401, 403/404, цепочка сообщений + read, cursor пагинация |
| HTTP (вложения) | `api/test_sync_messages_attachments.py` | Загрузка multipart + сообщение с file/* |
| WebSocket | `api/test_sync_websocket.py` | `channels.create` через WS, 403 без cookie, ошибка команды |
| WebSocket (broadcast 2 клиента) | `api/test_sync_websocket_broadcast.py` | Два пользователя получают `message.created` |
| **WS realtime E2E** | `api/test_sync_realtime_e2e.py` | 3-broadcast, reaction, reply, edit, delete, read_updated, forward, mention — все push-фреймы, без моков |
| **История чата E2E** | `api/test_sync_history_e2e.py` | Свежий HTTP-клиент видит историю, before-cursor пагинация, исключение удалённых, edit + react в ленте |
| **Skip-rules уведомлений** | `api/test_notification_skip_rules_e2e.py` | `notify/sync/sync_new_message_received` skip по WS-presence и по mute; mention доставляется даже при онлайне |
| Голос / флаг канала | `api/test_channel_voice_transcribe_flag.py` | `transcribe_voice_messages` через **`sync_service` + sync_worker** |
| STT REST + звонок | `api/test_transcribe_video_and_call_http.py` | `transcribe-video`, `transcribe-call` через worker |
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
