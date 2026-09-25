/**
 * Типы под деревом базового типа `note` не могут быть голосом заметки и якорем
 * контекста (см. crm.mdc). Используется в редакторе типа и при сохранении.
 *
 * @param {object} draft — черновик с полями `type_id`, `parent_type_id`
 * @param {object[]|null|undefined} catalogRows — типы из каталога `{ type_id, parent_type_id }`
 */
export function entityTypeNoteSubtreeLocked(draft, catalogRows) {
    if (draft === null || draft === undefined || typeof draft !== 'object') {
        throw new Error('entityTypeNoteSubtreeLocked: draft required');
    }
    if (typeof draft.type_id !== 'string' || draft.type_id.length === 0) {
        return false;
    }
    const parentByTypeId = new Map();
    if (Array.isArray(catalogRows)) {
        for (const row of catalogRows) {
            if (row === null || row === undefined || typeof row !== 'object') {
                continue;
            }
            if (typeof row.type_id !== 'string' || row.type_id.length === 0) {
                continue;
            }
            const p =
                typeof row.parent_type_id === 'string' && row.parent_type_id.length > 0
                    ? row.parent_type_id
                    : '';
            parentByTypeId.set(row.type_id, p);
        }
    }
    let cur = draft.type_id;
    for (let step = 0; step < 128; step += 1) {
        if (cur === 'note') {
            return true;
        }
        let next = parentByTypeId.has(cur) ? parentByTypeId.get(cur) : null;
        if (next === null && cur === draft.type_id) {
            const d = draft.parent_type_id;
            next =
                typeof d === 'string' && d.length > 0
                    ? d
                    : '';
        }
        if (next === null) {
            next = '';
        }
        if (next === '') {
            break;
        }
        cur = next;
    }
    return false;
}
