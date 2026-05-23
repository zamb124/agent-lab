/**
 * Реестр типов UI-блоков flows-chat. Используется всеми поверхностями чата flows.
 */

/** @type {Map<string, { ComponentClass: typeof import('lit').LitElement, schema: object|null, tagName: string }>} */
const types = new Map();

/**
 * @param {string} typeId
 * @param {typeof import('lit').LitElement} ComponentClass
 * @param {object|null} [schema]
 * @param {string} tagName - имя custom element (например flows-chat-ui-card)
 */
export function registerFlowChatBlockType(typeId, ComponentClass, schema = null, tagName = null) {
    if (!typeId || typeof typeId !== 'string') {
        throw new Error('registerFlowChatBlockType: typeId required');
    }
    if (!ComponentClass) {
        throw new Error('registerFlowChatBlockType: ComponentClass required');
    }
    if (!tagName || typeof tagName !== 'string') {
        throw new Error('registerFlowChatBlockType: tagName required');
    }
    types.set(typeId, { ComponentClass, schema, tagName });
}

export function getFlowChatBlockEntry(typeId) {
    return types.get(typeId) || null;
}

export function listFlowChatBlockTypes() {
    return Array.from(types.keys());
}

export function clearFlowChatBlockTypesForTests() {
    types.clear();
}
