# Целевая архитектура UI (north star)

Этот документ — эталон, к которому сходится миграция. Каждая правка в
рекурсивном цикле измеряется им: «соответствует ли это слою и контракту?»

## Слои — разрешённые зависимости сверху вниз

```
apps/<svc>/ui/**           композиция: pages, modals, routes, i18n, static factories
        │  может зависеть только на ↓
lib/events/factories + resources + effects   данные, команды, push, стейт
        │
lib/components/**          kit-примитивы и поля (platform-*)
        │
lib/styles/shared/**       css``-модули паттернов (form, field-pill, card…)
        │
assets/css/tokens.css      единственный источник значений (цвет/типографика/ритм)
        │
vendored (assets/js/…)     lit, codemirror, three — только внешние библиотеки
```

Запрещённые направления: lib → apps, components → events-конкретики,
shared-стили → компонентные, значения в обход tokens.css.

## Контракт слоя apps (`apps/<svc>/ui/**`)

Приложение — только композиция. В `apps/<svc>/ui` разрешено:

- `index.html`, `index.ts` — entry и boot;
- `pages/`, `modals/`, `components/` — классы `PlatformPage`/`PlatformModal`/
  `PlatformElement`, render = html`` из kit-компонентов и данных фабрик;
- `events/resources/*.resource.ts` — декларации фабрик;
- `<svc>-app.ts` — `static factories`, маршруты, i18n-namespace;
- `styles/` — css``-модули композиции (раскладка, отступы); без значений цвета.

В `apps/<svc>/ui` **запрещено** (полный список — `anti-patterns.md` +
`scripts/ui_canon_rules.py`):

1. Свои примитивы: `customElements.define` для *-button/-input/-modal/
   -dropdown/-tooltip/-tabs/-table/-card/-badge/-chip/-spinner/-skeleton/… —
   примитив живёт в `core/frontend/static/lib/components/` или не существует.
2. Сырые `<input>/<textarea>/<select>` — только `<platform-field>`;
   ручная `.field-pill`-разметка — только `<platform-field-shell>`.
3. `fetch`/`httpRequest` вне `events/` — данные приходят через фабрику.
4. `document.createElement`+`appendChild` для модалок — `this.openModal`;
   `window.confirm/alert/prompt` — `platformConfirm`/`toast`.
5. Прямой `localStorage` — `platformStorageKey`; `window.dispatchEvent`
   (CustomEvent) — EventBus; `this.dispatch(CoreEvents.*)` — helpers базы.
6. Литеральные цвета/размеры вне tokens.css; локальные `--*` токены,
   дублирующие платформенные; локальные keyframes/спиннеры.
7. Утилиты, которые уже есть в `lib/utils/` (debounce, форматтеры дат/денег,
   clipboard, download, viewport, storage). Дубль = удалить, взять из lib.
8. Относительные импорты в vendored (`assets/js/lit/lit.min.js` и т.п.) —
   только `from 'lit'`, `from 'marked'`, `from 'centrifuge'`.
9. Состояние домена в полях компонента (`this._items = …` после fetch) —
   фабрика; локальные массивы, мержимые по push, — `extraReducer` фабрики.
10. Свой роутер, свой стор, свой bus — всё это уровень lib, не сервиса.

## Контракт kit (`core/frontend/static/lib/**`)

- Один компонент на задачу: `platform-*` тег, UIKDS-карточка
  (`tests/ui/design-system/components/<tag>/`), contract.spec, README.
- Компонент kit не знает про сервисы: никаких `apps/`-импортов,
  никаких доменных типов в props — только generic-контракты.
- Поля — через `platform-field-shell`; labels/hints/errors — props, не
  внешняя разметка.
- Стили — токены + shared-модули; компонентные css`` — только layout
  собственного shadow.
- Public API компонента — props/events; уходить в shadow наружу нельзя.

## Типизация (TS-контракт)

- `strict`, `noUncheckedIndexedAccess` — включены глобально.
- Reactive props: `static properties` + `declare`-поля (НЕ поля-инициализаторы —
  `useDefineForClassFields: true` делает их own-property и глушит реактивность).
- `import type` для типов (`verbatimModuleSyntax`).
- `any`/неявный any — запрещены; точка потери типа чинится, не маскируется
  (та же норма, что ratchet `cast_calls` в Python).
- Доменные payload'ы — типы рядом с фабрикой (`events/resources/<e>.ts`
  экспортирует `interface`), страницы импортируют, не переобъявляют.

## Сборка

- `npm run build:ui` → `apps/<svc>/ui-dist/` (esbuild, splitting, hashed chunks).
- `make ui` = `ui-build` + `ui-typecheck` + `lint-ts` + `test-frontend-core`.
- `make ui-watch` — dev watch. `make app` после миграции требует собранный
  ui-dist (mount отдаёт dist через `resolve_ui_static_dir`).

## Hard cutover

Обратной совместимости нет: API переименовывается без адаптеров, старые
компоненты/пути удаляются в том же коммите, все callsites обновляются
атомарно. «Временный мост» = костыль = немедленный детектор.
