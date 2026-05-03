# DevOps Troubleshooting — каталог типовых проблем

Каждая проблема: симптом → команды диагностики → причина → решение.

## 1. Pod в `CrashLoopBackOff` / `Error`

**Команды:**
```bash
kubectl get pods -n platform | grep -v Running
POD=<имя>
kubectl describe pod -n platform $POD | tail -50
kubectl logs -n platform $POD --previous --tail=200
kubectl logs -n platform $POD --tail=200
```

**Типовые причины:**
- ENV не задан → проверить `kubectl get secret platform-secrets -n platform -o yaml | grep <key>`. Решение: `make k8s-secrets-sync`.
- Postgres недоступен → `kubectl exec -n platform postgres-0 -- pg_isready`. Если нет — см. секцию 4.
- OOMKilled → `kubectl describe pod` → Events показывают OOMKilled. Решение: поднять `resources.limits.memory` в `values.yaml`.
- Образ не подгрузился (`ImagePullBackOff`) — см. секцию 2.

## 2. `ImagePullBackOff` / `ErrImagePull`

**Команды:**
```bash
kubectl describe pod -n platform $POD | grep -A5 Events
```

**Причины:**
- Тэг не существует в GHCR → проверить `https://github.com/<owner>/agent-lab/pkgs/container/agent-lab`.
- Нет access от MicroK8s к ghcr.io → `kubectl get nodes -o wide` (есть ли интернет на ноде), `ssh root@<node> 'docker pull ghcr.io/<owner>/agent-lab:<tag>'`.
- Приватный образ без imagePullSecret → нужен imagePullSecret (для public образа не требуется).

**Решение:**
- Перебилдить с правильным тэгом: `make k8s-deploy IMAGE_TAG=<correct-tag>`.

## 3. Certificate `Issuing` уже > 5 минут

**Команды:**
```bash
kubectl get certificate -n platform
kubectl describe certificate platform-tls -n platform
kubectl get certificaterequests -n platform
kubectl get challenges -A
kubectl describe challenge -n platform <name>
kubectl logs -n cert-manager deployment/cert-manager --tail=200
kubectl logs -n cert-manager deployment/cert-manager-webhook-regru --tail=200
```

**Причины:**
- HTTP-01 challenge не проходит (для wildcard используется DNS-01) → нет публичного доступа `/.well-known/acme-challenge/...` на apex.
- DNS-01 webhook не отвечает → проверить `kubectl get pods -n cert-manager`, логи webhook-regru.
- regru-credentials Secret устарел → `kubectl delete secret regru-credentials -n cert-manager` и `bash deploy/scripts/setup-wildcard-tls.sh`.
- Rate limit Let's Encrypt (5 за неделю на одну doсtain) → подождать или использовать staging issuer.

**Решение:**
- `bash deploy/scripts/setup-wildcard-tls.sh` (идемпотентно — пересоздаст Issuer и Certificate).
- Принудительный перевыпуск: `kubectl delete certificate platform-tls -n platform` → скрипт пересоздаст.

## 4. Postgres под `Pending` / не Running

**Команды:**
```bash
kubectl describe pod postgres-0 -n platform | tail -30
kubectl get pvc -n platform | grep postgres
kubectl describe pvc data-postgres-0 -n platform
kubectl get events -n platform --sort-by='.lastTimestamp' | tail -30
```

**Причины:**
- PVC не Bound → проверить `kubectl get sc` (StorageClass `microk8s-hostpath` есть?).
- nodeSelector `kubernetes.io/hostname: master` не матчится → проверить `kubectl get node` (есть ли нода с таким hostname).
- Диск на ноде кончился → `ssh root@84.38.184.105 df -h /var/snap/microk8s/common/default-storage`.
- init.sql упал → `kubectl logs postgres-0 -n platform`. Часто из-за прав на ConfigMap или дубликата в init.sql.

