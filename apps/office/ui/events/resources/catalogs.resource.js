/**
 * Office Catalogs — каталоги документов внутри namespace.
 *
 * Backend (`/documents/api/v1/catalogs`):
 *   GET    /                       → OfficeCatalogListResponse { items }
 *   GET    /{catalog_id}           → OfficeCatalogDetailResponse
 *   POST   /                       → OfficeCatalogDetailResponse
 *   PATCH  /{catalog_id}           → OfficeCatalogDetailResponse (title? / is_public?)
 *   DELETE /{catalog_id}           → 204
 *
 * idField — `catalog_id`. Все запросы несут заголовок `X-Platform-Namespace`.
 *
 * `catalogCreateForm` / `catalogEditForm` — формы для модалок
 * `office.catalog_create` и `office.catalog_edit`.
 */

import {
    createResourceCollection,
    createForm,
} from '@platform/lib/events/index.js';
import { nsHeader } from './_namespace-header.js';

export const catalogsResource = createResourceCollection({
    name: 'office/catalogs',
    baseUrl: '/documents/api/v1/catalogs',
    idField: 'catalog_id',
    operations: ['list', 'get', 'create', 'update', 'remove'],
    transport: 'http',
    requestHeaders: ({ ctx }) => nsHeader(ctx),
    restMirror: {
        list:   { method: 'GET',    path: '/documents/api/v1/catalogs' },
        get:    { method: 'GET',    path: '/documents/api/v1/catalogs/:catalog_id' },
        create: { method: 'POST',   path: '/documents/api/v1/catalogs' },
        update: { method: 'PATCH',  path: '/documents/api/v1/catalogs/:catalog_id' },
        remove: { method: 'DELETE', path: '/documents/api/v1/catalogs/:catalog_id' },
    },
    toastKeys: {
        create: 'documents:toast.catalog_created',
        create_error: 'documents:toast.catalog_create_failed',
        update: 'documents:toast.catalog_updated',
        update_error: 'documents:toast.catalog_update_failed',
        remove: 'documents:toast.catalog_deleted',
        remove_error: 'documents:toast.catalog_delete_failed',
    },
});

export const catalogCreateForm = createForm({
    name: 'office/catalog_create_form',
    schema: {
        title: {
            required: true,
            minLength: 1,
            maxLength: 128,
            errorKey: 'form.catalog_title_required',
        },
        is_public: {},
    },
    initial: { title: '', is_public: true },
    submitEvent: catalogsResource.events.CREATE_REQUESTED,
    buildPayload: (draft) => ({
        title: typeof draft.title === 'string' ? draft.title.trim() : '',
        is_public: Boolean(draft.is_public),
    }),
});

export const catalogEditForm = createForm({
    name: 'office/catalog_edit_form',
    schema: {
        catalog_id: { required: true },
        title: {
            required: true,
            minLength: 1,
            maxLength: 128,
            errorKey: 'form.catalog_title_required',
        },
        is_public: {},
    },
    initial: { catalog_id: '', title: '', is_public: false },
    submitEvent: catalogsResource.events.UPDATE_REQUESTED,
    buildPayload: (draft) => ({
        catalog_id: draft.catalog_id,
        title: typeof draft.title === 'string' ? draft.title.trim() : '',
        is_public: Boolean(draft.is_public),
    }),
});
