# Деплой Humanitec Platform

Платформа разворачивается единым **Helm-чартом** в **MicroK8s** кластере (master + GPU worker нода). Всё, что нужно для деплоя, лежит в [`deploy/helm/agent-lab/`](helm/agent-lab/).

См. также:
- [`cluster-setup.md`](cluster-setup.md) — одноразовая настройка нод кластера (MicroK8s install, GPU, лейблы).
- [`scripts/`](scripts/) — идемпотентные shell-скрипты для всех операций над кластером.
- [`infrastructure.mdc`](../.cursor/rules/infrastructure.mdc) — канон инфраструктуры (источник правды).
- [`.cursor/skills/devops-engineer/`](../.cursor/skills/devops-engineer/) — DevOps skill для Cursor (карта компонентов, чек-листы, runbooks).

## Архитектура

```
MicroK8s cluster
├── master (84.38.184.105)         hostname=master
│   ├── postgres StatefulSet (PVC 50Gi)
│   ├── redis StatefulSet (PVC 10Gi)
│   ├── 9 application Deployments (flows, frontend, crm, rag, sync, scheduler-api, office, voice, browser)
│   ├── 6 worker Deployments (flows-worker x2, scheduler, rag-worker, sync-worker, crm-worker, idle-worker)
│   ├── livekit + livekit-egress + coturn DaemonSet (hostNetwork)
│   ├── onlyoffice Deployment
│   ├── observability: loki StatefulSet, tempo StatefulSet, grafana Deployment
│   ├── alloy DaemonSet (на каждой ноде)
│   ├── ingress-nginx + cert-manager
│   └── 4 Ingress: platform, livekit, onlyoffice, grafana
└── gpu-worker (188.246.224.228)   accelerator=nvidia-gpu
    ├── provider-litserve Deployment (по умолчанию: nodeSelector GPU + `nvidia.com/gpu: 1`)
    └── alloy DaemonSet
```

### LitServe: GPU-нода или CPU на master

В [`values.yaml`](helm/agent-lab/values.yaml) — `litserve.scheduleOnGpuNode` (по умолчанию `true`).

- **`true`** — под только на ноде с лейблом `accelerator=nvidia-gpu`, CUDA, лимит GPU 1.
- **`false`** — под на master (`kubernetes.io/hostname` = `masterNodeName`), `PROVIDER_LITSERVE__INFRA__ACCELERATOR=cpu` (медленнее, без выделенной GPU).

Переключение: правка values / `--set litserve.scheduleOnGpuNode=false`, затем `make k8s-deploy`.
Скрипт [`cluster-health.sh`](scripts/cluster-health.sh) проверяет `nvidia.com/gpu` на worker только если у Deployment всё ещё есть `nodeSelector.accelerator=nvidia-gpu`.

## CI/CD

[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) — ручной запуск (**Actions → Deploy → Run workflow**):

1. **`build`** — `docker build --target full` → push в GHCR (`ghcr.io/<owner>/agent-lab:<sha>` + `:latest` на default branch).
2. **`deploy`** — `helm upgrade --install` через `KUBECONFIG_B64`, с выбором **`litserve_node`**: **`gpu`** (по умолчанию, нода с `accelerator=nvidia-gpu`) или **`cpu`** (под на master, медленнее), затем `bash deploy/scripts/cluster-health.sh`.

Параметры workflow:

| Input | Значение |
|---|---|
| `image_tag` | Пусто = тег из build (короткий SHA); иначе явный тег образа. |
| `litserve_node` | `gpu` или `cpu` → `--set litserve.scheduleOnGpuNode=true/false`. |

Никакого SSH, SCP, `docker compose`. Один helm-релиз, единый артефакт.

## Конфигурация платформы для Helm (ConfigMap)

- **Канон** структуры и значений по умолчанию — только корневой **`conf.json`**.
- **`deploy/helm/agent-lab/files/app-conf.k8s-overlay.json`** — только узкие дельты без Helm ENV. Это **не** блок **`server`** (URL между сервисами там не трогаем — их даёт Helm ENV). Пример: вложенная секция **`services.browser.browser`** (рантайм browser в конфиге приложения), например **`cdp_endpoints.lightpanda: null`**, чтобы в кластере не тащить локальный endpoint из канона.
- **`deploy/helm/agent-lab/files/app-conf.json`** — **генерируется**, в репозитории **не хранится** (`.gitignore`). Перед **`helm template`** / **`helm lint`** / **`helm upgrade`** без целей **`make k8s-*`** нужно один раз выполнить **`make render-helm-app-conf`** или полагаться на CI (**`.github/workflows/deploy.yml`** рендерит файл перед **`helm lint`**).

