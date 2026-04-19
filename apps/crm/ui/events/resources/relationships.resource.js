/**
 * Relationships — связи между сущностями.
 *
 * Backend (`/crm/api/v1/relationships`):
 *   GET    /                    → CursorPage[RelationshipResponse]
 *   GET    /{id}                → RelationshipResponse
 *   POST   /                    → RelationshipResponse        (create)
 *   DELETE /{id}                → 204
 *   GET    /path/               → ShortestPathResponse        (отдельный op)
 */

import {
    createResourceCollection,
    createCursorList,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const relationshipsResource = createResourceCollection({
    name: 'crm/relationships',
    baseUrl: '/crm/api/v1/relationships',
    idField: 'relationship_id',
    operations: ['get', 'create', 'remove'],
    toastKeys: {
        create: 'crm:toast.relationship.created',
        create_error: 'crm:toast.relationship.create_failed',
        remove: 'crm:toast.relationship.removed',
        remove_error: 'crm:toast.relationship.remove_failed',
    },
});

export const relationshipsListResource = createCursorList({
    name: 'crm/relationships_list',
    baseUrl: '/crm/api/v1/relationships',
    pageSize: 50,
    buildQuery: (filters) => {
        if (!filters || typeof filters !== 'object') {
            throw new Error('relationshipsListResource.buildQuery: filters required');
        }
        const query = {};
        if (typeof filters.namespace === 'string' && filters.namespace.length > 0) {
            query.namespace = filters.namespace;
        }
        if (typeof filters.entity_id === 'string' && filters.entity_id.length > 0) {
            query.entity_id = filters.entity_id;
        }
        if (typeof filters.type_id === 'string' && filters.type_id.length > 0) {
            query.type_id = filters.type_id;
        }
        return query;
    },
    errorToastKey: 'crm:toast.relationships_list.failed',
});

export const relationshipShortestPathOp = createAsyncOp({
    name: 'crm/relationship_shortest_path',
    silent: true,
    request: async ({ payload }) => {
        if (!payload || typeof payload.from_id !== 'string' || typeof payload.to_id !== 'string') {
            throw new Error('relationshipShortestPathOp: { from_id, to_id } required');
        }
        const params = new URLSearchParams({ from_id: payload.from_id, to_id: payload.to_id });
        if (typeof payload.max_depth === 'number') {
            params.set('max_depth', String(payload.max_depth));
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/relationships/path/?${params.toString()}`,
        });
    },
});
