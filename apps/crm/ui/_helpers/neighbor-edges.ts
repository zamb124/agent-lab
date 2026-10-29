/**
 * Рёбра карточки сущности, пригодные для единого списка «соседей».
 */

import { entityKind } from './related-entity-presenter.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export const NEIGHBOR_EDGE_EXCLUDED_TYPES = Object.freeze(['note_voice', 'in_context']);

export interface NeighborEdge {
    rel: Record<string, unknown>;
    otherId: string;
    otherEntity: Record<string, unknown> | null;
    isOutgoing: boolean;
}

export function extractNeighborEdges(
    card: Record<string, unknown> | null,
    centerEntityId: string,
    options: { excludedRelationshipTypes?: Iterable<string>; skipTaskNeighbors?: boolean } = {},
): NeighborEdge[] {
    if (typeof centerEntityId !== 'string' || centerEntityId.length === 0) {
        throw new Error('extractNeighborEdges: centerEntityId required');
    }
    const excluded = options.excludedRelationshipTypes !== undefined
        ? new Set(options.excludedRelationshipTypes)
        : new Set(NEIGHBOR_EDGE_EXCLUDED_TYPES);
    const skipTaskNeighbors = options.skipTaskNeighbors !== false;

    const rels = card !== null && typeof card === 'object' && Array.isArray(card.relationships)
        ? card.relationships
        : [];
    const related = card !== null && typeof card === 'object' && Array.isArray(card.related_entities)
        ? card.related_entities
        : [];
    const byId: Record<string, Record<string, unknown>> = {};
    for (const raw of related) {
        if (!isPlainRecord(raw)) continue;
        const entityId = raw.entity_id;
        if (typeof entityId !== 'string' || entityId.length === 0) continue;
        byId[entityId] = raw;
    }

    const out: NeighborEdge[] = [];
    for (const rel of rels) {
        if (!rel || typeof rel.relationship_id !== 'string') continue;
        if (typeof rel.relationship_type !== 'string') continue;
        if (excluded.has(rel.relationship_type)) continue;
        if (typeof rel.source_entity_id !== 'string' || typeof rel.target_entity_id !== 'string') {
            continue;
        }
        const isOutgoing = rel.source_entity_id === centerEntityId;
        const otherId = isOutgoing ? rel.target_entity_id : rel.source_entity_id;
        if (typeof otherId !== 'string' || otherId.length === 0) continue;
        const storedEntity = byId[otherId];
        const otherEntity = storedEntity === undefined ? null : storedEntity;
        if (skipTaskNeighbors && otherEntity !== null && entityKind(otherEntity) === 'task') {
            continue;
        }
        out.push({ rel, otherId, otherEntity, isOutgoing });
    }
    return out;
}
