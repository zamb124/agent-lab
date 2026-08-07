/**
 * Interface editor domain: manifest-driven component factory, subtree/clipboard
 * operations and the publish validator. Pure functions over FlowUIDocument —
 * no DOM, no bus. The catalog manifest is the single source for component
 * kind/defaults/schema (Zero duplication with palette/inspector).
 */
import {
    FLOW_UI_CATALOG_MANIFEST,
    layoutCapabilitiesForType,
} from '@platform/lib/flow-ui/catalog/manifest.js';
import { firstFreeRow, placementCells } from '@platform/lib/flow-ui/layout/grid-occupancy.js';
import { assignExplicitGridRows } from '@platform/lib/flow-ui/layout/grid-normalize.js';

export const FLOW_UI_CLIPBOARD_VERSION = 'flow-ui-clipboard@1';

export function clone(value) { return structuredClone(value); }

export function activeSurface(document, pageId = null) {
    const page = document.pages[pageId || document.active_page_id];
    return page ? document.surfaces[page.root_surface_id] : null;
}

export function manifestEntry(type) {
    return FLOW_UI_CATALOG_MANIFEST.components[type] || null;
}

export function uniqueComponentId(surface, type) {
    const root = String(type || 'component').replace(/([a-z])([A-Z])/g, '$1-$2').toLowerCase();
    let index = 1;
    let id = root;
    while (surface.components[id]) { index += 1; id = `${root}-${index}`; }
    return id;
}

const GRID_LAYOUT_PRESET = Object.freeze({
    mode: 'grid',
    grid: {
        columns_by_band: { compact: 4, medium: 8, wide: 12 },
        column_gap_token: 'space.4',
        row_gap_token: 'space.4',
        outer_padding_inline_token: 'space.4',
        outer_padding_block_token: 'space.4',
        max_content_width_token: null,
        auto_rows: 'content',
        auto_flow: 'row',
        align_items: 'stretch',
        justify_items: 'stretch',
        baseline_step_token: 'space.1',
    },
    stack: null,
    flex: null,
});

const STACK_LAYOUT_PRESET = Object.freeze({
    mode: 'stack',
    grid: null,
    stack: { direction: 'vertical', gap_token: 'space.4', align: 'stretch' },
    flex: null,
});

export const FLEX_LAYOUT_PRESET = Object.freeze({
    mode: 'flex',
    grid: null,
    stack: null,
    flex: {
        direction: 'row',
        wrap: true,
        gap_token: 'space.4',
        align_items: 'stretch',
        justify_content: 'start',
    },
});

export function containerLayoutPreset(mode) {
    if (mode === 'grid') return clone(GRID_LAYOUT_PRESET);
    if (mode === 'flex') return clone(FLEX_LAYOUT_PRESET);
    return clone(STACK_LAYOUT_PRESET);
}

function localizedDefault(value, locale) {
    if (value && typeof value === 'object' && !Array.isArray(value)
        && (typeof value.ru === 'string' || typeof value.en === 'string')) {
        return locale === 'ru' ? value.ru : value.en;
    }
    return value;
}

/** Compact controls default to a short column span instead of a full-width row. */
const COMPACT_DEFAULT_SPAN = Object.freeze({
    Button: 3,
    Badge: 2,
    Icon: 1,
    Avatar: 2,
    Switch: 2,
    CheckBox: 2,
    PageLink: 3,
});

const SPAN_BY_LOWER_TYPE = Object.freeze(Object.fromEntries(
    Object.entries(COMPACT_DEFAULT_SPAN).map(([type, span]) => [type.toLowerCase(), span]),
));

/**
 * Column span a newly inserted component of `type` occupies. Shared by the
 * component factory and the canvas drop preview, so the highlighted cell is the
 * cell the component lands in. Accepts the lowercase form because drag MIME
 * types are lowercased by the browser.
 *
 * @param {string} type
 * @returns {number | 'full'}
 */
export function defaultColumnSpan(type) {
    if (typeof type !== 'string' || type.length === 0) {
        throw new Error('interface-editor: type required for default column span');
    }
    const span = SPAN_BY_LOWER_TYPE[type.toLowerCase()];
    return span === undefined ? 'full' : span;
}

