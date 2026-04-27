# Browser MCP

Сервис `browser` экспортирует Browser Runtime как MCP (Model Context Protocol) JSON-RPC 2.0 endpoint.

## Endpoint

- MCP JSON-RPC: `/browser/api/v1/mcp`

Поддерживаемые методы JSON-RPC:

- `initialize`
- `tools/list`
- `tools/call`

## MCP server config (flows)

Пример создания MCP server config для компании (через flows API) должен указывать URL browser MCP:

- `url`: `http(s)://<host>/browser/api/v1/mcp`

`server_id` выбирайте стабильный, например `browser`.

## Использование во flow

### MCP нода графа

```json
{
  "type": "mcp",
  "server_id": "browser",
  "tool_name": "browser_observe",
  "input_mapping": {
    "session_id": "@state:browser_session_id"
  },
  "output_mapping": {
    "mcp_result": "browser_snapshot_json"
  }
}
```

### MCP tool внутри `llm_node`

```json
{
  "tool_id": "browser_observe_tool",
  "type": "mcp",
  "server_id": "browser",
  "tool_name": "browser_observe"
}
```

## Tools

Список MCP tools (см. `tools/list`):

- `browser_create_session`
- `browser_navigate`
- `browser_observe`
- `browser_click`
- `browser_fill`
- `browser_press`
- `browser_wait`
- `browser_close_session`

## Канон взаимодействий (обязательно)

Для кликов и ввода текста **нельзя** использовать селекторы, поиск по тексту или прямую навигацию “на нужный элемент”.

Единственный поддерживаемый поток действий для UI-взаимодействий:

- `browser_observe` → получить `snapshot.text` и `snapshot.refs`
- выбрать `ref` из `snapshot.refs` (например `e42` или `@e42`, в зависимости от клиента)
- `browser_click(ref=...)` / `browser_fill(ref=..., text=...)`

Это требуется для корректной работы human-like взаимодействий (interaction profile `human`) и стабильной воспроизводимости действий.

## Lightpanda (CDP)

Единственный поддерживаемый способ запуска Lightpanda для Browser Runtime — CDP server в debug режиме через `docker run`:

```bash
docker run --rm -it --name lightpanda \
  -p 127.0.0.1:9222:9222 \
  lightpanda/browser:nightly \
  lightpanda serve --host 0.0.0.0 --port 9222 --log-level debug --log-format pretty
```

## Chromium (CDP)

Browser Runtime поддерживает CDP Chromium на тех же условиях, что и Lightpanda:

- используется тот же `browser.cdp_url` / `browser.cdp_endpoints`;
- `endpoint_key` может быть любым ключом из `cdp_endpoints`, включая `"chromium"`;
- отдельного набора настроек для Chromium нет: поведение и возможности CDP-ветки совпадают 1:1.

Пример запуска локального Chromium с CDP:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir="$(mktemp -d)" \
  --no-first-run --no-default-browser-check
```

CDP URL можно получить через `http://127.0.0.1:9222/json/version` → поле `webSocketDebuggerUrl`
и передать его в `BROWSER__CDP_URL`.

### Chromium с CDP через Docker

Ниже пример запуска headless Chromium с открытым CDP-портом `9222`:

```bash
docker run --rm -it --name chromium-cdp \
  -p 127.0.0.1:9222:9222 \
  --shm-size=1g \
  zenika/alpine-chrome:124 \
  chromium-browser \
    --headless=new \
    --no-sandbox \
    --disable-dev-shm-usage \
    --remote-debugging-address=0.0.0.0 \
    --remote-debugging-port=9222 \
    about:blank
```

Проверка, что CDP поднялся:

- `http://127.0.0.1:9222/json/version` → поле `webSocketDebuggerUrl`

Настройка Browser Runtime:

- для локального запуска `browser` на хосте: `BROWSER__CDP_URL=<webSocketDebuggerUrl>` или `BROWSER__CDP_ENDPOINTS__chromium=<webSocketDebuggerUrl>`
- если `browser` тоже запущен в Docker: вместо `127.0.0.1` используйте адрес хоста, доступный контейнеру (например `host.docker.internal`), либо поднимайте Chromium в той же docker-сети и используйте имя контейнера/сервиса

