#!/usr/bin/env bash
# Проверка архитектурного канона UI: apps/* наследуют PlatformElement/модалки из core,
# импорты lib только через @platform/*, ServiceRegistry не в прикладном коде apps.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
    echo "check_ui_canon: нужен ripgrep (rg)" >&2
    exit 1
fi

ERR=0

if rg -q 'extends LitElement' apps -g '*.js'; then
    echo "check_ui_canon: запрещено extends LitElement в apps/**/*.js" >&2
    rg 'extends LitElement' apps -g '*.js' >&2 || true
    ERR=1
fi

if rg -q "from ['\"]/static/core/lib" apps -g '*.js'; then
    echo "check_ui_canon: импорты из /static/core/lib обходят import map; используйте @platform/lib/..." >&2
    rg "from ['\"]/static/core/lib" apps -g '*.js' >&2 || true
    ERR=1
fi

if rg -q '\bServiceRegistry\b' apps -g '*.js'; then
    echo "check_ui_canon: ServiceRegistry не импортировать в apps/; bootstrap через this.services в *App" >&2
    rg '\bServiceRegistry\b' apps -g '*.js' >&2 || true
    ERR=1
fi

if [ "$ERR" -ne 0 ]; then
    exit 1
fi

echo "check_ui_canon: OK"
