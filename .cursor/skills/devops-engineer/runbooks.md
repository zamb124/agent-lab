# DevOps Runbooks — пошаговые сценарии

Каждая операция — через идемпотентный скрипт из `deploy/scripts/`, чтобы повторный запуск был безопасен.

## 1. Первичная настройка кластера с нуля

См. полный гайд в [`deploy/cluster-setup.md`](mdc:deploy/cluster-setup.md). Краткая выжимка:

```bash
# 1. DNS: setup-brand-dns.sh → 31.192.111.33 (оба apex). Whitelist Reg.ru API = этот IP.

# 2. На BM:
ssh root@31.192.111.33
git clone https://github.com/<owner>/agent-lab.git /root/agent-lab-deploy && cd /root/agent-lab-deploy
bash deploy/scripts/bootstrap-master.sh
# exit 10 — reboot и повторить

# 3. Wildcard TLS (kubectl на новый кластер):
export REGRU_USERNAME=... REGRU_PASSWORD=...
bash deploy/scripts/setup-wildcard-tls.sh

# 4. KUBECONFIG_B64 в GitHub (server 31.192.111.33, не 127.0.0.1; не печатать в чат):
gh secret set KUBECONFIG_B64 --body "$(bash deploy/scripts/kubeconfig-for-github-actions.sh)"

# 5. Заполнить остальные GitHub Secrets (см. deploy/README.md)

# 6. Первый деплой:
make k8s-secrets-sync
make k8s-deploy IMAGE_TAG=<sha>

# 9. Проверка:
make k8s-health
```

## 2. Деплой нового релиза

### Через CI (стандартно)

GitHub → Actions → Deploy → Run workflow. Опционально передать `image_tag` (по умолчанию короткий SHA).

CI делает: build → push GHCR → создание/обновление Secret **`ghcr-agent-lab-pull`** из **`GHCR_PULL_USERNAME`** / **`GHCR_PULL_TOKEN`** → один проход `helm upgrade --install` (`--create-namespace`, секреты через `deploy/scripts/helm_platform_secrets_json.sh` и `--set-json platformSecrets=...`) → cluster-health.sh.

### Вручную (для ad-hoc образов)

```bash
TAG="local-$(date +%s)"
docker build --target full -t ghcr.io/zamb124/agent-lab:$TAG .
docker push ghcr.io/zamb124/agent-lab:$TAG
make k8s-deploy IMAGE_TAG=$TAG
make k8s-health
```

## 3. Откат деплоя

Если после `make k8s-deploy` cluster-health показывает FAIL:

```bash
helm history agent-lab -n platform
# Найти предыдущую успешную ревизию (REV)
helm rollback agent-lab <REV> -n platform
# или просто на N-1:
make k8s-rollback
make k8s-health
```

Если откат helm не помогает (например, изменения схемы БД несовместимы) — restore Postgres из последнего бэкапа.

## 4. Бэкап Postgres

### Локально (одноразово)

```bash
make k8s-backup
# → backups/dump-<ts>.sql.gz
```

### Локальный дамп

```bash
export AWS_ENDPOINT_URL=https://s3.ru-3.storage.selcloud.ru
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
make k8s-backup
```

### Cron на master (ежедневно)

Простой systemd timer на master, вызывающий `make k8s-backup S3=...`. Helm-чарт это не описывает — добавляется отдельным CronJob в namespace platform при необходимости (раздел "Добавить CronJob" ниже).

## 5. Restore Postgres из бэкапа

```bash
# СНАЧАЛА: остановить сервисы, чтобы не было активных коннектов
kubectl -n platform scale deployment frontend flows crm rag sync office voice scheduler-api --replicas=0
# Воркеры тоже:
kubectl -n platform scale deployment flows-worker scheduler rag-worker sync-worker crm-worker idle-worker --replicas=0

# Restore (с подтверждением)
make k8s-restore FILE=backups/dump-20260103T093000Z.sql.gz

# Поднять обратно
make k8s-deploy IMAGE_TAG=<последний-stable-tag>
make k8s-health
```

## 6. Перевыпуск/продление TLS-сертификата

cert-manager перевыпускает Let's Encrypt автоматически за 30 дней до истечения. Если что-то сломалось:

```bash
# Посмотреть статус
kubectl get certificate -n platform
kubectl describe certificate platform-tls -n platform
kubectl get certificaterequests -n platform
kubectl get challenges -A

# Принудительный перевыпуск:
kubectl delete certificate platform-tls -n platform
bash deploy/scripts/setup-wildcard-tls.sh   # пересоздаст идемпотентно
# Ждём Ready — скрипт сам поллит до 10 мин

# Логи cert-manager:
kubectl logs -n cert-manager deployment/cert-manager -f
kubectl logs -n cert-manager deployment/cert-manager-webhook-regru -f
```

## 7. Обновление NVIDIA driver

```bash
kubectl -n platform scale deployment provider-litserve --replicas=0
ssh root@31.192.111.33
cd /root/agent-lab-deploy
git pull
bash deploy/scripts/bootstrap-nvidia.sh
# exit 10 — reboot, затем снова bootstrap-nvidia.sh / bootstrap-master.sh
nvidia-smi
kubectl -n platform scale deployment provider-litserve --replicas=1
make k8s-health
```

## 8. Добавление второй ноды (не канон)

