---
name: new-service
description: "Добавить сервис в Платформу: apps/<svc> layout, порт в _default_ports, база и миграции, TaskIQ-очередь и воркер, Helm-деплой, правило <svc>.mdc и строка в main.mdc"
---

# Новый сервис Платформы

Порядок — снизу вверх: модель → DI → транспорт → топология → деплой → правила. Каждый шаг завершается зелёным `make lint` и `rules_drift`.

## 1. Пакет `apps/<svc>/`

Минимальный состав (канон — `main.mdc` § Стандарт сервиса, `architecture.mdc`):

- `config.py` — `<Svc>Settings` (наследник core `BaseSettings`); секции — только нужные компонентам.
- `di.py` — `<Svc>Di(PlatformDi)`, `Di = Annotated[<Svc>Di, http_di(<Svc>Di), task_di(<Svc>Di)]`.
- `main.py` — `create_service_app("<svc>", <Svc>Settings, <Svc>Di, database="<svc>_url", operations=<SVC>_OPERATIONS, routers=[...], services_spa_index=...)`; app-level поведение — только параметрами фабрики (`extra_middlewares`/`outer_middlewares`), не `app.add_middleware`.
- `api/` — REST-зеркала команд: тот же Pydantic payload, тот же `op_*`; path-id = поле payload.
- `realtime/command_router.py` — `<SVC>_OPERATIONS: dict[str, RegisteredOperation[<Svc>Di]]`; `operations.py` — `async def op_<entity>_<verb>(payload, *, user: User, di: Di)`.
- `models/<entity>.py` — Oxyde-модели (`__global_model__` при company-scope); таблица `__<svc>_<entity>`.
- `services/` — доменная логика: конкретные зависимости в `__init__`, не `di`.
- `events.py` — push-типы `<svc>/<entity>/<verb>`; импорт side-effect в `main.py`.
- `worker.py` + `tasks/task_names.py` + `tasks/*_tasks.py`, если есть фон и очередь: `wire_worker("<queue>")` + `build_worker(..., di_class=<Svc>Di, database="<svc>_url")`.
- `authz/` — если новый FGA-тип: tuple-helpers `sync_<resource>_created|deleted`, backfill.
- `ui/` — SPA `index.html` + `<svc>-app.ts`, фабрики `transport: 'ws'` + `restMirror`.

## 2. Порт и конфиг

- `core/config/models.py::_default_ports` — `"<svc>": <port>`; URL peer-сервиса — `get_service_url("<svc>")`, env `SERVER__<SVC>_SERVICE_URL`.
- База: секция `database.<svc>_url` + env `DATABASE__<SVC>_URL`; первая миграция `migrations/<svc>/0001_initial.py`; алиас Oxyde — в `create_service_app(database="<svc>_url")`.
- Публичные (anonymous) пути — `RouteRule` в `core/middleware/auth/route_config.py`.

## 3. Очередь и воркер

- `apps/worker_manifest.py`: `_QUEUE_SERVICE` (`"<queue>": "<svc>_worker"`) и `_QUEUE_TASK_MODULES`.
- `mprocs.yaml` — процесс `<svc>` (`python -m scripts.dev.run <svc>`) и `<svc>_worker` при очереди.
- `scripts/testing/stack.py` — `ServiceSpec` сервиса и воркера (env, порт, health).

## 4. Деплой

- `deploy/helm/agent-lab/values.yaml`: `deployments.<svc>` (`serviceName`, `port`, `command granian`); при воркере — `workers.<svc>_worker`; ingress — шаблон в `templates/80-ingress/` при публичном хосте.
- Секреты — через `platformSecrets`/`env`, не в values открытым текстом → `infrastructure.mdc`.

## 5. Правила и реестры

- `.cursor/rules/<svc>.mdc` — доменное правило по шаблону `rules.mdc` (Модель → Инварианты → Контракты → Интеграции → UI → Запреты → Исключения → Гейты).
- `main.mdc`: строка в «Сервисы и стек», владелец доменов в «Владельцы», `<svc>` в «Навигации», очередь — в списке воркеров.
- Протокольные хендлеры без `op_*` — только через `PROTOCOL_HANDLERS` (`scripts/gates/backend/rest_handlers_call_ops.py`).

## Проверка

`make lint`, `uv run python -m scripts.gates.repo.rules_drift`, `make test-up` + `uv run pytest tests/<svc>/ -q`, `make app` — сервис отвечает на `/health`.
