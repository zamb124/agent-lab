/**
 * Query проводника Документов: workspace + папка + access-модалка.
 *
 * @param {unknown} search `state.router.search` (`?a=b` или пустая строка)
 * @returns {{ catalogId: string, namespace: string, access: boolean }}
 */
export function documentsExplorerQuery(search) {
    const raw = typeof search === 'string' ? search : '';
    const query = raw.startsWith('?') ? raw.slice(1) : raw;
    const params = new URLSearchParams(query);
    const catalogId = params.get('catalog_id');
    const namespace = params.get('namespace');
    return {
        catalogId: typeof catalogId === 'string' && catalogId.length > 0 ? catalogId : '',
        namespace: typeof namespace === 'string' && namespace.length > 0 ? namespace : '',
        access: params.get('access') === '1',
    };
}

/**
 * Deep-link из `state.router.search`. Если router ещё пустой, а в адресной
 * строке уже есть `catalog_id`/`namespace` — читаем `location.search`
 * (полный заход на `/documents?…`, до ROUTER_ROUTE_CHANGED).
 *
 * @param {unknown} routerSearch `state.router.search`
 * @param {unknown} locationSearch `window.location.search`
 * @returns {{ catalogId: string, namespace: string, access: boolean }}
 */
export function documentsExplorerPageQuery(routerSearch, locationSearch) {
    const routed = documentsExplorerQuery(routerSearch);
    if (routed.catalogId.length > 0 || routed.namespace.length > 0) {
        return routed;
    }
    return documentsExplorerQuery(locationSearch);
}

/**
 * Workspace для deep-link. Явный `namespace` главнее. Если есть только
 * `catalog_id` — `default` (тот же namespace, что AuthMiddleware без заголовка).
 *
 * @param {{ catalogId: string, namespace: string }} query
 * @returns {string}
 */
export function documentsExplorerQueryNamespace(query) {
    if (!query || typeof query !== 'object') {
        throw new Error('documentsExplorerQueryNamespace: query object required');
    }
    if (query.namespace.length > 0) {
        return query.namespace;
    }
    if (query.catalogId.length > 0) {
        return 'default';
    }
    return '';
}
