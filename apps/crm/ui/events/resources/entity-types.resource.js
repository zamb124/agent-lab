/**
 * Entity Types — типы сущностей CRM (привязаны к namespace).
 *
 * Backend (`/crm/api/v1/entity-types`):
 *   GET    /                                → OffsetPage[EntityTypeResponse]
 *   GET    /by-namespace/{namespace}        → OffsetPage[EntityTypeResponse]
 *   GET    /{type_id}                       → EntityTypeResponse
 *   POST   /                                → EntityTypeResponse
 *   PUT    /{type_id}                       → EntityTypeResponse  (через PUT)
 *   POST   /{type_id}/namespaces            → EntityTypeResponse
 *   PUT    /{type_id}/public-fields         → EntityTypeResponse  (через PUT)
 *
 * `update` — отдельный `entityTypeUpdateOp` (PUT).
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const entityTypesResource = createResourceCollection({
    name: 'crm/entity_types',
    baseUrl: '/crm/api/v1/entity-types',
    idField: 'type_id',
    operations: ['list', 'get', 'create'],
    listQuery: (payload) => {
        if (!payload || typeof payload !== 'object') {
            return { limit: 200, offset: 0 };
        }
        const limit = typeof payload.limit === 'number' ? payload.limit : 200;
        const offset = typeof payload.offset === 'number' ? payload.offset : 0;
        const query = { limit, offset };
        if (typeof payload.namespace === 'string' && payload.namespace.length > 0) {
            query.namespace = payload.namespace;
        }
        return query;
    },
    toastKeys: {
        create: 'crm:toast.entity_type.created',
    },
});

export const entityTypeUpdateOp = createAsyncOp({
    name: 'crm/entity_type_update',
    successToastKey: 'crm:toast.entity_type.updated',
    errorToastKey: 'crm:toast.entity_type.update_failed',
    restMirror: { method: 'PUT', path: '/crm/api/v1/entity-types/:type_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.type_id !== 'string' || !payload.body) {
            throw new Error('entityTypeUpdateOp: { type_id, body } required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `/crm/api/v1/entity-types/${encodeURIComponent(payload.type_id)}`,
            body: payload.body,
        });
    },
});

export const entityTypePublicFieldsOp = createAsyncOp({
    name: 'crm/entity_type_public_fields',
    successToastKey: 'crm:toast.entity_type.public_fields_updated',
    errorToastKey: 'crm:toast.entity_type.public_fields_update_failed',
    restMirror: { method: 'PUT', path: '/crm/api/v1/entity-types/:type_id/public-fields' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.type_id !== 'string' || !Array.isArray(payload.fields)) {
            throw new Error('entityTypePublicFieldsOp: { type_id, fields } required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `/crm/api/v1/entity-types/${encodeURIComponent(payload.type_id)}/public-fields`,
            body: { fields: payload.fields },
        });
    },
});
