# Playbooks — сквозные срезы-корни

Playbook устраняет класс находок целиком, а не отдельное место. Шаги обязательны и идут по порядку; критерий «закрыт» проверяется детектором. Конкретные файлы находит `.cursor/skills/frontend-engineer/scripts/ui_audit.py` — playbook их не перечисляет. Порядок между playbooks задаёт приоритет `../SKILL.md` § Приоритет срезов; зависимость одного корня от другого разрешает рекурсия.

## Слепой гейт → зрячий

Признак: `ui_audit.py` § Слепота или § Скрытое; гейт печатает «OK», но сканирует ноль файлов, `.js`-маску, набор суффиксов без `.ts` или освобождает файлы исключением.

1. Для гейта выписать, какие файлы он обязан видеть (раздел «Гейты» правила-владельца) и какие видит сейчас.
2. Маски, имена и пути — на фактические `.ts`; наборы суффиксов — с `.ts`; резолверы `js_or_ts` удалить, путь указать как есть.
3. Самопроверка гейта: пустой набор сканируемых файлов или отсутствующий ожидаемый файл — падение с именем гейта.
4. Прогнать гейт: нарушения, накопленные за время слепоты, исправляются в этом срезе; больше одного среза — ratchet и отдельный срез.
5. Exemption и pragma удалить; принципиальное исключение существует только как `Исключение:` в правиле-владельце со ссылкой на allowlist гейта.

Закрыт: § Слепота и § Скрытое пусты для гейта; гейт падает на подложенном нарушении.

## Метрика → ratchet

Признак: soft-правило `ts_*` или другая метрика долга растёт без гейта.

1. Сигнатура точная: выборка из 20 находок без ложных; неточная — сначала уточняется.
2. `severity="hard"` в `scripts/gates/frontend/ui_canon_rules.py`; `uv run python -m scripts.gates.frontend.ui_kit_canon --update` фиксирует текущее число.
3. Норма — в правило-владельца (`frontend.mdc` для типов, фолбеков и замалчивания) с гейтом `scripts/gates/frontend/ui_kit_canon.py`.

Закрыт: рост метрики роняет `make lint-ts`.

## Конвейер toolchain

Признак: `ui_audit.py` § Конвейер — FAIL.

| Пункт | Исправление |
|---|---|
| tsc в lint-ts | цель `ui-typecheck` в рецепте `lint-ts` (`mk/lint.mk`) |
| tsc в Docker | `npm run typecheck:ui` в стадии `ui-builder` (`Dockerfile`) до `npm run build:ui` |
| сборка в make app, test-up, doc | `ui-build` — предпосылка целей `app` (`mk/app.mk`), `test-up` (`mk/test.mk`) и `doc` (`Makefile`: `extract_openapi.py` импортирует приложения) |
| watch в make app | процесс `ui_watch` (`npm run watch:ui`) в `mprocs.yaml` и `scripts/dev/run.py`; watch-режим `ui.ts` не удаляет `ui-dist` и `embed-dist` — сервисы уже раздают их |
| сборка в GPU-образе | стадия `ui-builder` в `Dockerfile.gpu`, как в `Dockerfile` |
| granian на исходниках | маунты на `apps/<svc>/ui-dist`; `/static/core/lib` → `core/frontend/embed-dist` до `/static/core` в `scripts/dev/run.py`, `deploy/helm/agent-lab/values.yaml`, `templates/50-gpu/litserve.yaml`; отсутствующий маунт в `run.py` — ошибка |
| `make lint <file>.ts` | ветка `*.ts)` в `lint-file` и `%.ts` в `LINT_PATH_GOALS` (`mk/lint.mk`) |
| раздача без ui-dist | `resolve_ui_static_dir` и `mount_core_frontend` (`core/app/spa.py`) бросают с подсказкой `make ui-build`; ветки возврата исходников нет |

`scripts/build/ui.ts` в том же срезе: одна точка входа `index.ts` и падение при её отсутствии, `gitSha` без значения `'unknown'`.

Закрыт: все пункты § Конвейер — OK; `make lint-ts` падает на подложенной ошибке типа.

## Один Lit

Признак: § Мосты — «shim Lit», «импорт vendored-копии npm-пакета», «import map при бандле», «переписывание vendored-путей при сборке»; WTR печатает `Multiple versions of Lit loaded`.

1. Импорты Lit — `from 'lit'` и `from 'lit/directives/<name>.js'`; `lit-shim` удаляется вместе со всеми импортами на него.
2. Embed-автолоады собираются самодостаточно в `core/frontend/embed-dist/`: проверка, требовавшая относительных vendored-путей в замыкании embed, и `exempt_in_embed_closure` удаляются; вместо них — проверка собранного embed-бандла на отсутствие голых спецификаторов.
3. Import map в `apps/*/ui/index.html`, в HTML, который отдаёт `core/app`, и в `web-test-runner.config.ts` удаляется; WTR резолвит npm `lit`.
4. Переписывание vendored-путей в `scripts/build/ui.ts`, vendored-копии Lit, `marked`, `centrifuge` и их записи в precache `core/frontend/static/lib/pwa/sw.ts` удаляются; DOMPurify и прочие — тем же шагом, если пакет есть в npm.
5. `frontend.mdc`, `testing.mdc`, `flow_ui.mdc` — as-is.

