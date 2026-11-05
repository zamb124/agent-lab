# Виджет карты

Платформенный компонент `platform-map` — единая config-driven карта
(MapLibre + канонические geo-слои + TerraDraw), переиспользуемая во всех
SPA и embed-контекстах (wiki, tracker, flow-ui).

Статус документации: **backlog**.

## Запуск тестов

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-map/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-map/playwright.spec.py -v
```
