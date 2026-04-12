# Deploy

Деплой запускается вручную через **`workflow_dispatch`** (GitHub Actions → workflow Deploy → Run workflow).

## Схема

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub                                                         │
│                                                                 │
│  workflow_dispatch                                            │
│      │                                                          │
│      ▼                                                          │
│  GitHub Actions                                                 │
│  ┌─────────────────────┐    ┌──────────────────────────────┐    │
│  │  1. build-and-push  │    │  2. deploy                   │    │
│  │                     │    │                              │    │
│  │  Dockerfile target  │    │  SCP → /opt/agent-lab/:      │    │
│  │  full → собирает    │    │    docker-compose-prod.yaml  │    │
│  │  один образ со      │───▶│    conf.json                 │    │
│  │                     │    │    migrations/postgres/      │    │
│  │  всем кодом         │    │      init.sql                │    │
│  │                     │    │      bootstrap_idempotent.sql│    │
│  │  Push →             │    │                              │    │
│  │  ghcr.io/<owner>/   │    │  SSH → запуск на сервере     │    │
│  │  agent-lab:<tag>    │    │  (секреты в env сессии)      │    │
│  └─────────────────────┘    └──────────────────────────────┘    │
│                                                                 │
│  GitHub Secrets (environment: production)                       │
│      │                                                          │
│      └── передаются как env vars в SSH-сессию                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Сервер 84.38.184.105                                           │
│                                                                 │
│  /opt/agent-lab/                                                │
│  ├── docker-compose-prod.yaml   ← из репо                       │
│  └── conf.json                  ← из репо (в т.ч. services.*)   │
│                                                                 │
│  docker compose pull            ← тянет образ из ghcr.io        │
│  up -d postgres redis → bootstrap_idempotent.sql (psql)       │
│  docker compose run migrations  ← применяет миграции БД       │
│  up -d …                        ← приложение и воркеры          │
│                                                                 │
│  Секреты → env vars SSH-сессии → docker compose подхватывает   │
│  из окружения (без .env файла на диске)                         │
│                                                                 │
│  Сервисы (один образ приложения, разные command):               │
│  ┌────────────────┬──────┬──────────────────────────────────┐  │
│  │ agents         │ 8001 │ python -m apps.flows.main          │  │
│  │ frontend       │ 8002 │ python -m apps.frontend.main       │  │
│  │ crm            │ 8003 │ python -m apps.crm.main            │  │
│  │ rag            │ 8004 │ python -m apps.rag.main            │  │
│  │ sync           │ 8005 │ python -m apps.sync.main           │  │
│  │ scheduler-api  │ 8006 │ python -m apps.scheduler.main     │  │
│  │ worker         │  —   │ taskiq worker apps.broker…         │  │
│  │ scheduler      │  —   │ taskiq scheduler apps.scheduler…   │  │
│  │ rag-worker     │  —   │ taskiq worker apps.rag_worker…     │  │
│  │ sync-worker    │  —   │ taskiq worker apps.sync_worker…    │  │
│  │ livekit        │ 7880 │ образ livekit/livekit-server       │  │
│  │ livekit-egress │  —   │ образ livekit/egress               │  │
│  │ coturn         │ host │ coturn (TURN для WebRTC)           │  │
│  └────────────────┴──────┴──────────────────────────────────┘  │
│                                                                 │
│  MicroK8s Ingress                                               │
│  humanitec.ru/         → frontend :8002                         │
│  humanitec.ru/agents   → agents   :8001                         │
│  humanitec.ru/crm      → crm      :8003                         │
│  humanitec.ru/rag      → rag      :8004                         │
│  humanitec.ru/sync     → sync     :8005                         │
│  *.humanitec.ru        → frontend :8002 (поддомены компаний)    │
└─────────────────────────────────────────────────────────────────┘
```

## Postgres: `migrations/postgres/init.sql` и `bootstrap_idempotent.sql`

Compose монтирует `init.sql` в `agentlab_postgres` как `/docker-entrypoint-initdb.d/01-init-databases.sql`. При **первом** создании тома данных выполняется SQL: дополнительные БД (`platform_agents`, …) и `CREATE EXTENSION vector` там, где нужно.

После старта контейнера Postgres деплой выполняет **`bootstrap_idempotent.sql`** через `psql` (идемпотентные шаги для уже существующего кластера и повторных выкладок). Без этого файла на сервере шаг деплоя завершается с ошибкой.

На сервере путь `/opt/agent-lab/migrations/postgres/init.sql` обязан быть **файлом**, не каталогом. Иначе в логах Postgres: `could not read from input file: Is a directory`, сервисные БД не создаются, миграции падают с `database "platform_agents" does not exist`. В workflow перед копированием `init.sql` выполняется `rm -rf` этого пути, чтобы не оставался каталог от ошибочной прошлой выкладки. Для `appleboy/scp-action` задан `strip_components: 2`, иначе файл уезжает в `.../postgres/migrations/postgres/init.sql`, нужный путь не существует и Docker создаёт **каталог** `init.sql` при первом `compose up`.

Если том Postgres уже инициализирован без дополнительных БД: удалить ошибочный каталог `init.sql`, положить файл, затем либо выполнить SQL из `init.sql` вручную в работающем Postgres, либо снести том `postgres_data` и поднять заново (данные обнулятся).

### Сбой при деплое: `TLS handshake timeout` к `ghcr.io`

Это сетевой отказ с **сервера** до GitHub Container Registry (не GitHub Actions). В workflow для `docker login` и `docker compose pull` заданы повторы с паузой. Если ошибка повторяется стабильно — проверить на сервере: `curl -vI https://ghcr.io/v2/`, DNS, маршрут, firewall; при необходимости прокси или зеркало образов.

