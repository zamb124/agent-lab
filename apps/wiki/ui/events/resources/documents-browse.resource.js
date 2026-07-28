/**
 * Browse Documents из wiki: каталоги и файлы для platform.file_picker.
 *
 * HTTP — Office BFF (`/documents/api/v1/...`) с `X-Platform-Namespace`.
 * Имена фабрик `wiki/*`: wiki не регистрирует `office/*`.
 * restMirror.service = office — path живёт в apps/office/api, не в wiki.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { platformNamespaceHeader } from '@platform/lib/utils/platform-namespace-header.js';

export const wikiCatalogsOp = createAsyncOp({
    name: 'wiki/catalogs',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/documents/api/v1/catalogs',
        service: 'office',
    },
    request: ({ ctx }) => httpRequest({
        method: 'GET',
        url: '/documents/api/v1/catalogs',
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiDocumentsOp = createAsyncOp({
    name: 'wiki/documents',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/documents/api/v1/documents',
        service: 'office',
    },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('wiki/documents: payload required');
        }
        const catalogId = payload.catalog_id;
        if (typeof catalogId !== 'string' || catalogId.length === 0) {
            throw new Error('wiki/documents: catalog_id required');
        }
        const params = new URLSearchParams();
        params.set('catalog_id', catalogId);
        if (typeof payload.q === 'string' && payload.q.trim() !== '') {
            params.set('q', payload.q.trim());
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/documents?${params.toString()}`,
            headers: platformNamespaceHeader(ctx),
        });
    },
});

export const wikiDocumentsSearchOp = createAsyncOp({
    name: 'wiki/documents_search',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/documents/api/v1/documents/search',
        service: 'office',
    },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('wiki/documents_search: payload required');
        }
        const q = payload.q;
        if (typeof q !== 'string' || q.trim() === '') {
            throw new Error('wiki/documents_search: q required');
        }
        const params = new URLSearchParams();
        params.set('q', q.trim());
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/documents/search?${params.toString()}`,
            headers: platformNamespaceHeader(ctx),
        });
    },
});
