# Frontend Anti-Patterns — каталог костылей и единственный корректный ответ

Каждая запись: **симптом → почему это костыль → корректно → детектор CI**. Если детектор не ловит — добавляй детектор первым делом, потом правь код.

См. также: [`SKILL.md`](.cursor/skills/frontend-engineer/SKILL.md), [`recipes.md`](.cursor/skills/frontend-engineer/recipes.md), правила в `.cursor/rules/frontend.mdc` / `ui_events.mdc` / `ui_factories.mdc` / `ui_components.mdc`.

---

## 1. Базовый класс компонента

### 1.1 `extends LitElement` напрямую

ПЛОХО:

```js
import { LitElement, html } from 'lit';
export class MyPage extends LitElement {
    render() { return html`...`; }
}
```

Почему костыль: компонент не получает helpers базы (`dispatch`, `select`, `useResource`, `t`), не интегрирован в bus, не реактивен на `state.i18n.locale`, не имеет `baseStyles`/`glassStyles`/`formStyles`/`buttonStyles`. Дальше команда вынуждена «дотачивать» — это лавинообразно плодит костыли.

ХОРОШО:

```js
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
export class MyPage extends PlatformPage {
    render() { return html`...`; }
}
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.1; [`scripts/check_core_frontend_canon.py`](scripts/check_core_frontend_canon.py).

### 1.2 `extends HTMLElement`

ПЛОХО: ручной web-component без Lit.

ХОРОШО: всегда `PlatformElement` / `PlatformPage` / `PlatformModal` / `PlatformFormModal`.

Детектор: те же.

---

## 2. HTTP в компоненте (pages/modals/components)

### 2.1 `fetch(...)` / `axios` / прямой `httpRequest` в pages

ПЛОХО:

```js
// apps/frontend/ui/pages/api-keys-page.js
async firstUpdated() {
    const r = await fetch('/frontend/api/api-keys');
    this._items = await r.json();
}
```

Почему костыль: state живёт в локальном поле страницы (костыль 4.x), нет нормализации, нет toast при ошибке, нет интеграции с bus, при reload данные дублируются.

ХОРОШО:

```js
// apps/frontend/ui/events/resources/api-keys.resource.js
export const apiKeysResource = createResourceCollection({
    name: 'frontend/api_keys',
    baseUrl: '/frontend/api/api-keys',
    idField: 'key_id',
    operations: ['list', 'create', 'update', 'remove'],
    toastKeys: { /* ... */ },
    mapItem: (raw) => { /* нормализация */ return { ... }; },
});

// apps/frontend/ui/pages/api-keys/api-keys-page.js
constructor() {
    super();
    this._keys = this.useResource('frontend/api_keys', { autoload: true });
}
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.7 (запрет `\bfetch\(` вне `events/effects/**` — а каталога `events/effects/` в сервисах вообще быть не должно).

### 2.2 `httpRequest` в фабрике без обработки `HttpError`

ПЛОХО:

```js
request: async ({ payload }) => {
    try {
        return await httpRequest({ url: '...', method: 'GET' });
    } catch {
        return [];   // тихий фолбек
    }
},
```

Почему костыль: ошибку не видно, FAILED-событие не диспатчится, `lastError` slice пуст, toast не показывается.

ХОРОШО — пробрасывать `HttpError`:

```js
request: async ({ payload }) => {
    return await httpRequest({ url: '...', method: 'GET' });   // throw HttpError -> FAILED через effect фабрики
},
```

Фабрика сама конвертирует `HttpError`/`WsTransportError` в `*_failed` событие. Любая другая ошибка пробрасывается выше — баг должен быть виден.

---

## 3. Старый сервис-канон (this.services и подобные)

### 3.1 `this.services.*`

ПЛОХО:

```js
async _load() {
    this._items = await this.services.api.get('/api-keys');
    this.services.notify.toast('Loaded');
}
```

Почему костыль: `this.services` не существует в платформе (его удалили вместе с `ServiceRegistry`). Если кто-то «починит» это через monkey-patch — это два слоя костылей.

ХОРОШО:

```js
this._keys = this.useResource('frontend/api_keys', { autoload: true });
this.toast('frontend:api_keys_page.loaded');
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.6 (запрет `this\.(services|auth|notify|theme|companies|calendarApi|filesApi|fileTypes|team|a2a|syncWs|syncApi|crmApi|ragApi)\b`).

### 3.2 `BaseStore` / `BaseService` / `AppEvents` / `ServiceRegistry`

ПЛОХО: импорт любого из этих имён.

Почему костыль: модулей не существует. Любая такая запись — поломка сборки или возрождение мёртвой архитектуры.

ХОРОШО: фабрика + helper базы.

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.4.

### 3.3 `this.bus.getState()` в компонентах

ПЛОХО:

```js
const items = this.bus.getState().frontendApiKeys.items;
```

Почему костыль: imperative, не реактивно, рендер не обновится при изменении.

ХОРОШО:

```js
this._keys = this.useResource('frontend/api_keys');
// далее в render(): this._keys.items
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.14.

### 3.4 `await this.dispatch(...)` («fake await»)

ПЛОХО:

```js
await this.dispatch('crm/notes/create_requested', { text: '...' });
this.toast('crm:notes.created');
```

Почему костыль: `dispatch` fire-and-forget, возвращает event-объект, а не Promise результата. `await` ничего не ждёт, toast выскочит до того как запрос дошёл до бэка.

ХОРОШО — `useOp(...).run()`:

