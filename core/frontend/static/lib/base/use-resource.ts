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
import { isPlainRecord } from '../events/payload.js';
import { hasPlatformBus, awaitPlatformBus, cancelPlatformBusWait } from '../events/bus-singleton.js';
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
import type { ActionMap, PlatformFactory, PlatformFactoryName, PlatformFactoryRegistry } from '../events/factory-registry.js';

type AnyResourceFactory = ResourceCollectionFactory<ResourceCollectionSlice<unknown>, ActionMap>;
type AnyOpFactory = AsyncOpFactory<unknown, AsyncOpSlice<unknown>, ActionMap>;
type AnySliceFactory = SliceFactory<object, ActionMap>;

/** Контроллер фабрики F: состояние — S фабрики (`F['slice']['initial']`), методы — её actions. */
export type ResourceControllerOf<F extends AnyResourceFactory> = ResourceController<F['slice']['initial']> & ActionMethods<F['actions']>;
export type OpControllerOf<F extends AnyOpFactory> = OpController<F['slice']['initial'], AsyncOpResultOf<F>> & ActionMethods<F['actions']>;
export type SliceControllerOf<F extends AnySliceFactory> = SliceController<F['slice']['initial']> & ActionMethods<F['actions']>;

/** Результат `OpController.run()`: `TResult` фабрики; `unknown` для нетипизированного op. */
export type OpRunResult<S extends AsyncOpSlice<unknown>> = S extends AsyncOpSlice<infer R> ? R : unknown;

/** `TResult` фабрики async-op (result команды `commandType`). */
export type AsyncOpResultOf<F> = F extends AsyncOpFactory<infer R, AsyncOpSlice<unknown>, ActionMap> ? R : unknown;

/** Элемент курсорной ленты по типу фабрики. */
export type CursorListItemOf<F> = F extends CursorListFactory<infer I> ? I : unknown;
export type CursorListControllerOf<F> = CursorListController<CursorListItemOf<F>>;

/** Тип контроллера, который `use*` возвращает для зарегистрированного имени фабрики. */
export type ControllerFor<N extends PlatformFactoryName> =
    PlatformFactoryRegistry[N] extends AnyResourceFactory ? ResourceControllerOf<PlatformFactoryRegistry[N]>
    : PlatformFactoryRegistry[N] extends AnyOpFactory ? OpControllerOf<PlatformFactoryRegistry[N]>
    : PlatformFactoryRegistry[N] extends AnySliceFactory ? SliceControllerOf<PlatformFactoryRegistry[N]>
    : PlatformFactoryRegistry[N] extends FormFactory ? FormController
    : PlatformFactoryRegistry[N] extends CursorListFactory<infer I> ? CursorListController<I>
    : PlatformFactoryRegistry[N] extends FacetsFactory ? FacetsController
    : never;

/** Host компонента с доступом к platform bus (PlatformElement). */
export interface ControllerHost {
    bus: PlatformBusLike;
    addController(controller: { hostConnected?(): void; hostDisconnected?(): void }): void;
    requestUpdate(): void;
}

/** Методы действий контроллера: имя из `factory.actions`, вызов диспатчит тип события действия. */
export type ActionMethods<A extends ActionMap> = { readonly [K in keyof A]: (payload: unknown) => PlatformEvent | null };

function _requireFactory(factory: PlatformFactory | null | undefined, expectedKind: string, controllerName: string): void {
    if (!factory || factory.kind !== expectedKind) {
        throw new Error(`${controllerName}: factory of kind "${expectedKind}" required, got "${factory && factory.kind}"`);
    }
}

export function bindActions<C extends { readonly bus: PlatformBusLike }, A extends ActionMap>(
    controller: C,
    actions: A,
    controllerName: string,
    factoryName: string,
): C & ActionMethods<A> {
    const methods: Record<string, (payload: unknown) => PlatformEvent | null> = {};
    for (const [methodName, eventType] of Object.entries(actions)) {
        if (methodName in controller) {
            throw new Error(`${controllerName}: action "${methodName}" collides with built-in member on factory "${factoryName}"`);
        }
        methods[methodName] = (payload: unknown) => {
            if (payload === undefined) {
                throw new Error(`${controllerName}.${methodName}: payload required (use null for empty events)`);
            }
            return controller.bus.dispatch(eventType, payload, { source: 'local' });
        };
    }
    if (!actionMethodsMatch(methods, actions)) {
        throw new Error(`${controllerName}: actions of factory "${factoryName}" were not bound`);
    }
    return Object.assign(controller, methods);
}

