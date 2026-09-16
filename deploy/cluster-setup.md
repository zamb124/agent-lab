# Одноразовая настройка MicroK8s кластера

Все шаги — **идемпотентные скрипты** в [`deploy/scripts/`](scripts/). Повторный запуск
любого скрипта проверяет реальное состояние и пропускает уже выполненное (`[SKIP]`)
или досогласовывает (`[DO]`). Безопасно запускать заново при любом сбое.

Кластер — **одна нода** `hostname=master`, IP `31.192.111.33`: control-plane, все поды и GPU
(LitServe + NVIDIA device plugin). Taint `dedicated=gpu` не ставится.

`ytai.tech` живёт на `84.38.184.105`, не namespace `platform`, этим гайдом не трогать.

## 0. Предусловия (вне кластера)

Primary apex — **linnex.io**; legacy apex **humanitec.ru** остаётся для regression. DNS для обоих apex настраивается скриптом [`setup-brand-dns.sh`](scripts/setup-brand-dns.sh); см. [`docs/multi-brand-prod-smoke.md`](docs/multi-brand-prod-smoke.md).

| Что | Где | Действие |
|---|---|---|
| DNS A `linnex.io` → `31.192.111.33` | `setup-brand-dns.sh` / reg.ru | один раз |
| DNS A `*.linnex.io` → `31.192.111.33` | то же | один раз |
| DNS A `livekit` / `onlyoffice` / `grafana` / `api` / `cdn`.`linnex.io` | то же | один раз |
| DNS A `humanitec.ru` + те же субдомены → `31.192.111.33` | то же | один раз (legacy) |
| Ubuntu 22.04+ | BM `31.192.111.33` | один раз |
| SSH ключ для root (`pubkey` в `/root/.ssh/authorized_keys`) | локально | один раз; `harden-ssh.sh` отключает пароль |
| Whitelist IP `31.192.111.33` в Reg.ru API | Настройки → API | иначе DNS-01 и `setup-brand-dns` с master дадут ACCESS_DENIED |

## 1. Master + GPU (31.192.111.33)

```bash
ssh root@31.192.111.33
git clone https://github.com/<owner>/agent-lab.git /root/agent-lab-deploy && cd /root/agent-lab-deploy
bash deploy/scripts/bootstrap-master.sh
```

Если NVIDIA driver только что поставлен — скрипт выходит с кодом **10**. `reboot`, затем снова `bootstrap-master.sh`.

Скрипт: hostname=`master`, `harden-ssh.sh`, [`bootstrap-nvidia.sh`](scripts/bootstrap-nvidia.sh) (driver, toolkit, containerd drop-in), MicroK8s канал `MICROK8S_CHANNEL=1.35/stable`, аддоны `dns hostpath-storage ingress cert-manager`, попытка community `portainer` (не блокер, если hang), лейбл `accelerator=nvidia-gpu`, [`bootstrap-host-docker.sh`](scripts/bootstrap-host-docker.sh) (Docker Engine, не snap; сокет для `guest-runtime`). KUBECONFIG_B64 — [`kubeconfig-for-github-actions.sh`](scripts/kubeconfig-for-github-actions.sh).

**Не** запускать `bootstrap-gpu-worker.sh` и **не** `join-cluster.sh` — второй ноды нет.

NVIDIA k8s-device-plugin DaemonSet ставит Helm-чарт (`templates/50-gpu/nvidia-device-plugin.yaml`) на первом `make k8s-deploy`.

**Idempotent.** Повторный запуск: всё `[SKIP]`.

## 2. Wildcard TLS (DNS-01 через reg.ru)

С локальной машины (kubectl на новый кластер):

```bash
export REGRU_USERNAME='<логин reg.ru>'
export REGRU_PASSWORD='<API-пароль reg.ru>'
bash deploy/scripts/setup-wildcard-tls.sh
```

Скрипт:
- `git clone` `flant/cert-manager-webhook-regru` в `${TMPDIR:-/tmp}/cert-manager-webhook-regru`;
- `helm upgrade --install regru-webhook` (image `ghcr.io/flant/cluster-issuer-regru:1.2.0`);
- создаёт `ClusterIssuer letsencrypt-prod-dns01`;
- создаёт `Certificate platform-tls` для brand apex + wildcard в namespace `platform`;
- ждёт `Ready=True` (DNS-01 — до 10 минут на первом выпуске).

В CI скрипт вызывается перед `helm upgrade --install` (`.github/workflows/deploy.yml`).

**Idempotent.** При уже Ready Certificate — fast-path skip.

## 3. Сохранение kubeconfig в GitHub

```bash
gh secret set KUBECONFIG_B64 --body "$(bash deploy/scripts/kubeconfig-for-github-actions.sh)"
```

Скрипт подставляет `https://31.192.111.33:16443` вместо `127.0.0.1` из `microk8s config`. Полный kubeconfig в чат не печатать. Список секретов — [`README.md`](README.md).

## 4. Первый деплой

```bash
make k8s-secrets-sync
make k8s-deploy IMAGE_TAG=<immutable-sha>
```

Или через CI: workflow `Deploy`.

## 5. Полная проверка здоровья

```bash
make k8s-health
# до cutover DNS: CHECK_PUBLIC=0 make k8s-health
```

## 6. Бэкап и восстановление Postgres

```bash
make k8s-backup                              # → backups/dump-<ts>.sql.gz
make k8s-restore FILE=backups/dump-<ts>.sql.gz
```

## 7. Что НЕ нужно делать

- НЕ открывать `ufw allow 5432` или `ufw allow 6379`.
- НЕ запускать `docker compose` на ноде (Docker Engine нужен только как dockerd для `guest-runtime`, ставит `bootstrap-host-docker.sh`).
- НЕ копировать `init.sql` на хост — он в ConfigMap чарта.
- НЕ делать `kubectl apply -f` отдельных манифестов мимо чарта.
- НЕ держать `static-server` Deployment отдельно.
- НЕ редактировать ресурсы через `kubectl edit` — только PR в Helm-чарт + `helm upgrade`.
- НЕ ставить taint `dedicated=gpu:NoSchedule` на единственную ноду.
- НЕ трогать `ytai.tech` на `84.38.184.105`.
