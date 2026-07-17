#!/usr/bin/env bash
# Health-check Compose-стека zed-search (Ollama + Milvus + CBM + claude-context).
#
# exit 0 — стек жив (возможны WARN)
# exit 1 — семантика и/или HTTP MCP недоступны
#
# Вызов: make zed-search-check

set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/docker/.env"
MCP_HTTP="$SCRIPT_DIR/mcp_http.py"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

OLLAMA_HOST_URL="${OLLAMA_HOST_URL:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-nomic-embed-text}"
OLLAMA_MODE="${OLLAMA_MODE:-}"
CBM_URL="${CBM_URL:-http://127.0.0.1:9751/mcp}"
CLAUDE_URL="${CLAUDE_URL:-http://127.0.0.1:9752/mcp}"
INDEX_STALE_HOURS="${INDEX_STALE_HOURS:-48}"
CLAUDE_INDEX_MIN_COVERAGE_PCT="${CLAUDE_INDEX_MIN_COVERAGE_PCT:-70}"

OK_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
REPORT=()

check() {
  local name="$1" status="$2" detail="$3"
  if [ "$status" = "OK" ]; then
    OK_COUNT=$((OK_COUNT + 1))
    REPORT+=("  OK  $name — $detail")
  elif [ "$status" = "WARN" ]; then
    WARN_COUNT=$((WARN_COUNT + 1))
    REPORT+=("  WARN $name — $detail")
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    REPORT+=("  FAIL $name — $detail")
  fi
}

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  OLLAMA_MODEL="${OLLAMA_MODEL:-nomic-embed-text}"
  REPO_ROOT="${REPO_ROOT:-$REPO_ROOT}"
fi

if [ -z "${OLLAMA_MODE:-}" ]; then
  case "$(uname -s)" in
    Darwin) OLLAMA_MODE=metal ;;
    *) OLLAMA_MODE=docker ;;
  esac
fi

MCP_API_KEY="${MCP_API_KEY:-}"

expected_claude_index_files() {
  REPO_ROOT="$REPO_ROOT" python3 - <<'PY'
import fnmatch
import os
import subprocess
from pathlib import Path

root = Path(os.environ["REPO_ROOT"])
supported_extensions = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".java", ".cpp", ".c", ".h", ".hpp",
    ".cs", ".go", ".rs", ".php", ".rb", ".swift", ".kt", ".scala", ".m", ".mm",
    ".dart", ".sol", ".md", ".markdown", ".ipynb",
}
ignore_names = {
    ".git", ".svn", ".hg", "node_modules", "dist", "build", "out", "target",
    "coverage", ".nyc_output", ".vscode", ".idea", ".cache", "__pycache__",
    ".pytest_cache", "logs", "tmp", "temp",
}
ignore_patterns = [
    ".search-comparison/**",
    ".cursor/debug-*.log",
    "documentation-dist/**",
    "artifacts/**",
    "test-results/**",
    "lightpanda/**",
    "reports/**",
    "*.map",
    "*.log",
    ".env",
    ".env.*",
    "*.local",
    "*.min.js",
    "*.min.css",
    "*.min.map",
    "*.bundle.js",
    "*.bundle.css",
    "*.chunk.js",
    "*.vendor.js",
    "*.polyfills.js",
    "*.runtime.js",
]


def ignored(relative_path: str, *, is_dir: bool) -> bool:
    normalized = relative_path.replace(os.sep, "/")
    name = normalized.rsplit("/", 1)[-1]
    if name in ignore_names:
        return True
    if is_dir and normalized in ignore_names:
        return True
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
    return False


try:
    candidate_files = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).splitlines()
except (OSError, subprocess.SubprocessError):
    candidate_files = []
    for current_root, dirs, files in os.walk(root):
        base = Path(current_root)
        rel_base = base.relative_to(root)
        kept_dirs = []
        for dirname in dirs:
            rel_dir = str(rel_base / dirname) if str(rel_base) != "." else dirname
            if not ignored(rel_dir, is_dir=True):
                kept_dirs.append(dirname)
        dirs[:] = kept_dirs
        for filename in files:
            rel_file = str(rel_base / filename) if str(rel_base) != "." else filename
            candidate_files.append(rel_file)

count = 0
for rel_file in candidate_files:
    if ignored(rel_file, is_dir=False):
        continue
    if Path(rel_file).suffix in supported_extensions:
        count += 1
print(count)
PY
}

