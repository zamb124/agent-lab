/**
 * Relationship Types — типы связей между сущностями.
 *
 * Backend (`/crm/api/v1/relationships/types`):
 *   GET  /  → OffsetPage[RelationshipTypeResponse]
 *   POST /  → RelationshipTypeResponse
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

export const relationshipTypesResource = createResourceCollection({
    name: 'crm/relationship_types',
    baseUrl: '/crm/api/v1/relationships/types/',
    idField: 'type_id',
    operations: ['list', 'create'],
    listQuery: () => ({ limit: 200, offset: 0 }),
    toastKeys: {
        create: 'crm:toast.relationship_type.created',
    },
});
