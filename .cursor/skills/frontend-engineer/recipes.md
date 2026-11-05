# Frontend Recipes — пошаговые сценарии на TS

Рецепт — путь от фабрики до компонента. Нормы — `ui_factories.mdc`, `ui_components.mdc`, `ui_fields.mdc`, `frontend.mdc`; после любого рецепта — гейты `SKILL.md` § Гейты перед «готово». Живые файлы фабрик и страниц содержат остаток (`.cursor/skills/frontend-engineer/scripts/ui_audit.py`): форма берётся из рецепта, живой файл — только пример API.

## Типизация во всех рецептах

Рецепты записаны в форме `references/target-architecture.md` § Типовой контракт:

- Модуль фабрик регистрирует каждое имя в `PlatformFactoryRegistry` (блок `declare module` в § 1); `use*` принимает только зарегистрированное имя своего вида.
- Тип состояния `S` — аннотация параметра `state` в `extraReducer` типом slice, объявленным рядом с фабрикой; тип элемента коллекции — возврат `mapItem`; методы контроллера — ключи `actions`.
- Поле контроллера — инициализатор `private readonly _x = this.useX('<svc>/<entity>')` (тип выводится) или объявление `ControllerFor<'<svc>/<entity>'>` (`@platform/lib/base/use-resource.js`, только `import type`).
- Тип элемента коллекции ограничен `ResourceItem` (`TItem extends ResourceItem`): объектный тип (`type Widget = { … }`), не `interface` без индекс-сигнатуры. Ограничение снимает корень «внутренности фабрик без erased-типов» (`idField: keyof TItem`).
- Нет `wire.gen.ts` сервиса — тип объявляется в файле фабрики, функция границы `require<Entity>(raw: ResourceItem): <Entity>` проверяет обязательные поля и бросает; открытый корень «Wire-типы из Pydantic» называется в отчёте.
- Нужной возможности нет в kit (generic `createForm`, `createCursorList`, `createFacets`, типизированная статическая конфигурация баз) — корень P2, рекурсия; при ограниченной границе — блокер `kit_gap`. Каст, `any`, non-null и переобъявление типа в странице не заменяют ни один шаг.

## 1. CRUD-коллекция (`createResourceCollection`)

1. Backend: `GET/POST /<svc>/api/<entities>`, `GET/PATCH/DELETE /<svc>/api/<entities>/{<entity>_id}` и команды `<svc>/<entities>/{list,create,update,remove}_requested`.
2. Файл `apps/<svc>/ui/events/resources/<entity>.resource.ts`:

```ts
import { createResourceCollection } from '@platform/lib/events/index.js';
import { requireWidget } from '../wire.gen.js';

export const widgetsResource = createResourceCollection({
    name: '<svc>/widgets',
    baseUrl: '/<svc>/api/widgets',
    idField: 'widget_id',
    operations: ['list', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    toastKeys: { create: '<svc>:widgets.toast_created', update: '<svc>:widgets.toast_updated', remove: '<svc>:widgets.toast_removed' },
    mapItem: requireWidget,
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        '<svc>/widgets': typeof widgetsResource;
    }
}
```

3. `apps/<svc>/ui/app/<svc>-app.ts`: импорт и `static factories = [widgetsResource, …]`.
4. Страница: `private readonly _widgets = this.useResource('<svc>/widgets', { autoload: true })`; список — `this._widgets.items` (`readonly Widget[]`), строка занята — `this._widgets.isBusy(id)`, кнопка «создать» — `?disabled=${this._widgets.createInFlight}`.
5. Ключи toast — парой в `core/i18n/translations/{ru,en}/<svc>.json` (§ 12).
6. Нестандартный путь операции — `restMirror: { update: { method: 'PUT', path: '/<svc>/api/widgets/:widget_id' } }`; операция вне CRUD — отдельный `createAsyncOp` (§ 2).

## 2. Команда (`createAsyncOp`)

```ts
export const callInviteOp = createAsyncOp({
    name: 'sync/calls_invite',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    commandType: 'sync/calls/invite_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/invite' },
});
```

