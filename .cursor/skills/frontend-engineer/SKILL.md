---
name: frontend-engineer
description: "Frontend инженер Платформы: TypeScript strict + Lit 3 + EventBus + шесть фабрик, эталонная архитектура без фолбеков и замалчивания. Без задачи или по «проверь фронт / что не доделано / выровняй UI» — автономный рекурсивный цикл: discovery ui_audit → срез по приоритету → устранение корня → гейты → следующий срез, пока discovery не пуст; большой рефакторинг ради корня — норма. Использовать ВСЕГДА при правках core/frontend/static/lib/**, apps/*/ui/**, tests/frontend_core/**, tests/ui/design-system/**, core/i18n/translations/**, tsconfig*, scripts/build/ui.ts и UI-гейтов; при упоминании TypeScript, tsc, esbuild, ui-dist, Lit, PlatformElement, PlatformPage, PlatformApp, PlatformModal, PlatformFormModal, useResource, useOp, useForm, useCursorList, useFacets, useSlice, createAsyncOp, createResourceCollection, createCursorList, createFacets, createForm, createSlice, dispatch, EventBus, restMirror, transport='ws', commandType, modal, bottom sheet, sidebar, breadcrumbs, toast, platform-field, tokens.css, Figma, i18n; при ошибках tsc, check_ui_canon, check_ui_factories, check_field_canon, check_i18n_keys, check_core_frontend_canon, check_command_rest_mirror, check_ui_kit_docs, check_ui_kit_canon."
---

# Frontend Engineer

Процедура UI-работы и автономного выравнивания UI под эталон. Нормы — `frontend.mdc`, `ui_factories.mdc`, `ui_components.mdc`, `ui_fields.mdc` и правило домена; эталон, к которому сходится код, — `references/target-architecture.md`. Скил норм не пересказывает: он задаёт порядок работы и не даёт закрыть работу, пока код расходится с эталоном.

## Закон

1. **Эталон, а не «работает».** Код, который работает, но расходится с эталоном, — недоделка: она устраняется или называется в отчёте поимённо.
2. **Ноль фолбеков.** Отсутствие значения — `throw`; дефолт — только `initialSlice`/`extraInitial` фабрики (`main.mdc` § Запреты 1, 7).
3. **Ноль замалчивания.** `catch` без привязки, `console` вместо ошибки, `any` и каст вместо типа, exemption, pragma и allowlist вместо исправления, «мелочь» вне отчёта — запрещены.
4. **Корень, а не симптом.** Правка, упёршаяся в причину ниже по слоям (контроллер, фабрика, транспорт, сборка, гейт, правило), спускается к причине и устраняет её. Размер среза задаёт корень; большой рефакторинг, который убирает класс проблем, — норма.
5. **Hard cutover.** Старый путь удаляется в том же изменении: adapter, alias, shim, compat и «мост на переходный период» запрещены (`main.mdc` § Запреты 12, 14).
6. **Гейт, который врёт, хуже отсутствующего.** Гейт, сканирующий ноль файлов, слепой к `.ts` или прячущий находки исключением, чинится первым.
7. **Новое — в правило.** Новый паттерн, компонент, гейт или конвенция фиксируются в правиле-владельце в том же изменении (`main.mdc` § Принципы п.9, `rules.mdc`).

## Режимы

| Режим | Когда | Результат |
|---|---|---|
| `task` | конкретная задача UI | задача закрыта, долг не вырос, встреченный корень устранён или назван блокером |
| `audit` | запуск без задачи; «проверь фронт», «что не доделано», «выровняй UI», «наведи канон» | серия срезов, пока discovery не пуст |
| `gate` | слепой гейт, метрика без ratchet, норма `[без гейта]` | детектор видит `.ts`, падает на нарушении, счётчик зафиксирован |
| `rules` | UI-правило или этот скил расходятся с кодом | текст as-is по `rules.mdc` |

Пользователь назвал сервис, файл или класс нарушения — это граница discovery; иначе граница — весь UI и его инструменты (сборка, тесты, гейты, правила).

## Режим task

### Прочитать

| Задача | Что открыть |
|---|---|
| любая правка UI | `frontend.mdc`, правило домена сервиса (`crm.mdc`, `sync.mdc`, `flows.mdc`, `flow_ui.mdc`, `office.mdc`, `wiki.mdc`, `worktracker.mdc`, `stock.mdc`, `voice.mdc`, `mail.mdc`) |
| состояние, команда, push | `ui_factories.mdc`, `events.mdc`, `architecture.mdc` § REST-зеркало и § WS request-reply |
| модалка, sheet, навигация, core-компонент | `ui_components.mdc` + UIKDS-карточка `tests/ui/design-system/components/<tag>/` |
| поле формы | `ui_fields.mdc` |
| визуал, CSS, Figma | `references/design-standard.md`, `core/frontend/static/assets/css/tokens.css` |
| типы, фабрика, контроллер, сборка | `references/target-architecture.md` |

