# platform-mail-modal

Платформенный компонент `platform-mail-modal` (`modalKind=platform.mail`).

## Settings overlay

- Sticky header: title + icon close (`platform-icon name="close"`, `aria-label` = `settings_close`).
- Секции: **Мои ящики** (все members) → **Ящики компании** + create/bind (admin) → **Почтовый сервер** (admin).
- Назначение сотрудника на существующий адрес — `POST /bindings` (backend reassign).
- Отвязка — `platformConfirm`, затем `BINDING_DELETE_REQUESTED`.
- Чтение писем переключается аватарами rail, не из settings (`settings_reading_hint`).

## Запуск

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-mail-modal/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-mail-modal/playwright.spec.py -v
```
