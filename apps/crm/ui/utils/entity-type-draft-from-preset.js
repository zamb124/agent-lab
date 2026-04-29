/**
 * Черновик редактора типа из снимка типа шаблона пространства.
 * type_id подставляется из снимка; пользователь может изменить перед сохранением.
 */

import { normalizeSchemaRows } from '../components/schema-field-builder.js';
import { entityTypeNoteSubtreeLocked } from './entity-type-note-subtree-lock.js';

/**
 * @param {object} item — объект типа из ответа GET /templates/{id} (поля type_id, name, …)
 * @param {{ type_id: string, parent_type_id: string }[]} catalogRows
 * @param {(overrides?: object) => object} makeTypeDraft — фабрика черновика страницы (space или templates)
 * @param {{ namespaceIds: boolean }} opts — для templates-page: true, для space: false
 */
export function buildEntityTypeDraftFromTemplateTypeItem(item, catalogRows, makeTypeDraft, opts) {
    if (!item || typeof item !== 'object' || typeof item.type_id !== 'string' || item.type_id.length === 0) {
        throw new Error('buildEntityTypeDraftFromTemplateTypeItem: item.type_id required');
    }
    if (typeof makeTypeDraft !== 'function') {
        throw new Error('buildEntityTypeDraftFromTemplateTypeItem: makeTypeDraft required');
    }
    const withNs = opts !== undefined && opts.namespaceIds === true;
    const parentId = typeof item.parent_type_id === 'string' ? item.parent_type_id : '';
    const noteLocked = entityTypeNoteSubtreeLocked(
        { type_id: item.type_id, parent_type_id: parentId },
        catalogRows,
    );
    const payload = {
        type_id: item.type_id,
        name: typeof item.name === 'string' ? item.name : '',
        description: typeof item.description === 'string' ? item.description : '',
        prompt: typeof item.prompt === 'string' ? item.prompt : '',
        required_fields_rows: normalizeSchemaRows(
            item.required_fields !== undefined && item.required_fields !== null && typeof item.required_fields === 'object'
                ? item.required_fields
                : {},
        ),
        optional_fields_rows: normalizeSchemaRows(
            item.optional_fields !== undefined && item.optional_fields !== null && typeof item.optional_fields === 'object'
                ? item.optional_fields
                : {},
        ),
        parent_type_id: parentId,
        icon: typeof item.icon === 'string' ? item.icon : '',
        color: typeof item.color === 'string' ? item.color : '',
        is_event: item.is_event === true,
        check_duplicates: item.check_duplicates !== false,
        is_context_anchor: noteLocked ? false : item.is_context_anchor === true,
        is_voice_target: noteLocked ? false : item.is_voice_target === true,
        weight_coefficient: String(item.weight_coefficient === undefined ? 1 : item.weight_coefficient),
    };
    if (withNs) {
        payload.namespace_ids = Array.isArray(item.namespace_ids) ? [...item.namespace_ids] : [];
    }
    return makeTypeDraft(payload);
}
