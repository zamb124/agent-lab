# Field Shell

Платформенный компонент `platform-field-shell` — единая pill-обёртка поля:
floating label с notch в бордере (`<fieldset>`/`<legend>`), фокус-ринг,
hint и error-сообщение. Внутри него живут `<platform-field>` и core-виджеты
полей; приложения рендерят его напрямую только для кастомных контролов.

Статус документации: **production**.

## Запуск тестов

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-field-shell/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-field-shell/playwright.spec.py -v
```
