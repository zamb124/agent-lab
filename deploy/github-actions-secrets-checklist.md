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

## 1d. Обязательно для brand DNS и wildcard TLS (Reg.ru API)

Reg.ru API принимает запросы **только с whitelist IP**. Шаг **Setup brand DNS** в CI запускает `setup-brand-dns.sh` **с master-ноды** (Kubernetes Job с `nodeName=master`), egress IP = `84.38.184.105`. В whitelist Reg.ru должен быть **master** `84.38.184.105` (не GitHub Actions runner, не домашний Mac).

| Имя в GitHub | Как получить |
|---|---|
| **`REGRU_USERNAME`** | Логин Reg.ru (личный кабинет). |
| **`REGRU_PASSWORD`** | **API-пароль** из Reg.ru → Настройки → API (не обязательно пароль от аккаунта). |

Без этих секретов deploy **падает** на шагах DNS/TLS. Локальная проверка: `bash deploy/scripts/test-regru-api.sh` (с Mac — IP в whitelist Reg.ru) или `bash deploy/scripts/setup-brand-dns-via-master-job.sh` при настроенном `kubectl`.

## 2. Обязательные для шага «Sync platform-secrets»

Имена должны совпадать с колонкой «Имя в GitHub».

| Имя в GitHub |
|---|
| `POSTGRES_PASSWORD` |
| `OPENFGA_API_TOKEN` |
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

`OPENFGA_API_TOKEN` → `platform-secrets.openfga-api-token` (`openssl rand -hex 32`).

### 2b. OpenFGA pin (автоматически, не GitHub Secrets)

После `helm upgrade` CI / `make k8s-deploy` сам запускает `deploy/scripts/openfga_bootstrap_cluster.sh`:

1. создаёт store (или reuse) + пишет authorization model;
2. пишет канон в Kubernetes Secret `openfga-ids` (`store-id`, `authorization-model-id`);
3. `helm upgrade --reuse-values --set openfga.storeId/authorizationModelId`.

Следующие деплои подхватывают ids из `openfga-ids` (`openfga_load_pinned_ids.sh`) до helm.

Опциональный override в GitHub (редко нужно):

| Имя в GitHub | Назначение |
|---|---|
| `OPENFGA_STORE_ID` | форс Helm `openfga.storeId` (поверх Secret) |
| `OPENFGA_AUTHORIZATION_MODEL_ID` | форс Helm `openfga.authorizationModelId` |

Ручной повтор: `make k8s-openfga-bootstrap` (APPLY=1 по умолчанию).

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
| `LLM__HUGGINGFACE__API_KEY` / `LLM__DEEPINFRA__API_KEY` / `LLM__CAILA__API_KEY` / `LLM__YANDEX__API_KEY` / `LLM__YANDEX__FOLDER_ID` |
| `LLM__OPENROUTER__API_KEYS` / `LLM__BOTHUB__API_KEYS` / `LLM__GROQ__API_KEYS` / `LLM__GOOGLE__API_KEYS` / `LLM__GITHUB__API_KEYS` / `LLM__HUGGINGFACE__API_KEYS` / `LLM__DEEPINFRA__API_KEYS` / `LLM__CAILA__API_KEYS` / `LLM__YANDEX__API_KEYS` | (опционально) дополнительные API ключи для ротации внутри одного провайдера. JSON-массив: `'["sk-1","sk-2","sk-3"]'`. Каждый ключ создаёт отдельного кандидата в free-pool; cooldown одного ключа не блокирует другие ключи того же провайдера. |
| `STT__CLOUD_RU__API_KEY` |
| `VOICE__STT__YANDEX__API_KEY` / `VOICE__STT__YANDEX__FOLDER_ID` |
| `VOICE__STT__SBER__CLIENT_ID` / `VOICE__STT__SBER__CLIENT_SECRET` |
| `MAIL__SYSTEM__ISPMANAGER__AUTHINFO_PASSWORD` |
| `VOICE__TTS__CLOUD_RU__API_KEY` |
| `VOICE__TTS__YANDEX__API_KEY` / `VOICE__TTS__YANDEX__FOLDER_ID` |
| `VOICE__TTS__SBER__CLIENT_ID` / `VOICE__TTS__SBER__CLIENT_SECRET` |
| `RAG_EMBEDDING_API_KEY` |
| `TINKOFF_TERMINAL_KEY` / `TINKOFF_TERMINAL_PASSWORD` | (опционально) интернет-эквайринг Т-Банка: TerminalKey и пароль терминала. Helm `tinkoff-terminal-key` / `tinkoff-terminal-password` → Pod env `PAYMENT_PROVIDERS__PROVIDERS__TINKOFF_MAIN__TERMINAL_KEY` / `__PASSWORD`. |
| `PROXY__ENABLED` / `PROXY__PROXIES` | (опционально) исходящий HTTP(S) прокси платформы: `PROXY__ENABLED` — `true` / `false`; `PROXY__PROXIES` — **одна строка**, JSON-массив URL, например `["http://user:pass@host:3128"]`. Попадает в Kubernetes `platform-secrets` и в Pod env как `PROXY__ENABLED` / `PROXY__PROXIES` (см. `settings.proxy`). |
| `SEARCH__TINYFISH__API_KEY` / `SEARCH__LINKUP__API_KEY` / `SEARCH__SERPER__API_KEY` / `SEARCH__TAVILY__API_KEY` | (опционально) ключи провайдеров Search MCP. Без ключа конкретный provider возвращает typed provider error; provider policy пробует следующий доступный provider. |
| `MAIL__SYSTEM__ISPMANAGER__AUTHINFO_PASSWORD` | (опционально) ISPmanager authinfo для `mail.system` на company `system`. Hosts/user — в `app-conf.k8s-overlay.json`. |
| `AGENT__RELEASES__GITHUB_TOKEN` | (опционально) PAT для GitHub Releases API на prod (`/frontend/api/agent/download/*`). **Обязателен для private repo.** Fallback в deploy: `GHCR_PULL_TOKEN`, если у него есть `repo` / Contents Read. Без токена API отдаёт 404. |