1. Payload и результат выводятся из `CommandMap['sync/calls/invite_requested']`; WS-фабрике `request` не нужен: она шлёт кадр `commandType` и ждёт `*_succeeded`/`*_failed`.
2. HTTP-вариант (сервис вне `COMMAND_WS_SERVICES` или allowlist) — `request: async ({ payload }) => requireInviteResult(await httpRequest({ method, url, body: payload }))`; `HttpError` не ловится.
3. Toast — `silent: true` либо пара `successToastKey` + `errorToastKey`; своя реакция на ошибку — `onFailure(ctx, …)`.
4. Регистрация имени — блок `declare module` как в § 1.
5. Компонент: `private readonly _invite = this.useOp('sync/calls_invite')`; кнопка — `?disabled=${this._invite.busy}`; вызов — `const result = await this._invite.run({ call_id: callId })`; `null` — ошибка уже в `this._invite.error` и toast фабрики.

## 3. Цепочка команд и ожидание исхода

| Задача | Шаг |
|---|---|
| кнопка «создать» | `?disabled=${resource.createInFlight}`; форма + коллекция — `form.submitting \|\| resource.createInFlight` |
| кнопка действия | `?disabled=${op.busy}` + `await op.run(payload)` |
| результат для следующего шага | `await op.run(payload)` или `op.lastResult` |
| созданный элемент коллекции | ожидание `CREATED` по `causation_id` (ниже) |
| поиск с debounce | фильтр `useEvent` по `op.lastRequestId` |

```ts
private _createEntity(payload: CrmEntityCreate): Promise<CrmEntity> {
    const requested = this._entities.create(payload);
    if (!requested) throw new Error('createEntity: create already in flight');
    const requestId = requested.id;
    const { CREATED, CREATE_FAILED } = this._entities.resource.events;
    return new Promise((resolve, reject) => {
        const offOk = this.bus.subscribeType(CREATED, (event) => {
            if (event.meta.causation_id !== requestId) return;
            offOk(); offFail(); resolve(event.payload.item);
        });
        const offFail = this.bus.subscribeType(CREATE_FAILED, (event) => {
            if (event.meta.causation_id !== requestId) return;
            offOk(); offFail(); reject(new Error(event.payload.message));
        });
    });
}
```

Поиск с debounce — ответ устаревшего запроса отбрасывается:

```ts
this.useEvent(this._search.op.events.SUCCEEDED, (event) => {
    if (event.meta.causation_id !== this._search.lastRequestId) return;
    this._results = event.payload.result.items;
});
```

## 4. Лента (`createCursorList`)

```ts
export const tracingSpansList = createCursorList({
    name: 'frontend/tracing_spans',
    baseUrl: '/frontend/api/platform-tracing/spans',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'frontend/platform_tracing/spans_requested',
    pageSize: 50,
    buildQuery: buildSpansQuery,
    mapItem: requireTraceSpan,
    statusMap: { 403: 'forbidden', 503: 'unavailable' },
    errorToastKey: 'frontend:tracing_page.load_error',
});
```

1. `buildQuery(filters: SpansFilters)` — чистая функция; WS-payload равен REST-query `{ ...buildQuery(filters), limit, cursor? }`.
2. Компонент: `private readonly _spans = this.useCursorList('frontend/tracing_spans', { autoload: true })`; `items`, `hasMore`, `loadingMore`, `terminal` (`forbidden`/`unavailable`), `loadMore()`, `changeFilters(patch)`, `resetFilters()`.

## 5. Typeahead (`createFacets`)

1. Фабрика: `facets: { companies: 'companies', users: 'users' }`, `debounceMs: 200`, `minQueryLength: 2`; URL — `${baseUrl}/${facets[key]}`, транспорт HTTP.
2. Компонент: `private readonly _facets = this.useFacets('frontend/tracing_facets')`; ввод — `<platform-field type="string" input-type="search" @change=${(event: PlatformFieldChangeEvent<string>) => this._facets.search('companies', event.detail.value)}>`; результат — `this._facets.items('companies')`, загрузка — `this._facets.loading('companies')`.

## 6. Форма (`createForm`)

