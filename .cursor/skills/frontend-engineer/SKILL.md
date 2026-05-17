---
name: frontend-engineer
description: Frontend инженер платформы Humanitec. ZERO-FALLBACK, ZERO-IMPORT canon. Lit 3 + EventBus + фабрики (createAsyncOp / createResourceCollection / createCursorList / createFacets / createForm / createSlice). Использовать ВСЕГДА при правках в core/frontend/static/lib/**, apps/*/ui/**, добавлении страниц/модалок/компонентов/ресурсов/событий/i18n/маршрутов; при упоминании Lit, PlatformElement, PlatformPage, PlatformApp, PlatformModal, PlatformFormModal, useResource, useOp, useForm, useCursorList, useFacets, useSlice, dispatch, EventBus, slice, reducer, modal, sidebar, breadcrumbs, toast, навигации, темы, locale, фабрик, restMirror, transport='ws', WS request-reply, factory-registry, glass-modal, platform-modal-stack, platform-trace-viewer, platform-log-viewer, platform-user-chip; перед коммитом любых .js под frontend; при ошибках check_ui_canon / check_ui_factories / check_i18n / check_i18n_keys / check_core_frontend_canon / check_command_rest_mirror; и каждый раз когда задача уровня "изменить UI", "добавить страницу", "новый ресурс", "новая модалка", "i18n", "поменять стейт", "WS-команда", "слать событие".
---

# Frontend Engineer — Humanitec Platform

## Идентичность и манифест строгости

Я фронтенд-инженер платформы Humanitec. Мои продукты — `core/frontend/static/lib/**` (общий UI Kit + EventBus + фабрики) и `apps/<svc>/ui/**` (frontend / crm / rag / sync / office / flows / voice / provider_litserve).

Главный закон: **ZERO-FALLBACK, ZERO-IMPORT, ZERO-COSTYL.**

- Любое отклонение от канона = **сначала** правка `.cursor/rules/frontend.mdc` / `ui_events.mdc` / `ui_factories.mdc` / `ui_components.mdc`, **потом** код. Не наоборот.
- Костыль = «временный» хардкод, фолбек на пустой массив, тихий `try/catch`, дубль логики, обход контракта. Костыль **хуже** явной ошибки. Лучше потратить час на правку контракта, чем минуту на `|| []`.
- «Потом отрефакторим» — запрещённая фраза. «Потом» в таком виде не наступает.
- Если CI зелёный, но в коде костыль — значит CI неполный. Тогда:
  1. сначала добавляю детектор костыля в [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) / [`scripts/check_ui_factories.py`](scripts/check_ui_factories.py) / [`scripts/check_core_frontend_canon.py`](scripts/check_core_frontend_canon.py),
  2. потом правлю код под канон,
  3. потом обновляю rule в `.cursor/rules/`.
- Если канон чего-то не покрывает — это пробел в каноне, не лицензия писать «как удобно».

Прежде чем тронуть `.js` под фронт, я обязан:

1. Прочитать актуальные правила: [`frontend.mdc`](.cursor/rules/frontend.mdc), [`ui_events.mdc`](.cursor/rules/ui_events.mdc), [`ui_factories.mdc`](.cursor/rules/ui_factories.mdc), [`ui_components.mdc`](.cursor/rules/ui_components.mdc), [`architecture.mdc`](.cursor/rules/architecture.mdc) (REST-зеркало команд), и сервисное правило (`sync.mdc`/`crm.mdc`/`rag.mdc`/`flows.mdc`/`office.mdc`/`voice.mdc`).
2. Понять, к какой из шести фабрик сводится моя задача (или это slice-only через `createSlice`).
3. Перед declaration «готово» прогнать чек-лист из последнего раздела и убедиться, что **`make check-events-canon`** зелёный.

## Один поток данных (диаграмма)

```mermaid
flowchart LR
  click[click / HTTP / WS / timer / router]
  click --> dispatch[EventBus.dispatch]
  dispatch --> log[EventLog append-only]
  log --> reducer[Reducer slice фабрики - pure]
  reducer --> state[State frozen]
  state --> select[SelectController / use*]
  select --> render[Lit re-render]
  log --> effect[Effect фабрики]
  effect --> http[HTTP / WS / storage / timer]
  effect --> dispatch
```

Source of truth — реализация: [`core/frontend/static/lib/events/bus.js`](core/frontend/static/lib/events/bus.js), [`core/frontend/static/lib/events/log.js`](core/frontend/static/lib/events/log.js), [`core/frontend/static/lib/events/select-controller.js`](core/frontend/static/lib/events/select-controller.js), [`core/frontend/static/lib/events/factories/`](core/frontend/static/lib/events/factories/).

State `frozen`. Изменения — **только** reducer фабрики. Никакого `setState`, `state.x = ...`, `getState().x =`. Источник правды — append-only event log + reducers.

## Базовые классы (единственно допустимые)

| Класс | Файл | Назначение |
|---|---|---|
| `PlatformElement` | [`core/frontend/static/lib/platform-element/index.js`](core/frontend/static/lib/platform-element/index.js) | Любой Lit-компонент платформы. |
| `PlatformApp` | [`core/frontend/static/lib/base/PlatformApp.js`](core/frontend/static/lib/base/PlatformApp.js) | Корневой `<svc>-app` — регистрирует фабрики и effects. |
| `PlatformPage` | [`core/frontend/static/lib/base/PlatformPage.js`](core/frontend/static/lib/base/PlatformPage.js) | Страницы-маршруты. |
| `PlatformModal` | [`core/frontend/static/lib/components/glass-modal.js`](core/frontend/static/lib/components/glass-modal.js) | Модалка с тёмным backdrop'ом. |
| `PlatformFormModal` | [`core/frontend/static/lib/components/glass-form-modal.js`](core/frontend/static/lib/components/glass-form-modal.js) | Модалка с формой (dirty-tracking, `closeAfterSave()`). |

**Запрещено**: `extends LitElement`, `extends HTMLElement`, любая своя «упрощённая» база. Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.1, [`scripts/check_core_frontend_canon.py`](scripts/check_core_frontend_canon.py).

Каждый файл с переводами обязан иметь `static i18nNamespace = '<ns>'` строкой ИЛИ опираться на `static defaultI18nNamespace` `PlatformApp`. Импорт `I18nNs.X` из `@platform/lib/utils/i18n-namespace.js` в pages/modals — **запрещён** ([`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13).

## API компонента — ТОЛЬКО helpers базы

Полный набор методов `PlatformElement` (источник: [`core/frontend/static/lib/platform-element/index.js`](core/frontend/static/lib/platform-element/index.js)):

| Helper | Что делает | Эквивалент CoreEvents |
|---|---|---|
| `this.dispatch(type, payload, meta?)` | Отправить событие в bus. `payload === undefined` — `throw`. | — |
| `this.useEvent(type, handler)` | Подписка на отдельный тип. Авто-unsubscribe в `disconnectedCallback`. | — |
| `this.select(selector, opts?)` | Реактивная подписка на срез state. Возвращает `SelectController`; `.value` — текущий снимок. | — |
| `this.t(key, vars?, namespace?)` | Перевод. NS: явный аргумент → `static i18nNamespace` → `defaultI18nNamespace`. Иначе `throw`. | — |
| `this.useResource(name, opts?)` | `ResourceController` поверх `createResourceCollection`. | — |
| `this.useOp(name)` | `OpController` поверх `createAsyncOp`. | — |
| `this.useForm(name)` | `FormController` поверх `createForm`. | — |
| `this.useCursorList(name, opts?)` | `CursorListController` поверх `createCursorList`. | — |
| `this.useFacets(name)` | `FacetsController` поверх `createFacets`. | — |
| `this.useSlice(name)` | `SliceController` поверх `createSlice`. | — |
| `this.toast(i18n_key, { type?, vars?, duration?, namespace? })` | Toast. `type ∈ {success, error, warning, info}`. | `UI_TOAST_SHOW` |
| `this.openModal(kindOrClass, props?)` | Открыть модалку из реестра. Класс должен иметь `static modalKind`. | `UI_MODAL_OPEN` |
| `this.closeModal(kind?)` / `this.closeModal({ id })` | Закрыть модалку. | `UI_MODAL_CLOSE` |
| `this.openSidebar()` / `this.closeSidebar()` | Mobile-сайдбар через bus. | `UI_SIDEBAR_OPEN_REQUESTED` / `_CLOSE_REQUESTED` |
| `this.navigate(routeKey, params?, { search?, replace? }?)` | Навигация. | `ROUTER_NAVIGATE_REQUESTED` |
| `this.copyToClipboard(text, { success_i18n_key, error_i18n_key })` | Clipboard API через effect. | `UI_CLIPBOARD_COPY_REQUESTED` |
| `this.setLocale(locale)` | Смена языка. | `I18N_LOCALE_REQUESTED` |
| `this.setTheme('dark' \| 'light')` | Смена темы. | `THEME_SET_REQUESTED` |
| `this.switchCompany(company_id)` | Смена активной компании. | `AUTH_COMPANY_SWITCH_REQUESTED` |
| `this.startOAuth(provider, { returnPath?, plan? })` | OAuth-редирект. | `auth/oauth/start_requested` |
| `this.emit(name, detail?)` | DOM event для slot/composed-композиции (parent←child) **внутри одного компонента**. Не для cross-app. | — |

В `apps/<svc>/ui/{pages,modals,components}/**` **запрещён прямой `this.dispatch(CoreEvents.UI_*|ROUTER_*|AUTH_*|I18N_*|THEME_*|COMPANIES_*)`** — нужный helper уже есть. Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13.

**Запрещено в pages/modals/components сервиса** (детекторы: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.4, п.6, п.11):

- `this.services.*`, `this.auth`, `this.notify`, `this.theme`, `this.i18n`, `this.companies`, `this.calendarApi`, `this.filesApi`, `this.fileTypes`, `this.team`, `this.icon`, `this.a2a`, `this.syncWs`, `this.syncApi`, `this.crmApi`, `this.ragApi` — этих геттеров **не существует**. Если нужно соответствующее действие — есть helper или фабрика.
- `ServiceRegistry`, `BaseStore`, `BaseService`, `AppEvents` — таких модулей нет.
- `this.bus.getState()` в компонентах — читай через `this.select(s => ...)`. Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.14.
- `await this.dispatch(...)` (fake await) — диспатч fire-and-forget; ответ ловится через `useEvent('*_succeeded' / '*_failed')` или `OpController.run()`. Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.14.

## Шесть фабрик — единственный способ описать домен

Полные контракты — [`ui_factories.mdc`](.cursor/rules/ui_factories.mdc), реализация — [`core/frontend/static/lib/events/factories/`](core/frontend/static/lib/events/factories/).

| Фабрика | Назначение | Контроллер | Helper |
|---|---|---|---|
| `createAsyncOp` | Одиночная операция (load/save/run). | `OpController` | `this.useOp(name)` |
| `createResourceCollection` | CRUD-коллекция (list/get/create/update/remove). | `ResourceController` | `this.useResource(name, opts?)` |
| `createCursorList` | Cursor-paginated лента + filters. | `CursorListController` | `this.useCursorList(name, opts?)` |
| `createFacets` | Typeahead по фасетам. | `FacetsController` | `this.useFacets(name)` |
| `createForm` | Форма (draft / errors / submit). | `FormController` | `this.useForm(name)` |
| `createSlice` | UI-only state без транспорта (overlay, presence, push-only). | `SliceController` | `this.useSlice(name)` |

**Других фабрик нет и не будет.** Если кейс не лезет — не создавай «свою» фабрику; уточняй контракт существующих или комбинируй (например, `form.submitEvent` указывает в `asyncOp.events.REQUESTED`).

### Обязательные поля каждой фабрики (zero-guess)

Контроль: [`scripts/check_ui_factories.py`](scripts/check_ui_factories.py) + сама фабрика бросает на старте.

- `name: '<svc>/<entity>'` — lowercase snake_case, ровно 2 сегмента, `<svc>` совпадает с каталогом (`apps/<svc>/ui/...`). Проверка: [`assertResourceName`](core/frontend/static/lib/events/factories/_internal.js).
- `sliceKey` выводится автоматически из `name` (`scope_entity` -> `scopeEntity` lowerCamel) — перекрывать вручную нельзя для всех, кроме `createSlice` (там опционально, см. ниже).
- `successToastKey` + `errorToastKey` ИЛИ `silent: true` (в `createAsyncOp`); `toastKeys: { create, update, remove, create_error?, update_error?, remove_error? }` (в `createResourceCollection` для каждой mutating op). Любой toast-ключ обязан существовать одновременно в `core/i18n/translations/ru/<ns>.json` и `en/<ns>.json` ([`scripts/check_ui_factories.py`](scripts/check_ui_factories.py)).
- `transport: 'http' \| 'ws'` (default `'http'`). Для `'ws'` обязательны `wsTimeoutMs` (положительное число) и `restMirror: { method, path }`.
- `restMirror` — платформенный инвариант REST-зеркала команды ([`architecture.mdc`](.cursor/rules/architecture.mdc)). Для HTTP обычно auto-derived из `baseUrl`+`idField`; для WS обязателен явный. CI: [`scripts/check_command_rest_mirror.py`](scripts/check_command_rest_mirror.py) сверяет с FastAPI route в `apps/<svc>/api/**`.
- В `createResourceCollection`: `baseUrl` (без trailing slash), `idField` (имя поля id), `operations` непустой массив из `['list','get','create','update','remove']`.
- В `createCursorList`: `baseUrl`, `buildQuery(filters)`, `pageSize` (число > 0). Только `transport: 'http' | 'ws'` с `method: 'GET'` (cursor lists read-only).
- В `createFacets`: `facets: { [key]: 'url-segment' }`, `debounceMs >= 0`, `minQueryLength >= 0`.
- В `createForm`: непустая `schema` + `initial` со значением для каждого поля схемы (отсутствие — `throw`); `submitEvent: '<scope>/<entity>/<verb>'`.
- В `createSlice`: `extraInitial` (минимум один ключ) + `extraReducer(state, event, events)` (pure). Запрещены `transport`, `request`, `restMirror`, `wsTimeoutMs` (slice без транспорта). Опционально `extraEvents`, `actions`.

### `commandType` — переопределение типа WS-фрейма

Когда имя фабрики (`sync/calls_invite`) не совпадает с каноничным backend-именем команды (`sync/calls/invite_requested`), используется `commandType: '<scope>/<entity>/<verb>_requested'` в `createAsyncOp`:

```js
createAsyncOp({
    name: 'sync/calls_invite',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    commandType: 'sync/calls/invite_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/invite' },
});
```

Reply-типы выводятся автоматически: `<commandType без _requested>_succeeded` / `_failed`. Допустим **только** при `transport: 'ws'`. Опция отсутствует у `createResourceCollection` (см. [`ui_factories.mdc`](.cursor/rules/ui_factories.mdc)) — для отдельной нестандартной операции пиши отдельный `createAsyncOp`.

### Сериализованный create (UI-идемпотентность)

Reducer на первый `*/create_requested` ставит `createInFlight: true`, `createLockEventId: event.id`. Второй `create_requested` при уже `createInFlight` lock не меняет. `CREATED` / `create_failed` сбрасывают lock.

`ResourceController.create(payload)` сам возвращает `undefined` при `createInFlight`, второй dispatch не делается ([`use-resource.js`](core/frontend/static/lib/base/use-resource.js)). Кнопку «Создать» дизейблить **от `this._resource.createInFlight`**, не от `this._resource.loading` (`loading` относится только к `list`).

## factory-registry: lookup ТОЛЬКО по имени

Реализация: [`core/frontend/static/lib/events/factory-registry.js`](core/frontend/static/lib/events/factory-registry.js).

Регистрация — один раз при boot'е в `PlatformApp` через `static factories = [...]`:

```js
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { apiKeysResource } from '../events/resources/api-keys.resource.js';
import { teamMembersResource, inviteGenerateOp } from '../events/resources/team.resource.js';