Скрипт: **`deploy/scripts/render_helm_app_conf.py`**.

### Первый `helm install`: «invalid ownership metadata» у Secret `platform-secrets`

Если релиза **`agent-lab`** ещё нет, а в **`platform`** уже есть **`platform-secrets`** (ручной `kubectl`, не Helm), первый деплой с **`platformSecrets.create: true`** падает: Helm не может заявить ресурс без меток **`app.kubernetes.io/managed-by: Helm`** и аннотаций **`meta.helm.sh/release-*`**.

Удалите сиротский секрет и повторите деплой (значения возьмутся из GitHub Secrets):

```bash
kubectl delete secret platform-secrets -n platform
```

Перед установкой тот же случай отлавливает **`deploy/scripts/helm_precheck_install_secret_conflict.sh`** (CI и **`make k8s-deploy`** при заданном **`POSTGRES_PASSWORD`**).

## Идемпотентные скрипты (`deploy/scripts/`)

Все операции над кластером — через скрипты с общей библиотекой [`_common.sh`](scripts/_common.sh).
Каждый скрипт безопасен к повторному запуску: `[SKIP]` для уже сделанного, `[DO]` для нового, `[FAIL]` с диагностикой при ошибке.

| Скрипт | Где запускать | Назначение |
|---|---|---|
| [`bootstrap-master.sh`](scripts/bootstrap-master.sh) | master нода под root | MicroK8s + аддоны (dns/ingress/cert-manager/hostpath-storage) |
| [`bootstrap-gpu-worker.sh`](scripts/bootstrap-gpu-worker.sh) | gpu-worker под root | NVIDIA driver + container-toolkit + MicroK8s |
| [`join-cluster.sh`](scripts/join-cluster.sh) | master | `add-node` + SSH `microk8s join` + label + `enable gpu` на worker |
| [`setup-wildcard-tls.sh`](scripts/setup-wildcard-tls.sh) | локально / master | `cert-manager-webhook-regru` + ClusterIssuer DNS-01 + Certificate `platform-tls` |
| [`cluster-health.sh`](scripts/cluster-health.sh) | локально / master / CI | Полная проверка: ноды, GPU (если LitServe на GPU), поды, PVC, Ingress, Certificate, Postgres, Redis, Loki/Tempo, public health |
| [`backup-postgres.sh`](scripts/backup-postgres.sh) | локально / master | `pg_dumpall` через `kubectl exec`, опционально `--s3` в Selectel |
| [`restore-postgres.sh`](scripts/restore-postgres.sh) | локально / master | Restore из дампа в pod `postgres-0` |
| [`migrate-data-from-compose.sh`](scripts/migrate-data-from-compose.sh) | локально | Одноразово: SSH на старый docker-compose хост → `pg_dumpall` → restore в новый кластер |
| [`render_helm_app_conf.py`](scripts/render_helm_app_conf.py) | локально / CI | `conf.json` + `files/app-conf.k8s-overlay.json` → `files/app-conf.json` для Helm ConfigMap |
| [`helm_precheck_install_secret_conflict.sh`](scripts/helm_precheck_install_secret_conflict.sh) | CI / `make k8s-deploy` с секретами | Перед первым install: если релиза нет, а `platform-secrets` уже есть без меток Helm — понятная ошибка вместо «invalid ownership metadata» |

Обёртки в Makefile: `make k8s-deploy` / `k8s-health` / `k8s-backup` / `k8s-restore` / `k8s-rollback` / `k8s-uninstall`.

## GitHub Secrets

Деплой читает **`secrets.*` из репозитория** (Settings → Secrets and variables → Actions). Организационные секреты тоже доступны, если repo им наследует. Раньше использовался GitHub Environment `production` — он отключён, чтобы не затенять `KUBECONFIG_B64`. Если у вас секреты платформы заведены **только** в Environment `production`, перенесите их в Repository или верните `environment: production` в job `deploy` и заполните там все имена (включая непустой `KUBECONFIG_B64`).

### Доступ к кластеру

