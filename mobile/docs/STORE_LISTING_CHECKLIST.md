# Фаза 7 — карточки магазинов (чеклист)

**Источник правды в репозитории:** каталог [`../store-listing/`](../store-listing/) — тексты (`metadata/<locale>/*.txt`), скриншоты, загрузка в App Store Connect через [`../fastlane/`](../fastlane/) (`bundle exec fastlane upload_listing`). Подробности: [`../store-listing/README.md`](../store-listing/README.md).

## Общее

- [ ] Название и краткое имя согласованы с брендом.
- [ ] Описание на русском (и при необходимости английском) — правки в `store-listing/metadata/`, не только в веб-консоли.
- [ ] Скриншоты для телефона (и планшета для iPad, если таргет); iPhone 6.7": `uv run python mobile/scripts/capture_app_store_screenshots.py`.
- [ ] Иконка 512×512 и требования витрины выполнены.
- [ ] URL **Privacy Policy** и **Terms** актуальны и открываются публично.
- [ ] Категория приложения и возрастной рейтинг заполнены честно (чаты, звонки, обработка данных).

## Google Play

- [ ] Data safety / декларация сбора данных.
- [ ] AAB загружен, подпись release.

## Apple App Store

- [ ] App Privacy (nutrition labels) согласованы с фактическим сбором данных.
- [ ] IPA / архив из Xcode, версия и build number.

## Дополнительные витрины (RuStore, AppGallery, …)

- [ ] Отдельные требования модерации прочитаны и выполнены.
