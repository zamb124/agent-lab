# Секреты GitHub Actions для `deploy.yml`

Секреты создаются только в GitHub: **Settings → Secrets and variables → Actions → New repository secret**.  
В git они **не** коммитятся.

## 1. Обязательно для доступа к кластеру

| Имя в GitHub (копировать как есть) | Как получить значение |
|---|---|
| **`KUBECONFIG_B64`** | На **master-ноде** с MicroK8s (или там, где рабочий `kubectl get nodes`): см. скрипт ниже или вручную `microk8s config \| base64 -w0` (Linux) / `microk8s config \| base64 \| tr -d '\n'` (macOS). Вставить в поле **Secret** одной строкой, без пробелов в начале/конце. |

После добавления перезапустите workflow **Deploy**.

### Генерация kubeconfig на сервере

С master (из корня репозитория на сервере или скопировав скрипт):

```bash
bash deploy/scripts/kubeconfig-for-github-actions.sh
```

Скрипт выводит **одну строку** — её целиком вставьте в секрет **`KUBECONFIG_B64`**.

## 1b. Обязательно для pull образа платформы из GHCR

Кластер должен аутентифицироваться в `ghcr.io`, иначе Pod’ы с образом `ghcr.io/.../agent-lab` останутся в `ImagePullBackOff`.

| Имя в GitHub (копировать как есть) | Как получить значение |
|---|---|
| **`GHCR_PULL_USERNAME`** | Логин GitHub для `docker login ghcr.io` (или PAT username по документации GHCR). |
| **`GHCR_PULL_TOKEN`** | PAT с правом **`read:packages`** (classic) или fine-grained с доступом к пакету. Workflow создаёт или обновляет Kubernetes Secret **`ghcr-agent-lab-pull`** в namespace платформы; имя совпадает с `image.pullSecrets` в `values-prod.yaml`. |

Если любой из секретов пустой — шаг workflow **падает** с понятной ошибкой (пропуска нет).

## 1c. Локальный pull test-образов (make test-up)

`make test` перед `docker-compose-test` вызывает `scripts/ensure_test_compose_images.py`: образы тянутся из GHCR, при отсутствии — локальная сборка.

**Обязательно для каждого разработчика:** установлен **GitHub CLI (`gh`)**. При первом `make test-up` без GHCR-сессии скрипт **интерактивно запускает** `gh auth login -s read:packages` и затем `docker login ghcr.io` через токен `gh`.

| Действие | Когда |
|---|---|
| Авто-login | Первый `make test-up` без docker/gh auth — скрипт сам вызовет `gh auth login` |
| Ручная проверка | `gh auth status` и `docker manifest inspect ghcr.io/zamb124/agent-lab-base:latest` |
| Push после локальной сборки | `TEST_IMAGES_PUSH=1 make test-up` (нужен scope **`write:packages`**) |
| CI / без интерактива | `TEST_IMAGES_SKIP_GHCR_AUTH=1` (только automation, не для локальной разработки) |

Образы: `ghcr.io/<owner>/agent-lab:<git-sha>`, `agent-lab-test-base:deps-<hash>`, `agent-lab-test:<git-sha>`, `agent-lab-test-a2a:<hash>`. CI пушит их через workflows **Build Test Base Image** и **Build Test Images** при push в `main`.

Без успешного GHCR login **`make test-up` падает** — локальная сборка без auth не используется как обход.

## 2. Обязательные для шага «Sync platform-secrets»

Имена должны совпадать с колонкой «Имя в GitHub».

| Имя в GitHub |
|---|
| `POSTGRES_PASSWORD` |
| `AUTH_JWT_SECRET` |
| `SECRETS_ENCRYPTION_KEY` |
| `SELECTEL_ACCESS_KEY` |
| `SELECTEL_SECRET_KEY` |
| `LIVEKIT_API_KEY` |
| `LIVEKIT_API_SECRET` |
| `TURN_SECRET` |
| `ONLYOFFICE_JWT_SECRET` |
| `GRAFANA_ADMIN_PASSWORD` |

**Значения:** для OnlyOffice и Grafana задайте достаточно длинные случайные строки (например `openssl rand -hex 32`), один раз сохраните в GitHub Secrets; дальше они попадают в Kubernetes Secret `platform-secrets` как `onlyoffice-jwt-secret` и `grafana-admin-password`.

## 3. Опциональные (workflow допускает пустые)

> **Примечание:** некоторые имена используют `__` (исторически, нотация pydantic), другие — `_`. Это разные реальные имена секретов в GitHub Settings — не переименовывать без синхронного обновления `deploy.yml` и `helm_platform_secrets_json.sh`.

