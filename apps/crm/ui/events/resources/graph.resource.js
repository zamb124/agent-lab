/**
 * Graph — граф влияния, связей и кратчайших путей между сущностями.
 *
 * Backend (`/crm/api/v1/entities`):
 *   POST /overview-graph                       → InfluenceGraphResponse
 *   GET  /{entity_id}/influence-graph          → InfluenceGraphResponse
 *   GET  /{entity_id}/related                  → RelatedEntitiesResponse
 *   GET  /{entity_id}/relationships            → EntityRelationshipsResponse
 *   GET  /shortest-path                        → ShortestPathResponse
 *   GET  /timeline/bounds                      → TimelineBoundsResponse
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

function _buildQuery(params) {
    const url = new URLSearchParams();
    Object.keys(params).forEach((key) => {
        const value = params[key];
        if (value === null || value === undefined) {
            return;
        }
        if (typeof value === 'object') {
            return;
        }
        url.set(key, String(value));
    });
    const qs = url.toString();
    return qs.length > 0 ? `?${qs}` : '';
}

export const overviewGraphOp = createAsyncOp({
    name: 'crm/overview_graph',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/overview-graph' },
    request: async ({ payload }) => {
        if (!payload || !Array.isArray(payload.entity_ids) || payload.entity_ids.length === 0) {
            throw new Error('overviewGraphOp: payload.entity_ids required');
        }
        const body = { entity_ids: payload.entity_ids };
        if (typeof payload.max_depth === 'number') body.max_depth = payload.max_depth;
        if (typeof payload.relationship_types === 'string') body.relationship_types = payload.relationship_types;
        if (typeof payload.namespace === 'string') body.namespace = payload.namespace;
        if (typeof payload.created_at_from === 'string') body.created_at_from = payload.created_at_from;
        if (typeof payload.created_at_to === 'string') body.created_at_to = payload.created_at_to;
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/overview-graph',
            body,
        });
    },
});

export const influenceGraphOp = createAsyncOp({
    name: 'crm/influence_graph',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/influence-graph' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.entityId !== 'string' || payload.entityId.length === 0) {
            throw new Error('influenceGraphOp: payload.entityId required');
        }
        const params = (payload.params && typeof payload.params === 'object') ? payload.params : {};
        const qs = _buildQuery(params);
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.entityId)}/influence-graph${qs}`,
        });
    },
});

export const relatedEntitiesOp = createAsyncOp({
    name: 'crm/related_entities',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/related' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.entityId !== 'string' || payload.entityId.length === 0) {
            throw new Error('relatedEntitiesOp: payload.entityId required');
        }
        const params = (payload.params && typeof payload.params === 'object') ? payload.params : {};
        const qs = _buildQuery(params);
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.entityId)}/related${qs}`,
        });
    },
});

export const entityRelationshipsOp = createAsyncOp({
    name: 'crm/entity_relationships',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/relationships' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.entityId !== 'string' || payload.entityId.length === 0) {
            throw new Error('entityRelationshipsOp: payload.entityId required');
        }
        const params = (payload.params && typeof payload.params === 'object') ? payload.params : {};
        const qs = _buildQuery(params);
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.entityId)}/relationships${qs}`,
        });
    },
});

/**
 * `shortestPathOp` делает GET `/crm/api/v1/relationships/path/` с параметрами
 * `from` / `to`. Ранее UI вызывал `/crm/api/v1/entities/shortest-path` —
 * такого роута в `apps/crm/api/**` нет; эндпоинт кратчайшего пути живёт в
 * `apps/crm/api/relationships.py` (router prefix `/relationships`).
 * На время подготовки backend alias'а `/entities/shortest-path` выравниваем
 * UI на существующий путь, а payload (`source_id`/`target_id`) маппим в
 * query `from`/`to`.
 */
export const shortestPathOp = createAsyncOp({
    name: 'crm/shortest_path',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/relationships/path/' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.source_id !== 'string' || typeof payload.target_id !== 'string') {
            throw new Error('shortestPathOp: payload.source_id and target_id required');
        }
        const params = {
            from: payload.source_id,
            to: payload.target_id,
        };
        if (typeof payload.max_depth === 'number') params.max_depth = payload.max_depth;
        if (typeof payload.namespace === 'string') params.namespace = payload.namespace;
        if (typeof payload.created_at_from === 'string') params.created_at_from = payload.created_at_from;
        if (typeof payload.created_at_to === 'string') params.created_at_to = payload.created_at_to;
        const qs = _buildQuery(params);
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/relationships/path/${qs}`,
        });
    },
});

export const timelineBoundsOp = createAsyncOp({
    name: 'crm/timeline_bounds',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/timeline/bounds' },
    request: async ({ payload }) => {
        const params = {};
        if (payload && typeof payload.namespace === 'string') {
            params.namespace = payload.namespace;
        }
        const qs = _buildQuery(params);
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/entities/timeline/bounds${qs}`,
        });
    },
});
