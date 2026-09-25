/**
 * Relationships — связи между сущностями.
 *
 * Backend (`/crm/api/v1/relationships`):
 *   GET    /                    → CursorPage[Relationship]  (HTTP cursor-list)
 *   GET    /{relationship_id}   → Relationship
 *   POST   /                    → Relationship
 *   DELETE /{relationship_id}   → 204
 *   GET    /path/               → ShortestPathResponse              (graph.resource)
 */

import {
    createResourceCollection,
    createCursorList,
} from '@platform/lib/events/index.js';

export const relationshipsResource = createResourceCollection({
    name: 'crm/relationships',
    baseUrl: '/crm/api/v1/relationships',
    idField: 'relationship_id',
    operations: ['get', 'create', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
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
        return query;
    },
    errorToastKey: 'crm:toast.relationships_list.failed',
});