```ts
export const widgetCreateForm = createForm<WidgetCreateDraft>({
    name: '<svc>/widget_create_form',
    schema: { name: { required: true, minLength: 1, maxLength: 64, errorKey: '<svc>:widget_modal.err_name' } },
    initial: { name: '' },
    submitEvent: widgetsResource.events.CREATE_REQUESTED,
});
```

1. Регистрация — рядом с коллекцией в `static factories` и в `PlatformFactoryRegistry`.
2. Модалка: `private readonly _form = this.useForm('<svc>/widget_create_form')`; `openForm(initial)` в `connectedCallback`; поле — `<platform-field .value=${this._form.draft.name} @change=${(event: PlatformFieldChangeEvent<string>) => this._form.setField('name', event.detail.value)}>`; ошибки — `this._form.errors`; отправка — `this._form.submit()`; дизейбл — `this._form.submitting`.

## 7. UI-only slice (`createSlice`)

```ts
export const callUiSlice = createSlice({
    name: 'sync/call_ui',
    extraInitial: { activeCall: null, overlayMinimized: false },
    extraEvents: { OVERLAY_MINIMIZED: 'overlay_minimized' },
    actions: { minimizeOverlay: 'overlay_minimized' },
    extraReducer: (state: SyncCallUiSlice, event, events) => {
        if (event.type === SYNC_CALL_ENDED) return { ...state, activeCall: null, overlayMinimized: false };
        if (event.type === events.OVERLAY_MINIMIZED) return { ...state, overlayMinimized: true };
        return state;
    },
});
```

Компонент: `private readonly _callUi = this.useSlice('sync/call_ui')`; чтение — `this._callUi.value.overlayMinimized`, действие — `this._callUi.minimizeOverlay(null)`: payload действия обязателен, пустое событие несёт `null`. Точный тип `value` — аннотация `extraReducer: (state: SyncCallUiSlice, event, events) => …`; `extraInitial` проверяется по тому же типу.

## 8. Страница и маршрут

