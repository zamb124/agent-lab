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

## SSO / OAuth (вход перекидывает в Safari и сессия не в приложении)

По умолчанию WKWebView разрешает навигацию только в пределах origin приложения. Редирект на страницы провайдера (Google, Яндекс, GitHub) Capacitor на iOS обрабатывает как внешнюю навигацию и открывает **системный браузер**. Callback снова на `humanitec.ru` отрабатывает уже в Safari: cookie сессии оказываются там, а не в WebView приложения.

В [`capacitor.config.json`](../capacitor.config.json) задано **`server.allowNavigation`** — шаблоны **hostname** (как в документации Capacitor: `accounts.google.com`, `*.yandex.ru`, без `https://`), по которым переходы остаются **внутри WebView**. После успешного OAuth редирект на ваш `/auth/callback/...` снова в том же WebView, cookie сессии остаются в оболочке.

После правки конфига обязательно: `npx cap sync ios` и пересборка.

Если конкретный провайдер всё равно требует только системный браузер (политика Google для embedded WebView), понадобится отдельный сценарий: ASWebAuthenticationSession / custom URL scheme или мост одноразового кода — это уже изменения в потоке авторизации, не только конфиг.

### Ошибки JS на `oauth.yandex.ru` / «уход в Safari» при входе

Стандартный User-Agent WKWebView отличается от Safari. Яндекс (и другие провайдеры) могут отдавать страницу OAuth, которая в WebView падает с **`SyntaxError`** на своих скриптах (в логах Capacitor будет URL вида `https://oauth.yandex.ru/authorize/allow`). В [`capacitor.config.json`](../capacitor.config.json) задано **`ios.overrideUserAgent`** — строка как у **Mobile Safari**; после изменения обязательно **`npx cap sync ios`**.

Если после этого провайдер всё равно ломает сценарий во встроенном браузере — остаётся только нативный OAuth (**ASWebAuthenticationSession** + callback на **custom URL scheme**, зарегистрированный в кабинете провайдера) или одноразовый код на бэке; это отдельная проектная задача.

### Логи Xcode / системы (часто не баг приложения)

- **`UIScene` lifecycle will soon be required** — предупреждение Apple: шаблон Capacitor до сих пор на классическом `AppDelegate` без Scene; отслеживать [обсуждение в Capacitor](https://github.com/ionic-team/capacitor/issues/7961). На работу WebView в обычной сборке обычно не влияет.
- **`Could not create a sandbox extension`**, **`unable to make sandbox extension`**, **`SOAuthorizationCoordinator`**, **`DownloadFailed`**, **`MDNS registration`**, **`WEBP` reader** — часто шум WebKit/системы на устройстве; не всегда связаны с вашим JS.

## Субдомены компаний (`slug.humanitec.ru`)

`server.url` задаёт один origin (например `https://humanitec.ru`). Ссылка на **`https://mycompany.humanitec.ru/...`** — это **другой host**, для Capacitor это не «тот же сайт», и iOS открывает **Safari**. В **`server.allowNavigation`** перечислены базовые домены и `*.домен` для тенантов. Сейчас: **`humanitec.ru` / `*.humanitec.ru`** и **`humanetic.ru` / `*.humanetic.ru`** (если компания ведёт на `system.humanetic.ru`, это другой registrable domain, чем `humanitec.ru` — без отдельной строки Capacitor снова откроет Safari). Любой новый корневой домен окружения добавляйте парами `apex` + `*.apex`.

Переходы на сервисы с дашборда и из меню пользователя не должны использовать **`window.open(..., '_blank')`** в нативной оболочке: на iOS это уводит в Safari. В веб-коде: **`openUrlSameWindowOrTab`** и глобальный перехват **`installNativeAppShellLinkCapture`** (клики по ссылкам внутри продукта и между поддоменами тенантов остаются в WebView; подключается из `viewport-app-vh.js` вместе с `app-loader`). Слушатель вешается **всегда**; признак оболочки проверяется **на клике**. Детекция натива: помимо PWA / `Capacitor.isNativePlatform`, в коде учитываются **`webkit.messageHandlers.bridge`** (iOS) и **`androidBridge`** (Android), как в `@capacitor/core` — иначе до полной инициализации `window.Capacitor` срабатывал `window.open` и открывался Safari.

Дополнительно **`installNativeAppShellWindowOpenPatch`** подменяет **`window.open`**: любой вызов с URL внутри продукта (тот же origin и тенанты) выполняется как **`location.assign`** в том же WebView — иначе сторонний код и `_blank` всё равно создают «новую вкладку» / внешний браузер. На Android (Capacitor или TWA) тот же JS.

**Нативный iOS (обязательно к сборке):** в Capacitor `WKUIDelegate.webView(_:createWebViewWith:...)` по умолчанию всегда вызывает **`UIApplication.shared.open`** (см. `WebViewDelegationHandler.swift` в Pods). Подкласс `CAPBridgeViewController` не может подменить `WebViewDelegationHandler`, потому что **`loadView` объявлен `final`**. В приложении подключён **`HumanitecWebViewNewWindowFix.swift`**: swizzle с сохранением оригинального IMP; для URL из **`server.allowNavigation`** и для префиксов **server URL / local URL** выполняется **`webView.load(request)`** в том же `WKWebView`. Установка в **`application(_:willFinishLaunchingWithOptions:)`** в `AppDelegate.swift` — до создания WebView. После смены `allowNavigation` — **`npx cap sync ios`**.

Логи **`SOAuthorizationCoordinator`** / **`sandbox extension`** часто идут от системы (Keychain, AutoFill, вложенные фреймы на страницах OAuth) и не всегда устраняются из JS.

## Safe area и shell (тот же веб, что в браузере)

Вёрстка общая с PWA и вебом: **`viewport-fit=cover`**, токены **`--platform-safe-*`** в **`core/frontend/static/assets/css/tokens.css`**, хедер страниц **`page-header`** со sticky и отступом под вырез, контейнер **`platform-island`** с нижним inset на мобилке, полноэкранный **`glass-modal`** без полей у overlay на fullscreen. Подробнее — **`.cursor/rules/frontend.mdc`**, раздел «Высота вьюпорта» и safe area.

## Синхронизация после смены конфига

```bash
cd mobile
npx cap sync ios
```

## Сборка: Sandbox deny на `Pods-App-frameworks.sh`

Если Xcode пишет `Sandbox: bash deny file-read-data` на скрипт из Pods — в проекте отключён песочный режим для user scripts: **Build Settings** → **User Script Sandboxing** → **No** (в репозитории для target App выставлено `ENABLE_USER_SCRIPT_SANDBOXING = NO` в `App.xcodeproj`).
