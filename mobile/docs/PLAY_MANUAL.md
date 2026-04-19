# Google Play: что и где заполнять вручную (Android)

Конспект по экранам **Google Play Console**. Сборка AAB и подпись описаны в [`mobile/android/README.md`](../android/README.md). Тексты витрины и графика — в [`PLAY_HUMANITEC.md`](PLAY_HUMANITEC.md).

---

## 1. Аккаунт разработчика

| Шаг | Где | Что сделать |
|-----|-----|-------------|
| 1.1 | [play.google.com/console](https://play.google.com/console) | Войти под Google-аккаунтом владельца. |
| 1.2 | **Setup → Developer profile** | Заполнить контактные данные, согласиться с актуальной редакцией Google Play Developer Distribution Agreement. Для организации — `Account type: Organization` и проверка по документам. |
| 1.3 | **Setup → Payments profile** | Только если будут платные приложения / IAP. Для бесплатного клиента не обязательно. |

---

## 2. Создание приложения

| Шаг | Где | Что сделать |
|-----|-----|-------------|
| 2.1 | **All apps → Create app** | App name: `Humanitec`. Default language: `Russian`. App or game: `App`. Free or paid: `Free`. Согласиться с Developer Program Policies и US export laws. |
| 2.2 | После создания — слева раздел **Dashboard** показывает мастер «Get your app ready for review» | Шаги 3–7 ниже соответствуют пунктам этого мастера. |

---

## 3. App content (Setup → App content)

Это блок-список обязательных деклараций. Каждый пункт — отдельная страница.

| Подраздел | Ответ Humanitec |
|-----------|-----------------|
| **Privacy policy** | URL рабочей страницы политики на вашем домене (тот же, что в App Store Connect). |
| **App access** | `All or some functionality is restricted` → дать тестовый логин/пароль для ревью (Sign-in required). |
| **Ads** | `No, my app does not contain ads`. |
| **Content ratings** | Пройти анкету IARC. Платформа b2b/коммуникации — обычно `Everyone` / `3+`. |
| **Target audience and content** | Возрастная аудитория `13+` (или `18+` по соображениям B2B). Не отмечать «Appeal to children». |
| **News apps** | `No`. |
| **COVID-19 contact tracing and status apps** | `No`. |
| **Data safety** | Перечислить, какие данные собираются (аккаунт, сообщения, файлы, диагностика). Соответствовать политике конфиденциальности. |
| **Government apps** | `No, my app is not a government app`. |
| **Financial features** | `No, my app does not provide financial features`. |
| **Health** | `No`. |
| **Actions on Google** | `No`. |
| **Advertising ID** | `No, my app does not use advertising ID` (мы не показываем рекламу и не трекаем). |

---

## 4. Store presence → Main store listing

Поля и черновики текстов — [`PLAY_HUMANITEC.md`](PLAY_HUMANITEC.md). Кратко: App name, Short description (≤80), Full description (≤4000), категория, иконка 512×512 (`mobile/screens/play_icon_512.png`), Feature graphic 1024×500 (`mobile/screens/play_feature_graphic_1024x500.png`), screenshots (`mobile/screens/generated/play_*`), URL поддержки и e-mail.

---

## 5. Подпись и Play App Signing

| Шаг | Где | Что сделать |
|-----|-----|-------------|
| 5.1 | **Release → Setup → App signing** | По умолчанию активирован Play App Signing — Google управляет release-ключом. Согласиться. |
| 5.2 | **App signing key certificate (SHA-256)** | После первой загрузки AAB здесь появится **SHA-256 release-сертификата** — это значение нужно прописать в `core/frontend/pwa/assetlinks.json` (см. ниже). |
| 5.3 | **Upload key certificate (SHA-256)** | Тот же экран показывает SHA-256 upload-ключа, тоже добавить в `assetlinks.json` рядом с release-fingerprint. |

Локальный keystore (upload key) хранится в виде секрета (`*.jks`), пароли — в ENV `ANDROID_KEYSTORE_*` (см. [`mobile/android/README.md`](../android/README.md)).

---

## 6. App Links (Digital Asset Links)

| Шаг | Где | Что сделать |
|-----|-----|-------------|
| 6.1 | На сервере | На каждом **апексном** домене (`humanitec.ru`, `humanetic.ru`, `agents-lab.ru`) должен отдаваться `GET https://<host>/.well-known/assetlinks.json` с `Content-Type: application/json`. Этого достаточно: для wildcard-хостов из [`AndroidManifest.xml`](../android/app/src/main/AndroidManifest.xml) (`*.humanitec.ru` и т.д.) Android (API 31+) берёт `assetlinks.json` с апекса, отдельный файл на каждом slug-поддомене **не нужен**. Бэкенд платформы делает это через [`core/app/pwa_routes.py`](../../core/app/pwa_routes.py) условно — если файл `core/frontend/pwa/assetlinks.json` присутствует. |
| 6.2 | `core/frontend/pwa/assetlinks.json` | По шаблону [`assetlinks.json.example`](../../core/frontend/pwa/assetlinks.json.example): `package_name = ru.humanitec.app`, в `sha256_cert_fingerprints` — **оба** fingerprint из п. 5.2 (upload + app signing). На каждом из трёх апексов нужен свой `/.well-known/assetlinks.json` с тем же содержимым. |
| 6.3 | **Release → Setup → Deep links** | После релиза Play Console сам проверяет статус verification по каждому хосту, включая wildcard-домены. Если статус `Failed`, проблема обычно в недоступности `assetlinks.json` на апексе или в опечатке fingerprint. Проверка вручную: [Statement List Generator](https://developers.google.com/digital-asset-links/tools/generator). |

---

## 7. Internal testing → закрытое тестирование

| Шаг | Где | Что сделать |
|-----|-----|-------------|
| 7.1 | **Testing → Internal testing → Create new release** | Загрузить AAB (`mobile/android/app/build/outputs/bundle/release/app-release.aab`). Указать **release notes**. |
| 7.2 | **Testers** | Создать список email тестеров, поделиться opt-in URL. |
| 7.3 | **Review release → Start rollout to internal testing** | После проверки полей — выкатить. |

---

## 8. Production release

| Шаг | Где | Что сделать |
|-----|-----|-------------|
| 8.1 | **Production → Create new release** | Прикрепить тот же AAB (или новый билд). Release notes на ru/en. |
| 8.2 | **Countries / regions** | Выбрать страны распространения. |
| 8.3 | **Send for review** | После заполнения мастера Dashboard и устранения warning'ов — отправить на ревью. Среднее время — несколько дней. |

---

## 9. Частый порядок действий

1. Аккаунт + Developer profile (п. 1).
2. Create app (п. 2).
3. Загрузить **первый AAB** в **Internal testing** (без Play App Signing fingerprint в Console работа невозможна).
4. Получить SHA-256 (Play App Signing + Upload key) из **Release → Setup → App signing** (п. 5.2).
5. Сформировать `core/frontend/pwa/assetlinks.json` (п. 6.2), задеплоить на все домены.
6. Заполнить App content (п. 3), Main store listing (п. 4), Data safety, Content rating.
7. Production release → Send for review (п. 8).

Точные названия пунктов меняются; ориентир — [Google Play Console help](https://support.google.com/googleplay/android-developer/).
