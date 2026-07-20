# platform-mail-modal

Platform component `platform-mail-modal` (`modalKind=platform.mail`).

## Settings overlay

- Sticky header: title + icon close (`platform-icon name="close"`, `aria-label` = `settings_close`).
- Sections: **My mailboxes** (all members) → **Company mailboxes** + create/bind (admin) → **Mail server** (admin).
- Assigning a member to an existing address uses `POST /bindings` (backend reassign).
- Unbind uses `platformConfirm`, then `BINDING_DELETE_REQUESTED`.
- Reading mail switches via rail avatars, not settings (`settings_reading_hint`).

## Run

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-mail-modal/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-mail-modal/playwright.spec.py -v
```
