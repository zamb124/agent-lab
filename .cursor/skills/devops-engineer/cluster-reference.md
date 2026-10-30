# Справочник кластера

Факты устройства прод-кластера для операций. Нормы — `.cursor/rules/infrastructure.mdc`.

## Нода и сеть

- Одна нода `master` `77.91.94.127` (лейблы `kubernetes.io/hostname=master`, `accelerator=nvidia-gpu`): Postgres, Redis, Loki, Tempo, Grafana, приложения, воркеры, LiveKit, Coturn, OnlyOffice, ingress, `provider_litserve`, NVIDIA device plugin, `guest-runtime` (Docker-слоты `code_agent` через hostPath `/var/run/docker.sock`).
- Taint `dedicated=gpu` и отдельная guest-нода не используются; executor фермы — `docker` (прод) или `inprocess` (тесты).
- Postgres — `postgres.platform.svc.cluster.local:5432` (StatefulSet, PVC 50Gi `microk8s-hostpath`, `postgres.maxConnections`/`sharedBuffers`); Redis — `redis.platform.svc.cluster.local:6379` (PVC 10Gi, AOF).
- DNS: `@` и `*` каждого apex (`linnex.io`, `humanitec.ru`) → `77.91.94.127`, плюс `livekit`, `onlyoffice`, `grafana`, `cdn`, `api`; скрипт — `deploy/scripts/setup-brand-dns.sh`; smoke — `deploy/docs/multi-brand-prod-smoke.md`.

## Чарт

- `templates/`: `01-platform-secrets.yaml`, `02-configmap-app-conf.yaml`, `10-postgres/`, `11-redis/`, `30-apps/`, `40-workers/`, `50-gpu/litserve.yaml`, `60-external/` (livekit, livekit-egress, coturn, onlyoffice), `61-centrifugo/` (Centrifugo v6 + `redis-realtime` noeviction), `70-observability/`, `80-ingress/`; источники ConfigMap — `files/`.
- `values.yaml`: `applications.<name>` (порт, реплики, command), `workers.<name>`, `litserve`, `livekit`, `coturn`, `onlyoffice`, `observability.*`, `ingress.*`, `platformSecrets`; общий env — `_helpers.tpl::agentlab.appEnv`.
- Frontend — initContainer `extract-static` копирует `/app/static/` в `emptyDir` `shared-static`; CRM отдаёт `/crm/ui/vendor/...` из `/app/node_modules` (three.js, 3d-force-graph).
- Browser — sidecar `chromium-cdp` (`zenika/alpine-chrome`, CDP `127.0.0.1:9222`), без Ingress, ClusterIP `http://browser:8009`.

## Ingress и TLS

- `ingress-nginx` + `cert-manager` (ClusterIssuer `letsencrypt-prod`, HTTP-01 для apex); wildcard `*.<apex>` — DNS-01 webhook в тот же Secret `platform-tls` (`deploy/cluster-setup.md`).
- Хосты каждого apex: apex + wildcard → `platform-services` (priority `10`) и `platform-frontend` (`-100`); `livekit.*` → livekit:7880, `onlyoffice.*` → onlyoffice:80, `grafana.*` → grafana:3000 (все `1000`); аннотации `proxy-body-size: 100m`, `proxy-read-timeout: 300s`.
- Grafana: `auth.proxy` (`GF_AUTH_PROXY_HEADER_NAME=X-Auth-User`); аннотация middleware — `<k8s-namespace>-grafana-forward-auth@kubernetescrd` (без префикса namespace роут не создаётся и трафик уходит на landing); второй Ingress `grafana-health` (`/api/health`, Exact, priority `1001`, без middleware).
- PWA-маршруты (`/manifest.json`, `/sw.js`, `/offline.html`, `/.well-known/*`) отдаёт frontend (`register_platform_pwa_routes`).

## GPU

- `provider-litserve`: `litserve.nodeName: master`, `nvidia.com/gpu: 1`, образ `ghcr.io/zamb124/agent-lab-gpu:<tag>` (`--set litserve.image=...`), PVC `litserve-model-cache` 50Gi, ENV `PROVIDER_LITSERVE__INFRA__BACKEND=flagllm`, `PROVIDER_LITSERVE__INFRA__ACCELERATOR=cuda`, `MODEL_ID`, `EMBEDDING_MODEL_ID`, `HF_TOKEN`; внутри кластера — `http://provider-litserve:8014/v1`, снаружи — `https://<apex>/litserve/*`.
- Причина отдельного образа: `torchaudio` (через `silero_vad`) не имеет cp314t wheels; базовый образ — `.github/workflows/build-base-gpu.yml`.
- Smoke: `kubectl exec -n platform deployment/provider-litserve -- nvidia-smi`, `curl -fsS https://linnex.io/litserve/health`.

## Observability

- Loki (StatefulSet, 100Gi, `files/loki.yaml`), Tempo (50Gi, `files/tempo.yaml`), Grafana (10Gi), Alloy (DaemonSet, `files/alloy.config`: `discovery.kubernetes role=pod`, метки `namespace`, `pod`, `container`, `service`, `node`; `level` — label, остальные поля — `| json`).
- OTLP — `http://alloy:4317` → Tempo; Derived Field `trace_id` → Tempo.
- Дашборды — `files/dashboards/` (ConfigMap `grafana-dashboards`, в том числе `11-crawl-indexing.json`); алерты — `files/grafana-alerts/` (error rate, service down, 5xx, TaskIQ failures, LLM errors, log contract violations, slow P99, DB latency).

## Деплой

- CI: job `build` (`docker build --target full` → GHCR `<sha>`), job `deploy` (`helm upgrade --install agent-lab ./deploy/helm/agent-lab --namespace platform --create-namespace --set image.tag=<sha>` + `--set-json platformSecrets=...`), затем `kubectl get pods -n platform`.
- Локально: `make k8s-lint`, `make k8s-template`, `make k8s-deploy IMAGE_TAG=<sha>`, `make k8s-status`, `make k8s-logs SVC=<svc>`, `make k8s-rollback`, `make k8s-uninstall` (PVC сохраняются).
- `KUBECONFIG_B64` — `deploy/scripts/kubeconfig-for-github-actions.sh` (сервер `https://77.91.94.127:16443`).

## Разовая настройка ноды

- `deploy/cluster-setup.md`: `bootstrap-master.sh` (NVIDIA, MicroK8s, аддоны `dns hostpath-storage ingress cert-manager`, лейбл GPU, Docker Engine через `bootstrap-host-docker.sh`, `harden-ssh.sh`), `bootstrap-nvidia.sh`.
- Whitelist Reg.ru API — `77.91.94.127`; DNS и TLS — `setup-brand-dns.sh`, `setup-wildcard-tls.sh`.