```js
const result = await this._createNoteOp.run({ text: '...' });
if (this._createNoteOp.error) return;
this.toast('crm:notes.created');
```

Или — обработать через push: фабрика сама покажет toast по `successToastKey`, отдельный код не нужен.

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.14.

---

## 4. Прямой импорт ресурса / контроллера

### 4.1 `import { fooResource } from '../events/resources/foo.resource.js'` в pages/modals

ПЛОХО:

```js
// apps/frontend/ui/pages/api-keys-page.js
import { apiKeysResource } from '../events/resources/api-keys.resource.js';
constructor() {
    super();
    this._keys = new ResourceController(this, apiKeysResource);
}
```

Почему костыль: дублирует logic регистрации, ломает factory-registry (фабрика может оказаться не зарегистрирована в `static factories`), мешает тестам (нельзя подменить через `clearFactoryRegistry()`).

ХОРОШО:

```js
this._keys = this.useResource('frontend/api_keys', { autoload: true });
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13.

### 4.2 `new ResourceController(this, ...)` / `new OpController(...)`

ПЛОХО:

```js
this._op = new OpController(this, someOp);
```

Почему костыль: тот же — обходит `factory-registry`, ломает контракт «фабрика достаётся по имени».

ХОРОШО:

```js
this._op = this.useOp('<svc>/<op>');
```

Детектор: тот же.

### 4.3 Импорт из `@platform/lib/events/controllers/`

ПЛОХО: такого пути нет. Если кто-то предложит «давай создадим» — это попытка обойти helpers базы.

ХОРОШО: контроллеры экспортируются из [`@platform/lib/base/use-resource.js`](core/frontend/static/lib/base/use-resource.js), но импортировать их в pages/modals — **запрещено**. Только helpers `PlatformElement`.

---

## 5. Прямой dispatch CoreEvents в pages/modals/components

### 5.1 `this.dispatch(CoreEvents.UI_TOAST_SHOW, ...)`

ПЛОХО:

```js
import { CoreEvents } from '@platform/lib/events/contract.js';
this.dispatch(CoreEvents.UI_TOAST_SHOW, {
    type: 'success',
    i18n_key: 'frontend:foo.bar',
});
```

Почему костыль: импорт `CoreEvents` в pages/modals не нужен, форму payload легко перепутать (`message` vs `i18n_key`, `type` vs `severity`), всегда есть готовый helper.

ХОРОШО:

```js
this.toast('foo.bar');                                   // namespace из static i18nNamespace
this.toast('frontend:foo.bar');                          // явный namespace
this.toast('foo.bar', { type: 'error', vars: { x: 1 } });
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13.

### 5.2 `this.dispatch(CoreEvents.UI_MODAL_OPEN, ...)`

ПЛОХО:

```js
this.dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'frontend.api_key_create', props: null });
```

ХОРОШО:

```js
this.openModal(FrontendCreateApiKeyModal);
// или по строке:
this.openModal('frontend.api_key_create', { item: ... });
```

Детектор: тот же.

### 5.3 `this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, ...)`

ПЛОХО:

```js
this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, {
    routeKey: 'channel',
    params: { channelId },
    search: '?focus=...',
});
```

ХОРОШО:

```js
this.navigate('channel', { channelId }, { search: '?focus=...' });
```

Детектор: тот же.

### 5.4 `this.dispatch(CoreEvents.UI_CLIPBOARD_COPY_REQUESTED, ...)`

ПЛОХО: ручное составление payload + риск забыть `success_i18n_key`/`error_i18n_key`.

ХОРОШО:

```js
this.copyToClipboard(secret, {
    success_i18n_key: 'api_key_modal.toast_key_copied',
    error_i18n_key: 'api_key_modal.err_copy_failed',
});
```

---

## 6. Модалки руками

### 6.1 `document.createElement('*-modal')` + `appendChild`

ПЛОХО:

```js
const modal = document.createElement('frontend-create-api-key-modal');
modal.open = true;
document.body.appendChild(modal);
```

Почему костыль: модалка не попадает в `state.modals.stack`, не получает `_modalId`, `closeAfterSave()` не работает, z-index ломается, при роуте не закрывается. Это не просто стиль — это сломанная функциональность.

ХОРОШО:

```js
this.openModal(FrontendCreateApiKeyModal, { /* props */ });
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.9.

### 6.2 `modal.open = true` / `this.open = false`

ПЛОХО: прямая мутация property управления модалкой.

ХОРОШО:

- Открыть: `this.openModal(...)`.
- Закрыть из формы (`PlatformFormModal`): `this.closeAfterSave()` сбрасывает `isDirty` и зовёт `super.close()`.
- Закрыть из кода вне модалки: `this.closeModal('<scope>.<entity>')` или `this.closeModal({ id })`.

Детектор: тот же (`\.open\s*=\s*(true|false)\b`).

### 6.3 Слушатели `CustomEvent('open-modal'|'close')` для cross-component

ПЛОХО:

```js
window.addEventListener('open-modal', (e) => { /* ... */ });
this.dispatchEvent(new CustomEvent('open-modal', { detail: { kind } }));
```

ХОРОШО: `this.openModal(...)` → bus → `<platform-modal-stack>`.

### 6.4 `super.showModal()`

ПЛОХО:

```js
super.showModal();
```

Почему костыль: у `GlassModal` нет `showModal()` (это API нативного `<dialog>`).

ХОРОШО: `this.openModal(SomeModal, props)` снаружи или ничего внутри (модалка открывается стеком).

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.14.

---

## 7. Фолбеки (zero-fallback canon — МЕГА-правило)

### 7.1 `state.items || []` / `state[sliceKey] || initial`

ПЛОХО:

```js
render() {
    const items = (this._keys && this._keys.items) || [];
    return items.map(...);
}
```

Почему костыль: `initialSlice` фабрики уже гарантирует `items: []` через `Object.freeze([])`. Двойной фолбек = недоверие к фабрике + лишний шум, скрывающий реальные баги (если `this._keys` undefined — это ошибка, а не «пустая лента»).

ХОРОШО:

```js
render() {
    const items = this._keys.items;   // фабрика гарантирует array
    return items.map(...);
}
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.15 (только для `events/resources/**`); для pages/modals/components — code-review + правила в [`frontend.mdc`](.cursor/rules/frontend.mdc).

