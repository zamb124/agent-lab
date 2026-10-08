/**
 * useResource / useOp / useForm / useКурсорList / useFacets — Reactive
 * Controllers поверх фабрик.
 *
 * Назначение: компоненту достаточно подключить контроллер, чтобы автоматически
 * подписаться на slice ресурса/операции/формы, dispatch'ить нужные события и
 * получить узкий API без копирования select+dispatch на каждой странице.
 *
 * Все контроллеры — Lit ReactiveController. Любая мутация state идёт через
 * dispatch (никакого setState в компоненте, никаких прямых обращений к фабрике).
 *
 * Контроллеры читают slice через узкие селекторы фабрики, селекторы в свою
 * очередь читают `state[sliceKey]` напрямую и бросают, если slice не
 * зарегистрирован. Никаких `state || initial`, `items || []`, `error || null`
 * фолбеков — slice всегда есть, потому что фабрика регистрирует его в
 * PlatformApp при бутстрапе.
 */

import { SelectController } from '../events/select-controller.js';
import type { PlatformBusLike } from '../events/bus-singleton.js';
import type { PlatformEvent } from '../events/contract.js';
import type {
    ResourceCollectionFactory,
    ResourceCollectionSlice,
    ResourceItem,
} from '../events/factories/resource-collection.js';
import type { AsyncOpFactory, AsyncOpSlice } from '../events/factories/async-op.js';
import type { FormFactory, FormSlice } from '../events/factories/form.js';
import type { CursorListFactory, CursorListSlice } from '../events/factories/cursor-list.js';
import type { FacetsFactory, FacetsSlice } from '../events/factories/facets.js';
import type { SliceFactory } from '../events/factories/slice.js';
import type { PlatformFactory } from '../events/factory-registry.js';

/** Host компонента с доступом к platform bus (PlatformElement). */
export interface ControllerHost {
    bus: PlatformBusLike;
    addController(controller: { hostConnected?(): void; hostDisconnected?(): void }): void;
    requestUpdate(): void;
}

type ActionMap = Readonly<Record<string, string>>;

interface ActionTarget {
    bus: PlatformBusLike;
    [methodName: string]: unknown;
}

function _requireFactory(factory: PlatformFactory | null | undefined, expectedKind: string, controllerName: string): void {
    if (!factory || factory.kind !== expectedKind) {
        throw new Error(`${controllerName}: factory of kind "${expectedKind}" required, got "${factory && factory.kind}"`);
    }
}

function _bindActions(target: ActionTarget, actions: ActionMap, controllerName: string, factoryName: string): void {
    for (const [methodName, eventType] of Object.entries(actions)) {
        if (typeof target[methodName] === 'function') {
            throw new Error(`${controllerName}: action "${methodName}" collides with built-in method on factory "${factoryName}"`);
        }
        target[methodName] = (payload: unknown) => {
            if (payload === undefined) {
                throw new Error(`${controllerName}.${methodName}: payload required (use null for empty events)`);
            }
            return target.bus.dispatch(eventType, payload, { source: 'local' });
        };
    }
}

/**
 * useResource(host, resource, opts) — для createResourceCollection.
 *
 *   const ctl = new ResourceController(this, apiKeysResource, { autoload: true });
 *   ctl.items, ctl.byId, ctl.loading, ctl.createInFlight, ctl.error, ctl.busyIds
 *   ctl.load(query?), ctl.create(payload), ctl.update(id, payload), ctl.remove(id)
 *   ctl.fetchItem(id) — Promise с mapped item после ITEM_LOADED
 */
export class ResourceController {
    host: ControllerHost;
    resource: ResourceCollectionFactory;
    autoload: boolean;
    autoloadQuery: Record<string, unknown> | null;
    private _slice: SelectController<ResourceCollectionSlice>;
    [action: string]: unknown;

