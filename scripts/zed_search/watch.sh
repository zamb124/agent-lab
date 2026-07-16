#!/usr/bin/env bash
# claude-context auto-reindex watcher
#
# Watches the project directory and touches ~/.context/.sync-trigger whenever
# files change. The @zilliz/claude-context-mcp server watches that sentinel file
# and starts an incremental (Merkle-based) re-index — only changed files get
# re-embedded. The MCP server debounces by 2s, so rapid bursts collapse to a
# single re-index.
#
# Requires: fswatch (brew install fswatch)

set -euo pipefail

# launchd запускает с минимальным окружением без PATH Homebrew — добавляем.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# По умолчанию — корень проекта (родитель каталога scripts/)
PROJECT_DIR="${1:-$(dirname "$SCRIPT_DIR")}"
TRIGGER_FILE="${HOME}/.context/.sync-trigger"

mkdir -p "$(dirname "$TRIGGER_FILE")"
touch "$TRIGGER_FILE"

if ! command -v fswatch >/dev/null 2>&1; then
  echo "ERROR: fswatch is not installed (PATH=$PATH)." >&2
  echo "Install it:  brew install fswatch" >&2
  exit 1
fi

echo "[claude-context-watch] Watching: $PROJECT_DIR"
echo "[claude-context-watch] Trigger:  $TRIGGER_FILE"
echo "[claude-context-watch] MCP server debounces re-index by 2s. Ctrl+C to stop."

fswatch \
  --event Created \
  --event Updated \
  --event Removed \
  --event Renamed \
  --exclude '/\.git/' \
  --exclude '/node_modules/' \
  --exclude '/\.venv/' \
  --exclude '/__pycache__/' \
  --exclude '/\.pytest_cache/' \
  --exclude '/\.ruff_cache/' \
  --exclude '/\.idea/' \
  --exclude '/\.cursor/' \
  --exclude '/\.zed/' \
  --exclude '/\.vscode/' \
  --exclude '/dist/' \
  --exclude '/build/' \
  --exclude '/test-results/' \
  --exclude '/artifacts/' \
  "$PROJECT_DIR" \
  | while IFS= read -r _; do
      touch "$TRIGGER_FILE"
      echo "[claude-context-watch] $(date '+%H:%M:%S') trigger touched -> re-index queued"
    done
