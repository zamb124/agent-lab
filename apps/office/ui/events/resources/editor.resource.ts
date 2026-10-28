/**
 * Office Document Editor Config — JWT и URL для DocsAPI.DocEditor.
 *
 * Backend (`GET /documents/api/v1/documents/{file_id}/editor-config`):
 *   → DocumentOpenConfigResponse (handler + typed payload + capabilities).
 *
 * Используется `<office-document-editor-page>` → `<platform-document-viewer-host>`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { nsHeader } from './_namespace-header.js';

export const documentEditorConfigOp = createAsyncOp({
    name: 'office/document_editor_config',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/documents/:file_id/editor-config' },
    request: ({ payload, ctx }) => {
        const requestPayload = payload as { fileId?: unknown; namespace?: unknown } | null;
        if (!requestPayload || typeof requestPayload.fileId !== 'string' || requestPayload.fileId.length === 0) {
            throw new Error('office/document_editor_config: payload.fileId required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/documents/${encodeURIComponent(requestPayload.fileId)}/editor-config`,
            headers: nsHeader(ctx, typeof requestPayload.namespace === 'string' ? requestPayload.namespace : ''),
        });
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'office/document_editor_config': typeof documentEditorConfigOp;
    }
}