Канон — одна нода. Если нужна вторая: `GPU_WORKER_HOST=root@<ip> bash deploy/scripts/join-cluster.sh` и добавить имя в `gpuNodeNames`. Taint `dedicated=gpu` только на **дополнительной** GPU-ноде, не на master.

## 8a. Перенос сервиса на другую ноду

### Apps / Workers / onlyoffice / litserve (stateless или с emptyDir — мгновенный)

```bash
# Через CI: GitHub Actions → Deploy → Run workflow
#   apps_node=<node>  или  service_overrides="<svc>=<node>"
# Или вручную:
helm upgrade --install agent-lab ./deploy/helm/agent-lab \
  --namespace platform --reuse-values \
  --set "applications.rag.nodeName=master" \
  --wait --timeout 15m
kubectl get pods -n platform -o wide   # проверить ноду
```

### StatefulSets с PVC (postgres / redis / loki / tempo / grafana)

ВНИМАНИЕ: остановка компонента на время переноса (~5–15 мин).

```bash
# Переносит с backup → helm upgrade → пересоздание PVC → restore:
bash deploy/scripts/migrate-pvc.sh postgres master
# Прогресс сохраняется: повторный запуск безопасен (backup за 5 мин — skip).
# Финальная проверка:
bash deploy/scripts/cluster-health.sh
```

### hostNetwork-сервисы (livekit / coturn / onlyoffice)

ВНИМАНИЕ: смена ноды меняет внешний IP — нужно обновить DNS.

```bash
# Обновляет DNS через Reg.ru API, затем helm upgrade:
REGRU_USERNAME=... REGRU_PASSWORD=... \
bash deploy/scripts/rebind-public-node.sh master 31.192.111.33
# Ждёт DNS_TTL=300s, после чего helm upgrade и cluster-health.sh.
```

## 9. Добавление CronJob (например, ежедневный backup в S3)

В `deploy/helm/agent-lab/templates/` создать `60-cronjobs/backup-postgres.yaml`:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: {{ .Values.namespace }}
spec:
  schedule: "0 3 * * *"        # каждый день в 03:00 UTC
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: postgres:17-alpine
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: {{ .Values.platformSecretName }}
                      key: postgres-password
                - name: AWS_ACCESS_KEY_ID
                  valueFrom:
                    secretKeyRef: { name: {{ .Values.platformSecretName }}, key: s3-access-key }
                - name: AWS_SECRET_ACCESS_KEY
                  valueFrom:
                    secretKeyRef: { name: {{ .Values.platformSecretName }}, key: s3-secret-key }
              command:
                - sh
                - -c
                - |
                  ts=$(date -u +%Y%m%dT%H%M%SZ)
                  pg_dumpall -h postgres -U platform_user --clean --if-exists | gzip > /tmp/dump-$ts.sql.gz
                  apk add --no-cache aws-cli
                  aws --endpoint-url http://seaweedfs:8333 \
                    s3 cp /tmp/dump-$ts.sql.gz s3://platform/backups/dump-$ts.sql.gz
```

Затем `make k8s-deploy` — CronJob применится без рестарта остальных подов.

## 10. Изменение размера PVC

Postgres / Loki / Tempo — PVC c `microk8s-hostpath`. Чтобы расширить:

1. Правка `values.yaml` (`postgres.storage: 100Gi` вместо 50Gi).
2. `make k8s-deploy`.
3. Если StorageClass поддерживает онлайн-расширение — PVC расширится сам. Проверить: `kubectl describe pvc data-postgres-0 -n platform`.
4. Если нет — `kubectl delete pvc data-postgres-0 -n platform` (ОПАСНО! только после backup) → пересоздаст с новым размером.

## 11. Полная пересборка с миграцией данных

Бывает редко: например, поменяли `microk8s-hostpath` на Longhorn.

```bash
# 1. Backup
make k8s-backup

# 2. helm uninstall (PVC сохраняются)
make k8s-uninstall
# или с удалением PVC:
kubectl delete pvc -n platform --all   # ОПАСНО

# 3. Поменять storageClassName в values.yaml

# 4. Заново
make k8s-deploy IMAGE_TAG=latest

# 5. Restore
make k8s-restore FILE=backups/dump-...sql.gz
```

## 12. Breaking change в Kubernetes версии

MicroK8s обновляется через snap channel. Перед обновлением:

```bash
# 1. Backup
make k8s-backup S3=s3://...

# 2. На master: проверить что всё в одной версии
microk8s kubectl version --short
# Server == Client

# 3. Drain noдev (kubectl drain не работает в MicroK8s так же — лучше snap refresh с маленьким channel-bump)
ssh root@31.192.111.33 'snap refresh microk8s --channel=1.35/stable'
make k8s-health
ssh root@31.192.111.33 'snap revert microk8s'
```

## 13. Изменение OAuth провайдера / секрета

```bash
# 1. Обновить GitHub Secret в Settings.

# 2. Запустить деплой через Actions (или вручную):
make k8s-secrets-sync
# secret platform-secrets обновится

# 3. Перезапустить поды, чтобы они подтянули новый ENV:
kubectl rollout restart deployment -n platform
make k8s-health
```

## 14. Открыть Grafana локально без публичного URL

```bash
kubectl port-forward -n platform svc/grafana 3000:3000
# Открыть http://localhost:3000, логин admin / пароль из Secret platform-secrets.grafana-admin-password
```
