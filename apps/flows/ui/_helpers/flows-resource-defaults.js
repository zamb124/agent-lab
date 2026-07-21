/**
 * Default config для нового ресурса при drop из палитры.
 */

/**
 * @param {string} resourceType
 * @param {string} resourceKey
 * @returns {Record<string, unknown>}
 */
export function defaultResourceConfigForType(resourceType, resourceKey) {
    if (typeof resourceType !== 'string' || resourceType.length === 0) {
        throw new Error('defaultResourceConfigForType: resourceType required');
    }
    if (typeof resourceKey !== 'string' || resourceKey.length === 0) {
        throw new Error('defaultResourceConfigForType: resourceKey required');
    }
    if (resourceType === 'rag') {
        const slug = resourceKey.replace(/[^a-z0-9_-]/gi, '-').toLowerCase();
        const namespace = slug.startsWith('kb-') ? slug : `kb-${slug}`;
        return {
            namespace,
            provider: 'pgvector',
            default_top_k: 5,
        };
    }
    return {};
}

/**
 * @param {string} resourceType
 * @returns {string}
 */
export function defaultResourceDisplayName(resourceType) {
    if (resourceType === 'rag') {
        return 'RAG';
    }
    if (resourceType === 'llm') {
        return 'LLM';
    }
    if (resourceType === 'llm_context') {
        return 'LLM Context';
    }
    return resourceType;
}
