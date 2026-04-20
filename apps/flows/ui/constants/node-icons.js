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
    code:         { icon: 'code',     category: 'core' },
    formatter:    { icon: 'sparkle',  category: 'core' },
    external_api: { icon: 'globe',    category: 'integrations' },
    mcp:          { icon: 'mcp',      category: 'integrations' },
    remote_flow:  { icon: 'cloud',    category: 'integrations' },
    channel:      { icon: 'send',     category: 'flow' },
    flow:         { icon: 'workflow', category: 'flow' },
    hitl_node:    { icon: 'users',    category: 'hitl' },
});

export const CATEGORY_TOKEN = Object.freeze({
    core: 'var(--accent)',
    integrations: 'var(--info)',
    flow: 'var(--accent-secondary)',
    hitl: 'var(--warning)',
    triggers: 'var(--success)',
});

export const FALLBACK_NODE_META = Object.freeze({ icon: 'box', category: 'core' });

export function getNodeTypeMeta(type) {
    if (typeof type !== 'string' || type.length === 0) return FALLBACK_NODE_META;
    const meta = NODE_TYPE_META[type];
    return meta ? meta : FALLBACK_NODE_META;
}

export function getCategoryToken(category) {
    if (typeof category !== 'string' || category.length === 0) return CATEGORY_TOKEN.core;
    const token = CATEGORY_TOKEN[category];
    return typeof token === 'string' && token.length > 0 ? token : CATEGORY_TOKEN.core;
}