# 1. Docker
if ! command -v docker >/dev/null 2>&1; then
  check "Docker" "FAIL" "docker не найден. Починка: установи Docker Desktop"
else
  if docker info >/dev/null 2>&1; then
    check "Docker" "OK" "daemon отвечает"
  else
    check "Docker" "FAIL" "daemon не отвечает. Починка: запусти Docker Desktop"
  fi
fi

# 2. Compose-контейнеры (ollama — только OLLAMA_MODE=docker; metal = host brew)
COMPOSE_CONTAINERS=(zed-search-milvus zed-search-cbm zed-search-claude-context)
if [ "$OLLAMA_MODE" = "docker" ]; then
  COMPOSE_CONTAINERS=(zed-search-ollama "${COMPOSE_CONTAINERS[@]}")
fi
for name in "${COMPOSE_CONTAINERS[@]}"; do
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name"; then
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "$name" 2>/dev/null || echo unknown)"
    if [ "$health" = "healthy" ] || [ "$health" = "running" ]; then
      check "$name" "OK" "health=$health"
    else
      check "$name" "FAIL" "health=$health. Починка: make zed-search-logs"
    fi
  else
    check "$name" "FAIL" "не запущен. Починка: make zed-search"
  fi
done

if [ "$OLLAMA_MODE" = "metal" ]; then
  check "Ollama-runtime" "OK" "OLLAMA_MODE=metal (host Apple Metal GPU)"
elif [ "$OLLAMA_MODE" = "docker" ]; then
  check "Ollama-runtime" "OK" "OLLAMA_MODE=docker"
else
  check "Ollama-runtime" "WARN" "неизвестный OLLAMA_MODE=$OLLAMA_MODE"
fi

# 3. Ollama API + модель
if curl -sf "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1; then
  if curl -sf "$OLLAMA_HOST_URL/api/tags" | grep -q "$OLLAMA_MODEL"; then
    check "Ollama-model" "OK" "$OLLAMA_MODEL доступна"
  else
    check "Ollama-model" "FAIL" "модель $OLLAMA_MODEL не найдена. Починка: make zed-search"
  fi
else
  check "Ollama-model" "FAIL" "не отвечает на $OLLAMA_HOST_URL"
fi

# 4. HTTP ping прокси
if curl -sf http://127.0.0.1:9751/ping >/dev/null 2>&1; then
  check "CBM-HTTP" "OK" "http://127.0.0.1:9751/ping"
else
  check "CBM-HTTP" "FAIL" "ping fail. Починка: make zed-search"
fi
if curl -sf http://127.0.0.1:9752/ping >/dev/null 2>&1; then
  check "Claude-HTTP" "OK" "http://127.0.0.1:9752/ping"
else
  check "Claude-HTTP" "FAIL" "ping fail. Починка: make zed-search"
fi

# 5. MCP smoke (нужен API key)
if [ -z "$MCP_API_KEY" ]; then
  check "MCP-auth" "FAIL" "нет MCP_API_KEY в $ENV_FILE. Починка: make zed-search"
elif [ ! -f "$MCP_HTTP" ]; then
  check "MCP-auth" "FAIL" "нет $MCP_HTTP"
