# GitHub Actions

| Workflow | Триггер | Описание |
|---|---|---|
| [`deploy.yml`](deploy.yml) | `workflow_dispatch` | Build → push GHCR → `helm upgrade --install` в MicroK8s; input **`litserve_node`**: `gpu` \| `cpu` |
| [`mobile-android-build.yml`](mobile-android-build.yml) | manual / по тегу | Сборка Android-приложения |
| [`mobile-pwa-lighthouse.yml`](mobile-pwa-lighthouse.yml) | по расписанию / manual | Lighthouse аудит PWA (`PWA_LIGHTHOUSE_URL`) |

## Deploy: схема

```
GitHub Actions (Run workflow)
    │
    ├─ build job
    │     docker build --target full
    │     push → ghcr.io/<owner>/agent-lab:<sha> (+ :latest на default branch)
    │
    └─ deploy job (needs: build)
          KUBECONFIG_B64 → ~/.kube/config
          kubectl create secret platform-secrets (из GitHub Secrets)
          helm upgrade --install agent-lab ./deploy/helm/agent-lab \
              --namespace platform --create-namespace \
              --values values.yaml --values values-prod.yaml \
              --set image.tag=<sha> \
              --set litserve.scheduleOnGpuNode=<true|false из input litserve_node> \
              --wait --timeout 15m
          bash deploy/scripts/cluster-health.sh (CHECK_PUBLIC=1)

MicroK8s cluster
├── master (84.38.184.105)         hostname=master
│   └── Postgres, Redis, all apps + workers, observability, ingress
│       (и provider-litserve при litserve_node=cpu)
└── gpu-worker (188.246.224.228)   accelerator=nvidia-gpu
    └── provider-litserve при litserve_node=gpu (nodeSelector + nvidia.com/gpu: 1)
```

## Конфигурация и секреты

Полная документация и список GitHub Secrets — в `[deploy/README.md](../../deploy/README.md)`. Здесь — короткая выжимка.

### Доступ к кластеру (обязательно)

| Secret | Источник | Где используется |
|---|---|---|
| `KUBECONFIG_B64` | См. **`deploy/README.md`** (Environment `production` перекрывает Repository; пустой Environment-secret ломает деплой). Опционально **`KUBECONFIG_B64_REPOSITORY`** в repo как fallback. |

### Платформенные секреты (передаются в `platform-secrets`)

`deploy` job шагом "Sync platform-secrets" формирует `kubectl create secret generic platform-secrets ...` из переменных окружения (см. полный список в `deploy/README.md`).

Минимум обязательных:

| Secret | Назначение |
|---|---|
| `POSTGRES_PASSWORD` | Пароль PostgreSQL (общий для всех 7 сервисных БД) |
| `AUTH_JWT_SECRET` | Подпись session JWT |
| `SELECTEL_ACCESS_KEY` / `SELECTEL_SECRET_KEY` | Selectel S3 |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | LiveKit |
| `TURN_SECRET` | coturn static-auth-secret |
| `ONLYOFFICE_JWT_SECRET` | OnlyOffice DocumentServer JWT |
| `GRAFANA_ADMIN_PASSWORD` | пароль admin@grafana |

Опциональные: OAuth (Yandex/Google/GitHub/AmoCRM/Apple), LLM API (BotHub/OpenRouter), Push (VAPID/APNs/FCM), YooMoney, STT cloud.ru, HF token для litserve.

## OAuth Callback URLs

Прописать в консолях провайдеров:

| Провайдер | Callback URL |
|---|---|
| Yandex | `https://humanitec.ru/auth/callback/yandex` |
| Google | `https://humanitec.ru/auth/callback/google` |
| GitHub | `https://humanitec.ru/auth/callback/github` |
| Apple (Services ID) | `https://humanitec.ru/auth/callback/apple` |

## Что НЕ делает CI

- **Не настраивает кластер MicroK8s.** Это одноразовая операция, см. `[deploy/cluster-setup.md](../../deploy/cluster-setup.md)`.
- **Не ставит cert-manager / ingress-nginx.** Аддоны MicroK8s, включаются вручную при настройке кластера.
- **Не управляет DNS.** A-записи у регистратора, DNS-01 webhook для wildcard — отдельные шаги.
- **Не делает SSH/SCP** — всё через `kubectl` и `helm` поверх `KUBECONFIG_B64`.
- **Не запускает миграции напрямую** — Helm hook Job `migrations` (post-install/post-upgrade) делает `python -m scripts.db_migrate upgrade` сам.

## Откат

Если деплой прошёл, но что-то сломалось:

```bash
helm history agent-lab -n platform
helm rollback agent-lab <REV> -n platform
```

Если деплой не прошёл (helm timeout или валидация не дала пройти):

- `kubectl get pods -n platform` — найти не-Running
- `kubectl describe pod -n platform <pod>` — причина
- `kubectl logs -n platform deployment/<svc> --tail=200`
- При полной поломке: `helm rollback` на предыдущую успешную ревизию.

## Mobile: Lighthouse CI

Workflow `[mobile-pwa-lighthouse.yml](mobile-pwa-lighthouse.yml)` — по расписанию и вручную; проверяет PWA на URL из секрета **`PWA_LIGHTHOUSE_URL`** (например `https://humanitec.ru/`).
