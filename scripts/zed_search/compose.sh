#!/usr/bin/env bash
# Оркестратор zed-search Docker Compose-стека.
# Канон: Milvus + CBM + claude-context в Compose.
# Ollama: на macOS — host Metal GPU (OLLAMA_MODE=metal); docker-профиль — только Linux/CPU.
# Хост: Docker Desktop + IDE HTTP-клиенты (Zed/Cursor) + (metal) brew Ollama.
#
# usage:
#   bash scripts/zed_search/compose.sh up [--no-index]
#   bash scripts/zed_search/compose.sh down
#   bash scripts/zed_search/compose.sh status
#   bash scripts/zed_search/compose.sh logs [service]
#   bash scripts/zed_search/compose.sh reindex
#   bash scripts/zed_search/compose.sh update
#   bash scripts/zed_search/compose.sh wire
#   bash scripts/zed_search/compose.sh ensure-env

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOCKER_DIR="$SCRIPT_DIR/docker"
COMPOSE_FILE="$DOCKER_DIR/docker-compose.yml"
ENV_FILE="$DOCKER_DIR/.env"
ENV_EXAMPLE="$DOCKER_DIR/.env.example"
MCP_HTTP="$SCRIPT_DIR/mcp_http.py"

CBM_URL_DEFAULT="http://127.0.0.1:9751/mcp"
CLAUDE_URL_DEFAULT="http://127.0.0.1:9752/mcp"
ZED_SETTINGS="${ZED_SETTINGS:-$HOME/.config/zed/settings.json}"
CURSOR_MCP="${CURSOR_MCP:-$HOME/.cursor/mcp.json}"

log() { echo "[zed-search] $*"; }
die() { echo "[zed-search] ERROR: $*" >&2; exit 1; }

require_docker() {
  command -v docker >/dev/null 2>&1 || die "docker не найден — установи Docker Desktop"
  docker info >/dev/null 2>&1 || die "Docker daemon не отвечает — запусти Docker Desktop"
  docker compose version >/dev/null 2>&1 || die "docker compose недоступен"
}

# metal (Darwin default) | docker
resolve_ollama_mode() {
  if [ -n "${OLLAMA_MODE:-}" ]; then
    echo "$OLLAMA_MODE"
    return
  fi
  case "$(uname -s)" in
    Darwin) echo metal ;;
    *) echo docker ;;
  esac
}

env_set_key() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >>"$ENV_FILE"
  fi
  rm -f "${ENV_FILE}.bak"
}

compose() {
  local mode
  mode="$(resolve_ollama_mode)"
  if [ "$mode" = "docker" ]; then
    COMPOSE_PROFILES=docker-ollama docker compose --project-directory "$DOCKER_DIR" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
  else
    # Явно пустой profile: иначе унаследованный COMPOSE_PROFILES поднимет docker-ollama.
    COMPOSE_PROFILES= docker compose --project-directory "$DOCKER_DIR" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
  fi
}

load_env() {
  [ -f "$ENV_FILE" ] || die "нет $ENV_FILE — сначала: bash scripts/zed_search/compose.sh ensure-env"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  : "${REPO_ROOT:?REPO_ROOT required in .env}"
  : "${MCP_API_KEY:?MCP_API_KEY required in .env}"
}