**Решение:**
- При нехватке места: cleanup старых snap revisions: `ssh root@84.38.184.105 'snap set system refresh.retain=2 && snap refresh'`.
- При проблемах с init.sql: правка `deploy/helm/agent-lab/files/postgres-init.sql` + `make k8s-deploy`. Если PVC уже инициализирован старой версией — init.sql НЕ перезапустится. Решение: `kubectl exec postgres-0 -- psql ...` для миграции вручную или пересоздание PVC (с потерей данных — нужен backup).

## 5. LitServe не стартует на GPU / без GPU

**Симптомы:** `nvidia.com/gpu: 0` в Allocatable, под `Pending`, или CrashLoopBackOff с `RuntimeError: cuda not available`.

**Команды:**
```bash
kubectl get pods -n platform -o wide | grep provider-litserve
kubectl describe node gpu-worker | grep -A3 Allocatable
kubectl describe pod -n platform <litserve-pod>
kubectl logs -n platform deployment/provider-litserve --tail=200

# На gpu-worker:
ssh root@188.246.224.228
nvidia-smi
microk8s status --addon gpu
```

**Причины:**
- GPU аддон выключен → `ssh root@188.246.224.228 microk8s enable gpu`.
- NVIDIA Device Plugin не запустился → `kubectl get pods -n gpu-operator-resources` (или `kubectl get pods -A | grep nvidia`).
- Driver сломался после обновления ядра → `nvidia-smi` падает → переустановить driver (см. runbook 7).
- Лейбл `accelerator=nvidia-gpu` не проставлен → `kubectl label node gpu-worker accelerator=nvidia-gpu --overwrite`.

**Решение:**
- `bash deploy/scripts/join-cluster.sh` (идемпотентно — переставит лейбл, попробует enable gpu).
- При полном провале driver: `runbook 7` (обновление NVIDIA driver).

## 6. Ingress отдаёт 502 / 503 / 504

**Команды:**
```bash
kubectl get ingress -n platform
kubectl describe ingress platform -n platform
kubectl get endpoints -n platform <service-name>
kubectl get pods -n platform -l app=<service> -o wide
kubectl logs -n platform deployment/<service> --tail=100
# Логи ingress-nginx:
kubectl logs -n ingress deployment/nginx-ingress-microk8s-controller --tail=200
```

**Причины:**
- Под не Ready → readiness probe не проходит. `kubectl describe pod`.
- Service не имеет endpoints → labels не совпадают между Deployment и Service. `kubectl get endpoints -n platform`.
- Ingress controller не видит правило → `kubectl describe ingress`.
- TLS expired → см. секцию 3.

**Решение:**
- Если под не готов: подождать readinessProbe (есть `startupProbe`), или поднять `failureThreshold`.
- Если labels рассинхронизированы: правка template + `make k8s-deploy`.

## 7. Loki не пишет логи / в Explore пусто

**Команды:**
```bash
kubectl get pods -n platform -l app=alloy -o wide   # должен быть на КАЖДОЙ ноде
kubectl logs -n platform daemonset/alloy --tail=200
kubectl get sa -n platform alloy
kubectl get clusterrolebinding alloy -o yaml
kubectl exec -n platform loki-0 -- wget -q -O - http://localhost:3100/ready
```

**Причины:**
- alloy DaemonSet не запущен на новой ноде → проверить `tolerations` в `templates/70-observability/alloy-daemonset.yaml`.
- ServiceAccount alloy без RBAC → `kubectl get clusterrole alloy`. Должны быть pods/list-watch и nodes/proxy.
- alloy не может прочитать `/var/log/pods` → проверить `securityContext` в DaemonSet.
- Loki переполнен → `kubectl exec loki-0 -- df -h /loki`. Решение: правка `files/loki.yaml` (`retention_period`).

## 8. Trace_id есть в логе, но в Tempo не находится

**Команды:**
```bash
kubectl get pods -n platform | grep tempo
kubectl logs -n platform tempo-0 --tail=200
kubectl exec -n platform deployment/alloy -c alloy -- env | grep OTEL
```

**Причины:**
- Сервис не отправляет trace в Alloy → проверить `OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4317` в Pod env.
- Alloy не форвардит → лог alloy.
- Tempo переполнен → проверить PVC.

## 9. Helm

### 9.1 Первый install: `invalid ownership metadata` у Secret `platform-secrets`

