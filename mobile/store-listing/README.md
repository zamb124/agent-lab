# Витрина App Store / Google Play — текст и скриншоты из репозитория

Здесь **источник правды** для описаний и файлов витрины: правки в git, затем загрузка в App Store Connect через **fastlane** (или копирование вручную). Так не нужно хранить уникальные формулировки только в веб-интерфейсе Apple.

## Структура

| Путь | Назначение |
|------|------------|
| `metadata/copyright.txt` | Копирайт (одна строка, общий для локалей) |
| `metadata/<locale>/` | Локаль: `ru`, `en-US`, … |
| `metadata/<locale>/*.txt` | Поля витрины (см. ниже) |
| `metadata/<locale>/screenshots/` | Скриншоты iPhone для этой локали |

Имена файлов совместимы с **fastlane deliver** / `upload_to_app_store`.

### Текстовые поля (iOS)

| Файл | Ограничение | Пример |
|------|-------------|--------|
| `name.txt` | до 30 символов | Название приложения |
| `subtitle.txt` | до 30 символов | Подзаголовок |
| `description.txt` | до 4000 | Полное описание |
| `keywords.txt` | до 100 символов, через запятую | Ключевые слова (без пробелов после запятых — по правилам Apple) |
| `promotional_text.txt` | до 170 | Промо-текст (можно менять без релиза) |
| `release_notes.txt` | | «Что нового» для отправленной версии |
| `support_url.txt` | URL | Поддержка |
| `marketing_url.txt` | URL | Маркетинг (опционально) |
| `privacy_url.txt` | URL | Политика конфиденциальности |

Категории, возрастной рейтинг, подписи In-App Purchase при первом выпуске часто задают один раз в App Store Connect; при необходимости их можно дописать в fastlane позже.

### Скриншоты iPhone (6.7")

Apple требует набор для **6.7"** (например **1290 × 2796** px, портрет). Скрипт сохраняет файлы с именами, которые ожидает fastlane, в:

`metadata/<locale>/screenshots/iPhone 15 Pro Max-<n>.png`

Список URL и порядок кадров задаются в `mobile/scripts/capture_app_store_screenshots.py`.

## Генерация скриншотов в CI / локально

Требуется Chromium для Playwright (один раз): `uv run playwright install chromium`.

```bash
cd /path/to/agent-lab
export STORE_SCREENSHOT_BASE_URL="https://humanitec.ru"
export STORE_SCREENSHOT_LOCALE="ru"
uv run python mobile/scripts/capture_app_store_screenshots.py
```

Переменные:

| Переменная | По умолчанию | Назначение |
|------------|----------------|------------|
| `STORE_SCREENSHOT_BASE_URL` | `https://humanitec.ru` | Базовый URL продукта |
| `STORE_SCREENSHOT_LOCALE` | `ru` | Подкаталог `metadata/<locale>/screenshots/` |
| `STORE_SCREENSHOT_HEADED` | (пусто) | Если `1` — браузер с окном (отладка) |

Скриншоты большие — при необходимости подключите Git LFS.

## Загрузка метаданных и скриншотов в App Store Connect

1. Установить Ruby и bundler, в каталоге `mobile/fastlane`: `bundle install`.
2. Выдать **ключ API** App Store Connect (роль Developer или Admin) и сохранить `.p8` вне репозитория.
3. Задать переменные окружения (или `.env` в `mobile/fastlane/`, не коммитить):

   - `APP_STORE_CONNECT_KEY_ID`
   - `APP_STORE_CONNECT_ISSUER_ID`
   - `APP_STORE_CONNECT_KEY_PATH` — путь к `.p8`

4. Выполнить:

```bash
cd mobile/fastlane
bundle exec fastlane upload_listing
```

Чтобы **не** перезаписывать скриншоты в ASC (только текст):

```bash
SKIP_SCREENSHOTS=1 bundle exec fastlane upload_listing
```

Подробнее: **`../fastlane/README.md`**.

## Google Play

Формат Google Play отличается (XML/HTML, другие размеры скриншотов). Для единого источника текста можно дублировать ключевые блоки из `metadata/ru/description.txt` в `fastlane supply` или в консоль Play вручную; отдельный автоматический поток можно добавить позже.
