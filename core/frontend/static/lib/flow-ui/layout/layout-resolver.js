import { FLOW_UI_DEFAULT_COLUMNS, resolvedPlacement } from './grid-contract.js';
import { FLOW_UI_ROW_HEIGHT_PX } from './grid-geometry.js';

const TOKEN_VALUES = Object.freeze({
    'space.0': '0px', 'space.1': '4px', 'space.2': '8px', 'space.3': '12px',
    'space.4': '16px', 'space.5': '20px', 'space.6': '24px', 'space.8': '32px',
    'content.narrow': '720px', 'content.medium': '960px', 'content.wide': '1280px',
});

export function tokenValue(token, fallback = '0px') {
    return TOKEN_VALUES[token] || `var(--flow-ui-${String(token || '').replace(/\./g, '-')}, ${fallback})`;
}

/**
 * Rows a grid container needs for its children (wide band), at least one.
 * Emitted as explicit tracks so a row never clips its content and the editor can
 * read real track sizes back from computed style.
 *
 * @param {object} component grid container
 * @param {Record<string, object>} components surface components
 * @returns {number}
 */
export function gridRowCount(component, components) {
    if (component?.container_layout?.mode !== 'grid') return 1;
    if (!components || typeof components !== 'object') return 1;
    let rows = 1;
    for (const childId of component.children || []) {
        const child = components[childId];
        if (!child || typeof child !== 'object') continue;
        const value = resolvedPlacement(child.placement || { base: {}, overrides: {} }, 'wide');
        const start = Number.isInteger(value.row_start) && value.row_start >= 1 ? value.row_start : 1;
        const span = Number.isInteger(value.row_span) && value.row_span >= 1 ? value.row_span : 1;
        if (start + span - 1 > rows) rows = start + span - 1;
    }
    return rows;
}

export function containerLayoutStyle(layout, rowCount = 1) {
    if (!layout) return '';
    if (layout.mode === 'grid' && layout.grid) {
        const grid = layout.grid;
        const columns = grid.columns_by_band || FLOW_UI_DEFAULT_COLUMNS;
        const wideCols = columns.wide || 12;
        const rows = Number.isInteger(rowCount) && rowCount >= 1 ? rowCount : 1;
        return [
            'display:grid',
            'width:100%',
            'min-width:0',
            'box-sizing:border-box',
            // Baseline columns: @container rules on .flow-grid may not apply when
            // the grid element is itself the containment context.
            `grid-template-columns:repeat(${wideCols},minmax(0,1fr))`,
            // A row is one baseline tall and grows with its content, so a card or
            // section can never spill over the row below it.
            `grid-template-rows:repeat(${rows},minmax(${FLOW_UI_ROW_HEIGHT_PX}px,auto))`,
            `grid-auto-rows:minmax(${FLOW_UI_ROW_HEIGHT_PX}px,auto)`,
            'container-type:inline-size',
            `--flow-ui-cols-compact:${columns.compact || 4}`,
            `--flow-ui-cols-medium:${columns.medium || 8}`,
            `--flow-ui-cols-wide:${wideCols}`,
            `column-gap:${tokenValue(grid.column_gap_token, '16px')}`,
            `row-gap:${tokenValue(grid.row_gap_token, '16px')}`,
            `padding-inline:${tokenValue(grid.outer_padding_inline_token, '16px')}`,
            `padding-block:${tokenValue(grid.outer_padding_block_token, '16px')}`,
            grid.max_content_width_token ? `max-width:${tokenValue(grid.max_content_width_token, '1280px')}` : '',
            grid.max_content_width_token ? 'margin-inline:auto' : '',
            // Rows hug their content: a taller container (page shell, card) must not
            // distribute its free height into the tracks, or every element would look
            // stretched and could never be made smaller.
            'align-content:start',
            `align-items:${grid.align_items || 'stretch'}`,
            `justify-items:${grid.justify_items || 'stretch'}`,
        ].filter(Boolean).join(';');
    }
    if (layout.mode === 'flex' && layout.flex) {
        const flex = layout.flex;
        return [
            'display:flex',
            'width:100%',
            'min-width:0',
            'box-sizing:border-box',
            `flex-direction:${flex.direction || 'row'}`,
            `flex-wrap:${flex.wrap === false ? 'nowrap' : 'wrap'}`,
            `gap:${tokenValue(flex.gap_token, '16px')}`,
            `align-items:${flex.align_items || 'stretch'}`,
            `justify-content:${flex.justify_content || 'start'}`,
        ].join(';');
    }
    const stack = layout.stack || {};
    return [
        'display:flex',
        'width:100%',
        'min-width:0',
        'box-sizing:border-box',
        `flex-direction:${stack.direction === 'horizontal' ? 'row' : 'column'}`,
        `gap:${tokenValue(stack.gap_token, '16px')}`,
        `align-items:${stack.align || 'stretch'}`,
    ].join(';');
}

