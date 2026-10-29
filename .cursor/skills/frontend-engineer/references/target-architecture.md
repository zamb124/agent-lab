# Эталон UI (north star)

Эталон — одна правильная форма на каждую задачу UI. Каждый срез измеряется им: код, который расходится с эталоном, — недоделка, даже если он работает. Нормы, уже закреплённые в правилах, здесь не пересказываются — даётся ссылка; то, чего ещё нет в коде, описано как целевая форма, к которой ведёт срез из `playbooks.md`. Срез, доведший часть эталона до кода, переносит её норму в правило-владельца (`rules.mdc`).

## Toolchain — одна цепочка

| Звено | Эталон |
|---|---|
| Язык | TypeScript strict для всего UI-кода и UI-тестов (`tsconfig.base.json`); исключение — файл, который рантайм обязан грузить отдельным URL (AudioWorklet), и он собирается отдельной точкой входа esbuild из `.ts` |
| Строгость | `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `verbatimModuleSyntax`, `useDefineForClassFields`; целевой набор дополняют `exactOptionalPropertyTypes`, `noImplicitReturns`, `noPropertyAccessFromIndexSignature`, `noUnusedLocals`, `noUnusedParameters` — каждый флаг включает срез, который доводит `tsc` до 0 |
| Импорт | относительный `./x.js` для файла `x.ts` (TS ESM); core — `@platform/lib/...`; npm — голый спецификатор (`lit`, `lit/directives/*`, `marked`, `centrifuge`); резолв `.js → .ts` задают tsconfig, esbuild и vite, сторонних резолверов нет |
| Сборка | `scripts/build/ui.mjs`: esbuild на сервис → `apps/<svc>/ui-dist/` (entry `index.js` + hashed chunks), embed-автолоады → самодостаточные `core/frontend/embed-dist/`; модули страниц, которые строит backend (flow-ui host и `import` UIKDS-манифестов), — `buildPageModules` в тот же `embed-dist` с общими chunk-ами; точка входа одна — `index.ts`; переписывания путей при сборке нет |
| Раздача | сервис отдаёт только `ui-dist`, `/static/core/lib` — только `embed-dist`; нет бандла — процесс падает при старте с подсказкой `make ui-build`; import map в `index.html` нет |
| Dev | `make app` поднимает esbuild watch вместе с сервисами; правка `.ts` видна после перезагрузки страницы |
| Test | `make test-up` собирает UI до старта стека; Vitest и WTR исполняют `.ts` на том же npm `lit`, что прод, без резолв-мостов |
| CI и образ | Docker `ui-builder` выполняет `tsc` и сборку; `make lint-ts` включает `tsc` |
| Гейты | каждый UI-гейт сканирует `.ts` и падает, если набор сканируемых файлов пуст; долг типов — ratchet-правила `scripts/gates/frontend/ui_canon_rules.py`, baseline только вниз |

## Слои — зависимости сверху вниз

```text
apps/<svc>/ui/**                         композиция: pages, modals, components, routes, static factories
  │ import type ↓ (runtime-импорт фабрик запрещён, фабрика — по имени)
apps/<svc>/ui/events/resources/*.resource.ts   фабрики сервиса: options + типы элемента/результата
  │
core/frontend/static/lib/events/**       шина, фабрики, эффекты, транспорт, реестр — generic-контракт
  │
core/frontend/static/lib/components/**   kit platform-* (поля — components/fields/)
  │
core/frontend/static/lib/styles/shared/**  css-модули паттернов
  │
core/frontend/static/assets/css/tokens.css  единственный источник значений
  │
wire-типы (*.gen.ts)                     генерируются из Pydantic-моделей владельца
```

Запрещённые направления: lib → apps, components → конкретика сервисов и фабрик, shared-стили → компонентные стили, значения в обход `tokens.css`, `apps/<a>/ui` → `apps/<b>/ui` (`frontend.mdc` § Инварианты).

## Типовой контракт

Цель — ноль `any`, ноль `as` (кроме `as const`), ноль non-null: тип доходит от Pydantic-модели backend до шаблона Lit без потери.

1. **Wire-типы генерируются.** Payload и результат каждой команды из `<SVC>_OPERATIONS` (`Operation(payload_model, fn)` и тип возврата `op_*`), payload каждого push из `register_platform_event` (`core/events/registry.py`) и response REST-зеркала генерируются в TS из тех же Pydantic-моделей — `apps/<svc>/ui/events/wire.gen.ts` для сервиса, `core/frontend/static/lib/wire/<domain>.gen.ts` для домена core. Генератор имеет режим `--check`; дрейф — падение `make lint`. Ручной интерфейс wire-формы — дубль модели (`main.mdc` § Запреты 13).
2. **Карты контракта.** Генератор выдаёт `CommandMap` (`'<svc>/<entity>/<verb>_requested'` → `{ payload, result }`) и `PlatformEventMap` (тип push → payload). `CoreEvents` (`core/frontend/static/lib/events/contract.ts`) дополняет карту UI-событий; литерал типа вне карт — ошибка компиляции.
3. **Фабрики generic.** `createResourceCollection<TItem>`, `createAsyncOp<TPayload, TResult>` (из `CommandMap` по `commandType`), `createCursorList<TItem, TFilters>`, `createForm<TDraft>`, `createSlice<TState, TActions>`, `createFacets<TFacets>`. `mapItem: (raw: unknown) => TItem` — единственная точка сужения ответа; отсутствие обязательного поля — `throw`. Имена событий фабрики — литеральные типы, не `Record<string, string>`; явный `sliceKey` в опциях отсутствует (`ui_factories.mdc` § Имена).
4. **Реестр типизирован по имени.** `PlatformFactoryRegistry` (`core/frontend/static/lib/events/factory-registry.ts`) — пустой интерфейс, который каждый `*.resource.ts` расширяет module augmentation: `'<svc>/<entity>': typeof <factory>`. `useResource(name)`, `useOp(name)` и остальные helpers выводят тип контроллера из имени; незарегистрированное имя или имя чужого вида — ошибка компиляции; дубль имени с другим типом — ошибка компиляции. Страница не импортирует модуль фабрики — zero-import сохраняется.
5. **Контроллеры generic.** `ResourceController<TItem>` (`items: readonly TItem[]`), `OpController<TPayload, TResult>` (`run(payload: TPayload): Promise<TResult | null>`, `lastResult: TResult | null`), `CursorListController<TItem, TFilters>`, `FormController<TDraft>`, `SliceController<TState, TActions>` с типизированными методами действий; индекс-сигнатуры `[action: string]: unknown` нет; `select(...).value` имеет тип `T`, без `| undefined`.
6. **События типизированы.** `useEvent(type, handler)` и `extraReducer` получают payload из карты по литералу типа; разбор `event.payload as X` отсутствует.
7. **DOM без кастов.** Kit объявляет свои события в `HTMLElementEventMap` (`'change': CustomEvent<{ value: T }>`); `event.target` сужается `instanceof`-проверкой с `throw`; `querySelector<T>` — generic.
8. **`unknown` только на границе.** `httpRequest`, `ws.effect.ts`, `JSON.parse`, storage, `postMessage`, внешний SDK — `unknown`, сужаемый сразу в typed boundary; внутрь системы `unknown` и индекс-сигнатуры не проходят.
9. **Типы страницы.** Страница, модалка, компонент берут доменные типы `import type` из wire-модуля или фабрики; локальное переобъявление формы данных запрещено.
10. **Статическая конфигурация баз типизирована.** `PlatformApp`, `PlatformElement`, `PlatformModal`, `PlatformBottomSheet` объявляют свои статические поля (`factories`, `bottomNavItems`, `platformAssistant`, `defaultI18nNamespace`, `i18nNamespace`, `modalKind`, `bottomSheetKind`) с точными типами; наследник пишет `static override`; чтение через `this.constructor as <Ctor>` и `unknown[]` отсутствуют.

## Ошибки и fail-closed

1. **Эффект упал — операция провалилась.** Исключение в effect фабрики даёт `*_FAILED` этой операции с `meta.causation_id` запроса: контроллер резолвит `run()`, `busy` снимается, ошибка показывается через `formatPlatformError` (`core/frontend/static/lib/utils/platform-error-message.ts`) и видна в devtools. Событие ошибки без потребителя и литерал вне `CoreEvents` запрещены.
2. **`catch` с привязкой и классом.** `catch (err)` сужает `instanceof HttpError | WsTransportError | DOMException | SyntaxError` и диспатчит `*_FAILED` или пробрасывает `new Error(msg, { cause: err })`; прочее всплывает. `catch {}` и `catch { /* noop */ }` отсутствуют (`ui_factories.mdc` § Запрет фолбеков).
3. **Teardown по состоянию.** Освобождение WebAudio, MediaStream, WebSocket, observer идёт по явной машине состояний (что открыто — то закрывается); `try { x.close() } catch {}` не нужен и отсутствует.
4. **`console` — не обработка.** Ошибка — `throw` или `*_FAILED`; диагностика — `?platform_devtools=1`.
5. **Дефолт один.** Только `initialSlice`/`extraInitial`; `||`/`??`-подстановка при чтении отсутствует; хелперы-фолбеки вида `stringOr(value, fallback)` отсутствуют.
6. **Раздача и сборка падают громко.** Нет `ui-dist` — старт сервиса падает; нет точки входа — сборка падает; `gitSha` недоступен — сборка падает.

## Один источник

| Что | Единственный источник |
|---|---|
| Lit | npm `lit`; vendored-копия, `lit-shim`, import map, переписывание путей при сборке отсутствуют |
| Прочие npm-библиотеки (`marked`, `centrifuge`, DOMPurify) | npm-пакет; vendored-копия — только для того, чего нет в npm, с причиной в правиле |
| Тип UI-события | `CoreEvents` + сгенерированные карты |
| Wire-форма | Pydantic-модель владельца → `*.gen.ts` |
| Утилита | `core/frontend/static/lib/utils/` (`frontend.mdc` § Утилиты) |
| Примитив UI | core UI Kit (`ui_components.mdc` § Один компонент на задачу) |
| Резолв `.js → .ts` | tsconfig/esbuild/vite; `js_or_ts`-резолверы в скриптах и раннерах отсутствуют |

## Контракт слоя apps

`apps/<svc>/ui/` — только композиция: `index.html`, `index.ts`, `app/<svc>-app.ts`, `pages/`, `modals/`, `components/`, `events/resources/*.resource.ts`, `events/types.ts`, `events/wire.gen.ts`, `_helpers/`, `styles/`. Запреты — `frontend.mdc` § Структура, `ui_components.mdc`, `ui_fields.mdc` и `anti-patterns.md`; машинные сигнатуры — `scripts/gates/frontend/ui_canon_rules.py`.

## Контракт kit

- Один компонент на задачу: тег `platform-*`, UIKDS-карточка `tests/ui/design-system/components/<tag>/` (`contract.spec.ts`, `playwright.spec.py`, README), запись в `tests/ui/design-system/catalog.yaml`.
- Компонент kit не знает сервисов: нет импортов `apps/`, нет доменных типов в props — generic-контракт и типизированные события в `HTMLElementEventMap`.
- Поля — через `<platform-field-shell>`; label, hint, error — props.
- Стили — токены и shared-модули; `static styles` компонента — только layout своего shadow.

## Hard cutover

API переименовывается без адаптеров; старые компоненты, пути, мосты и исключения удаляются в том же изменении; все callsites обновляются. Большой корень ведётся серией зелёных шагов без runtime-адаптеров и закрывается, когда старое не осталось ни в одном потребителе.