export class FrontendApp extends PlatformApp {
    static defaultI18nNamespace = 'frontend';
    static factories = [apiKeysResource, teamMembersResource, inviteGenerateOp /* ... */];
    getBaseUrl() { return '/frontend/api'; }
    getRoutes() { return FRONTEND_ROUTES; }
    renderRoute(routeKey, params) { /* ... */ }
}
```

Из компонента фабрика достаётся **по строковому имени** через helper:

```js
this._keys = this.useResource('frontend/api_keys', { autoload: true });
```

**Запрещено в pages/modals/components**:

- `import { fooResource } from '../events/resources/foo.resource.js'` — фабрика достаётся через `this.useResource(...)`/`useOp(...)`/.... Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13.
- `new ResourceController(...)` / `new OpController(...)` / `new FormController(...)` / `new CursorListController(...)` / `new FacetsController(...)` / `new SliceController(...)`. Детектор: тот же.
- Импорт `from '@platform/lib/events/controllers/...'` — таких контроллер-модулей нет; всё через helpers базы.

Любая коллизия имени — `throw` сразу при старте `PlatformApp` (см. [`registerFactory`](core/frontend/static/lib/events/factory-registry.js)). Имя уникально в процессе.

## Контракт события

Имя: `<scope>/<entity>/<verb>` — lowercase, snake_case, **≥ 3 сегмента**. Регулярка из [`assertEventType`](core/frontend/static/lib/events/contract.js): `^[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*){2,}$`.

WS-команды (фрейм клиент → сервер) обязаны заканчиваться на `_requested` — `core.websocket.command_router` отказывает в регистрации handler'а с типом без этого суффикса. Reply-типы выводятся механически: `<type без _requested>_succeeded` / `_failed`.

Push-события (server-initiated broadcast) приходят по WebSocket из `core/ui_events/dispatcher.py::publish_ui_event_*` через канал `platform:ui_events`. Их имя НЕ должно совпадать с командой (нельзя `sync/messages/send` и `sync/messages/send_requested` одновременно — используй разные entity-имена, например `sync/messages/send_requested` (команда) vs `sync/message/created` (push)).

Запрет: имя события без формата `<scope>/<entity>/<verb>` ≥ 3 сегмента. Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.12.

## REST-зеркало команд (платформенный инвариант)

Полное правило: [`architecture.mdc`](.cursor/rules/architecture.mdc) (раздел «REST-зеркало команд»).

| Тип события | REST-зеркало | WS-доступность |
|---|---|---|
| **Команда** (`<svc>/<entity>/<verb>_requested`) | **Обязательно** HTTP в `apps/<svc>/api/**` с тем же method+path+payload+response. | Опционально (через `transport: 'ws'`). |
| **Success/Failure** | Body HTTP-ответа = payload event-а. | Reply-фрейм с тем же `request_id`. |
| **Push** (без `_requested`) | **Запрещено** REST-зеркало. | Только через `publish_ui_event_*`. |

CI: [`scripts/check_command_rest_mirror.py`](scripts/check_command_rest_mirror.py) (входит в `make check-events-canon`) проверяет:

1. Каждая factory operation имеет `restMirror` (явный или auto).
2. Соответствующий FastAPI route существует.
3. Имя push-события не совпадает с именем команды.

Запрет fallback с WS на HTTP в коде. Если WS оборвался или истёк timeout — операция падает в `*_failed` с `error_code: 'ws_disconnected'|'ws_timeout'`. Никакого retry через HTTP.

## Идемпотентные команды: ждать ответа без двойного клика

Любая команда (HTTP или WS) — это `<scope>/<entity>/<verb>_requested` → серверное `<...>_succeeded` / `_failed`. Между «нажал кнопку» и «получил ответ» проходит время. Запрещено допускать повторный `_requested` от того же действия пользователя — это плодит дубли в БД и race conditions в UI. Запрещено также **руками** держать `this._busy = true / false` — это всегда заканчивается багом (двойной клик во время сетевой ошибки, сброс флага не в той ветке, гонки с push-событиями).

Платформа даёт **три** канонических механизма, и других не нужно.

### 1. `createResourceCollection.create` — встроенный UI-lock

Reducer на первый `*/create_requested` ставит `createInFlight: true`, `createLockEventId: event.id`. Второй `create_requested` при уже `createInFlight` lock не меняет; effect пропускает HTTP/WS, если `event.id !== createLockEventId`; `ResourceController.create()` вообще не диспатчит второй раз. Полный контракт — [`ui_factories.mdc`](.cursor/rules/ui_factories.mdc) (раздел «Сериализованный create»). Реализация — [`core/frontend/static/lib/events/factories/resource-collection.js`](core/frontend/static/lib/events/factories/resource-collection.js).

В компоненте — кнопка дизейблится **от `createInFlight`**, не от `loading` (loading относится только к `list`):

```js
constructor() {
    super();
    this._namespaces = this.useResource('crm/namespaces');
}
render() {
    return html`
        <button ?disabled=${this._namespaces.createInFlight}
                @click=${() => this._namespaces.create({ name: this._draft })}>
            ${this.t('namespace_modal.action_create')}
        </button>
    `;
}
```

Каноничные применения: [`apps/crm/ui/components/note-card-view.js`](apps/crm/ui/components/note-card-view.js) (`busy = isCreate ? this._entities.createInFlight : this._updateOp.busy`), [`apps/crm/ui/modals/namespace-modal.js`](apps/crm/ui/modals/namespace-modal.js) (`this._createForm.submitting || this._namespaces.createInFlight`).

### 2. `OpController.run()` — Promise по `causation_id`

Реализация — [`core/frontend/static/lib/base/use-resource.js`](core/frontend/static/lib/base/use-resource.js). `ctl.run(payload)`:

1. Диспатчит `op.events.REQUESTED` (получает `event.id`).
2. Подписывается на `op.events.SUCCEEDED` / `FAILED`, фильтруя по `event.meta.causation_id === requested.id`.
3. Возвращает Promise, который **всегда резолвится**: SUCCEEDED → `result`, FAILED → `null` (ошибка в `ctl.error`).

Это значит:

- Один компонент = один in-flight запуск op'ы (`ctl.busy === true` пока ждём).
- Кнопку дизейблим через `?disabled=${this._op.busy}`.
- Несколько параллельных запусков той же op'ы из разных мест — корректно разводятся по `causation_id` (каждый callback получает свой ответ).

Каноничные применения: [`apps/crm/ui/pages/daily-notes-page.js`](apps/crm/ui/pages/daily-notes-page.js) (`useEvent('crm/note_search/succeeded', ...)` с фильтром по `meta.causation_id !== this._lastSearchRequestId`), [`apps/crm/ui/components/note-card-view.js`](apps/crm/ui/components/note-card-view.js) (отдельные `_mentionRequestId` / `_voiceSearchRequestId` / `_contextSearchRequestId` для одной op'ы `entity_search` с разными «целями»).

### 3. `_awaitOp` / `_waitForResourceResult` — ждать конкретный SUCCEEDED по `causation_id`

Если нужен **`result`** в коде (например, цепочка зависимых команд: создать сущность → получить `entity_id` → создать relationship), `OpController.run()` уже это даёт. Но если используется `ResourceController.create(...)` (нет `run()`-метода) или сложная цепочка — пишется helper:

```js
_waitForResourceResult(controller, requestedId) {
    const bus = controller.bus;
    const successType = controller.resource.events.CREATED;
    const failedType = controller.resource.events.CREATE_FAILED;
    return new Promise((resolve, reject) => {
        let offSuccess = null;
        let offFailed = null;
        const cleanup = () => {
            if (typeof offSuccess === 'function') offSuccess();
            if (typeof offFailed === 'function') offFailed();
        };
        offSuccess = bus.subscribeType(successType, (event) => {
            if (!event.meta || event.meta.causation_id !== requestedId) return;
            cleanup();
            const item = event.payload && typeof event.payload.item === 'object' ? event.payload.item : null;
            resolve(item);
        });
        offFailed = bus.subscribeType(failedType, (event) => {
            if (!event.meta || event.meta.causation_id !== requestedId) return;
            cleanup();
            const message = event.payload && typeof event.payload.message === 'string'
                ? event.payload.message
                : 'resource create failed';
            reject(new Error(message));
        });
    });
}

