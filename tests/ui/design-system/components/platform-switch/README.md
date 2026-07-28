# Switch

Платформенный компонент `platform-switch`.

Зона нажатия — тумблер и подпись `label`: клик по подписи переключает состояние,
как у нативного `<label>`. Событие одно — `change` с `detail.value`.

Статус документации: **backfill**.

## Запуск тестов

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-switch/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-switch/playwright.spec.py -v
```
