/**
 * Плоский объект type_id → подпись типа связи для подписей на рёбрах графа.
 */

/**
 * @param {unknown} items
 * @returns {Record<string, string>}
 */
export function buildRelationshipTypeLabelMapFromItems(items) {
    if (!Array.isArray(items)) {
        throw new Error('buildRelationshipTypeLabelMapFromItems: items must be an array');
    }
    /** @type {Record<string, string>} */
    const out = {};
    for (const it of items) {
        if (!it || typeof it !== 'object') {
            continue;
        }
        const idRaw = it.type_id;
        const id = typeof idRaw === 'string' ? idRaw.trim() : '';
        if (id.length === 0) {
            continue;
        }
        const nameRaw = it.name;
        const name = typeof nameRaw === 'string' ? nameRaw.trim() : '';
        out[id] = name.length > 0 ? name : id;
    }
    return out;
}