| Секрет | Что туда положить |
|---|---|
| `KUBECONFIG_B64` | На master: **`microk8s config \| base64 -w0`** (Linux) или **`microk8s config \| base64 \| tr -d '\n'`** (macOS). Один **repository secret** (Settings → Secrets → Actions). Job деплоя **без** GitHub Environment, чтобы секрет не затенялся пустым Environment-secret с тем же именем. |

### Платформа (передаются в Secret `platform-secrets`)

| Секрет | Назначение |
|---|---|
| `POSTGRES_PASSWORD` | пароль БД, общий для всех сервисных схем |
| `AUTH_JWT_SECRET` | подпись session JWT |
| `HF_TOKEN` | (опционально) Hugging Face token для litserve |
| `AUTH_YANDEX_CLIENT_ID` / `AUTH_YANDEX_CLIENT_SECRET` | OAuth Yandex |
| `AUTH_GOOGLE_CLIENT_ID` / `AUTH_GOOGLE_CLIENT_SECRET` | OAuth Google |
| `AUTH_GITHUB_CLIENT_ID` / `AUTH_GITHUB_CLIENT_SECRET` | OAuth GitHub |
| `AUTH_AMOCRM_CLIENT_ID` / `AUTH_AMOCRM_CLIENT_SECRET` | (опционально) AmoCRM |
| `AUTH_APPLE_PRIVATE_KEY` | (опционально) Sign in with Apple |
| `AUTH_DEMO_PASSWORD` | (опционально) демо-вход |
| `SELECTEL_ACCESS_KEY` / `SELECTEL_SECRET_KEY` | Selectel S3 (бакет `shvedzilla`) |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | LiveKit (WebRTC) |
| `TURN_SECRET` | static-auth-secret для coturn |
| `ONLYOFFICE_JWT_SECRET` | OnlyOffice DocumentServer JWT |
| `GRAFANA_ADMIN_PASSWORD` | пароль admin@grafana |
| `LLM_BOTHUB_API_KEY` | (опционально) LLM провайдер |
| `LLM_OPENROUTER_API_KEY` | (опционально) OpenRouter |
| `STT_CLOUD_RU_API_KEY` | (опционально) STT cloud.ru |
| `RAG_EMBEDDING_API_KEY` | (опционально) RAG embeddings (если отличается от LLM) |
| `PUSH_VAPID_PUBLIC_KEY` / `PUSH_VAPID_PRIVATE_KEY` | (опционально) Web Push VAPID |
| `PUSH_APNS_PRIVATE_KEY` | (опционально) APNs .p8 |
| `PUSH_FCM_CREDENTIALS_JSON` / `PUSH_FCM_PROJECT_ID` | (опционально) FCM service account |
| `YOOMONEY_*` | (опционально) платежи YooMoney |

Эти переменные задаются в GitHub Actions как env и передаются в Helm одним `--set-json platformSecrets=...` через `deploy/scripts/helm_platform_secrets_json.sh` (jq экранирует многострочные секреты).

## Ручной деплой (без CI)

Нужны **kubectl**, **helm**, **jq** (`brew install jq` / `apt install jq`) — jq собирает JSON секретов для `helm --set-json`.

```bash
# 1. KUBECONFIG настроен (kubectl get nodes показывает обе ноды)
kubectl get nodes
# NAME         STATUS   ROLES           AGE
# master       Ready    control-plane   ...
# gpu-worker   Ready    <none>          ...

# 2. Экспорт секретов и установка релиза (namespace создаётся `helm --create-namespace`, Secret — шаблон чарта при переданных platformSecrets):
export POSTGRES_PASSWORD=...
export AUTH_JWT_SECRET=...
export SELECTEL_ACCESS_KEY=...
export SELECTEL_SECRET_KEY=...
export LIVEKIT_API_KEY=...
export LIVEKIT_API_SECRET=...
export TURN_SECRET=...
export ONLYOFFICE_JWT_SECRET=...
export GRAFANA_ADMIN_PASSWORD=...
make k8s-deploy IMAGE_TAG=latest

# При необходимости обновить только секреты (релиз уже есть):
# source .env.k8s.secrets && make k8s-secrets-sync

# 3. Проверка
make k8s-status
make k8s-logs SVC=frontend
```

## Локальная валидация перед PR

```bash
make k8s-lint       # helm lint
make k8s-template   # рендер всех манифестов в stdout
```

