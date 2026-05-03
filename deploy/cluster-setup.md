# Одноразовая настройка MicroK8s кластера

Все шаги — **идемпотентные скрипты** в [`deploy/scripts/`](scripts/). Повторный запуск
любого скрипта проверяет реальное состояние и пропускает уже выполненное (`[SKIP]`)
или досогласовывает (`[DO]`). Безопасно запускать заново при любом сбое.

## 0. Предусловия (вне кластера)

| Что | Где | Действие |
|---|---|---|
| DNS A `humanitec.ru` → `84.38.184.105` | reg.ru панель | один раз |
| DNS A `*.humanitec.ru` → `84.38.184.105` | reg.ru панель | один раз |
| DNS A `livekit.humanitec.ru` → `84.38.184.105` | reg.ru панель | один раз |
| DNS A `onlyoffice.humanitec.ru` → `84.38.184.105` | reg.ru панель | один раз |
| DNS A `grafana.humanitec.ru` → `84.38.184.105` | reg.ru панель | один раз |
| Ubuntu 22.04+ на обеих нодах | сервер | один раз |
| SSH ключ для root@84.38.184.105 и root@188.246.224.228 | локально | один раз |

## 1. Master нода (84.38.184.105)

```bash
ssh root@84.38.184.105
git clone https://github.com/<owner>/agent-lab.git /root/agent-lab-deploy && cd /root/agent-lab-deploy
bash deploy/scripts/bootstrap-master.sh
```

Скрипт ставит MicroK8s (канал `MICROK8S_CHANNEL=1.35/stable`, см. `snap info microk8s`),
включает core-аддоны `dns hostpath-storage ingress cert-manager` и community-аддон `portainer`
(NodePort 30777/30779), печатает `KUBECONFIG_B64` для GitHub Secret.

**Idempotent.** Повторный запуск: всё `[SKIP]`.

## 2. GPU worker нода (188.246.224.228)

```bash
ssh root@188.246.224.228
git clone https://github.com/<owner>/agent-lab.git /root/agent-lab-deploy && cd /root/agent-lab-deploy
bash deploy/scripts/bootstrap-gpu-worker.sh
```

Скрипт ставит NVIDIA driver (если нет — exit 10, нужен reboot и повторный запуск),
`nvidia-container-toolkit`, MicroK8s, конфигурирует `containerd` через drop-in
`/etc/containerd/conf.d/99-nvidia.toml` и добавляет `imports` в шаблон containerd.

**Idempotent.** Повторный запуск: `[SKIP]` для уже сделанных шагов.

## 3. Объединение в кластер

С master ноды:

```bash
ssh root@84.38.184.105
cd /root/agent-lab-deploy
bash deploy/scripts/join-cluster.sh
```

Скрипт:
- проверяет SSH master → gpu-worker (генерит ed25519 ключ при необходимости);
- выпускает разовый `microk8s add-node` токен;
- по SSH применяет `microk8s join --worker` на gpu-worker (data-plane, не control-plane);
- ждёт `Ready`;
- проставляет лейбл `accelerator=nvidia-gpu`.

NVIDIA k8s-device-plugin DaemonSet ставит Helm-чарт `agent-lab` (`templates/50-gpu/nvidia-device-plugin.yaml`),
он публикует `nvidia.com/gpu` в Allocatable после первого `make k8s-deploy`.

**Idempotent.** Если нода уже в кластере — `[SKIP]` для join, label досогласовывается.

## 4. Wildcard TLS (DNS-01 через reg.ru)

С локальной машины или master:

```bash
export REGRU_USERNAME='<логин reg.ru>'
export REGRU_PASSWORD='<API-пароль reg.ru>'
bash deploy/scripts/setup-wildcard-tls.sh
```

Скрипт:
- `git clone` `flant/cert-manager-webhook-regru` в `${TMPDIR:-/tmp}/cert-manager-webhook-regru`;
- `helm upgrade --install regru-webhook` (image `ghcr.io/flant/cluster-issuer-regru:1.2.0`);
- создаёт `ClusterIssuer letsencrypt-prod-dns01`;
- создаёт `Certificate platform-tls` для `humanitec.ru` + `*.humanitec.ru` в namespace `platform`;
- ждёт `Ready=True` (DNS-01 challenge у Let's Encrypt — до 10 минут на первом выпуске).

В CI скрипт вызывается перед `helm upgrade --install` (`.github/workflows/deploy.yml`).
Reg.ru API требует whitelist IP master-ноды (Настройки → API в личном кабинете).

**Idempotent.** При повторном запуске и уже Ready Certificate выходит сразу через fast-path skip.

## 5. Сохранение kubeconfig в GitHub

```bash
ssh root@84.38.184.105 microk8s config | base64
# Результат → GitHub Settings → Secrets → KUBECONFIG_B64
```

Полный список GitHub Secrets — в [`README.md`](README.md).

## 6. Первый деплой

```bash
# С локальной машины (kubectl настроен)
# Заполнить ENV из секретов, затем:
make k8s-secrets-sync
make k8s-deploy IMAGE_TAG=latest
```

Или через CI: запустить `Deploy` workflow в GitHub Actions.

## 7. Полная проверка здоровья

```bash
make k8s-health
# или
bash deploy/scripts/cluster-health.sh
```

Скрипт проверяет: ноды Ready, GPU, поды Running, все ожидаемые Deployments/StatefulSets/DaemonSets,
PVC Bound, Ingress, Certificates Ready, Postgres alive, Redis alive, Loki/Tempo ready, public health endpoints.
Exit 0 только если ВСЁ OK.

## 8. Бэкап и восстановление Postgres

```bash
make k8s-backup                              # → backups/dump-<ts>.sql.gz
make k8s-restore FILE=backups/dump-<ts>.sql.gz
```

Подробности по флагам (`--s3 s3://...` для Selectel) — в скриптах `backup-postgres.sh` / `restore-postgres.sh`.

## 9. Что НЕ нужно делать (анти-шаблоны)

- НЕ открывать `ufw allow 5432` или `ufw allow 6379` — связь Postgres/Redis между нодами через ClusterIP.
- НЕ запускать `docker compose` на нодах — на нодах живёт только MicroK8s.
- НЕ копировать `init.sql` на хост — он в ConfigMap чарта.
- НЕ делать `kubectl apply -f` отдельных манифестов мимо чарта — релиз управляется только Helm.
- НЕ держать `static-server` Deployment отдельно — frontend сам отдаёт статику через initContainer.
- НЕ редактировать ресурсы через `kubectl edit` — только через PR в Helm-чарт + `helm upgrade`.
