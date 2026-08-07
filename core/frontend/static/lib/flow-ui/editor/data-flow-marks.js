/**
 * Pure helpers for Flow UI data-flow marks (no DOM / Lit).
 * Used by the editor overlay and unit tests.
 */

/** JSON Pointer scope → overlay scope. */
export function flowUIBindingScope(pointer) {
    if (typeof pointer !== 'string') return null;
    if (pointer === '/values' || pointer.startsWith('/values/')) return 'input';
    if (pointer === '/content' || pointer.startsWith('/content/')) return 'content';
    if (pointer === '/system' || pointer.startsWith('/system/')) return 'system';
    return null;
}

function fieldTag(component, pointer) {
    const override = component?.properties?.fieldName;
    if (typeof override === 'string' && override.trim() !== '') {
        return `@state:ui_values.${override.trim()}`;
    }
    if (pointer === '/values') return '@state:ui_values';
    const segment = pointer.slice('/values/'.length).replace(/\//g, '_');
    return segment ? `@state:ui_values.${segment}` : '@state:ui_values';
}

/**
 * Build overlay marks from a surface and measured component rects.
 * One mark per data-bearing binding; submit controls get a dedicated mark.
 *
 * @param {object|null|undefined} surface
 * @param {readonly {componentId: string, rect: {x:number,y:number,width:number,height:number}}[]} inspectedComponents
 * @returns {readonly {componentId: string, scope: string, tag: string, rect: object, pointer?: string}[]}
 */
export function buildFlowUIDataFlowMarks(surface, inspectedComponents) {
    if (!surface || typeof surface !== 'object') return Object.freeze([]);
    if (!Array.isArray(inspectedComponents)) return Object.freeze([]);

    const rectById = new Map();
    for (const item of inspectedComponents) {
        if (!item || typeof item.componentId !== 'string' || !item.rect) continue;
        rectById.set(item.componentId, item.rect);
    }

    const marks = [];
    const components = surface.components;
    if (!components || typeof components !== 'object') return Object.freeze([]);

    for (const [componentId, component] of Object.entries(components)) {
        const rect = rectById.get(componentId);
        if (!rect) continue;

        const press = component.actions?.press;
        if (
            press
            && typeof press === 'object'
            && press.kind === 'event'
            && press.name === 'platform.ui.submit'
        ) {
            marks.push(Object.freeze({
                componentId,
                scope: 'submit',
                tag: 'submit → flow',
                rect: Object.freeze({ ...rect }),
            }));
        }

        const bindings = component.bindings;
        if (!bindings || typeof bindings !== 'object') continue;
        for (const pointer of Object.values(bindings)) {
            const scope = flowUIBindingScope(pointer);
            if (scope === null) continue;
            const tag = scope === 'input'
                ? fieldTag(component, pointer)
                : String(pointer);
            marks.push(Object.freeze({
                componentId,
                scope,
                tag,
                pointer: String(pointer),
                rect: Object.freeze({ ...rect }),
            }));
        }
    }

    return Object.freeze(marks);
}
