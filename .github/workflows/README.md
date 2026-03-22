# Deploy

Деплой запускается автоматически при push в `main` или вручную через `workflow_dispatch`.

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
│  └── conf.json                  ← из репо (в т.ч. services.*)   │
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
│  │ worker   │  —   │ taskiq worker apps.broker.worker:broker│   │
│  │ scheduler│  —   │ taskiq scheduler ...                   │   │
│  └──────────┴──────┴────────────────────────────────────────┘   │
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

## Postgres: `migrations/postgres/init.sql`

Compose монтирует этот путь в `agentlab_postgres` как `/docker-entrypoint-initdb.d/01-init-databases.sql`. При **первом** создании тома данных выполняется SQL: дополнительные БД (`platform_agents`, …) и `CREATE EXTENSION vector` там, где нужно.

На сервере путь `/opt/agent-lab/migrations/postgres/init.sql` обязан быть **файлом**, не каталогом. Иначе в логах Postgres: `could not read from input file: Is a directory`, сервисные БД не создаются, миграции падают с `database "platform_agents" does not exist`. В workflow перед копированием `init.sql` выполняется `rm -rf` этого пути, чтобы не оставался каталог от ошибочной прошлой выкладки.

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

### S3 Selectel (обязательные)

| Secret | Описание |
|---|---|
| `SELECTEL_ACCESS_KEY` | Selectel S3 access key |
| `SELECTEL_SECRET_KEY` | Selectel S3 secret key |

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

### RAG / Embeddings (нужны для RAG)

| Secret | ENV переменная | Описание |
|---|---|---|
| `RAG_EMBEDDING_API_KEY` | `RAG__PROVIDERS__PGVECTOR__EMBEDDING_API_KEY` | API ключ для эмбеддингов |
| `RAG_AGENTSET_API_KEY` | `RAG__PROVIDERS__AGENTSET__API_KEY` | Agentset API key |

### Платежи YooMoney (опционально)

| Secret | ENV переменная |
|---|---|
| `YOOMONEY_ACCOUNT_NUMBER` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__ACCOUNT_NUMBER` |
| `YOOMONEY_NOTIFICATION_SECRET` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__NOTIFICATION_SECRET` |
| `YOOMONEY_CLIENT_ID` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__CLIENT_ID` |
| `YOOMONEY_CLIENT_SECRET` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__CLIENT_SECRET` |
| `YOOMONEY_ACCESS_TOKEN` | `PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__ACCESS_TOKEN` |

### Cloud Voice / Nano Banana (опционально)

| Secret | ENV переменная |
|---|---|
| `CLOUD_VOICE_SECRET_KEY` | `CLOUD_VOICE__SECRET_KEY` |
| `CLOUD_VOICE_CLIENT_ID` | `CLOUD_VOICE__CLIENT_ID` |
| `NANO_BANANA_API_KEY` | `NANO_BANANA__API_KEY` |

## OAuth Callback URLs

Прописать в консолях провайдеров:

| Провайдер | Callback URL |
|---|---|
| Yandex | `https://humanitec.ru/frontend/api/auth/callback/yandex` |
| Google | `https://humanitec.ru/frontend/api/auth/callback/google` |
| GitHub | `https://humanitec.ru/frontend/api/auth/callback/github` |
