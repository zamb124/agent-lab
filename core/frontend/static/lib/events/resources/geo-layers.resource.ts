/**
 * Geo — канонические слои карты и их видимость.
 *
 * `geoLayersOp` — реестр слоёв со счётчиками (`geo/layers/list`).
 * `geoLayerFeaturesOp` — GeoJSON-фичи в рамке (`geo/layers/features`):
 * silent, без toast — дёргается на каждый moveend карты.
 * `geoMapSlice` — локальное состояние видимости слоёв: `hidden[name]=true`
 * прячет слой; отсутствие ключа = виден (новые слои реестра видны сразу).
 */

import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';
import type {
    GeoFeatureCollectionResponse,
    GeoLayerListResponse,
} from '../wire/geo.gen.js';

export const geoLayersOp = createAsyncOp<GeoLayerListResponse>({
    name: 'geo/layers',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/layers/list_requested',
    restMirror: { method: 'GET', path: '/geo/api/v1/layers' },
});

export const geoLayerFeaturesOp = createAsyncOp<GeoFeatureCollectionResponse>({
    name: 'geo/layer_features',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'geo/layers/features_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/layers/features' },
});

interface GeoMapSliceState extends Record<string, unknown> {
    hidden: Record<string, boolean>;
}

export const geoMapSlice = createSlice<GeoMapSliceState, { toggle: string }>({
    name: 'geo/map',
    extraInitial: { hidden: {} },
    actions: { toggle: 'toggle' },
    extraReducer: (state, event) => {
        if (event.type !== 'geo/map/toggle') return null;
        const payload = event.payload as { name?: unknown } | null;
        const name = payload && typeof payload.name === 'string' ? payload.name : '';
        if (name.length === 0) {
            throw new Error('geo/map/toggle: payload.name required');
        }
        const hidden = { ...state.hidden };
        if (hidden[name]) {
            delete hidden[name];
        } else {
            hidden[name] = true;
        }
        return { ...state, hidden };
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'geo/layers': typeof geoLayersOp;
        'geo/layer_features': typeof geoLayerFeaturesOp;
        'geo/map': typeof geoMapSlice;
    }
}
