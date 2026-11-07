/**
 * Geo — реестр покрытия: регионы, источники, статистика, статус импорта.
 *
 * `geoRegionsResource` — CRUD-коллекция регионов (idField `name`;
 * ws-команды `geo/regions/<verb>_requested`, REST `/geo/api/v1/regions`).
 * Остальные — одиночные async-опросы для страницы «Источники».
 */

import { createAsyncOp, createResourceCollection } from '@platform/lib/events/index.js';
import type {
    GeoCursorItem,
    GeoCursorListResponse,
    GeoEnrichItemResponse,
    GeoEnrichListResponse,
    GeoImportRunResponse,
    GeoImportStatusResponse,
    GeoRegionItem,
    GeoSourceListResponse,
    GeoStatsOverview,
} from '../wire/geo.gen.js';

export const geoRegionsResource = createResourceCollection<GeoRegionItem>({
    name: 'geo/regions',
    baseUrl: '/geo/api/v1/regions',
    idField: 'name',
    operations: ['list', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: {
        list:   { method: 'GET',    path: '/geo/api/v1/regions' },
        create: { method: 'POST',   path: '/geo/api/v1/regions' },
        update: { method: 'PUT',    path: '/geo/api/v1/regions/:name' },
        remove: { method: 'DELETE', path: '/geo/api/v1/regions/:name' },
    },
    toastKeys: {
        create: 'geo:toast.region_created',
        create_error: 'geo:toast.region_create_failed',
        update: 'geo:toast.region_updated',
        update_error: 'geo:toast.region_update_failed',
        remove: 'geo:toast.region_removed',
        remove_error: 'geo:toast.region_remove_failed',
    },
});

export const geoSourcesOp = createAsyncOp<GeoSourceListResponse>({
    name: 'geo/sources',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/sources/list_requested',
    restMirror: { method: 'GET', path: '/geo/api/v1/sources' },
});

export const geoStatsOp = createAsyncOp<GeoStatsOverview>({
    name: 'geo/stats',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/stats/overview_requested',
    restMirror: { method: 'GET', path: '/geo/api/v1/stats/overview' },
});

export const geoCursorsOp = createAsyncOp<GeoCursorListResponse>({
    name: 'geo/cursors',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/cursors/list_requested',
    restMirror: { method: 'GET', path: '/geo/api/v1/cursors' },
});

export const geoImportStatusOp = createAsyncOp<GeoImportStatusResponse>({
    name: 'geo/import_status',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/import/status_requested',
    restMirror: { method: 'GET', path: '/geo/api/v1/import/status' },
});

export const geoEnrichOp = createAsyncOp<GeoEnrichListResponse>({
    name: 'geo/enrich',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/enrich/list_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/enrich/list' },
});

export const geoCursorResetOp = createAsyncOp<GeoCursorItem>({
    name: 'geo/cursor_reset',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/cursors/reset_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/cursors/reset' },
    successToastKey: 'geo:toast.cursor_reset',
    errorToastKey: 'geo:toast.cursor_reset_failed',
});

export const geoEnrichRetryOp = createAsyncOp<GeoEnrichItemResponse>({
    name: 'geo/enrich_retry',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/enrich/retry_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/enrich/retry' },
    successToastKey: 'geo:toast.enrich_retried',
    errorToastKey: 'geo:toast.enrich_retry_failed',
});

export const geoImportRunOp = createAsyncOp<GeoImportRunResponse>({
    name: 'geo/import_run',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'geo/import/run_requested',
    restMirror: { method: 'POST', path: '/geo/api/v1/import/run' },
    successToastKey: 'geo:toast.import_enqueued',
    errorToastKey: 'geo:toast.import_enqueue_failed',
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'geo/regions': typeof geoRegionsResource;
        'geo/sources': typeof geoSourcesOp;
        'geo/stats': typeof geoStatsOp;
        'geo/cursors': typeof geoCursorsOp;
        'geo/cursor_reset': typeof geoCursorResetOp;
        'geo/enrich': typeof geoEnrichOp;
        'geo/enrich_retry': typeof geoEnrichRetryOp;
        'geo/import_status': typeof geoImportStatusOp;
        'geo/import_run': typeof geoImportRunOp;
    }
}
