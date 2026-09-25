# Frontend Recipes — пошаговые сценарии

Каждый рецепт — путь от фабрики до компонента. Нормы, которые рецепт выполняет, — в `.cursor/rules/ui_factories.mdc`, `ui_components.mdc`, `ui_fields.mdc`, `frontend.mdc`; здесь только шаги. После любого рецепта — гейты из `SKILL.md` § 5.

## 1. CRUD-коллекция (`createResourceCollection`)

Эталон: [`api-keys.resource.js`](apps/frontend/ui/events/resources/api-keys.resource.js) + [`api-keys-page.js`](apps/frontend/ui/pages/api-keys/api-keys-page.js).

1. Проверить backend: `GET/POST /<svc>/api/<entities>`, `GET/PATCH/DELETE /<svc>/api/<entities>/{<entity>_id}` и команды `<svc>/<entities>/{list,create,update,remove}_requested`.
2. Файл `apps/<svc>/ui/events/resources/<entity>.resource.js`:

```js
import { createResourceCollection } from '@platform/lib/events/index.js';

export const widgetsResource = createResourceCollection({
    name: '<svc>/widgets',
    baseUrl: '/<svc>/api/widgets',
    idField: 'widget_id',
    operations: ['list', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    toastKeys: { create: '<svc>:widgets.toast_created', update: '<svc>:widgets.toast_updated', remove: '<svc>:widgets.toast_removed' },
    mapItem: (raw) => {
        if (typeof raw.widget_id !== 'string') throw new Error('<svc>/widgets.mapItem: widget_id required');
        return { widget_id: raw.widget_id, name: raw.name, tags: raw.tags };
    },
});
```

3. `apps/<svc>/ui/app/<svc>-app.js`: импорт и `static factories = [widgetsResource, …]`.
4. Страница: `this._widgets = this.useResource('<svc>/widgets', { autoload: true })`; список — `this._widgets.items`, строка занята — `this._widgets.isBusy(id)`, кнопка «создать» — `?disabled=${this._widgets.createInFlight}`.
5. Ключи toast — парой в `core/i18n/translations/{ru,en}/<svc>.json` (§ 12).
6. Нестандартный путь операции — запись `restMirror: { update: { method: 'PUT', path: '/<svc>/api/widgets/:widget_id' } }`; операция вне CRUD — отдельный `createAsyncOp` (§ 2).

## 2. Команда (`createAsyncOp`)

Эталоны: `tracingTraceLoadOp` в [`tracing.resource.js`](apps/frontend/ui/events/resources/tracing.resource.js), `callInviteOp` в [`calls.resource.js`](apps/sync/ui/events/resources/calls.resource.js).

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

1. WS-фабрике `request` не нужен: фабрика шлёт кадр `commandType` и ждёт `*_succeeded`/`*_failed`.
2. HTTP-вариант (сервис вне `COMMAND_WS_SERVICES` или allowlist) — `request: async ({ payload }) => httpRequest({ method, url, body })`; проверка обязательных полей payload — `throw`, `HttpError` не ловим.
3. Toast — `silent: true` либо пара `successToastKey` + `errorToastKey`; своя реакция на ошибку — `onFailure(ctx, …)`.
4. Компонент: `this._invite = this.useOp('sync/calls_invite')`; кнопка — `?disabled=${this._invite.busy}`; вызов — `const result = await this._invite.run({ call_id })`, ошибка — `this._invite.error` (`run` на FAILED резолвит `null`).

## 3. Цепочка команд и ожидание исхода

Эталоны: [`namespace-modal.js`](apps/crm/ui/modals/namespace-modal.js) (lock create), [`daily-notes-page.js`](apps/crm/ui/pages/daily-notes-page.js) (фильтр по `lastRequestId`), [`note-page.js`](apps/crm/ui/pages/note-page.js) (`_waitForResourceResult`), [`knowledge-import-modal.js`](apps/crm/ui/modals/knowledge-import-modal.js) (`_awaitOp`).

| Задача | Шаг |
|---|---|
| кнопка «создать» | `?disabled=${res.createInFlight}`; форма + коллекция — `form.submitting \|\| res.createInFlight` |
| кнопка действия | `?disabled=${op.busy}` + `await op.run(payload)` |
| нужен `result` для следующего шага | `await op.run(payload)` или `op.lastResult` |
| нужен созданный `item` коллекции | helper ожидания `CREATED` по `causation_id` (ниже) |
| поиск с debounce | фильтр `useEvent` по `op.lastRequestId` |

