# Fumadocs (Humanitec)

Контент в корневом каталоге репозитория **`docs/`**. В `source.config.ts` путь к `docs/` задаётся так, чтобы работал и исходный файл в `apps/documentation/`, и сгенерированный **`.source/source.config.mjs`** (иначе коллекция MDX пустая и все страницы — 404).

## Тема оформления

**`app/global.css`** подключает **`fumadocs-ui/css/catppuccin.css`** (+ `preset.css`) — мягкие цвета, популярна в dev-сообществе, есть светлая и тёмная версии.

Другие готовые темы в пакете: `neutral`, `aspen`, `dusk`, `ocean`, `vitepress`, `purple`, `emerald`, `shadcn` (для `shadcn` нужны переменные `--background` и т.д., см. их `css/shadcn.css`).

## Язык (i18n)

**Fumadocs i18n** (настроен в `lib/source.ts`):
- **`parser: 'dir'`** — ожидается структура `{locale}/guides/...` и `{locale}/scenarios/...`
- **`languages: ['ru', 'en']`**, **`defaultLanguage: 'ru'`**
- **`hideLocale: 'default-locale'`** — URL `/` для русского, `/en/...` для английского

**Переключатель языка** появляется в сайдбаре автоматически (через `RootProvider` → `i18n`). Выбор сохраняется в **`localStorage`** (`humanitec-documentation-locale`).

**Структура контента:**
```
docs/
├── ru/
│   ├── guides/...       # Руководства на русском
│   └── scenarios/...    # Сценарии (RU)
└── en/
    ├── guides/...       # Руководства на английском
    └── scenarios/...    # Сценарии (EN, пока копия RU)
```

**URL (с учётом basePath `/documentation`):**
- `/documentation/` — главная (редирект на `/documentation/ru/`)
- `/documentation/ru/` — корень русской документации (можно `/documentation/`, т.к. ru по умолчанию)
- `/documentation/en/` — корень английской документации
- `/documentation/en/guides/...` — английские руководства
- `/documentation/en/scenarios/...` — английские сценарии
- `/documentation/ru/guides/...` — русские руководства (можно без `/ru/`: `/documentation/guides/...`)
- `/documentation/ru/scenarios/...` — русские сценарии

Перед сборкой выполняется **`../../scripts/docs_prepare.py`** (prebuild): сценарии `docs/scenarios/**/README.md` → **`index.mdx`**, манифест **`generated/doc-paths.json`** для `generateStaticParams`.

- Сборка: из корня репозитория **`make doc`** или здесь **`npm run build`**.
- Статический вывод: **`out/`**; в монорепо копируется в **`documentation-dist/`**.
- Dev: **`npm run dev`** — открыть **`http://127.0.0.1:3000/documentation/`** (задан `basePath`).
- В `lib/source.ts` **`baseUrl` loader’а = `/`**: префикс `/documentation/` даёт только Next `basePath`; иначе ссылки и prefetch уходят на `/documentation/documentation/...`.
- В `next.config.mjs` **`experimental.clientRouterFilter: false`**: при `output: 'export'` и `basePath` у Next бывает ложное срабатывание Bloom-filter и клиентская навигация удваивает префикс в URL.
- Индекс поиска: **`components/search.tsx`** → `GET` **`/documentation/api/search`** (константа `docPublicBasePath` в `lib/shared.ts`, должна совпадать с `basePath`).
