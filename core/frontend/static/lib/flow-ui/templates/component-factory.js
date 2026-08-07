/**
 * Shared immutable builders for Flow UI document templates.
 * Every template (chat, page starters) uses these — component/layout shapes
 * are declared exactly once.
 */

/** `row_start: 'auto'` asks the template normalize for the next free row. */
export function defaultPlacement() {
    return Object.freeze({
        base: Object.freeze({
            column_start: 1,
            column_span: 'full',
            row_start: 'auto',
            row_span: 1,
            order: 0,
            align_self: 'auto',
            justify_self: 'auto',
        }),
        overrides: Object.freeze({}),
    });
}

export function placement(base) {
    return Object.freeze({
        base: Object.freeze({ ...defaultPlacement().base, ...base }),
        overrides: Object.freeze({}),
    });
}

/** Narrow bands where a wide-band span may not fit. */
const NARROW_BAND_COLUMNS = Object.freeze({ medium: 8, compact: 4 });

/**
 * An explicit cell in the wide 12-column band, stacked full width wherever the
 * span would not fit. Templates declare real cells because the author sees and
 * edits those very cells — nothing is left to CSS auto-placement.
 *
 * `narrowRow` is the row the item takes once it stacks, so a two-up pair does not
 * land on the same narrow row.
 *
 * @param {{
 *   column?: number,
 *   span?: number | 'full',
 *   row?: number,
 *   rowSpan?: number,
 *   narrowRow?: number,
 * }} cell
 */
export function gridCell({
    column = 1,
    span = 'full',
    row = 1,
    rowSpan = 1,
    narrowRow = null,
} = {}) {
    const overrides = {};
    for (const [band, columns] of Object.entries(NARROW_BAND_COLUMNS)) {
        if (span === 'full' || column + span - 1 <= columns) continue;
        overrides[band] = Object.freeze({
            column_start: 1,
            column_span: 'full',
            row_start: narrowRow === null ? row : narrowRow,
        });
    }
    return Object.freeze({
        base: Object.freeze({
            ...defaultPlacement().base,
            column_start: column,
            column_span: span,
            row_start: row,
            row_span: rowSpan,
        }),
        overrides: Object.freeze(overrides),
    });
}

export function stackLayout(gap = 'space.4', direction = 'vertical') {
    return Object.freeze({
        mode: 'stack',
        grid: null,
        stack: Object.freeze({ direction, gap_token: gap, align: 'stretch' }),
        flex: null,
    });
}

export function flexLayout({ direction = 'row', gap = 'space.4', justify = 'start' } = {}) {
    return Object.freeze({
        mode: 'flex',
        grid: null,
        stack: null,
        flex: Object.freeze({
            direction,
            wrap: true,
            gap_token: gap,
            align_items: 'stretch',
            justify_content: justify,
        }),
    });
}

export function gridLayout({ compact = 4, medium = 8, wide = 12, gap = 'space.4' } = {}) {
    return Object.freeze({
        mode: 'grid',
        grid: Object.freeze({
            columns_by_band: Object.freeze({ compact, medium, wide }),
            column_gap_token: gap,
            row_gap_token: gap,
            outer_padding_inline_token: 'space.4',
            outer_padding_block_token: 'space.4',
            max_content_width_token: null,
            auto_rows: 'content',
            auto_flow: 'row',
            align_items: 'stretch',
            justify_items: 'stretch',
            baseline_step_token: 'space.1',
        }),
        stack: null,
        flex: null,
    });
}

export function flowUIComponent(spec) {
    return Object.freeze({
        component_id: spec.component_id,
        type: spec.type,
        kind: spec.kind || 'leaf',
        children: Object.freeze([...(spec.children || [])]),
        bindings: Object.freeze({ ...(spec.bindings || {}) }),
        properties: Object.freeze({ ...(spec.properties || {}) }),
        actions: Object.freeze({ ...(spec.actions || {}) }),
        container_layout: spec.container_layout || null,
        placement: spec.placement || defaultPlacement(),
        visibility: null,
        checks: Object.freeze([...(spec.checks || [])]),
        provenance: null,
    });
}

export function submitAction(formId) {
    return Object.freeze({
        press: Object.freeze({
            kind: 'event',
            name: 'platform.ui.submit',
            context: Object.freeze(formId ? { formId } : {}),
        }),
    });
}
