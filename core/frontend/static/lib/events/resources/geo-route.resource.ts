/**
 * Geo — маршрутные операции для лаборатории и потребителей карт.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import type {
    GeoIsochroneResponse,
    GeoRouteResponse,
} from '../wire/geo.gen.js';

export const geoRouteOp = createAsyncOp<GeoRouteResponse>({
    name: 'geo/route',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'geo/route/calculate_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/route/calculate' },
});

export const geoIsochroneOp = createAsyncOp<GeoIsochroneResponse>({
    name: 'geo/isochrone',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'geo/route/isochrone_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/route/isochrone' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'geo/route': typeof geoRouteOp;
        'geo/isochrone': typeof geoIsochroneOp;
    }
}
