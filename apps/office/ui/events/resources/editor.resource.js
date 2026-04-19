/**
 * Office Document Editor Config — JWT и URL для DocsAPI.DocEditor.
 *
 * Backend (`/documents/api/v1/documents/{binding_id}/editor-config`):
 *   GET → OfficeEditorConfigResponse {
 *       document_server_url, token, document, editorConfig, type
 *   }
 *
 * Используется страницей `<office-document-editor-page>` и компонентом
 * `<onlyoffice-host>` (последний получает `result` как prop `.config` и
 * монтирует DocsAPI.DocEditor поверх iframe-портала).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { nsHeader } from './_namespace-header.js';

export const documentEditorConfigOp = createAsyncOp({
    name: 'office/document_editor_config',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/documents/:binding_id/editor-config' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.bindingId !== 'string' || payload.bindingId.length === 0) {
            throw new Error('office/document_editor_config: payload.bindingId required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.bindingId)}/editor-config`,
            headers: nsHeader(ctx),
        });
    },
});
