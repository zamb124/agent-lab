/**
 * Пространства в UI Sync — platform Namespace 1:1.
 *
 * Список — общий op реестра (`sync/namespaces/list_requested` → `op_namespaces_list`),
 * запись — только секция `Namespace.sync_settings` (`sync/namespace/sync_settings_update_requested`).
 * Создание/удаление пространства — CRM.
 */

import { createAsyncOp, createResourceCollection } from '@platform/lib/events/index.js';

export const namespacesResource = createResourceCollection({
    name: 'sync/namespaces',
    baseUrl: '/sync/api/v1/namespaces',
    idField: 'name',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({ limit: 200, offset: 0 }),
    restMirror: { list: { method: 'GET', path: '/sync/api/v1/namespaces' } },
});

export const namespaceUpdateOp = createAsyncOp({
    name: 'sync/namespace_update',
    successToastKey: 'sync:namespace_settings.toast_saved',
    errorToastKey: 'sync:namespace_settings.toast_save_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'sync/namespace/sync_settings_update_requested',
    restMirror: { method: 'PUT', path: '/sync/api/v1/namespaces/:name' },
});
