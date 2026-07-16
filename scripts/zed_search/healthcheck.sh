#!/usr/bin/env bash
# Health-check для claude-context MCP (семантический поиск по коду).
#
# Проверяет всю цепочку: Ollama -> Milvus -> watcher -> индекс -> пакет MCP.
# Возвращает:
#   exit 0 + JSON-подобный отчёт в stdout — всё ОК
#   exit 1 + понятная диагностика — что именно сломано и как починить
#
# Вызывается из Make: make zed-search-check
# Может вызываться агентом Zed при старте (см. .cursor/rules/claude-context.mdc).

set -euo pipefail

# launchd запускает с минимальным PATH — добавляем Homebrew.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

OLLAMA_HOST_URL="${OLLAMA_HOST_URL:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-nomic-embed-text}"
MILVUS_CONTAINER="${MILVUS_CONTAINER:-milvus-standalone}"
WATCH_LABEL="${WATCH_LABEL:-com.claude-context-watch}"
CBM_BIN="${CBM_BIN:-$HOME/.local/bin/codebase-memory-mcp}"
CBM_SH="$(cd "$(dirname "$0")" 2>/dev/null && pwd)/cbm.sh"
CONTEXT_DIR="${HOME}/.context"
SNAPSHOT_FILE="$CONTEXT_DIR/mcp-codebase-snapshot.json"
MERKLE_DIR="$CONTEXT_DIR/merkle"

# Порог устаревания индекса (часы). Если snapshot старше — предупреждаем.
INDEX_STALE_HOURS="${INDEX_STALE_HOURS:-24}"

OK_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
REPORT=()

check() {
  local name="$1"
  local status="$2"
  local detail="$3"
  if [ "$status" = "OK" ]; then
    OK_COUNT=$((OK_COUNT + 1))
    REPORT+=("  ✅ $name — $detail")
  elif [ "$status" = "WARN" ]; then
    WARN_COUNT=$((WARN_COUNT + 1))
    REPORT+=("  ⚠️  $name — $detail")
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    REPORT+=("  ❌ $name — $detail")
  fi
}

# 1. Ollama
if curl -sf "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1; then
  if ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
    check "Ollama" "OK" "запущен, модель $OLLAMA_MODEL загружена"
  else
    check "Ollama" "FAIL" "запущен, но модель $OLLAMA_MODEL НЕ загружена. Починка: ollama pull $OLLAMA_MODEL"
  fi
else
  check "Ollama" "FAIL" "не отвечает на $OLLAMA_HOST_URL. Починка: brew services start ollama"
fi

# 2. Milvus (Docker)
if command -v docker >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$MILVUS_CONTAINER"; then
    health="$(docker inspect --format '{{.State.Health.Status}}' "$MILVUS_CONTAINER" 2>/dev/null || echo "unknown")"
    if [ "$health" = "healthy" ]; then
      check "Milvus" "OK" "контейнер $MILVUS_CONTAINER healthy"
    else
      check "Milvus" "FAIL" "контейнер запущен, но health=$health. Починка: docker logs $MILVUS_CONTAINER"
    fi
  else
    check "Milvus" "FAIL" "контейнер $MILVUS_CONTAINER не запущен. Починка: make zed-search"
  fi
else
  check "Milvus" "FAIL" "docker недоступен. Починка: запусти Docker Desktop"
fi

# 3. Watcher (launchd-агент)
if launchctl list 2>/dev/null | grep -qw "$WATCH_LABEL"; then
  check "Watcher" "OK" "launchd-агент $WATCH_LABEL загружен (автоиндексация активна)"
else
  check "Watcher" "WARN" "launchd-агент $WATCH_LABEL НЕ загружен. Индексация только по background-sync MCP. Починка: make zed-search-watch-install"
fi

# 4. Индекс (snapshot + merkle)
if [ -f "$SNAPSHOT_FILE" ]; then
  # Возраст snapshot в часах
  snapshot_mtime="$(stat -f '%m' "$SNAPSHOT_FILE" 2>/dev/null || stat -c '%Y' "$SNAPSHOT_FILE" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  age_hours=$(( (now - snapshot_mtime) / 3600 ))
  if [ "$age_hours" -gt "$INDEX_STALE_HOURS" ]; then
    check "Индекс" "WARN" "snapshot устарел (${age_hours}ч > ${INDEX_STALE_HOURS}ч). Починка: make zed-search-reindex"
  else
    check "Индекс" "OK" "snapshot свежий (${age_hours}ч)"
  fi
else
  check "Индекс" "WARN" "snapshot-файл отсутствует ($SNAPSHOT_FILE). Первичная индексация ещё не прошла или MCP не запущен. Починка: открой проект в Zed (MCP запустит индексацию) или make zed-search-reindex"