/**
 * Manifest-driven default component for insert.
 * `Submit` — Button pre-wired to platform.ui.submit.
 * Grid-first: every container gets `container_layout.mode = grid`.
 */
export function defaultComponent(type, id, locale = 'en') {
    if (type === 'Submit') {
        const submit = defaultComponent('Button', id, locale);
        submit.properties = {
            label: locale === 'ru' ? 'Отправить' : 'Submit',
            variant: 'primary',
        };
        submit.actions = { press: { kind: 'event', name: 'platform.ui.submit', context: {} } };
        return submit;
    }
    const entry = manifestEntry(type);
    if (!entry) {
        throw new Error(`interface-editor: unknown catalog type ${type}`);
    }
    const columnSpan = defaultColumnSpan(type);
    const component = {
        component_id: id,
        type,
        kind: entry.kind,
        properties: {},
        children: [],
        container_layout: null,
        placement: {
            base: {
                column_start: 1,
                column_span: columnSpan,
                row_start: 1,
                row_span: 1,
                order: 0,
                align_self: 'auto',
                justify_self: 'auto',
            },
            overrides: {},
        },
        bindings: {},
        actions: {},
        visibility: null,
        checks: [],
        provenance: null,
    };
    if (entry.kind === 'container') {
        // Grid-first authoring: all insertable containers are grids.
        component.container_layout = containerLayoutPreset('grid');
    }
    const defaults = entry.editor?.defaults || {};
    if (defaults.properties) {
        component.properties = Object.fromEntries(
            Object.entries(defaults.properties)
                .map(([name, value]) => [name, localizedDefault(clone(value), locale)]),
        );
    }
    if (defaults.bindings) {
        component.bindings = Object.fromEntries(
            Object.entries(defaults.bindings)
                .map(([name, path]) => [name, String(path).replace('{id}', id)]),
        );
    }
    if (defaults.actions) {
        component.actions = clone(defaults.actions);
    }
    return component;
}

/**
 * Columns(N) palette preset: one Row(grid) + N equal Column slots (span 12/N).
 * @returns {{ rootId: string, components: Record<string, object> }}
 */
export function createColumnsPreset(columnCount, surface, locale = 'en') {
    if (![2, 3, 4].includes(columnCount)) {
        throw new Error(`interface-editor: Columns preset supports 2|3|4, got ${columnCount}`);
    }
    const rootId = uniqueComponentId(surface, 'Row');
    const row = defaultComponent('Row', rootId, locale);
    const components = { [rootId]: row };
    const span = Math.floor(12 / columnCount);
    const children = [];
    const staging = { components: { ...surface.components, [rootId]: row } };
    for (let index = 0; index < columnCount; index += 1) {
        const colId = uniqueComponentId(staging, 'Column');
        staging.components[colId] = true;
        const column = defaultComponent('Column', colId, locale);
        column.placement.base.column_span = span;
        column.placement.base.column_start = index * span + 1;
        components[colId] = column;
        children.push(colId);
    }
    row.children = children;
    return { rootId, components };
}

/**
 * Idempotent authoring migrate: every container with mode≠grid becomes grid.
 * Grid children with row_start auto get explicit cumulative row_start (baseline).
 * Runtime conversation flex is applied later by renderPageShell, not here.
 * @returns {boolean} true if any container/placement changed
 */
export function normalizeAuthorContainersToGrid(document) {
    if (!document || typeof document !== 'object') {
        throw new Error('interface-editor: document required for grid normalize');
    }
    let changed = false;
    for (const surface of Object.values(document.surfaces || {})) {
        if (!surface?.components || typeof surface.components !== 'object') continue;
        for (const component of Object.values(surface.components)) {
            if (!component || typeof component !== 'object') continue;
            if (collapseStretchedRowSpan(component)) {
                changed = true;
            }
            if (component.kind !== 'container') continue;
            if (!component.container_layout || typeof component.container_layout !== 'object') {
                component.container_layout = containerLayoutPreset('grid');
                changed = true;
                continue;
            }
            if (component.container_layout.mode === 'grid') continue;
            component.container_layout = containerLayoutPreset('grid');
            changed = true;
        }
        if (normalizeExplicitGridRows(surface)) {
            changed = true;
        }
    }
    return changed;
}

