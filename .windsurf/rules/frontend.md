---
trigger: model_decision
alwaysApply: true
---
# Frontend: Full Event Sourcing + zero-import canon

Весь UI — на событиях через единый `EventBus`. Доменное состояние — в фабриках
(`createAsyncOp`/`createResourceCollection`/`createCursorList`/`createFacets`/
`createForm`/`createSlice`). Pages, modals и components получают доступ к
фабрикам ТОЛЬКО через helpers базы по строковому имени. Никаких сервисов,
store, features, Zustand, BaseStore, ad-hoc HTTP-клиентов и фолбеков.

НИКАКОГО ОТКЛОНЕНИЯ ОТ КАНОНА. ZERO-IMPORT, ZERO-FALLBACK.

См. также: `ui_factories.mdc` (контракт фабрик), `ui_events.mdc` (bus / contract /
backend → UI), `ui_components.mdc` (правила core UI Kit).

## Стек

Lit 3, ES modules через import map, нативные web components. Бандлера
**нет** — браузер грузит модули напрямую. Никакого Zustand/Redux/MobX.

## Один поток

```
[click/HTTP/WS/timer/router]
  -> EventBus.dispatch(event)
       -> EventLog (append-only)
       -> Reducers (slice фабрик, pure)         -> State -> Selectors -> Lit re-render
       -> Effects (фабрик: HTTP/WS/storage/...) -> dispatch новых событий
```

State `frozen`. Изменения — ТОЛЬКО reducer. Источник правды — event log +
reducer фабрики.

## Базовые классы (единственно допустимые)

| Класс | Файл | Назначение |
|---|---|---|
| `PlatformElement` | `@platform/lib/platform-element/index.js` | Любой Lit-компонент платформы. |
| `PlatformApp`     | `@platform/lib/base/PlatformApp.js`        | Корневой `<svc>-app`, регистрирует фабрики. |
| `PlatformPage`    | `@platform/lib/base/PlatformPage.js`       | Страницы-маршруты. |
| `PlatformModal`   | `@platform/lib/components/glass-modal.js`  | Модалка с тёмным backdrop'ом. |
| `PlatformFormModal` | там же                                   | Модалка с формой (dirty-tracking, closeAfterSave). |
| `PlatformLightModal` | `@platform/lib/components/glass-light-modal.js` | Лёгкая модалка / drawer. |

Запрещено: `LitElement`, `HTMLElement`, любая своя база.

## API компонента — ТОЛЬКО helpers базы

Полный список методов `PlatformElement`:

| Метод | Что делает |
|---|---|
| `this.dispatch(type, payload?, meta?)` | отправить событие в bus |
| `this.useEvent(type, handler)`         | подписка на отдельный тип события |
| `this.select(selector, opts?)`         | реактивная подписка на срез state |
| `this.t(key, vars?, namespace?)`       | перевод; ns берётся из явного аргумента → `static i18nNamespace` → `defaultI18nNamespace` PlatformApp; иначе `throw` |
| `this.useResource(name, opts?)`        | `ResourceController` поверх `createResourceCollection` |
| `this.useOp(name)`                     | `OpController` поверх `createAsyncOp` |
| `this.useForm(name)`                   | `FormController` поверх `createForm` |
| `this.useCursorList(name, opts?)`      | `CursorListController` поверх `createCursorList` |
| `this.useFacets(name)`                 | `FacetsController` поверх `createFacets` |
| `this.useSlice(name)`                  | `SliceController` поверх `createSlice` |
| `this.toast(i18n_key, {type?, vars?, duration?})` | toast через `UI_TOAST_SHOW` |
| `this.openModal(kindOrClass, props?)`  | `UI_MODAL_OPEN` |
| `this.closeModal(kind?)`               | `UI_MODAL_CLOSE` |
| `this.openSidebar()`                   | `UI_SIDEBAR_OPEN_REQUESTED` |
| `this.closeSidebar()`                  | `UI_SIDEBAR_CLOSE_REQUESTED` |
| `this.navigate(routeKey, params?)`     | `ROUTER_NAVIGATE_REQUESTED` |
| `this.copyToClipboard(text, {success_i18n_key, error_i18n_key})` | `UI_CLIPBOARD_COPY_REQUESTED` |
| `this.setLocale(locale)`               | `I18N_LOCALE_REQUESTED` |
| `this.setTheme(name)`                  | `THEME_SET_REQUESTED` |
| `this.switchCompany(companyId)`        | `AUTH_COMPANY_SWITCH_REQUESTED` |
| `this.emit(name, detail?)`             | DOM-событие parent←child через slot/composed (только для composition внутри одного компонента; не cross-app) |

