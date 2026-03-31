# Фаза 2 — готовность веба (чеклист)

## HTTPS и манифест

- [ ] `GET https://<host>/manifest.json` — 200, `Content-Type` соответствует манифесту.
- [ ] `GET https://<host>/sw.js` — 200 (см. [`core/app/pwa_routes.py`](../../core/app/pwa_routes.py)).

Локально: [`scripts/check-pwa-manifest-url.sh`](../scripts/check-pwa-manifest-url.sh) (нужен `PWA_MANIFEST_URL` в `mobile/.env`).

## Lighthouse CI

```bash
cd mobile
export PWA_LIGHTHOUSE_URL="https://humanitec.ru/"
./scripts/run-lighthouse-ci.sh
```

Или: `npm run pwa:lighthouse` (после `npm install`, с тем же env).

Пороги настроены в [`lighthouserc.cjs`](../lighthouserc.cjs); при необходимости ослабьте `minScore` для категории PWA до стабилизации продакшена.

## Tenant и `start_url`

См. [TENANT_START_URL.md](TENANT_START_URL.md).

## VAPID (публичный ключ)

Публичный endpoint без авторизации (см. `core/middleware/auth/route_config.py`):

- `GET /frontend/api/push/vapid-public-key`
- `GET /sync/api/push/vapid-public-key`
- и шаблон `/*/api/push/vapid-public-key` для других сервисов.

Проверка вручную:

```bash
curl -sS "https://humanitec.ru/frontend/api/push/vapid-public-key"
```

Ожидается JSON с полем `publicKey` (см. [`core/push/router.py`](../../core/push/router.py)).
