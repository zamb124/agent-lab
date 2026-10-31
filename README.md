# Платформа (linnex.io)

Платформа для ИИ-агентов (Flows), командного чата (Sync), графа знаний (NetWorkle/CRM), семантического поиска (RAG), документов (Office), задач (Worktracker) и голоса (Voice). Primary apex — **linnex.io**; также доступна на **linnex.io** и других доменах из `platform_brands` ([`configuration.mdc`](.cursor/rules/configuration.mdc)).

**Инвариант**: Database-First — конфигурация flows, tools и resources в базе данных; код задаёт только поведение.

## Документация

| Раздел | Где |
|---|---|
| Пользовательский портал | `make doc` / `make doc-serve` → `/documentation/` |
| Исходники документации | [doc-sources.md](doc-sources.md) |
| Быстрый старт интеграции (A2A) | [docs/quickstart.md](docs/quickstart.md) |
| E2E-инструкции | [docs/scenarios/](docs/scenarios/) |
| OpenAPI | [docs/openapi/](docs/openapi/) → генерируется в портал |
| Деплой | [deploy/README.md](deploy/README.md), [deploy/cluster-setup.md](deploy/cluster-setup.md) |
| CRM, RAG, LitServe | [apps/crm/README.md](apps/crm/README.md), [apps/rag/README.md](apps/rag/README.md), [apps/provider_litserve/README.md](apps/provider_litserve/README.md) |
| Канон разработки | [.cursor/rules/](.cursor/rules/) |

Полный список команд: `make help`.

## Быстрый старт

### Локальная разработка

```bash
# Python 3.14t (free-threaded, PEP 779) — один раз
uv python install 3.14t

# Зависимости (uv подхватит .python-version=3.14t)
uv sync

# Browser Runtime (Playwright + CDP): зависимость в группе browser
uv sync --group browser

# Локальные секреты (OAuth, LLM-ключи) — скопировать и заполнить
cp conf.local.json.example conf.local.json

# Инфраструктура (Postgres :54321, Redis :63791, SeaweedFS :19001/19011, Chromium CDP :9222)
make dev-up

# Создать недостающие БД + Alembic upgrade
make dev-bootstrap-postgres

# Все HTTP-сервисы и TaskIQ-воркеры (Granian с --reload)
make app   # mprocs: раздельные логи по сервису (brew install mprocs)
# или с предварительным освобождением портов:
make app APP_KILL=1
# исключить сервис из all:
make app ex flows_worker
```

HTTP-сервисы стартуют через **Granian** (Rust ASGI, не uvicorn). `runtime-bootstrap` вызывается автоматически из `dev-up` и `app`. В docker/k8s `PYTHON_GIL=0` задан в окружении. `apps/provider_litserve` и `apps/rag` импортируют HuggingFace-стек — внутри их процесса CPython автоматически включает GIL (known limitation, фиксируется в startup-логе и OTEL).

Один сервис: `uv run python -m scripts.dev.run <service>` (реестр — [scripts/dev/run.py](scripts/dev/run.py)).

Конфигурация: каскад ENV → `conf.json` / `conf.local.json` → defaults через Pydantic Settings. Подробности — [.cursor/rules/configuration.mdc](.cursor/rules/configuration.mdc).

### Тесты и линтеры

```bash
make lint            # ruff + basedpyright + architecture gates + frontend canon
make test            # python lint + frontend-core + unit + retry-failed
make test-unit       # Только unit/API (без UI)
make test-rag        # RAG-тесты с pgvector + SeaweedFS
make test-ui         # Playwright E2E
make ui-doc          # UI + E2E doc scenarios + сборка docs/scenarios
```

### Документация локально

```bash
make doc             # Zensical RU + EN → documentation-dist/
make doc-serve       # Локальный предпросмотр RU-сайта
```

## Сервисы и порты

Канон портов — [scripts/dev/run.py](scripts/dev/run.py).

| Сервис | Порт | Назначение |
|---|---|---|
| flows | 8001 | Графы, branches, A2A, durable runtime |
| frontend | 8002 | Платформенный UI, auth, billing, settings |
| crm | 8003 | Entities, graph, access control (NetWorkle) |
| rag | 8004 | Документы, семантический поиск |
| sync | 8005 | Инженерный чат, Git, звонки |
| scheduler-api | 8006 | Scheduler control-plane API |
| office | 8008 | OnlyOffice, путь `/documents` |
| browser | 8009 | Browser Runtime: Playwright + CDP |
| search | 8010 | Search/crawl MCP |
| provider_litserve | 8014 | Embeddings, rerank, локальные STT/TTS/VAD |
| voice | 8015 | Voice gateway; WS `/voice/api/ws/session/{id}` |
| capability_gateway | 8016 | Trusted gateway capabilities, manifest/docs sandbox |
| code_runner_python | 8017 | Изолированное исполнение Python user-code |
| code_runner_node | 8018 | Изолированное исполнение JS/TS user-code |
| code_runner_go | 8019 | Изолированное исполнение Go user-code |
| code_runner_csharp | 8020 | Изолированное исполнение C# user-code |
| worktracker | 8021 | WorkItem, канбан, очереди, HITL |
| secrets | 8022 | Версионируемые переменные и секреты компании |

