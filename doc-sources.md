# Исходники пользовательской документации

Сборка: **`make doc`** — `scripts/gates/repo/scenario_docs_quality.py` → `scripts/docs/prepare.py` (деревья **`build/documentation-ru/`** и **`build/documentation-en/`**) → два прохода **`uv run --group docs zensical build`**. Артефакт: **`documentation-dist/`** (RU) и **`documentation-dist/en/`** (EN), раздача **`/documentation/`** и **`/documentation/en/`**.

Логотип документации — тот же файл, что у SPA: `core/frontend/static/assets/service_logos/frontend_logo.svg`. `docs_prepare` копирует его в `docs/assets/logo.svg` при каждой сборке (zensical `logo` / `favicon`).

**Ask AI:** грузит `/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js` и session API `/frontend/api/public/docs-assistant/session`. Работает только там, где есть mount платформы (`/documentation/` на frontend или `make doc-serve` → `scripts/docs/dev_server.py`). Голый `zensical serve` (`make doc-serve-zensical`) отдаёт HTML на `/static/core/*` → MIME error у module script.

## Разделы сайта

| Раздел | Источник |
|---|---|
| Home | `docs/index.md`, `docs/en/index.md` |
| **Начни отсюда** | генерируется из `docs/scenarios/taxonomy.yaml` → `start-here.md` |
| Быстрый старт | `docs/quickstart.md` |
| API | OpenAPI → `scripts/docs/openapi_to_markdown.py` |
| Инструкции | `docs/scenarios/` + hub-страницы из taxonomy; **sidebar** — основной путь навигации |

## Навигация инструкций

- **Sidebar (primary):** `scripts/docs/prepare.py` публикует инструкции как плоские `scenarios/<service>/<slug>.md` (не `slug/index.md`) и пишет `.pages` с titled leaves (`"Title": slug.md`). Так Zensical не делает из каждой папки отдельное меню. UI Kit — секция тега с hub `ui-kit/index.md` (`navigation.indexes`) и плоским списком компонентов.
- **Hub-страницы (secondary):** `scenarios/index.md`, `scenarios/<service>/index.md` — обзорные карточки; прямые ссылки на инструкции, без единственного tag-hub-only маршрута.
- Zensical: `navigation.indexes` — кликабельный заголовок секции на hub; **без** `navigation.expand` (секции свёрнуты, кроме активной ветки).

## Локали документации

- RU: `/documentation/`; EN: `/documentation/en/`.
- Ссылки из SPA: `core/frontend/static/lib/utils/documentation-url.js` — locale-aware (`state.i18n.locale`).
- `platform-help-hint` с `docHref` автоматически подставляет `/documentation/en/` при locale `en`.

## Сценарии E2E → docs/scenarios

- Тесты пишут **`README.md`**, **`README.en.md`** и PNG рядом с ними ([`tests/ui/scenario_doc.py`](../tests/ui/scenario_doc.py)).
- Путь в репозитории: **`docs/scenarios/<service>/<tag>/<slug>/`**.
- Имя PNG: **`<slug>--<номер>-<понятное-имя>.png`**. Смысловая часть задаётся через `scenario.step(..., screenshot_name="...")`; каталог `screenshots/` запрещён.
- Тег **`tag`** — группировка на hub-странице сервиса; в URL **нет** уровня tag: **`/documentation/scenarios/<service>/<slug>/`**.
- **`doc_slug`** задаётся маркером или из `nodeid` pytest; уникален внутри `service`.
- **`tag`** должен быть в [`docs/scenarios/taxonomy.yaml`](scenarios/taxonomy.yaml) — иначе CI падает.

После **`make test-ui`**: **`make doc`** или **`make test-ui-doc`**.

## SEO-артефакты документации

`scripts/docs/seo_postbuild.py` (в цепочке `make doc` после `postprocess`, а также в Dockerfile docs-builder): `index.md`-зеркала рядом с каждым `index.html`, `link[alternate type=text/markdown]`, TechArticle+Breadcrumb JSON-LD, `<lastmod>` в `sitemap.xml` (git-история → mtime источника). LLM получает исходный markdown по URL страницы + `/index.md`; корневой `/llms.txt` ссылается на docs `llms.txt`/`llms-full.txt`.

## Блог

Источник — `blog/<slug>.md` + `blog/<slug>.en.md` (YAML-шапка: `title`, `summary`, `date`, `updated`, `author`, `tags`, `draft`). Сборка — `python -m scripts.seo.blog_build` (часть `make ui-build`/`seo-build`) → `seo-dist/`: статические страницы постов с BlogPosting JSON-LD и hreflang, `body.html` для `/api/public/blog/post`, `index.json` (каталог + sitemap-blog), `feed.xml`. Правила канона — `.cursor/rules/seo.mdc`.

### Качество скриншотов (норма)

- Браузерный контекст e2e: **viewport 1440×900, `device_scale_factor=2`** → desktop PNG **2880×1800**
  (`tests/ui/conftest.py::_new_browser_context`, тот же кадр, что у marketing shots).
- Мобильный сценарий задаёт `set_viewport_size` явно (390×844 → PNG ~780×1688).
- Gate предупреждает о PNG с «@1x-подобной» шириной (901–2499px) — признак устаревшего или неверного контекста.
- Видимый контент — реалистичные демо-данные (названия, имена, фото), а не сырые `unique_id` на кадрах.
- Каждая новая инструкция проходит self-review на портале: страница открывается, все PNG осмотрены глазами,
  инструкция находится из sidebar-меню и поиском портала, карточка видна на hub сервиса.

## Стиль инструкции (канон)

- Заголовок шага: **`## Шаг N. …`** (EN: **`## Step N. …`**).
- Авторский стандарт — **4–7 шагов** на инструкцию; технический gate дополнительно проверяет наличие PNG, плоское размещение и формат имени.
- Перед скриншотом: зачем этот шаг и что видно на экране (см. `sync-complete-guide`).
- У каждого шага обязательны понятный `details` и короткий `screenshot_name`, описывающий состояние на снимке.
- Без непонятного жаргона.
- **EN обязателен:** у `@pytest.mark.scenario` — `title_en` и `description_en`; у каждого `scenario.step` — `label_en`; если есть `details=` — также `details_en`.
- После правок EN-метаданных без E2E: `uv run python -m scripts.docs.regenerate_scenario_readme_en`.

## Taxonomy

[`docs/scenarios/taxonomy.yaml`](scenarios/taxonomy.yaml) — порядок сервисов, подписи тегов, `featured_slug`, learning paths для «Начни отсюда».

Новый сценарий:

1. Добавить `tag` в taxonomy (если новая тема).
2. E2E с `@pytest.mark.scenario(service=..., tag=..., doc_slug=...)`.
3. `make test-ui-doc`.