async _createEntity(payload) {
    const requested = this._entities.create(payload);
    if (!requested || typeof requested.id !== 'string') {
        throw new Error('CRMNotePage._createEntity: create dispatch returned no id');
    }
    return await this._waitForResourceResult(this._entities, requested.id);
}
```

Каноничные применения: [`apps/crm/ui/pages/note-page.js`](apps/crm/ui/pages/note-page.js) (`_waitForResourceResult` для зависимой цепочки `entities.create → relationships.create`), [`apps/crm/ui/modals/knowledge-import-modal.js`](apps/crm/ui/modals/knowledge-import-modal.js) (`_awaitOp` для последовательного импорта файлов).

Замечание: `ResourceController.create()` сам по себе **уже идемпотентен** (см. п.1) — если `createInFlight === true`, второй вызов вернёт `undefined` без диспатча. Поэтому в `_createEntity` важно проверить `requested && typeof requested.id === 'string'`: `undefined` означает «дубль игнорирован», тогда нет события для ожидания.

### Сводное правило

| Тип операции | Идемпотентность | Дизейбл UI | Когда использовать кастомный await |
|---|---|---|---|
| `createResourceCollection.create` | Встроенная (reducer + effect + controller). | `?disabled=${this._res.createInFlight}` | Когда нужен `item` сразу после create — `_waitForResourceResult`. |
| `createResourceCollection.update / remove` | item-level через `busyIds[id]`. | `?disabled=${this._res.isBusy(id)}` | Редко — обычно push-событие обновляет slice. |
| `createAsyncOp` | `OpController.busy` + `causation_id`. | `?disabled=${this._op.busy}` | Когда нужен `result` для следующего шага — `await this._op.run(...)` или кастомный helper. |
| `createForm.submit` | Внутренний `submitting` + `submitEvent` указывает в op/resource. | `?disabled=${this._form.submitting}` | Не нужно — `submitEvent` сам ставит lock. |

**Запрещено** в pages/modals/components:

- `this._busy = true` / `this._busy = false` — это ручной костыль, всегда теряется на ошибке/race. Используй `createInFlight` / `OpController.busy` / `FormController.submitting`.
- `await this.dispatch(...)` (fake await) — `dispatch` не возвращает Promise результата. См. [`anti-patterns.md`](.cursor/skills/frontend-engineer/anti-patterns.md) пункт 3.4.
- Подписка на `op.events.SUCCEEDED` без проверки `event.meta.causation_id === requested.id` — поймаешь ответ от чужого запуска. Все примеры в CRM фильтруют.
- Несколько `dispatch(events.REQUESTED)` подряд из одного клика — это всегда баг. Если нужно несколько шагов — `await` каждый, желательно через `OpController.run()`.

Полный рецепт цепочки зависимых команд — [`recipes.md`](.cursor/skills/frontend-engineer/recipes.md) рецепт 2bis «Идемпотентные команды и ожидание ответа».

## CoreEvents и helpers (что куда)

Реестр — [`core/frontend/static/lib/events/contract.js`](core/frontend/static/lib/events/contract.js). Сервисные имена (`crm/...`, `flows/...`, `frontend/api_keys/...`) **не лежат** в `CoreEvents` — они порождаются фабриками сервиса.

Прямой `dispatch(CoreEvents.<UI_*|ROUTER_*|AUTH_*|I18N_*|THEME_*|COMPANIES_*>)` в `apps/<svc>/ui/{pages,modals,components}/**` — **запрещён**. Маппинг helper ↔ событие:

| Helper в `PlatformElement` | CoreEvent |
|---|---|
| `this.toast(key, opts)` | `UI_TOAST_SHOW` |
| `this.openModal(kind, props)` | `UI_MODAL_OPEN` |
| `this.closeModal(kind?)` | `UI_MODAL_CLOSE` |
| `this.openSidebar()` | `UI_SIDEBAR_OPEN_REQUESTED` |
| `this.closeSidebar()` | `UI_SIDEBAR_CLOSE_REQUESTED` |
| `this.navigate(routeKey, params?, opts?)` | `ROUTER_NAVIGATE_REQUESTED` |
| `this.copyToClipboard(text, opts)` | `UI_CLIPBOARD_COPY_REQUESTED` |
| `this.setLocale(locale)` | `I18N_LOCALE_REQUESTED` |
| `this.setTheme(mode)` | `THEME_SET_REQUESTED` |
| `this.switchCompany(company_id)` | `AUTH_COMPANY_SWITCH_REQUESTED` |
| `this.startOAuth(provider, opts?)` | `auth/oauth/start_requested` |

Подписка `useEvent` на CoreEvents — допустима (например, страница хочет реагировать на `AUTH_COMPANY_SWITCHED`, `ROUTER_ROUTE_CHANGED`, `UI_DOCUMENTS_RELOAD_REQUESTED`). Запрет — на исходящий dispatch UI-семейств.

## Field canon (поля форм)

Полное правило: [`data-types.mdc`](.cursor/rules/data-types.mdc), [`frontend.mdc`](.cursor/rules/frontend.mdc) (раздел «Field canon»), [`ui_components.mdc`](.cursor/rules/ui_components.mdc) (раздел «Field pill canon»).

`<platform-field>` — единственный канон для **любого** поля формы во всех сервисах (имя/email/url/password/query/description, типизированные атрибуты CRM). Диспетчер всегда рисует `<div class="field-pill">` + опциональный `<span class="field-pill-label">` + подкомпонент.

### API

```html
<platform-field
    type="string"
    input-type="email"
    .label=${this.t('lead_form.email_label')}
    .value=${draft.email}
    .placeholder=${this.t('lead_form.email_placeholder')}
    mode="edit"
    ?disabled=${false}
    @change=${(e) => this._setEmail(e.detail.value)}>
</platform-field>
```

| Свойство | Тип | Что |
|---|---|---|
| `type` | `string\|text\|number\|integer\|boolean\|date\|datetime\|enum\|array\|object\|external_refs` | Тип поля |
| `value` | any | Типизированное значение |
| `mode` | `'view'\|'edit'` | view = readonly |
| `label` | string | Опц.; рисуется как `field-pill-label` |
| `config` | object | Для `enum`: `{ values: [...] }` |
| `placeholder` | string | Edit-режим |
| `disabled` | boolean | — |
| `inputType` | `'text'\|'email'\|'password'\|'url'\|'tel'\|'search'` | Только при `type='string'`. Default `'text'`. Любое другое — `throw`. Атрибут: `input-type` |
| `hint` | string | Подсказка-tooltip рядом с label через `<platform-help-hint>` (наведение/фокус). НЕ always-visible div. |

`@change.detail.value` содержит **типизированное** значение.

`config.values` для `type='enum'` — массив строк `['a', 'b']` ИЛИ массив объектов `[{ value: 'a', label: 'Активно' }, ...]`. Для технических id (flow_id, provider id, etc.) **обязательно** `{value, label}` — иначе пользователь видит сырой технический id вместо имени.

### Whitelist core-виджетов с собственным UI (НЕ заменяют поле)

`<platform-date-picker>`, `<platform-switch>`, `<platform-cron-field>`, `<platform-timezone-picker>`, `<platform-icon-picker>`, `<platform-palette-color-picker>`, `<tag-input>` (внутри `platform-field-array`; атрибут `flat` удалён), `<platform-help-hint>`.

### Сырые `<input>` / `<textarea>` / `<select>` вне `<platform-field>`

Правило: [`scripts/check_field_canon.sh`](scripts/check_field_canon.sh) — запуск `make check-field-canon`. Whitelist `input type` и `data-canon` — как в [`frontend.mdc`](.cursor/rules/frontend.mdc). Классы `form-input` / `field-pill-input` на сыром DOM не освобождают от проверки.

### Spec-widgets через `data-canon`

```html
<input type="text" class="task-input" data-canon="composer" @input=${...}/>
<textarea data-canon="mention" @input=${...}></textarea>
<input data-canon="inline-edit" .value=${title}/>
<input data-canon="search-as-you-type" type="text"/>
<input data-canon="combobox" type="text"/>
```

Без `data-canon` (где требуется) или без whitelisted `type` для `<input>` — нарушение `check_field_canon`.

### Запреты

- `<glass-input>` / `<glass-textarea>` — компоненты удалены в PHASE 1.5; импортировать запрещено.
- Локальный `css\`...\`` блок в `apps/**` с правилами `.form-input` / `.form-textarea` / `.form-select` / `.form-group` / `.form-label` / `.field-pill*`.
- Атрибут `flat` (на `<tag-input>` и любых подкомпонентах).
- Сырые `<input>` / `<textarea>` / `<select>` без `<platform-field>`, без whitelisted `type` и без требуемого `data-canon`.

CI: [`make check-field-canon`](Makefile) ([`scripts/check_field_canon.sh`](scripts/check_field_canon.sh)); [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.17/18. Реализация стилей — [`field-pill.styles.js`](core/frontend/static/lib/styles/shared/field-pill.styles.js), токены `--field-pill-*` в [`tokens.css`](core/frontend/static/assets/css/tokens.css).

## Utility canon (форматтеры / escape / hash / validators)

Любая «общая» утильная функция живёт в [`core/frontend/static/lib/utils/`](core/frontend/static/lib/utils/) и [`core/frontend/static/lib/events/factories/_multipart-upload.js`](core/frontend/static/lib/events/factories/_multipart-upload.js). Локальные копии в `apps/<svc>/ui/**` запрещены — это нарушение DRY и канона.

### Канонические модули

| Модуль | API |
|---|---|
| [`format-file-size.js`](core/frontend/static/lib/utils/format-file-size.js) | `formatFileSize(bytes, { precision? })` |
| [`format-duration.js`](core/frontend/static/lib/utils/format-duration.js) | `formatDurationSeconds(sec, { withHours? })`, `formatDurationMs(ms, { withHours? })` |
| [`format-platform-number.js`](core/frontend/static/lib/utils/format-platform-number.js) | `formatPlatformNumber(value, locale, options?)`, `formatPlatformCurrencyRub(amount, locale, options?)` |
| [`format-platform-date.js`](core/frontend/static/lib/utils/format-platform-date.js) | `formatPlatformDate(input, locale, options?)`, `formatPlatformDateTime(input, locale)`, `formatPlatformTime(input, locale)` |
| [`escape-html.js`](core/frontend/static/lib/utils/escape-html.js) | `escapeHtml(value)` |
| [`hash-string.js`](core/frontend/static/lib/utils/hash-string.js) | `hashString31(seed)`, `hueFromString(seed)`, `initialsFromName(name)`, `indexFromSeed(seed, modulo)` |
| [`validators.js`](core/frontend/static/lib/utils/validators.js) | `EMAIL_RE`, `isValidEmail(value)`, `digitsOnly(value)`, `isValidPhone(value)`, `PHONE_DIGITS_MIN` |
| [`storage-keys.js`](core/frontend/static/lib/utils/storage-keys.js) | `platformStorageKey(scope, key)` — единый префикс `platform:<scope>:<key>` |
| [`_multipart-upload.js`](core/frontend/static/lib/events/factories/_multipart-upload.js) | `createMultipartFileUploadOp({ name, url, extraFields?, restMirror? })` |

### Локаль для форматтеров

`formatPlatform*` принимают `locale` аргументом. Компонент берёт активную локаль через `this.select((s) => s.i18n.locale).value`. Хардкод `'ru-RU'` / `'en-US'` в `Intl.*` / `toLocaleString` запрещён.

### Запреты в `apps/<svc>/ui/**`

- Локальный `function escapeHtml`, `const escapeHtml = ...`.
- Локальный `EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/`, `_digitsOnly`, ad-hoc email regex.
- Локальный hash-цикл `h = (h * 31 + s.charCodeAt(i))`.
- Локальный `formatFileSize` / `_formatBytes` / `_formatFileSize` цикл (свой). Допустима тонкая обёртка-метод компонента, делегирующая в core `formatFileSize`.
- `Intl.NumberFormat('ru-RU', ...)`, `Intl.DateTimeFormat('ru-RU', ...)`, `toLocaleDateString('ru-RU', ...)`, `toLocaleString('ru-RU', ...)`.
- Свободный префикс ключа localStorage (`humanitec.*`, `<svc>:*`, `sync.chat.*`) — только `platformStorageKey('<scope>', '<key>')`.
- Свой multipart-upload `createAsyncOp` без обёртки `createMultipartFileUploadOp` — копипаста запрещена.
- Always-visible `<div class="hint">…</div>` под полем формы: описание передавай в `.hint=${...}` атрибут `<platform-field>` — он рисует hover-tooltip через `<platform-help-hint>`.
- `<platform-field type='enum' .config=${{ values: ['flow_id_1', 'flow_id_2'] }}>` для технических id: пользователь увидит сырой id. Канон — `{ values: [{ value: 'flow_id_1', label: 'Имя flow' }, ...] }`.

CI: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.19 (детекторы `'ru-RU'`, `EMAIL_RE`/`_digitsOnly`, `escapeHtml`, hash×31).

## Modal canon

Правила: [`ui_components.mdc`](.cursor/rules/ui_components.mdc) (раздел «Modal canon»). Реализация: [`core/frontend/static/lib/components/glass-modal.js`](core/frontend/static/lib/components/glass-modal.js), [`core/frontend/static/lib/utils/modal-registry.js`](core/frontend/static/lib/utils/modal-registry.js), [`core/frontend/static/lib/components/platform-modal-stack.js`](core/frontend/static/lib/components/platform-modal-stack.js).

Канон:

```js
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

export class FrontendCreateApiKeyModal extends PlatformFormModal {
    static modalKind = 'frontend.api_key_create';
    constructor() {
        super();
        this._keys = this.useResource('frontend/api_keys');
    }
    async handleSubmit() {
        this._keys.create({ name: this._name, scopes: Array.from(this._scopes) });
        this.closeAfterSave();
    }
}
customElements.define('frontend-create-api-key-modal', FrontendCreateApiKeyModal);
registerModalKind(FrontendCreateApiKeyModal.modalKind, 'frontend-create-api-key-modal');
```

`modalKind` обязан соответствовать `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (snake_case, точка как разделитель). Регистрация дубля — `throw`.

Открытие/закрытие — **только** через `this.openModal(SomeModal, props)` и `this.close()` (внутри модалки) или `this.closeModal()` (снаружи). Стек живёт в `state.modals.stack`, рендерит `<platform-modal-stack>`, монтируемый один раз в `PlatformApp.render()`.

**Запрещено** (детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.9):

- `document.createElement('*-modal')`.
- `document.body.appendChild(modalEl)`.
- `modal.open = true | false` / `this.open = true | false`.
- `super.showModal()` (у `GlassModal` нет `showModal()`).
- Слушатели `CustomEvent('open-modal' / 'close')` для открытия/закрытия.

`PlatformFormModal.closeAfterSave()` сбрасывает `isDirty` и вызывает `super.close()`, которая диспатчит `UI_MODAL_CLOSE` с `_modalId`. Прямое `this.open = false` запрещено.

## Структура `apps/<svc>/ui/`

Обязательная схема (см. [`frontend.mdc`](.cursor/rules/frontend.mdc)):

```
apps/<svc>/ui/
  index.html                # import map (@platform/lib/, @platform/services/, lit), tokens.css
  index.js                  # bootstrap: импорт <svc>-app + страниц + модалок + компонентов
  app/<svc>-app.js          # extends PlatformApp; static factories, static defaultI18nNamespace
  events/
    resources/              # все фабрики: '<svc>/<entity>'
      api-keys.resource.js
      embed.resource.js
      ...
    <bridge>.effect.js      # ТОЛЬКО bridge-effects (доменное -> core STORAGE_*/ROUTER_*/AUTH_*)
  components/               # presentational PlatformElement
  pages/                    # PlatformPage; ZERO IMPORT (lit + база + локальные стили)
  modals/                   # PlatformModal / PlatformFormModal
  styles/<svc>.css
  _helpers/                 # доменные id-resolvers (как у sync — sync-id-resolvers.js)
