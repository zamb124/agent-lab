# Multi-brand (primary apex: linnex.io)

После добавления `linnex.io` зарегистрируйте callback URL на apex **каждого** brand-домена.
Primary deployment apex — **linnex.io**; humanitec.ru остаётся legacy brand.

## Yandex OAuth

- `https://humanitec.ru/auth/callback/yandex`
- `https://linnex.io/auth/callback/yandex`

## Google OAuth

- `https://humanitec.ru/auth/callback/google`
- `https://linnex.io/auth/callback/google`

## GitHub OAuth

- `https://humanitec.ru/auth/callback/github`
- `https://linnex.io/auth/callback/github`

## Apple Sign-In

- Service ID / Return URLs для `app.linnex.io` (отдельно от `app.humanitec.ru`)
- Associated Domains: `linnex.io`, `*.linnex.io`

## YooMoney (billing)

- `https://humanitec.ru/frontend/api/billing/yoomoney/callback`
- `https://linnex.io/frontend/api/billing/yoomoney/callback`

## amoCRM (если используется)

- Redirect URI на обоих apex по тому же шаблону, что и Yandex.

После регистрации проверьте login flow на `https://linnex.io/login` и на tenant `https://{slug}.linnex.io`.