Ожидание созданного элемента коллекции:

```js
async _createEntity(payload) {
    const requested = this._entities.create(payload);
    if (!requested || typeof requested.id !== 'string') {
        throw new Error('createEntity: create already in flight');
    }
    return new Promise((resolve, reject) => {
        const { CREATED, CREATE_FAILED } = this._entities.resource.events;
        const offOk = this.bus.subscribeType(CREATED, (event) => {
            if (event.meta.causation_id !== requested.id) return;
            offOk(); offFail(); resolve(event.payload.item);
        });
        const offFail = this.bus.subscribeType(CREATE_FAILED, (event) => {
            if (event.meta.causation_id !== requested.id) return;
            offOk(); offFail(); reject(new Error(event.payload.message));
        });
    });
}
```

Поиск с debounce — ответ устаревшего запроса отбрасывается:

```js
this.useEvent(this._search.op.events.SUCCEEDED, (event) => {
    if (event.meta.causation_id !== this._search.lastRequestId) return;
    this._results = event.payload.result.items;
});
```

## 4. Лента (`createCursorList`)

Эталон: `tracingSpansList` в [`tracing.resource.js`](apps/frontend/ui/events/resources/tracing.resource.js).

```js
export const tracingSpansList = createCursorList({
    name: 'frontend/tracing_spans',
    baseUrl: '/frontend/api/platform-tracing/spans',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'frontend/platform_tracing/spans_requested',
    pageSize: 50,
    buildQuery: _buildSpansQuery,
    statusMap: { 403: 'forbidden', 503: 'unavailable' },
    errorToastKey: 'frontend:tracing_page.load_error',
});
```

1. `buildQuery(filters)` — чистая функция; WS-payload = REST-query `{ ...buildQuery(filters), limit, cursor? }`, payload команды на backend совпадает с query REST-зеркала.
2. Компонент: `this._spans = this.useCursorList('frontend/tracing_spans', { autoload: true })`; `items`, `hasMore`, `loadingMore`, `terminal` (`forbidden`/`unavailable`), `loadMore()`, `changeFilters(patch)`, `resetFilters()`.

## 5. Typeahead (`createFacets`)

Эталон: `tracingFacets` в [`tracing.resource.js`](apps/frontend/ui/events/resources/tracing.resource.js).

1. Фабрика: `facets: { companies: 'companies', users: 'users' }`, `debounceMs: 200`, `minQueryLength: 2`; URL — `${baseUrl}/${facets[key]}`, транспорт HTTP.
2. Компонент: `this._facets = this.useFacets('frontend/tracing_facets')`; ввод — `<platform-field type="string" input-type="search" @change=${(e) => this._facets.search('companies', e.detail.value)}>`; результат — `this._facets.items('companies')`, загрузка — `this._facets.loading('companies')`.

## 6. Форма (`createForm`)

```js
export const widgetCreateForm = createForm({
    name: '<svc>/widget_create_form',
    schema: { name: { required: true, minLength: 1, maxLength: 64, errorKey: '<svc>:widget_modal.err_name' } },
    initial: { name: '' },
    submitEvent: widgetsResource.events.CREATE_REQUESTED,
});
```

1. Регистрация — рядом с коллекцией в `static factories`.
2. Модалка: `this._form = this.useForm('<svc>/widget_create_form')`; `openForm(initial)` в `connectedCallback`, поле — `<platform-field .value=${this._form.draft.name} @change=${(e) => this._form.setField('name', e.detail.value)}>`, ошибки — `this._form.errors`, отправка — `this._form.submit()`, дизейбл — `this._form.submitting`.

## 7. UI-only slice (`createSlice`)

Эталоны: `sync/call_ui` в [`calls.resource.js`](apps/sync/ui/events/resources/calls.resource.js), `sync/presence` в [`presence.resource.js`](apps/sync/ui/events/resources/presence.resource.js).

```js
export const callUiSlice = createSlice({
    name: 'sync/call_ui',
    extraInitial: { activeCall: null, overlayMinimized: false },
    extraEvents: { OVERLAY_MINIMIZED: 'overlay_minimized' },
    actions: { minimizeOverlay: 'overlay_minimized' },
    extraReducer: (state, event, events) => {
        if (event.type === 'sync/call/ended') return { ...state, activeCall: null, overlayMinimized: false };
        if (event.type === events.OVERLAY_MINIMIZED) return { ...state, overlayMinimized: true };
        return state;
    },
});
```