### 7.2 `event.payload || {}` в reducer/effect

ПЛОХО:

```js
extraReducer: (state, event, events) => {
    const item = event.payload || {};
    return { ...state, last: item };
},
```

Почему костыль: payload приходит **типизированным** через узкие нормализаторы. Если payload пустой — это баг бэка/фабрики, его надо ловить, а не маскировать.

ХОРОШО:

```js
extraReducer: (state, event, events) => {
    if (event.type !== events.CREATED) return state;
    const item = event.payload && event.payload.item;
    if (!item || typeof item.id !== 'string') return state;   // явный игнор невалидного push
    return { ...state, last: { id: item.id, name: item.name } };
},
```

### 7.3 `try { ... } catch { return null }` (тихий catch)

ПЛОХО:

```js
try {
    return await httpRequest({ ... });
} catch {
    return null;
}
```

Почему костыль: поглощённое исключение никуда не диспатчится, `*_failed` не происходит, slice.error пуст, toast не показывается, баг невидим.

ХОРОШО (если действительно нужен узкий catch):

```js
try {
    return await httpRequest({ ... });
} catch (err) {
    if (err instanceof HttpError) {
        ctx.dispatch(events.FAILED, { error: { message: err.message, status: err.status } }, { source: 'local' });
        return;
    }
    throw err;   // не HttpError — настоящий баг, пробрасываем
}
```

Идеальный путь — отдать ошибку фабрике: фабрика сама конвертирует `HttpError`/`WsTransportError` в `*_failed`, без ручных try/catch.

### 7.4 `q || ''`, `context || null`, `draft || {}` в публичных методах контроллеров

ПЛОХО:

```js
search(facet, q, context) {
    const query = q || '';
    const ctx = context || null;
    /* ... */
}
```

ХОРОШО — обязывать вызывающий передавать явный аргумент:

```js
search(facet, q, context) {
    if (typeof q !== 'string') {
        throw new Error('search: q required (string, "" — допустимо)');
    }
    /* ... */
}
```

Реализация платформы — [`FacetsController.search`](core/frontend/static/lib/base/use-resource.js) бросает на пустом facet, проверяет тип context.

---

## 8. i18n

### 8.1 `import { I18nNs } from '@platform/lib/utils/i18n-namespace.js'` в pages/modals

ПЛОХО:

```js
import { I18nNs } from '@platform/lib/utils/i18n-namespace.js';
static i18nNamespace = I18nNs.FRONTEND;
```

Почему костыль: лишний импорт, ломает zero-import canon, `I18nNs` нужен только в core. К тому же `defaultI18nNamespace` `PlatformApp` уже снимает необходимость объявления namespace в каждом классе.

ХОРОШО — строкой:

```js
static i18nNamespace = 'frontend';
```

Или вообще ничего, если в `PlatformApp` объявлен `static defaultI18nNamespace = 'frontend';`.

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13.

### 8.2 Динамические ключи `t('foo.' + status)`

ПЛОХО:

```js
return this.t('foo.' + status);   // status: 'forbidden' | 'unavailable'
```

Почему костыль: [`scripts/check_i18n_keys.py`](scripts/check_i18n_keys.py) такие ключи не валидирует, опечатка станет багом в проде. Кроме того, нельзя автоматически найти неиспользуемые ключи.

ХОРОШО — явные ветки:

```js
if (status === 'forbidden')   return this.t('foo.forbidden');
if (status === 'unavailable') return this.t('foo.unavailable');
throw new Error(`unknown status: ${status}`);
```

### 8.3 Хардкод кириллицы / эмодзи вместо `t(...)`

ПЛОХО:

```js
return html`<button>Сохранить</button>`;
```

Почему костыль: нет EN-перевода, нарушает [`main.mdc`](.cursor/rules/main.mdc) («Новый функционал = i18n с парой ru/en сразу»).

ХОРОШО:

```js
return html`<button>${this.t('common:action_save')}</button>`;
```

Плюс пара ключей в `core/i18n/translations/{ru,en}/common.json`.

Детекторы: [`uv run python scripts/report_ui_i18n_gaps.py --app <svc>`](scripts/report_ui_i18n_gaps.py) (кириллица в JS-литералах), [`scripts/check_i18n_keys.py`](scripts/check_i18n_keys.py) (`--mode missing --strict`), [`scripts/check_i18n.sh`](scripts/check_i18n.sh) (структура / парность).

### 8.4 Toast-ключ без namespace (`successToastKey: 'foo.bar'`)

ПЛОХО:

```js
createAsyncOp({
    name: 'frontend/foo',
    successToastKey: 'foo.bar',     // нет namespace
    errorToastKey: 'foo.error',
});
```

ХОРОШО:

