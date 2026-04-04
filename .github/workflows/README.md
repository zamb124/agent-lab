# Deploy

Деплой запускается вручную через **`workflow_dispatch`** (см. [`deploy.yml`](deploy.yml)).

## Схема

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub                                                         │
│                                                                 │
│  main branch                                                    │
│      │                                                          │
│      ▼                                                          │
│  GitHub Actions                                                 │
│  ┌─────────────────────┐    ┌──────────────────────────────┐    │
│  │  1. build-and-push  │    │  2. deploy                   │    │
│  │                     │    │                              │    │
│  │  Dockerfile target  │    │  SCP → /opt/agent-lab/:      │    │
│  │  full → собирает    │    │    docker-compose-prod.yaml  │    │
│  │  один образ со      │───▶│    conf.json                 │    │
│  │                     │    │    migrations/postgres/init.sql│  │
│  │                     │    │    deploy/onlyoffice/themes/…  │  │
│  │  всем кодом         │    │                              │    │
│  │                     │    │                              │    │
│  │  Push →             │    │  SSH → запуск на сервере     │    │
│  │  ghcr.io/zamb124/   │    │  (секреты в env сессии)      │    │
│  │  agent-lab:latest   │    └──────────────────────────────┘    │
│  └─────────────────────┘                                        │
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
│  ├── conf.json                  ← из репо (в т.ч. services.*)   │
│  ├── migrations/postgres/*.sql  ← из репо                       │
│  └── deploy/onlyoffice/themes/theme-humanitec-light.json       │
│                                                                 │
│  docker compose pull            ← тянет образ из ghcr.io        │
│  docker compose run migrations  ← применяет миграции БД         │
│  docker compose up -d ...       ← поднимает все сервисы         │
│                                                                 │
│  Секреты → env vars SSH-сессии → docker compose подхватывает    │
│  из окружения (без .env файла на диске)                         │
│                                                                 │
│  Сервисы (один образ, разные command):                          │
│  ┌──────────┬──────┬────────────────────────────────────────┐   │
│  │ agents   │ 8001 │ python -m apps.flows.main             │   │
│  │ frontend │ 8002 │ python -m apps.frontend.main           │   │
│  │ crm      │ 8003 │ python -m apps.crm.main                │   │
│  │ rag      │ 8004 │ python -m apps.rag.main                │   │
│  │ sync     │ 8005 │ python -m apps.sync.main               │   │
│  │ office   │ 8008 │ python -m apps.office.main (Documents BFF)│   │
│  │ onlyoffice-documentserver │ 8088 │ onlyoffice/documentserver-de │   │
│  │ scheduler-api │ 8006 │ python -m apps.scheduler.main      │   │
│  │ flows_worker │  —   │ taskiq worker apps.flows_worker.worker:worker_app│   │
│  │ crm_worker │  —   │ taskiq worker apps.crm_worker.worker:worker_app│   │
│  │ rag_worker │  —   │ taskiq worker apps.rag_worker.worker:worker_app│   │
│  │ sync_worker │  —   │ taskiq worker apps.sync_worker.worker:worker_app│   │
│  │ idle_worker │  —   │ taskiq worker apps.idle_worker.worker:worker_app│   │
│  │ scheduler│  —   │ taskiq scheduler ...                   │   │
│  └──────────┴──────┴────────────────────────────────────────┘   │
│                                                                 │
│  MicroK8s Ingress                                               │
│  humanitec.ru/         → frontend :8002                         │
│  humanitec.ru/agents   → agents   :8001                         │
│  humanitec.ru/crm      → crm      :8003                         │
│  humanitec.ru/rag      → rag      :8004                         │
│  humanitec.ru/sync     → sync     :8005                         │
│  humanitec.ru/documents → office  :8008 (BFF + UI документов)   │
│  humanitec.ru/onlyoffice или отдельный хост → DS :8088 (api.js) │
│  *.humanitec.ru        → frontend :8002 (поддомены компаний)    │
└─────────────────────────────────────────────────────────────────┘
```

## Postgres: `migrations/postgres/init.sql`

Compose монтирует этот путь в `agentlab_postgres` как `/docker-entrypoint-initdb.d/01-init-databases.sql`. При **первом** создании тома данных выполняется SQL: дополнительные БД (`platform_agents`, …) и `CREATE EXTENSION vector` там, где нужно.

На сервере путь `/opt/agent-lab/migrations/postgres/init.sql` обязан быть **файлом**, не каталогом. Иначе в логах Postgres: `could not read from input file: Is a directory`, сервисные БД не создаются, миграции падают с `database "platform_agents" does not exist`. В workflow перед копированием `init.sql` выполняется `rm -rf` этого пути, чтобы не оставался каталог от ошибочной прошлой выкладки. Для `appleboy/scp-action` задан `strip_components: 2`, иначе файл уезжает в `.../postgres/migrations/postgres/init.sql`, нужный путь не существует и Docker создаёт **каталог** `init.sql` при первом `compose up`.

Если том Postgres уже инициализирован без дополнительных БД: удалить ошибочный каталог `init.sql`, положить файл, затем либо выполнить SQL из `init.sql` вручную в работающем Postgres, либо снести том `postgres_data` и поднять заново (данные обнулятся).

### Сбой при деплое: `TLS handshake timeout` к `ghcr.io`

Это сетевой отказ с **сервера** до GitHub Container Registry (не GitHub Actions). В workflow для `docker login` и `docker compose pull` заданы повторы с паузой. Если ошибка повторяется стабильно — проверить на сервере: `curl -vI https://ghcr.io/v2/`, DNS, маршрут, firewall; при необходимости прокси или зеркало образов.

## Конфигурация

| Источник | Что содержит | Где хранится |
|---|---|---|
| `conf.json` | Общие настройки и `services.<имя>` для сервисов | Git репо |
| GitHub Secrets | Пароли, ключи, токены | GitHub → Settings → Secrets |

Секреты **никогда не попадают на диск сервера** — только в память SSH-сессии.

## GitHub Secrets

### Инфраструктура (обязательные)

| Secret | Описание |
|---|---|
| `SERVER_HOST` | IP сервера |
| `SERVER_USER` | SSH пользователь |
| `SERVER_SSH_KEY` | SSH приватный ключ |
| `GHCR_TOKEN` | GitHub PAT с `read:packages` для pull образа |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `AUTH_JWT_SECRET` | JWT секрет (`openssl rand -hex 32`) |

### S3 (продакшен: не MinIO из `conf.json`)

Корневой блок **`s3`** в `conf.json` (тот же файл копируется на сервер) задаёт **имя бакета по умолчанию**, endpoint и структуру `buckets`. Запись **`test-bucket` / MinIO** в репозитории — для **локальной** разработки; в проде приложения используют **`s3.default_bucket`** (сейчас в шаблоне — **`shvedzilla`**, Selectel), если вы не меняли его на сервере.

В **`docker-compose-prod.yaml`** в `x-common-env` жёстко задано:

- `S3__DEFAULT_BUCKET: shvedzilla`
- `S3__BUCKETS__SHVEDZILLA__ACCESS_KEY_ID` / `S3__BUCKETS__SHVEDZILLA__SECRET_ACCESS_KEY` из секретов

Имя **`SHVEDZILLA`** в переменных окружения должно совпадать с **ключом** объекта в `s3.buckets` и с **`s3.default_bucket`** в `conf.json` на сервере. Если продакшен использует **другой бакет** (не `shvedzilla`), нужно:

1. Обновить **`conf.json`** на сервере: `default_bucket`, соответствующий объект в `buckets` (endpoint, `bucket_name`, provider).
2. Обновить **`docker-compose-prod.yaml`**: `S3__DEFAULT_BUCKET` и блок `S3__BUCKETS__<ИМЯ_КЛЮЧА_В_UPPERCASE>` под тот же ключ (как в Pydantic nested env).

Ключи S3 в GitHub — это **не** MinIO:

| Secret | Описание |
|---|---|
| `SELECTEL_ACCESS_KEY` | S3 access key (например Selectel) |
| `SELECTEL_SECRET_KEY` | S3 secret key |

Отдельный секрет «для S3» не требуется, если достаточно пары `SELECTEL_*`: они подставляются в env контейнеров и **перекрывают** плейсхолдеры в JSON для бакета `shvedzilla`.

### LLM (обязательные)

| Secret | ENV переменная | Описание |
|---|---|---|
| `LLM_BOTHUB_API_KEY` | `LLM__BOTHUB__API_KEY` | BotHub API key |
| `LLM_OPENROUTER_API_KEY` | `LLM__OPENROUTER__API_KEY` | OpenRouter API key |

### OAuth провайдеры (нужны для входа)

| Secret | Описание |
|---|---|
| `AUTH_YANDEX_CLIENT_ID` | Яндекс OAuth client id |
| `AUTH_YANDEX_CLIENT_SECRET` | Яндекс OAuth client secret |
| `AUTH_GOOGLE_CLIENT_ID` | Google OAuth client id |
| `AUTH_GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `AUTH_GITHUB_CLIENT_ID` | GitHub OAuth client id |
| `AUTH_GITHUB_CLIENT_SECRET` | GitHub OAuth client secret |

### RAG / Embeddings (нужны для RAG и CRM-индексации)

В `docker-compose-prod.yaml` в контейнеры пробрасывается `RAG__PROVIDERS__PGVECTOR__EMBEDDING_API_KEY`. Если задан только `LLM_OPENROUTER_API_KEY`, он же подставляется для эмбеддингов (отдельный секрет не обязателен).

| Secret | Передаётся на сервер как | Описание |
|---|---|---|
| `LLM_OPENROUTER_API_KEY` | `LLM_OPENROUTER_API_KEY` | OpenRouter: чат и эмбеддинги по умолчанию |
| `RAG_EMBEDDING_API_KEY` (опционально) | `RAG_EMBEDDING_API_KEY` | Другой ключ только для embeddings (перебивает LLM-ключ в compose) |
| `RAG_AGENTSET_API_KEY` (опционально) | не в workflow — добавь в `deploy.yml` env + `envs`, если используете Agentset | Agentset API key |

### Документы / OnlyOffice

В **`docker-compose-prod.yaml`** поднимаются **`onlyoffice-documentserver`** (**`onlyoffice/documentserver-de`**, порт **8088**) и BFF **`office`** (**8008**). Секрет JWT должен совпадать в контейнере DS и в BFF (**`OFFICE__JWT_SECRET`** / **`ONLYOFFICE_JWT_SECRET`**). Публичные URL браузера и callback — в **`OFFICE__DOCUMENT_SERVER_PUBLIC_URL`** и **`OFFICE__CALLBACK_PUBLIC_BASE_URL`** (часто совпадают с origin ingress и с URL, с которого Document Server достучится до BFF).

| Secret | Описание |
|---|---|
| `ONLYOFFICE_JWT_SECRET` | Общий секрет JWT для DS и BFF |
| `OFFICE_DOCUMENT_SERVER_PUBLIC_URL` (опционально) | Origin Document Server для скрипта api.js (по умолчанию в compose `http://localhost:8088`) |
| `OFFICE_CALLBACK_PUBLIC_BASE_URL` (опционально) | Публичный базовый URL BFF для download/callback (по умолчанию `http://localhost:8008`) |

### Платежи YooMoney (опционально)

| Secret | ENV переменная |
|---|---|
| `YOOMONEY_ACCOUNT_NUMBER` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__ACCOUNT_NUMBER` |
| `YOOMONEY_NOTIFICATION_SECRET` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__NOTIFICATION_SECRET` |
| `YOOMONEY_CLIENT_ID` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__CLIENT_ID` |
| `YOOMONEY_CLIENT_SECRET` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__CLIENT_SECRET` |
| `YOOMONEY_ACCESS_TOKEN` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__ACCESS_TOKEN` |

### STT / Nano Banana (опционально)

| Secret | ENV переменная |
|---|---|
| `STT_CLOUD_RU_API_KEY` | `STT__CLOUD_RU__API_KEY` |
| `NANO_BANANA_API_KEY` | `NANO_BANANA__API_KEY` |

## OAuth Callback URLs

Прописать в консолях провайдеров. Единый callback на фронтовом сервисе (без префикса `/frontend`): `https://<публичный_хост>/auth/callback/<provider>`.

| Провайдер | Callback URL |
|---|---|
| Yandex | `https://humanitec.ru/auth/callback/yandex` |
| Google | `https://humanitec.ru/auth/callback/google` |
| GitHub | `https://humanitec.ru/auth/callback/github` |
| Apple (Services ID) | `https://humanitec.ru/auth/callback/apple` |

### Sign in with Apple: conf.json и секрет

`client_id` (Services ID), `apple_team_id`, `apple_key_id` — **не секреты**, задавай в **`conf.json`**, который копируется на сервер с деплоем (`auth.providers.apple`).

| Поле в `conf.json` | Пример |
|---|---|
| `client_id` | `app.humanitec.ru` |
| `apple_team_id` | Team ID из Membership |
| `apple_key_id` | Key ID ключа Sign in with Apple |

В **GitHub Secrets** достаточно одного секрета:

| Secret | Назначение |
|---|---|
| `AUTH_APPLE_PRIVATE_KEY` | Содержимое `.p8` в одной строке: `-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----` |

Compose пробрасывает его как `AUTH__PROVIDERS__APPLE__APPLE_PRIVATE_KEY` (перекрывает поле `apple_private_key` из JSON, если задан).

### Демо-вход (App Review, опционально)

В **`conf.json`** на сервере: `auth.demo.login_enabled: true`, при необходимости `email` / `company_id` / `subdomain`, и **`auth.demo.password`** (можно публичный пароль для демо). Альтернатива или дополнение: секрет **`AUTH_DEMO_PASSWORD`** в GitHub Secrets → `AUTH__DEMO__PASSWORD` в compose. После ревью выключить демо: `auth.demo.login_enabled: false` в `conf.json`.

## Mobile: Lighthouse CI

Workflow [`mobile-pwa-lighthouse.yml`](mobile-pwa-lighthouse.yml) — по расписанию и вручную; проверяет PWA на URL из секрета **`PWA_LIGHTHOUSE_URL`** (например `https://humanitec.ru/`). Без секрета job завершится ошибкой на шаге Lighthouse.
