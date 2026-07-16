const FRONTEND_SCREEN_BY_ROUTE = Object.freeze({
    dashboard: 'dashboard',
    platform_services: 'services',
    team: 'team',
    'api-keys': 'api_keys',
    'company-variables': 'company_variables',
    'company-voice-providers': 'company_voice_providers',
    'embed-configs': 'embed_configs',
    billing: 'billing',
    'scheduler-tasks': 'scheduler_tasks',
    settings: 'settings',
    'lead-requests': 'lead_requests',
    'platform-tracing': 'platform_tracing',
    'crawl-report': 'crawl_report',
    'platform-billing': 'platform_billing',
});

export function buildFrontendAssistantContext(routeKey) {
    if (typeof routeKey !== 'string' || routeKey.length === 0) {
        throw new Error('buildFrontendAssistantContext: routeKey required');
    }
    const screen = FRONTEND_SCREEN_BY_ROUTE[routeKey];
    if (typeof screen !== 'string') {
        throw new Error(`buildFrontendAssistantContext: unsupported console route ${routeKey}`);
    }
    return {
        service: 'frontend',
        route_key: routeKey,
        screen,
    };
}