/**
 * Drop machine-inflated row spans.
 *
 * Rows grow with their content, so a content element needs exactly one row: a
 * multi-row span only reserves empty space below it. Spans written from stretched
 * measurements (`block_clamp`) are removed together with the dead flag; surfaces the
 * runtime fills itself (feeds, chrome) keep the size the author gave them.
 *
 * @returns {boolean} true when the placement changed
 */
function collapseStretchedRowSpan(component) {
    const base = component.placement?.base;
    if (!base || typeof base !== 'object') return false;
    if (base.block_clamp !== true) return false;
    if (manifestEntry(component.type)?.editor?.maturity === 'runtime_owned') {
        delete base.block_clamp;
        return true;
    }
    delete base.block_clamp;
    if (Number.isInteger(base.row_span) && base.row_span > 1) {
        base.row_span = 1;
    }
    return true;
}

/**
 * Give every grid child an explicit cell (core normalize, one implementation).
 * @returns {boolean}
 */
export function normalizeExplicitGridRows(surface) {
    return assignExplicitGridRows(surface);
}

/**
 * Make room for an inserted element: siblings take the rows the drag preview showed.
 *
 * @param {object} surface
 * @param {ReadonlyArray<{ componentId: string, rowStart: number }> | null} shifted
 */
export function applyRowShifts(surface, shifted) {
    if (shifted == null) return;
    if (!Array.isArray(shifted)) {
        throw new Error('interface-editor: row shifts must be an array');
    }
    for (const shift of shifted) {
        const component = surface.components[shift.componentId];
        if (!component) continue;
        if (!Number.isInteger(shift.rowStart) || shift.rowStart < 1) {
            throw new Error(`interface-editor: invalid shifted row ${JSON.stringify(shift)}`);
        }
        component.placement ||= { base: {}, overrides: {} };
        component.placement.base ||= {};
        component.placement.base.row_start = shift.rowStart;
    }
}

/**
 * Place a freshly created component inside its grid parent.
 *
 * With `area` (canvas drop) the component takes exactly those cells; otherwise it
 * appends to the first row where its own column range is free, so an insert never
 * lands on top of an existing component.
 *
 * @param {object} parent grid container receiving the child
 * @param {object} surface owning surface (for sibling placements)
 * @param {object} component newly created component (mutated)
 * @param {{ columnStart: number, columnSpan: number, rowStart: number, rowSpan: number } | null} area
 */
export function placeInGrid(parent, surface, component, area = null) {
    if (parent?.container_layout?.mode !== 'grid') return;
    const columns = parent.container_layout.grid?.columns_by_band?.wide ?? 12;
    const base = component.placement.base;
    if (area) {
        base.column_start = area.columnStart;
        base.column_span = area.columnSpan >= columns ? 'full' : area.columnSpan;
        base.row_start = area.rowStart;
        base.row_span = area.rowSpan;
        return;
    }
    const taken = (parent.children || [])
        .map((childId) => surface.components[childId])
        .filter((child) => child && typeof child === 'object')
        .map((child) => ({
            componentId: child.component_id,
            ...placementCells(child.placement, 'wide', columns),
        }));
    const cells = placementCells(component.placement, 'wide', columns);
    base.row_start = firstFreeRow({
        columnStart: cells.columnStart,
        columnSpan: cells.columnEnd - cells.columnStart + 1,
        rowStart: 1,
        rowSpan: cells.rowEnd - cells.rowStart + 1,
    }, taken, columns);
}

/** Palette pseudo-types Columns2|3|4 → column count, else null. */
export function columnsPresetCount(type) {
    if (type === 'Columns2') return 2;
    if (type === 'Columns3') return 3;
    if (type === 'Columns4') return 4;
    return null;
}

