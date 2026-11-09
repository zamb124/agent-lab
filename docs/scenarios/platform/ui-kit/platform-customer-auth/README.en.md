# Customer Auth

Platform component `platform-customer-auth` — bottom sheet that authorizes a
customer by phone number. Providers, codes and fallback live in the core
`/…/public/customer-auth` router; the component only knows the shared contract.

Documentation status: **production**.

## Run tests

```bash
npm run test:ui-kit -- tests/ui/design-system/components/platform-customer-auth/contract.spec.js
uv run pytest tests/ui/design-system/components/platform-customer-auth/playwright.spec.py -v
```
