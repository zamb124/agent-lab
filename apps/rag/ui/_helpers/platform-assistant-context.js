export function buildRagAssistantContext(routeKey, params) {
    if (typeof routeKey !== 'string' || routeKey.length === 0) {
        throw new Error('buildRagAssistantContext: routeKey required');
    }
    if (!params || typeof params !== 'object') {
        throw new Error('buildRagAssistantContext: params required');
    }
    const context = {
        service: 'rag',
        route_key: routeKey,
        screen: routeKey,
    };
    if (typeof params.namespaceId === 'string' && params.namespaceId.length > 0) {
        context.namespace_id = params.namespaceId;
    }
    return context;
}
