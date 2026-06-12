#!/usr/bin/env bash
# Строит строку аргументов `--set <path>.nodeName=<value>` для `helm upgrade`.
#
# Читает ENV-переменные, которые выставляет шаг Helm upgrade --install в deploy.yml:
#   APPS_NODE      — нода для всех приложений (applications.*.nodeName)
#   WORKERS_NODE   — нода для всех воркеров (workers.*.nodeName)
#   DATA_NODE      — нода для StatefulSets (postgres/redis/loki/tempo/grafana)
#   PUBLIC_NODE    — нода для hostNetwork-сервисов (livekit/livekitEgress/coturn/onlyoffice)
#   LITSERVE_NODE  — нода для litserve
#   SERVICE_OVERRIDES — CSV точечных override, например: flows=gpu-worker,redis=master,rag=auto
#
# Значение "unchanged" или пустая строка → ключ не добавляется (берётся из values.yaml).
#
# Вывод: строка из токенов "--set foo.nodeName=bar --set baz.nodeName=qux" (или пусто).
# Использование в shell:
#   NODE_SETS=$(bash build_helm_node_sets.sh)
#   helm upgrade ... $NODE_SETS ...

set -euo pipefail

APPS_NODE="${APPS_NODE:-}"
WORKERS_NODE="${WORKERS_NODE:-}"
DATA_NODE="${DATA_NODE:-}"
PUBLIC_NODE="${PUBLIC_NODE:-}"
LITSERVE_NODE="${LITSERVE_NODE:-}"
SERVICE_OVERRIDES="${SERVICE_OVERRIDES:-}"

SETS=()

# ---------- helper ----------
add_set() {
  local path="$1"
  local value="$2"
  if [ -n "$value" ] && [ "$value" != "unchanged" ]; then
    SETS+=("--set" "${path}.nodeName=${value}")
  fi
}

# ---------- apps ----------
APPS=(flows frontend crm rag sync scheduler-api office voice browser search capability-gateway code-runner-python code-runner-node code-runner-go code-runner-csharp)
for app in "${APPS[@]}"; do
  add_set "applications.${app}" "$APPS_NODE"
done

# ---------- workers ----------
WORKERS=(flows-worker scheduler rag-worker sync-worker crm-worker idle-worker search-worker)
for w in "${WORKERS[@]}"; do
  add_set "workers.${w}" "$WORKERS_NODE"
done

# ---------- data (StatefulSets) ----------
DATA_SERVICES=(postgres redis)
for svc in "${DATA_SERVICES[@]}"; do
  add_set "$svc" "$DATA_NODE"
done
OBSERVABILITY=(loki tempo grafana)
for obs in "${OBSERVABILITY[@]}"; do
  add_set "observability.${obs}" "$DATA_NODE"
done

# ---------- public (hostNetwork) ----------
PUBLIC_SERVICES=(livekit livekitEgress coturn onlyoffice)
for svc in "${PUBLIC_SERVICES[@]}"; do
  add_set "$svc" "$PUBLIC_NODE"
done

# ---------- litserve ----------
add_set "litserve" "$LITSERVE_NODE"

# ---------- service_overrides (CSV: name=node,...) ----------
# name → Helm path lookup через case (bash 3 совместимо).
svc_to_helm_path() {
  case "$1" in
    flows)           echo "applications.flows" ;;
    frontend)        echo "applications.frontend" ;;
    crm)             echo "applications.crm" ;;
    rag)             echo "applications.rag" ;;
    sync)            echo "applications.sync" ;;
    scheduler-api)   echo "applications.scheduler-api" ;;
    office)          echo "applications.office" ;;
    voice)           echo "applications.voice" ;;
    browser)         echo "applications.browser" ;;
    search)          echo "applications.search" ;;
    capability-gateway) echo "applications.capability-gateway" ;;
    code-runner-python) echo "applications.code-runner-python" ;;
    code-runner-node) echo "applications.code-runner-node" ;;
    code-runner-go) echo "applications.code-runner-go" ;;
    code-runner-csharp) echo "applications.code-runner-csharp" ;;
    flows-worker)    echo "workers.flows-worker" ;;
    scheduler)       echo "workers.scheduler" ;;
    rag-worker)      echo "workers.rag-worker" ;;
    sync-worker)     echo "workers.sync-worker" ;;
    crm-worker)      echo "workers.crm-worker" ;;
    idle-worker)     echo "workers.idle-worker" ;;
    search-worker)   echo "workers.search-worker" ;;
    postgres)        echo "postgres" ;;
    redis)           echo "redis" ;;
    loki)            echo "observability.loki" ;;
    tempo)           echo "observability.tempo" ;;
    grafana)         echo "observability.grafana" ;;
    livekit)         echo "livekit" ;;
    livekit-egress)  echo "livekitEgress" ;;
    coturn)          echo "coturn" ;;
    onlyoffice)      echo "onlyoffice" ;;
    litserve)        echo "litserve" ;;
    *)               echo "" ;;
  esac
}

if [ -n "$SERVICE_OVERRIDES" ]; then
  IFS=',' read -ra PAIRS <<< "$SERVICE_OVERRIDES"
  for pair in "${PAIRS[@]}"; do
    pair="${pair// /}"
    if [ -z "$pair" ]; then continue; fi
    name="${pair%%=*}"
    value="${pair#*=}"
    path=$(svc_to_helm_path "$name")
    if [ -z "$path" ]; then
      echo "::warning::service_overrides: неизвестный сервис '${name}' — пропускаю" >&2
      continue
    fi
    if [ -n "$value" ] && [ "$value" != "unchanged" ]; then
      # Убираем из SETS уже добавленный --set для этого пути (если был от category)
      NEW_SETS=()
      i=0
      while [ "$i" -lt "${#SETS[@]}" ]; do
        tok="${SETS[$i]}"
        next_i=$((i+1))
        next_tok="${SETS[$next_i]:-}"
        if [ "$tok" = "--set" ] && [ "${next_tok}" = "${path}.nodeName=${next_tok#*=}" ] && \
           echo "$next_tok" | grep -q "^${path}\\.nodeName="; then
          i=$((i+2))
          continue
        fi
        NEW_SETS+=("$tok")
        i=$((i+1))
      done
      SETS=("${NEW_SETS[@]+"${NEW_SETS[@]}"}")
      SETS+=("--set" "${path}.nodeName=${value}")
    fi
  done
fi

# ---------- output ----------
printf '%s\n' "${SETS[@]+"${SETS[@]}"}"
