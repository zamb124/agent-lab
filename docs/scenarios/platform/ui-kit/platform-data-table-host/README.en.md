# Data Table Host

Platform component `platform-data-table-host`.

Grid for `FileCategory.DATA_TABLE` (`.sqlite`). Rows come from the office paging API; SQLite is never loaded in the browser.

Documentation status: **backlog**.

## Run tests

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-data-table-host/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-data-table-host/playwright.spec.py -v
```
