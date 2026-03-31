# Фаза 8 — регламент релизов магазинов

## Что обновляется только вебом

- UI, логика, исправления в `core/`, `apps/` — после деплоя на production подхватываются TWA и Capacitor **без** нового бинарника (пока не меняются нативный `applicationId`, signing, домен, критичные нативные плагины).

## Когда нужен новый билд

- Смена `package_name` / bundle id.
- Новые нативные разрешения (Info.plist / AndroidManifest).
- Обновление Capacitor / Bubblewrap / целевого SDK по требованию магазина.
- Добавление нативных плагинов (push, фон).

## Версионирование

- **Android:** монотонно увеличивать `versionCode`; `versionName` — по семантике продукта.
- **iOS:** `CFBundleShortVersionString` и `CFBundleVersion` — по правилам Apple.

## Мониторинг

- Краши веба: существующие инструменты проекта (при подключении Sentry или аналога — зафиксировать здесь ссылку).
- Нативные краши: Xcode Organizer / Play Console при появлении отчётов.

## CI

- Сборки с подписью только в защищённых ветках; секреты не в репозитории.
- См. [`.github/workflows/mobile-pwa-lighthouse.yml`](../../.github/workflows/mobile-pwa-lighthouse.yml) для необязательной проверки PWA по URL.