cmd_ensure_env() {
  mkdir -p "$DOCKER_DIR"
  if [ ! -f "$ENV_FILE" ]; then
    [ -f "$ENV_EXAMPLE" ] || die "нет $ENV_EXAMPLE"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    log "создан $ENV_FILE из .env.example"
  fi

  local key repo minio_user minio_pass
  key="$(grep -E '^MCP_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  repo="$(grep -E '^REPO_ROOT=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  minio_user="$(grep -E '^MINIO_ROOT_USER=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  minio_pass="$(grep -E '^MINIO_ROOT_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"

  if [ -z "$repo" ] || [ "$repo" = "/Users/you/power/agent-lab" ]; then
    if grep -q '^REPO_ROOT=' "$ENV_FILE"; then
      sed -i.bak "s|^REPO_ROOT=.*|REPO_ROOT=$REPO_ROOT|" "$ENV_FILE"
    else
      echo "REPO_ROOT=$REPO_ROOT" >>"$ENV_FILE"
    fi
    rm -f "${ENV_FILE}.bak"
    log "REPO_ROOT=$REPO_ROOT"
  fi

  if [ -z "$key" ] || [ "$key" = "replace-me" ]; then
    key="$(openssl rand -hex 24)"
    if grep -q '^MCP_API_KEY=' "$ENV_FILE"; then
      sed -i.bak "s|^MCP_API_KEY=.*|MCP_API_KEY=$key|" "$ENV_FILE"
    else
      echo "MCP_API_KEY=$key" >>"$ENV_FILE"
    fi
    rm -f "${ENV_FILE}.bak"
    log "сгенерирован MCP_API_KEY"
  fi

  if [ -z "$minio_user" ]; then
    echo "MINIO_ROOT_USER=zedsearch" >>"$ENV_FILE"
  fi
  if [ -z "$minio_pass" ] || [ "$minio_pass" = "zedsearch-change-me" ]; then
    minio_pass="$(openssl rand -hex 16)"
    if grep -q '^MINIO_ROOT_PASSWORD=' "$ENV_FILE"; then
      sed -i.bak "s|^MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=$minio_pass|" "$ENV_FILE"
    else
      echo "MINIO_ROOT_PASSWORD=$minio_pass" >>"$ENV_FILE"
    fi
    rm -f "${ENV_FILE}.bak"
    log "сгенерирован MINIO_ROOT_PASSWORD"
  fi

  # Ollama: на Darwin дефолт Metal (host GPU); иначе docker.
  local ollama_mode ollama_host batch
  ollama_mode="$(grep -E '^OLLAMA_MODE=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  if [ -z "$ollama_mode" ]; then
    case "$(uname -s)" in
      Darwin) ollama_mode=metal ;;
      *) ollama_mode=docker ;;
    esac
    env_set_key OLLAMA_MODE "$ollama_mode"
    log "OLLAMA_MODE=$ollama_mode"
  fi
  if [ "$ollama_mode" = "metal" ]; then
    ollama_host="http://host.docker.internal:11434"
    batch=8
  else
    ollama_host="http://ollama:11434"
    batch=2
  fi
  env_set_key OLLAMA_HOST "$ollama_host"
  if ! grep -q '^EMBEDDING_BATCH_SIZE=' "$ENV_FILE"; then
    env_set_key EMBEDDING_BATCH_SIZE "$batch"
  elif [ "$ollama_mode" = "metal" ]; then
    # Поднять дефолтный batch=2 с docker-эпохи до Metal-friendly.
    cur_batch="$(grep -E '^EMBEDDING_BATCH_SIZE=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
    if [ "$cur_batch" = "2" ]; then
      env_set_key EMBEDDING_BATCH_SIZE "$batch"
    fi
  fi

  chmod 600 "$ENV_FILE" 2>/dev/null || true
  log "env готов: $ENV_FILE (OLLAMA_MODE=$ollama_mode OLLAMA_HOST=$ollama_host)"
}