    constructor(host: ControllerHost, resource: ResourceCollectionFactory, opts?: { autoload?: boolean; autoloadQuery?: Record<string, unknown> | null }) {
        _requireFactory(resource, 'resource-collection', 'ResourceController');
        this.host = host;
        this.resource = resource;
        this.autoload = Boolean(opts && opts.autoload === true);
        this.autoloadQuery = opts && opts.autoloadQuery !== undefined ? opts.autoloadQuery : null;
        this._slice = new SelectController(host, resource.selectors.slice);
        _bindActions(this, resource.actions || {}, 'ResourceController', resource.name);
        host.addController(this);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get state(): ResourceCollectionSlice { return this._slice.value as ResourceCollectionSlice; }
    get items(): readonly ResourceItem[] { return this.state.items; }
    get byId(): Readonly<Record<string, ResourceItem>> { return this.state.byId; }
    get loading(): boolean { return Boolean(this.state.loading); }
    get refreshing(): boolean { return Boolean(this.state.refreshing); }
    get listTotal(): number | null {
        const total = this.state.listTotal;
        return typeof total === 'number' ? total : null;
    }
    get createInFlight(): boolean { return Boolean(this.state.createInFlight); }
    get error(): string | null { return this.state.error; }
    get busyIds(): Readonly<Record<string, boolean>> { return this.state.busyIds; }
    get lastError(): Readonly<Record<string, string | null>> { return this.state.lastError; }

    isBusy(id: string | number): boolean { return Boolean(this.busyIds[id]); }

    load(query?: Record<string, unknown> | null): PlatformEvent | null {
        return this.bus.dispatch(
            this.resource.events.LIST_REQUESTED,
            query === undefined ? null : query,
            { source: 'local' },
        );
    }
    get(id: string | number): PlatformEvent | null {
        if (!id) throw new Error(`ResourceController(${this.resource.name}).get: id required`);
        return this.bus.dispatch(
            this.resource.events.ITEM_REQUESTED,
            { [this.resource.idField]: id },
            { source: 'local' },
        );
    }
    fetchItem(id: string | number): Promise<ResourceItem> {
        if (!id) throw new Error(`ResourceController(${this.resource.name}).fetchItem: id required`);
        const okType = this.resource.events.ITEM_LOADED;
        const failType = this.resource.events.ITEM_FAILED;
        const idField = this.resource.idField;
        const requested = this.bus.dispatch(
            this.resource.events.ITEM_REQUESTED,
            { [idField]: id },
            { source: 'local' },
        );
        if (!requested || typeof requested.id !== 'string') {
            throw new Error(`ResourceController(${this.resource.name}).fetchItem: dispatch returned no event with id`);
        }
        const requestedId = requested.id;
        return new Promise((resolve, reject) => {
            let unsubOk: (() => void) | null = null;
            let unsubFail: (() => void) | null = null;
            const cleanup = () => {
                if (typeof unsubOk === 'function') unsubOk();
                if (typeof unsubFail === 'function') unsubFail();
            };
            unsubOk = this.bus.subscribeType(okType, (event) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                const item = this.byId[id];
                if (!item || typeof item !== 'object') {
                    reject(new Error(`ResourceController(${this.resource.name}).fetchItem: item "${id}" missing after ITEM_LOADED`));
                    return;
                }
                resolve(item);
            });
            unsubFail = this.bus.subscribeType(failType, (event) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                const p = event.payload;
                const message = p && typeof p === 'object' && typeof (p as { message?: unknown }).message === 'string'
                    ? (p as { message: string }).message
                    : `ResourceController(${this.resource.name}).fetchItem failed`;
                reject(new Error(message));
            });
        });
    }
    create(payload: Record<string, unknown>): PlatformEvent | null | undefined {
        if (!payload || typeof payload !== 'object') {
            throw new Error(`ResourceController(${this.resource.name}).create: payload object required`);
        }
        if (this.resource.operations.includes('create') && this.createInFlight) {
            return undefined;
        }
        return this.bus.dispatch(this.resource.events.CREATE_REQUESTED, payload, { source: 'local' });
    }
    update(id: string | number, payload: Record<string, unknown>): PlatformEvent | null {
        if (!id) throw new Error(`ResourceController(${this.resource.name}).update: id required`);
        if (!payload || typeof payload !== 'object') {
            throw new Error(`ResourceController(${this.resource.name}).update: payload object required`);
        }
        return this.bus.dispatch(
            this.resource.events.UPDATE_REQUESTED,
            { [this.resource.idField]: id, ...payload },
            { source: 'local' },
        );
    }
    remove(id: string | number): PlatformEvent | null {
        if (!id) throw new Error(`ResourceController(${this.resource.name}).remove: id required`);
        return this.bus.dispatch(
            this.resource.events.REMOVE_REQUESTED,
            { [this.resource.idField]: id },
            { source: 'local' },
        );
    }

    hostConnected(): void {
        if (this.autoload) {
            this.load(this.autoloadQuery);
        }
    }
}

