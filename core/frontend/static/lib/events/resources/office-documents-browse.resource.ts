/**
 * Browse Documents для platform.file_picker: список каталогов, файлы каталога, поиск.
 * Те же op_catalogs_list / op_documents_list / op_documents_search, что REST office.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const catalogsListOp = createAsyncOp({
    name: 'office/catalogs_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/list_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs' },
});

export const documentsListOp = createAsyncOp({
    name: 'office/documents_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/list_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/documents' },
});

export const documentsSearchOp = createAsyncOp({
    name: 'office/documents_search',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/search_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/documents/search' },
});
