/**
 * Entity Types — типы сущностей CRM (одна строка = company_id + namespace + type_id).
 *
 * GET    /                                → OffsetPage (опционально ?namespace=)
 * GET    /by-namespace/{namespace}        → OffsetPage
 * GET    /{type_id}?namespace=            → EntityTypeResponse
 * POST   /                                → EntityTypeResponse (body.namespace)
 * PUT    /{type_id}?namespace=             → EntityTypeResponse
 * PUT    /{type_id}/public-fields?namespace=
 *
 * Идентификатор строки в коллекции: crm_entity_type_row_id = `${namespace}\\0${type_id}`.
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const ROW_SEP = '\u0000';

function rowIdFromRaw(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('crm/entity_types rowId: object required');
    }
    const ns = raw.namespace;
    const tid = raw.type_id;
    if (typeof ns !== 'string' || !ns.length) {
        throw new Error('crm/entity_types rowId: namespace string required');
    }
    if (typeof tid !== 'string' || !tid.length) {
        throw new Error('crm/entity_types rowId: type_id string required');
    }
    return `${ns}${ROW_SEP}${tid}`;
}

function parseRowId(rowId) {
    if (typeof rowId !== 'string' || !rowId.length) {
        throw new Error('crm/entity_types: row id string required');
    }
    const i = rowId.indexOf(ROW_SEP);
    if (i <= 0 || i === rowId.length - 1) {
        throw new Error('crm/entity_types: invalid row id');
    }
    return {
        namespace: rowId.slice(0, i),
        type_id: rowId.slice(i + ROW_SEP.length),
    };
}

export const entityTypesResource = createResourceCollection({
    name: 'crm/entity_types',
    baseUrl: '/crm/api/v1/entity-types',
    idField: 'crm_entity_type_row_id',
    operations: ['list', 'get', 'create'],
    restMirror: {
        get: { method: 'GET', path: '/crm/api/v1/entity-types/:type_id' },
    },
    listFetchAllPages: true,
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
    buildItemUrl: (rowId) => {
        const { namespace, type_id: typeId } = parseRowId(rowId);
        return `/crm/api/v1/entity-types/${encodeURIComponent(typeId)}?namespace=${encodeURIComponent(namespace)}`;
    },
    mapItem: (raw) => {
        if (!raw || typeof raw !== 'object') {
            throw new Error('crm/entity_types mapItem: item object required');
        }
        const listEntityType = raw.list_entity_type;
        if (typeof listEntityType !== 'string' || listEntityType.length === 0) {
            throw new Error('crm/entity_types mapItem: list_entity_type string required');
        }
        let listEntitySubtype = raw.list_entity_subtype;
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
            throw new Error('entityTypeUpdateOp: { type_id, namespace, body } required');
        }
        if (typeof payload.namespace !== 'string' || !payload.namespace.length) {
            throw new Error('entityTypeUpdateOp: namespace required');
        }
        const { type_id: typeId, namespace, body } = payload;
        return await httpRequest({
            method: 'PUT',
            url: `/crm/api/v1/entity-types/${encodeURIComponent(typeId)}?namespace=${encodeURIComponent(namespace)}`,
            body,
        });
    },
});

export const entityTypePublicFieldsOp = createAsyncOp({
    name: 'crm/entity_type_public_fields',
    successToastKey: 'crm:toast.entity_type.public_fields_updated',
    errorToastKey: 'crm:toast.entity_type.public_fields_update_failed',
    restMirror: { method: 'PUT', path: '/crm/api/v1/entity-types/:type_id/public-fields' },
    request: async ({ payload }) => {
        if (
            !payload
            || typeof payload.type_id !== 'string'
            || typeof payload.namespace !== 'string'
            || !payload.namespace.length
            || !Array.isArray(payload.fields)
        ) {
            throw new Error('entityTypePublicFieldsOp: { type_id, namespace, fields } required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `/crm/api/v1/entity-types/${encodeURIComponent(payload.type_id)}/public-fields?namespace=${encodeURIComponent(payload.namespace)}`,
            body: { public_fields: payload.fields },
        });
    },
});