```js
successToastKey: 'frontend:foo.bar',
errorToastKey:   'frontend:foo.error',
```

Детектор: [`scripts/check_ui_factories.py`](scripts/check_ui_factories.py) (бросает `ERROR ... toast-ключ '...' без namespace`).

### 8.5 `this.i18n.t(...)` / `this.i18n.getCurrentLocale()`

ПЛОХО: такого `this.i18n` не существует.

ХОРОШО:

```js
this.t('key', vars, namespace?);
this.select((s) => s.i18n.locale);
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.14.

---

## 9. Имена событий и фабрик

### 9.1 Имя события < 3 сегмента или не snake_case

ПЛОХО:

```js
this.dispatch('foo/bar', {});
this.dispatch('Foo/Bar/Baz', {});
this.dispatch('foo-bar/baz/qux', {});
```

Почему костыль: [`assertEventType`](core/frontend/static/lib/events/contract.js) бросит при `dispatch`. Регулярка: `^[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*){2,}$`.

ХОРОШО:

```js
this.dispatch('crm/note/created', payload);
this.dispatch('frontend/api_keys/secret_dismissed', null);
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.12 + сама [`assertEventType`](core/frontend/static/lib/events/contract.js).

### 9.2 Имя фабрики не `<svc>/<entity>`

ПЛОХО:

```js
createAsyncOp({ name: 'crm.notes.create', ... });   // точки, 3 сегмента
createAsyncOp({ name: 'notes/create', ... });        // нет <svc>
createAsyncOp({ name: 'crm/notes_create', ... });    // ровно 2 — но имя должно быть про сущность
```

Почему костыль: ломает routing через `factory-registry` и резолв slice key.

ХОРОШО:

```js
createAsyncOp({ name: 'crm/note_create', ... });
createResourceCollection({ name: 'crm/notes', ... });
```

Детектор: [`scripts/check_ui_factories.py`](scripts/check_ui_factories.py) — формат `<svc>/<entity>`, `<svc>` совпадает с каталогом.

### 9.3 WS-команда без `_requested`

ПЛОХО:

```js
createAsyncOp({
    name: 'sync/calls_invite',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'sync/calls/invite',     // нет _requested
});
```

Почему костыль: [`assertEventType`](core/frontend/static/lib/events/contract.js) пройдёт, но фабрика бросит — `commandType must end with "_requested"`. Backend-handler в `core.websocket.command_router` тоже отказывается регистрироваться без суффикса.

ХОРОШО:

```js
commandType: 'sync/calls/invite_requested',
```

---

## 10. WS / REST-зеркало команд

### 10.1 Ручной `WebSocket` или `fetch` для WS-команды в effect

ПЛОХО:

```js
// своя effect-функция
const ws = new WebSocket('/sync/api/ws/notifications');
ws.send(JSON.stringify({ type: 'sync/calls/invite_requested', payload }));
```

Почему костыль: дубль платформенного [`ws.effect.js`](core/frontend/static/lib/events/effects/ws.effect.js); нет `request_id`, нет timeout, нет authentication, нет retry.

ХОРОШО — фабрика с `transport: 'ws'`:

```js
export const callInviteOp = createAsyncOp({
    name: 'sync/calls_invite',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    commandType: 'sync/calls/invite_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/invite' },
});
```

И из компонента: `await this._invite.run({ call_id })`.

### 10.2 WS-фабрика без `restMirror`

ПЛОХО:

```js
createAsyncOp({
    name: 'sync/calls_invite',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'sync/calls/invite_requested',
    // нет restMirror
});
```

Почему костыль: фабрика бросит на старте (REST-зеркало — платформенный инвариант, см. [`architecture.mdc`](.cursor/rules/architecture.mdc)). Кроме того, без REST невозможно использовать команду из CLI/SDK/тестов без WS-стенда.

ХОРОШО — `restMirror` обязателен и должен указывать на реальный FastAPI route в `apps/<svc>/api/**`:

```js
restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/invite' },
```

Детектор: [`scripts/check_command_rest_mirror.py`](scripts/check_command_rest_mirror.py).

### 10.3 Fallback с WS на HTTP в коде

ПЛОХО:

```js
try {
    return await runViaWs(payload);
} catch {
    return await runViaHttp(payload);   // запрещено
}
```

Почему костыль: транспорт выбирается **один раз** в фабрике через `transport`. Если WS оборвался — операция падает в `*_failed` с `error_code: 'ws_disconnected'|'ws_timeout'`, retry — задача пользователя, не fallback на HTTP.

ХОРОШО: только один транспорт. Если задаче нужен HTTP — `transport: 'http'`.

### 10.4 Push-событие с именем команды

ПЛОХО:

```python
# backend
await publish_ui_event_to_user(
    user_id=...,
    type="sync/messages/send",   # совпадает с именем команды (без _requested)
    payload={"message": ...},
)
```

Почему костыль: коллизия с командой `sync/messages/send_requested` запутывает наблюдателя bus и может ломать reducer фабрик, которые слушают и команды, и push.

ХОРОШО — разные entity-имена:

```python
type="sync/message/created"   # другое entity (message vs messages)
```

Детектор: [`scripts/check_command_rest_mirror.py`](scripts/check_command_rest_mirror.py).

---

## 11. Cross-component через `CustomEvent`

### 11.1 `new CustomEvent(...)` в `apps/<svc>/ui/**`

ПЛОХО:

```js
window.dispatchEvent(new CustomEvent('crm-notes-reload', { detail: { id } }));
window.addEventListener('crm-notes-reload', (e) => { /* ... */ });
```