**Симптомы:** `Release "agent-lab" does not exist. Installing...` затем ошибка про отсутствие `app.kubernetes.io/managed-by: Helm` и аннотаций `meta.helm.sh/release-name` у существующего Secret.

**Причина:** в namespace **`platform`** уже есть **`platform-secrets`**, созданный не через Helm (kubectl, сторонний скрипт), а деплой включает **`platformSecrets.create: true`**.

**Решение:** при необходимости сохранить ключи, затем `kubectl delete secret platform-secrets -n platform` и повторить деплой. В GitHub Actions включите вход **`replace_orphan_platform_secret`** в workflow Deploy (удаление секрета перед install). Префлайт: **`deploy/scripts/helm_precheck_install_secret_conflict.sh`**. Подробнее — **`deploy/README.md`** (раздел про первый install).

### 9.2 `helm upgrade` завис / timeout

**Команды:**
```bash
kubectl get events -n platform --sort-by='.lastTimestamp' | tail -50
kubectl get pods -n platform | grep -v Running
helm history agent-lab -n platform   # последняя ревизия pending-upgrade?
```

**Причины:**
- Истёк лимит **`helm --wait`** (**`context deadline exceeded`** в логе Helm) — первый install с большим числом образов и StatefulSets часто дольше 15m; в репозитории по умолчанию **30m** (CI и `HELM_WAIT_TIMEOUT` в Makefile).
- Под не входит в Ready (failed startupProbe) → `helm upgrade --wait` ждёт rolloutReady.
- PVC не Bound (см. секцию 4).
- Ресурсный квоты: `kubectl describe nodes | grep Allocated` — нет ли OOM на ноде.
- Helm в pending state из-за фейла предыдущего: см. **§9.3** или `helm rollback agent-lab -n platform` / при крайней необходимости `helm uninstall && reinstall`.

**Решение:**
- Подкрутить `--timeout 45m` при очень медленном первом pull образов (по умолчанию **30m** в Makefile и CI).
- Если нужно только снять блокировку **без отката приложений** — **§9.3**.
- Если нужен именно откат манифестов предыдущей ревизии: `helm history` → `helm rollback`.

### 9.3 `another operation (install/upgrade/rollback) is in progress`

**Симптомы:** `helm upgrade` / CI Deploy падает с **`UPGRADE FAILED: another operation ... is in progress`**.

**Причина:** предыдущий install/upgrade/rollback оборвался (timeout, Ctrl+C, второй параллельный деплой). В namespace остаётся Helm Secret ревизии с label **`status=pending-upgrade`**, **`pending-install`** или **`pending-rollback`** (`sh.helm.release.v1.<release>.v<N>`).

**Решение без `helm rollback` (Pod в кластере не откатываются):**
```bash
make k8s-helm-clear-pending
# эквивалент:
# HELM_NAMESPACE=platform HELM_RELEASE=agent-lab bash deploy/scripts/helm_clear_pending_release.sh
```
Затем повторить **`make k8s-deploy`** или workflow **Deploy**. Убедитесь, что нет второго одновременного запуска Helm против того же релиза.

**Диагностика:**
```bash
kubectl get secrets -n platform -l owner=helm,name=agent-lab -o custom-columns=NAME:.metadata.name,STATUS:.metadata.labels.status
```

## 10. KUBECONFIG_B64 не валиден

**Симптомы:** CI шаг "Configure kubeconfig" падает с `error: not a valid x509 certificate`.

**Решение:**
```bash
# На master:
ssh root@84.38.184.105
microk8s config | base64

# Скопировать вывод полностью (без переноса строк) и обновить GitHub Secret KUBECONFIG_B64.
```

## 11. PVC не расширяется

**Команды:**
```bash
kubectl describe pvc <name> -n platform
kubectl get sc microk8s-hostpath -o yaml | grep allowVolumeExpansion
```

**Причины:**
- StorageClass `microk8s-hostpath` обычно не поддерживает онлайн-расширение → `allowVolumeExpansion: false`.

**Решение:**
- Backup → удалить PVC → пересоздать с большим размером → restore.