Код-источник перед нетривиальной правкой: `core/frontend/static/lib/platform-element/index.ts` (helpers), `core/frontend/static/lib/base/PlatformApp.ts` (статические поля SPA), `core/frontend/static/lib/base/use-resource.ts` (контроллеры), `core/frontend/static/lib/events/factories/` (контракт опций фабрик), `core/frontend/static/lib/events/factory-registry.ts` (реестр), `core/frontend/static/lib/events/contract.ts` (`CoreEvents`).

### Выбрать инструмент

1. Доменные данные — всегда фабрика: CRUD → `createResourceCollection`; лента с курсором → `createCursorList`; одиночная команда или объект → `createAsyncOp`; typeahead → `createFacets`; форма → `createForm` с `submitEvent`; состояние без сети → `createSlice`. Кейс не ложится — комбинация фабрик; седьмая фабрика и локальный store запрещены.
2. Транспорт: сервис из `COMMAND_WS_SERVICES` (`scripts/gates/backend/command_rest_mirror.py`) → `transport: 'ws'` + `wsTimeoutMs` + `restMirror`; имя фабрики ≠ команде backend → `commandType`.
3. UI-примитив — core UI Kit (`core/frontend/static/lib/components/`); не хватает возможности — расширяется core-компонент. Поле — `<platform-field>`.
4. Тип — из эталонного контракта (`references/target-architecture.md` § Типовой контракт); его нет в kit — это корень, а не повод для каста.

### Порядок

1. Backend-контракт: команда `<svc>/<entity>/<verb>_requested`, REST-зеркало, push через `register_platform_event` (скил `backend-engineer`).
2. Фабрика `apps/<svc>/ui/events/resources/<entity>.resource.ts` с типом элемента или результата → `recipes.md` § 1–7.
3. Ключи i18n парой ru/en → `recipes.md` § 12.
4. Регистрация в `static factories` `apps/<svc>/ui/app/<svc>-app.ts`, маршрут с `titleKey`.
5. Страница, модалка, компонент → `recipes.md` § 8–10.
6. Push и исходы мутаций — мерж в фабрике → `recipes.md` § 11.
7. Тесты `.ts`: reducer — unit, контроллер и компонент — WTR; новый `platform-*` — UIKDS-карточка → `recipes.md` § 15.
8. Правило-владелец — в том же изменении.

### Долг рядом с задачей

- Новый и изменённый код не добавляет находок `ui_audit.py` (сигнатуры, слепота, мосты) — сравнение до и после.
- Задаче нужна возможность kit, которой нет (generic-контроллер, wire-тип, слот компонента), — рекурсия в корень (§ Рекурсия), затем задача.
- Пользователь ограничил границу, а корень за её пределами — задача делается в лучшей форме без обхода (типизированная граница в фабрике: интерфейс + сужение в `mapItem` с `throw`), корень называется в отчёте как открытый срез. Каст, `any`, фолбек, exemption недопустимы ни в каком случае.

## Режим audit — рекурсивный цикл

Детали команд, классификации и отчёта — `references/loop.md`; сквозные срезы-корни — `references/playbooks.md`; классы нарушений и детекторы — `anti-patterns.md`.

```text
LOOP:
  0. preflight  git status --porcelain > /tmp/ui_preflight_status.txt; чужие правки не трогаются
  1. discovery  uv run python .cursor/skills/frontend-engineer/scripts/ui_audit.py --json /tmp/ui_audit_before.json
                + rules_drift.py + чтение кода находок
  2. срез       первый непустой приоритет P0..P6; одна причина — один срез
  3. контракт   печатается пользователю до первой правки
  4. детектор   есть и видит .ts → N; нет или слепой → сначала гейт (режим gate)
  5. правка     playbook класса; корень ниже по слоям → рекурсия
  6. проверка   детектор 0 в границе, гейты зелёные, ratchet --update вниз, тесты, визуал
  7. правило    факты среза as-is в правиле-владельце; скил — тоже
  8. отчёт      включая «Найдено и не исправлено»
  9. goto 1     пока discovery не пуст
```

### Приоритет срезов

