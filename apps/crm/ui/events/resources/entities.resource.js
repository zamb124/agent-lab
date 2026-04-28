/**
 * Entities — сущности CRM (cursor-paginated по `created_at, id`).
 *
 * Backend (`/crm/api/v1/entities`):
 *   GET    /                    → CursorPage[EntityResponse]   (list / search)
 *   GET    /search              → CursorPage[EntityResponse]
 *   POST   /query               → CursorPage[EntityResponse]
 *   GET    /aggregate           → { types: [...], statuses: [...], months: [...] }
 *   GET    /{id}                → EntityResponse
 *   POST   /                    → EntityResponse               (create)
 *   PUT    /{id}                → EntityResponse               (update via PUT)
 *   PUT    /bulk                → BulkUpdateResponse
 *   DELETE /{id}                → 204
 *   POST   /merge               → EntityMergeResponse
 *   POST   /bulk-delete         → BulkDeleteResponse
 *
 * `crm/entities_list` — основная cursor-лента с фильтрами namespace/типа/тегов/
 *   диапазона дат/режима поиска (text|semantic|hybrid).
 * `crm/entity_update` — отдельный AsyncOp с PUT (default ResourceCollection
 *   шлёт PATCH, что CRM не принимает).
 * `crm/entity_bulk_update`/`crm/entity_bulk_delete` — массовые операции.
 * `crm/entity_aggregate` — фасетная сводка для счётчиков и таймлайна.
 */

import {
    createResourceCollection,
    createAsyncOp,
    createCursorList,
    createForm,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const ENTITY_NAME_MAX = 256;
const ENTITY_DESCRIPTION_MAX = 4096;
const NAMESPACE_NAME_PATTERN = /^[a-z][a-z0-9_]*$/;

export const entitiesResource = createResourceCollection({
    name: 'crm/entities',
    baseUrl: '/crm/api/v1/entities',
    idField: 'entity_id',
    operations: ['get', 'create', 'remove'],
    toastKeys: {
        create: 'crm:toast.entity.created',
        create_error: 'crm:toast.entity.create_failed',
        remove: 'crm:toast.entity.removed',
        remove_error: 'crm:toast.entity.remove_failed',
    },
});

export const entityCardOp = createAsyncOp({
    name: 'crm/entity_card',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/card' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.entity_id !== 'string' || payload.entity_id.length === 0) {
            throw new Error('entityCardOp: payload.entity_id required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.entity_id)}/card`,
        });
    },
});

export const entityUpdateOp = createAsyncOp({
    name: 'crm/entity_update',
    successToastKey: 'crm:toast.entity.updated',
    errorToastKey: 'crm:toast.entity.update_failed',
    restMirror: { method: 'PUT', path: '/crm/api/v1/entities/:entity_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.id !== 'string' || !payload.body) {
            throw new Error('entityUpdateOp: { id, body } required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.id)}`,
            body: payload.body,
        });
    },
});

function _buildEntityQueryFilters(filters, dateField) {
    const leaves = [];
    if (typeof filters.status === 'string' && filters.status.length > 0) {
        leaves.push({ field: 'status', op: '$eq', value: filters.status });
    }
    if (Array.isArray(filters.tags) && filters.tags.length > 0) {
        for (const tag of filters.tags) {
            if (typeof tag === 'string' && tag.length > 0) {
                leaves.push({ field: 'tags', op: '$contains', value: tag });
            }
        }
    }
    if (typeof filters.date_from === 'string' && filters.date_from.length > 0) {
        leaves.push({ field: dateField, op: '$gte', value: filters.date_from });
    }
    if (typeof filters.date_to === 'string' && filters.date_to.length > 0) {
        leaves.push({ field: dateField, op: '$lte', value: filters.date_to });
    }
    if (leaves.length === 0) return null;
    if (leaves.length === 1) return leaves[0];
    return { $and: leaves };
}

