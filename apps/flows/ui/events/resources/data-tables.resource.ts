/**
 * DataTable create — flows command. Snapshot схемы — office REST (нет office WS-команды).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export const flowsDataTableCreateOp = createAsyncOp({
    name: 'flows/data_table_create',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/data_tables/create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/data-tables' },
    successToastKey: 'flows:data_table_resource_editor.toast_created',
    errorToastKey: 'flows:data_table_resource_editor.toast_create_failed',
});

export const flowsDataTableSnapshotOp = createAsyncOp({
    name: 'flows/data_table_snapshot',
    silent: true,
    transport: 'http',
    restMirror: { method: 'GET', path: '/documents/api/v1/data-tables/{file_id}', service: 'office' },
    request: async ({ payload }) => {
        if (!isPlainRecord(payload)) {
            throw new Error('flowsDataTableSnapshotOp: payload required');
        }
        const fileId = payload.file_id;
        if (typeof fileId !== 'string' || fileId.length === 0) {
            throw new Error('flowsDataTableSnapshotOp: file_id required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/data-tables/${encodeURIComponent(fileId)}`,
        });
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/data_table_create': typeof flowsDataTableCreateOp;
        'flows/data_table_snapshot': typeof flowsDataTableSnapshotOp;
    }
}