1. **P0 — сломанный контроль.** Красный `make ui` или шаг `make lint`; гейт сканирует ноль файлов, ищет `.js`-маску или набор суффиксов без `.ts`; исключение или pragma прячет находку; `tsc` вне обязательного пути (`ui_audit` § Конвейер); метрика долга без ratchet; дрейф правила или скила, который ведёт агента к несуществующему коду.
2. **P1 — замалчивание в runtime.** Ошибка эффекта без `*_FAILED` своей операции; `catch` без привязки; `console` вместо ошибки; раздача без `ui-dist` не падает; литеральный фолбек в core.
3. **P2 — типовой контракт.** Негенерические фабрики и контроллеры, реестр без типов по имени, ручные wire-интерфейсы вместо генерации из Pydantic, события без карты типов; `any`, двойной каст и non-null как следствие.
4. **P3 — один источник.** Две копии Lit, shim, vendored-копии npm-пакетов, import map при бандле, мосты резолва, мёртвые артефакты миграции.
5. **P4 — канон слоёв UI.** Hard-правила `scripts/gates/frontend/ui_canon_rules.py`, zero-import, фабрики, модалки, поля, мерж push.
6. **P5 — тесты.** `.js`-тесты → `.ts`, тесты на том же Lit, что прод, раннеры без мостов.
7. **P6 — soft.** `hex_colors`, `window_listeners`, `manual_busy_state`, `innerhtml_raw`, `setinterval_poll`, нормы `[без гейта]`.

Внутри приоритета — сначала core (`core/frontend/static/lib/**`), потом сервисы по убыванию находок.

### Рекурсия

- Срез, который нельзя закрыть без изменения слоя ниже, кладётся на стек; открывается срез корня со своим контрактом и детектором; после его закрытия цикл возвращается к исходному срезу.
- Направление спуска: страница → компонент kit → контроллер → фабрика → транспорт и сборка → гейт → правило.
- Корень, затрагивающий сотни файлов (generic-реестр, wire-генерация, один Lit), ведётся серией шагов: каждый шаг оставляет `make ui` зелёным и ratchet не выше; runtime-адаптеров и дублирующих API нет; срез закрыт, когда корень устранён во всех потребителях.
- В один срез не смешиваются независимые корни.

### Контракт среза

```text
Срез: <класс> в <граница>. Корень: <где теряется правильность>.
Эталон: references/target-architecture.md § <раздел>; норма: <file>.mdc § <раздел>.
Инвариант: <одна проверяемая фраза>.
Детектор: <rule_id | гейт | проба ui_audit>; сейчас N.
```

## Гейты перед «готово»

```bash
make ui-typecheck                 # npx tsc -p tsconfig.json — 0 ошибок
make ui-build                     # esbuild → apps/<svc>/ui-dist/, core/frontend/embed-dist/
make lint-ts                      # tsc + check-events-canon + check_ui_kit_docs + field + ui kit canon + logging
make test-frontend-core           # канон core + vitest + WTR (включая UIKDS L1)
make ui                           # всё выше одной командой — эталонный гейт UI
uv run python -m scripts.gates.frontend.ui_kit_canon                              # ratchet hard-правил; --update только вниз
uv run python .cursor/skills/frontend-engineer/scripts/ui_audit.py       # дельта к preflight
```

- Затронут Python, скрипты гейтов или правила — `make lint`; все шаги без остановки — `uv run python .cursor/skills/refactor-engineer/scripts/gates_report.py /tmp/ui_gates`.
- Core UI Kit или модалка — `make test-ui-components`; UIKDS-сценарии и доки — `make ui-doc` (нужен `make test-up`).
- i18n — `make check-i18n`, `make check-i18n-keys`, `uv run python -m scripts.tools.report_ui_i18n_gaps --app <svc>`.

## Визуальная проверка

1. Свежий бандл: `make app` собирает UI до старта и держит процесс `ui_watch` (esbuild watch); `make app APP_KILL=1` — занятые порты.
2. URL: frontend `http://localhost:8002/`, flows `:8001/flows`, CRM `:8003/crm`, RAG `:8004/rag`, Sync `:8005/sync`, Documents `:8008/documents`, worktracker `:8021/worktracker`, wiki `:8023/wiki`, stock `:8026/stock`.
3. Desktop `1440x1024`; shell, страница или модалка — ещё mobile `390x844` или `430x932`: нет overlap, горизонтального скролла, обрезанного текста; ритм — `references/design-standard.md`.
4. Скриншоты до и после — в отчёте.

## Чек-лист «готово»

