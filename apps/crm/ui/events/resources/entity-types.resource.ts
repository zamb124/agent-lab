/**
 * Entity Types — типы сущностей CRM (одна строка = company_id + namespace + type_id).
 *
 * GET    /                                → OffsetPage (опционально ?namespace=)
 * GET    /{type_id}?namespace=            → EntityTypeResponse
 * POST   /                                → EntityTypeResponse (body.namespace)
 * PUT    /{type_id}?namespace=             → EntityTypeResponse
 * PUT    /{type_id}/public-fields         → body CrmEntityTypePublicFieldsPayload
 *
 * Идентификатор строки в коллекции: crm_entity_type_row_id = `${namespace}\\0${type_id}`.
 * GET item в operations нет: фабрика слала бы composite id, бэкенд принимает type_id + namespace.
 */

import {
    createResourceCollection,
    createAsyncOp,
    upsertItem,
} from '@platform/lib/events/index.js';

const ROW_SEP = '\u0000';

function rowIdFromRaw(raw: unknown): string {
    if (!raw || typeof raw !== 'object') {
        throw new Error('crm/entity_types rowId: object required');
    }
    const r = raw as Record<string, unknown>;
    const ns = r.namespace;
    const tid = r.type_id;
    if (typeof ns !== 'string' || !ns.length) {
        throw new Error('crm/entity_types rowId: namespace string required');
    }
    if (typeof tid !== 'string' || !tid.length) {
        throw new Error('crm/entity_types rowId: type_id string required');
    }
    return `${ns}${ROW_SEP}${tid}`;
}

function mapEntityType(raw: unknown) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('crm/entity_types mapItem: item object required');
    }
    const r = raw as Record<string, unknown>;
    const listEntityType = r.list_entity_type;
    if (typeof listEntityType !== 'string' || listEntityType.length === 0) {
        throw new Error('crm/entity_types mapItem: list_entity_type string required');
    }
    let listEntitySubtype = r.list_entity_subtype;
    if (listEntitySubtype === undefined || listEntitySubtype === null) {
        listEntitySubtype = null;
    } else if (typeof listEntitySubtype !== 'string') {
        throw new Error('crm/entity_types mapItem: list_entity_subtype must be string or null');
    } else if (listEntitySubtype.length === 0) {
        listEntitySubtype = null;
    }
    return {
        ...raw,
        crm_entity_type_row_id: rowIdFromRaw(raw),
        list_entity_type: listEntityType,
        list_entity_subtype: listEntitySubtype,
    };
}

const ENTITY_TYPE_UPDATE_SUCCEEDED = 'crm/entity_type_update/succeeded';

export const entityTypesResource = createResourceCollection({
    name: 'crm/entity_types',
    baseUrl: '/crm/api/v1/entity-types',
    idField: 'crm_entity_type_row_id',
    operations: ['list', 'create'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listFetchAllPages: true,
    listQuery: (payload) => {
        if (!payload || typeof payload !== 'object') {
            return { limit: 200, offset: 0 };
        }
        const limit = typeof payload.limit === 'number' ? payload.limit : 200;
        const offset = typeof payload.offset === 'number' ? payload.offset : 0;
        const query: Record<string, any> = { limit, offset };
        if (typeof payload.namespace === 'string' && payload.namespace.length > 0) {
            query.namespace = payload.namespace;
        }
        return query;
    },
    mapItem: mapEntityType,
    toastKeys: {
        create: 'crm:toast.entity_type.created',
    },
    extraReducer: (state, event) => {
        if (event.type !== ENTITY_TYPE_UPDATE_SUCCEEDED) {
            return state;
        }
        const updated = (event.payload as Record<string, any>).result;
        if (!updated || typeof updated !== 'object' || typeof updated.type_id !== 'string') {
            return state;
        }
        return upsertItem(state, mapEntityType(updated), 'crm_entity_type_row_id');
    },
});

export const entityTypeUpdateOp = createAsyncOp({
    name: 'crm/entity_type_update',
    successToastKey: 'crm:toast.entity_type.updated',
    errorToastKey: 'crm:toast.entity_type.update_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entity_types/update_requested',
    restMirror: { method: 'PUT', path: '/crm/api/v1/entity-types/:type_id' },
});

export const entityTypePublicFieldsOp = createAsyncOp({
    name: 'crm/entity_type_public_fields',
    successToastKey: 'crm:toast.entity_type.public_fields_updated',
    errorToastKey: 'crm:toast.entity_type.public_fields_update_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entity_types/public_fields_requested',
    restMirror: { method: 'PUT', path: '/crm/api/v1/entity-types/:type_id/public-fields' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/entity_types': typeof entityTypesResource;
        'crm/entity_type_update': typeof entityTypeUpdateOp;
        'crm/entity_type_public_fields': typeof entityTypePublicFieldsOp;
    }
}