fi

if [ -d "$MERKLE_DIR" ]; then
  merkle_files="$(find "$MERKLE_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')"
  check "Merkle" "OK" "$merkle_files файлов в дереве"
else
  check "Merkle" "WARN" "каталог $MERKLE_DIR отсутствует. Инкрементальная индексация не настроена."
fi

# 5. Пакет MCP + проверка версии (свежая ли сборка)
if command -v npx >/dev/null 2>&1; then
  # Установленная версия из кеша npx
  installed_version="нет"
  pkg_json="$(find "$HOME/.npm/_npx" -name "package.json" -path "*claude-context-mcp*" 2>/dev/null | head -1)"
  if [ -n "$pkg_json" ]; then
    installed_version="$(python3 -c "import json; print(json.load(open('$pkg_json')).get('version','?'))" 2>/dev/null || echo "?")"
  fi
  # Актуальная версия в npm
  latest_version="$(npm view @zilliz/claude-context-mcp version 2>/dev/null || echo "?")"
  if [ "$latest_version" = "?" ]; then
    check "MCP-пакет" "WARN" "npx доступен, но не удалось получить версию из npm (нет сети?). Установлена: $installed_version"
  elif [ "$installed_version" = "$latest_version" ]; then
    check "MCP-пакет" "OK" "npx + @zilliz/claude-context-mcp v$installed_version (актуальна)"
  else
    check "MCP-пакет" "WARN" "устарела: v$installed_version, в npm v$latest_version. Починка: make zed-search-update + перезапуск Zed"
  fi
else
  check "MCP-пакет" "FAIL" "npx не найден. Починка: установи Node.js (brew install node)"
fi

# 6. codebase-memory-mcp (структурный граф знаний)
if [ -x "$CBM_BIN" ] && "$CBM_BIN" --version >/dev/null 2>&1; then
  cbm_ver="$(bash "$CBM_SH" installed-version 2>/dev/null || echo "")"
  check "CBM-бинарь" "OK" "v${cbm_ver:-?} ($CBM_BIN)"

  cbm_info="$(bash "$CBM_SH" project-info "$(pwd -P 2>/dev/null || pwd)" 2>/dev/null || echo "")"
  if [ -n "$cbm_info" ]; then
    check "CBM-граф" "OK" "проиндексирован: $(echo "$cbm_info" | awk '{print $1}') ($(echo "$cbm_info" | awk '{print $2}') узлов)"
  else
    check "CBM-граф" "WARN" "проект не проиндексирован. Починка: make zed-search-reindex"
  fi

  cbm_latest="$(bash "$CBM_SH" latest-version 2>/dev/null || echo "")"
  if [ -z "$cbm_latest" ]; then
    check "CBM-версия" "WARN" "не удалось получить актуальную версию (нет сети?). Установлена: v${cbm_ver:-?}"
  elif [ "${cbm_ver:-}" = "$cbm_latest" ]; then
    check "CBM-версия" "OK" "v${cbm_ver} актуальна"
  else
    check "CBM-версия" "WARN" "устарела: v${cbm_ver:-?}, актуальна v$cbm_latest. Починка: make zed-search-update"
  fi

  if [ "$(bash "$CBM_SH" auto-index 2>/dev/null || echo false)" = "true" ]; then
    check "CBM-auto_index" "OK" "включён (граф автоиндексируется при старте сессии)"
  else
    check "CBM-auto_index" "WARN" "auto_index выключен. Починка: codebase-memory-mcp config set auto_index true"
  fi
else
  check "CBM-бинарь" "FAIL" "бинарь не установлен ($CBM_BIN). Починка: make zed-search"
fi

# --- Итоговый отчёт ---
echo "================================================================"
echo "[zed-search-check] Health стека поиска (claude-context + codebase-memory-mcp)"
echo "[zed-search-check] Health claude-context MCP"
echo "================================================================"
printf '%s\n' "${REPORT[@]}"
echo ""
if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "[zed-search-check] ❌ Сломано: $FAIL_COUNT, предупреждений: $WARN_COUNT, ОК: $OK_COUNT"
  echo "[zed-search-check] Семантический поиск НЕ РАБОТАЕТ. Агент должен сказать пользователю:"
  echo "  «claude-context MCP не работает. Запусти: make zed-search»"
  exit 1
fi
if [ "$WARN_COUNT" -gt 0 ]; then
  echo "[zed-search-check] ⚠️  Предупреждений: $WARN_COUNT, ОК: $OK_COUNT — поиск работает, но есть риски."
  exit 0
fi
echo "[zed-search-check] ✅ Всё ОК ($OK_COUNT компонентов). MCP готов к семантическому поиску."
exit 0