function actionMethodsMatch<A extends ActionMap>(
    methods: Record<string, (payload: unknown) => PlatformEvent | null>,
    actions: A,
): methods is ActionMethods<A> {
    return Object.keys(actions).every((key) => typeof methods[key] === 'function');
}

/**
 * useResource(host, resource, opts) — для createResourceCollection.
 *
 *   const ctl = new ResourceController(this, apiKeysResource, { autoload: true });
 *   ctl.items, ctl.byId, ctl.loading, ctl.createInFlight, ctl.error, ctl.busyIds
 *   ctl.load(query?), ctl.create(payload), ctl.update(id, payload), ctl.remove(id)
 *   ctl.fetchItem(id) — Promise с mapped item после ITEM_LOADED
 */
export class ResourceController<S extends ResourceCollectionSlice<unknown> = ResourceCollectionSlice> {
    host: ControllerHost;
    resource: ResourceCollectionFactory<S, ActionMap>;
    autoload: boolean;
    autoloadQuery: Record<string, unknown> | null;
    private _slice: SelectController<unknown>;
    private _awaitingBus: boolean;

    constructor(host: ControllerHost, resource: ResourceCollectionFactory<S, ActionMap>, opts?: { autoload?: boolean; autoloadQuery?: Record<string, unknown> | null }) {
        _requireFactory(resource, 'resource-collection', 'ResourceController');
        this.host = host;
        this.resource = resource;
        this.autoload = Boolean(opts && opts.autoload === true);
        this.autoloadQuery = opts && opts.autoloadQuery !== undefined ? opts.autoloadQuery : null;
        this._slice = new SelectController<unknown>(host, resource.selectors.slice);
        this._awaitingBus = false;
        host.addController(this);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get state(): S { return this.resource.selectors.slice(this.bus.getState()); }
    get items(): S['items'] { return this.state.items; }
    get byId(): S['byId'] { return this.state.byId; }
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
    fetchItem<K extends keyof S['byId'] & string>(id: K): Promise<S['byId'][K]> {
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
                const item: S['byId'][K] = this.byId[id];
                if (!item || typeof item !== 'object') {
                    reject(new Error(`ResourceController(${this.resource.name}).fetchItem: item "${id}" missing after ITEM_LOADED`));
                    return;
                }
                resolve(item);
            });
            unsubFail = this.bus.subscribeType(failType, (event) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                const message = isPlainRecord(event.payload) ? event.payload.message : undefined;
                reject(new Error(
                    typeof message === 'string'
                        ? message
                        : `ResourceController(${this.resource.name}).fetchItem failed`,
                ));
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
        if (!this.autoload) return;
        if (!hasPlatformBus()) {
            this._awaitingBus = true;
            awaitPlatformBus(this);
            return;
        }
        this.load(this.autoloadQuery);
    }

    bindPlatformBus(): void {
        this._awaitingBus = false;
        this.load(this.autoloadQuery);
    }