```

**Запрещены** в `apps/<svc>/ui/` (детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.8, п.13 пункт `events/effects`):

- Папки `services/`, `store/`, `stores/`, `features/`.
- Файлы `*.service.js`, `*.store.js`, `*.controller.js`.
- Папки `events/effects/`, `events/reducers/`, `events/<svc>-events.js`, `events/selectors.js`, `events/contract.js` — это всё контракт фабрики, а не сервиса.

**Bridge-effect** допустим **только** как тонкая связка domain-events сервиса с платформенными core-events (`STORAGE_*` / `ROUTER_*` / `WS_*` / `AUTH_*`). Пример: [`apps/sync/ui/events/sync-persist.effect.js`](apps/sync/ui/events/sync-persist.effect.js). Запрещены domain-effects, которые делают HTTP/WS, мутируют доменный slice или содержат бизнес-логику — это контракт фабрик и backend.

## Zero-import canon в pages/ и modals/

Файл `apps/<svc>/ui/pages/<x>.js` и `apps/<svc>/ui/modals/<x>.js` импортирует **только**:

- `lit` (`html`, `css`, `nothing`, ...).
- Базу из `@platform/lib/base/...` (`PlatformPage`, `PlatformModal`, `PlatformFormModal`).
- Core UI Kit-компоненты из `@platform/lib/components/...` (`<glass-card>`, `<platform-icon>`, `<page-header>`, `<platform-trace-viewer>`, `<platform-log-viewer>`, `<platform-user-chip>`, `<glass-spinner>`, `<platform-confirm-modal>` и т.д.).
- Локальные стили / локальные модалки / локальные компоненты сервиса (`../styles/...`, `../modals/...`, `../components/...`).

**Запрещено** (детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13):

- `from '@platform/lib/events/contract.js'` для `dispatch UI_*|ROUTER_*|AUTH_*|I18N_*|THEME_*|COMPANIES_*` — используй helpers.
- `from '@platform/lib/utils/i18n-namespace.js'` (`I18nNs.X`) — пиши `static i18nNamespace = '<ns>'` строкой.
- `from '@platform/lib/base/use-resource.js'` (контроллеры) — только `this.useResource(...)`/`useOp(...)`/....
- `from '../events/resources/*.resource.js'` — фабрики достаются по имени.
- `new ResourceController/OpController/FormController/CursorListController/FacetsController/SliceController` — конструкторы напрямую запрещены.
- `httpRequest` / `fetch` / `axios` — HTTP только в `request` функции `createAsyncOp` / `createResourceCollection` / `createCursorList` / `createFacets`. Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.7.
- `||`, `??` фолбеки в местах чтения. Подробности — следующий раздел.

## Zero-fallback canon (МЕГА-правило)

Дефолт ровно один — `initialSlice` фабрики (или `extraInitial` у `createSlice`). Запрещено:

- `state.items || []`, `state[sliceKey] || initial`, `event.payload || {}`, `(event.payload && event.payload.items) || []`, `payload || null`, `q || ''`, `context || null`, `draft || {}`, `meta || { source: 'local' }` в reducers/effects/контроллерах/публичных методах.
- В `events/resources/**.resource.js` запрещены `|| []`, `|| {}`, `|| null`, `|| ''`, `?? []`, `?? {}`, `?? null`, `?? ''`. Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.15.
- `try { ... } catch { return null }` или `catch { return [] }` в effects: допустимо ловить **только** конкретные исключения (`HttpError`, `WsTransportError`, `SyntaxError` в `JSON.parse`, `DOMException` для `localStorage`/clipboard), и каждое поглощённое исключение **обязано** диспатчить `<X>_FAILED` событие.

Гарантия формы данных — **в одном месте, в фабрике**:

- `mapItem: (raw) => normalized` для `createResourceCollection` / `createCursorList` приводит item к каноничной форме (массивы → `[]`, объекты-словари → `{}`, строки → `''`, числа → `0`). Невалидный item — `throw` (см. [`apps/frontend/ui/events/resources/api-keys.resource.js`](apps/frontend/ui/events/resources/api-keys.resource.js)).
- Для `createAsyncOp` нормализатор живёт в `request` (HTTP) или в `extraReducer` для WS reply (через приватные `_normalize*` helpers).
- `extraReducer` нормализует payload push-событий теми же `_normalize*`-helpers; вход без обязательных строковых ключей **игнорируется** через явные `typeof`-проверки (`if (typeof p.id !== 'string') return state`).
- `extraInitial` всегда задаёт каноничную форму slice через `Object.freeze` (`Object.freeze([])`, `Object.freeze({})`).
- Helper `_get<Entity>Data(state, id)` (как `_getChannelData` в [`apps/sync/ui/events/resources/messages.resource.js`](apps/sync/ui/events/resources/messages.resource.js)) возвращает гарантированно полную форму вложенной сущности.

Выбор источника отображения (`space.space_id` vs `space.id`, `member.name` vs `member.user_id`, `channel.peer.display_name` vs `channel.name`) — только через helpers сервиса в `apps/<svc>/ui/_helpers/<svc>-id-resolvers.js`. Прямой `a || b` для выбора-источника в pages/modals/components — **запрещён**.

## i18n

Канон: [`frontend.mdc`](.cursor/rules/frontend.mdc) (раздел «Internationalization»), [`main.mdc`](.cursor/rules/main.mdc) (раздел про i18n).

- `static i18nNamespace = '<ns>';` в каждом классе с переводами **строкой** ИЛИ `static defaultI18nNamespace = '<ns>'` на `PlatformApp` (приземляется через `setDefaultI18nNamespace`). `I18nNs.X` импорт в pages/modals — **запрещён**.
- Каждый новый ключ — парно `core/i18n/translations/{ru,en}/<ns>.json`. Без пары `ru` + `en` — фича не считается готовой.
- Toast/error ключи фабрики — обязательны, проверяются [`scripts/check_ui_factories.py`](scripts/check_ui_factories.py).
- Динамические ключи (`t('foo.' + status)`) **запрещены**. Если статус конечен (`forbidden`/`unavailable`) — это разные ключи в схеме и разные ветки кода.
- Захардкоженный пользовательский текст (особенно кириллица) вместо `this.t(...)` — **запрещён**.
- Прямой вызов `this.i18n.getCurrentLocale()` / `this.i18n.t(...)` — нет такого `this.i18n`. Используй `this.t(key)` и `this.select((s) => s.i18n.locale)`. Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.14.

CI:

- **`make check-i18n`** — структура JSON-бандлов `ru` / `en`, парность.
- **`make check-i18n-keys`** — cross-check кода ↔ JSON. Каждый вызов `t('key', vars?, namespace?)` в `apps/*/ui/**/*.js` и `core/frontend/static/lib/**/*.js` обязан резолвиться хотя бы в одном из бандлов. Цель: `--mode missing --strict` = exit 0. Детали: [`scripts/check_i18n_keys.py`](scripts/check_i18n_keys.py).
- **`uv run python scripts/report_ui_i18n_gaps.py --app <svc>`** — сканер кириллицы в JS-литералах. Цель: **0** совпадений по сервису.

## UI Components / core UI Kit

Полные правила: [`ui_components.mdc`](.cursor/rules/ui_components.mdc).

| Кейс | Обязательно использовать | Запрет |
|---|---|---|
| Дерево / waterfall spans одного trace | `<platform-trace-viewer>` ([`core/.../components/platform-trace-viewer.js`](core/frontend/static/lib/components/platform-trace-viewer.js)) | Ad-hoc «trace tree» / «span waterfall» в `apps/<svc>/ui/components/`. |
| Список записей логов (Loki ответы) | `<platform-log-viewer>` ([`core/.../components/platform-log-viewer.js`](core/frontend/static/lib/components/platform-log-viewer.js)) | Своя `.log-entry` таблица в сервисе. |
| Любой показ чужого `user_id` | `<platform-user-chip user-id="..." [size="sm|md"] [?interactive=...]>` + клик открывает `platform.user_info` | Сырой `user_id` в pages/modals/components/таблицах; ad-hoc `*-user-row`/`*-user-avatar`. |
| Профиль / редактирование пользователя | core-модалка `platform.user_info` (`<platform-user-info-modal>`), открывается через `this.openModal('platform.user_info', { userId })` | Любая отдельная «модалка профиля» в сервисе. |
| Хлебные крошки | `<platform-breadcrumbs>` (читает `state.router.routes`) | Своя реализация breadcrumbs. |
| Shell-сайдбар сервиса | `<platform-service-sidebar>` (опционально + `<platform-sidebar-nav-tree>` для иерархического меню с `storage-scope`) | Своя оболочка sidebar. |
| Витрина сервисов | `<platform-services-launcher>` + модалка `platform.services` | Дубли каталога в `apps/**`. |
| Заголовок страницы | `<page-header>` (десктоп + mobile sticky) | Свой header в pages. |
| Confirm | `await platformConfirm(message, opts)` | `window.confirm()`, ручные модалки подтверждения. |

Любой UI платформы, который должен показать дерево spans/таймлайн trace или список Loki-логов или чужого пользователя или хлебные крошки — **обязан** использовать соответствующий core-компонент. Дубли в `apps/<svc>/ui/components/` ловятся в code-review и в [`ui_components.mdc`](.cursor/rules/ui_components.mdc).

Если возможностей core-компонента не хватает — расширяй **только в core**, не переноси логику в сервис.

## Sidebar / breadcrumbs / namespace canon

См. [`ui_components.mdc`](.cursor/rules/ui_components.mdc) (раздел «Sidebar / breadcrumbs / namespace canon»).

- Открыть mobile-сайдбар: `dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, null)` (или `this.openSidebar()`).
- Закрыть: `dispatch(CoreEvents.UI_SIDEBAR_CLOSE_REQUESTED, null)` (или `this.closeSidebar()`).
- `<platform-sidebar>` сам диспатчит `UI_SIDEBAR_COLLAPSE_CHANGED` / `UI_SIDEBAR_MOBILE_CHANGED`. Читать состояние — только селектором `state.ui.sidebar`.
- Breadcrumbs — клик по крошке = `dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, { routeKey, params })` (в core разрешено; в apps — `this.navigate(routeKey, params)`).
- Namespace выбор — `setPlatformNamespaceSelection(companyId, name)` диспатчит `CoreEvents.UI_NAMESPACE_SELECT_REQUESTED`. Подписка на смену namespace / перезагрузку — `useEvent(UI_DOCUMENTS_RELOAD_REQUESTED, ...)`.

**Запрещено** (детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.10):

- `window.dispatchEvent(new CustomEvent('platform-sidebar-open' | 'platform-sidebar-mobile-change' | 'office-documents-list-reload'))`.
- `window.addEventListener('platform-sidebar-open' | 'platform-sidebar-mobile-change' | 'office-documents-list-reload', ...)`.
- `new CustomEvent('navigate', ...)` для роутинга.
- `this.calendarApi`, `this.companies`, `this.team` и подобные геттеры в `core/frontend/static/lib/**` — только `dispatch(<SLICE_EVENTS>)` + `select`.

## Backend → UI: «нажать кнопку из бэка»

Backend публикует событие в общий канал `platform:ui_events` через [`core/ui_events/dispatcher.py`](core/ui_events/dispatcher.py):

```python
from core.ui_events import publish_ui_event_to_user
await publish_ui_event_to_user(
    user_id=...,
    type="crm/note/updated",
    payload={"note_id": note_id},
    correlation_id=trace_id,
)
```

WS-эффект форвардит фрейм, фронт диспатчит как обычное событие. Подписанный компонент:

```js
constructor() {
    super();
    this._notes = this.useResource('crm/notes', { autoload: true });
}
connectedCallback() {
    super.connectedCallback();
    this.useEvent('crm/note/updated', () => this._notes.load());
}
```

Имя push-события **не должно** совпадать с командой (без суффикса). Используй разные entity-имена.

## Имена scope сервисов и фабрик (сводка)

| `<svc>` | Сервис | i18n namespace | baseUrl |
|---|---|---|---|
| `frontend` | console / landing | `frontend` (default) | `/frontend/api` |
| `crm` | NetWorkle | `crm` | `/crm/api` |
| `rag` | Knowledge Base | `rag` | `/rag/api` |
| `sync` | Инженерный чат | `sync` | `/sync/api` |
| `office` | OnlyOffice | `office` | `/documents/api` |
| `flows` | AI Studio | `flows` | `/flows/api` |
| `voice` | Voice gateway | `voice` | `/voice/api` |
| `provider_litserve` | LitServe | — | `/litserve/api` |

`baseUrl` фабрики обязан попадать под префикс `/<svc>/api` (для office — `/documents/api`, для provider_litserve — `/litserve/api`). Проверка — [`scripts/check_ui_factories.py`](scripts/check_ui_factories.py).

## Тестирование

Канон: [`testing.mdc`](.cursor/rules/testing.mdc), [`mk/test.mk`](mk/test.mk), [`tests/frontend_core/unit/`](tests/frontend_core/unit/).

Three-layer canon ([`mk/test.mk`](mk/test.mk)):

| Слой | Команда | Что |
|---|---|---|
| Layer 1 — статический канон | `make test-frontend-core-canon` | [`scripts/check_core_frontend_canon.py`](scripts/check_core_frontend_canon.py) — regex по `core/frontend/static/lib/**`. |
| Layer 2 — pure-node unit | `make test-frontend-core-unit` | Vitest + MSW + MockWebSocket в `tests/frontend_core/unit/`. |
| Layer 3 — браузерные | `make test-frontend-core-browser` | Web Test Runner + Playwright Chromium. |
| **Полный**: | `make test-frontend-core` | Все 3 слоя fail-fast. |
| Lit-компоненты сервисов | `make test-ui-components` | Web Test Runner. |
| E2E UI | `make test-ui` | Playwright (`tests/ui/e2e`). |

Между тестами обязательно: `clearFactoryRegistry()` ([`core/frontend/static/lib/events/factory-registry.js`](core/frontend/static/lib/events/factory-registry.js)), `_resetResourceRegistryForTests()` ([`core/frontend/static/lib/events/factories/_internal.js`](core/frontend/static/lib/events/factories/_internal.js)), `resetPlatformBusForTests()`.

Шаблоны:

- **Reducer фабрики** — чистая `(state, event) => state`, unit без mocks, без bus.
- **Effect фабрики** — фейковый `ctx = { dispatch, getState }`; реальный `httpRequest` с моком `fetch` через `msw`/`undici`.
- **Контроллер (use*)** — Web Test Runner, рендер компонента поверх фабрики, проверка по dispatch'ам.
- **E2E** — backend dispatch → UI обновляется; click → reducer → render.

## DevTools

`?platform_devtools=1` в URL включает:

- console-лог каждого события через [`core/frontend/static/lib/events/devtools.js`](core/frontend/static/lib/events/devtools.js);
- `window.__platformDevtools__ = { trail(), state(), dispatch(), clear() }`.

Используй для дебага потока событий. **Не оставляй** `?platform_devtools=1` в коде или ссылках — это runtime-флаг.

## Чек-лист «фича готова» (обязательная последовательность)

Запускать в этом порядке. Любой fail = вернуться к канону, не «обходить».

```bash
# Layer 1 — статический канон UI (apps/**) и core/frontend/static/lib/**
make check-ui-canon
make check-ui-factories
make check-command-rest-mirror
make check-core-frontend-canon  # = uv run python scripts/check_core_frontend_canon.py

# i18n
make check-i18n
make check-i18n-keys
uv run python scripts/report_ui_i18n_gaps.py --app <svc>   # 0 совпадений

# Объединённая цель — должна быть зелёной перед коммитом
make check-events-canon

# Layer 2 — pure-node unit (Vitest)
make test-frontend-core-unit

# Lit-компоненты (если правил core UI Kit или модалки)
make test-ui-components

# Layer 3 — browser (если правил event-flow / SelectController / use*-helpers)
make test-frontend-core-browser
```

Объявляю фичу готовой **только** когда:

1. Все вышеперечисленные команды зелёные.
2. Каждый новый `t('key', ...)` парно есть в `core/i18n/translations/ru/<ns>.json` и `core/i18n/translations/en/<ns>.json`.
3. Каждый новый `<scope>/<entity>/<verb>_requested` имеет REST-зеркало (FastAPI route) в соответствующем `apps/<svc>/api/**`.
4. Каждый новый `<svc>/<entity>` (имя фабрики) уникален в репо и зарегистрирован через `static factories` в `<svc>-app.js`.
5. Каждая новая модалка имеет `static modalKind = '<scope>.<name>'` + `registerModalKind(...)` + рендерится из `platform-modal-stack` (т.е. открывается через `this.openModal(...)`).
6. Никаких `||`/`??` фолбеков в `apps/**/events/resources/**` и в pages/modals/components.
7. Никаких `import { fooResource } from '../events/resources/foo.resource.js'`, `new XController(...)`, `httpRequest(...)`, `fetch(...)`, `this.dispatch(CoreEvents.UI_*)` в pages/modals/components.
8. Все новые поля ввода — `<platform-field>`. Никаких сырых `<input>`/`<textarea>`/`<select>` без `data-canon` или whitelisted `type` (`file|hidden|range|color|checkbox|radio|search`).
9. Никаких `<glass-input>` / `<glass-textarea>` импортов (компоненты удалены).
10. Никаких локальных `.form-*` / `.field-pill*` CSS правил в `static styles` компонентов сервиса; кастомизация — только токены `--field-pill-*` в [`tokens.css`](core/frontend/static/assets/css/tokens.css).
11. Никаких локальных `escapeHtml` / `EMAIL_RE` / `_digitsOnly` / `hash*31` / `formatFileSize` циклов / `Intl.*('ru-RU', ...)` / `toLocale*('ru-RU')`. Используй `core/frontend/static/lib/utils/` (см. раздел «Utility canon»).
12. Никакого своего multipart-upload `createAsyncOp` — только `createMultipartFileUploadOp({ name, url, extraFields? })` из [`@platform/lib/events/index.js`](core/frontend/static/lib/events/factories/_multipart-upload.js).
13. Никаких свободных префиксов localStorage (`humanitec.*`, `<svc>:*`, `sync.chat.*`) — только `platformStorageKey('<scope>', '<key>')` из [`@platform/lib/utils/storage-keys.js`](core/frontend/static/lib/utils/storage-keys.js).
14. В flows LLM editor fallback-модель настраивается тем же полным редактором, что основная LLM-модель. `fallback_models` — ordered array полноценных `LLMCallConfig`; `string[]` и урезанный UI запрещены.

Если что-то из этого нельзя выполнить — задача **не закрыта**. Возвращаюсь к канону, при необходимости — к правке `.cursor/rules/`.

## Анти-паттерны (краткая сводка)

Полный каталог — [`anti-patterns.md`](.cursor/skills/frontend-engineer/anti-patterns.md). Топ-20 типовых костылей и единственно корректные ответы:

| # | Костыль | Корректно | Детектор |
|---|---|---|---|
| 1 | `extends LitElement` | `PlatformElement`/`PlatformPage`/`PlatformModal` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.1 |
| 2 | `fetch(...)` / `axios` / `httpRequest` в `pages/`/`modals/`/`components/` | `request` в `events/resources/*.resource.js` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.7 |
| 3 | `this.services.*` / `this.auth` / `this.notify` / `ServiceRegistry` / `BaseStore` / `AppEvents` | `this.useResource/useOp/...` + helpers | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.4, п.6, п.11 |
| 4 | `import { fooResource } from '../events/resources/foo.resource.js'` / `new ResourceController(...)` | `this.useResource('<svc>/<entity>')` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13 |
| 5 | `this.dispatch(CoreEvents.UI_TOAST_SHOW \| UI_MODAL_OPEN \| ROUTER_NAVIGATE_REQUESTED, ...)` в pages/modals | `this.toast/openModal/closeModal/copyToClipboard/navigate` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13 |
| 6 | `document.createElement('*-modal')` / `appendChild` / `this.open = true` | `this.openModal(SomeModal, props)` / `this.close()` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.9 |
| 7 | `state.items \|\| []`, `payload \|\| {}`, `obj.field ?? '—'`, тихий `try/catch` | `initialSlice`/`extraInitial` + `mapItem`/`_normalize*`; узкий `catch (HttpError)` с dispatch `*_FAILED` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.15 |
| 8 | `I18nNs.FRONTEND` импорт; динамический `t('foo.' + status)`; кириллица в литералах | `static i18nNamespace = 'frontend'`; явные ключи; парные `ru/en` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13, [`check_i18n.sh`](scripts/check_i18n.sh), [`check_i18n_keys.py`](scripts/check_i18n_keys.py), [`report_ui_i18n_gaps.py`](scripts/report_ui_i18n_gaps.py) |
| 9 | Имя события `<scope>/<entity>` (2 сегмента); имя фабрики не `<svc>/<entity>` | `<scope>/<entity>/<verb>` ≥ 3 / `<svc>/<entity>` ровно 2 | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.12, [`check_ui_factories.py`](scripts/check_ui_factories.py) |
| 10 | Ручной `WebSocket` или `fetch` для WS-команды; `restMirror` нет; команда без `_requested` | `transport: 'ws'` + `wsTimeoutMs` + `restMirror` + `commandType` (если имя фабрики ≠ `<svc>/<entity>/<verb>_requested`) | [`check_command_rest_mirror.py`](scripts/check_command_rest_mirror.py), [`check_ui_factories.py`](scripts/check_ui_factories.py) |
| 11 | `new CustomEvent(...)` для cross-component обмена в `apps/<svc>/ui/**` | `this.dispatch(<event>)`; `emit()` оставить только для slot-композиции внутри одного компонента | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.5 |
| 12 | `window.dispatchEvent('platform-sidebar-open' / 'office-documents-list-reload' / 'navigate')` | `dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED)` / `useEvent(UI_DOCUMENTS_RELOAD_REQUESTED)` / `dispatch(ROUTER_NAVIGATE_REQUESTED)` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.10 |
| 13 | `<glass-input>` / `<glass-textarea>` (импорт `@platform/lib/components/glass-input.js`/`glass-textarea.js`) | `<platform-field type='string' input-type='email\|password\|...'>` или `<platform-field type='text'>` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.18 |
| 14 | Локальный `css\`...\`` с правилами `.form-input` / `.form-textarea` / `.form-select` / `.form-group` / `.form-label` / `.field-pill*` в `apps/<svc>/ui/**` | Удалить — стили в [`field-pill.styles.js`](core/frontend/static/lib/styles/shared/field-pill.styles.js); кастомизация только через токены `--field-pill-*` в [`tokens.css`](core/frontend/static/assets/css/tokens.css) | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.17 |
| 15 | Сырые `<input>` / `<textarea>` / `<select>` в `apps/<svc>/ui/{pages,modals,components}/**` без `<platform-field>`, без whitelisted `input type` и без требуемого `data-canon` | `<platform-field type='...'>`; для spec-widget — whitelist `type`/`data-canon` по канону | [`check_field_canon.sh`](scripts/check_field_canon.sh); [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.17 (локальный CSS `.form-*`/`.field-pill*`) |
| 16 | Атрибут `flat` (на `<tag-input>` или любом подкомпоненте) | удалён в PHASE 1.5; pill — единственный режим | ручная проверка в code-review |
| 17 | Локальный `function escapeHtml` / `const escapeHtml = ...` в `apps/<svc>/ui/**` | `import { escapeHtml } from '@platform/lib/utils/escape-html.js'` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.19 |
| 18 | Локальный `EMAIL_RE` / `_digitsOnly` / ad-hoc email regex | `import { isValidEmail, digitsOnly, EMAIL_RE } from '@platform/lib/utils/validators.js'` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.19 |
| 19 | Локальный hash-цикл `h * 31 + charCodeAt`, локальный `_formatBytes`/`_formatFileSize`, локальный `_formatDuration` (mm:ss) | `hashString31`/`hueFromString` из `@platform/lib/utils/hash-string.js`; `formatFileSize` из `@platform/lib/utils/format-file-size.js`; `formatDurationSeconds`/`formatDurationMs` из `@platform/lib/utils/format-duration.js` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.19 |
| 20 | `Intl.NumberFormat('ru-RU', ...)`, `Intl.DateTimeFormat('ru-RU', ...)`, `toLocale*('ru-RU')` хардкод | `formatPlatformNumber`/`formatPlatformCurrencyRub`/`formatPlatformDate*` с локалью из `state.i18n.locale` | [`check_ui_canon.sh`](scripts/check_ui_canon.sh) п.19 |

## Прогрессивные ссылки

- Полный каталог костылей с обоснованием и заменой — [`anti-patterns.md`](.cursor/skills/frontend-engineer/anti-patterns.md).
- Типовые сценарии end-to-end (новый ресурс / команда / **идемпотентная цепочка с ожиданием ответа** / страница / модалка / форма / cursor-list / facets / slice / WS-команда / push-подписка / toast+clipboard / новый i18n-ключ) — [`recipes.md`](.cursor/skills/frontend-engineer/recipes.md).
- Правила платформы:
  - [`.cursor/rules/frontend.mdc`](.cursor/rules/frontend.mdc) — структура `apps/<svc>/ui/`, helpers базы, zero-import canon.
  - [`.cursor/rules/ui_events.mdc`](.cursor/rules/ui_events.mdc) — bus, contract, backend → UI.
  - [`.cursor/rules/ui_factories.mdc`](.cursor/rules/ui_factories.mdc) — полный контракт 6 фабрик.
  - [`.cursor/rules/ui_components.mdc`](.cursor/rules/ui_components.mdc) — core UI Kit, модалки, sidebar, breadcrumbs, user-chip.
  - [`.cursor/rules/architecture.mdc`](.cursor/rules/architecture.mdc) — REST-зеркало команд (платформенный инвариант).
- Ядро (читать перед нетривиальной правкой):
  - [`core/frontend/static/lib/platform-element/index.js`](core/frontend/static/lib/platform-element/index.js)
  - [`core/frontend/static/lib/base/PlatformApp.js`](core/frontend/static/lib/base/PlatformApp.js)
  - [`core/frontend/static/lib/base/PlatformPage.js`](core/frontend/static/lib/base/PlatformPage.js)
  - [`core/frontend/static/lib/base/use-resource.js`](core/frontend/static/lib/base/use-resource.js)
  - [`core/frontend/static/lib/events/contract.js`](core/frontend/static/lib/events/contract.js)
  - [`core/frontend/static/lib/events/factory-registry.js`](core/frontend/static/lib/events/factory-registry.js)
  - [`core/frontend/static/lib/events/factories/`](core/frontend/static/lib/events/factories/)
  - [`core/frontend/static/lib/components/glass-modal.js`](core/frontend/static/lib/components/glass-modal.js)
  - [`core/frontend/static/lib/utils/modal-registry.js`](core/frontend/static/lib/utils/modal-registry.js)
  - [`core/frontend/static/lib/utils/i18n-namespace.js`](core/frontend/static/lib/utils/i18n-namespace.js)

Канон один. Отклонения запрещены. Костыли запрещены.