Почему костыль: глобальный bus в обход `EventBus`, нет логирования в EventLog, нет devtools, нет автоматической отписки.

ХОРОШО:

```js
// отправить:
this.dispatch('crm/notes/reload_requested', { id });

// слушать:
this.useEvent('crm/notes/reload_requested', ({ payload }) => {
    this._notes.load(payload);
});
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.5.

### 11.2 `this.emit(name, detail)` для cross-app/cross-component обмена

ПЛОХО:

```js
// ChildA emit -> ChildB слушает в другой ветке dom
this.emit('reload-list', null);
```

Почему костыль: `emit` создаёт DOM-событие с `composed: true`, но это не bus. Cross-app коммуникация через DOM-bubble хрупкая — слушатель может оказаться вне дерева. К тому же ломает devtools.

ХОРОШО:

- Для slot/composed-композиции **внутри одного компонента** (parent ↔ slotted child) — `this.emit('change', detail)` ОК.
- Для всего остального — `this.dispatch(...)`.

Правило в [`frontend.mdc`](.cursor/rules/frontend.mdc): «`emit` — DOM-событие parent←child через slot/composed-boundary; запрещено для cross-component / cross-app обмена».

---

## 12. Sidebar / breadcrumbs / namespace через `window`

### 12.1 `window.dispatchEvent('platform-sidebar-open')`

ПЛОХО:

```js
window.dispatchEvent(new CustomEvent('platform-sidebar-open'));
```

ХОРОШО:

```js
this.openSidebar();
// или явно:
this.dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, null);
```

### 12.2 `window.addEventListener('office-documents-list-reload', ...)`

ПЛОХО: глобальный listener на legacy-событие.

ХОРОШО:

```js
this.useEvent(CoreEvents.UI_DOCUMENTS_RELOAD_REQUESTED, () => this._docs.load());
```

### 12.3 `new CustomEvent('navigate', ...)` для роутинга

ПЛОХО:

```js
this.dispatchEvent(new CustomEvent('navigate', { detail: { routeKey: 'team' } }));
```

ХОРОШО:

```js
this.navigate('team');
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.10.

---

## 13. Структура `apps/<svc>/ui/`

### 13.1 Папка `apps/<svc>/ui/services/`

ПЛОХО: возрождает старый `BaseService` канон.

ХОРОШО — фабрика в `events/resources/*.resource.js`. Фактически старый «сервис» = одна или несколько фабрик.

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.8.

### 13.2 Папка `apps/<svc>/ui/store/` или `stores/` или `features/`

ПЛОХО: импорт Zustand, MobX, своего `BaseStore`.

ХОРОШО — slice фабрики (`createSlice` или `createResourceCollection.extraInitial`).

Детектор: тот же.

### 13.3 Файлы `*.service.js`, `*.store.js`, `*.controller.js` в `apps/<svc>/ui/`

ПЛОХО.

ХОРОШО — соответствующая фабрика в `events/resources/*.resource.js`.

### 13.4 Папки `events/effects/`, `events/reducers/`, файлы `events/<svc>-events.js`, `events/selectors.js`, `events/contract.js`

ПЛОХО: дубль контракта core. Каждая фабрика **сама** содержит свой reducer, effect, события и селекторы. Сервису это не нужно.

ХОРОШО:

- Domain-effects не существуют. Если нужен «домен → core STORAGE_*/ROUTER_*» — это **bridge-effect**, кладётся в `events/<svc>-persist.effect.js` (по образцу [`apps/sync/ui/events/sync-persist.effect.js`](apps/sync/ui/events/sync-persist.effect.js)).
- Domain-reducers пишутся внутри фабрик (`extraReducer`).
- Selectors — из фабрики (`factory.selectors`).

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.13 (запрет `apps/<svc>/ui/events/effects`).

---

## 13bis. Идемпотентность команд: ручные busy-флаги, гонки, дубли

Полный рецепт — [`recipes.md`](.cursor/skills/frontend-engineer/recipes.md) рецепт 2bis. Полное правило — раздел «Идемпотентные команды» в [`SKILL.md`](.cursor/skills/frontend-engineer/SKILL.md).

### 13bis.1 Ручной `this._busy = true / false`

ПЛОХО:

```js
async _onCreate() {
    if (this._busy) return;
    this._busy = true;
    try {
        await this._createOp.run(payload);
    } finally {
        this._busy = false;
    }
}
render() {
    return html`<button ?disabled=${this._busy} @click=${this._onCreate}>...</button>`;
}
```

Почему костыль: дубль контракта `createAsyncOp.busy` / `createResourceCollection.createInFlight`. Любая ошибка ветви (раннее `return`, exception до `try`, повторный rerender) — флаг не сбросится, кнопка зависнет. Кроме того, не реактивен между разными компонентами (другая страница не увидит, что команда в полёте).

ХОРОШО:

```js
constructor() {
    super();
    this._createOp = this.useOp('crm/note_create');
}
render() {
    return html`<button ?disabled=${this._createOp.busy} @click=${() => this._createOp.run(payload)}>...</button>`;
}
```

Для `createResourceCollection.create`:

```js
this._namespaces = this.useResource('crm/namespaces');
// далее:
?disabled=${this._namespaces.createInFlight}
```

Канон: [`apps/crm/ui/modals/namespace-modal.js`](apps/crm/ui/modals/namespace-modal.js): `this._createForm.submitting || this._namespaces.createInFlight` — комбинация двух платформенных флагов, **никаких** локальных `_busy`.

