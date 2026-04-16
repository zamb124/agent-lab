# Исходники пользовательской документации

Сборка: **`make doc`** — `scripts/docs_prepare.py` (деревья **`build/documentation-ru/`** и **`build/documentation-en/`**) затем два прохода **`uv run --group docs zensical build`** с конфигами **[`zensical.ru.toml`](zensical.ru.toml)** и **[`zensical.en.toml`](zensical.en.toml)**. Артефакт: **`documentation-dist/`** (RU) и **`documentation-dist/en/`** (EN), раздача **`/documentation/`** и **`/documentation/en/`**.

- **`docs/scenarios/`** — канонические сценарии E2E: тесты пишут **`README.md`** / **`README.en.md`** ([`tests/ui/scenario_doc.py`](tests/ui/scenario_doc.py)); в репозитории путь всегда **`docs/scenarios/<service>/<tag>/<slug>/`**, тег по умолчанию **`general`**. В **`build/documentation-ru/`** и EN-сборке уровень **`general` опускается**: сценарии попадают в **`…/scenarios/<service>/<slug>/`**, остальные теги остаются как **`…/<service>/<tag>/<slug>/`**. Каталог **`slug`** задаётся маркером **`doc_slug`** или из `nodeid` pytest. **`index.md`** в `build/` генерируется из README (в репозитории под `docs/scenarios/**/index.md` файлы не создаются). На уровнях **service** и не-`general` **tag** при сборке пишется краткий **`index.md`** со списком дочерних сценариев.
- **`docs/guides/`** — обзорные страницы (русский корень).
- **`docs/en/index.md`**, **`docs/en/guides/`** — английский хаб и гайды (без зеркала `docs/en/scenarios` в репозитории).
- **`docs/openapi/`**, **`docs/assets/`** — вспомогательные файлы (копируются в оба дерева сборки при наличии).

После **`make test-ui`** при необходимости выполните **`make doc`** (или **`make test-ui-doc`**) чтобы обновить статический сайт.
