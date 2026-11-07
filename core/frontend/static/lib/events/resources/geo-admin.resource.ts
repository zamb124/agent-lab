/**
 * Geo — правки админа: адреса, тумбстоуны сущностей, закрытие дорог, аудит.
 *
 * Все мутации административные (`require_company_admin` на бэкенде);
 * аудит `geoOverridesOp` — сводный журнал по всем сущностям.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import type {
    GeoAddressHit,
    GeoOverrideListResponse,
} from '../wire/geo.gen.js';

export const geoAddressCreateOp = createAsyncOp<GeoAddressHit>({
    name: 'geo/addresses_create',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/addresses/create_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/addresses/create' },
    successToastKey: 'geo:toast.address_saved',
    errorToastKey: 'geo:toast.address_save_failed',
});

export const geoAddressUpdateOp = createAsyncOp<GeoAddressHit>({
    name: 'geo/addresses_update',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/addresses/update_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/addresses/update' },
    successToastKey: 'geo:toast.address_saved',
    errorToastKey: 'geo:toast.address_save_failed',
});

export const geoAddressRemoveOp = createAsyncOp<Record<string, never>>({
    name: 'geo/addresses_remove',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/addresses/remove_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/addresses/remove' },
    successToastKey: 'geo:toast.address_removed',
    errorToastKey: 'geo:toast.address_remove_failed',
});

export const geoAddressRevertOp = createAsyncOp<GeoAddressHit | null>({
    name: 'geo/addresses_revert',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/addresses/override_revert_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/addresses/override-revert' },
    successToastKey: 'geo:toast.override_reverted',
    errorToastKey: 'geo:toast.override_revert_failed',
});

export const geoOverridesOp = createAsyncOp<GeoOverrideListResponse>({
    name: 'geo/overrides',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/overrides/list_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/overrides/list' },
});

export const geoFeatureSuppressOp = createAsyncOp<Record<string, never>>({
    name: 'geo/features_suppress',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/features/suppress_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/features/suppress' },
    successToastKey: 'geo:toast.feature_suppressed',
    errorToastKey: 'geo:toast.feature_suppress_failed',
});

export const geoFeatureUnsuppressOp = createAsyncOp<Record<string, never>>({
    name: 'geo/features_unsuppress',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/features/unsuppress_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/features/unsuppress' },
    successToastKey: 'geo:toast.feature_restored',
    errorToastKey: 'geo:toast.feature_restore_failed',
});

export const geoEdgeCloseOp = createAsyncOp<Record<string, never>>({
    name: 'geo/edges_close',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/edges/close_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/edges/close' },
    successToastKey: 'geo:toast.edge_closed',
    errorToastKey: 'geo:toast.edge_close_failed',
});

export const geoEdgeOpenOp = createAsyncOp<Record<string, never>>({
    name: 'geo/edges_open',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/edges/open_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/edges/open' },
    successToastKey: 'geo:toast.edge_opened',
    errorToastKey: 'geo:toast.edge_open_failed',
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'geo/addresses_create': typeof geoAddressCreateOp;
        'geo/addresses_update': typeof geoAddressUpdateOp;
        'geo/addresses_remove': typeof geoAddressRemoveOp;
        'geo/addresses_revert': typeof geoAddressRevertOp;
        'geo/overrides': typeof geoOverridesOp;
        'geo/features_suppress': typeof geoFeatureSuppressOp;
        'geo/features_unsuppress': typeof geoFeatureUnsuppressOp;
        'geo/edges_close': typeof geoEdgeCloseOp;
        'geo/edges_open': typeof geoEdgeOpenOp;
    }
}