## Конфигурация

| Источник | Что содержит | Где хранится |
|---|---|---|
| `conf.json` | Общие настройки, `provider_litserve`, `rag`, `services.<имя>` | Git репо |
| GitHub Secrets | Пароли, ключи, токены | GitHub → Settings → Secrets |

Секреты **никогда не попадают на диск сервера** — только в память SSH-сессии.

## RAG на проде

- **`rag`** (порт **8004**): HTTP API поиска и управления документами; запросы к провайдеру хранения (например **pgvector**) выполняются в процессе API.
- **`rag-worker`**: TaskIQ-воркер **`apps.rag_worker.worker:broker`** — фоновая индексация и обслуживающие задачи (очередь в Redis). Без запущенного `rag-worker` загрузка и переиндексация документов не обрабатываются.

В **`conf.json`** задаётся **`rag`** (провайдер хранения, **`rag.embedding`**, **`rag.reranker`**, профили индекса). Для **локальных** моделей эмбеддинга и реранка указывают **`provider: "provider_litserve"`** — вызовы идут на LitServe (**`provider_litserve.api.base_url`**), а не на OpenRouter / внешний LLM-only endpoint.

## `provider_litserve` (локальные эмбеддинги и реранк)

Контур **локального** инференса: один процесс LitServe (**`apps.provider_litserve.main`**). Запуск: **`scripts/run.py provider-litserve`**. Подробности — **`apps/provider_litserve/README.md`**.

В **`conf.json`** — блок **`provider_litserve`**:

- **`provider_litserve.api.base_url`** — корень клиентского API с суффиксом **`/v1`** (например `http://127.0.0.1:8014/v1`). Его должны видеть процессы **`rag`** и **`rag-worker`** (при Docker — URL хоста, `host.docker.internal` или отдельный сервис в той же сети).
- **`provider_litserve.infra`** — **`gateway_port`** (по умолчанию **8014**), ускоритель, веса и лимиты; **не путать** с публичным **`rag.reranker`**: клиенты платформы ходят на **`api.base_url`**.

Переопределение через окружение: **`PROVIDER_LITSERVE__API__BASE_URL`**, **`PROVIDER_LITSERVE__INFRA__*`** (например **`PROVIDER_LITSERVE__INFRA__GATEWAY_PORT`**). См. **`core/config/models.py`** (`ProviderLitserveConfig`).

**В `docker-compose-prod.yaml` отдельного сервиса под gateway нет** — при необходимости стек поднимается на том же хосте или рядом; важно, чтобы **`provider_litserve.api.base_url`** из контейнеров `rag` / `rag-worker` открывался по сети.

Альтернатива без своего gateway: **`rag.embedding.provider`** / настройки провайдера хранения с внешним API (например OpenRouter для эмбеддингов) — тогда ключи LLM из секретов ниже остаются актуальны.

## GitHub Secrets

Полный список переменных, которые **`deploy.yml`** пробрасывает в SSH-сессию, смотри в файле workflow (**`env:`** у шага Deploy и **`envs:`**). Ниже — смысловые группы.

### Инфраструктура (обязательные)