Каждый метод бросает `Error` при отсутствии обязательных аргументов или
неизвестном `name`/`kind`/типе toast. Никаких неявных дефолтов.

Запрещено в pages/modals/components: `this.services`, `this.auth`,
`this.notify`, `this.icon`, `this.theme`, `this.i18n`, `this.companies`,
`this.calendarApi`, `this.filesApi`, `this.fileTypes`, `this.team`. Этих
геттеров не существует.

## Имена событий

`<scope>/<entity>/<verb>` — lowercase, snake_case, ровно >= 3 сегмента.

WS-команды (фрейм клиент → сервер) дополнительно обязаны заканчиваться на
`_requested` — иначе `core.websocket.command_router` отказывает в
регистрации handler'а. Если имя фабрики не совпадает с каноничным
backend-именем, используй опцию `commandType: 'sync/<entity>/<verb>_requested'`
в `createAsyncOp` (см. `ui_factories.mdc`).

Core scope'ы (`@platform/lib/events/contract.js`): `auth`, `theme`, `i18n`,
`router`, `network`, `ui`, `notify`, `pwa`, `storage`, `http`, `ws`. Дополнительно
из `@platform/lib/events/index.js`: `CoreAuthEvents`, `ICON_EVENTS`,
`FILES_EVENTS`, `COMPANIES_EVENTS`, `TEAM_EVENTS`, `CALENDAR_EVENTS`,
`NOTIFICATIONS_EVENTS`, `FILE_TYPES_EVENTS`, `PWA_EVENTS`,
`I18N_NAMESPACE_SET_REQUESTED`.

Сервисные имена — порождаются фабриками в `apps/<svc>/ui/events/resources/*.resource.js`
по контракту `'<svc>/<entity>/<verb>'`. Литералы прямо в коде запрещены —
импортируй `factory.events.X` или используй helper-методы контроллера.

## Структура apps/<svc>/ui

```
apps/<svc>/ui/
  index.js                          # bootstrap: импорт <svc>-app + страниц + модалок
  app/<svc>-app.js                  # extends PlatformApp; static factories, static defaultI18nNamespace
  events/
    resources/                      # все фабрики: '<svc>/<entity>'
      api-keys.resource.js
      embed.resource.js
      ...
  components/                       # presentational PlatformElement
  pages/                            # PlatformPage; ZERO IMPORT (lit + база + локальные стили)
  modals/                           # PlatformModal / PlatformFormModal / PlatformLightModal
  styles/<svc>.css
```

**Запрещено** в `apps/<svc>/ui/`:

- папки `services/`, `store/`, `features/`;
- файлы `*.service.js`, `*.store.js`, `*.controller.js` (контроллеры
  достаются только через helpers базы — `useResource`/`useOp`/...);
- `events/effects/` или `events/reducers/` — вся логика домена в фабриках;
- `events/<svc>-events.js` или `events/selectors.js` — события и селекторы
  выводятся фабрикой автоматически;
- `events/contract.js` (создание своего) — реестр core-типов один на платформу.

## Zero-import canon в pages/ и modals/

Файл `apps/<svc>/ui/pages/<x>.js` и `apps/<svc>/ui/modals/<x>.js` импортирует
**только**:

- `lit` (`html`, `css`, `nothing`, ...);
- базу из `@platform/lib/base/...` (`PlatformPage`, `PlatformModal`, ...);
- core UI Kit-компоненты из `@platform/lib/components/...`
  (`<glass-card>`, `<platform-icon>`, `<page-header>`, ...);
- локальные стили этого же сервиса (`../components/...`, `../styles/...`).

Запрещено в pages/modals/components сервиса:

- `from '@platform/lib/events/contract.js'` для `dispatch UI_*|ROUTER_*|AUTH_*|I18N_*|THEME_*|COMPANIES_*` — используй helpers;
- `from '@platform/lib/utils/i18n-namespace.js'` (`I18nNs.X`) — пиши
  `static i18nNamespace = '<ns>';` строкой или опирайся на
  `defaultI18nNamespace` PlatformApp;
- `from '@platform/lib/base/use-resource.js'` (контроллеры) — только
  `this.useResource(...)` / `this.useOp(...)` / ...;
- `from '../events/resources/*.resource.js'` — фабрики достаются по имени;
- `new ResourceController/OpController/FormController/CursorListController/FacetsController` — запрещены конструкторы напрямую;
- `httpRequest` / `fetch` / `axios` — HTTP только в `request` функции
  фабрики;
- `||`, `??` фолбеки в местах чтения (`x || []`, `obj.field || 'def'`) —
  дефолты живут только в `initialSlice` фабрики (см. `ui_factories.mdc`).

## Жёсткие запреты (CI-проверяемые)