export function findParentId(surface, componentId) {
    for (const [id, component] of Object.entries(surface.components || {})) {
        if ((component.children || []).includes(componentId)) return id;
    }
    return null;
}

const COMPONENT_ID_RE = /^[a-z][a-z0-9_-]*$/;

/** Rename a component id in place: map key, component_id and all parent refs. */
export function renameComponent(surface, componentId, nextId) {
    if (!COMPONENT_ID_RE.test(nextId)) {
        throw new Error(`interface-editor: invalid component id "${nextId}" (lowercase, digits, - and _)`);
    }
    if (surface.components[nextId]) {
        throw new Error(`interface-editor: component id "${nextId}" already exists`);
    }
    const component = surface.components[componentId];
    if (!component) {
        throw new Error(`interface-editor: cannot rename missing component ${componentId}`);
    }
    if (componentId === (surface.root_component_id || 'root')) {
        throw new Error('interface-editor: root component cannot be renamed');
    }
    delete surface.components[componentId];
    component.component_id = nextId;
    surface.components[nextId] = component;
    for (const parent of Object.values(surface.components)) {
        parent.children = (parent.children || [])
            .map((childId) => (childId === componentId ? nextId : childId));
    }
    return component;
}

export function collectSubtreeIds(surface, componentId, out = []) {
    const component = surface.components?.[componentId];
    if (!component) return out;
    out.push(componentId);
    for (const childId of component.children || []) {
        collectSubtreeIds(surface, childId, out);
    }
    return out;
}

export function removeSubtree(surface, componentId) {
    const ids = new Set(collectSubtreeIds(surface, componentId));
    for (const id of ids) delete surface.components[id];
    for (const component of Object.values(surface.components)) {
        component.children = (component.children || []).filter((childId) => !ids.has(childId));
    }
}

/**
 * Deep copy a subtree with fresh component ids.
 * @returns {{ rootId: string, components: Record<string, object> }}
 */
export function cloneSubtree(surface, componentId, idFor = uniqueComponentId) {
    const source = surface.components?.[componentId];
    if (!source) {
        throw new Error(`interface-editor: cannot clone missing component ${componentId}`);
    }
    const staging = { components: { ...surface.components } };
    const idMap = new Map();
    const orderedIds = collectSubtreeIds(surface, componentId);
    for (const oldId of orderedIds) {
        const newId = idFor(staging, surface.components[oldId].type);
        staging.components[newId] = true;
        idMap.set(oldId, newId);
    }
    const components = {};
    for (const oldId of orderedIds) {
        const copy = clone(surface.components[oldId]);
        copy.component_id = idMap.get(oldId);
        copy.provenance = null;
        copy.children = (copy.children || []).map((childId) => {
            const mapped = idMap.get(childId);
            if (!mapped) {
                throw new Error('interface-editor: clone subtree child escaped the subtree');
            }
            return mapped;
        });
        components[copy.component_id] = copy;
    }
    return { rootId: idMap.get(componentId), components };
}

/** Versioned sanitized clipboard payload for copy/paste. */
export function serializeClipboard(surface, componentIds) {
    const roots = [];
    const components = {};
    for (const componentId of componentIds) {
        const ids = collectSubtreeIds(surface, componentId);
        if (!ids.length) continue;
        roots.push(componentId);
        for (const id of ids) {
            components[id] = clone(surface.components[id]);
        }
    }
    if (!roots.length) {
        throw new Error('interface-editor: clipboard requires at least one component');
    }
    return { version: FLOW_UI_CLIPBOARD_VERSION, roots, components };
}

/**
 * Validate + rebuild a clipboard payload against the catalog. Unknown types,
 * broken children and provenance are rejected/stripped fail-closed.
 */