/**
 * useOp(host, op) — для createAsyncOp.
 *
 *   const ctl = new OpController(this, acceptInviteOp);
 *   ctl.busy, ctl.error, ctl.lastResult
 *   const result = await ctl.run(payload);
 *
 * `run(payload)` возвращает Promise, который ВСЕГДА резолвится:
 *   - SUCCEEDED → resolve(result) (значение из `event.payload.result`).
 *   - FAILED    → resolve(null), ошибка кладётся в `state.error` slice.
 *
 * Это явный контракт: caller, которому важна обработка ошибки, проверяет
 * `ctl.error` после `await ctl.run(...)` (или подписывается на slice).
 * Никакого скрытого успеха — null result отличим от реального result.
 * Спасает fire-and-forget вызовы (`this._typing.run(...)` без await/catch)
 * от unhandled promise rejection.
 *
 * Привязка REQUESTED → SUCCEEDED/FAILED делается по `causation_id`
 * (фабрика всегда выставляет его в effect'е).
 */
export class OpController {
    host: ControllerHost;
    op: AsyncOpFactory;
    private _slice: SelectController<AsyncOpSlice>;
    [action: string]: unknown;

    constructor(host: ControllerHost, op: AsyncOpFactory) {
        _requireFactory(op, 'async-op', 'OpController');
        this.host = host;
        this.op = op;
        this._slice = new SelectController(host, op.selectors.slice);
        _bindActions(this, op.actions || {}, 'OpController', op.name);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get state(): AsyncOpSlice { return this._slice.value as AsyncOpSlice; }
    get busy(): boolean { return Boolean(this.state.busy); }
    get error(): string | null { return this.state.error; }
    get lastResult(): unknown { return this.state.lastResult; }
    get lastRequestId(): string | null { return this.state.lastRequestId; }

    run(payload?: unknown): Promise<unknown> {
        const okType = this.op.events.SUCCEEDED;
        const failType = this.op.events.FAILED;
        const requested = this.bus.dispatch(
            this.op.events.REQUESTED,
            payload === undefined ? null : payload,
            { source: 'local' },
        );
        if (!requested || typeof requested.id !== 'string') {
            throw new Error(`OpController(${this.op.name}).run: dispatch returned no event with id`);
        }
        const requestedId = requested.id;
        return new Promise((resolve) => {
            let unsubOk: (() => void) | null = null;
            let unsubFail: (() => void) | null = null;
            const cleanup = () => {
                if (typeof unsubOk === 'function') unsubOk();
                if (typeof unsubFail === 'function') unsubFail();
            };
            unsubOk = this.bus.subscribeType(okType, (event) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                const pl = event.payload;
                const out = pl != null && typeof pl === 'object' && Object.prototype.hasOwnProperty.call(pl, 'result')
                    ? (pl as { result: unknown }).result
                    : null;
                resolve(out);
            });
            unsubFail = this.bus.subscribeType(failType, (event) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                resolve(null);
            });
        });
    }
}

/**
 * useForm(host, form) — для createForm.
 *
 *   const ctl = new FormController(this, apiKeyForm);
 *   ctl.draft, ctl.errors, ctl.submitting, ctl.isValid, ctl.open
 *   ctl.openForm(initial?), ctl.close(), ctl.setField(field, value),
 *   ctl.reset(), ctl.submit()
 */
