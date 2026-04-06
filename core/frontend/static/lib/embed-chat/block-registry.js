/**
 * Реестр типов блоков embed-chat (расширяется хостом).
 */

/** @type {Map<string, { ComponentClass: typeof import('lit').LitElement, schema: object|null, tagName: string }>} */
const types = new Map();

/**
 * @param {string} typeId
 * @param {typeof import('lit').LitElement} ComponentClass
 * @param {object|null} [schema]
 * @param {string} tagName - имя custom element (например embed-ui-card)
 */
export function registerEmbedBlockType(typeId, ComponentClass, schema = null, tagName = null) {
    if (!typeId || typeof typeId !== 'string') {
        throw new Error('registerEmbedBlockType: typeId required');
    }
    if (!ComponentClass) {
        throw new Error('registerEmbedBlockType: ComponentClass required');
    }
    if (!tagName || typeof tagName !== 'string') {
        throw new Error('registerEmbedBlockType: tagName required');
    }
    types.set(typeId, { ComponentClass, schema, tagName });
}

export function getEmbedBlockEntry(typeId) {
    return types.get(typeId) || null;
}

export function listEmbedBlockTypes() {
    return Array.from(types.keys());
}

export function clearEmbedBlockTypesForTests() {
    types.clear();
}
