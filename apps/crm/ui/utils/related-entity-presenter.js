/**
 * Единые правила тона, иконки и подписи для карточек связанных сущностей (CRM).
 */

import { NOTE_ROOT_ENTITY_TYPE_ID } from '../constants/entity-type-ids.js';

export function entityKind(entity) {
    if (!entity || typeof entity.entity_type !== 'string') return '';
    return entity.entity_type;
}

export function relatedTone(entity) {
    const type = entityKind(entity);
    if (type === 'company' || type === 'organization' || type === 'team') return 'yellow';
    if (type === NOTE_ROOT_ENTITY_TYPE_ID || type === 'event' || type === 'meeting' || type === 'document') {
        return 'orange';
    }
    return 'violet';
}

export function relatedIcon(entity) {
    const type = entityKind(entity);
    if (type === 'company' || type === 'organization' || type === 'team') return 'building';
    if (type === NOTE_ROOT_ENTITY_TYPE_ID) return 'note';
    if (type === 'event' || type === 'meeting') return 'calendar';
    if (type === 'document') return 'folder';
    if (type === 'task') return 'check';
    return 'user';
}

export function relatedSubtitle(entity) {
    if (entity && typeof entity.entity_subtype === 'string' && entity.entity_subtype.length > 0) {
        return entity.entity_subtype;
    }
    if (entity && typeof entity.entity_type === 'string') {
        return entity.entity_type;
    }
    return '';
}
