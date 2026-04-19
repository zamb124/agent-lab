/**
 * createFacets — фабрика typeahead suggestions.
 *
 * Назначение: подсказки для фильтров tracing/billing-admin (companies, users,
 * services и т.д.). Каждый фасет — отдельный ключ, BE-эндпоинт строится как
 * `${baseUrl}/${facets[facetKey]}`.
 *
 * Контракт:
 *   - name: 'scope/entity'
 *   - baseUrl: HTTP-префикс
 *   - facets: { [facetKey]: 'url-segment' } — обязательно непустой объект
 *   - debounceMs: обязательное число (явный zero-guess против неявного || 200)
 *   - minQueryLength: обязательное число (>= 0); запросы короче не диспатчатся
 *   - pageSize: число (default 20)
 *
 * Возвращает:
 *   { name, sliceKey, events: { LOAD_REQUESTED, LOADED, FAILED }, reducer,
 *     slice, selectors: { facet(key) }, effect }
 */

import { httpRequest, HttpError } from '../http.js';
import {
    assertResourceName,
    deriveSliceKey,
    buildEventType,
    registerResourceName,
    freeze,
    requireField,
} from './_internal.js';

export function createFacets(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('createFacets: options object required');
    }
    const name = requireField(options, 'name', 'createFacets');
    assertResourceName(name);
    const baseUrl = requireField(options, 'baseUrl', `createFacets(${name})`);
    const facets = requireField(options, 'facets', `createFacets(${name})`);
    if (typeof facets !== 'object' || Object.keys(facets).length === 0) {
        throw new Error(`createFacets(${name}): facets must be non-empty object`);
    }
    const debounceMs = requireField(options, 'debounceMs', `createFacets(${name})`);
    if (typeof debounceMs !== 'number' || debounceMs < 0) {
        throw new Error(`createFacets(${name}): debounceMs must be non-negative number`);
    }
    const minQueryLength = requireField(options, 'minQueryLength', `createFacets(${name})`);
    if (typeof minQueryLength !== 'number' || minQueryLength < 0) {
        throw new Error(`createFacets(${name}): minQueryLength must be non-negative number`);
    }
    const pageSize = typeof options.pageSize === 'number' && options.pageSize > 0 ? options.pageSize : 20;

    const sliceKey = options.sliceKey || deriveSliceKey(name);
    registerResourceName(name, 'facets');

    const events = freeze({
        LOAD_REQUESTED: buildEventType(name, 'load_requested'),
        LOADED:         buildEventType(name, 'loaded'),
        FAILED:         buildEventType(name, 'failed'),
    });

    const initialItems = {};
    const initialLoading = {};
    const initialQuery = {};
    for (const facetKey of Object.keys(facets)) {
        initialItems[facetKey] = freeze([]);
        initialLoading[facetKey] = false;
        initialQuery[facetKey] = '';
    }
    const initialSlice = freeze({
        items: freeze(initialItems),
        loading: freeze(initialLoading),
        lastQuery: freeze(initialQuery),
    });

    function _requireFacetKey(event, eventKey) {
        if (!event.payload || typeof event.payload.facet !== 'string') {
            throw new Error(`createFacets(${name}): ${eventKey} payload.facet required (string)`);
        }
        const facet = event.payload.facet;
        if (!(facet in facets)) {
            throw new Error(`createFacets(${name}): ${eventKey} unknown facet "${facet}"`);
        }
        return facet;
    }

    function reducer(state = initialSlice, event) {
        switch (event.type) {
            case events.LOAD_REQUESTED: {
                const facet = _requireFacetKey(event, 'LOAD_REQUESTED');
                const q = typeof event.payload.q === 'string' ? event.payload.q : '';
                return freeze({
                    ...state,
                    loading: freeze({ ...state.loading, [facet]: true }),
                    lastQuery: freeze({ ...state.lastQuery, [facet]: q }),
                });
            }
            case events.LOADED: {
                const facet = _requireFacetKey(event, 'LOADED');
                if (!Array.isArray(event.payload.items)) {
                    throw new Error(`createFacets(${name}): LOADED payload.items must be array`);
                }
                return freeze({
                    ...state,
                    items: freeze({ ...state.items, [facet]: freeze(event.payload.items) }),
                    loading: freeze({ ...state.loading, [facet]: false }),
                });
            }
            case events.FAILED: {
                const facet = _requireFacetKey(event, 'FAILED');
                return freeze({
                    ...state,
                    items: freeze({ ...state.items, [facet]: freeze([]) }),
                    loading: freeze({ ...state.loading, [facet]: false }),
                });
            }
            default:
                return state;
        }
    }

    function _readSlice(state) {
        const slice = state[sliceKey];
        if (slice === undefined) {
            throw new Error(`createFacets(${name}): slice "${sliceKey}" not registered in bus`);
        }
        return slice;
    }

    const _facetCache = new Map();
    const selectors = freeze({
        slice:   (state) => _readSlice(state),
        facet:   (key) => {
            if (!(key in facets)) {
                throw new Error(`createFacets(${name}): unknown facet "${key}"`);
            }
            if (!_facetCache.has(key)) {
                _facetCache.set(key, (state) => _readSlice(state).items[key]);
            }
            return _facetCache.get(key);
        },
        loading: (key) => {
            if (!(key in facets)) {
                throw new Error(`createFacets(${name}): unknown facet "${key}"`);
            }
            return (state) => Boolean(_readSlice(state).loading[key]);
        },
    });

    const _timers = new Map();

    function effect(event, ctx) {
        if (event.type !== events.LOAD_REQUESTED) return;
        const facet = _requireFacetKey(event, 'LOAD_REQUESTED');
        const payload = event.payload;
        const q = typeof payload.q === 'string' ? payload.q.trim() : '';
        if (q.length < minQueryLength && q.length !== 0) {
            return;
        }
        if (_timers.has(facet)) {
            clearTimeout(_timers.get(facet));
        }
        const handle = setTimeout(() => {
            _timers.delete(facet);
            _runFacetRequest({ name, baseUrl, facets, pageSize }, payload, event, ctx, events);
        }, debounceMs);
        _timers.set(facet, handle);
    }

    const restMirror = {};
    for (const [facetKey, segment] of Object.entries(facets)) {
        restMirror[facetKey] = freeze({ method: 'GET', path: `${baseUrl}/${segment}` });
    }

    return freeze({
        kind: 'facets',
        name,
        sliceKey,
        baseUrl,
        transport: 'http',
        restMirror: freeze(restMirror),
        facets: freeze({ ...facets }),
        events,
        reducer,
        slice: freeze({ reducer, initial: initialSlice }),
        selectors,
        effect,
    });
}

async function _runFacetRequest(cfg, payload, event, ctx, events) {
    const facet = payload.facet;
    const path = cfg.facets[facet];
    const query = {};
    if (typeof payload.q === 'string' && payload.q.length > 0) query.q = payload.q;
    if (payload.context && typeof payload.context === 'object') {
        Object.assign(query, payload.context);
    }
    query.limit = typeof payload.limit === 'number' && payload.limit > 0 ? payload.limit : cfg.pageSize;
    try {
        const data = await httpRequest({ method: 'GET', url: `${cfg.baseUrl}/${path}`, query });
        if (!data || !Array.isArray(data.items)) {
            throw new Error(`createFacets(${cfg.name}): facet "${facet}" response.items must be array`);
        }
        ctx.dispatch(
            events.LOADED,
            { facet, items: data.items },
            { causation_id: event.id, source: 'http' },
        );
    } catch (err) {
        if (!(err instanceof HttpError)) throw err;
        ctx.dispatch(
            events.FAILED,
            { facet, message: err.message },
            { causation_id: event.id, source: 'http' },
        );
    }
}
