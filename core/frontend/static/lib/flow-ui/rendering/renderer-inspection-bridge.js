/**
 * Read-only inspection of a mounted production surface.
 *
 * Single projection shared by the parent-side bridge and the production iframe
 * boot script — the editor's grid geometry depends on `contentRect`/gaps being
 * identical on both paths, so there is exactly one place that builds them.
 */

function paddingBoxRect(element, style) {
    const rect = element.getBoundingClientRect();
    const left = Number.parseFloat(style.paddingLeft) || 0;
    const right = Number.parseFloat(style.paddingRight) || 0;
    const top = Number.parseFloat(style.paddingTop) || 0;
    const bottom = Number.parseFloat(style.paddingBottom) || 0;
    const borderLeft = Number.parseFloat(style.borderLeftWidth) || 0;
    const borderRight = Number.parseFloat(style.borderRightWidth) || 0;
    const borderTop = Number.parseFloat(style.borderTopWidth) || 0;
    const borderBottom = Number.parseFloat(style.borderBottomWidth) || 0;
    return {
        x: rect.x + borderLeft + left,
        y: rect.y + borderTop + top,
        width: Math.max(0, rect.width - borderLeft - borderRight - left - right),
        height: Math.max(0, rect.height - borderTop - borderBottom - top - bottom),
    };
}

/** Computed `grid-template-rows` resolves to used pixel sizes for a laid out grid. */
function usedTrackSizes(value) {
    if (typeof value !== 'string' || value === '' || value === 'none') return [];
    const sizes = [];
    for (const token of value.split(' ')) {
        const size = Number.parseFloat(token);
        if (Number.isFinite(size) && size > 0) sizes.push(size);
    }
    return sizes;
}

/**
 * @param {ShadowRoot | Element} componentRoot root that contains `[data-flow-ui-component]`
 * @returns {Array<object>}
 */
export function collectFlowUIInspection(componentRoot) {
    if (!componentRoot || typeof componentRoot.querySelectorAll !== 'function') {
        throw new Error('flow-ui inspection: component root required');
    }
    const components = [];
    for (const element of componentRoot.querySelectorAll('[data-flow-ui-component]')) {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        // A container with a visual surface (card, section, field group) puts the grid
        // on that surface, so cell geometry must be read there and not on the node.
        const gridHost = element.classList.contains('flow-grid')
            ? element
            : (element.querySelector(':scope > .flow-grid') || element);
        const gridStyle = gridHost === element ? style : getComputedStyle(gridHost);
        components.push({
            componentId: element.dataset.flowUiComponent,
            rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
            // Grid tracks live inside the padding box; the editor maps cells against it.
            contentRect: paddingBoxRect(gridHost, gridStyle),
            scroll: { width: element.scrollWidth, height: element.scrollHeight },
            columnGap: Number.parseFloat(gridStyle.columnGap) || 0,
            rowGap: Number.parseFloat(gridStyle.rowGap) || 0,
            // Rows grow with their content, so the editor needs the used track sizes
            // rather than assuming a uniform baseline step.
            rowTracks: usedTrackSizes(gridStyle.gridTemplateRows),
            overflow: element.scrollWidth > element.clientWidth
                || element.scrollHeight > element.clientHeight,
        });
    }
    return components;
}

export function inspectFlowUIRenderer(renderer) {
    if (!renderer?.shadowRoot) throw new Error('flow-ui inspection requires a mounted renderer');
    const surface = renderer.shadowRoot.querySelector('flow-ui-surface');
    if (!surface) throw new Error('flow-ui inspection: flow-ui-surface missing');
    const root = surface.shadowRoot;
    if (!root) throw new Error('flow-ui inspection: surface shadow missing');
    const document = renderer.controller?.document;
    if (!document || typeof document.revision !== 'number') {
        throw new Error('flow-ui inspection: hydrated document revision required');
    }
    const components = collectFlowUIInspection(root).map((entry) => Object.freeze({
        ...entry,
        rect: Object.freeze(entry.rect),
        contentRect: Object.freeze(entry.contentRect),
        scroll: Object.freeze(entry.scroll),
        rowTracks: Object.freeze(entry.rowTracks),
    }));
    return Object.freeze({ revision: document.revision, components: Object.freeze(components) });
}