export class FormController {
    host: ControllerHost;
    form: FormFactory;
    private _slice: SelectController<FormSlice>;

    constructor(host: ControllerHost, form: FormFactory) {
        _requireFactory(form, 'form', 'FormController');
        this.host = host;
        this.form = form;
        this._slice = new SelectController(host, form.selectors.slice);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get state(): FormSlice { return this._slice.value as FormSlice; }
    get open(): boolean { return Boolean(this.state.open); }
    get draft(): Readonly<Record<string, unknown>> { return this.state.draft; }
    get errors(): Readonly<Record<string, string>> { return this.state.errors; }
    get submitting(): boolean { return Boolean(this.state.submitting); }
    get isValid(): boolean { return Object.keys(this.errors).length === 0; }

    openForm(initial?: Record<string, unknown> | null): PlatformEvent | null {
        if (initial !== undefined && initial !== null && typeof initial !== 'object') {
            throw new Error(`FormController(${this.form.name}).openForm: initial must be object|null|omitted`);
        }
        return this.bus.dispatch(
            this.form.events.OPENED,
            { initial: initial === undefined ? null : initial },
            { source: 'local' },
        );
    }
    close(): PlatformEvent | null {
        return this.bus.dispatch(this.form.events.CLOSED, null, { source: 'local' });
    }
    setField(field: string, value: unknown): PlatformEvent | null {
        if (typeof field !== 'string' || field.length === 0) {
            throw new Error(`FormController(${this.form.name}).setField: field required (non-empty string)`);
        }
        if (value === undefined) {
            throw new Error(`FormController(${this.form.name}).setField: value required (use null for empty)`);
        }
        return this.bus.dispatch(this.form.events.FIELD_CHANGED, { field, value }, { source: 'local' });
    }
    reset(): PlatformEvent | null {
        return this.bus.dispatch(this.form.events.RESET, null, { source: 'local' });
    }
    submit(): PlatformEvent | null {
        return this.bus.dispatch(this.form.events.SUBMIT_REQUESTED, null, { source: 'local' });
    }
}

/**
 * useКурсорList(host, list, opts) — для createКурсорList.
 *
 *   const ctl = new КурсорListController(this, spansList, { autoload: true });
 *   ctl.items, ctl.hasMore, ctl.loading, ctl.loadingMore, ctl.terminal,
 *   ctl.filters
 *   ctl.load(filters?), ctl.loadMore(), ctl.changeFilters(patch), ctl.resetFilters()
 */
export class CursorListController {
    host: ControllerHost;
    list: CursorListFactory;
    autoload: boolean;
    autoloadFilters: Record<string, unknown> | null;
    private _slice: SelectController<CursorListSlice>;

    constructor(host: ControllerHost, list: CursorListFactory, opts?: { autoload?: boolean; autoloadFilters?: Record<string, unknown> | null }) {
        _requireFactory(list, 'cursor-list', 'CursorListController');
        this.host = host;
        this.list = list;
        this.autoload = Boolean(opts && opts.autoload === true);
        this.autoloadFilters = opts && opts.autoloadFilters !== undefined ? opts.autoloadFilters : null;
        this._slice = new SelectController(host, list.selectors.slice);
        host.addController(this);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get state(): CursorListSlice { return this._slice.value as CursorListSlice; }
    get items(): readonly unknown[] { return this.state.items; }
    get hasMore(): boolean { return Boolean(this.state.hasMore); }
    get loading(): boolean { return Boolean(this.state.loading); }
    get loadingMore(): boolean { return Boolean(this.state.loadingMore); }
    get error(): string | null { return this.state.error; }
    get terminal(): string | null { return this.state.terminal; }
    get filters(): Readonly<Record<string, unknown>> { return this.state.filters; }

    load(filters?: Record<string, unknown> | null): PlatformEvent | null {
        const target = filters === undefined || filters === null ? this.filters : filters;
        if (typeof target !== 'object') {
            throw new Error(`CursorListController(${this.list.name}).load: filters must be object`);
        }
        return this.bus.dispatch(
            this.list.events.LOAD_REQUESTED,
            { filters: target, append: false },
            { source: 'local' },
        );
    }
    loadMore(): PlatformEvent | null {
        if (!this.hasMore || this.loadingMore) return null;
        return this.bus.dispatch(
            this.list.events.LOAD_REQUESTED,
            { filters: this.filters, cursor: this.state.nextCursor, append: true },
            { source: 'local' },
        );
    }
    changeFilters(patch: Record<string, unknown>): PlatformEvent | null {
        if (!patch || typeof patch !== 'object') {
            throw new Error(`CursorListController(${this.list.name}).changeFilters: patch object required`);
        }
        return this.bus.dispatch(this.list.events.FILTERS_CHANGED, { filters: patch }, { source: 'local' });
    }
    resetFilters(): PlatformEvent | null {
        return this.bus.dispatch(this.list.events.FILTERS_RESET, null, { source: 'local' });
    }

    hostConnected(): void {
        if (this.autoload) {
            this.load(this.autoloadFilters);
        }
    }
}

/**
 * useSlice(host, slice) — для createSlice.
 *
 *   const ctl = new SliceController(this, callUiSlice);
 *   ctl.value          // slice только для чтения (frozen)
 *   ctl.<actionMethod>(payload)  // привязан из factory.actions
 */
export class SliceController {
    host: ControllerHost;
    slice: SliceFactory;
    private _slice: SelectController<Record<string, unknown>>;
    [action: string]: unknown;