## 12. Под на gpu-worker не шедулится

**Команды:**
```bash
kubectl describe pod <pod> -n platform | grep -A5 Events
# обычно: 0/2 nodes available: 1 node(s) didn't match Pod's node affinity
kubectl describe node gpu-worker | grep -A3 Labels
kubectl describe node gpu-worker | grep -A5 Taints
```

**Причины:**
- Лейбл слетел → `kubectl label node gpu-worker accelerator=nvidia-gpu --overwrite`.
- Taint без матча toleration → проверить `tolerations` в `templates/50-gpu/litserve.yaml`.

## 13. Worker Deployment не обрабатывает задачи

**Команды:**
```bash
kubectl get pods -n platform | grep worker
kubectl logs -n platform deployment/flows-worker --tail=200
# Redis broker:
kubectl exec -n platform redis-0 -- redis-cli -n 1 keys 'taskiq:*' | head
kubectl exec -n platform redis-0 -- redis-cli -n 1 llen 'taskiq:queue:default'
```

**Причины:**
- Воркер падает на старте → лог покажет ImportError / неверный AUTH_JWT_SECRET и т.п.
- Очередь пустая → задачи не пишутся (баг на стороне отправителя — см. логи app сервиса).
- Воркеры подключаются к не тому Redis → проверить `TASKS__BROKER_URL`.

## 14. После деплоя `make k8s-health` показывает FAIL для нескольких сервисов

**Команды:**
```bash
make k8s-health 2>&1 | grep FAIL
kubectl get pods -n platform | grep -v Running
kubectl get events -n platform --sort-by='.lastTimestamp' | tail -50
```

**Решение:**
- Если массово (вся платформа): откат — `make k8s-rollback`.
- Если 1-2 сервиса: `kubectl rollout restart deployment/<svc> -n platform`. Если не помогает — `kubectl logs` и анализ.

## 15. Загрузка диска master на 100%

**Команды:**
```bash
ssh root@84.38.184.105
df -h
du -sh /var/snap/microk8s/common/default-storage/* | sort -h | tail
du -sh /var/lib/snapd/* | sort -h | tail
```

**Причины:**
- Loki/Tempo переполнили PVC.
- Старые snap revisions.
- Docker images cache (если оставались от docker compose).

**Решение:**
- `snap set system refresh.retain=2 && snap refresh`.
- Уменьшить `retention_period` в `files/loki.yaml`.
- Если на ноде остались docker volumes старого compose: `docker volume ls`, `docker volume prune` (ОПАСНО если волюм нужен).

## 16. Sync (WebSocket) не подключается

**Команды:**
```bash
# В браузере DevTools → Network → WS → проверить URL и статус.
kubectl logs -n platform deployment/sync --tail=200
kubectl get ingress platform -n platform -o yaml | grep -A2 sync
```

**Причины:**
- Ingress proxy-read-timeout слишком маленький → в нашем чарте 300s, должно хватить.
- WebSocket Upgrade не пробрасывается nginx → ingress-nginx делает это по умолчанию для WS.
- AUTH_JWT_SECRET рассогласован между фронтом и sync → один Secret, одно значение.

## Полезные общие команды

```bash
# Все события за последний час, отсортированные:
kubectl get events -A --sort-by='.lastTimestamp' | tail -50

# Топ потребителей CPU/RAM:
kubectl top nodes
kubectl top pods -n platform --sort-by=memory

# Что именно изменилось в helm release:
helm get values agent-lab -n platform > /tmp/current.yaml
diff /tmp/current.yaml deploy/helm/agent-lab/values.yaml

# Снятие текущего рендера манифестов из релиза:
helm get manifest agent-lab -n platform > /tmp/release.yaml

# Принудительный rollout без изменений (например после изменения Secret):
kubectl rollout restart deployment -n platform

# Проверить что Pod видит правильный Secret:
kubectl exec -n platform deployment/frontend -- env | grep AUTH

# Прокси Postgres локально (для psql / DBeaver):
kubectl port-forward -n platform postgres-0 5432:5432
# затем: psql -h 127.0.0.1 -U platform_user platform_shared
```