export function sanitizeClipboard(payload) {
    if (!payload || typeof payload !== 'object' || payload.version !== FLOW_UI_CLIPBOARD_VERSION) {
        throw new Error('interface-editor: unsupported clipboard payload');
    }
    if (!Array.isArray(payload.roots) || !payload.roots.length) {
        throw new Error('interface-editor: clipboard has no roots');
    }
    const components = payload.components;
    if (!components || typeof components !== 'object') {
        throw new Error('interface-editor: clipboard has no components');
    }
    for (const [id, component] of Object.entries(components)) {
        if (!component || typeof component !== 'object') {
            throw new Error(`interface-editor: clipboard component ${id} invalid`);
        }
        if (!manifestEntry(component.type)) {
            throw new Error(`interface-editor: clipboard component type ${component.type} is not in the catalog`);
        }
        component.provenance = null;
        for (const childId of component.children || []) {
            if (!components[childId]) {
                throw new Error(`interface-editor: clipboard child ${childId} missing`);
            }
        }
    }
    return payload;
}

/**
 * Materialize a sanitized clipboard payload into a surface: every component
 * gets a fresh unique id; children references are remapped.
 * @returns {{ roots: string[], components: Record<string, object> }}
 */
export function materializeClipboard(surface, payload) {
    const sanitized = sanitizeClipboard(payload);
    const staging = { components: { ...surface.components } };
    const idMap = new Map();
    for (const [oldId, component] of Object.entries(sanitized.components)) {
        const newId = uniqueComponentId(staging, component.type);
        staging.components[newId] = true;
        idMap.set(oldId, newId);
    }
    const components = {};
    for (const [oldId, component] of Object.entries(sanitized.components)) {
        const copy = clone(component);
        copy.component_id = idMap.get(oldId);
        copy.children = (copy.children || []).map((childId) => {
            const mapped = idMap.get(childId);
            if (!mapped) {
                throw new Error('interface-editor: clipboard child escaped the payload');
            }
            return mapped;
        });
        components[copy.component_id] = copy;
        void oldId;
    }
    return { roots: sanitized.roots.map((id) => idMap.get(id)), components };
}

function walkReachable(surface, componentId, visited = new Set()) {
    if (!componentId || visited.has(componentId)) return visited;
    const component = surface.components?.[componentId];
    if (!component) return visited;
    visited.add(componentId);
    for (const childId of component.children || []) {
        walkReachable(surface, childId, visited);
    }
    return visited;
}

function isPermanentlyDisabled(component) {
    return component?.properties?.disabled === true
        && component?.bindings?.disabled == null;
}

const INTERACTIVE_INPUT_TYPES = Object.freeze([
    'TextField', 'TextArea', 'NumberField', 'Select', 'ChoicePicker', 'CheckBox',
    'Switch', 'FileUpload', 'DateTimeInput', 'DatePicker', 'Slider',
]);

function placementForBand(component, band) {
    return {
        ...(component.placement?.base || {}),
        ...(component.placement?.overrides?.[band] || {}),
    };
}

const BAND_COLUMNS = Object.freeze({ compact: 4, medium: 8, wide: 12 });

/**
 * Publish validator. Blocking errors cover: submit reachability, binding scope,
 * unique/known ids, catalog allowlist, navigation targets, per-band grid
 * placement validity and accessibility labels for interactive components.
 * @returns {{severity: string, code: string, message: string, componentId?: string, surfaceId?: string}[]}
 */
