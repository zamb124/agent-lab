/**
 * Палитра типов нод и категорийная карта семантических токенов.
 *
 * Никаких hex цветов: значение `var(--…)` в `CATEGORY_TOKEN` указывает на
 * семантическую CSS-переменную из `core/frontend/static/assets/css/tokens.css`,
 * благодаря чему canvas, sidebar и floating-panel автоматически адаптируются
 * к смене темы.
 *
 * Используется в `flows-node-types-sidebar`, `flows-flow-canvas` и шапке
 * `flows-floating-panel`.
 */

export const NODE_TYPE_META = Object.freeze({
    llm_node:     { icon: 'llm_node', category: 'core' },
    resource:     { icon: 'box', category: 'flow' },
    code:         { icon: 'code',     category: 'code' },
    code_agent:   { icon: 'code_agent', category: 'core' },
    formatter:    { icon: 'sparkle',  category: 'core' },
    external_api: { icon: 'globe',    category: 'integrations' },
    mcp:          { icon: 'mcp',      category: 'integrations' },
    datasource:   { icon: 'database', category: 'sources' },
    remote_flow:  { icon: 'cloud',    category: 'integrations' },
    channel:      { icon: 'send',     category: 'flow' },
    flow:         { icon: 'workflow', category: 'flow' },
    hitl_node:    { icon: 'users',    category: 'hitl' },
    reflection:   { icon: 'sparkle',  category: 'core' },
});

export const CATEGORY_TOKEN = Object.freeze({
    core: 'var(--accent)',
    code: 'var(--success)',
    integrations: 'var(--info)',
    sources: 'var(--info)',
    flow: 'var(--accent-secondary)',
    hitl: 'var(--warning)',
    triggers: 'var(--success)',
});

export const FALLBACK_NODE_META = Object.freeze({ icon: 'box', category: 'core' });

export const DATASOURCE_CONNECTOR_ICONS = Object.freeze({
    postgres: { icon: 'postgres' },
    mysql: { icon: 'mysql' },
    clickhouse: { icon: 'clickhouse' },
});

export function datasourceIconName(connectorId: any) {
    if (typeof connectorId !== 'string' || connectorId.length === 0) {
        throw new Error('datasourceIconName: connector_id required');
    }
    const meta = (DATASOURCE_CONNECTOR_ICONS as any)[connectorId];
    if (meta) {
        return meta.icon;
    }
    return 'database';
}

export function getNodeTypeMeta(type: string) {
    if (typeof type !== 'string' || type.length === 0) return FALLBACK_NODE_META;
    const meta = (NODE_TYPE_META as any)[type];
    return meta ? meta : FALLBACK_NODE_META;
}

export function getCategoryToken(category: string) {
    if (typeof category !== 'string' || category.length === 0) return CATEGORY_TOKEN.core;
    const token = (CATEGORY_TOKEN as any)[category];
    return typeof token === 'string' && token.length > 0 ? token : CATEGORY_TOKEN.core;
}