# Host Ollama с Apple Metal (не Linux-контейнер — там на Mac только CPU).
ensure_host_ollama() {
  local model="${OLLAMA_MODEL:-nomic-embed-text}"
  if ! command -v ollama >/dev/null 2>&1; then
    [ "$(uname -s)" = "Darwin" ] || die "ollama не найден — установи Ollama или выставь OLLAMA_MODE=docker"
    command -v brew >/dev/null 2>&1 || die "Homebrew не найден — установи brew или выставь OLLAMA_MODE=docker"
    log "установка host Ollama через Homebrew (Metal GPU)..."
    brew install ollama
  fi

  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx 'zed-search-ollama'; then
    log "останавливаю docker ollama (переход на Metal host)..."
    docker stop zed-search-ollama 2>/dev/null || true
    docker rm zed-search-ollama 2>/dev/null || true
  fi
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx 'zed-search-ollama-init'; then
    docker rm -f zed-search-ollama-init 2>/dev/null || true
  fi

  if ! curl -sf --connect-timeout 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    log "запуск host Ollama (Metal)..."
    if command -v brew >/dev/null 2>&1; then
      brew services start ollama 2>/dev/null || true
    fi
    if ! curl -sf --connect-timeout 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      nohup ollama serve >/tmp/zed-search-ollama-host.log 2>&1 &
    fi
    local i=0
    while [ "$i" -lt 45 ]; do
      if curl -sf --connect-timeout 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        break
      fi
      i=$((i + 1))
      sleep 2
    done
  fi
  curl -sf --connect-timeout 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 \
    || die "host Ollama не отвечает на :11434 — brew services start ollama"

  if ! curl -sf http://127.0.0.1:11434/api/tags | grep -q "$model"; then
    log "pull $model на host Ollama..."
    ollama pull "$model"
  fi
  log "host Ollama OK (Metal) model=$model"
}

# Освободить порты 9751/9752 (+11434 только в docker-режиме) под Compose.
free_host_ports() {
  log "освобождение портов под Compose..."

  local watch_plist="${HOME}/Library/LaunchAgents/com.claude-context-watch.plist"
  local cbm_plist="${HOME}/Library/LaunchAgents/com.codebase-memory-mcp.daemon.plist"
  local old_milvus="${HOME}/.local/share/claude-context-milvus/docker-compose.yml"
  local mode
  mode="$(resolve_ollama_mode)"

  if [ -f "$watch_plist" ]; then
    launchctl unload "$watch_plist" 2>/dev/null || true
    rm -f "$watch_plist"
  fi
  if [ -f "$cbm_plist" ]; then
    launchctl unload "$cbm_plist" 2>/dev/null || true
    rm -f "$cbm_plist"
  fi

  if [ "$mode" = "docker" ]; then
    if command -v brew >/dev/null 2>&1; then
      brew services stop ollama 2>/dev/null || true
    fi
    if lsof -nP -iTCP:11434 -sTCP:LISTEN >/dev/null 2>&1; then
      if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'zed-search-ollama'; then
        pkill -f '/[o]llama serve' 2>/dev/null || true
        pkill -x ollama 2>/dev/null || true
        sleep 1
      fi
    fi
  fi

  if [ -f "$old_milvus" ]; then
    docker compose -f "$old_milvus" down 2>/dev/null || true
  fi
  docker stop milvus-standalone milvus-minio milvus-etcd 2>/dev/null || true
  docker rm milvus-standalone milvus-minio milvus-etcd 2>/dev/null || true

  pkill -f 'mcp-proxy --host 127.0.0.1 --port 9751' 2>/dev/null || true
  pkill -f 'mcp-proxy --host 127.0.0.1 --port 9752' 2>/dev/null || true
  pkill -f 'npm exec @zilliz/claude-context-mcp' 2>/dev/null || true
  pkill -f 'node_modules/.bin/claude-context-mcp' 2>/dev/null || true
  pkill -f "$HOME/.local/bin/codebase-memory-mcp$" 2>/dev/null || true

  sleep 1
}

wait_http() {
  local url="$1" name="$2" tries="${3:-60}"
  local i=0
  while [ "$i" -lt "$tries" ]; do
    if curl -fsS --connect-timeout 2 "$url" >/dev/null 2>&1; then
      log "  $name OK ($url)"
      return 0
    fi
    i=$((i + 1))
    sleep 2
  done
  die "$name не поднялся: $url"
}

wait_stack() {
  log "ожидание health..."
  wait_http "http://127.0.0.1:11434/api/tags" "Ollama" 90
  wait_http "http://127.0.0.1:9751/ping" "CBM proxy" 90
  wait_http "http://127.0.0.1:9752/ping" "claude-context proxy" 120
  # milvus healthz внутри контейнера; с хоста — порт 19530
  local i=0
  while [ "$i" -lt 60 ]; do
    if docker inspect --format '{{.State.Health.Status}}' zed-search-milvus 2>/dev/null | grep -qx healthy; then
      log "  Milvus OK"
      return 0
    fi
    i=$((i + 1))
    sleep 3
  done
  die "Milvus не healthy"
}