    constructor(host: ControllerHost, slice: SliceFactory) {
        _requireFactory(slice, 'slice', 'SliceController');
        this.host = host;
        this.slice = slice;
        this._slice = new SelectController(host, slice.selectors.slice);
        _bindActions(this, slice.actions || {}, 'SliceController', slice.name);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get value(): Record<string, unknown> | undefined { return this._slice.value; }
}

/**
 * useFacets(host, facets) — для createFacets.
 *
 *   const ctl = new FacetsController(this, tracingFacets);
 *   ctl.items('company'), ctl.loading('company')
 *   ctl.search('company', query, context?)
 */
export class FacetsController {
    host: ControllerHost;
    facets: FacetsFactory;
    private _slice: SelectController<FacetsSlice>;

    constructor(host: ControllerHost, facets: FacetsFactory) {
        _requireFactory(facets, 'facets', 'FacetsController');
        this.host = host;
        this.facets = facets;
        this._slice = new SelectController(host, facets.selectors.slice);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get state(): FacetsSlice { return this._slice.value as FacetsSlice; }

    items(facet: string): readonly unknown[] | undefined {
        if (!(facet in this.facets.facets)) {
            throw new Error(`FacetsController(${this.facets.name}).items: unknown facet "${facet}"`);
        }
        return this.state.items[facet];
    }
    loading(facet: string): boolean {
        if (!(facet in this.facets.facets)) {
            throw new Error(`FacetsController(${this.facets.name}).loading: unknown facet "${facet}"`);
        }
        return Boolean(this.state.loading[facet]);
    }
    lastQuery(facet: string): string | undefined {
        if (!(facet in this.facets.facets)) {
            throw new Error(`FacetsController(${this.facets.name}).lastQuery: unknown facet "${facet}"`);
        }
        return this.state.lastQuery[facet];
    }

    search(facet: string, q: string, context?: Record<string, unknown> | null): PlatformEvent | null {
        if (typeof facet !== 'string' || facet.length === 0) {
            throw new Error(`FacetsController(${this.facets.name}).search: facet required (non-empty string)`);
        }
        if (!(facet in this.facets.facets)) {
            throw new Error(`FacetsController(${this.facets.name}).search: unknown facet "${facet}"`);
        }
        const query = typeof q === 'string' ? q : '';
        const ctx = context === undefined ? null : context;
        if (ctx !== null && typeof ctx !== 'object') {
            throw new Error(`FacetsController(${this.facets.name}).search: context must be object|null|omitted`);
        }
        return this.bus.dispatch(
            this.facets.events.LOAD_REQUESTED,
            { facet, q: query, context: ctx },
            { source: 'local' },
        );
    }
}
