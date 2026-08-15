# Data Table Host

Платформенный компонент `platform-data-table-host`.

Сетка для `FileCategory.DATA_TABLE` (`.sqlite`). Строки приходят с office paging API; SQLite в браузер не загружается.

Статус документации: **backlog**.

## Запуск тестов

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-data-table-host/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-data-table-host/playwright.spec.py -v
```
