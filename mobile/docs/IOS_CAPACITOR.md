# iOS: Capacitor (WKWebView + удалённый URL)

Публикация в App Store требует нативного бинарника. Оболочка загружает тот же production URL, что и браузер; бизнес-логика остаётся в репозитории платформы (`core/`, `apps/`).

## Предварительные условия

1. Закрыта **Фаза 2** из [`WATERFALL.md`](WATERFALL.md).
2. macOS: установлен **полный Xcode** из App Store (не только Command Line Tools). В терминале: `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`, затем `xcodebuild -version`.
3. **CocoaPods**: `brew install cocoapods` (или `gem install cocoapods`). После `cap add ios` / `cap sync ios` при ошибке pod выполните: `cd ios/App && pod install`.
4. В **`mobile/`**: `npm install`.

## Инициализация (первый раз)

Capacitor требует `webDir`: в репозитории уже есть минимальный [`../www/index.html`](../www/index.html) (заглушка под remote URL).

Конфиг: [`../capacitor.config.json`](../capacitor.config.json). Пример без прод-URL: [`../config/capacitor.config.json.example`](../config/capacitor.config.json.example).

```bash
cd mobile
npx cap add ios
npx cap sync ios
npx cap open ios
```

## Обязательные доработки в Xcode

- **Signing & Capabilities:** команда разработчика, bundle id.
- **Info.plist:** `NSCameraUsageDescription`, `NSMicrophoneUsageDescription` (и при необходимости для файлов/фото) — тексты на языке пользователя.
- **Guideline 4.2:** нативный splash, экран настроек/«О приложении», офлайн-поведение — см. [`APP_STORE_4_2.md`](APP_STORE_4_2.md) и WATERFALL.

## Пуши

Веб Push в установленной из App Store WKWebView-оболочке **не** эквивалентен Safari PWA; для фоновых уведомлений обычно нужны **APNs** и плагин (см. [`PUSH_PARITY_APNS.md`](PUSH_PARITY_APNS.md)).

## Синхронизация после смены конфига

```bash
cd mobile
npx cap sync ios
```
