# Switch

Platform component `platform-switch`.

The hit area covers both the toggle and its `label`: clicking the label flips the
state, like a native `<label>`. There is a single `change` event with
`detail.value`.

Documentation status: **backfill**.

## Run tests

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-switch/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-switch/playwright.spec.py -v
```
