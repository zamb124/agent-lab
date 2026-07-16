#!/usr/bin/env bash
# Опциональная настройка Linear MCP: спрашивает API-токен и вписывает в settings.json Zed.
# Вызывается из: make zed-search

set -euo pipefail

ZED_SETTINGS="${ZED_SETTINGS:-$HOME/.config/zed/settings.json}"
INFO="[zed-search]"

echo ""
echo "$INFO Linear MCP (необязательно) — issue-tracking через Linear.app"

if [ ! -f "$ZED_SETTINGS" ]; then
  echo "$INFO settings.json не найден — пропускаю."
  exit 0
fi

# Уже настроен — не спрашиваем повторно
if python3 - "$ZED_SETTINGS" <<'PY'
import json, sys
path = sys.argv[1]
s = open(path).read()

def strip_jsonc(s):
    out = []
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

try:
    data = json.loads(strip_jsonc(s))
    tok = (
        data.get("context_servers", {})
        .get("linear", {})
        .get("env", {})
        .get("LINEAR_ACCESS_TOKEN", "")
    )
    sys.exit(0 if tok else 1)
except Exception:
    sys.exit(1)
PY
then
  echo "$INFO Linear MCP уже настроен — пропускаю."
  exit 0
fi

echo "$INFO Токен: Linear → Personal Settings → API → Personal API Keys"
printf "%s" "$INFO Вставь Linear API-токен (lin_api_…) и Enter, либо Enter чтобы пропустить: "
read -r LINEAR_TOKEN </dev/tty || LINEAR_TOKEN=""
echo ""

if [ -z "$LINEAR_TOKEN" ]; then
  echo "$INFO Пропущено."
  exit 0
fi

python3 - "$ZED_SETTINGS" "$LINEAR_TOKEN" <<'PY'
import json, shutil, datetime, sys

path, token = sys.argv[1], sys.argv[2]

def strip_jsonc(s):
    out = []
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

s = open(path).read()
old = '  "context_servers": {\n'
if s.count(old) != 1:
    print("[zed-search] context_servers не найден — пропускаю.", file=sys.stderr)
    sys.exit(0)

block = (
    '    "linear": {\n'
    '      "enabled": true,\n'
    '      "command": "npx",\n'
    '      "args": [\n'
    '        "-y",\n'
    '        "mcp-server-linear"\n'
    '      ],\n'
    '      "env": {\n'
    '        "LINEAR_ACCESS_TOKEN": ' + json.dumps(token) + '\n'
    '      }\n'
    '    }'
)
new = s.replace(old, old + block + ',\n', 1)
json.loads(strip_jsonc(new))
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(path, path + ".bak." + ts)
open(path, "w").write(new)
print("[zed-search] Linear MCP добавлен в settings.json")
PY

echo "$INFO Перезапусти Zed, чтобы подхватить Linear MCP."
