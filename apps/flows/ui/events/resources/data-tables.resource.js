/**
 * DataTable create/snapshot for the flows resource editor.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const flowsDataTableCreateOp = createAsyncOp({
    name: 'flows/data_table_create',
    transport: 'http',
    restMirror: { method: 'POST', path: '/flows/api/v1/data-tables' },
    successToastKey: 'flows:data_table_resource_editor.toast_created',
    errorToastKey: 'flows:data_table_resource_editor.toast_create_failed',
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('flowsDataTableCreateOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/data-tables',
            body: payload,
        });
    },
});

export const flowsDataTableSnapshotOp = createAsyncOp({
    name: 'flows/data_table_snapshot',
    silent: true,
    transport: 'http',
    restMirror: { method: 'GET', path: '/documents/api/v1/data-tables/{file_id}', service: 'office' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
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