- [ ] `make ui` зелёный; Python или гейты затронуты — `make lint` зелёный или падения доказаны baseline.
- [ ] `ui_audit.py` после ≤ до по каждой секции в границе; новых находок нет.
- [ ] Нет `any`, `as unknown as`, non-null без контракта, `@ts-ignore`/`@ts-expect-error`/`@ts-nocheck`, `catch` без привязки, `console`, `||`/`??`-фолбеков в новом коде.
- [ ] Типы элемента и результата объявлены у фабрики; страница импортирует их `import type`, не переобъявляет.
- [ ] Новый `t('key')` есть в `core/i18n/translations/ru/<ns>.json` и `en/<ns>.json`; динамических ключей нет.
- [ ] Новая команда `_requested` имеет REST-зеркало; push не совпадает с командой по имени.
- [ ] Новая фабрика — уникальное `<svc>/<entity>` в `static factories`; компонент берёт её по имени.
- [ ] Модалка или sheet — `modalKind`/`bottomSheetKind` + регистрация, открытие helper-ом.
- [ ] Поля — `<platform-field>`; визуал — токены и core-компоненты; новый `platform-*` имеет UIKDS-карточку.
- [ ] Удалены старые пути, мосты, исключения; правило-владелец и скил отражают факты as-is.
- [ ] Отчёт содержит раздел «Найдено и не исправлено» (пустой — явно «нет»).

## Блокеры

Остановиться без обхода; дать доказательство и одно рекомендуемое решение:

- `rule_conflict` — нормы правил несовместимы для этого случая;
- `rule_change_required` — честное решение вводит новый общий канон UI;
- `kit_gap` — нужна возможность core, а пользователь ограничил границу; приложить контракт корневого среза;
- `external_contract` — форма зафиксирована внешней спекой (A2A, LiveKit, Capacitor);
- `infra_unavailable` — стек, браузер или сборка не поднимаются; срез не объявляется закрытым.

## Запреты процесса

- `any`, касты, non-null, `@ts-*`-подавления, `eslint-disable`, `catch` без привязки, `console` как обработка, `||`/`??`-фолбек ради зелёного прогона.
- Ослабление гейта, расширение allowlist, exemption и pragma, `--update` ratchet вверх, skip или удаление теста ради зелёного.
- Правки вне границы среза, форматирование чужих файлов; `git stash`, `git reset`, `git checkout -- <file>` чужих правок; коммит без просьбы пользователя.
- «Потом», `TODO`, «временно» в коде, комментариях и отчёте вместо исправления или блокера.
- Объявлять UI выровненным, пока `ui_audit.py` находит нарушения.

## Отладка

- `?platform_devtools=1` — лог каждого события и `window.__platformDevtools__ = { trail(), state(), dispatch(), clear() }` (`core/frontend/static/lib/events/devtools.ts`). Подсистемы пишут диагностику только через `devtoolsLog(scope, message, payload)` из того же файла; собственные флаги и `console.*` запрещены.
- `Argument of type '…' is not assignable to parameter of type 'FactoryNameOfKind<…>'` — имени нет в `PlatformFactoryRegistry` (у модуля фабрик нет блока `declare module`) или фабрика другого вида.
- `getFactory: factory "…" not registered` — фабрики нет в `static factories` приложения, где её берёт `use*`; `has kind "…", expected "…"` — не тот helper.
- `<Controller>.<action>: payload required (use null for empty events)` — действие вызвано без аргумента: пустое событие несёт `null`.
- `i18n key required (format "namespace:key")` — toast-ключ без namespace; `restMirror is required when transport='ws'` — у WS-фабрики нет `restMirror`; `commandType … must end with "_requested"` — неверный тип кадра.
- Шторм HTTP/WS после рендера — `run()` в `updated()`/`render()` без проверки `busy`/`error`/`lastResult`.
- `Multiple versions of Lit loaded` — модуль импортирует Lit не из npm `lit` → `references/playbooks.md` § Один Lit.
- Страница пустая после правки `.ts` — устаревший `apps/<svc>/ui-dist/`: процесс `ui_watch` в mprocs упал или не запущен; `make ui-build`.
- Сервис не стартует с `UI bundle is not built` или `embed bundles are not built` — нет сборки: `make ui-build`.
- Пустое место вместо иконки — имя без ассета: `tests/frontend_core/unit/utils/ui-icon-assets.spec.js`.

## Файлы скила

- `references/target-architecture.md` — эталон UI: toolchain, слои, типовой контракт, fail-closed, один источник.
- `references/loop.md` — рекурсивный цикл режима audit: команды, классификация, отчёт, стоп-условия.
- `references/playbooks.md` — сквозные срезы-корни: слепой гейт, ratchet, конвейер, один Lit, типизированный реестр, wire-типы, ошибка эффекта, тихий catch, тесты на TS.
- `anti-patterns.md` — класс нарушения → замена → детектор.
- `recipes.md` — рецепты задач на TS: фабрики, страница, модалка, sheet, push, i18n, upload, kit-компонент, конверсия в TS.
- `references/design-standard.md` — Figma → `tokens.css`.
- `.cursor/skills/frontend-engineer/scripts/ui_audit.py` — discovery одним прогоном.