wire_clients() {
  load_env
  local cbm_url claude_url
  cbm_url="${CBM_URL:-$CBM_URL_DEFAULT}"
  claude_url="${CLAUDE_URL:-$CLAUDE_URL_DEFAULT}"

  python3 - "$ZED_SETTINGS" "$cbm_url" "$claude_url" "$MCP_API_KEY" <<'PY'
import datetime, json, pathlib, re, shutil, sys

path = pathlib.Path(sys.argv[1])
cbm_url, claude_url, api_key = sys.argv[2], sys.argv[3], sys.argv[4]
if not path.exists():
    print(f"  Zed settings не найден ({path}) — пропуск")
    raise SystemExit(0)

raw = path.read_text(encoding="utf-8")

def block(name: str, url: str) -> str:
    return (
        f'    "{name}": {{\n'
        f'      "enabled": true,\n'
        f'      "url": {json.dumps(url)},\n'
        f'      "headers": {{\n'
        f'        "X-API-Key": {json.dumps(api_key)}\n'
        f'      }}\n'
        f'    }}'
    )

def find_object_span(src: str, key: str) -> tuple[int, int] | None:
    m = re.search(rf'[ \t]*"{re.escape(key)}"\s*:\s*\{{', src)
    if not m:
        return None
    start = m.start()
    i = src.find("{", m.start())
    depth = 0
    in_str = False
    while i < len(src):
        ch = src[i]
        if in_str:
            if ch == "\\" and i + 1 < len(src):
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    return None

def replace_or_insert(raw: str, name: str, url: str) -> str:
    b = block(name, url)
    span = find_object_span(raw, name)
    if span is not None:
        a, c = span
        return raw[:a] + b + raw[c:]
    marker = '  "context_servers": {\n'
    if marker not in raw:
        print(f"  context_servers не найден — пропуск {name}", file=sys.stderr)
        return raw
    return raw.replace(marker, marker + b + ",\n", 1)

new = replace_or_insert(raw, "codebase-memory-mcp", cbm_url)
new = replace_or_insert(new, "claude-context", claude_url)

def strip_jsonc(s: str) -> str:
    out: list[str] = []
    i = 0
    n = len(s)
    in_str = False
    while i < n:
        c = s[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            i += 2
            while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)

cleaned = re.sub(r",(\s*[}\]])", r"\1", strip_jsonc(new))
json.loads(cleaned)
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(path, f"{path}.bak.zed-search-compose-{ts}")
path.write_text(new, encoding="utf-8")
print(f"  Zed: codebase-memory-mcp + claude-context → HTTP + X-API-Key")
PY

  python3 - "$CURSOR_MCP" "$cbm_url" "$claude_url" "$MCP_API_KEY" <<'PY'
import json, pathlib, sys

path = pathlib.Path(sys.argv[1])
cbm_url, claude_url, api_key = sys.argv[2], sys.argv[3], sys.argv[4]
data: dict = {}
if path.exists() and path.stat().st_size > 0:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
servers = data.setdefault("mcpServers", {})
headers = {"X-API-Key": api_key}
servers["codebase-memory-mcp"] = {"url": cbm_url, "headers": headers}
servers["claude-context"] = {"url": claude_url, "headers": headers}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("  Cursor: mcpServers codebase-memory-mcp + claude-context → HTTP + X-API-Key")
PY

  log "перезапусти Zed/Cursor — клиенты должны ходить только по HTTP URL (без stdio spawn)."
}

cmd_reindex() {
  load_env
  require_docker
  local repo="$REPO_ROOT"
  log "reindex claude-context (force=true)..."
  python3 "$MCP_HTTP" --url "${CLAUDE_URL:-$CLAUDE_URL_DEFAULT}" --api-key "$MCP_API_KEY" --timeout 900 \
    call index_codebase "{\"path\":\"$repo\",\"force\":true}" --wait-status --status-path "$repo" --max-wait-s 3600
  log "reindex CBM..."
  python3 "$MCP_HTTP" --url "${CBM_URL:-$CBM_URL_DEFAULT}" --api-key "$MCP_API_KEY" --timeout 900 \
    call index_repository "{\"repo_path\":\"$repo\"}"
  log "reindex done"
}

