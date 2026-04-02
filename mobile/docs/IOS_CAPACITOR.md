# iOS: Capacitor (WKWebView + удалённый URL)

Публикация в App Store требует нативного бинарника. Оболочка загружает тот же production URL, что и браузер; бизнес-логика остаётся в репозитории платформы (`core/`, `apps/`).

## Предварительные условия

1. Production URL и PWA (`manifest`, `sw.js`, HTTPS) доступны так же, как для браузера (см. [`mobile/README.md`](../README.md)).
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

## App Store: Guideline 4.2 (не «просто сайт»)

Оболочка Capacitor загружает веб по `server.url`; для ревью Apple нужно показать ценность **приложения** как продукта.

**Минимальный набор для продуктовой заявки**

- [ ] Нативный **splash** / launch screen (бренд Humanitec).
- [ ] Работа **offline** на уровне ожиданий: показ [`/offline.html`](../../core/app/pwa_routes.py) или эквивалент при отсутствии сети.
- [ ] Экран **«О приложении»** или раздел настроек с версией, ссылками на Privacy Policy и поддержку.
- [ ] Описание в App Store явно перечисляет: чаты, звонки, CRM, агенты — то, что отличает клиент от «оболочки вокруг сайта».

**Технические напоминания**

- `Info.plist`: `NSCameraUsageDescription`, `NSMicrophoneUsageDescription` для WebRTC и голосовых.
- Прогон на физическом iPhone: Sync (звонок, сообщение, голосовое, файл).

## Universal Links (ссылка из Mail / Notes открывает приложение)

