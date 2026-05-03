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

## 2. Обязательные для шага «Sync platform-secrets»

Имена должны совпадать с колонкой «Имя в GitHub».

| Имя в GitHub |
|---|
| `POSTGRES_PASSWORD` |
| `AUTH_JWT_SECRET` |
| `SELECTEL_ACCESS_KEY` |
| `SELECTEL_SECRET_KEY` |
| `LIVEKIT_API_KEY` |
| `LIVEKIT_API_SECRET` |
| `TURN_SECRET` |
| `ONLYOFFICE_JWT_SECRET` |
| `GRAFANA_ADMIN_PASSWORD` |

**Значения:** для OnlyOffice и Grafana задайте достаточно длинные случайные строки (например `openssl rand -hex 32`), один раз сохраните в GitHub Secrets; дальше они попадают в Kubernetes Secret `platform-secrets` как `onlyoffice-jwt-secret` и `grafana-admin-password`.

## 3. Опциональные (workflow допускает пустые)

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
| `LLM_BOTHUB_API_KEY` / `LLM_OPENROUTER_API_KEY` |
| `STT__CLOUD_RU__API_KEY` |
| `RAG_EMBEDDING_API_KEY` |
| `YOOMONEY_ACCOUNT_NUMBER` / `YOOMONEY_NOTIFICATION_SECRET` / `YOOMONEY_CLIENT_ID` / `YOOMONEY_CLIENT_SECRET` / `YOOMONEY_ACCESS_TOKEN` |

В **`helm_platform_secrets_json.sh`** ключ embedding в платформенный Secret попадает только из **`RAG_EMBEDDING_API_KEY`**; подстановки из **`LLM_OPENROUTER_API_KEY`** нет.

Полное описание назначения — в [`deploy/README.md`](README.md).