### 13bis.2 `?disabled=${this._res.loading}` для кнопки «Создать»

ПЛОХО:

```js
<button ?disabled=${this._items.loading} @click=${() => this._items.create(payload)}>Создать</button>
```

Почему костыль: `loading` в `ResourceController` относится **только** к `list`-операции (см. [`use-resource.js`](core/frontend/static/lib/base/use-resource.js): `get loading() { return Boolean(this.state.loading); }`). Во время первой загрузки списка кнопка «Создать» дизейблится без причины; во время `create` — наоборот, не дизейблится, и пользователь успевает кликнуть второй раз.

ХОРОШО:

```js
<button ?disabled=${this._items.createInFlight} @click=${() => this._items.create(payload)}>Создать</button>
```

### 13bis.3 Несколько `_requested` подряд (без `await`)

ПЛОХО:

```js
_onSubmit() {
    this._entities.create({ entity_type: 'task', name: 'Foo' });
    this._relationships.create({ from_entity_id: noteId, to_entity_id: '???' });   // нет id ещё
    this.toast('crm:tasks.created');
}
```

Почему костыль: `dispatch` — fire-and-forget. Второй `create` стартует, не зная id первого. Toast выскочит до подтверждения с бэка. Это race condition в чистом виде.

ХОРОШО — последовательно через `_waitForResourceResult` или `OpController.run()`:

```js
async _onSubmit() {
    const task = await this._createEntity({ entity_type: 'task', name: 'Foo' });
    if (!task) return;
    await this._createRelationship({
        from_entity_id: noteId,
        to_entity_id: task.entity_id,
        relationship_type: 'has_task',
    });
    // toast purchases автоматически из toastKeys фабрики; вручную не зовём.
}
```

Канон: [`apps/crm/ui/pages/note-page.js`](apps/crm/ui/pages/note-page.js).

### 13bis.4 Подписка `useEvent('<...>/succeeded')` без фильтра по `causation_id`

ПЛОХО:

```js
this.useEvent('crm/note_search/succeeded', (event) => {
    this._results = event.payload.result.items;
    this._loading = false;
});
```

Почему костыль: ловишь **все** ответы, в т.ч. от устаревших запросов и от других компонентов. При быстром наборе текста (debounce + старые ответы прилетают позже) — поздний ответ перезапишет свежий, UI «прыгает».

ХОРОШО — фильтр по `causation_id` твоего dispatch:

```js
const requested = this._search.run({ query: this._draft });
this._lastSearchRequestId = requested.id;

this.useEvent('crm/note_search/succeeded', (event) => {
    if (event.meta && event.meta.causation_id !== this._lastSearchRequestId) return;
    this._results = event.payload.result.items;
    this._loading = false;
});
```

