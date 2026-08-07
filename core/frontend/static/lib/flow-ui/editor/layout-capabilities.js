/**
 * What the author may do with a component inside its parent.
 *
 * Authoring is grid-only: every authorable container is a grid (guaranteed by
 * the on-load normalize), so a parent is either a grid with free 2D placement or
 * not authorable at all. Runtime may still render `flex`/`stack` (conversation
 * shell, composer) — that is a rendering decision, not an authoring mode.
 */
import {
    FLOW_UI_CATALOG_MANIFEST,
    LAYOUT_NONE,
    layoutCapabilitiesForType,
} from '../catalog/manifest.js';
import { FLOW_UI_DEFAULT_COLUMNS } from '../layout/grid-contract.js';

/**
 * @param {object} surface
 * @param {string} componentId
 * @returns {object | null}
 */
export function findParentComponent(surface, componentId) {
    if (!surface || typeof surface !== 'object') {
        throw new Error('flow-ui layout-capabilities: surface required');
    }
    if (typeof componentId !== 'string' || componentId.length === 0) {
        throw new Error('flow-ui layout-capabilities: componentId required');
    }
    for (const component of Object.values(surface.components || {})) {
        if (!component || typeof component !== 'object') continue;
        if ((component.children || []).includes(componentId)) {
            return component;
        }
    }
    return null;
}

/**
 * True when the parent is a conversation PageShell (explicit or structural).
 *
 * @param {object} parent
 * @param {Record<string, object> | null} components
 * @returns {boolean}
 */
function isConversationShellParent(parent, components) {
    if (parent.properties?.presentation === 'conversation') return true;
    if (parent.type !== 'PageShell' || !components || typeof components !== 'object') {
        return false;
    }
    for (const childId of parent.children || []) {
        const child = components[childId];
        if (!child || typeof child !== 'object') continue;
        if (child.type === 'ConversationFeed') return true;
        if (child.type === 'ArtifactFeed'
            && child.properties?.presentation === 'conversation') {
            return true;
        }
    }
    return false;
}

/**
 * Authoring mode of a parent container: `grid` when its children carry real
 * placement, `none` when the runtime owns their geometry.
 *
 * @param {object | null} parent
 * @param {Record<string, object> | null} [components]
 * @returns {'grid' | 'none'}
 */
export function effectiveParentMode(parent, components = null) {
    if (!parent || typeof parent !== 'object') return 'none';
    // Composer / conversation shells own child geometry; placement is ignored.
    if (parent.properties?.presentation === 'composer') return 'none';
    if (isConversationShellParent(parent, components)) return 'none';
    return parent.container_layout?.mode === 'grid' ? 'grid' : 'none';
}

/**
 * @param {object} parent
 * @param {string} band
 * @returns {number}
 */
export function parentGridColumns(parent, band = 'wide') {
    const columns = parent?.container_layout?.grid?.columns_by_band || FLOW_UI_DEFAULT_COLUMNS;
    const value = columns[band];
    if (!Number.isInteger(value) || value < 1) {
        throw new Error(`flow-ui layout-capabilities: invalid columns for band ${band}`);
    }
    return value;
}

/**
 * Resolved interaction policy for the selected component in its parent.
 *
 * @param {{
 *   component: object,
 *   parent: object | null,
 *   rootComponentId?: string,
 *   components?: Record<string, object> | null,
 * }} args
 */
export function resolveInteractionPolicy({
    component,
    parent,
    rootComponentId = 'root',
    components = null,
}) {
    if (!component || typeof component !== 'object') {
        throw new Error('flow-ui layout-capabilities: component required');
    }
    const type = component.type;
    if (typeof type !== 'string' || type.length === 0) {
        throw new Error('flow-ui layout-capabilities: component.type required');
    }
    const typeLayout = layoutCapabilitiesForType(type);
    const isRoot = component.component_id === rootComponentId || parent == null;
    const parentMode = isRoot ? 'none' : effectiveParentMode(parent, components);

    if (isRoot || parentMode !== 'grid') {
        return Object.freeze({
            ...LAYOUT_NONE,
            parentMode,
            canMove: false,
            canResizeInline: false,
            canResizeBlock: false,
            handles: Object.freeze([]),
        });
    }

    const move = typeLayout.move;
    const resizeInline = typeLayout.resizeInline;
    const resizeBlock = typeLayout.resizeBlock;

    const handles = [];
    if (move !== 'none') handles.push('move');
    if (resizeInline === 'span') handles.push('e', 'w');
    if (resizeBlock === 'row_span') handles.push('n', 's');
    if (resizeInline === 'span' && resizeBlock === 'row_span') {
        handles.push('ne', 'nw', 'se', 'sw');
    }

    return Object.freeze({
        move,
        resizeInline,
        resizeBlock,
        minColumnSpan: typeLayout.minColumnSpan,
        maxColumnSpan: typeLayout.maxColumnSpan,
        minRowSpan: typeLayout.minRowSpan,
        maxRowSpan: typeLayout.maxRowSpan,
        lockAspect: typeLayout.lockAspect,
        parentMode,
        canMove: move !== 'none',
        canResizeInline: resizeInline !== 'none',
        canResizeBlock: resizeBlock !== 'none',
        handles: Object.freeze(handles),
    });
}

/**
 * Containers the author may drop into. Runtime-owned feeds fill themselves from
 * the A2A stream, so they never receive authored children.
 *
 * @param {object | null} container
 * @param {Record<string, object> | null} [components]
 * @returns {boolean}
 */
export function isAuthorableDropTarget(container, components = null) {
    if (!container || typeof container !== 'object') return false;
    if (container.kind !== 'container') return false;
    if (container.type === 'ArtifactFeed' || container.type === 'ConversationFeed') return false;
    return effectiveParentMode(container, components) === 'grid';
}

/**
 * @param {string} type
 */
export function catalogEntry(type) {
    const entry = FLOW_UI_CATALOG_MANIFEST.components[type];
    if (!entry) {
        throw new Error(`flow-ui layout-capabilities: unknown catalog type ${type}`);
    }
    return entry;
}
