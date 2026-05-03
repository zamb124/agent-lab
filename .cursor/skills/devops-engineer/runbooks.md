# DevOps Runbooks — пошаговые сценарии

Каждая операция — через идемпотентный скрипт из `deploy/scripts/`, чтобы повторный запуск был безопасен.

## 1. Первичная настройка кластера с нуля

См. полный гайд в [`deploy/cluster-setup.md`](mdc:deploy/cluster-setup.md). Краткая выжимка:

```bash
# 1. DNS A-записи у регистратора (humanitec.ru, *.humanitec.ru, livekit/onlyoffice/grafana → 84.38.184.105)

# 2. На master:
ssh root@84.38.184.105
git clone https://github.com/<owner>/agent-lab.git /opt/agent-lab && cd /opt/agent-lab
bash deploy/scripts/bootstrap-master.sh

# 3. На gpu-worker:
ssh root@188.246.224.228
git clone https://github.com/<owner>/agent-lab.git /opt/agent-lab && cd /opt/agent-lab
bash deploy/scripts/bootstrap-gpu-worker.sh
# Если exit 10 — reboot и повторить

# 4. На master:
bash deploy/scripts/join-cluster.sh

# 5. Wildcard TLS (с любой машины с kubectl + helm):
export REGRU_USERNAME=... REGRU_PASSWORD=...
bash deploy/scripts/setup-wildcard-tls.sh

# 6. KUBECONFIG_B64 в GitHub:
ssh root@84.38.184.105 microk8s config | base64
# → GitHub Settings → Secrets → KUBECONFIG_B64

# 7. Заполнить остальные GitHub Secrets (см. deploy/README.md)

# 8. Первый деплой через CI или вручную:
make k8s-secrets-sync
make k8s-deploy IMAGE_TAG=latest

# 9. Проверка:
make k8s-health
```

## 2. Деплой нового релиза

### Через CI (стандартно)

GitHub → Actions → Deploy → Run workflow. Опционально передать `image_tag` (по умолчанию короткий SHA).

CI делает: build → push GHCR → один проход `helm upgrade --install` (`--create-namespace`, секреты через `deploy/scripts/helm_platform_secrets_lib.sh`) → cluster-health.sh.

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

### Локально + S3 (Selectel)

```bash
export AWS_ENDPOINT_URL=https://s3.ru-3.storage.selcloud.ru
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
make k8s-backup S3=s3://shvedzilla/backups/
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

`migrate-data-from-compose.sh` — то же самое, но дамп берётся через SSH из старого docker-compose стенда.

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

## 7. Обновление NVIDIA driver на GPU-ноде

```bash
# 1. На master: scale provider-litserve до 0
kubectl -n platform scale deployment provider-litserve --replicas=0

# 2. SSH на gpu-worker:
ssh root@188.246.224.228
cd /opt/agent-lab
git pull   # получить актуальный bootstrap скрипт

# 3. Обновить driver (idempotent — проверит, нужно ли)
apt update && apt upgrade -y
ubuntu-drivers autoinstall
reboot   # если был upgrade

# 4. После reboot повторно:
bash deploy/scripts/bootstrap-gpu-worker.sh
nvidia-smi   # должен показать новый driver

# 5. На master: scale обратно
kubectl -n platform scale deployment provider-litserve --replicas=1
make k8s-health
```

## 8. Добавление новой ноды в кластер

```bash
# 1. На новой ноде (Ubuntu 22.04+):
ssh root@<NEW_IP>
git clone https://github.com/<owner>/agent-lab.git /opt/agent-lab && cd /opt/agent-lab

# Если это GPU нода — bootstrap-gpu-worker; иначе — обычный bootstrap (можно скопировать bootstrap-master.sh, но только snap install + минимальные аддоны):
# Для CPU worker нужно создать deploy/scripts/bootstrap-cpu-worker.sh (по аналогии).
bash deploy/scripts/bootstrap-gpu-worker.sh   # или новый bootstrap-cpu-worker.sh

# 2. На master:
GPU_HOST_IP=<NEW_IP> GPU_NODE_NAME=<имя> bash deploy/scripts/join-cluster.sh

# 3. Если нода для специфической нагрузки — добавить лейбл:
kubectl label node <имя> role=worker

# 4. Если нужно прибить какой-то Deployment к этой ноде — правка values.yaml + nodeSelector в шаблоне.
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
                    secretKeyRef: { name: {{ .Values.platformSecretName }}, key: selectel-access-key }
                - name: AWS_SECRET_ACCESS_KEY
                  valueFrom:
                    secretKeyRef: { name: {{ .Values.platformSecretName }}, key: selectel-secret-key }
              command:
                - sh
                - -c
                - |
                  ts=$(date -u +%Y%m%dT%H%M%SZ)
                  pg_dumpall -h postgres -U platform_user --clean --if-exists | gzip > /tmp/dump-$ts.sql.gz
                  apk add --no-cache aws-cli
                  aws --endpoint-url https://s3.ru-3.storage.selcloud.ru \
                    s3 cp /tmp/dump-$ts.sql.gz s3://shvedzilla/backups/dump-$ts.sql.gz
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
make k8s-backup S3=s3://shvedzilla/backups/

# 2. helm uninstall (PVC сохраняются)
make k8s-uninstall
# или с удалением PVC:
kubectl delete pvc -n platform --all   # ОПАСНО

# 3. Поменять storageClassName в values.yaml

# 4. Заново
make k8s-deploy IMAGE_TAG=latest

# 5. Restore
make k8s-restore FILE=backups/dump-...sql.gz S3=s3://shvedzilla/backups/dump-...sql.gz
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
ssh root@84.38.184.105 'snap refresh microk8s --channel=1.31/stable'
# Подождать рестарта, потом то же на gpu-worker:
ssh root@188.246.224.228 'snap refresh microk8s --channel=1.31/stable'

# 4. После обновления:
make k8s-health
# Если что-то сломалось — snap revert:
ssh root@84.38.184.105 'snap revert microk8s'
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