Канон: [`apps/crm/ui/pages/daily-notes-page.js`](apps/crm/ui/pages/daily-notes-page.js), [`apps/crm/ui/components/note-card-view.js`](apps/crm/ui/components/note-card-view.js) (`_mentionRequestId` / `_voiceSearchRequestId` / `_contextSearchRequestId` — у каждого использования одной и той же op'ы свой `requestId`).

### 13bis.5 `await this.dispatch(...)` (fake await)

ПЛОХО:

```js
await this.dispatch('crm/notes/create_requested', { text });
this.toast('crm:notes.created');
```

Почему костыль: `dispatch` возвращает event-объект, не Promise результата. `await` ничего не ждёт. Toast выскочит до того, как запрос дошёл до бэка. Если бэк вернёт 4xx — toast уже показан.

ХОРОШО — `OpController.run()`:

```js
const result = await this._createNote.run({ text });
if (this._createNote.error) {
    // toast 'error' уже показан фабрикой (errorToastKey) или тут руками
    return;
}
// `successToastKey` фабрики уже показал toast — лишний this.toast не нужен
```

Канон: [`use-resource.js`](core/frontend/static/lib/base/use-resource.js) — `OpController.run()` строит Promise через `subscribeType` + `causation_id`.

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.14.

### 13bis.6 Утечка подписок при ожидании SUCCEEDED

ПЛОХО:

```js
async _create(payload) {
    const requested = this._entities.create(payload);
    return await new Promise((resolve) => {
        this.bus.subscribeType('crm/entities/created', (event) => {
            if (event.meta.causation_id === requested.id) {
                resolve(event.payload.item);
                // забыли отписаться — на следующий create предыдущий callback тоже выстрелит
            }
        });
    });
}
```

Почему костыль: подписка остаётся, а Promise уже зарезолвился. Каждый последующий `create` накапливает зомби-listener'ов.

ХОРОШО — снимать подписку в `cleanup()`:

```js
return new Promise((resolve, reject) => {
    let offSuccess = null, offFailed = null;
    const cleanup = () => {
        if (typeof offSuccess === 'function') offSuccess();
        if (typeof offFailed === 'function') offFailed();
    };
    offSuccess = this.bus.subscribeType('crm/entities/created', (event) => {
        if (!event.meta || event.meta.causation_id !== requested.id) return;
        cleanup();
        resolve(event.payload.item);
    });
    offFailed = this.bus.subscribeType('crm/entities/create_failed', (event) => {
        if (!event.meta || event.meta.causation_id !== requested.id) return;
        cleanup();
        reject(new Error(event.payload.message));
    });
});
```

Канон: [`apps/crm/ui/pages/note-page.js`](apps/crm/ui/pages/note-page.js) (`_waitForResourceResult`), [`apps/crm/ui/modals/knowledge-import-modal.js`](apps/crm/ui/modals/knowledge-import-modal.js) (`_awaitOp`).

### 13bis.7 `ResourceController.create` без проверки `requested.id`

ПЛОХО:

```js
async _createEntity(payload) {
    const requested = this._entities.create(payload);
    return await this._waitForResourceResult(this._entities, requested.id);  // requested === undefined → TypeError
}
```

Почему костыль: при `createInFlight === true` контроллер возвращает `undefined` (см. [`use-resource.js`](core/frontend/static/lib/base/use-resource.js)). `requested.id` бросит TypeError, и идёт обвал стека.

ХОРОШО:

```js
async _createEntity(payload) {
    const requested = this._entities.create(payload);
    if (!requested || typeof requested.id !== 'string') {
        throw new Error('createEntity: create dispatch returned no id (already in flight?)');
    }
    return await this._waitForResourceResult(this._entities, requested.id);
}
```

Канон: [`apps/crm/ui/pages/note-page.js`](apps/crm/ui/pages/note-page.js) (`_createEntity`, `_createRelationship`).

---

## 14. Стейт без фабрики

### 14.1 Локальное поле страницы вместо slice

ПЛОХО:

```js
constructor() {
    super();
    this._items = [];
    this._loading = false;
}
async firstUpdated() {
    this._loading = true;
    this._items = await fetch('/...').then(r => r.json());
    this._loading = false;
    this.requestUpdate();
}
```

Почему костыль: state не в bus, нельзя реагировать на push-события, нельзя поделить с другой страницей, при reroute теряется.

ХОРОШО — `createResourceCollection` + `useResource`.

### 14.2 `state.foo = bar` (мутация frozen state)

ПЛОХО: бросает в strict-mode или ломает реактивность.

ХОРОШО: state меняется только через reducer (внутри фабрики). Для UI-only state — `createSlice` + actions.

### 14.3 «Псевдо-slice» через `useEvent` + локальные поля

ПЛОХО:

```js
this.useEvent('crm/notes/created', (e) => {
    this._notes.push(e.payload);
    this.requestUpdate();
});
```

ХОРОШО — `extraReducer` фабрики `crm/notes`:

```js
extraReducer: (state, event, events) => {
    if (event.type === events.CREATED) {
        const item = event.payload && event.payload.item;
        if (!item) return state;
        return { ...state, items: [...state.items, item] };
    }
    return state;
},
```

И в компоненте — просто `this._notes.items` (реактивно).

---

## 15. Тесты

### 15.1 Не вызывать `clearFactoryRegistry()` между тестами

ПЛОХО: первый тест регистрирует фабрику, второй пытается зарегистрировать ту же — `throw`.

ХОРОШО:

```js
beforeEach(() => {
    clearFactoryRegistry();
    _resetResourceRegistryForTests();
    resetPlatformBusForTests();
});
```

### 15.2 Мок reducer / effect фабрики

ПЛОХО: `vi.spyOn(factory, 'reducer')` — это нарушение контракта чистой функции.

ХОРОШО: тестировать reducer как чистую `(state, event) => state`. Effect — фейковым `ctx = { dispatch, getState }`, реальный `httpRequest` с `msw`.

### 15.3 Утекающие компоненты в Lit-тестах

ПЛОХО: `document.body.appendChild(el)` без очистки.

ХОРОШО: использовать стандартный `fixture` Web Test Runner с автоматической очисткой.

---

## 16. CSS / стили

### 16.1 Хардкод цветов / отступов

ПЛОХО:

```css
.btn { background: #2563eb; padding: 8px 16px; }
```

Почему костыль: ломается тёмная/светлая тема, не отвечает редизайну.

ХОРОШО — токены из [`core/frontend/static/assets/css/tokens.css`](core/frontend/static/assets/css/tokens.css):

```css
.btn {
    background: var(--accent);
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-md);
    color: var(--text-on-accent);
}
```

### 16.2 Свой `position:fixed` для модалки

ПЛОХО: модалка не попадает в `<platform-modal-stack>`, ломаются предки с `backdrop-filter`.

ХОРОШО: использовать `PlatformModal`/`PlatformFormModal`. Они сами переносятся в `document.body` при открытии (см. [`glass-modal.js`](core/frontend/static/lib/components/glass-modal.js)).

### 16.3 Свой `z-index` для всплывающих

ПЛОХО: `z-index: 9999` без координации.

ХОРОШО: `nextModalLayerZIndex()` ([`core/frontend/static/lib/utils/modal-z-stack.js`](core/frontend/static/lib/utils/modal-z-stack.js)) или CSS-переменная `--platform-modal-layer-z`.

---

## 17. Неиспользуемые core-компоненты (создание дублей)

### 17.1 Своя «trace tree» в сервисе

ПЛОХО: `apps/flows/ui/components/flows-trace-tree.js`, `apps/sync/ui/components/sync-trace-spans.js` — каждый со своим CSS и поведением.

ХОРОШО: `<platform-trace-viewer>` ([`core/frontend/static/lib/components/platform-trace-viewer.js`](core/frontend/static/lib/components/platform-trace-viewer.js)). Если возможностей не хватает — расширяй **в core**.

Правило: [`ui_components.mdc`](.cursor/rules/ui_components.mdc) (раздел «Platform Trace Viewer»).

### 17.2 Своя «таблица логов»

ПЛОХО: ad-hoc `.log-entry` список.

ХОРОШО: `<platform-log-viewer>`.

### 17.3 Свой компонент пользователя

ПЛОХО: `<sync-user-row>`, `<crm-user-avatar>`, `<flows-user-cell>` — каждый со своей версткой.

ХОРОШО: `<platform-user-chip user-id="..." [size="sm|md"] [?interactive=...]>`. Клик автоматически открывает модалку `platform.user_info`.

### 17.4 Свой confirm

ПЛОХО:

```js
if (window.confirm('Точно удалить?')) { /* ... */ }
```

ХОРОШО:

```js
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
const ok = await platformConfirm(this.t('foo.confirm_delete', { name: x.name }), {
    title: this.t('foo.delete_title'),
    variant: 'danger',
    confirmText: this.t('common:action_delete'),
    cancelText: this.t('common:action_cancel'),
});
if (!ok) return;
```

---

## 18. `<svc>-app.js` без `static factories`

ПЛОХО:

```js
export class FrontendApp extends PlatformApp {
    getServiceSlices() {
        return { someManualSlice: { reducer, initial } };   // дубль фабрики
    }
}
```

Почему костыль: пишет slice вручную там, где нужна фабрика; теряет автоматический effect, события, селекторы, REST-зеркало.

ХОРОШО:

```js
export class FrontendApp extends PlatformApp {
    static defaultI18nNamespace = 'frontend';
    static factories = [apiKeysResource, /* ... */];
}
```

`getServiceSlices()` оставляй пустым; `getServiceEffects()` — только для платформенных core-effects (`createRouterEffect`, `createSyncPersistEffect()` и т.п.).

---

## 19. Импорты в обход import map

### 19.1 `from '/static/core/lib/...'`

ПЛОХО:

```js
import { PlatformElement } from '/static/core/lib/platform-element/index.js';
```

ХОРОШО:

```js
import { PlatformElement } from '@platform/lib/platform-element/index.js';
```

Детектор: [`scripts/check_ui_canon.sh`](scripts/check_ui_canon.sh) п.2.

### 19.2 Импорт из `apps/<other>/ui/**`

ПЛОХО:

```js
// apps/flows/ui/pages/foo.js
import { syncSomething } from '../../../sync/ui/components/sync-channel-row.js';
```

Почему костыль: cross-service зависимость через UI. Если общее — место в `core/frontend/static/lib/`.

ХОРОШО: переносим переиспользуемое в `core/frontend/static/lib/components/`.

---

## 20. Новый функционал без обновления rules

ПЛОХО: добавил новый паттерн (новый kind фабрики, новый core-компонент, новое helper'а в `PlatformElement`), но `.cursor/rules/*.mdc` не обновил.

Почему костыль: правило сразу устаревает, новая фича не обязательная для других → лавина «у меня было сделано иначе».

ХОРОШО:

1. Сначала — правка соответствующего `.mdc` (rule).
2. Потом — код.
3. Потом — детектор в `scripts/check_*` если применимо.

См. [`main.mdc`](.cursor/rules/main.mdc): «Новое = правка рулов».

---

## 21. Игнорирование `make check-events-canon`

ПЛОХО: «починю позже», «коммитим без проверки», `--no-verify`.

Почему костыль: CI отлавливает 90% перечисленного выше. Игнор = пропуск регрессии в master.

ХОРОШО: перед коммитом / закрытием задачи — обязательно

```bash
make check-events-canon
make check-i18n-keys
uv run python scripts/report_ui_i18n_gaps.py --app <svc>
make test-frontend-core-canon
```

Все зелёные — только тогда задача считается закрытой.

---

## 22. «Временный workaround» / «потом отрефакторим»

ПЛОХО:

```js
// TODO: убрать костыль, временно вернём пустой список при ошибке
items = [];
```

Почему костыль: «временно» становится «навсегда». Кроме того, тихий фолбек скрывает баг от мониторинга.

ХОРОШО:

- Если действительно не успеваем починить причину — открыть отдельный тикет, в коде явный `throw new Error('not implemented: X')`. Пусть страница упадёт, чем тихо отдаст пустоту.
- Если причина нашлась — починить, не оставлять следов.

Канон: [`main.mdc`](.cursor/rules/main.mdc) → «АБСОЛЮТНЫЕ ЗАПРЕТЫ» → 1 (никаких фолбеков), 2 (никаких лишних try-except), 3 (никаких проглоченных исключений), 7 (никаких неявных фолбеков в значениях).

---

## 23. Урезанный UI для `fallback_models`

ПЛОХО: fallback-модель как строка, отдельное маленькое поле `model`, без `provider`/`base_url`/`temperature`/headers/body, или без drag-and-drop порядка.

Почему костыль: fallback — не «имя запасной модели», а полноценная LLM-попытка с тем же контрактом, что основная модель. Урезанный UI создаёт второй смысл данных и ломает backend-архитектуру.

ХОРОШО: `fallback_models: LLMCallConfig[]`, тот же редактор полей, раскрывающиеся элементы, порядок массива меняется drag-and-drop. Новое поле LLM-конфига появляется одновременно у основной модели и fallback.

Канон: [`flows.mdc`](.cursor/rules/flows.mdc) → «LLM fallback-модели».

---

## Дискуссия и эскалация

Если правило в `.cursor/rules/` мешает решить задачу честно — это сигнал, что правило устарело **или** задача неверно сформулирована. Не надо обходить правило в коде. Надо:

1. Сформулировать конфликт.
2. Предложить правку правила (в том же PR).
3. Получить апрув на новое правило.
4. Реализовать.

«Реализовал в обход правила, потом обновим» — запрещено. Это и есть тот самый костыль.
