---
name: figma-mcp
description: Подключение агента к Figma и FigJam через figma-console-mcp — установка и запуск плагина Desktop Bridge в Figma Desktop, вызовы инструментов (чтение досок, стикеров, скриншоты, токены, запись), драйвер scripts/tools/figma_mcp.py без MCP-реестра, troubleshooting коннекта и токенов. Использовать при любой работе с файлами/досками/комментариями Figma, ссылками figma.com, дизайн-токенами и переносом макетов в код.
---

# Figma MCP — подключение и вызовы

Канон → [`.cursor/rules/figma.mdc`](mdc:.cursor/rules/figma.mdc). Сервер `figma-console` объявлен в `.cursor/mcp.json` (`npx -y figma-console-mcp@1.46.0`, ~130 инструментов). Основной транспорт — плагин **Desktop Bridge** в Figma Desktop: Plugin API, без REST-лимитов и без токена.

## Архитектура

```
Агент ──stdio MCP──▶ npx figma-console-mcp ──ws://localhost:9223–9232──▶ Desktop Bridge плагин ──Plugin API──▶ открытый файл/доска
```

- Сервер при каждом старте перезаписывает плагин в `~/.figma-console-mcp/plugin/`.
- Плагин открыт на файле ⇄ мост жив; закрыли плагин — `transport.active` становится `none`.
- `editorType` плагина: `figma`, `figjam`, `slides`, `dev`.

## Первичная настройка (один раз на машину)

1. Node.js 18+ и Figma Desktop (веб-Figma не подходит).
2. `npx -y figma-console-mcp@1.46.0 --print-path` — печатает путь к `manifest.json` и создаёт `~/.figma-console-mcp/plugin/`.
3. В Figma Desktop с открытым файлом: `Plugins → Development → Import plugin from manifest…` → `⌘⇧G` → вставить `/Users/<user>/.figma-console-mcp/plugin/manifest.json` → Import.
4. `Plugins → Development → Figma Desktop Bridge` — окно плагина показывает `Connected` (~3 c).
5. Проверка: `uv run python -m scripts.tools.figma_mcp status` → `transport.active: "websocket"`, `currentFileName` — имя файла.

## Вызовы

Через MCP-реестр IDE инструменты видны как `figma_*`/`figjam_*`. Без реестра (текущая сессия, CI):

```bash
uv run python -m scripts.tools.figma_mcp list                      # все инструменты
uv run python -m scripts.tools.figma_mcp call <tool> '<json>'      # один вызов
uv run python -m scripts.tools.figma_mcp batch <file>              # пакет: JSON-список или JSONL
uv run python -m scripts.tools.figma_mcp status                    # figma_get_status probe:true
uv run python -m scripts.tools.figma_mcp --wait-plugin 60 status   # ждать подключения моста
```

Каждый запуск поднимает сервер, выполняет вызовы и гасит его; плагин переподключается к новому экземпляру на том же порту. `--raw` — полный JSON-RPC конверт.

## Карта инструментов

| Задача | Инструмент |
|---|---|
| Состояние моста | `figma_get_status` (`probe: true`), `figma_reconnect`, `figma_list_open_files`, `figma_navigate` |
| Доска FigJam | `figjam_get_board_contents` (стикеры/фигуры/коннекторы/секции/текст), `figjam_get_connections` |
| Документ | `figma_get_file_data`, `figma_get_selection`, `figma_get_design_changes` |
| Снимок | `figma_take_screenshot` (страница/узел), `figma_capture_screenshot` (текущий кадр узла) |
| Комментарии | `figma_get_comments`, `figma_post_comment`, `figma_delete_comment` — REST, нужен `FIGMA_ACCESS_TOKEN` |
| Токены/компоненты | `figma_get_variables*`, `figma_get_components`, `figma_get_text_styles`, DTCG-экспорт |
| Произвольный код | `figma_execute` — любой Plugin API в песочнице файла |
| Запись | `figma_create_*`, `figjam_create_*`, `figma_set_*`, `figma_apply_*` |

## Правила для агента

1. Файл/доска — живой документ команды и могут быть открыты у людей: читаем свободно, пишем только по явному запросу пользователя (создание/правка узлов, постинг комментариев, переменные).
2. Стикеры дизайнера — канвас-контент: читаются `figjam_get_board_contents` без токена. Нити комментариев — REST, требуют токен пользователя.
3. `figma_get_file_data` на большом файле возвращает весь документ — сначала `figma_get_selection` или снимок, документ — точечно по узлу.
4. Снимок для контекста — `figma_take_screenshot`; файлы попадают в temp-каталог сервера.

## Troubleshooting

- **`transport.active: none`** — плагин не запущен: `Plugins → Development → Figma Desktop Bridge` на открытом файле. Проверить `lsof -iTCP:9223 -sTCP:LISTEN` — сервер слушает только пока жив MCP-клиент/драйвер.
- **Плагин не коннектится** — `figma_reconnect`; закрыть и открыть плагин; конфликт порта — плагин сканирует 9223–9232, второй сервер займёт свободный.
- **Баннер обновления в плагине** — ре-import `manifest.json` из того же пути (Figma кеширует `code.js`/`ui.html`); нужно при смене пина версии.
- **`figd_` токены** — `mcp-server-figma`/`figma-developer-mcp` в пользовательских конфигах (`~/.config/zed/settings.json` → `context_servers`, `~/.cursor/mcp.json`, `~/.codeium/windsurf/mcp_config.json`) с просроченным токеном дают ошибку `Token has expired`: обновить PAT на figma.com → Settings → Personal access tokens или удалить сервер — канонический `figma-console` их не требует.
- **REST-инструменты** — задать `FIGMA_ACCESS_TOKEN` в env MCP-сервера своего клиента (не в `.cursor/mcp.json`): PAT со скоупами file content/comments/current user.
- **Офлайн** — `npx` тянет пакет при каждом холодном старте; `npm i -g figma-console-mcp@1.46.0` и `command: "figma-console-mcp"` в локальном конфиге снимают зависимость от сети.