Компонент: `this._callUi = this.useSlice('sync/call_ui')`; чтение — `this._callUi.value`, действие — `this._callUi.minimizeOverlay(null)`.

## 8. Страница и маршрут

Эталон: [`api-keys-page.js`](apps/frontend/ui/pages/api-keys/api-keys-page.js).

1. `apps/<svc>/ui/pages/<entity>-page.js` — `class … extends PlatformPage`, `static i18nNamespace = '<svc>'` (или `defaultI18nNamespace` приложения), импорт `lit`, `@platform/lib/**` и локальных модулей сервиса.
2. Разметка: `<platform-breadcrumbs>` первым (динамический хвост — `current-label`), `<page-header title subtitle>` с кнопками в `slot="actions"`, тело — данные контроллеров, загрузка — `<platform-spinner>`.
3. Маршрут в `getRoutes()` приложения: `{ key: 'widgets', path: 'widgets', titleKey: 'routes.widgets' }`, вложенный — `{ key: 'widget', path: 'widgets/:widgetId', parent: 'widgets', titleKey: 'routes.widget' }`.
4. `renderRoute(routeKey, params)` → тег страницы; импорт страницы в `<svc>-app.js`.
5. `routes.<key>` в ru и en; таб мобильной навигации — § 10.
6. Вложенность внутри маршрута (дерево, папки) — `.trail=${[{ label, routeKey, params }]}` у `<platform-breadcrumbs>`.

## 9. Модалка

Эталон: [`create-api-key-modal.js`](apps/frontend/ui/modals/create-api-key-modal.js).

```js
import { html } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

export class WidgetCreateModal extends PlatformFormModal {
    static modalKind = '<svc>.widget_create';
    static properties = { ...PlatformFormModal.properties, _name: { state: true } };
    constructor() { super(); this._name = ''; this.size = 'md'; this._widgets = this.useResource('<svc>/widgets'); }
    willUpdate(changed) { super.willUpdate(changed); this.title = this.t('widget_modal.header_create'); }
    validateForm() { return this._name.trim() ? {} : { name: this.t('widget_modal.err_name') }; }
    async handleSubmit() { this._widgets.create({ name: this._name.trim() }); this.closeAfterSave(); }
    renderFormBody() {
        return html`<platform-field type="string" .label=${this.t('widget_modal.field_name')}
            .value=${this._name} @change=${(e) => { this._name = e.detail.value; }}></platform-field>`;
    }
}
customElements.define('<svc>-widget-create-modal', WidgetCreateModal);
registerModalKind(WidgetCreateModal.modalKind, '<svc>-widget-create-modal');
```

1. Модуль модалки импортируется в `<svc>-app.js` или в странице, иначе реестр не знает kind.
2. Открытие — `this.openModal(WidgetCreateModal)` или `this.openModal('<svc>.widget_create', props)`; закрытие снаружи — `this.closeModal('<svc>.widget_create')`.
3. Подтверждение — `const ok = await platformConfirm(this.t('widgets.confirm_delete'), { title, variant: 'danger', confirmText, cancelText })` из `@platform/lib/components/platform-confirm-modal.js`.

## 10. Bottom sheet и таб навигации

```js
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';

export class WidgetFilterSheet extends PlatformBottomSheet {
    static bottomSheetKind = '<svc>.widget_filter';
    static i18nNamespace = '<svc>';
    connectedCallback() { super.connectedCallback(); this.heading = this.t('widgets.filter_title'); }
    renderBody() { /* поля фильтра */ }
}
customElements.define('<svc>-widget-filter-sheet', WidgetFilterSheet);
registerBottomSheetKind(WidgetFilterSheet.bottomSheetKind, '<svc>-widget-filter-sheet');
```

1. Открытие — `this.openBottomSheet('<svc>.widget_filter', props)`; `snap = 'full'` — для длинного содержимого.
2. Таб: `static bottomNavItems = [{ key: 'widgets', routeKey: 'widgets', icon: 'list', labelKey: 'bottom_nav.widgets' }, { key: 'me', sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.me' }]`; полноэкранные маршруты — `static bottomNavHideOnRoutes`.
3. `bottom_nav.<key>` в ru и en; top-bar — `static topBarEnabled = true`.

## 11. Push с backend → мерж в фабрике

Эталоны: `crm/access_requests` в [`access-requests.resource.js`](apps/crm/ui/events/resources/access-requests.resource.js), досинхронизация — `crm/tasks` в [`tasks.resource.js`](apps/crm/ui/events/resources/tasks.resource.js).

