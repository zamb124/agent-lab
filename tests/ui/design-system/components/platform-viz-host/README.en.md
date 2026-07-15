# Viz Host

Platform component `platform-viz-host`.

Switch ECharts / Mermaid by document/openConfig. Inputs: `.document` (VizDocument JSON), `.openConfig` with handler=viz, `.compact` for chat inline.

Documentation status: **backfill**.

## Run tests

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-viz-host/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-viz-host/playwright.spec.py -v
```
