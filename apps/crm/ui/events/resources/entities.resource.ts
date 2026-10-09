/**
 * Entities — сущности CRM (cursor-paginated по `created_at, id`).
 *
 * Backend (`/crm/api/v1/entities`):
 *   POST   /query               → CursorPage[EntityResponse]
 *   GET    /aggregate           → { types: [...], statuses: [...], months: [...] }
 *   GET    /{entity_id}         → EntityResponse | JsonObject
 *   POST   /                    → EntityResponse
 *   PUT    /{entity_id}         → EntityResponse
 *   PUT    /bulk                → BulkUpdateResponse
 *   DELETE /{entity_id}         → 204
 *   POST   /merge               → EntityMergeResponse
 *   POST   /bulk-delete         → BulkDeleteResponse
 *   GET    /{entity_id}/card    → card bundle
 *
 * `crm/entities_list` — основная cursor-лента с фильтрами namespace/типа/тегов/
 *   диапазона дат/режима поиска (text|semantic|hybrid).
 * `crm/entity_update` — отдельный AsyncOp с PUT (ResourceCollection по умолчанию
 *   шлёт PATCH, что CRM не принимает). Payload = EntityUpdate + entity_id.
 * Лента `crm/entities_list` остаётся HTTP: createCursorList шлёт UI-filters,
 * а команда `crm/entities/query_requested` принимает EntitySearchQueryRequest.
 */

import {
    createResourceCollection,
    createAsyncOp,
    createCursorList,
    createForm,
    rerunLastRequest,
} from '@platform/lib/events/index.js';

const ENTITY_NAME_MAX = 256;
const ENTITY_DESCRIPTION_MAX = 4096;
const NAMESPACE_NAME_PATTERN = /^[a-z][a-z0-9_]*$/;

export const entitiesResource = createResourceCollection({
    name: 'crm/entities',
    baseUrl: '/crm/api/v1/entities',
    idField: 'entity_id',
    operations: ['get', 'create', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    toastKeys: {
        create: 'crm:toast.entity.created',
        create_error: 'crm:toast.entity.create_failed',
        remove: 'crm:toast.entity.removed',
        remove_error: 'crm:toast.entity.remove_failed',
    },
    extraReducer: (state, event) => {
        if (event.type !== 'crm/note/updated') {
            return state;
        }
        const payload = (event.payload as Record<string, any>);
        if (!payload || typeof payload !== 'object') {
            return state;
        }
        const noteId = payload.note_id;
        if (typeof noteId !== 'string' || noteId.length === 0) {
            return state;
        }
        if (payload.action === 'deleted') {
            if (!state.byId || !(noteId in state.byId)) {
                return state;
            }
            const byId = { ...state.byId };
            delete byId[noteId];
            const items = Array.isArray(state.items)
                ? state.items.filter((item) => item && item.entity_id !== noteId)
                : state.items;
            return { ...state, byId, items };
        }
        const note = payload.note;
        if (!note || typeof note !== 'object' || typeof note.entity_id !== 'string') {
            return state;
        }
        if (!state.byId || !(noteId in state.byId)) {
            return state;
        }
        const byId = { ...state.byId, [noteId]: note };
        const items = Array.isArray(state.items)
            ? state.items.map((item) => (item && item.entity_id === noteId ? note : item))
            : state.items;
        return { ...state, byId, items };
    },
});

const RELATIONSHIP_CHANGED_EVENTS = new Set([
    'crm/relationships/created',
    'crm/relationships/removed',
]);

/**
 * Карточка сущности (entity + relationships + related_entities + attachments):
 * связи и related нельзя смержить из исхода команды, поэтому после изменения
 * связей и обновления сущности фабрика перечитывает открытую карточку сама.
 */
export const entityCardOp = createAsyncOp({
    name: 'crm/entity_card',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/card_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/card' },
    extraEffect: async (event, ctx) => {
        if (!RELATIONSHIP_CHANGED_EVENTS.has(event.type)) {
            return false;
        }
        rerunLastRequest(ctx, entityCardOp);
        return false;
    },
});

export const entityUpdateOp = createAsyncOp({
    name: 'crm/entity_update',
    successToastKey: 'crm:toast.entity.updated',
    errorToastKey: 'crm:toast.entity.update_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/update_requested',
    restMirror: { method: 'PUT', path: '/crm/api/v1/entities/:entity_id' },
    onSuccess: (ctx, result) => {
        rerunLastRequest(ctx, entityCardOp, {
            when: (request) => Boolean(request)
                && (request as Record<string, unknown>).entity_id === (result as Record<string, unknown>).entity_id,
        });
    },
});

function _buildEntityQueryFilters(filters: Record<string, any>, dateField: string): Record<string, unknown> | null {
    const leaves: Record<string, unknown>[] = [];
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
    if (leaves.length === 1) return leaves[0] ?? null;
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
        const body: Record<string, unknown> = {};
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
    extraReducer: (state, event) => {
        if (event.type === 'crm/entity_bulk_delete/succeeded') {
            const result = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).result ? (event.payload as Record<string, any>).result : null;
            const deleted = result && Array.isArray(result.deleted) ? result.deleted : null;
            if (!deleted || deleted.length === 0) {
                return state;
            }
            const removed = new Set(deleted);
            const items = Array.isArray(state.items)
                ? state.items.filter((item) => item && !removed.has(item.entity_id))
                : state.items;
            return { ...state, items };
        }
        if (event.type === 'crm/entity_bulk_update/succeeded') {
            const result = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).result ? (event.payload as Record<string, any>).result : null;
            const updated = result && Array.isArray(result.updated) ? result.updated : null;
            if (!updated || updated.length === 0) {
                return state;
            }
            const byId = new Map();
            for (const entity of updated) {
                if (entity && typeof entity.entity_id === 'string') {
                    byId.set(entity.entity_id, entity);
                }
            }
            if (byId.size === 0 || !Array.isArray(state.items)) {
                return state;
            }
            const items = state.items.map((item) => {
                if (!item || typeof item.entity_id !== 'string') {
                    return item;
                }
                const next = byId.get(item.entity_id);
                return next || item;
            });
            return { ...state, items };
        }
        if (event.type === 'crm/entity_merge/succeeded') {
            const result = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).result ? (event.payload as Record<string, any>).result : null;
            if (!result || typeof result !== 'object') {
                return state;
            }
            const survivor = result.entity;
            const mergedFrom = result.merged_from_entity_id;
            if (!survivor || typeof survivor.entity_id !== 'string') {
                return state;
            }
            if (typeof mergedFrom !== 'string' || mergedFrom.length === 0) {
                return state;
            }
            if (!Array.isArray(state.items)) {
                return state;
            }
            const items = [];
            let survivorSeen = false;
            for (const item of state.items) {
                if (!item || typeof item.entity_id !== 'string') {
                    continue;
                }
                if (item.entity_id === mergedFrom) {
                    continue;
                }
                if (item.entity_id === survivor.entity_id) {
                    items.push(survivor);
                    survivorSeen = true;
                    continue;
                }
                items.push(item);
            }
            if (!survivorSeen) {
                items.unshift(survivor);
            }
            return { ...state, items };
        }
        return state;
    },
});

