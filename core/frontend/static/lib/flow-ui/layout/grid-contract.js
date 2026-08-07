export const FLOW_UI_GRID_BANDS = Object.freeze(['compact', 'medium', 'wide']);
export const FLOW_UI_DEFAULT_COLUMNS = Object.freeze({ compact: 4, medium: 8, wide: 12 });

export function resolvedPlacement(placement, band = 'wide') {
    if (placement == null || typeof placement !== 'object') {
        throw new Error('flow-ui layout: placement is required');
    }
    const base = placement.base != null && typeof placement.base === 'object'
        ? placement.base
        : {};
    const overridePatch = placement.overrides?.[band];
    const override = overridePatch != null && typeof overridePatch === 'object'
        ? overridePatch
        : {};
    return {
        ...base,
        ...Object.fromEntries(Object.entries(override).filter(([, value]) => value != null)),
    };
}

export function validateGridPlacement(placement, columns) {
    const span = placement.column_span;
    if (span !== 'full' && (!Number.isInteger(span) || span < 1 || span > columns)) {
        return `column span ${JSON.stringify(span)} exceeds ${columns} columns`;
    }
    const start = placement.column_start;
    if (start !== 'auto' && (!Number.isInteger(start) || start < 1 || start > columns)) {
        return `column start ${JSON.stringify(start)} is outside ${columns} columns`;
    }
    if (
        Number.isInteger(start)
        && Number.isInteger(span)
        && start + span - 1 > columns
    ) {
        return `column start+span ${start}+${span} exceeds ${columns} columns`;
    }
    return null;
}
