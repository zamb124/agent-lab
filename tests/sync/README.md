# Тесты Sync Service

## Принципы

- Реальная PostgreSQL (`DATABASE__SYNC_URL` / `tests/fixtures/test_database_env.py`), миграции Alembic для сервиса `sync`.
- Без моков репозиториев, `execute_command`, `dispatch_sync_command`, `handle_command.kiq`, Redis Pub/Sub и WebSocket.
- TaskIQ: очередь `sync` — для HTTP/WS, где вызывается `handle_command.kiq()`, нужен **реальный** `sync_worker` ([`tests/fixtures/workers.py`](../fixtures/workers.py)).
- Redis: `DATABASE__REDIS_URL` / `TASKS__BROKER_URL` как в корневом [`tests/conftest.py`](../conftest.py).

Подробнее: `.cursor/rules/sync.mdc` (раздел «Тестирование»), `.cursor/rules/testing.mdc`.

## Запуск

```bash
uv run pytest tests/sync/ -v
```

Для тестов загрузки файлов нужны MinIO/S3 (см. переменные `S3__*` в окружении) и `S3__ENABLED=true`. Тест `test_upload_returns_503_when_s3_disabled_via_env` временно выключает S3 через `S3__ENABLED=false` и сброс глобальных настроек.

## Критерии готовности (green)

1. `uv run pytest tests/sync/ -v` проходит целиком при поднятой инфраструктуре: Postgres (порты из `TEST_DATABASE_ENV`), Redis (`63792`), MinIO для S3-веток (если включены тесты файлов), процесс **Sync HTTP** на `9005` для WebSocket-тестов, **sync_worker** в фикстурах.
2. Нет подмены внешних клиентов: используются реальные БД, Redis, TaskIQ, при необходимости — отдельный ASGI-клиент с другим `S3__ENABLED` без мока S3-клиента.

## Матрица покрытия

| Слой | Файлы | Что проверяется |
|------|--------|-----------------|
| Репозитории (база) | `db/test_*_repository.py` | Space, Channel, Message, Thread, File, GitResourceRef |
| Репозитории (расширение) | `db/test_message_repository_extended.py`, `db/test_channel_repository_extended.py` | `get_by_id_for_company`, замена контента, удаление, реакции, `max_root_lane_sent_at`, `get_thread_root`, пагинация; `list_for_user` + `space_id`, `is_member`, `set_pinned_message_ids`, ошибки `set_member_last_read_at` |
| Пространства | `db/test_space_repository.py` | В т.ч. `get_by_name` при одинаковом имени в разных компаниях |
| Хелперы чтения | `test_read_helpers_integration.py` | `channel_read_from_entity` (direct + peer, topic + lane summary), `message_read_from_entity` |
| Команды (happy path) | `realtime/test_handlers_execute_command.py` | `execute_command` по основным `CommandType` |
| Команды (негативы) | `realtime/test_handlers_errors.py` | direct/topic/channel update, сообщения (чужой автор, удаление, forward/react/pin, несовпадение канала), тред без root, идемпотентность git upsert |
| Dispatch + Redis | `realtime/test_dispatch_redis_publish.py` | После `dispatch_sync_command` подписчик на `sync.realtime.events` получает JSON события |
| HTTP (smoke) | `api/test_sync_http.py` | Список/создание space, patch, каналы |
| HTTP (матрица) | `api/test_sync_http_matrix.py` | 401 без Bearer, 403/404 по каналам и тредам, company members, git GET/POST, цепочка сообщений + read |
| WebSocket | `api/test_sync_websocket.py` | Успех через TaskIQ, отказ без cookie (403 handshake), `ok: false` при ошибке задачи, две команды подряд |
| Файлы | `api/test_sync_files_upload.py`, `api/test_sync_files_negative.py` | Загрузка при S3; пустой файл 400; метаданные 404; 503 при `S3__ENABLED=false` через env |
| Маршруты | `test_route_config.py` | Публичные/защищённые пути AuthMiddleware |
| Unit | `unit/test_sync_commands_pydantic.py` | Валидация DTO команд |

## Фикстуры

- [`conftest.py`](conftest.py): `sync_database`, `sync_db_clean`, репозитории, `company_id`, `unique_id`, `sync_user_repository`.
- [`tests/sync/realtime/conftest.py`](realtime/conftest.py): autouse `get_context()` для handler-тестов (`company_id` совпадает с данными в БД).
- [`tests/fixtures/clients.py`](../fixtures/clients.py): `sync_app`, `sync_client` (зависят от `sync_worker`).
- [`tests/fixtures/services.py`](../fixtures/services.py): `sync_service` (порт 9005) для WebSocket.
