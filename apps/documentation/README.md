# Fumadocs (Humanitec)

Контент в корневом каталоге репозитория **`docs/`** (`source.config.ts` → `../../docs`).

Перед сборкой выполняется **`../../scripts/docs_prepare.py`** (prebuild): сценарии `docs/scenarios/**/README.md` → **`index.mdx`**, манифест **`generated/doc-paths.json`** для `generateStaticParams`.

- Сборка: из корня репозитория **`make doc`** или здесь **`npm run build`**.
- Статический вывод: **`out/`**; в монорепо копируется в **`documentation-dist/`**.
- Dev: **`npm run dev`** — открыть **`http://127.0.0.1:3000/documentation/`** (задан `basePath`).