export const entitiesListResource = createCursorList({
    name: 'crm/entities_list',
    baseUrl: '/crm/api/v1/entities/query',
    pageSize: 50,
    httpMethod: 'POST',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
    buildQuery: (filters) => {
        if (!filters || typeof filters !== 'object') {
            throw new Error('entitiesListResource.buildQuery: filters required');
        }
        const body = {};
        if (typeof filters.namespace === 'string' && filters.namespace.length > 0) {
            body.namespace = filters.namespace;
        }
        if (typeof filters.entity_type === 'string' && filters.entity_type.length > 0) {
            body.entity_type = filters.entity_type;
        }
        if (typeof filters.entity_subtype === 'string' && filters.entity_subtype.length > 0) {
            body.entity_subtype = filters.entity_subtype;
        }
        if (typeof filters.q === 'string' && filters.q.length > 0) {
            body.query = filters.q;
        }
        if (typeof filters.search_mode === 'string' && filters.search_mode.length > 0) {
            body.search_mode = filters.search_mode;
        }
        const dsl = _buildEntityQueryFilters(filters, 'created_at');
        if (dsl !== null) body.filters = dsl;
        return body;
    },
    statusMap: {
        403: 'forbidden',
    },
    errorToastKey: 'crm:toast.entities_list.failed',
});

export const entityMergeOp = createAsyncOp({
    name: 'crm/entity_merge',
    successToastKey: 'crm:toast.entity.merged',
    errorToastKey: 'crm:toast.entity.merge_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/merge' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('entityMergeOp: payload required');
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/merge',
            body: payload,
        });
    },
});

export const entityBulkDeleteOp = createAsyncOp({
    name: 'crm/entity_bulk_delete',
    successToastKey: 'crm:toast.entity.bulk_deleted',
    errorToastKey: 'crm:toast.entity.bulk_delete_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/bulk-delete' },
    request: async ({ payload }) => {
        if (!payload || !Array.isArray(payload.entity_ids) || payload.entity_ids.length === 0) {
            throw new Error('entityBulkDeleteOp: payload.entity_ids (non-empty) required');
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/bulk-delete',
            body: { entity_ids: payload.entity_ids },
        });
    },
});

export const entityBulkUpdateOp = createAsyncOp({
    name: 'crm/entity_bulk_update',
    successToastKey: 'crm:toast.entity.bulk_updated',
    errorToastKey: 'crm:toast.entity.bulk_update_failed',
    restMirror: { method: 'PUT', path: '/crm/api/v1/entities/bulk' },
    request: async ({ payload }) => {
        if (!payload || !Array.isArray(payload.items) || payload.items.length === 0) {
            throw new Error('entityBulkUpdateOp: payload.items (non-empty) required');
        }
        return await httpRequest({
            method: 'PUT',
            url: '/crm/api/v1/entities/bulk',
            body: { items: payload.items },
        });
    },
});

export const entitiesLookupOp = createAsyncOp({
    name: 'crm/entities_lookup',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('entitiesLookupOp: payload required');
        }
        const body = {};
        if (typeof payload.namespace === 'string' && payload.namespace.length > 0) body.namespace = payload.namespace;
        if (typeof payload.entity_type === 'string' && payload.entity_type.length > 0) body.entity_type = payload.entity_type;
        if (typeof payload.entity_subtype === 'string' && payload.entity_subtype.length > 0) {
            body.entity_subtype = payload.entity_subtype;
        }
        if (typeof payload.limit === 'number') body.limit = payload.limit;
        const dateLeaves = [];
        if (typeof payload.created_at_from === 'string' && payload.created_at_from.length > 0) {
            dateLeaves.push({ field: 'created_at', op: '$gte', value: payload.created_at_from });
        }
        if (typeof payload.created_at_to === 'string' && payload.created_at_to.length > 0) {
            dateLeaves.push({ field: 'created_at', op: '$lte', value: payload.created_at_to });
        }
        if (dateLeaves.length === 1) body.filters = dateLeaves[0];
        else if (dateLeaves.length > 1) body.filters = { $and: dateLeaves };
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/query',
            body,
        });
    },
});

