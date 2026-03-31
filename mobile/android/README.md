# Android: Trusted Web Activity (TWA)

Рекомендуемый путь для Google Play и совместимых витрин (Amazon, часть сценариев Huawei): приложение-минимум, контент с сайта, поведение как в Chrome.

## Предварительные условия

1. Production URL и PWA на том же хосте, что будет в TWA (см. [`mobile/README.md`](../README.md)).
2. Установлен JDK 17+, Android SDK (через Android Studio или command-line tools).
3. В корне **`mobile/`**: `npm install`.

## Digital Asset Links

На **том же origin**, что у `start_url` в манифесте, по **HTTPS** должен быть доступен файл:

`https://<ваш-домен>/.well-known/assetlinks.json`

Используйте шаблон [`../config/assetlinks.json.template`](../config/assetlinks.json.template). Значения:

- `package_name` — `applicationId` из Gradle после `bubblewrap init`.
- `sha256_cert_fingerprints` — отпечаток **ключа подписи release** (не debug).

**Платформа:** заполненный JSON можно положить в `core/frontend/pwa/assetlinks.json` (шаблон — `assetlinks.json.example` рядом). Маршрут `GET /.well-known/assetlinks.json` регистрируется только если файл есть (в git по умолчанию не коммитится — см. корневой `.gitignore`); на деплое файл копируют в образ/том вместе с конфигом. `Content-Type: application/json`.

Проверка: [Google Digital Asset Links](https://developers.google.com/digital-asset-links/tools/generator) или [Statement List Generator](https://developers.google.com/digital-asset-links/tools/generator).

**Пример для nginx**

```nginx
location = /.well-known/assetlinks.json {
    add_header Content-Type application/json;
    alias /var/www/static/assetlinks.json;
}
```

Инфраструктура может монтировать файл иначе — главное: стабильный URL и корректный JSON.

## Инициализация проекта TWA

Рабочий каталог для Gradle-проекта не коммитится целиком — генерируется локально или в CI.

Из корня `mobile/` (нужен `PWA_MANIFEST_URL` в `.env` или в окружении):

```bash
npm run twa:bootstrap
```

Или вручную: [`scripts/init-twa.sh`](../scripts/init-twa.sh).

Далее следовать интерактивным вопросам Bubblewrap (package name, app name, ключ и т.д.). Документация: [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap).

## Сборка

После `bubblewrap init` из корня `mobile/`:

```bash
npm run twa:build:project
```

Или в каталоге проекта:

```bash
cd android/twa-project
npx bubblewrap build
```

Артефакты: AAB/APK в выходных каталогах Gradle (см. вывод `bubblewrap build`).

## Обновление только веба

После публикации TWA обновления UI/логики на сайте подхватываются без пересборки APK, пока не меняются `package_name`, signing и требования к asset links.

## Альтернатива

[PWABuilder](https://www.pwabuilder.com/) — генерация TWA с веб-интерфейса; результат тот же класс приложений.
