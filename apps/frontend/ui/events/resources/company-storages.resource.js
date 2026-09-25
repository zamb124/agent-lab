/**
 * Хранилища компании: список, подключение, маршрут, перенос.
 */

import { createAsyncOp, createForm, createSlice } from '@platform/lib/events/index.js';

const WS_TIMEOUT_MS = 20_000;

export const companyStoragesLoadOp = createAsyncOp({
    name: 'frontend/company_storages_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/company_storages/list_requested',
    restMirror: { method: 'GET', path: '/frontend/api/company-storages' },
});

export const companyStoragesProbeOp = createAsyncOp({
    name: 'frontend/company_storages_probe',
    successToastKey: 'frontend:settings_page.storage_probe_ok',
    errorToastKey: 'frontend:settings_page.storage_probe_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/company_storages/probe_requested',
    restMirror: { method: 'POST', path: '/frontend/api/company-storages/probe' },
});

export const companyStoragesCreateOp = createAsyncOp({
    name: 'frontend/company_storages_create',
    successToastKey: 'frontend:settings_page.storages_saved',
    errorToastKey: 'frontend:settings_page.storages_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/company_storages/create_requested',
    restMirror: { method: 'POST', path: '/frontend/api/company-storages' },
    onSuccess: (ctx) => {
        ctx.dispatch(companyStoragesLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const companyStoragesRotateOp = createAsyncOp({
    name: 'frontend/company_storages_rotate',
    successToastKey: 'frontend:settings_page.storage_rotated',
    errorToastKey: 'frontend:settings_page.storages_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/company_storages/rotate_credentials_requested',
    restMirror: { method: 'POST', path: '/frontend/api/company-storages/rotate' },
    onSuccess: (ctx) => {
        ctx.dispatch(companyStoragesLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const companyStoragesDeleteOp = createAsyncOp({
    name: 'frontend/company_storages_delete',
    successToastKey: 'frontend:settings_page.storage_deleted',
    errorToastKey: 'frontend:settings_page.storages_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/company_storages/delete_requested',
    restMirror: { method: 'POST', path: '/frontend/api/company-storages/delete' },
    onSuccess: (ctx) => {
        ctx.dispatch(companyStoragesLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const companyStorageCreateForm = createForm({
    name: 'frontend/company_storage_create_form',
    submittingClearOnEventTypes: [
        companyStoragesCreateOp.events.SUCCEEDED,
        companyStoragesCreateOp.events.FAILED,
    ],
    schema: {
        name: { type: 'string', required: true },
        provider: { type: 'string', required: true },
        endpoint_url: { type: 'string', required: true },
        region_name: { type: 'string', required: true },
        bucket_name: { type: 'string', required: true },
        path_style: { type: 'boolean', required: true },
        access_key_id: { type: 'string', required: true },
        secret_access_key: { type: 'string', required: true },
    },
    initial: {
        name: '',
        provider: 'minio',
        endpoint_url: '',
        region_name: 'us-east-1',
        bucket_name: '',
        path_style: true,
        access_key_id: '',
        secret_access_key: '',
    },
    submitEvent: companyStoragesCreateOp.events.REQUESTED,
});

export const companyStorageRoutesSetOp = createAsyncOp({
    name: 'frontend/company_storage_routes_set',
    successToastKey: 'frontend:settings_page.storages_saved',
    errorToastKey: 'frontend:settings_page.storages_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/company_storage_routes/set_requested',
    restMirror: { method: 'POST', path: '/frontend/api/company-storages/routes' },
    onSuccess: (ctx) => {
        ctx.dispatch(companyStoragesLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const companyStorageMigrationsStartOp = createAsyncOp({
    name: 'frontend/company_storage_migrations_start',
    successToastKey: 'frontend:settings_page.storages_saved',
    errorToastKey: 'frontend:settings_page.storages_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/company_storage_migrations/start_requested',
    restMirror: { method: 'POST', path: '/frontend/api/company-storages/migrations' },
});

export const companyStorageMigrationSlice = createSlice({
    name: 'frontend/company_storage_migration',
    extraInitial: { progress: null },
    extraReducer: (state, event) => {
        if (event.type !== 'frontend/company_storage_migration/progressed') {
            return state;
        }
        const payload = event.payload;
        if (payload === null || typeof payload !== 'object') {
            return state;
        }
        if (typeof payload.storage_migration_id !== 'string') {
            return state;
        }
        return { ...state, progress: payload };
    },
});