## Откат

```bash
make k8s-rollback              # на предыдущую ревизию
helm history agent-lab -n platform   # список ревизий
helm rollback agent-lab <REV> -n platform   # на конкретную
```

## Полное удаление (PVC сохраняются)

```bash
make k8s-uninstall
# удалить PVC вручную, если нужно: kubectl delete pvc -n platform --all
```

## Миграция данных с предыдущей Docker Compose инсталляции

Одноразовая операция (не в CI):

```bash
# На старом сервере (где был docker-compose-prod):
docker exec agentlab_postgres pg_dumpall -U platform_user > /tmp/full_dump.sql
scp /tmp/full_dump.sql user@master:/tmp/

# На master ноде после helm install (postgres-0 уже Running):
microk8s kubectl cp /tmp/full_dump.sql platform/postgres-0:/tmp/full_dump.sql
microk8s kubectl exec -n platform postgres-0 -- \
  psql -U platform_user -f /tmp/full_dump.sql

# Проверка списка БД:
microk8s kubectl exec -n platform postgres-0 -- psql -U platform_user -l
```

Redis: AOF переносится при необходимости (TaskIQ очереди эфемерны, sessions в БД — переносить не обязательно).

## Структура чарта

```
deploy/helm/agent-lab/
├── Chart.yaml
├── values.yaml                 # дефолты (dev-friendly)
├── values-prod.yaml            # production overrides
├── files/                      # ConfigMap источники
│   ├── postgres-init.sql       # CREATE DATABASE для всех 7 сервисов + pgvector
│   ├── app-conf.json           # артефакт: conf.json + overlay (генерация, в git не коммитится)
│   ├── app-conf.k8s-overlay.json
│   ├── loki.yaml
│   ├── tempo.yaml
│   ├── alloy.config            # K8s discovery (вместо docker.sock)
│   ├── onlyoffice-theme.json
│   ├── grafana-datasources.yaml
│   ├── grafana-dashboards.yaml
│   ├── dashboards/             # 10 дашбордов
│   └── grafana-alerts/         # 3 файла (rules, contact-points, policies)
└── templates/
    ├── _helpers.tpl            # agentlab.appEnv, agentlab.image, agentlab.confVolume(Mount)
    ├── 01-platform-secrets.yaml  # Secret platform-secrets при platformSecrets.create=true
    ├── 02-configmap-app-conf.yaml
    ├── 10-postgres/            # StatefulSet + Service + ConfigMap init
    ├── 11-redis/               # StatefulSet + Service
    ├── 20-migrations-job.yaml  # helm hook post-install/post-upgrade
    ├── 30-apps/
    │   ├── deployments.yaml    # range по values.applications (9 сервисов)
    │   └── services.yaml       # range — ClusterIP для каждого
    ├── 40-workers/
    │   └── deployments.yaml    # range по values.workers (6 воркеров)
    ├── 50-gpu/litserve.yaml    # nodeSelector: accelerator=nvidia-gpu, nvidia.com/gpu: 1
    ├── 60-external/            # livekit, livekit-egress, coturn DaemonSet, onlyoffice
    ├── 70-observability/       # loki, tempo, grafana, alloy DaemonSet + ServiceAccount/RBAC
    ├── 80-ingress/             # cluster-issuer + 4 Ingress (platform, livekit, onlyoffice, grafana)
    └── NOTES.txt
```

После `helm upgrade` чарт создаёт ~65 K8s ресурсов (`make k8s-template | grep '^kind:' | sort | uniq -c`):

```
  1 ClusterIssuer
  1 ClusterRole
  1 ClusterRoleBinding
 11 ConfigMap
  2 DaemonSet
 19 Deployment
  4 Ingress
  1 Job
  1 Namespace
  2 PersistentVolumeClaim
 17 Service
  1 ServiceAccount
  4 StatefulSet
```

## Wildcard TLS

Для `*.humanitec.ru` чарт ссылается на Secret `platform-tls`. Если используется HTTP-01, доступен только apex `humanitec.ru` — wildcard приходится получать через DNS-01 (cert-manager + webhook регистратора, например [`cert-manager-webhook-regru`](https://github.com/regru/cert-manager-webhook-regru)). Установка webhook'а — одноразовая, описана в [`cluster-setup.md`](cluster-setup.md).
