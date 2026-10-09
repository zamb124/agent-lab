export function buildLitserveAssistantContext(routeKey: string): Record<string, unknown> {
    if (typeof routeKey !== 'string' || routeKey.length === 0) {
        throw new Error('buildLitserveAssistantContext: routeKey required');
    }
    return {
        service: 'provider_litserve',
        route_key: routeKey,
        screen: routeKey,
    };
}