Закрыт: § Мосты без Lit-пунктов; в логе `make test-frontend-core-browser` нет `Multiple versions of Lit`.

## Типизированный реестр фабрик

Признак: `use*` возвращает негенерический контроллер; страницы кастуют результат `use*`, `event.payload`, `lastResult`; `ts_explicit_any` и `ts_type_assertion` в `apps/**`.

1. Фабрики generic (`target-architecture.md` § Типовой контракт п.3): параметры типа, литеральные имена событий, `mapItem: (raw: unknown) => TItem`, без явного `sliceKey` в опциях.
2. Контроллеры generic (п.5): без индекс-сигнатуры действий, `select(...).value: T`.
3. `PlatformFactoryRegistry` и module augmentation в каждом `*.resource.ts`; `use*` выводит тип контроллера из имени.
4. Статическая конфигурация баз типизирована (п.10).
5. Серия по потребителям: core-фабрики → сервисы по убыванию находок; в каждом — типы элементов, удаление кастов и `any` страниц, `--update` ratchet.
6. Тесты фабрик и контроллеров — на типизированных фабриках.

Закрыт: в `apps/**` нет каста результата `use*`; `ts_explicit_any`, `ts_type_assertion`, `ts_double_cast` в границе — 0; `tsc` — 0.

## Wire-типы из Pydantic

Признак: интерфейсы payload и результата написаны руками; формы данных переобъявлены в страницах.

1. Генератор в `scripts/` читает `<SVC>_OPERATIONS` (payload и тип возврата `op_*`), каталог `register_platform_event` и `response_model` REST-зеркал; Pydantic JSON Schema → TS. Библиотека выбирается по документации (context7); зрелый генератор предпочтительнее самописного эмиттера.
2. Выход — `apps/<svc>/ui/events/wire.gen.ts` и `core/frontend/static/lib/wire/<domain>.gen.ts`, карты `CommandMap` и `PlatformEventMap`.
3. Режим `--check` в `make lint`; ручная правка `*.gen.ts` запрещена.
4. Фабрики и страницы берут типы из wire-модуля; ручные интерфейсы удаляются.
5. Норма — в `frontend.mdc` и `ui_factories.mdc`; прецедент механизма проверки дрейфа — `scripts/generate/flow_ui_schema_fixture.py --check`.

Закрыт: смена поля Pydantic-модели без регенерации роняет `make lint`, после регенерации — `tsc` в местах использования.

## Ошибка эффекта → `*_FAILED`

Признак: шина ловит исключение эффекта и шлёт событие без потребителя; операция остаётся `busy`, пользователь видит вечный спиннер.

1. Исключение в effect фабрики превращается в `*_FAILED` этой фабрики с `causation_id` запроса — в коде фабрики, а не литералом в шине.
2. Ошибка видна: toast через `formatPlatformError` (`core/frontend/static/lib/utils/platform-error-message.ts`) и запись в devtools.
3. Тест фабрики: effect бросает → `run()` резолвит `null`, `busy` снят, `error` заполнен.

Закрыт: литеральных событий ошибки вне `CoreEvents` нет; тест зелёный.

## Тихий catch и фолбек → исключение

Признак: `ts_silent_catch`, `ts_literal_fallback`, `ts_console`, хелперы вида `stringOr(value, fallback)`.

1. Для каждого места выяснить, какой контракт гарантирует значение. Гарантирует — фолбек удаляется. Не гарантирует — контракт чинится в источнике: `initialSlice`, wire-тип, `mapItem` с `throw`.
2. `catch {}` → `catch (err)` с `instanceof` и `*_FAILED` или `throw new Error(msg, { cause: err })`; teardown — по машине состояний.
3. «Пусто» на экране — явная ветка шаблона по типу значения, а не `|| ''`.

Закрыт: сигнатуры в границе — 0.

## Тесты на TS

Признак: `ui_js_files` в `tests/**`; § Мосты — «мост резолва тестового раннера», «подмена внутренностей плагина».

1. Конверсия по `../recipes.md` § 16: `*.spec.js` → `*.spec.ts`, `tests/frontend_core/helpers/**` → `.ts`.
2. `web-test-runner.config.ts`, `vitest.config.ts`, `package.json`: маски `.spec.ts`; мосты резолва удаляются.
3. `scripts/gates/frontend/ui_kit_docs.py` и `ui_components.mdc` § UI Kit Documentation System — `contract.spec.ts`; `testing.mdc` § UI-тесты — as-is.
4. Тесты исполняются на npm `lit` (§ Один Lit).

Закрыт: `ui_js_files` в `tests/**` — 0; § Мосты без раннерных пунктов; `make test-frontend-core` зелёный.