1. Backend: `register_platform_event` в `apps/<svc>/events.py`, публикация `publish_event_to_user(s)` в сервисе; имя push — другое entity, чем у команды (`crm/note/updated` при команде `crm/notes/update_requested`) → `events.mdc`.
2. Тип push — константа в `apps/<svc>/ui/events/types.js`.
3. Мерж — `extraReducer` фабрики, которая владеет данными:

```js
extraReducer: (state, event) => {
    if (event.type !== WIDGET_UPDATED) return state;
    const widget = event.payload.widget;
    if (!widget || typeof widget.widget_id !== 'string') return state;
    return upsertItem(state, widget, 'widget_id');
},
```

4. Данные, которые не мержатся из события (граф, карточка со связями), — `rerunLastRequest(ctx, op, { when })` или `reloadLastList(ctx, resource)` в `extraEffect`/`onSuccess`; после переподключения сокета — `extraEffect` на `CoreEvents.WS_CONNECTED`.
5. В странице — только UI-реакция без данных: `this.useEvent(WIDGET_UPDATED, (e) => this._highlight(e.payload.widget.widget_id))`.

## 12. Ключ i18n

1. Ключ в `core/i18n/translations/ru/<ns>.json` и `en/<ns>.json` одной структурой: `{ "widgets": { "toast_created": "Виджет создан" } }` / `"Widget created"`; переменные — `{{name}}`.
2. Код: `this.t('widgets.toast_created')`, чужой namespace — `this.t('action_save', null, 'common')`; toast-ключ фабрики — `'<ns>:widgets.toast_created'`.
3. Конечный набор статусов — отдельный ключ на статус и явная ветка кода.
4. Прогон: `make check-i18n`, `make check-i18n-keys`, `uv run python scripts/report_ui_i18n_gaps.py --app <svc>`.

## 13. Bridge-effect

Эталон: [`sync-persist.effect.js`](apps/sync/ui/events/sync-persist.effect.js).

```js
import { CoreEvents } from '@platform/lib/events/contract.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

const SELECTED_KEY = platformStorageKey('<svc>', 'selected_widget_id');

export function create<Svc>PersistEffect() {
    return (event, ctx) => {
        if (event.type === '<svc>/widgets/widget_selected') {
            ctx.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, { key: SELECTED_KEY, value: event.payload.widget_id }, { source: 'local' });
        }
    };
}
```

Подключение — `getServiceEffects() { return [createRouterEffect(ROUTES), create<Svc>PersistEffect()]; }`. HTTP, WS и мутация slice в bridge-effect не пишутся.

## 14. Загрузка файла

1. `static factories` приложения содержит `platformFileCreateOp` (`@platform/lib/events/factories/platform-file-create.js`); отдельное имя — `createPlatformFileCreateOp({ name: '<svc>/file_create' })`.
2. Компонент: `this._upload = this.useOp('platform/file_create')`; `await this._upload.run({ file, spec })`, где `spec` — JSON-строка `FileCreateSpec` (→ `files.mdc` § Загрузка), прогресс — `onProgress`.
3. Результат — `FileRef` в `this._upload.lastResult` (`file_id`, `original_name`, `content_type`); дальше в команду уходит `file_id`, не байты.

## 15. Core-компонент UI Kit и тесты

1. Файл `core/frontend/static/lib/components/platform-<name>.js`: `extends PlatformElement`, presentational — только `t()` и `this.emit(...)`; container — `select`/`use*`; прямой `dispatch(CoreEvents.*)` — только здесь.
2. UIKDS-карточка `tests/ui/design-system/components/platform-<name>/`: `README.md`, `README.en.md`, `manifest.yaml`, `contract.spec.js`, `playwright.spec.py`; запись в `tests/ui/design-system/catalog.yaml`.
3. i18n компонента — namespace `platform` (`core/i18n/translations/{ru,en}/platform.json`).
4. Тест фабрики: reducer — `(state, event) => state` без bus; effect — фейковый `ctx = { dispatch, getState }`; контроллер — WTR, перед каждым тестом `clearFactoryRegistry()`, `_resetResourceRegistryForTests()`, `resetPlatformBusForTests()`, затем `registerFactory(factory)`.
5. Прогон: `make ui`; сценарии и доки UIKDS — `make ui-doc`; компонентные тесты сервисов — `make test-ui-components`.