**Voice/Speech:** `STT__CLOUD_RU__API_KEY` попадает в Kubernetes Secret `platform-secrets` как `stt-cloud-ru-api-key`; в Pod env проброшен как **`VOICE__STT__CLOUD_RU__API_KEY`** (`settings.voice.stt.cloud_ru.api_key`). Остальные ключи `VOICE__STT__*` / `VOICE__TTS__*` маппятся через `helm_platform_secrets_json.sh` в `platformSecrets.{stt,tts}{Yandex,Sber,CloudRu}{ApiKey,FolderId,ClientId,ClientSecret}`, оттуда в `platform-secrets` (ключи `stt-yandex-api-key` и т.п.).

В **`helm_platform_secrets_json.sh`** ключ embedding в платформенный Secret попадает только из **`RAG_EMBEDDING_API_KEY`**; подстановки из **`LLM__OPENROUTER__API_KEY`** нет.

Полное описание назначения — в [`deploy/README.md`](README.md).

## 4. LinnexAgent desktop release (`humanitec-agent-build.yml`)

Запускается **только вручную** (`workflow_dispatch` в GitHub Actions). Без секретов ниже macOS/Windows job'ы собирают **unsigned** артефакты; Linux-сборки проходят как обычно.

| Имя в GitHub | Назначение |
|---|---|
| `APPLE_ID` | Apple ID для notarization |
| `APPLE_ID_PASSWORD` | App-specific password ([appleid.apple.com](https://appleid.apple.com)) |
| `APPLE_TEAM_ID` | Apple Team ID (`MLL2V8KTV4` — тот же, что iOS/mobile в `conf.json`) |
| `MACOS_CERTIFICATE_P12_BASE64` | Developer ID Application certificate (`.p12`, base64) |
| `MACOS_CERTIFICATE_PASSWORD` | Пароль экспорта `.p12` |
| `WINDOWS_CERTIFICATE_FILE` | Authenticode certificate (base64 или путь — как настроено в Goose forge) |
| `WINDOWS_CERTIFICATE_PASSWORD` | пароль сертификата |

**Не использовать для desktop:** `AUTH_APPLE_PRIVATE_KEY` (.p8) — Sign in with Apple на сайте, не codesign `.app`.

`KEYCHAIN_PATH` создаётся на macOS-раннере в CI (не GitHub Secret). Подробности: [`apps/agent/desktop/docs/MACOS_SIGNING.md`](../apps/agent/desktop/docs/MACOS_SIGNING.md).

Workflow использует `GITHUB_TOKEN` для публикации GitHub Release; отдельный PAT не нужен (`permissions: contents: write`).

Release tag по умолчанию: `linnex-agent-{short_sha}` (тот же short SHA, что Helm `image.tag` после Deploy).

Phase 1 публикует signed macOS `.dmg` сразу и шлёт submit в Apple (`AGENT_MACOS_NOTARIZE=submit-only`).

## 5. LinnexAgent macOS notarize follow-up (`humanitec-agent-macos-notarize.yml`)

Триггеры: cron каждые 30 мин, успешный `humanitec-agent-build`, `workflow_dispatch`.

Те же Apple/macOS secrets, что в §4. Без них job пропускается.

До 48 ч после release: poll Apple → stapler → replace `.dmg` в том же GitHub Release (`--clobber`).

Локально: `make agent-notarize-followup AGENT_RELEASE_TAG=humanitec-agent-<short_sha>`.