1. На сервере: **`GET https://<домен>/.well-known/apple-app-site-association`** — JSON без расширения (в репозитории: **`core/frontend/pwa/apple-app-site-association`**, отдаёт **`pwa_routes.py`**). Префиксы **`paths`** в файле должны совпадать с **`DEEPLINK_PATH_PREFIXES`** в **`core/frontend/static/lib/utils/platform-deeplink-paths.js`**.
2. В приложении: **`App.entitlements`** — **`com.apple.developer.associated-domains`**, значения **`applinks:humanitec.ru`** и при необходимости **`www.`** / другие продуктовые домены (файл в репо: **`mobile/ios/App/App/App.entitlements`**).
3. Плагин **`@capacitor/app`**: **`npm install`** в **`mobile/`**, **`npx cap sync ios`**. В веб-странице: **`platform-deeplink-init.js`** (подключение из **`app-loader.js`**) подписывается на **`appUrlOpen`** и делает **`location.assign`** на внутренний маршрут; фильтр URL — **`isInternalProductNavigationUrl`** в **`native-app-shell.js`**.
4. Проверка: [Apple App Search API Validation](https://search.developer.apple.com/appsearch-validation-tool/) или открытие ссылки из Notes на устройстве с установленной сборкой.

Ручной чеклист: сохранить ссылку **`https://humanitec.ru/join`** (или другой согласованный path) в Notes → по нажатию открывается приложение → в WebView загружается ожидаемый path.

## Пуши

Веб Push в установленной из App Store WKWebView-оболочке **не** эквивалентен Safari PWA; для фоновых уведомлений обычно нужны **APNs** и плагин (см. [`PUSH_PARITY_APNS.md`](PUSH_PARITY_APNS.md)).

## SSO / OAuth (вход перекидывает в Safari и сессия не в приложении)

По умолчанию WKWebView разрешает навигацию только в пределах origin приложения. Редирект на страницы провайдера (Google, Яндекс, GitHub) Capacitor на iOS обрабатывает как внешнюю навигацию и открывает **системный браузер**. Callback снова на `humanitec.ru` отрабатывает уже в Safari: cookie сессии оказываются там, а не в WebView приложения.

В [`capacitor.config.json`](../capacitor.config.json) задано **`server.allowNavigation`** — шаблоны **hostname** (как в документации Capacitor: `accounts.google.com`, `*.yandex.ru`, без `https://`), по которым переходы остаются **внутри WebView**. После успешного OAuth редирект на ваш `/auth/callback/...` снова в том же WebView, cookie сессии остаются в оболочке.

**Sign in with Apple через страницу в WebView** (не нативная кнопка `ASAuthorizationAppleIDButton`): в Developer обычно создают **Services ID** и ключ для веба, домен и return URL — это отдельно от диалога **Enable as a primary App ID** у capability **Sign in with Apple** на **App ID** приложения (тот вариант нужен для **нативного** SDK или группировки App ID). Для веб-флоу в WKWebView в `allowNavigation` должны быть **`appleid.apple.com`** и **`appleid.cdn-apple.com`** (JS-виджет Apple).

После правки конфига обязательно: `npx cap sync ios` и пересборка.

### Splash Screen при полной навигации (`location.assign`)

Плагин **`@capacitor/splash-screen`**: в веб-коде **`assignInNativeShell`** ([`native-app-shell.js`](../../core/frontend/static/lib/utils/native-app-shell.js)) перед внутренним переходом вызывает **`SplashScreen.show({ autoHide: false })`**, затем **`location.assign`**; на новой странице **`viewport-app-vh.js`** снимает слой через **`SplashScreen.hide()`** после **`DOMContentLoaded`** и двух **`requestAnimationFrame`**. Фон и поведение при старте — **`plugins.SplashScreen`** в [`capacitor.config.json`](../capacitor.config.json). Зависимость и vendor — как для **`@capacitor/app`** ([`mobile/README.md`](../README.md)).

Если конкретный провайдер всё равно требует только системный браузер (политика Google для embedded WebView), понадобится отдельный сценарий: ASWebAuthenticationSession / custom URL scheme или мост одноразового кода — это уже изменения в потоке авторизации, не только конфиг.

### Сессия после закрытия приложения

Сервер должен отдавать **`Set-Cookie`** с **`Max-Age`** (или **`Expires`**) для **`auth_token`** и **`session_id`**, согласованный с TTL JWT сессии (`TokenService.SESSION_EXPIRES` в репозитории). Куки **без** явного срока — это **session cookies**; в WKWebView сессия часто привязана к жизненному циклу процесса, и после свайпа приложения из переключателя задач куки могут пропасть — не потому что iOS «чистит все куки», а из‑за семантики session-cookie в WebKit.

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

Вёрстка общая с PWA и вебом: **`viewport-fit=cover`**, токены **`--platform-safe-*`** в **`core/frontend/static/assets/css/tokens.css`**, хедер страниц **`page-header`** со sticky и отступом под вырез, контейнер **`platform-island`** с нижним inset на мобилке, полноэкранный **`glass-modal`** без полей у overlay на fullscreen. В **`capacitor.config.json`** для iOS задано **`contentInset: "never"`** (safe area только из CSS, без дублирования от WKWebView). Подробнее — **`.cursor/rules/frontend.mdc`**, раздел «Высота вьюпорта» и safe area.

## Иконка приложения (Humanitec)

Единый знак с главной: **`core/frontend/static/assets/service_logos/frontend_logo.svg`** на фоне **`#1a1a2e`** (как **`background_color`** в PWA manifest). PNG для PWA: **`core/frontend/static/pwa/icons/`**; иконка App Store / Xcode: **`mobile/ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png`** (1024×1024).

Пересборка всех размеров после смены логотипа или фона:

```bash
cd /path/to/agent-lab
uv sync
uv run python scripts/generate_humanitec_pwa_icons.py
```

Зависимость генератора: **`skia-python`** (группа **`dev`** в `pyproject.toml`). После обновления **`AppIcon`** — снова **`npx cap sync ios`** при необходимости.

## Синхронизация после смены конфига

```bash
cd mobile
npx cap sync ios
```

## CocoaPods: `Pods-App.release.xcconfig` не найден

Каталог **`mobile/ios/App/Pods`** не коммитится; файлы появляются после **`pod install`**. Локально:

```bash
cd mobile && npm install
cd ios/App && pod install
```

Открывать **`App.xcworkspace`**, не `App.xcodeproj`.

**Xcode Cloud** (путь вида `/Volumes/workspace/repository/...`): в корне репозитория добавлен **`ci_scripts/ci_post_clone.sh`** — после клона выполняет `npm ci` в `mobile/` и **`pod install`** в `mobile/ios/App`. В настройках workflow должен быть выбран тот же репозиторий; при ошибке `npm ci` проверьте актуальность `package-lock.json`.

## Сборка: Sandbox deny на `Pods-App-frameworks.sh`

Если Xcode пишет `Sandbox: bash deny file-read-data` на скрипт из Pods — в проекте отключён песочный режим для user scripts: **Build Settings** → **User Script Sandboxing** → **No** (в репозитории для target App выставлено `ENABLE_USER_SCRIPT_SANDBOXING = NO` в `App.xcodeproj`).