else
  check "MCP-auth" "OK" "ключ загружен"
  if python3 "$MCP_HTTP" --url "$CBM_URL" --api-key "$MCP_API_KEY" --timeout 30 \
      call list_projects '{}' >/tmp/zed-search-cbm-smoke.txt 2>/tmp/zed-search-cbm-smoke.err; then
    check "CBM-tools" "OK" "list_projects ответил"
  else
    check "CBM-tools" "FAIL" "list_projects failed. $(head -c 200 /tmp/zed-search-cbm-smoke.err 2>/dev/null || true)"
  fi
  # get_indexing_status при пустом индексе часто isError=true — это WARN, не FAIL
  set +e
  python3 "$MCP_HTTP" --url "$CLAUDE_URL" --api-key "$MCP_API_KEY" --timeout 60 \
      call get_indexing_status "{\"path\":\"$REPO_ROOT\"}" >/tmp/zed-search-claude-smoke.txt 2>/tmp/zed-search-claude-smoke.err
  claude_rc=$?
  set -e
  status_txt="$(tr '\n' ' ' </tmp/zed-search-claude-smoke.txt 2>/dev/null | head -c 240)"
  err_txt="$(tr '\n' ' ' </tmp/zed-search-claude-smoke.err 2>/dev/null | head -c 200)"
  combined="${status_txt} ${err_txt}"
  low="$(echo "$combined" | tr '[:upper:]' '[:lower:]')"
  if echo "$low" | grep -Eq 'completed|ready|fully indexed|indexed files|[0-9]+ chunks'; then
    check "Claude-index" "OK" "$status_txt"
  elif echo "$low" | grep -Eq 'being indexed|currently being indexed|progress:'; then
    check "Claude-index" "WARN" "индексация идёт. Дождись завершения или make zed-search-reindex"
  elif echo "$low" | grep -Eq 'not indexed|no index|empty|is not indexed'; then
    check "Claude-index" "WARN" "индекс пуст/не готов. Починка: make zed-search-reindex"
  elif [ "$claude_rc" -eq 0 ]; then
    check "Claude-index" "WARN" "статус: $status_txt"
  else
    check "Claude-index" "FAIL" "get_indexing_status failed. $err_txt"
  fi

  indexed_files="$(printf '%s' "$combined" | python3 -c 'import re, sys; text = sys.stdin.read(); match = re.search(r"Statistics:\s*([0-9]+)\s+files", text) or re.search(r"([0-9]+)\s+files", text); print(match.group(1) if match else "")')"
  expected_files="$(expected_claude_index_files 2>/dev/null || true)"
  if [ -n "$indexed_files" ] && [ -n "$expected_files" ] && [ "$expected_files" -gt 0 ]; then
    coverage_pct=$((indexed_files * 100 / expected_files))
    if [ "$coverage_pct" -lt "$CLAUDE_INDEX_MIN_COVERAGE_PCT" ]; then
      check "Claude-index-coverage" "WARN" "индекс покрывает ${indexed_files}/${expected_files} файлов (${coverage_pct}%). Починка: make zed-search-reindex"
    else
      check "Claude-index-coverage" "OK" "покрытие ${indexed_files}/${expected_files} файлов (${coverage_pct}%)"
    fi
  else
    check "Claude-index-coverage" "WARN" "не удалось оценить покрытие индекса"
  fi
fi

# 6. Host MCP вне Compose — конфликт с :9751/:9752 (FAIL, не WARN)
host_claude="$(pgrep -f 'npm exec @zilliz/claude-context-mcp|node_modules/.bin/claude-context-mcp' 2>/dev/null | wc -l | tr -d ' ' || true)"
host_claude="${host_claude:-0}"
host_cbm="$(ps -axo command= 2>/dev/null | awk '
  /codebase-memory-mcp/ && $0 !~ /mcp-proxy/ && $0 !~ /cli / && $0 !~ /docker/ { c++ }
  END { print c+0 }
' || true)"
host_cbm="${host_cbm:-0}"
if [ "$host_claude" -ne 0 ]; then
  check "Host-claude" "FAIL" "на хосте $host_claude процессов claude-context вне Compose. Починка: make zed-search + перезапуск IDE"
fi
if [ "$host_cbm" -ne 0 ]; then
  check "Host-CBM" "FAIL" "на хосте $host_cbm процессов CBM вне Compose. Починка: make zed-search"
fi
if [ -f "$HOME/Library/LaunchAgents/com.claude-context-watch.plist" ] || \
   launchctl list 2>/dev/null | grep -q 'com.claude-context-watch'; then
  check "Host-launchd-watch" "FAIL" "launchd watcher конфликтует со стеком. Починка: make zed-search"
fi
if [ -f "$HOME/Library/LaunchAgents/com.codebase-memory-mcp.daemon.plist" ] || \
   launchctl list 2>/dev/null | grep -q 'com.codebase-memory-mcp.daemon'; then
  check "Host-launchd-cbm" "FAIL" "launchd CBM daemon конфликтует с :9751. Починка: make zed-search"
fi

echo "================================================================"
echo "[zed-search-check] Health Compose-стека (claude-context + CBM)"
echo "================================================================"
printf '%s\n' "${REPORT[@]}"
echo ""
if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "[zed-search-check] FAIL: $FAIL_COUNT, WARN: $WARN_COUNT, OK: $OK_COUNT"
  echo "[zed-search-check] Семантический/HTTP поиск НЕ готов. Запусти: make zed-search"
  exit 1
fi
if [ "$WARN_COUNT" -gt 0 ]; then
  echo "[zed-search-check] WARN: $WARN_COUNT, OK: $OK_COUNT — стек жив, есть риски."
  exit 0
fi
echo "[zed-search-check] OK ($OK_COUNT). Compose-стек готов."
exit 0
