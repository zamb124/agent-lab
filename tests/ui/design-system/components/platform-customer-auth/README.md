# Customer Auth

Платформенный компонент `platform-customer-auth` — лист авторизации покупателя
по номеру телефона. Провайдеры, коды и fallback — на стороне core-роутера
`/…/public/customer-auth`; компонент знает только общий контракт.

Статус документации: **production**.

## Запуск тестов

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-customer-auth/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-customer-auth/playwright.spec.py -v
```
