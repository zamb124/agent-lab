#!/usr/bin/env bash
# codebase-memory-mcp — структурный граф знаний (tree-sitter AST + Hybrid LSP → SQLite).
# Установка / обновление / переиндексация / статус. Идемпотентно.
# Вызывается из Make (mk/search.mk): make zed-search / -update / -reindex / -status.
#
# Health-check живёт в healthcheck.sh (один отчёт + один exit-код для всего стека):
# healthcheck.sh вызывает геттеры cbm.sh (installed-version / latest-version /
# project-info / auto-index), чтобы не дублировать логику разбора графа.

set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO="DeusData/codebase-memory-mcp"
INSTALL_DIR="${CBM_INSTALL_DIR:-$HOME/.local/bin}"
BIN="$INSTALL_DIR/codebase-memory-mcp"
CBM_VERSION="${CBM_VERSION:-latest}"   # "latest" или тег, например "v0.9.0"
PROJECT_ROOT="${CBM_PROJECT_ROOT:-$(pwd -P 2>/dev/null || pwd)}"

INFO="[zed-search]"
section() { echo ""; echo "$INFO $1"; }

# --- детект платформы ---
detect_os()   { case "$(uname -s)" in Darwin) echo darwin;; Linux) echo linux;; MINGW*|MSYS*|CYGWIN*) echo windows;; *) return 1;; esac; }
detect_arch() {
  local a; a="$(uname -m)"
  case "$a" in arm64|aarch64) echo arm64;; x86_64|amd64) echo amd64;; *) return 1;; esac
}

# --- версии ---
latest_tag() {
  curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('tag_name',''))" 2>/dev/null || true
}
installed_version() { [ -x "$BIN" ] && "$BIN" --version 2>/dev/null | awk 'NR==1{print $2}' || true; }

# --- имя/размер проекта в графе по root_path → одна строка "name nodes edges" (или пусто) ---
project_info_for_root() {
  local root="${1:-$PROJECT_ROOT}"
  [ -x "$BIN" ] || return 0
  "$BIN" cli list_projects 2>&1 | python3 -c "
import sys,json
raw=sys.stdin.read()
i=raw.find('{\"')
if i<0: sys.exit()
try: obj,_=json.JSONDecoder().raw_decode(raw[i:])
except: sys.exit()
root=sys.argv[1] if len(sys.argv)>1 else ''
for p in obj.get('projects',[]):
    if p.get('root_path')==root:
        print(p.get('name',''), p.get('nodes',0), p.get('edges',0)); break
" "$root" 2>/dev/null || true
}

# --- конфиг single-writer ---
# Канон (daemon): один процесс CBM за mcp-proxy (launchd com.codebase-memory-mcp.daemon),
# auto_index=true + auto_watch=true. Клиенты Zed/Cursor ходят по URL, не спавнят stdio.
# Без daemon (legacy): auto_*=false и ручной reindex — см. cbm_config_safe_writers.
# Установка daemon: bash scripts/zed_search/cbm_daemon.sh install

auto_index_state() {
  [ -x "$BIN" ] || { echo false; return; }
  if "$BIN" config get auto_index 2>/dev/null | grep -qi true; then echo true; else echo false; fi
}

auto_watch_state() {
  [ -x "$BIN" ] || { echo false; return; }
  if "$BIN" config get auto_watch 2>/dev/null | grep -qi true; then echo true; else echo false; fi
}

CBM_LOCK_DIR="${CBM_LOCK_DIR:-$HOME/.cache/codebase-memory-mcp}"
CBM_LOCK_FILE="$CBM_LOCK_DIR/reindex.lock"
CBM_DAEMON_SH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cbm_daemon.sh"

cbm_config() {
  # Дефолт при install бинаря без daemon — безопасный multi-stdio.
  # После cbm_daemon.sh install конфиг переключается на auto_*=true.
  "$BIN" config set auto_index false >/dev/null 2>&1 || true
  "$BIN" config set auto_watch false >/dev/null 2>&1 || true
}