export function validateInterfaceDocument(document) {
    const problems = [];
    if (!document || typeof document !== 'object') {
        return [{ severity: 'error', code: 'document.missing', message: 'Interface document is required.' }];
    }
    if (!document.pages?.[document.active_page_id]) {
        problems.push({ severity: 'error', code: 'page.active_missing', message: 'Active page does not exist.' });
    }

    for (const [pageId, page] of Object.entries(document.pages || {})) {
        if (!document.surfaces?.[page.root_surface_id]) {
            problems.push({
                severity: 'error',
                code: 'page.surface_missing',
                message: `${pageId}: root surface ${page.root_surface_id} missing`,
            });
        }
    }

    const submitActions = [];

    for (const [surfaceId, surface] of Object.entries(document.surfaces || {})) {
        if (!surface?.components || typeof surface.components !== 'object') {
            problems.push({ severity: 'error', code: 'surface.components', message: `${surfaceId}: components map missing`, surfaceId });
            continue;
        }
        const rootId = surface.root_component_id || 'root';
        if (!surface.components[rootId]) {
            problems.push({ severity: 'error', code: 'surface.root', message: `${surfaceId}: root component missing`, surfaceId });
        }
        const reachable = walkReachable(surface, rootId);

        for (const [id, component] of Object.entries(surface.components)) {
            if (component.component_id !== id) {
                problems.push({
                    severity: 'error',
                    code: 'component.id_mismatch',
                    message: `${surfaceId}:${id}: component_id "${component.component_id}" does not match its key`,
                    surfaceId,
                    componentId: id,
                });
            }
            const entry = manifestEntry(component.type);
            if (!entry) {
                problems.push({
                    severity: 'error',
                    code: 'catalog.unknown_type',
                    message: `${surfaceId}:${id}: type ${component.type} is not in the trusted catalog`,
                    surfaceId,
                    componentId: id,
                });
            }
            for (const childId of component.children || []) {
                if (!surface.components[childId]) {
                    problems.push({
                        severity: 'error',
                        code: 'component.child_missing',
                        message: `${surfaceId}:${id}: child ${childId} does not exist`,
                        surfaceId,
                        componentId: id,
                    });
                }
            }
            if ((component.children || []).length > 0 && component.kind !== 'container') {
                problems.push({
                    severity: 'error',
                    code: 'component.leaf_children',
                    message: `${surfaceId}:${id}: leaf component cannot have children`,
                    surfaceId,
                    componentId: id,
                });
            }
            for (const [slot, action] of Object.entries(component.actions || {})) {
                if (action?.kind === 'event' && action.name === 'platform.ui.submit') {
                    submitActions.push({
                        surfaceId,
                        componentId: id,
                        slot,
                        formId: action.context?.formId || component.properties?.formId || null,
                        reachable: reachable.has(id),
                        type: component.type,
                        disabledForever: isPermanentlyDisabled(component),
                    });
                }
                if (action?.kind === 'local' && action.name === 'page.navigate') {
                    const target = action.context?.pageId;
                    if (typeof target !== 'string' || !document.pages?.[target]) {
                        problems.push({
                            severity: 'error',
                            code: 'navigation.target_missing',
                            message: `${surfaceId}:${id}: navigation target page ${String(target)} does not exist`,
                            surfaceId,
                            componentId: id,
                        });
                    }
                }
            }
            if (component.type === 'PageLink') {
                const target = component.properties?.pageId
                    ?? component.properties?.targetPageId
                    ?? component.properties?.page_id;
                if (typeof target !== 'string' || !document.pages?.[target]) {
                    problems.push({
                        severity: 'error',
                        code: 'navigation.target_missing',
                        message: `${surfaceId}:${id}: PageLink target page ${String(target)} does not exist`,
                        surfaceId,
                        componentId: id,
                    });
                }
            }
            for (const [bindingName, path] of Object.entries(component.bindings || {})) {
                if (typeof path !== 'string' || !path.startsWith('/')) {
                    problems.push({
                        severity: 'error',
                        code: 'binding.invalid',
                        message: `${id}.${bindingName}: binding must be an absolute JSON Pointer`,
                        surfaceId,
                        componentId: id,
                    });
                    continue;
                }
                if (path.startsWith('/system/secrets')) {
                    problems.push({
                        severity: 'error',
                        code: 'binding.secret',
                        message: `${id}.${bindingName}: secret binding forbidden`,
                        surfaceId,
                        componentId: id,
                    });
                }
                if (
                    component.actions
                    && Object.values(component.actions).some((action) => action?.kind === 'event')
                    && !path.startsWith('/values')
                    && !path.startsWith('/system/')
                    && !path.startsWith('/content/')
                ) {
                    problems.push({
                        severity: 'error',
                        code: 'binding.scope',
                        message: `${id}.${bindingName}: interactive binding must stay under /values`,
                        surfaceId,
                        componentId: id,
                    });
                }
            }
            // Grid placement must stay valid in every band.
            if (reachable.has(id)) {
                const parentId = findParentId(surface, id);
                const parent = parentId ? surface.components[parentId] : null;
                if (parent?.container_layout?.mode === 'grid') {
                    for (const [band, columns] of Object.entries(BAND_COLUMNS)) {
                        const bandColumns = Number(
                            parent.container_layout.grid?.columns_by_band?.[band] ?? columns,
                        );
                        const placement = placementForBand(component, band);
                        const start = placement.column_start;
                        const span = placement.column_span;
                        if (Number.isInteger(start) && Number.isInteger(span)
                            && start + span - 1 > bandColumns) {
                            problems.push({
                                severity: 'error',
                                code: 'layout.overflow',
                                message: `${surfaceId}:${id}: ${band} placement ${start}+${span} exceeds ${bandColumns} columns`,
                                surfaceId,
                                componentId: id,
                            });
                        }
                    }
                }
            }
            // Accessibility: interactive controls need an accessible label.
            if (reachable.has(id)
                && (component.type === 'Button' || INTERACTIVE_INPUT_TYPES.includes(component.type))) {
                const label = component.properties?.label
                    ?? component.properties?.text
                    ?? component.bindings?.label;
                const isComposerChild = component.properties?.presentation === 'composer';
                if (!isComposerChild && (label == null || String(label).trim() === '')) {
                    problems.push({
                        severity: 'warning',
                        code: 'a11y.label_missing',
                        message: `${surfaceId}:${id}: interactive ${component.type} has no accessible label`,
                        surfaceId,
                        componentId: id,
                    });
                }
            }
        }

        const interactiveInputs = Object.values(surface.components).filter((component) => (
            INTERACTIVE_INPUT_TYPES.includes(component.type)
            && reachable.has(component.component_id)
        ));
        if (interactiveInputs.length > 0) {
            const pageHasSubmit = submitActions.some((item) => item.surfaceId === surfaceId && item.reachable);
            if (!pageHasSubmit) {
                problems.push({
                    severity: 'error',
                    code: 'submit.form_unreachable',
                    message: `${surfaceId}: interactive form page has no reachable platform.ui.submit`,
                    surfaceId,
                });
            }
        }
    }

    if (!submitActions.length) {
        problems.push({
            severity: 'error',
            code: 'submit.missing',
            message: 'Add a reachable platform.ui.submit button before publishing.',
        });
    } else if (!submitActions.some((item) => item.reachable)) {
        problems.push({
            severity: 'error',
            code: 'submit.unreachable',
            message: 'platform.ui.submit exists only on unreachable components (for example a closed Modal).',
        });
    }

    for (const item of submitActions) {
        if (item.disabledForever) {
            problems.push({
                severity: 'error',
                code: 'submit.disabled_forever',
                message: `${item.surfaceId}:${item.componentId}: submit button is permanently disabled`,
                surfaceId: item.surfaceId,
                componentId: item.componentId,
            });
        }
    }

    const formScope = new Map();
    for (const item of submitActions) {
        const key = item.formId || '__default__';
        if (!formScope.has(key)) formScope.set(key, []);
        formScope.get(key).push(item);
    }
    for (const [formId, items] of formScope.entries()) {
        if (items.length > 1 && formId !== '__default__') {
            const surfaces = new Set(items.map((item) => item.surfaceId));
            if (surfaces.size > 1) {
                problems.push({
                    severity: 'error',
                    code: 'submit.form_conflict',
                    message: `Duplicate platform.ui.submit actions share formId ${formId} across surfaces`,
                });
            }
        }
    }

    return problems;
}

export function quickFixAddSubmit(document, surfaceId = null) {
    const surface = activeSurface(document, surfaceId ? document.pages[surfaceId]?.page_id : null)
        || Object.values(document.surfaces || {})[0];
    if (!surface) {
        throw new Error('quickFixAddSubmit: no surface available');
    }
    const id = uniqueComponentId(surface, 'submit');
    const button = defaultComponent('Submit', id);
    surface.components[id] = button;
    const root = surface.components[surface.root_component_id || 'root'];
    if (!root) {
        throw new Error('quickFixAddSubmit: root missing');
    }
    root.children = [...(root.children || []), id];
    return document;
}

export { layoutCapabilitiesForType };
