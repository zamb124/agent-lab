/**
 * Graph — граф влияния, связей и кратчайших путей между сущностями.
 *
 * Бэкенд (`/crm/api/v1`):
 *   GET  /entities/person-entity/self           → EntityResponse
 *   POST /entities/overview-graph               → InfluenceGraphResponse
 *   GET  /entities/{entity_id}/influence-graph  → InfluenceGraphResponse
 *   GET  /entities/{entity_id}/related          → RelatedEntitiesResponse
 *   GET  /entities/{entity_id}/relationships    → CrmEntityRelationshipsResponse
 *   GET  /relationships/path/                   → ShortestPathResponse
 *   GET  /entities/timeline/bounds              → EntityTimelineBoundsResponse
 *
 * Payload = Pydantic snake_case. `relationship_types` — list[str].
 * Путь — `source_entity_id` / `target_entity_id`.
 */

import { createAsyncOp, rerunLastRequest } from '@platform/lib/events/index.js';

const ENTITY_MERGE_SUCCEEDED = 'crm/entity_merge/succeeded';

export const personEntitySelfOp = createAsyncOp({
    name: 'crm/person_entity_self',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/person_self_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/person-entity/self' },
});

export const overviewGraphOp = createAsyncOp({
    name: 'crm/overview_graph',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/overview_graph_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/overview-graph' },
});

export const influenceGraphOp = createAsyncOp({
    name: 'crm/influence_graph',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/influence_graph_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/influence-graph' },
});

export const relatedEntitiesOp = createAsyncOp({
    name: 'crm/related_entities',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/related_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/related' },
});

export const entityRelationshipsOp = createAsyncOp({
    name: 'crm/entity_relationships',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/relationships_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/relationships' },
});

export const shortestPathOp = createAsyncOp({
    name: 'crm/shortest_path',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/relationships/path_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/relationships/path/' },
});

export const exclusiveRelatedOp = createAsyncOp({
    name: 'crm/exclusive_related',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/exclusive_related_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/exclusive-related' },
});

/**
 * Границы таймлайна — корень цепочки загрузки графа (bounds → overview/influence).
 * Merge сущностей меняет топологию рёбер, граф не patchable: фабрика перезапускает
 * цепочку с последнего запроса, если граф уже открывали.
 */
export const timelineBoundsOp = createAsyncOp({
    name: 'crm/timeline_bounds',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/timeline_bounds_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/timeline/bounds' },
    extraEffect: async (event, ctx) => {
        if (event.type === ENTITY_MERGE_SUCCEEDED) {
            rerunLastRequest(ctx, timelineBoundsOp);
        }
        return false;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/person_entity_self': typeof personEntitySelfOp;
        'crm/overview_graph': typeof overviewGraphOp;
        'crm/influence_graph': typeof influenceGraphOp;
        'crm/related_entities': typeof relatedEntitiesOp;
        'crm/entity_relationships': typeof entityRelationshipsOp;
        'crm/shortest_path': typeof shortestPathOp;
        'crm/exclusive_related': typeof exclusiveRelatedOp;
        'crm/timeline_bounds': typeof timelineBoundsOp;
    }
}