```ts
import { html } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import type { Widget } from '../events/wire.gen.js';

export class WidgetsPage extends PlatformPage {
    static i18nNamespace = '<svc>';
    private readonly _widgets = this.useResource('<svc>/widgets', { autoload: true });

    override render(): TemplateResult {
        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <page-header .title=${this.t('widgets.title')}></page-header>
            ${this._widgets.loading
                ? html`<platform-spinner></platform-spinner>`
                : this._widgets.items.map((widget) => this._renderRow(widget))}
        `;
    }

    private _renderRow(widget: Widget): TemplateResult {
        return html`<div class="row">${widget.name}</div>`;
    }
}
customElements.define('<svc>-widgets-page', WidgetsPage);
```

1. Разметка: `<platform-breadcrumbs>` первым (динамический хвост — `current-label`), `<page-header>` с кнопками в `slot="actions"`, тело — данные контроллеров, загрузка — `<platform-spinner>`.
2. Маршрут в `getRoutes()` приложения: `{ key: 'widgets', path: 'widgets', titleKey: 'routes.widgets' }`, вложенный — `{ key: 'widget', path: 'widgets/:widgetId', parent: 'widgets', titleKey: 'routes.widget' }`.
3. `renderRoute(routeKey, params)` → тег страницы; импорт страницы в `<svc>-app.ts`.
4. `routes.<key>` в ru и en; таб мобильной навигации — § 10.
5. Вложенность внутри маршрута (дерево, папки) — `.trail=${[{ label, routeKey, params }]}` у `<platform-breadcrumbs>`.

## 9. Модалка

```ts
import { html } from 'lit';
import type { PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

export class WidgetCreateModal extends PlatformFormModal {
    static modalKind = '<svc>.widget_create';
    static override properties: PropertyDeclarations = { ...PlatformFormModal.properties, _name: { state: true } };
    declare _name: string;
    private readonly _widgets = this.useResource('<svc>/widgets');

    constructor() {
        super();
        this._name = '';
        this.size = 'md';
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('widget_modal.header_create');
    }

    override validateForm(): Record<string, string> {
        return this._name.trim() ? {} : { name: this.t('widget_modal.err_name') };
    }

    override async handleSubmit(): Promise<void> {
        this._widgets.create({ name: this._name.trim() });
        this.closeAfterSave();
    }

    override renderBody(): TemplateResult {
        return html`<platform-field type="string" .label=${this.t('widget_modal.field_name')} .value=${this._name}
            @change=${(event: PlatformFieldChangeEvent<string>) => { this._name = event.detail.value; }}></platform-field>`;
    }
}
customElements.define('<svc>-widget-create-modal', WidgetCreateModal);
registerModalKind(WidgetCreateModal.modalKind, '<svc>-widget-create-modal');
```

1. Модуль модалки импортируется в `<svc>-app.ts` или в странице, иначе реестр не знает kind.
2. Открытие — `this.openModal(WidgetCreateModal)` или `this.openModal('<svc>.widget_create', props)`; закрытие снаружи — `this.closeModal('<svc>.widget_create')`.
3. Подтверждение — `if ((await platformConfirm(this.t('widgets.confirm_delete'), { title, variant: 'danger', confirmText, cancelText })) !== true) return;` (`@platform/lib/components/platform-confirm-modal.js`).
4. `PlatformFieldChangeEvent<T>` — тип события kit (`references/target-architecture.md` § Типовой контракт п.7); нет экспорта в kit — срез kit, а не `any` в обработчике.

## 10. Bottom sheet и таб навигации

```ts
import { html } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';

export class WidgetFilterSheet extends PlatformBottomSheet {
    static bottomSheetKind = '<svc>.widget_filter';
    static i18nNamespace = '<svc>';

    override connectedCallback(): void {
        super.connectedCallback();
        this.heading = this.t('widgets.filter_title');
    }

    override renderBody(): TemplateResult {
        return html`…`;
    }
}
customElements.define('<svc>-widget-filter-sheet', WidgetFilterSheet);
registerBottomSheetKind(WidgetFilterSheet.bottomSheetKind, '<svc>-widget-filter-sheet');
```

1. Открытие — `this.openBottomSheet('<svc>.widget_filter', props)`; `snap = 'full'` — для длинного содержимого.
2. Таб: `static bottomNavItems = [{ key: 'widgets', routeKey: 'widgets', icon: 'list', labelKey: 'bottom_nav.widgets' }, { key: 'me', sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.me' }]`; полноэкранные маршруты — `static bottomNavHideOnRoutes`.
3. `bottom_nav.<key>` в ru и en; top-bar — `static topBarEnabled = true`.

## 11. Push с backend → мерж в фабрике

1. Backend: `register_platform_event` в `apps/<svc>/events.py`, публикация `publish_event_to_user(s)` в сервисе; имя push — другое entity, чем у команды (`crm/note/updated` при команде `crm/notes/update_requested`) → `events.mdc`.
2. Тип push — константа в `apps/<svc>/ui/events/types.ts`; payload — из `PlatformEventMap` (`wire.gen.ts`).
3. Мерж — `extraReducer` фабрики-владельца данных:

```ts
extraReducer: (state, event) => {
    if (event.type !== WIDGET_UPDATED) return state;
    const widget = event.payload.widget;
    if (typeof widget.widget_id !== 'string') return state;
    return upsertItem(state, widget, 'widget_id');
},
```

4. Данные, которые не мержатся из события (граф, карточка со связями), — `rerunLastRequest(ctx, op, { when })` или `reloadLastList(ctx, resource)` в `extraEffect`/`onSuccess`; после переподключения сокета — `extraEffect` на `CoreEvents.WS_CONNECTED`.
5. В странице — только UI-реакция без данных: `this.useEvent(WIDGET_UPDATED, (event) => this._highlight(event.payload.widget.widget_id))`.

## 12. Ключ i18n

1. Ключ в `core/i18n/translations/ru/<ns>.json` и `en/<ns>.json` одной структурой: `{ "widgets": { "toast_created": "Виджет создан" } }` / `"Widget created"`; переменные — `{{name}}`.
2. Код: `this.t('widgets.toast_created')`, чужой namespace — `this.t('action_save', null, 'common')`; toast-ключ фабрики — `'<ns>:widgets.toast_created'`.
3. Конечный набор статусов — отдельный ключ на статус и явная ветка кода с `throw` на неизвестном.
4. Прогон: `make check-i18n`, `make check-i18n-keys`, `uv run python -m scripts.tools.report_ui_i18n_gaps --app <svc>`.

## 13. Bridge-effect

```ts
import { CoreEvents } from '@platform/lib/events/contract.js';
import type { EffectCtx, PlatformEvent } from '@platform/lib/events/contract.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

const SELECTED_KEY = platformStorageKey('<svc>', 'selected_widget_id');

export function create<Svc>PersistEffect(): (event: PlatformEvent, ctx: EffectCtx) => void {
    return (event, ctx) => {
        if (event.type !== WIDGET_SELECTED) return;
        ctx.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, { key: SELECTED_KEY, value: event.payload.widget_id }, { source: 'local' });
    };
}
```

Подключение — `override getServiceEffects() { return [createRouterEffect({ routes: ROUTES }), create<Svc>PersistEffect()]; }`. HTTP, WS и мутация slice в bridge-effect не пишутся. Пример API — `apps/sync/ui/events/sync-persist.effect.ts`.

## 14. Загрузка файла

1. `static factories` приложения содержит `platformFileCreateOp` (`@platform/lib/events/factories/platform-file-create.js`); отдельное имя — `createPlatformFileCreateOp({ name: '<svc>/file_create' })`.
2. Компонент: `private readonly _upload = this.useOp('platform/file_create')`; `await this._upload.run({ file, spec })`, где `spec` — JSON-строка `FileCreateSpec` (→ `files.mdc` § Загрузка).
3. Результат — `FileRef` (`file_id`, `original_name`, `content_type`); дальше в команду уходит `file_id`, не байты.

## 15. Core-компонент UI Kit и тесты

1. Файл `core/frontend/static/lib/components/platform-<name>.ts`: `extends PlatformElement`; presentational — только `t()` и `this.emit(...)`; container — `select`/`use*`; прямой `dispatch(CoreEvents.*)` — только здесь. Тип каждого события компонента экспортируется из его файла.
2. UIKDS-карточка `tests/ui/design-system/components/platform-<name>/`: `README.md`, `README.en.md`, `manifest.yaml`, `contract.spec.ts`, `playwright.spec.py`; запись в `tests/ui/design-system/catalog.yaml`.
3. i18n компонента — namespace `platform` (`core/i18n/translations/{ru,en}/platform.json`).
4. Тест фабрики: reducer — `(state, event) => state` без bus; effect — фейковый `ctx = { dispatch, getState }`; контроллер — WTR на настоящей фабрике, перед каждым тестом `clearFactoryRegistry()`, `_resetResourceRegistryForTests()`, `resetPlatformBusForTests()`, затем `registerFactory(factory)`.
5. Прогон: `make ui`; сценарии и доки UIKDS — `make ui-doc`; компонентные тесты — `make test-ui-components`.

## 16. Конверсия файла `.js` → `.ts`

1. `git mv x.js x.ts` — история файла сохраняется; спецификаторы импортёров не меняются: `from './x.js'` резолвится в `x.ts`.
2. Реактивные поля Lit:

```ts
static override properties: PropertyDeclarations = { label: { type: String }, count: { type: Number } };
declare label: string;
declare count: number;
```

   `declare` обязателен: при `useDefineForClassFields` инициализатор поля создал бы own-property и заглушил accessor Lit. Значение — в `constructor()`. Декораторы не канон.
3. `import type` для типов (`verbatimModuleSyntax`); смешанный импорт — `import { foo, type Bar }`.
4. JSDoc-типы → настоящие типы; typedef → `interface`/`type` рядом с фабрикой или в wire-модуле.
5. DOM: `this.renderRoot.querySelector<HTMLInputElement>('…')` с `throw` на `null`; `event.target` — `instanceof`-проверка; событие kit — его экспортированный тип.
6. Тест — `*.spec.ts`, фикстуры и helpers — тоже `.ts`.
7. Запрещено: `any`, `as unknown as`, non-null без контракта, `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`. Не типизируется честно — корень в kit или фабрике, рекурсия (`SKILL.md` § Рекурсия).
8. Прогон: `npm run build:ui -- --apps=<svc>`, `npx tsc -p tsconfig.json`, затронутые specs.
