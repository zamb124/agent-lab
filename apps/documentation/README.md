# Fumadocs (Humanitec)

Контент в корневом каталоге репозитория **`docs/`**. В `source.config.ts` путь к `docs/` задаётся так, чтобы работал и исходный файл в `apps/documentation/`, и сгенерированный **`.source/source.config.mjs`** (иначе коллекция MDX пустая и все страницы — 404).

Тема оформления: **`app/global.css`** подключает **`fumadocs-ui/css/aspen.css`** (+ `preset.css`). Другие готовые темы в пакете: `neutral`, `catppuccin`, `dusk`, `ocean`, `vitepress`, `shadcn` (для `shadcn` нужны переменные `--background` и т.д., см. их `css/shadcn.css`).

Язык интерфейса доков: **`RootProvider` → `i18n`** (как у темы через `next-themes`): переключатель в сайдбаре, предпочтение в **`localStorage`** (`humanitec-documentation-locale`), навигация между `guides/ru/...` и `guides/en/...`. Сценарии без EN-ветки при смене языка ведут на корень `guides/{locale}/`.

Перед сборкой выполняется **`../../scripts/docs_prepare.py`** (prebuild): сценарии `docs/scenarios/**/README.md` → **`index.mdx`**, манифест **`generated/doc-paths.json`** для `generateStaticParams`.

- Сборка: из корня репозитория **`make doc`** или здесь **`npm run build`**.
- Статический вывод: **`out/`**; в монорепо копируется в **`documentation-dist/`**.
- Dev: **`npm run dev`** — открыть **`http://127.0.0.1:3000/documentation/`** (задан `basePath`).
- В `lib/source.ts` **`baseUrl` loader’а = `/`**: префикс `/documentation/` даёт только Next `basePath`; иначе ссылки и prefetch уходят на `/documentation/documentation/...`.
- В `next.config.mjs` **`experimental.clientRouterFilter: false`**: при `output: 'export'` и `basePath` у Next бывает ложное срабатывание Bloom-filter и клиентская навигация удваивает префикс в URL.
- Индекс поиска: **`components/search.tsx`** → `GET` **`/documentation/api/search`** (константа `docPublicBasePath` в `lib/shared.ts`, должна совпадать с `basePath`).
