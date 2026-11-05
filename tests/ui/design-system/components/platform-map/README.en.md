# Platform map widget

Platform component `platform-map` — single config-driven map widget
(MapLibre + canonical geo layers + TerraDraw) reused across all SPAs and
embed contexts (wiki, tracker, flow-ui).

Documentation status: **backlog**.

## Run tests

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-map/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-map/playwright.spec.py -v
```
