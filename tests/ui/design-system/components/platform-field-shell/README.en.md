# Field Shell

Platform component `platform-field-shell` — the single pill wrapper for a
field: floating label with a real border notch (`<fieldset>`/`<legend>`),
focus ring, hint and error message. It hosts `<platform-field>` and the core
field widgets; apps render it directly only for custom controls.

Documentation status: **production**.

## Running tests

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-field-shell/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-field-shell/playwright.spec.py -v
```