| Secret | Описание |
|---|---|
| `SERVER_HOST` | IP сервера |
| `SERVER_USER` | SSH пользователь |
| `SERVER_SSH_KEY` | SSH приватный ключ |
| `GHCR_TOKEN` | GitHub PAT с `read:packages` для pull образа |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `AUTH_JWT_SECRET` | JWT секрет (`openssl rand -hex 32`), в env как **`AUTH__JWT_SECRET`** |

### S3 Selectel (обязательные)

Секреты в GitHub по имени `SELECTEL_*` не меняются; в `docker-compose-prod.yaml` они мапятся в `S3__BUCKETS__<ключ>` — ключ должен совпадать с `s3.default_bucket` / ключом в `s3.buckets` в `conf.json` (например `shvedzilla`).

| Secret | Описание |
|---|---|
| `SELECTEL_ACCESS_KEY` | Selectel S3 access key |
| `SELECTEL_SECRET_KEY` | Selectel S3 secret key |

### LLM

| Secret | ENV переменная | Описание |
|---|---|---|
| `LLM_BOTHUB_API_KEY` | `LLM__BOTHUB__API_KEY` | BotHub API key |
| `LLM_OPENROUTER_API_KEY` | `LLM__OPENROUTER__API_KEY` | OpenRouter API key (чат; при конфиге без `provider_litserve` для эмбеддингов — источник ключей для соответствующих настроек в `conf.json`) |

### OAuth провайдеры (нужны для входа)

| Secret | Описание |
|---|---|
| `AUTH_YANDEX_CLIENT_ID` | Яндекс OAuth client id |
| `AUTH_YANDEX_CLIENT_SECRET` | Яндекс OAuth client secret |
| `AUTH_GOOGLE_CLIENT_ID` | Google OAuth client id |
| `AUTH_GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `AUTH_GITHUB_CLIENT_ID` | GitHub OAuth client id |
| `AUTH_GITHUB_CLIENT_SECRET` | GitHub OAuth client secret |

### Web Push (опционально)

| Secret | Описание |
|---|---|
| `PUSH__ENABLED` | Включение Web Push |
| `PUSH__VAPID_PUBLIC_KEY` | VAPID public |
| `PUSH__VAPID_PRIVATE_KEY` | VAPID private |
| `PUSH__VAPID_EMAIL` | Контакт для VAPID (по умолчанию в workflow: `ops@humanitec.ru`) |

### Звонки: LiveKit и TURN

| Secret | Описание |
|---|---|
| `LIVEKIT_API_KEY` | Ключ API LiveKit |
| `LIVEKIT_API_SECRET` | Секрет LiveKit |
| `LIVEKIT_PUBLIC_URL` | Публичный **`wss://`** для клиентов |
| `TURN_SECRET` | Секрет Coturn (`static-auth-secret`) |

`SERVER_HOST` из блока инфраструктуры также подставляется в **`CALLS__TURN_HOST`** (тот же IP, что для SSH).

### STT (опционально)

| Secret | ENV переменная |
|---|---|
| `STT__CLOUD_RU__API_KEY` или `STT_CLOUD_RU_API_KEY` | `STT__CLOUD_RU__API_KEY` |

### RAG: внешние провайдеры (по необходимости)

Секреты для **`provider_litserve`** в **`deploy.yml` не перечислены** — URL и доступность шлюза задаются в **`conf.json`** / окружении на сервере (см. раздел **`provider_litserve`**).

Для **Agentset** или отдельных ключей в **`services.rag`** при необходимости добавь секреты и проброс в **`deploy.yml`** (`env` + `envs`), как для остальных сервис-специфичных ключей.

### Платежи YooMoney (опционально)

В **`deploy.yml` не пробрасываются** — при необходимости задайте на сервере через окружение compose / внешний секретный менеджер. Имена ENV по схеме Pydantic:

| Переменная окружения | Назначение |
|---|---|
| `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__ACCOUNT_NUMBER` | номер счёта |
| `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__NOTIFICATION_SECRET` | секрет уведомлений |
| `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__CLIENT_ID` | OAuth client id |
| `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__CLIENT_SECRET` | OAuth client secret |
| `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__ACCESS_TOKEN` | access token |

Аналогично **`NANO_BANANA__API_KEY`** и другие ключи, которых нет в workflow, задаются вручную на стороне сервера, если они нужны в **`conf.json`**.

## OAuth Callback URLs

Прописать в консолях провайдеров:

| Провайдер | Callback URL |
|---|---|
| Yandex | `https://humanitec.ru/frontend/api/auth/callback/yandex` |
| Google | `https://humanitec.ru/frontend/api/auth/callback/google` |
| GitHub | `https://humanitec.ru/frontend/api/auth/callback/github` |
