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
import type { EffectCtx, PlatformEvent } from '../contract.js';
import { isPlainRecord } from '../payload.js';
import { registerFactory } from '../factory-registry.js';
import type { PlatformFactory } from '../factory-registry.js';
import type { SliceDef } from '../reducers/index.js';
import type { RestMirrorEntry } from './_transport.js';

export interface FacetsSlice {
    items: Readonly<Record<string, readonly unknown[]>>;
    loading: Readonly<Record<string, boolean>>;
    lastQuery: Readonly<Record<string, string>>;
    [key: string]: unknown;
}

export interface FacetsOptions {
    name: string;
    baseUrl: string;
    facets: Record<string, string>;
    debounceMs: number;
    minQueryLength: number;
    pageSize?: number;
    sliceKey?: string;
}

export interface FacetsFactory extends PlatformFactory {
    kind: 'facets';
    name: string;
    sliceKey: string;
    baseUrl: string;
    transport: 'http';
    restMirror: Readonly<Record<string, Readonly<RestMirrorEntry>>>;
    facets: Readonly<Record<string, string>>;
    events: Readonly<{ LOAD_REQUESTED: string; LOADED: string; FAILED: string }>;
    reducer: (state: FacetsSlice | undefined, event: PlatformEvent) => FacetsSlice;
    slice: SliceDef<FacetsSlice>;
    selectors: {
        slice: (state: Record<string, unknown>) => FacetsSlice;
        facet: (key: string) => (state: Record<string, unknown>) => readonly unknown[] | undefined;
        loading: (key: string) => (state: Record<string, unknown>) => boolean;
    };
    effect: (event: PlatformEvent, ctx: EffectCtx) => void;
}

function facetRequest(payload: Record<string, unknown>, facet: string): { facet: string; q?: unknown; context?: unknown; limit?: unknown } {
    return { facet, q: payload.q, context: payload.context, limit: payload.limit };
}

function isFacetsSlice(value: unknown): value is FacetsSlice {
    if (!isPlainRecord(value) || !isPlainRecord(value.items) || !isPlainRecord(value.loading) || !isPlainRecord(value.lastQuery)) {
        return false;
    }
    if (!Object.values(value.items).every((items) => Array.isArray(items))) return false;
    if (!Object.values(value.loading).every((loading) => typeof loading === 'boolean')) return false;
    return Object.values(value.lastQuery).every((query) => typeof query === 'string');
}