export const entityMergeOp = createAsyncOp({
    name: 'crm/entity_merge',
    successToastKey: 'crm:toast.entity.merged',
    errorToastKey: 'crm:toast.entity.merge_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/merge_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/merge' },
});

export const entityBulkDeleteOp = createAsyncOp({
    name: 'crm/entity_bulk_delete',
    successToastKey: 'crm:toast.entity.bulk_deleted',
    errorToastKey: 'crm:toast.entity.bulk_delete_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/bulk_delete_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/bulk-delete' },
});

export const entityBulkUpdateOp = createAsyncOp({
    name: 'crm/entity_bulk_update',
    successToastKey: 'crm:toast.entity.bulk_updated',
    errorToastKey: 'crm:toast.entity.bulk_update_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/bulk_update_requested',
    restMirror: { method: 'PUT', path: '/crm/api/v1/entities/bulk' },
});

export const entitiesLookupOp = createAsyncOp({
    name: 'crm/entities_lookup',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/query_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
});

export const entitySearchOp = createAsyncOp({
    name: 'crm/entity_search',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/query_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
});

export const entityAggregateOp = createAsyncOp({
    name: 'crm/entity_aggregate',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/aggregate_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/aggregate' },
});

function _normalizeAttributes(raw: unknown): Record<string, unknown> {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
    const out: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(raw)) {
        if (typeof key !== 'string' || key.length === 0) continue;
        if (value === undefined) continue;
        if (typeof value === 'string' && value.trim().length === 0) continue;
        out[key] = value;
    }
    return out;
}

function _normalizeTags(raw: unknown): string[] {
    if (!Array.isArray(raw)) return [];
    return raw
        .map((item) => (typeof item === 'string' ? item.trim() : ''))
        .filter((item) => item.length > 0);
}

function _trimmedOrNull(raw: unknown): string | null {
    if (typeof raw !== 'string') return null;
    const value = raw.trim();
    return value.length === 0 ? null : value;
}

export const entityCreateForm = createForm({
    name: 'crm/entity_create_form',
    submittingClearOnEventTypes: [
        entitiesResource.events.CREATED,
        entitiesResource.events.CREATE_FAILED,
    ],
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
        entity_id: {
            required: true,
            errorKey: 'entity_modal.err_id_required',
        },
        entity_type: {
            required: true,
            errorKey: 'entity_modal.err_type_required',
        },
        entity_subtype: {},
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
        entity_id: '',
        entity_type: '',
        entity_subtype: '',
        name: '',
        description: '',
        status: '',
        attributes: {},
        tags: [],
    },
    submitEvent: entityUpdateOp.events.REQUESTED,
    buildPayload: (draft) => {
        const et = typeof draft.entity_type === 'string' ? draft.entity_type.trim() : '';
        if (et.length === 0) {
            throw new Error('entityEditForm.buildPayload: entity_type required');
        }
        const subRaw = typeof draft.entity_subtype === 'string' ? draft.entity_subtype.trim() : '';
        return {
            entity_id: draft.entity_id,
            name: typeof draft.name === 'string' ? draft.name.trim() : '',
            description: _trimmedOrNull(draft.description),
            status: typeof draft.status === 'string' && draft.status.length > 0 ? draft.status : null,
            attributes: _normalizeAttributes(draft.attributes),
            tags: _normalizeTags(draft.tags),
            entity_type: et,
            entity_subtype: subRaw.length > 0 ? subRaw : null,
        };
    },
});