| Имя в GitHub |
|---|
| `HF_TOKEN` |
| `AUTH_YANDEX_CLIENT_ID` / `AUTH_YANDEX_CLIENT_SECRET` |
| `AUTH_GOOGLE_CLIENT_ID` / `AUTH_GOOGLE_CLIENT_SECRET` |
| `AUTH_GITHUB_CLIENT_ID` / `AUTH_GITHUB_CLIENT_SECRET` |
| `AUTH_AMOCRM_CLIENT_ID` / `AUTH_AMOCRM_CLIENT_SECRET` |
| `AUTH_APPLE_PRIVATE_KEY` |
| `AUTH_DEMO_PASSWORD` |
| `PUSH__VAPID_PUBLIC_KEY` / `PUSH__VAPID_PRIVATE_KEY` |
| `PUSH__APNS_PRIVATE_KEY` |
| `PUSH__FCM_CREDENTIALS_JSON` / `PUSH__FCM_PROJECT_ID` |
| `LLM__OPENROUTER__API_KEY` / `LLM__BOTHUB__API_KEY` |
| `LLM__GROQ__API_KEY` / `LLM__GOOGLE__API_KEY` / `LLM__GITHUB__API_KEY` |
| `LLM__HUGGINGFACE__API_KEY` / `LLM__DEEPINFRA__API_KEY` / `LLM__YANDEX__API_KEY` / `LLM__YANDEX__FOLDER_ID` |
| `STT__CLOUD_RU__API_KEY` |
| `VOICE__STT__YANDEX__API_KEY` / `VOICE__STT__YANDEX__FOLDER_ID` |
| `VOICE__STT__SBER__CLIENT_ID` / `VOICE__STT__SBER__CLIENT_SECRET` |
| `VOICE__TTS__CLOUD_RU__API_KEY` |
| `VOICE__TTS__YANDEX__API_KEY` / `VOICE__TTS__YANDEX__FOLDER_ID` |
| `VOICE__TTS__SBER__CLIENT_ID` / `VOICE__TTS__SBER__CLIENT_SECRET` |
| `RAG_EMBEDDING_API_KEY` |
| `YOOMONEY_ACCOUNT_NUMBER` / `YOOMONEY_NOTIFICATION_SECRET` / `YOOMONEY_CLIENT_ID` / `YOOMONEY_CLIENT_SECRET` / `YOOMONEY_ACCESS_TOKEN` |
| `PROXY__ENABLED` / `PROXY__PROXIES` | (опционально) исходящий HTTP(S) прокси платформы: `PROXY__ENABLED` — `true` / `false`; `PROXY__PROXIES` — **одна строка**, JSON-массив URL, например `["http://user:pass@host:3128"]`. Попадает в Kubernetes `platform-secrets` и в Pod env как `PROXY__ENABLED` / `PROXY__PROXIES` (см. `settings.proxy`). |
| `SEARCH__TINYFISH__API_KEY` / `SEARCH__LINKUP__API_KEY` / `SEARCH__SERPER__API_KEY` / `SEARCH__TAVILY__API_KEY` | (опционально) ключи провайдеров Search MCP. Без ключа конкретный provider возвращает typed provider error; provider policy пробует следующий доступный provider. |

**Voice/Speech:** `STT__CLOUD_RU__API_KEY` попадает в Kubernetes Secret `platform-secrets` как `stt-cloud-ru-api-key`; в Pod env проброшен как **`VOICE__STT__CLOUD_RU__API_KEY`** (`settings.voice.stt.cloud_ru.api_key`). Остальные ключи `VOICE__STT__*` / `VOICE__TTS__*` маппятся через `helm_platform_secrets_json.sh` в `platformSecrets.{stt,tts}{Yandex,Sber,CloudRu}{ApiKey,FolderId,ClientId,ClientSecret}`, оттуда в `platform-secrets` (ключи `stt-yandex-api-key` и т.п.).

В **`helm_platform_secrets_json.sh`** ключ embedding в платформенный Secret попадает только из **`RAG_EMBEDDING_API_KEY`**; подстановки из **`LLM__OPENROUTER__API_KEY`** нет.

Полное описание назначения — в [`deploy/README.md`](README.md).

## 4. HumanitecAgent desktop release (`humanitec-agent-build.yml`)

Запускается **только вручную** (`workflow_dispatch` в GitHub Actions). Без секретов ниже macOS/Windows job'ы упадут; Linux-сборки пройдут.

| Имя в GitHub | Назначение |
|---|---|
| `APPLE_ID` | macOS notarization |
| `APPLE_ID_PASSWORD` | app-specific password |
| `APPLE_TEAM_ID` | Apple Team ID |
| `KEYCHAIN_PATH` | CI keychain для codesign |
| `WINDOWS_CERTIFICATE_FILE` | Authenticode certificate (base64 или путь — как настроено в Goose forge) |
| `WINDOWS_CERTIFICATE_PASSWORD` | пароль сертификата |

Workflow использует `GITHUB_TOKEN` для публикации GitHub Release; отдельный PAT не нужен (`permissions: contents: write`).

Release tag по умолчанию: `humanitec-agent-{short_sha}` (тот же short SHA, что Helm `image.tag` после Deploy).