TaskIQ (без HTTP-порта): `flows_worker`, `rag_worker`, `search_worker`, `sync_worker`, `crm_worker`, `crm_summary_worker`, `idle_worker`, `scheduler`.

## Структура репозитория

```
agent-lab/
├── apps/              # Микросервисы (flows, frontend, crm, rag, sync, office, …)
│   ├── flows/         # Flow runtime, API, UI, bundles
│   ├── frontend/      # Платформенный shell, auth, billing
│   ├── idle/          # TaskIQ без HTTP: очереди idle и a2a_push
│   └── …              # у сервиса с очередью — worker.py и tasks/ в его каталоге
├── core/              # Общая платформа (ai, clients, db, frontend lib, llm_context, …)
├── migrations/        # Alembic per-domain (shared, flows, crm, rag, sync, office, …)
├── tests/             # pytest: core, apps, ui
├── scripts/           # run.py, db_migrate, docs_prepare, …
├── mk/                # app.mk, test.mk, lint.mk, migrate.mk
├── deploy/helm/       # Единый Helm-чарт всего стека
├── docs/              # Zensical-исходники, scenarios, openapi
├── mobile/            # Capacitor iOS/Android
├── conf.json          # Базовая конфигурация
├── conf.local.json    # Локальные секреты (gitignored)
├── pyproject.toml     # UV, dependency groups
├── Makefile           # dev, app, test, lint, k8s, doc, agent
└── docker-compose-dev.yaml
```

## Архитектура

1. **Database-First** — flows, tools, resources и company settings в БД; сборка через фабрики из репозиториев.
2. **Durable graph execution** — исполнение flows через append-only `workflow_events` и reducer; `ExecutionState` — projection, не mutable overwrite.
3. **core.ai** — единый слой provider/capability catalog, resolver и runtime для LLM, embeddings, rerank, image gen.
4. **Микросервисы + DI** — процесс описывает компоненты классом `<Process>Di`; boundary читает их параметром `di`. Доступ к данным peer-домена — модель владельца, не дублирующий REST.
5. **Frontend EventBus** — Lit 3, фабрики (`createAsyncOp`, `createResourceCollection`, …), REST-зеркало WS-команд.
6. **Zero-Guess** — нет фолбеков; недоступная инфраструктура → fail fast на старте.

Детали: [.cursor/rules/architecture.mdc](.cursor/rules/architecture.mdc), [.cursor/rules/flows_runtime.mdc](.cursor/rules/flows_runtime.mdc), [.cursor/rules/ai_models.mdc](.cursor/rules/ai_models.mdc), [.cursor/rules/frontend.mdc](.cursor/rules/frontend.mdc).

## Разработка

| Команда | Назначение |
|---|---|
| `make dev-up` / `make dev-down` | Docker-инфраструктура для dev |
| `make app` | Все сервисы через mprocs (раздельные логи) |
| `make lint` | Полный lint gate (python + frontend) |
| `make test` | CI-прогон unit/API |
| `make test-ui` / `make ui-doc` | Playwright E2E + doc scenarios |
| `make migrate` | Alembic всех сервисных деревьев |
| `make doc` | Zensical RU+EN build |

Миграции: `make migrate-new m="описание" s=shared` (`s` — имя базы из `migrations/services.json`). См. [.cursor/rules/database.mdc](.cursor/rules/database.mdc).

## Технологический стек

- **Python 3.14t** (free-threaded, PEP 779), **UV**, **FastAPI**, **Granian** (Rust ASGI)
- **Pydantic v2**, **SQLAlchemy** async, **Alembic**
- **PostgreSQL** + pgvector, **Redis**, **TaskIQ**, **SeaweedFS**/S3
- **Lit 3**, нативный EventBus, **Playwright**
- Observability (prod): OTEL, Loki, Tempo, Grafana, Alloy
- Документация: **Zensical**

Зависимости и группы — [pyproject.toml](pyproject.toml).

## Production-деплой

Production разворачивается единым **Helm-чартом** в **MicroK8s** (master + GPU worker). Docker Compose в проде не используется.

```bash
make k8s-lint                       # helm lint
make k8s-template                   # рендер манифестов в stdout
make k8s-deploy IMAGE_TAG=<sha>     # helm upgrade --install (ждёт rollout)
make k8s-status                     # nodes + pods + svc + ingress + pvc
make k8s-logs SVC=frontend          # логи Deployment
make k8s-rollback                   # helm rollback
```

Из CI: [.github/workflows/deploy.yml](.github/workflows/deploy.yml) — сборка образа → push в GHCR → `helm upgrade --install` через `KUBECONFIG_B64`.

Стек в кластере: 11 application Deployments, 6 worker Deployments, provider-litserve на GPU-ноде, postgres/redis, LiveKit, OnlyOffice, observability (Loki/Tempo/Grafana/Alloy). Подробности — [deploy/README.md](deploy/README.md), одноразовая настройка — [deploy/cluster-setup.md](deploy/cluster-setup.md).

## License

Copyright (c) 2024-2026 Шведов Виктор Викторович.

Исходный код Платформы распространяется под [Elastic License 2.0](LICENSE)
(SPDX: `Elastic-2.0`). Это source-available лицензия, **не** OSI open source: запрещено
предлагать продукт третьим лицам как hosted или managed service с существенной частью
функциональности платформы.

Сторонние компоненты и зависимости — в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