CI: `make check-ui-canon` (`scripts/check_ui_canon.sh`),
`make check-events-canon` (`+ scripts/check_ui_factories.py`).

- `extends LitElement` — везде (только базы платформы).
- `extends HTMLElement` — везде.
- `new CustomEvent(...)` в `apps/<svc>/ui/**` — допустимо ТОЛЬКО внутри
  `core/frontend/static/lib/components/**` для composition. В сервисе —
  `this.dispatch(...)` или `this.emit(...)` для slot-композиции.
- `this.services.*`, `this.auth`, `this.icon`, `this.theme`, `this.i18n`,
  `this.companies`, `ServiceRegistry`, `BaseStore`, `BaseService`,
  `AppEvents`, Zustand — нигде.
- `fetch(`, `axios`, `httpRequest` в pages/modals/components.
- `setState`, прямое присваивание полей state — запрещено.
- Папки `services/`, `store/`, `features/`, файлы `*.service.js`,
  `*.store.js`, `events/effects/`, `events/reducers/` в `apps/<svc>/ui/` —
  запрещены.
- `||`-фолбеки `|| []`, `|| {}`, `|| 'default'`, `?? '—'`, `?? null` в
  `apps/<svc>/ui/{pages,modals,components,events/resources}/**`.
- `dispatch(CoreEvents.<UI_*|ROUTER_*|AUTH_*|I18N_*|THEME_*|COMPANIES_*>)`
  в pages/modals/components — только через helpers базы.
- Имя события без формата `<scope>/<entity>/<verb>` — фейл.
- Имя фабрики без формата `<svc>/<entity>` (ровно 2 сегмента) — фейл.

## Modal canon

Все модалки наследуют `PlatformModal` / `PlatformFormModal` /
`PlatformLightModal`, имеют `static modalKind = '<scope>.<entity>'` и
регистрируются через `registerModalKind`.

```js
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

export class FrontendCreateApiKeyModal extends PlatformModal {
    static modalKind = 'frontend.api_key_create';
    constructor() {
        super();
        this._create = this.useOp('frontend/api_key_create');
    }
    render() { /* ... */ }
}
customElements.define('frontend-create-api-key-modal', FrontendCreateApiKeyModal);
registerModalKind(FrontendCreateApiKeyModal.modalKind, 'frontend-create-api-key-modal');
```

Открытие/закрытие — `this.openModal(SomeModal)` / `this.closeModal()`.
Прямое `document.createElement('*-modal')` / `document.body.appendChild` /
`this.open = true` запрещены — рендер делает `<platform-modal-stack>`.

## i18n

- Каждый компонент с переводами обязан иметь `static i18nNamespace = '<ns>';`
  ИЛИ `PlatformApp.defaultI18nNamespace = '<ns>';` (строкой). `I18nNs.X` —
  не использовать в pages/modals/components.
- Каждый новый ключ — парно в `core/i18n/translations/{ru,en}/<ns>.json`.
- Toast/error ключи фабрики — обязательны и проверяются `make check-i18n`,
  `scripts/check_ui_factories.py`.
- Скан непереведённого UI: `uv run python scripts/report_ui_i18n_gaps.py`.
  Цель: **0** совпадений по сервису.
- Cross-check код ↔ JSON: `make check-i18n-keys` —
  `--mode missing --strict` для каждого мигрированного сервиса = exit 0.

## Backend → UI

«Нажать кнопку из бэка» = бэк публикует событие в общий канал
`platform:ui_events` через `core/ui_events/dispatcher.py`:

```python
from core.ui_events import publish_ui_event_to_user
await publish_ui_event_to_user(
    user_id=...,
    type="crm/note/updated",
    payload={"note_id": note_id},
    correlation_id=trace_id,
)
```

WS-эффект форвардит фрейм, фронт диспатчит как обычное событие.
Подписанный компонент использует `this.useEvent('crm/note/updated', handler)`.

## Тесты

- Reducers фабрик — чистые `(state, event) => state`, unit без mocks.
- Effects фабрик — фейковый `ctx = { dispatch, getState }`; реальный
  `httpRequest` с моком `fetch`.
- Между тестами: `clearFactoryRegistry()`,
  `_resetResourceRegistryForTests()`, `resetPlatformBusForTests()`.
- E2E — Playwright: backend dispatch → UI обновляется; click → reducer →
  render.

## DevTools

`?platform_devtools=1` — пишет каждое событие в console и кладёт
`window.__platformDevtools__ = { trail(), state(), dispatch(), clear() }`.

## Канон фронтенда: отклонения запрещены

Любое отклонение от канона = сначала правка `frontend.mdc`/`ui_events.mdc`/
`ui_factories.mdc`, потом код. Не наоборот. CI отлавливает большинство
нарушений автоматически — `make check-events-canon`.
