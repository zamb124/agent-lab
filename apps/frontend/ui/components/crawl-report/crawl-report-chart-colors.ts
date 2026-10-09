export const URL_STATUS_CHART_COLORS = Object.freeze({
    indexed: 'var(--success)',
    pending: 'var(--warning)',
    fetching: 'color-mix(in srgb, var(--accent) 65%, var(--warning))',
    failed: 'var(--error)',
    skipped: 'var(--text-tertiary)',
});

export const DOMAIN_STATUS_CHART_COLORS = Object.freeze({
    active: 'var(--success)',
    paused: 'var(--text-tertiary)',
    blocked: 'var(--error)',
    error: 'color-mix(in srgb, var(--error) 75%, var(--warning))',
});

export const CATEGORY_CHART_COLORS = Object.freeze([
    'var(--accent)',
    'var(--info)',
    'var(--success)',
    'var(--warning)',
    'color-mix(in srgb, var(--accent) 55%, var(--info))',
    'color-mix(in srgb, var(--success) 55%, var(--accent))',
    'color-mix(in srgb, var(--warning) 55%, var(--error))',
    'var(--text-tertiary)',
]);