# Legacy: MCP stdio на каждую сессию — только чтение, без watch.
cbm_config_safe_writers() {
  if ! [ -x "$BIN" ]; then
    echo "  ❌ бинарь не установлен. Починка: make zed-search"
    return 1
  fi
  cbm_config
  local ai aw
  ai="$("$BIN" config get auto_index 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  aw="$("$BIN" config get auto_watch 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  echo "  auto_index=${ai:-?}  auto_watch=${aw:-?}  (legacy multi-stdio: оба false)"
  if [ "$ai" != "false" ] || [ "$aw" != "false" ]; then
    echo "  ⚠️  не удалось выставить auto_index/auto_watch в false. Проверь: $BIN config list"
    return 1
  fi
}

cbm_config_autoidx() { cbm_config_safe_writers "$@"; }

cbm_daemon_installed() {
  [ -f "${HOME}/Library/LaunchAgents/com.codebase-memory-mcp.daemon.plist" ]
}

# ============================================================================
# install — скачать + SHA-256 + codesign + установить + конфиг
# ============================================================================
cbm_install() {
  section "codebase-memory-mcp (структурный граф)..."
  if [ -x "$BIN" ] && "$BIN" --version >/dev/null 2>&1; then
    echo "  уже установлен: v$(installed_version) ($BIN) — пропуск"
    if cbm_daemon_installed; then
      echo "  daemon установлен — оставляю auto_index/auto_watch=true"
      "$BIN" config set auto_index true >/dev/null 2>&1 || true
      "$BIN" config set auto_watch true >/dev/null 2>&1 || true
    else
      cbm_config
    fi
    return 0
  fi

  local os arch archive ext base dldir
  os="$(detect_os)" || { echo "$INFO ОШИБКА: неподдерживаемая ОС"; exit 1; }
  arch="$(detect_arch)" || { echo "$INFO ОШИБКА: неподдерживаемая архитектура"; exit 1; }
  ext="tar.gz"; [ "$os" = "windows" ] && ext="zip"
  archive="codebase-memory-mcp-${os}-${arch}.${ext}"   # macOS/Windows без -portable

  if [ "$CBM_VERSION" = "latest" ]; then base="https://github.com/$REPO/releases/latest/download"
  else base="https://github.com/$REPO/releases/download/$CBM_VERSION"; fi

  echo "  Установка v${CBM_VERSION} ($os/$arch)..."
  dldir="$(mktemp -d)"; trap 'rm -rf "$dldir"' EXIT

  echo "  Скачиваю $archive..."
  curl -fsSL -o "$dldir/$archive" "$base/$archive" || { echo "$INFO ОШИБКА: не удалось скачать $archive"; exit 1; }

  echo "  Скачиваю checksums.txt..."
  curl -fsSL -o "$dldir/checksums.txt" "$base/checksums.txt" 2>/dev/null || true

  local expected=""
  [ -f "$dldir/checksums.txt" ] && expected="$(grep " $archive\$" "$dldir/checksums.txt" | awk '{print $1}')"
  if [ -n "$expected" ]; then
    local actual
    if command -v sha256sum >/dev/null 2>&1; then actual="$(sha256sum "$dldir/$archive" | awk '{print $1}')"
    else actual="$(shasum -a 256 "$dldir/$archive" | awk '{print $1}')"; fi
    if [ "$expected" != "$actual" ]; then
      echo "$INFO ОШИБКА: SHA-256 не совпал. expected=$expected actual=$actual"; exit 1
    fi
    echo "  SHA-256 совпал ✓"
  else
    echo "  ⚠️ checksums.txt без записи для $archive — проверка пропущена"
  fi

  ( cd "$dldir" && { [ "$ext" = "zip" ] && unzip -q "$archive" || tar xzf "$archive"; } )
  [ -f "$dldir/codebase-memory-mcp" ] || { echo "$INFO ОШИБКА: бинарь не найден после распаковки"; exit 1; }

  # macOS: strip quarantine + ad-hoc codesign
  if [ "$os" = "darwin" ]; then
    xattr -d com.apple.quarantine "$dldir/codebase-memory-mcp" 2>/dev/null || true
    codesign --sign - --force "$dldir/codebase-memory-mcp" 2>/dev/null || true
  fi

  mkdir -p "$INSTALL_DIR"
  cp "$dldir/codebase-memory-mcp" "$BIN"
  chmod 755 "$BIN"
  echo "  Установлен: v$(installed_version) -> $BIN"

  cbm_config
  echo "  ✅ codebase-memory-mcp готов. Перезапусти Zed, чтобы MCP-сервер подхватился."
}

# ============================================================================
# update — сверка версии с последним релизом и обновление
# ============================================================================
cbm_update() {
  section "codebase-memory-mcp: проверка версии..."
  if ! [ -x "$BIN" ]; then echo "  ❌ бинарь не установлен. Починка: make zed-search"; return 1; fi
  local inst latest
  inst="$(installed_version)"
  latest="$(latest_tag | sed 's/^v//')"
  if [ -z "$latest" ]; then
    echo "  ⚠️ не удалось получить актуальную версию (нет сети?). Установлена: v${inst:-?}"
    return 0
  fi
  if [ "${inst:-}" = "$latest" ]; then
    echo "  ✅ v${inst} актуальна."
    return 0
  fi
  echo "  Установлена v${inst:-?}, актуальна v$latest — обновляю..."
  if "$BIN" update -y >/dev/null 2>&1; then
    echo "  ✅ обновлено до v$(installed_version). Перезапусти Zed."
  else
    echo "  ⚠️ codebase-memory-mcp update не удался — переустанови: CBM_VERSION=latest make zed-search"
    return 1
  fi
}

# ============================================================================
# reindex — переиндексация графа (единственный писатель; lock через fcntl, без util-linux flock)
# ============================================================================
cbm_reindex() {
  local root="${1:-$PROJECT_ROOT}"
  local had_daemon=0
  section "codebase-memory-mcp: индексация графа..."
  if ! [ -x "$BIN" ]; then echo "  ❌ бинарь не установлен. Починка: make zed-search"; return 1; fi
  if cbm_daemon_installed; then
    had_daemon=1
    echo "  останавливаю CBM daemon на время exclusive reindex..."
    bash "$CBM_DAEMON_SH" stop >/dev/null 2>&1 || true
  else
    cbm_config
  fi
  local writers
  writers="$(pgrep -x codebase-memory-mcp 2>/dev/null | wc -l | tr -d ' ' || true)"
  writers="${writers:-0}"
  if [ "$writers" -gt 0 ]; then
    echo "  ⚠️  ещё запущено codebase-memory-mcp: $writers — жду освобождения..."
    sleep 2
  fi
  echo "  index_repository: $root"
  mkdir -p "$CBM_LOCK_DIR"
  set +e
  python3 - "$CBM_LOCK_FILE" "$BIN" "$root" <<'PY'
import fcntl, json, os, subprocess, sys

lock_path, bin_path, root = sys.argv[1], sys.argv[2], sys.argv[3]
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print(f"  ❌ другой reindex уже идёт (lock: {lock_path}). Дождись.")
    sys.exit(1)
os.ftruncate(fd, 0)
os.write(fd, f"{os.getpid()}\n".encode())

proc = subprocess.run(
    [bin_path, "cli", "index_repository", json.dumps({"repo_path": root})],
    capture_output=True,
    text=True,
)
raw = (proc.stdout or "") + (proc.stderr or "")
idx = raw.find('{"')
if idx < 0:
    print("  (нет JSON-ответа)")
    if raw.strip():
        print(raw.strip()[:500])
    sys.exit(1 if proc.returncode else 0)
try:
    obj, _ = json.JSONDecoder().raw_decode(raw[idx:])
except Exception as exc:
    print("  parse error:", exc)
    sys.exit(1)
nodes = obj.get("nodes", obj.get("expected_nodes", "?"))
edges = obj.get("edges", obj.get("expected_edges", "?"))
print(
    f"  проект: {obj.get('project', '?')} | узлов: {nodes} | рёбер: {edges} | status: {obj.get('status', '?')}"
)
sys.exit(proc.returncode)
PY
  local rc=$?
  set -e
  if [ "$had_daemon" -eq 1 ]; then
    echo "  поднимаю CBM daemon обратно..."
    bash "$CBM_DAEMON_SH" start || true
  fi
  return "$rc"
}

# ============================================================================
# status — быстрая сводка
# ============================================================================
cbm_status() {
  if [ -x "$BIN" ] && "$BIN" --version >/dev/null 2>&1; then
    local v; v="$(installed_version)"
    echo "[zed-search] codebase-memory-mcp: v${v:-?} ($BIN)"
    local info; info="$(project_info_for_root "$PROJECT_ROOT")"
    if [ -n "$info" ]; then
      echo "[zed-search] граф: $(echo "$info" | awk '{print $1}') — $(echo "$info" | awk '{print $2}') узлов, $(echo "$info" | awk '{print $3}') рёбер"
    else
      echo "[zed-search] граф: проект не проиндексирован. Починка: make zed-search-reindex"
    fi
  else
    echo "[zed-search] codebase-memory-mcp: НЕ установлен. Починка: make zed-search"
  fi
}

# --- диспетч (только при прямом запуске, не при source) ---
if [ "${BASH_SOURCE[0]}" = "${0}" ] 2>/dev/null; then
  cmd="${1:-status}"
  case "$cmd" in
    install)           shift; cbm_install "$@" ;;
    update)            cbm_update ;;
    reindex)           shift; cbm_reindex "$@" ;;
    config-autoidx|config-safe-writers) cbm_config_safe_writers ;;
    status)            cbm_status ;;
    installed-version) installed_version ;;
    latest-version)    latest_tag | sed 's/^v//' ;;
    project-info)      shift; project_info_for_root "${1:-}" ;;
    auto-index)        auto_index_state ;;
    auto-watch)        auto_watch_state ;;
    *) echo "usage: cbm.sh [install|update|reindex|config-safe-writers|status|installed-version|latest-version|project-info <root>|auto-index|auto-watch]"; exit 1 ;;
  esac
fi
