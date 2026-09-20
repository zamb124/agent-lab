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

import { createAsyncOp } from '@platform/lib/events/index.js';

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

export const timelineBoundsOp = createAsyncOp({
    name: 'crm/timeline_bounds',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/timeline_bounds_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/timeline/bounds' },
});
