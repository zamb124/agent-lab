# Исходники пользовательской документации

Сборка: **`make doc`** — `scripts/check_scenario_docs_quality.py` → `scripts/docs_prepare.py` (деревья **`build/documentation-ru/`** и **`build/documentation-en/`**) → два прохода **`uv run --group docs zensical build`**. Артефакт: **`documentation-dist/`** (RU) и **`documentation-dist/en/`** (EN), раздача **`/documentation/`** и **`/documentation/en/`**.

## Разделы сайта

| Раздел | Источник |
|---|---|
| Home | `docs/index.md`, `docs/en/index.md` |
| **Начни отсюда** | генерируется из `docs/scenarios/taxonomy.yaml` → `start-here.md` |
| Быстрый старт | `docs/quickstart.md` |
| API | OpenAPI → `scripts/openapi_to_markdown.py` |
| Инструкции | `docs/scenarios/` + hub-страницы из taxonomy |

## Сценарии E2E → docs/scenarios

- Тесты пишут **`README.md`** / **`README.en.md`** ([`tests/ui/scenario_doc.py`](../tests/ui/scenario_doc.py)).
- Путь в репозитории: **`docs/scenarios/<service>/<tag>/<slug>/`**.
- Тег **`tag`** — группировка на hub-странице сервиса; в URL **нет** уровня tag: **`/documentation/scenarios/<service>/<slug>/`**.
- **`doc_slug`** задаётся маркером или из `nodeid` pytest; уникален внутри `service`.
- **`tag`** должен быть в [`docs/scenarios/taxonomy.yaml`](scenarios/taxonomy.yaml) — иначе CI падает.

После **`make test-ui`**: **`make doc`** или **`make test-ui-doc`**.

## Стиль инструкции (канон)

- Заголовок шага: **`## Шаг N. …`** (EN: **`## Step N. …`**).
- Минимум **2 шага** и **1 скриншот** на сценарий (`check_scenario_docs_quality.py`); для **Office** — **4–7** шагов на инструкцию (средний сценарий, не атомарный).
- Перед скриншотом: зачем этот шаг и что видно на экране (см. `sync-complete-guide`).
- Без непонятного жаргона; **`label_en`** обязателен у каждого `scenario.step`, если в маркере есть **`title_en`**.

## Taxonomy

[`docs/scenarios/taxonomy.yaml`](scenarios/taxonomy.yaml) — порядок сервисов, подписи тегов, `featured_slug`, learning paths для «Начни отсюда».

Новый сценарий:

1. Добавить `tag` в taxonomy (если новая тема).
2. E2E с `@pytest.mark.scenario(service=..., tag=..., doc_slug=...)`.
3. `make test-ui-doc`.
