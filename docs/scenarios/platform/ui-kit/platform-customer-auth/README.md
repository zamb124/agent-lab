# Customer Auth

Платформенный компонент `platform-customer-auth` — лист авторизации покупателя
по номеру телефона. Провайдеры, коды и fallback — на стороне core-роутера
`/…/public/customer-auth`; компонент знает только общий контракт.

Статус документации: **production**.

Тема листа: атрибут `theme="light|dark|auto"` (default `auto`). `auto` берёт
унаследованный `color-scheme` витрины (forced-тема страницы), иначе
`prefers-color-scheme`. Акцент — `--accent`/`--on-accent` хост-страницы,
палитра переопределяется custom properties `--pca-*`.

## Запуск тестов

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-customer-auth/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-customer-auth/playwright.spec.py -v
```