/**
 * Explicit row_start → real grid-row tracks.
 * Legacy auto row_start: row_span/block_clamp → max-height only (not grid-row span on auto tracks).
 */
function placementVariables(placement, band) {
    const value = resolvedPlacement(placement, band);
    const start = value.column_start === 'auto' || value.column_start == null ? 'auto' : String(value.column_start);
    const span = value.column_span === 'full' || value.column_span == null ? '1 / -1' : `span ${value.column_span}`;
    const column = span === '1 / -1'
        ? '1 / -1'
        : (start === 'auto' ? `auto / ${span}` : `${start} / ${span}`);
    const rowStart = value.row_start;
    const hasExplicitRow = rowStart != null && rowStart !== 'auto' && Number.isInteger(rowStart);
    let row = 'auto';
    if (hasExplicitRow) {
        const rowSpan = Number.isInteger(value.row_span) && value.row_span >= 1 ? value.row_span : 1;
        row = `${rowStart} / span ${rowSpan}`;
    }
    const override = placement.overrides?.[band];
    const explicitRowSpan = override != null && Number.isInteger(override.row_span)
        ? override.row_span
        : (value.block_clamp === true && Number.isInteger(value.row_span) ? value.row_span : null);
    const maxBlock = hasExplicitRow
        ? 'none'
        : (Number.isInteger(explicitRowSpan) && explicitRowSpan >= 1
            ? `${explicitRowSpan * FLOW_UI_ROW_HEIGHT_PX}px`
            : 'none');
    const blockOverflow = maxBlock === 'none' ? 'visible' : 'hidden';
    return {
        column,
        row,
        maxBlock,
        blockOverflow,
        order: value.order || 0,
        align: value.align_self || 'auto',
        justify: value.justify_self || 'auto',
    };
}

export function placementStyle(placement) {
    if (placement == null || typeof placement !== 'object') {
        throw new Error('flow-ui layout: placement is required for placementStyle');
    }
    const compact = placementVariables(placement, 'compact');
    const medium = placementVariables(placement, 'medium');
    const wide = placementVariables(placement, 'wide');
    return [
        `--flow-ui-column-compact:${compact.column}`, `--flow-ui-column-medium:${medium.column}`,
        `--flow-ui-column-wide:${wide.column}`, `--flow-ui-row-compact:${compact.row}`,
        `--flow-ui-row-medium:${medium.row}`, `--flow-ui-row-wide:${wide.row}`,
        `--flow-ui-max-block-compact:${compact.maxBlock}`, `--flow-ui-max-block-medium:${medium.maxBlock}`,
        `--flow-ui-max-block-wide:${wide.maxBlock}`,
        `--flow-ui-block-overflow-compact:${compact.blockOverflow}`,
        `--flow-ui-block-overflow-medium:${medium.blockOverflow}`,
        `--flow-ui-block-overflow-wide:${wide.blockOverflow}`,
        `--flow-ui-order-compact:${compact.order}`, `--flow-ui-order-medium:${medium.order}`,
        `--flow-ui-order-wide:${wide.order}`, `--flow-ui-align-wide:${wide.align}`,
        `--flow-ui-justify-wide:${wide.justify}`,
    ].join(';');
}
