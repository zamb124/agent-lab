/**
 * Default config для нового ресурса при drop из палитры.
 */

/**
 * @param {string} resourceType
 * @param {string} resourceKey
 * @returns {Record<string, unknown>}
 */
export function defaultResourceConfigForType(resourceType: any, resourceKey: any) {
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
    if (resourceType === 'data_table') {
        return { file_id: '' };
    }
    return {};
}

/**
 * @param {string} stem
 * @returns {string}
 */
export function dataTableIdentFromStem(stem: any) {
    if (typeof stem !== 'string' || stem.trim().length === 0) {
        throw new Error('dataTableIdentFromStem: stem required');
    }
    let tableName = stem.toLowerCase().replace(/[^a-z0-9_]/g, '_');
    if (tableName.length === 0 || tableName[0]! < 'a' || tableName[0]! > 'z') {
        return 'data';
    }
    return tableName;
}

/**
 * @param {string} flowId
 * @param {string} stem
 */
export function dataTableCreateRequest(flowId: string, stem: any) {
    if (typeof flowId !== 'string' || flowId.trim().length === 0) {
        throw new Error('dataTableCreateRequest: flowId required');
    }
    if (typeof stem !== 'string' || stem.trim().length === 0) {
        throw new Error('dataTableCreateRequest: stem required');
    }
    const trimmed = stem.trim();
    return {
        original_name: `${trimmed}.sqlite`,
        scope: 'flow_asset',
        flow_id: flowId.trim(),
        tables: [
            {
                name: dataTableIdentFromStem(trimmed),
                columns: [{ name: 'value', column_type: 'text', not_null: false }],
            },
        ],
    };
}

/**
 * @param {string} resourceType
 * @returns {string}
 */
export function defaultResourceDisplayName(resourceType: any) {
    if (resourceType === 'rag') {
        return 'RAG';
    }
    if (resourceType === 'llm') {
        return 'LLM';
    }
    if (resourceType === 'llm_context') {
        return 'LLM Context';
    }
    if (resourceType === 'data_table') {
        return 'Data table';
    }
    return resourceType;
}