    hostDisconnected(): void {
        if (this._awaitingBus) {
            this._awaitingBus = false;
            cancelPlatformBusWait(this);
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
 *   - FAILED    → resolve(null), ошибка кладётся в `state.error` slice,
 *     HTTP-статус отказа — в `failureStatus` (иначе null).
 *
 * Это явный контракт: caller, которому важна обработка ошибки, проверяет
 * `ctl.error` после `await ctl.run(...)` и бросает её. `failureStatus === 404`
 * — единственный отказ, который страница может показать как «не найдено».
 * Никакого скрытого успеха — null result отличим от реального result.
 * Спасает fire-and-forget вызовы (`this._typing.run(...)` без await/catch)
 * от unhandled promise rejection.
 *
 * Привязка REQUESTED → SUCCEEDED/FAILED делается по `causation_id`
 * (фабрика всегда выставляет его в effect'е).
 */
function _httpStatus(payload: unknown): number | null {
    if (typeof payload !== 'object' || payload === null || !('status' in payload)) {
        return null;
    }
    return typeof payload.status === 'number' ? payload.status : null;
}

export class OpController<
    S extends AsyncOpSlice<unknown> = AsyncOpSlice,
    TResult = OpRunResult<S>,
> {
    host: ControllerHost;
    op: AsyncOpFactory<TResult, S, ActionMap>;
    private _slice: SelectController<unknown>;
    private _failureStatus: number | null = null;

    constructor(host: ControllerHost, op: AsyncOpFactory<TResult, S, ActionMap>) {
        _requireFactory(op, 'async-op', 'OpController');
        this.host = host;
        this.op = op;
        this._slice = new SelectController<unknown>(host, op.selectors.slice);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get state(): S { return this.op.selectors.slice(this.bus.getState()); }
    get busy(): boolean { return Boolean(this.state.busy); }
    get error(): string | null { return this.state.error; }
    /** HTTP-статус последнего FAILED этого контроллера; у успеха и не-HTTP отказа — null. */
    get failureStatus(): number | null { return this._failureStatus; }
    get lastResult(): S['lastResult'] { return this.state.lastResult; }
    get lastRequestId(): string | null { return this.state.lastRequestId; }

    run(payload?: unknown): Promise<TResult | null> {
        this._failureStatus = null;
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
                // Результат run() — result своего SUCCEEDED; lastResult slice может быть преобразован extraReducer.
                const pl = event.payload;
                const out = isPlainRecord(pl) && Object.prototype.hasOwnProperty.call(pl, 'result')
                    ? pl.result
                    : null;
                this._failureStatus = null;
                resolve(out as TResult | null);
            });
            unsubFail = this.bus.subscribeType(failType, (event) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                this._failureStatus = _httpStatus(event.payload);
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
    get state(): FormSlice { return this._slice.value; }
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
export class CursorListController<TItem = unknown> {
    host: ControllerHost;
    list: CursorListFactory<TItem>;
    autoload: boolean;
    autoloadFilters: Record<string, unknown> | null;
    private _slice: SelectController<CursorListSlice<TItem>>;
    private _awaitingBus: boolean;

    constructor(host: ControllerHost, list: CursorListFactory<TItem>, opts?: { autoload?: boolean; autoloadFilters?: Record<string, unknown> | null }) {
        _requireFactory(list, 'cursor-list', 'CursorListController');
        this.host = host;
        this.list = list;
        this.autoload = Boolean(opts && opts.autoload === true);
        this.autoloadFilters = opts && opts.autoloadFilters !== undefined ? opts.autoloadFilters : null;
        this._slice = new SelectController(host, list.selectors.slice);
        this._awaitingBus = false;
        host.addController(this);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get state(): CursorListSlice<TItem> { return this._slice.value; }
    get items(): readonly TItem[] { return this.state.items; }
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
        if (!this.autoload) return;
        if (!hasPlatformBus()) {
            this._awaitingBus = true;
            awaitPlatformBus(this);
            return;
        }
        this.load(this.autoloadFilters);
    }

    bindPlatformBus(): void {
        this._awaitingBus = false;
        this.load(this.autoloadFilters);
    }

    hostDisconnected(): void {
        if (this._awaitingBus) {
            this._awaitingBus = false;
            cancelPlatformBusWait(this);
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
export class SliceController<S extends object = Record<string, unknown>> {
    host: ControllerHost;
    slice: SliceFactory<S, ActionMap>;
    private _slice: SelectController<unknown>;

    constructor(host: ControllerHost, slice: SliceFactory<S, ActionMap>) {
        _requireFactory(slice, 'slice', 'SliceController');
        this.host = host;
        this.slice = slice;
        this._slice = new SelectController<unknown>(host, slice.selectors.slice);
    }

    get bus(): PlatformBusLike { return this.host.bus; }
    get value(): S { return this.slice.selectors.slice(this.bus.getState()); }
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
    get state(): FacetsSlice { return this._slice.value; }

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
