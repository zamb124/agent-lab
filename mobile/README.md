# Сборки магазинов (Android TWA / iOS)

Каталог **`mobile/`** — артефакты и инструкции для упаковки PWA платформы в приложения магазинов. **Бизнес-логика и UI остаются в веб-коде** (`core/frontend/`, `apps/*/ui/`); здесь только оболочки, конфиги, скрипты и документация по процессу.

## Связь с репозиторием

| Компонент | Где в репозитории |
|-----------|-------------------|
| Манифест, SW, offline | [`core/frontend/pwa/`](../core/frontend/pwa/) |
| Digital Asset Links (опционально) | `core/frontend/pwa/assetlinks.json` — `GET /.well-known/assetlinks.json` ([`pwa_routes.py`](../core/app/pwa_routes.py)), шаблон [`assetlinks.json.example`](../core/frontend/pwa/assetlinks.json.example) |
| Маршруты `/manifest.json`, `/sw.js` | [`core/app/pwa_routes.py`](../core/app/pwa_routes.py) |
| Клиент PWA (SW, VAPID push) | [`core/frontend/static/services/pwa.service.js`](../core/frontend/static/services/pwa.service.js) |

## Документация процесса

- **[Полный waterfall (фазы, ворота, артефакты)](docs/WATERFALL.md)** — единственный источник правды по этапам проекта магазинов.
- [Фаза 1 — инициация](docs/PHASE1_INITIATION.md) · [РФ / учётки](docs/RU_OPS_ACCOUNTS.md)
- [Фаза 2 — чеклист PWA](docs/PHASE2_PWA_CHECKLIST.md) · [Tenant / start_url](docs/TENANT_START_URL.md)
- [App Store 4.2](docs/APP_STORE_4_2.md) · [Push APNs roadmap](docs/PUSH_PARITY_APNS.md)
- [QA матрица](docs/QA_MATRIX_TEMPLATE.md) · [Карточки магазинов](docs/STORE_LISTING_CHECKLIST.md) · [Релизы](docs/RELEASE_REGIMEN.md)
- [Android TWA](android/README.md) — Trusted Web Activity, Bubblewrap, `assetlinks.json`.
- [iOS / Capacitor](docs/IOS_CAPACITOR.md) — WKWebView, удалённый URL, App Store 4.2.
- [Digital Asset Links на сервере](config/well-known-assetlinks-README.md)

## Быстрый старт (инструменты)

```bash
cd mobile
npm install
./scripts/check-pwa-manifest-url.sh
```

Переменные окружения: скопировать [`config/env.example`](config/env.example) в `mobile/.env` и выставить `PWA_MANIFEST_URL`.

Дальше — по фазам из `docs/WATERFALL.md` и README в `android/` / `ios/`.

## Структура каталога

```
mobile/
  docs/WATERFALL.md
  docs/PHASE*.md …
  lighthouserc.cjs
  capacitor.config.json
  android/README.md
  docs/IOS_CAPACITOR.md
  config/env.example
  config/capacitor.config.json.example
  config/assetlinks.json.template
  scripts/check-pwa-manifest-url.sh
  scripts/run-lighthouse-ci.sh
  scripts/init-twa.sh
  scripts/build-twa.sh
  www/index.html
  package.json
```

## Секреты

Ключи подписи, профили Apple, JSON сервис-аккаунта Play **не хранятся в git**. Шаблон переменных: [`config/env.example`](config/env.example).

В GitHub для workflow Lighthouse: секрет **`PWA_LIGHTHOUSE_URL`** (см. [`.github/workflows/README.md`](../.github/workflows/README.md)).
