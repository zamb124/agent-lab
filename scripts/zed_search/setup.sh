#!/usr/bin/env bash
# Полная настройка бэкенда для claude-context MCP (семантический поиск по коду):
#   1. Ollama — локальный сервер эмбеддингов
#   2. nomic-embed-text — модель эмбеддингов
#   3. Milvus Standalone — векторная БД (в Docker)
#   4. fswatch — watcher для автоиндексации
# Идемпотентно: пропускает уже настроенные шаги.
# Вызывается из Make: make zed-search

set -euo pipefail

# --- Конфигурация (можно переопределить env-переменными) ---
OLLAMA_MODEL="${OLLAMA_MODEL:-nomic-embed-text}"
OLLAMA_HOST_URL="${OLLAMA_HOST_URL:-http://127.0.0.1:11434}"
MILVUS_ADDRESS="${MILVUS_ADDRESS:-127.0.0.1:19530}"

CLAUDE_CONTEXT_DIR="${CLAUDE_CONTEXT_DIR:-$HOME/.local/share/claude-context-milvus}"
COMPOSE_FILE="$CLAUDE_CONTEXT_DIR/docker-compose.yml"
MILVUS_VERSION="${MILVUS_VERSION:-v2.6.7}"
MILVUS_COMPOSE_URL="https://github.com/milvus-io/milvus/releases/download/${MILVUS_VERSION}/milvus-standalone-docker-compose.yml"

# Порты MinIO сдвинуты, чтобы не конфликтовать с dev-окружением (9000/9001)
MILVUS_MINIO_API_PORT="${MILVUS_MINIO_API_PORT:-9005}"
MILVUS_MINIO_CONSOLE_PORT="${MILVUS_MINIO_CONSOLE_PORT:-9006}"

INFO="[zed-search]"
section() { echo ""; echo "$INFO $1"; }

# --- Проверка базовых зависимостей ---
if ! command -v brew >/dev/null 2>&1; then
  echo "$INFO ОШИБКА: Homebrew не установлен. См. https://brew.sh"
  exit 1
fi

# ============================================================================
# 1. Ollama (локальные эмбеддинги)
# ============================================================================
section "[1/4] Ollama (локальные эмбеддинги)..."
if ! command -v ollama >/dev/null 2>&1; then
  echo "  Устанавливаю ollama через brew..."
  brew install ollama
else
  echo "  ollama уже установлен"
fi

if curl -sf "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1; then
  echo "  ollama уже запущена"
else
  echo "  Запускаю ollama как фоновый сервис (brew services)..."
  brew services start ollama >/dev/null
fi

echo "  Ожидание готовности ollama..."
ready=0
for i in $(seq 1 30); do
  if curl -sf "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "  ОШИБКА: ollama не ответила за 30с. Проверь: brew services info ollama"
  exit 1
fi
echo "  ollama готова ($OLLAMA_HOST_URL)"

if ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
  echo "  Модель $OLLAMA_MODEL уже загружена"
else
  echo "  Загружаю модель $OLLAMA_MODEL..."
  ollama pull "$OLLAMA_MODEL"
fi

# ============================================================================
# 2. Milvus (векторная БД)
# ============================================================================
section "[2/4] Milvus (векторная БД)..."
if ! command -v docker >/dev/null 2>&1; then
  echo "$INFO ОШИБКА: docker не установлен / не запущен."
  exit 1
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'milvus-standalone'; then
  echo "  Milvus уже запущен — пропуск (контейнер milvus-standalone найден)"
else
  echo "  docker-compose.yml -> $COMPOSE_FILE"
  mkdir -p "$CLAUDE_CONTEXT_DIR"
  curl -fsSL "$MILVUS_COMPOSE_URL" -o "$COMPOSE_FILE"
  # Сдвиг портов MinIO во избежание конфликта с dev-окружением на 9000/9001
  sed -i '' "s/9000:9000/${MILVUS_MINIO_API_PORT}:9000/g" "$COMPOSE_FILE"
  sed -i '' "s/9001:9001/${MILVUS_MINIO_CONSOLE_PORT}:9001/g" "$COMPOSE_FILE"
  echo "  Запуск контейнеров Milvus (etcd + minio + standalone)..."
  docker compose -f "$COMPOSE_FILE" up -d
  echo "  Ожидание готовности Milvus (healthcheck, до 120с)..."
  ready=0
  for i in $(seq 1 60); do
    status="$(docker inspect --format '{{.State.Health.Status}}' milvus-standalone 2>/dev/null || echo "")"
    if [ "$status" = "healthy" ]; then ready=1; break; fi
    sleep 2
  done
  if [ "$ready" -ne 1 ]; then
    echo "  ОШИБКА: Milvus не стал healthy. Логи: docker logs milvus-standalone"
    exit 1
  fi
  echo "  Milvus готов ($MILVUS_ADDRESS)"
fi

# ============================================================================
# 3. fswatch (watcher для автоиндексации)
# ============================================================================
section "[3/4] fswatch (watcher для автоиндексации)..."
if ! command -v fswatch >/dev/null 2>&1; then
  echo "  Устанавливаю fswatch через brew..."
  brew install fswatch
else
  echo "  fswatch уже установлен"
fi

# ============================================================================
# 4. Сводка
# ============================================================================
section "[4/4] Проверка связки..."
ollama_status="FAIL"
curl -sf "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1 && ollama_status="OK ($OLLAMA_MODEL)"
milvus_status="$(docker inspect --format '{{.State.Health.Status}}' milvus-standalone 2>/dev/null || echo 'stopped')"
fswatch_status="missing"
command -v fswatch >/dev/null 2>&1 && fswatch_status="OK"
echo "  Ollama:  $ollama_status"
echo "  Milvus:  $milvus_status (MILVUS_ADDRESS=$MILVUS_ADDRESS)"
echo "  fswatch: $fswatch_status"

echo ""
echo "$INFO ✅ Бэкенд готов."
echo ""
echo "$INFO Первичная индексация кодовой базы запускается автоматически"
echo "$INFO через make zed-search (шаг после setup)."
echo ""
echo "Проверка здоровья:    make zed-search-check"
echo "Обновление MCP:       make zed-search-update"
echo "Переиндексация:       make zed-search-reindex"
