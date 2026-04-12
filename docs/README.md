# Исходники документации (Fumadocs)

- **`guides/`** — ручные страницы (в т.ч. `ru/`, `en/`).
- **`scenarios/`** — E2E: в репозитории хранятся **`README.md`**; перед сборкой `scripts/docs_prepare.py` создаёт **`index.mdx`** (в `.gitignore`) и манифест путей для Next.js.
- **`openapi/`** — спеки OpenAPI для будущего `fumadocs-openapi`.
- **`assets/`** — статика для контента.

Сборка: **`make doc`** из корня репозитория (или `npm run build` в `apps/documentation/`). Результат: **`documentation-dist/`** в корне репозитория, раздаётся на **`/documentation/`**.
