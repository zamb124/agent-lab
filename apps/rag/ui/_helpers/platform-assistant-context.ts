export interface RagAssistantContext {
    service: string;
    route_key: string;
    screen: string;
    namespace_id?: string;
    [key: string]: unknown;
}

export function buildRagAssistantContext(routeKey: string, params: Record<string, string>): RagAssistantContext {
    if (typeof routeKey !== 'string' || routeKey.length === 0) {
        throw new Error('buildRagAssistantContext: routeKey required');
    }
    if (!params || typeof params !== 'object') {
        throw new Error('buildRagAssistantContext: params required');
    }
    const context: RagAssistantContext = {
        service: 'rag',
        route_key: routeKey,
        screen: routeKey,
    };
    if (typeof params.namespaceId === 'string' && params.namespaceId.length > 0) {
        context.namespace_id = params.namespaceId;
    }
    return context;
}
