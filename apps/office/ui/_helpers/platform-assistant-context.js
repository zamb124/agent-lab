function _nonEmptyString(value) {
    return typeof value === 'string' && value.length > 0 ? value : null;
}

export function buildOfficeAssistantContext(routeKey, params, documentsState) {
    if (typeof routeKey !== 'string' || routeKey.length === 0) {
        throw new Error('buildOfficeAssistantContext: routeKey required');
    }
    if (!params || typeof params !== 'object') {
        throw new Error('buildOfficeAssistantContext: params required');
    }
    if (!documentsState || typeof documentsState !== 'object') {
        throw new Error('buildOfficeAssistantContext: documentsState required');
    }
    const context = {
        service: 'office',
        route_key: routeKey,
        screen: routeKey,
    };
    const routeBindingId = _nonEmptyString(params.bindingId);
    const selectedBindingId = _nonEmptyString(documentsState.selectedBindingId);
    if (routeBindingId !== null) {
        context.binding_id = routeBindingId;
    } else if (selectedBindingId !== null) {
        context.binding_id = selectedBindingId;
    }
    const catalogId = _nonEmptyString(documentsState.activeCatalogId);
    if (catalogId !== null) {
        context.catalog_id = catalogId;
    }
    return context;
}
