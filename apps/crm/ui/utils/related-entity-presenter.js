/**
 * Единые правила тона, иконки и подписи для карточек связанных сущностей (CRM).
 */

import { NOTE_ROOT_ENTITY_TYPE_ID } from '../constants/entity-type-ids.js';

/** Если строк каталога типов нет или в каталоге нет icon для type_id — без угадывания типа в коде. */
const FALLBACK_ENTITY_GLYPH = 'box';

export function fallbackEntityGlyph() {
    return FALLBACK_ENTITY_GLYPH;
}

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

/**
 * Иконка сущности без каталога типов недоступна по доменным правилам — только нейтральный глиф.
 * Конкретная иконка: {@link entityDisplayIconName} и строки из API entity_types.
 */
export function relatedIcon(entity) {
    void entity;
    return FALLBACK_ENTITY_GLYPH;
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

/** Ключ для сопоставления строки из ai_summary_entities с именем сущности в карточке. */
export function normalizeSummaryEntityLabelKey(label) {
    if (typeof label !== 'string') return null;
    let s = label.trim();
    if (!s) return null;
    if (s.startsWith('@')) s = s.slice(1).trim();
    s = s.replace(/^["'([{]+|["')\]}.,;:!?]+$/g, '').trim();
    return s.length === 0 ? null : s.toLowerCase();
}

/** Имя иконки каталога типов для platform-icon (как на странице списка сущностей). */
export function normalizeCatalogIconName(iconName) {
    if (iconName === 'file') return 'folder';
    if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) return iconName;
    return 'folder';
}

function iconFromEntityTypesRow(typeId, rows, namespace) {
    if (typeof typeId !== 'string' || typeId.length === 0 || !Array.isArray(rows)) {
        return null;
    }
    let firstMatch = null;
    for (const row of rows) {
        if (typeof row !== 'object' || row === null) continue;
        if (row.type_id !== typeId) continue;
        if (firstMatch === null) firstMatch = row;
        if (typeof namespace === 'string' && namespace.length > 0 && row.namespace !== namespace) continue;
        const ic = row.icon;
        if (typeof ic === 'string' && ic.trim().length > 0) {
            return normalizeCatalogIconName(ic.trim());
        }
        return null;
    }
    if (firstMatch !== null) {
        const ic = firstMatch.icon;
        if (typeof ic === 'string' && ic.trim().length > 0) {
            return normalizeCatalogIconName(ic.trim());
        }
    }
    return null;
}

/**
 * Иконка для отображения сущности: subtype и root по строкам каталога entity_types;
 * если в каталоге нет icon для type_id — {@link fallbackEntityGlyph}.
 */
export function entityDisplayIconName(entity, entityTypeRows) {
    if (!entity || typeof entity !== 'object') {
        return 'folder';
    }
    const rows = Array.isArray(entityTypeRows) ? entityTypeRows : [];
    const namespace = typeof entity.namespace === 'string' ? entity.namespace.trim() : '';
    const sub = typeof entity.entity_subtype === 'string' ? entity.entity_subtype.trim() : '';
    if (sub.length > 0) {
        const fromSub = iconFromEntityTypesRow(sub, rows, namespace);
        if (fromSub !== null) {
            return fromSub;
        }
    }
    const root = typeof entity.entity_type === 'string' ? entity.entity_type.trim() : '';
    if (root.length > 0) {
        const fromRoot = iconFromEntityTypesRow(root, rows, namespace);
        if (fromRoot !== null) {
            return fromRoot;
        }
    }
    return fallbackEntityGlyph();
}

/** Иконка для чипа сводки, когда строку не удалось сопоставить с загруженной сущностью. */
export function summaryChipUnresolvedIconName() {
    return 'folder';
}

export function resolveSummaryChipEntity(label, lookup) {
    const key = normalizeSummaryEntityLabelKey(label);
    if (!key) return null;
    const found = lookup.get(key);
    return found === undefined ? null : found;
}

/** Lookup по имени для AI-сводки ежедневника: все связанные сущности по заметкам периода. */
export function buildSummaryEntityLookupFromNoteBuckets(noteEntitiesByNoteId) {
    const map = new Map();
    if (!noteEntitiesByNoteId || typeof noteEntitiesByNoteId !== 'object') return map;
    for (const list of Object.values(noteEntitiesByNoteId)) {
        if (!Array.isArray(list)) continue;
        for (const ent of list) {
            if (!ent || typeof ent !== 'object' || typeof ent.entity_id !== 'string') continue;
            if (ent.entity_type === 'note') continue;
            const rawName = typeof ent.name === 'string' ? ent.name : '';
            const key = normalizeSummaryEntityLabelKey(rawName);
            if (!key || map.has(key)) continue;
            map.set(key, ent);
        }
    }
    return map;
}

/** Lookup для карточки заметки: связанные сущности из bulk-карточки. */
export function buildSummaryEntityLookupFromRelated(relatedEntities) {
    const map = new Map();
    if (!Array.isArray(relatedEntities)) return map;
    for (const ent of relatedEntities) {
        if (!ent || typeof ent !== 'object' || typeof ent.entity_id !== 'string') continue;
        if (ent.entity_type === 'note') continue;
        const rawName = typeof ent.name === 'string' ? ent.name : '';
        const key = normalizeSummaryEntityLabelKey(rawName);
        if (!key || map.has(key)) continue;
        map.set(key, ent);
    }
    return map;
}
