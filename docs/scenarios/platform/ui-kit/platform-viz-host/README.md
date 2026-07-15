# Viz Host

Платформенный компонент `platform-viz-host`.

Переключатель ECharts / Mermaid по document/openConfig. Входы: `.document` (VizDocument JSON), `.openConfig` с handler=viz, `.compact` для chat inline.

Статус документации: **backfill**.

## Запуск тестов

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-viz-host/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-viz-host/playwright.spec.py -v
```