export const entitySearchOp = createAsyncOp({
    name: 'crm/entity_search',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.q !== 'string' || payload.q.length === 0) {
            throw new Error('entitySearchOp: payload.q required');
        }
        const body = { query: payload.q };
        if (typeof payload.search_mode === 'string') body.search_mode = payload.search_mode;
        if (typeof payload.namespace === 'string') body.namespace = payload.namespace;
        if (typeof payload.entity_type === 'string') body.entity_type = payload.entity_type;
        if (typeof payload.limit === 'number') body.limit = payload.limit;
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/query',
            body,
        });
    },
});

export const entityAggregateOp = createAsyncOp({
    name: 'crm/entity_aggregate',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/aggregate' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('entityAggregateOp: payload required');
        }
        const query = {};
        if (typeof payload.namespace === 'string' && payload.namespace.length > 0) {
            query.namespace = payload.namespace;
        }
        return await httpRequest({
            method: 'GET',
            url: '/crm/api/v1/entities/aggregate',
            query,
        });
    },
});

function _normalizeAttributes(raw) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
    const out = {};
    for (const [key, value] of Object.entries(raw)) {
        if (typeof key !== 'string' || key.length === 0) continue;
        if (value === undefined) continue;
        if (typeof value === 'string' && value.trim().length === 0) continue;
        out[key] = value;
    }
    return out;
}

function _normalizeTags(raw) {
    if (!Array.isArray(raw)) return [];
    return raw
        .map((item) => (typeof item === 'string' ? item.trim() : ''))
        .filter((item) => item.length > 0);
}

function _trimmedOrNull(raw) {
    if (typeof raw !== 'string') return null;
    const value = raw.trim();
    return value.length === 0 ? null : value;
}

export const entityCreateForm = createForm({
    name: 'crm/entity_create_form',
    schema: {
        entity_type: {
            required: true,
            errorKey: 'entity_modal.err_type_required',
        },
        namespace: {
            required: true,
            pattern: NAMESPACE_NAME_PATTERN,
            errorKey: 'entity_modal.err_namespace_invalid',
        },
        name: {
            required: true,
            maxLength: ENTITY_NAME_MAX,
            errorKey: 'entity_modal.err_name_required',
        },
        description: {
            maxLength: ENTITY_DESCRIPTION_MAX,
        },
        attributes: {},
        tags: {},
    },
    initial: {
        entity_type: '',
        namespace: '',
        name: '',
        description: '',
        attributes: {},
        tags: [],
    },
    submitEvent: entitiesResource.events.CREATE_REQUESTED,
    buildPayload: (draft) => ({
        entity_type: draft.entity_type,
        namespace: draft.namespace,
        name: typeof draft.name === 'string' ? draft.name.trim() : '',
        description: _trimmedOrNull(draft.description),
        attributes: _normalizeAttributes(draft.attributes),
        tags: _normalizeTags(draft.tags),
    }),
});

export const entityEditForm = createForm({
    name: 'crm/entity_edit_form',
    schema: {
        id: {
            required: true,
            errorKey: 'entity_modal.err_id_required',
        },
        name: {
            required: true,
            maxLength: ENTITY_NAME_MAX,
            errorKey: 'entity_modal.err_name_required',
        },
        description: {
            maxLength: ENTITY_DESCRIPTION_MAX,
        },
        status: {},
        attributes: {},
        tags: {},
    },
    initial: {
        id: '',
        name: '',
        description: '',
        status: '',
        attributes: {},
        tags: [],
    },
    submitEvent: entityUpdateOp.events.REQUESTED,
    buildPayload: (draft) => ({
        id: draft.id,
        body: {
            name: typeof draft.name === 'string' ? draft.name.trim() : '',
            description: _trimmedOrNull(draft.description),
            status: typeof draft.status === 'string' && draft.status.length > 0 ? draft.status : null,
            attributes: _normalizeAttributes(draft.attributes),
            tags: _normalizeTags(draft.tags),
        },
    }),
});