export function createFacets(options: FacetsOptions): FacetsFactory {
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

    const initialItems: Record<string, readonly unknown[]> = {};
    const initialLoading: Record<string, boolean> = {};
    const initialQuery: Record<string, string> = {};
    for (const facetKey of Object.keys(facets)) {
        initialItems[facetKey] = freeze([]);
        initialLoading[facetKey] = false;
        initialQuery[facetKey] = '';
    }
    const initialSlice: FacetsSlice = freeze({
        items: freeze(initialItems),
        loading: freeze(initialLoading),
        lastQuery: freeze(initialQuery),
    });

    function _requireFacetKey(event: PlatformEvent, eventKey: string): string {
        const payload = event.payload;
        if (!isPlainRecord(payload)) {
            throw new Error(`createFacets(${name}): ${eventKey} payload.facet required (string)`);
        }
        const facet = payload.facet;
        if (typeof facet !== 'string') {
            throw new Error(`createFacets(${name}): ${eventKey} payload.facet required (string)`);
        }
        if (!(facet in facets)) {
            throw new Error(`createFacets(${name}): ${eventKey} unknown facet "${facet}"`);
        }
        return facet;
    }

    function reducer(state: FacetsSlice = initialSlice, event: PlatformEvent): FacetsSlice {
        switch (event.type) {
            case events.LOAD_REQUESTED: {
                const facet = _requireFacetKey(event, 'LOAD_REQUESTED');
                const request = event.payload;
                if (!isPlainRecord(request)) {
                    throw new Error(`createFacets(${name}): LOAD_REQUESTED payload.facet required (string)`);
                }
                const q = typeof request.q === 'string' ? request.q : '';
                return freeze({
                    ...state,
                    loading: freeze({ ...state.loading, [facet]: true }),
                    lastQuery: freeze({ ...state.lastQuery, [facet]: q }),
                });
            }
            case events.LOADED: {
                const facet = _requireFacetKey(event, 'LOADED');
                const loaded = event.payload;
                if (!isPlainRecord(loaded) || !Array.isArray(loaded.items)) {
                    throw new Error(`createFacets(${name}): LOADED payload.items must be array`);
                }
                return freeze({
                    ...state,
                    items: freeze({ ...state.items, [facet]: freeze(loaded.items) }),
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

    function _readSlice(state: Record<string, unknown>): FacetsSlice {
        const slice = state[sliceKey];
        if (slice === undefined) {
            throw new Error(`createFacets(${name}): slice "${sliceKey}" not registered in bus`);
        }
        if (!isFacetsSlice(slice)) {
            throw new Error(`createFacets(${name}): slice "${sliceKey}" must be a facets slice`);
        }
        return slice;
    }

    const _facetCache = new Map<string, (state: Record<string, unknown>) => readonly unknown[] | undefined>();
    const selectors = freeze({
        slice:   (state: Record<string, unknown>) => _readSlice(state),
        facet:   (key: string) => {
            if (!(key in facets)) {
                throw new Error(`createFacets(${name}): unknown facet "${key}"`);
            }
            if (!_facetCache.has(key)) {
                _facetCache.set(key, (state: Record<string, unknown>) => _readSlice(state).items[key]);
            }
            const cached = _facetCache.get(key);
            if (cached === undefined) {
                throw new Error(`createFacets(${name}): facet selector "${key}" missing`);
            }
            return cached;
        },
        loading: (key: string) => {
            if (!(key in facets)) {
                throw new Error(`createFacets(${name}): unknown facet "${key}"`);
            }
            return (state: Record<string, unknown>) => Boolean(_readSlice(state).loading[key]);
        },
    });

    const _timers = new Map<string, ReturnType<typeof setTimeout>>();

    function effect(event: PlatformEvent, ctx: EffectCtx): void {
        if (event.type !== events.LOAD_REQUESTED) return;
        const facet = _requireFacetKey(event, 'LOAD_REQUESTED');
        const payload = event.payload;
        if (!isPlainRecord(payload)) {
            throw new Error(`createFacets(${name}): LOAD_REQUESTED payload.facet required (string)`);
        }
        const q = typeof payload.q === 'string' ? payload.q.trim() : '';
        if (q.length < minQueryLength && q.length !== 0) {
            return;
        }
        if (_timers.has(facet)) {
            clearTimeout(_timers.get(facet));
        }
        const handle = setTimeout(() => {
            _timers.delete(facet);
            _runFacetRequest({ name, baseUrl, facets, pageSize }, facetRequest(payload, facet), event, ctx, events);
        }, debounceMs);
        _timers.set(facet, handle);
    }

    const restMirror: Record<string, Readonly<RestMirrorEntry>> = {};
    for (const [facetKey, segment] of Object.entries(facets)) {
        restMirror[facetKey] = freeze({ method: 'GET', path: `${baseUrl}/${segment}` });
    }

    return registerFactory(freeze({
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
    }));
}

interface _FacetCfg {
    name: string;
    baseUrl: string;
    facets: Record<string, string>;
    pageSize: number;
}

async function _runFacetRequest(
    cfg: _FacetCfg,
    payload: { facet: string; q?: unknown; context?: unknown; limit?: unknown },
    event: PlatformEvent,
    ctx: EffectCtx,
    events: FacetsFactory['events'],
): Promise<void> {
    const facet = payload.facet;
    const path = cfg.facets[facet];
    if (path === undefined) {
        throw new Error(`createFacets(${cfg.name}): facet path for "${facet}" missing`);
    }
    const query: Record<string, string | number | boolean | null | undefined> = {};
    if (typeof payload.q === 'string' && payload.q.length > 0) query.q = payload.q;
    if (payload.context && typeof payload.context === 'object') {
        Object.assign(query, payload.context);
    }
    query.limit = typeof payload.limit === 'number' && payload.limit > 0 ? payload.limit : cfg.pageSize;
    try {
        const data = await httpRequest({ method: 'GET', url: `${cfg.baseUrl}/${path}`, query });
        if (!isPlainRecord(data) || !Array.isArray(data.items)) {
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
