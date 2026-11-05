/**
 * Geo — адресный справочник: suggest (forward geocode) и nearest (reverse).
 *
 * Оба опа silent — используются картой/locate-кнопкой/панелью адресов
 * без toast-уведомлений на каждый запрос.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import type { GeoAddressListResponse } from '../wire/geo.gen.js';

export const geoAddressSuggestOp = createAsyncOp<GeoAddressListResponse>({
    name: 'geo/addresses_suggest',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/addresses/suggest_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/addresses/suggest' },
});

export const geoAddressNearestOp = createAsyncOp<GeoAddressListResponse>({
    name: 'geo/addresses_nearest',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/addresses/nearest_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/addresses/nearest' },
});

export const geoAddressesInZoneOp = createAsyncOp<GeoAddressListResponse>({
    name: 'geo/addresses_in_zone',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'geo/addresses/in_zone_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/addresses/in-zone' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'geo/addresses_suggest': typeof geoAddressSuggestOp;
        'geo/addresses_nearest': typeof geoAddressNearestOp;
        'geo/addresses_in_zone': typeof geoAddressesInZoneOp;
    }
}
