/**
 * Sync Namespaces — фабрики для платформенного namespace в UI Sync.
 *
 * Источник правды списка — `core/db/repositories/namespace_repository.py`
 * (shared KV `namespaces`); в UI достаётся через REST `apps/sync/api/namespaces.py`
 * (`GET /sync/api/v1/namespaces`). Обновление sync-настроек namespace —
 * `PUT /sync/api/v1/namespaces/{name}` с телом `{ sync_settings: NamespaceSyncSettings | null }`.
 *
 * Создание/удаление namespace выполняется в CRM (`apps/crm/api/namespaces.py`)
 * — sync только читает и пишет свою секцию `Namespace.sync_settings`.
 *
 * Паттерн полностью повторяет `apps/crm/ui/events/resources/namespaces.resource.js`:
 * `createResourceCollection` (operations: ['list']) + отдельный
 * `createAsyncOp` для PUT-апдейта (стандартный resource.update шлёт PATCH,
 * а REST-зеркало хочет PUT — поэтому отдельный op с явным `request`).
 */

import { createAsyncOp, createResourceCollection, httpRequest } from '@platform/lib/events/index.js';

export const namespacesResource = createResourceCollection({
    name: 'sync/namespaces',
    baseUrl: '/sync/api/v1/namespaces',
    idField: 'name',
    operations: ['list'],
    listQuery: () => ({ limit: 200, offset: 0 }),
});

export const namespaceUpdateOp = createAsyncOp({
    name: 'sync/namespace_update',
    successToastKey: 'sync:namespace_settings.toast_saved',
    errorToastKey: 'sync:namespace_settings.toast_save_failed',
    restMirror: { method: 'PUT', path: '/sync/api/v1/namespaces/:namespace_name' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.name !== 'string' || payload.name === '') {
            throw new Error('namespaceUpdateOp: payload.name (string) required');
        }
        if (!payload.body || typeof payload.body !== 'object') {
            throw new Error('namespaceUpdateOp: payload.body (object) required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `/sync/api/v1/namespaces/${encodeURIComponent(payload.name)}`,
            body: payload.body,
        });
    },
});