cmd_up() {
  local do_index=1
  if [ "${1:-}" = "--no-index" ]; then
    do_index=0
  fi
  require_docker
  cmd_ensure_env
  load_env
  local mode
  mode="$(resolve_ollama_mode)"
  free_host_ports
  if [ "$mode" = "metal" ]; then
    ensure_host_ollama
  fi
  log "docker compose up --build (OLLAMA_MODE=$mode)..."
  compose up --build -d --remove-orphans
  wait_stack
  wire_clients
  if [ "$do_index" -eq 1 ]; then
    cmd_reindex || log "WARN: primary index не завершился чисто — проверь make zed-search-logs / reindex"
  fi
  log "стек готов. Проверка: make zed-search-check"
}

cmd_down() {
  require_docker
  if [ -f "$ENV_FILE" ]; then
    # Без -v: named volumes (cbm_cache, claude_context_data, milvus, ollama, …) сохраняются.
    compose down
  else
    docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
  fi
  log "compose down (volumes сохранены; wipe только через docker compose down -v)"
}

cmd_status() {
  require_docker
  if [ -f "$ENV_FILE" ]; then
    load_env
    compose ps
    echo "OLLAMA_MODE=${OLLAMA_MODE:-$(resolve_ollama_mode)} OLLAMA_HOST=${OLLAMA_HOST:-}"
  fi
  echo "Ollama:  $(curl -sf http://127.0.0.1:11434/api/tags >/dev/null && echo OK || echo FAIL)"
  if command -v ollama >/dev/null 2>&1; then
    echo "Ollama-ps:"
    ollama ps 2>/dev/null || true
  fi
  echo "CBM:     $(curl -sf http://127.0.0.1:9751/ping >/dev/null && echo OK || echo FAIL)"
  echo "Claude:  $(curl -sf http://127.0.0.1:9752/ping >/dev/null && echo OK || echo FAIL)"
  echo "Milvus:  $(docker inspect --format '{{.State.Health.Status}}' zed-search-milvus 2>/dev/null || echo missing)"
}

cmd_logs() {
  require_docker
  load_env
  if [ -n "${1:-}" ]; then
    compose logs -f "$1"
  else
    compose logs -f
  fi
}

cmd_update() {
  require_docker
  cmd_ensure_env
  load_env
  local mode
  mode="$(resolve_ollama_mode)"
  if [ "$mode" = "metal" ]; then
    ensure_host_ollama
    log "pull инфраструктуры (milvus/etcd/minio; Ollama=Metal host)..."
    compose pull etcd minio milvus || true
  else
    log "pull инфраструктуры (milvus/ollama/etcd/minio)..."
    compose pull etcd minio milvus ollama ollama-init || true
  fi
  log "пересборка MCP-образов (latest npm/CBM, без кеша npm-слоёв)..."
  # --pull базовых FROM; без cache для proxy/build слоёв с npm install @latest
  compose build --pull --no-cache cbm claude-context
  compose up -d --no-deps cbm claude-context
  wait_http "http://127.0.0.1:9751/ping" "CBM proxy" 60
  wait_http "http://127.0.0.1:9752/ping" "claude-context proxy" 60
  wire_clients
  log "update done (версии пакетов зафиксированы в слоях нового образа)"
}

case "${1:-}" in
  up)          shift; cmd_up "$@" ;;
  down)        cmd_down ;;
  status)      cmd_status ;;
  logs)        shift; cmd_logs "$@" ;;
  reindex)     cmd_reindex ;;
  update)      cmd_update ;;
  wire)        cmd_ensure_env; wire_clients ;;
  ensure-env)  cmd_ensure_env ;;
  *)
    echo "usage: compose.sh {up|down|status|logs|reindex|update|wire|ensure-env} [--no-index]"
    exit 1
    ;;
esac
