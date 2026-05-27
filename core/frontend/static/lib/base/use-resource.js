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

function _requireFactory(factory, expectedKind, controllerName) {
    if (!factory || factory.kind !== expectedKind) {
        throw new Error(`${controllerName}: factory of kind "${expectedKind}" required, got "${factory && factory.kind}"`);
    }
}

function _bindActions(target, actions, controllerName, factoryName) {
    for (const [methodName, eventType] of Object.entries(actions)) {
        if (typeof target[methodName] === 'function') {
            throw new Error(`${controllerName}: action "${methodName}" collides with built-in method on factory "${factoryName}"`);
        }
        target[methodName] = (payload) => {
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
 */
export class ResourceController {
    constructor(host, resource, opts) {
        _requireFactory(resource, 'resource-collection', 'ResourceController');
        this.host = host;
        this.resource = resource;
        this.autoload = Boolean(opts && opts.autoload === true);
        this.autoloadQuery = opts && opts.autoloadQuery !== undefined ? opts.autoloadQuery : null;
        this._slice = new SelectController(host, resource.selectors.slice);
        _bindActions(this, resource.actions || {}, 'ResourceController', resource.name);
        host.addController(this);
    }

    get bus() { return this.host.bus; }
    get state() { return this._slice.value; }
    get items() { return this.state.items; }
    get byId() { return this.state.byId; }
    get loading() { return Boolean(this.state.loading); }
    get createInFlight() { return Boolean(this.state.createInFlight); }
    get error() { return this.state.error; }
    get busyIds() { return this.state.busyIds; }
    get lastError() { return this.state.lastError; }

    isBusy(id) { return Boolean(this.busyIds[id]); }

    load(query) {
        return this.bus.dispatch(
            this.resource.events.LIST_REQUESTED,
            query === undefined ? null : query,
            { source: 'local' },
        );
    }
    get(id) {
        if (!id) throw new Error(`ResourceController(${this.resource.name}).get: id required`);
        return this.bus.dispatch(
            this.resource.events.ITEM_REQUESTED,
            { [this.resource.idField]: id },
            { source: 'local' },
        );
    }
    create(payload) {
        if (!payload || typeof payload !== 'object') {
            throw new Error(`ResourceController(${this.resource.name}).create: payload object required`);
        }
        if (this.resource.operations.includes('create') && this.createInFlight) {
            return undefined;
        }
        return this.bus.dispatch(this.resource.events.CREATE_REQUESTED, payload, { source: 'local' });
    }
    update(id, payload) {
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
    remove(id) {
        if (!id) throw new Error(`ResourceController(${this.resource.name}).remove: id required`);
        return this.bus.dispatch(
            this.resource.events.REMOVE_REQUESTED,
            { [this.resource.idField]: id },
            { source: 'local' },
        );
    }

    hostConnected() {
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
    constructor(host, op) {
        _requireFactory(op, 'async-op', 'OpController');
        this.host = host;
        this.op = op;
        this._slice = new SelectController(host, op.selectors.slice);
        _bindActions(this, op.actions || {}, 'OpController', op.name);
    }

    get bus() { return this.host.bus; }
    get state() { return this._slice.value; }
    get busy() { return Boolean(this.state.busy); }
    get error() { return this.state.error; }
    get lastResult() { return this.state.lastResult; }
    get lastRequestId() { return this.state.lastRequestId; }

    run(payload) {
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
            let unsubOk = null;
            let unsubFail = null;
            const cleanup = () => {
                if (typeof unsubOk === 'function') unsubOk();
                if (typeof unsubFail === 'function') unsubFail();
            };
            unsubOk = this.bus.subscribeType(okType, (event) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                const pl = event.payload;
                const out = pl != null && Object.prototype.hasOwnProperty.call(pl, 'result')
                    ? pl.result
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
    constructor(host, form) {
        _requireFactory(form, 'form', 'FormController');
        this.host = host;
        this.form = form;
        this._slice = new SelectController(host, form.selectors.slice);
    }

    get bus() { return this.host.bus; }
    get state() { return this._slice.value; }
    get open() { return Boolean(this.state.open); }
    get draft() { return this.state.draft; }
    get errors() { return this.state.errors; }
    get submitting() { return Boolean(this.state.submitting); }
    get isValid() { return Object.keys(this.errors).length === 0; }

    openForm(initial) {
        if (initial !== undefined && initial !== null && typeof initial !== 'object') {
            throw new Error(`FormController(${this.form.name}).openForm: initial must be object|null|omitted`);
        }
        return this.bus.dispatch(
            this.form.events.OPENED,
            { initial: initial === undefined ? null : initial },
            { source: 'local' },
        );
    }
    close() {
        return this.bus.dispatch(this.form.events.CLOSED, null, { source: 'local' });
    }
    setField(field, value) {
        if (typeof field !== 'string' || field.length === 0) {
            throw new Error(`FormController(${this.form.name}).setField: field required (non-empty string)`);
        }
        if (value === undefined) {
            throw new Error(`FormController(${this.form.name}).setField: value required (use null for empty)`);
        }
        return this.bus.dispatch(this.form.events.FIELD_CHANGED, { field, value }, { source: 'local' });
    }
    reset() {
        return this.bus.dispatch(this.form.events.RESET, null, { source: 'local' });
    }
    submit() {
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
    constructor(host, list, opts) {
        _requireFactory(list, 'cursor-list', 'CursorListController');
        this.host = host;
        this.list = list;
        this.autoload = Boolean(opts && opts.autoload === true);
        this.autoloadFilters = opts && opts.autoloadFilters !== undefined ? opts.autoloadFilters : null;
        this._slice = new SelectController(host, list.selectors.slice);
        host.addController(this);
    }

    get bus() { return this.host.bus; }
    get state() { return this._slice.value; }
    get items() { return this.state.items; }
    get hasMore() { return Boolean(this.state.hasMore); }
    get loading() { return Boolean(this.state.loading); }
    get loadingMore() { return Boolean(this.state.loadingMore); }
    get error() { return this.state.error; }
    get terminal() { return this.state.terminal; }
    get filters() { return this.state.filters; }

    load(filters) {
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
    loadMore() {
        if (!this.hasMore || this.loadingMore) return null;
        return this.bus.dispatch(
            this.list.events.LOAD_REQUESTED,
            { filters: this.filters, cursor: this.state.nextCursor, append: true },
            { source: 'local' },
        );
    }
    changeFilters(patch) {
        if (!patch || typeof patch !== 'object') {
            throw new Error(`CursorListController(${this.list.name}).changeFilters: patch object required`);
        }
        return this.bus.dispatch(this.list.events.FILTERS_CHANGED, { filters: patch }, { source: 'local' });
    }
    resetFilters() {
        return this.bus.dispatch(this.list.events.FILTERS_RESET, null, { source: 'local' });
    }

    hostConnected() {
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
    constructor(host, slice) {
        _requireFactory(slice, 'slice', 'SliceController');
        this.host = host;
        this.slice = slice;
        this._slice = new SelectController(host, slice.selectors.slice);
        _bindActions(this, slice.actions || {}, 'SliceController', slice.name);
    }

    get bus() { return this.host.bus; }
    get value() { return this._slice.value; }
}

/**
 * useFacets(host, facets) — для createFacets.
 *
 *   const ctl = new FacetsController(this, tracingFacets);
 *   ctl.items('company'), ctl.loading('company')
 *   ctl.search('company', query, context?)
 */
export class FacetsController {
    constructor(host, facets) {
        _requireFactory(facets, 'facets', 'FacetsController');
        this.host = host;
        this.facets = facets;
        this._slice = new SelectController(host, facets.selectors.slice);
    }

    get bus() { return this.host.bus; }
    get state() { return this._slice.value; }

    items(facet) {
        if (!(facet in this.facets.facets)) {
            throw new Error(`FacetsController(${this.facets.name}).items: unknown facet "${facet}"`);
        }
        return this.state.items[facet];
    }
    loading(facet) {
        if (!(facet in this.facets.facets)) {
            throw new Error(`FacetsController(${this.facets.name}).loading: unknown facet "${facet}"`);
        }
        return Boolean(this.state.loading[facet]);
    }
    lastQuery(facet) {
        if (!(facet in this.facets.facets)) {
            throw new Error(`FacetsController(${this.facets.name}).lastQuery: unknown facet "${facet}"`);
        }
        return this.state.lastQuery[facet];
    }

    search(facet, q, context) {
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
