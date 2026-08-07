/**
 * Semantic layout commands — the only writers of `placement` and `children`.
 *
 * Fail-closed: root is locked, patches must stay inside the parent grid and the
 * resulting cells must be free. Because canvas gestures, keyboard steps and the
 * numeric layout inspector all funnel through `placement.set`, the free-cell
 * invariant holds for every authoring path without being restated anywhere.
 */
import { cloneSerializable } from '../utils/clone.js';
import { validateGridPlacement } from '../layout/grid-contract.js';
import {
    firstFreeRow,
    isAreaFree,
    occupiedAreas,
    placementCells,
} from '../layout/grid-occupancy.js';
import {
    effectiveParentMode,
    findParentComponent,
    parentGridColumns,
    resolveInteractionPolicy,
} from './layout-capabilities.js';

function clone(value) {
    return cloneSerializable(value);
}

function validatePlacementPatch(patch, columns, policy) {
    if (!patch || typeof patch !== 'object') {
        throw new Error('flow-ui editor: placement patch required');
    }
    const probe = {
        column_span: patch.column_span === undefined ? 1 : patch.column_span,
        column_start: patch.column_start === undefined ? 'auto' : patch.column_start,
    };
    const error = validateGridPlacement(probe, columns);
    if (error) {
        throw new Error(`flow-ui editor: ${error}`);
    }
    if (patch.column_span != null && patch.column_span !== 'full') {
        if (!Number.isInteger(patch.column_span)) {
            throw new Error('flow-ui editor: column_span must be integer or full');
        }
        if (patch.column_span < policy.minColumnSpan) {
            throw new Error(`flow-ui editor: column_span below min ${policy.minColumnSpan}`);
        }
        if (policy.maxColumnSpan !== 'full' && patch.column_span > policy.maxColumnSpan) {
            throw new Error(`flow-ui editor: column_span above max ${policy.maxColumnSpan}`);
        }
    }
    if (
        Number.isInteger(patch.column_start)
        && patch.column_span != null
        && patch.column_span !== 'full'
    ) {
        if (patch.column_start + patch.column_span - 1 > columns) {
            throw new Error('flow-ui editor: column_start + column_span exceeds grid');
        }
    }
    if (patch.row_span != null) {
        if (!Number.isInteger(patch.row_span) || patch.row_span < policy.minRowSpan) {
            throw new Error('flow-ui editor: invalid row_span');
        }
        if (policy.maxRowSpan != null && patch.row_span > policy.maxRowSpan) {
            throw new Error('flow-ui editor: row_span above max');
        }
    }
    if (patch.row_start != null) {
        if (!Number.isInteger(patch.row_start) || patch.row_start < 1) {
            throw new Error('flow-ui editor: row_start must be an integer >= 1');
        }
    }
}

function placementStorageBand(band) {
    if (band == null || band === 'base' || band === 'wide') {
        return 'base';
    }
    return band;
}

const NARROW_BAND_COLUMNS = Object.freeze({ medium: 8, compact: 4 });

function ensureNarrowBandPlacementFits(component) {
    const base = component.placement?.base;
    if (!base || typeof base !== 'object') return;
    component.placement.overrides ||= {};
    for (const [band, columns] of Object.entries(NARROW_BAND_COLUMNS)) {
        const resolved = {
            ...base,
            ...(component.placement.overrides[band] || {}),
        };
        const start = resolved.column_start;
        const span = resolved.column_span;
        if (!Number.isInteger(start) || !Number.isInteger(span)) continue;
        if (start + span - 1 <= columns) continue;
        component.placement.overrides[band] = {
            ...(component.placement.overrides[band] || {}),
            column_start: 1,
            column_span: 'full',
        };
    }
}

function applyPlacementPatchToComponent(component, band, patch) {
    component.placement ||= { base: {}, overrides: {} };
    const writeBand = placementStorageBand(band);
    // `block_clamp` belonged to the legacy max-height clamp; explicit rows are real
    // grid tracks now, so a row_span write no longer sets it.
    const nextPatch = { ...patch };
    if (writeBand === 'base') {
        component.placement.base = { ...component.placement.base, ...nextPatch };
        const wideOverride = component.placement.overrides?.wide;
        if (wideOverride != null && typeof wideOverride === 'object') {
            const cleared = { ...wideOverride };
            let changed = false;
            for (const key of Object.keys(nextPatch)) {
                if (Object.prototype.hasOwnProperty.call(cleared, key)) {
                    delete cleared[key];
                    changed = true;
                }
            }
            if (changed) {
                if (Object.keys(cleared).length === 0) {
                    delete component.placement.overrides.wide;
                } else {
                    component.placement.overrides.wide = cleared;
                }
            }
        }
        // Wide coords live in base; clamp narrower bands so start+span cannot overflow.
        ensureNarrowBandPlacementFits(component);
        return;
    }
    component.placement.overrides[writeBand] = {
        ...(component.placement.overrides[writeBand] || {}),
        ...nextPatch,
    };
}

/**
 * The free-cell invariant. A placement is accepted only when its cells are
 * inside the grid and touch no sibling — never by pushing siblings aside.
 */
function assertCellsFree({ surface, parent, component, band, columns, patch }) {
    const probe = clone(component);
    applyPlacementPatchToComponent(probe, band, patch);
    const cells = placementCells(probe.placement, band === 'base' ? 'wide' : band, columns);
    const area = {
        columnStart: cells.columnStart,
        columnSpan: cells.columnEnd - cells.columnStart + 1,
        rowStart: cells.rowStart,
        rowSpan: cells.rowEnd - cells.rowStart + 1,
    };
    const occupied = occupiedAreas({
        parent,
        components: surface.components,
        band: band === 'base' ? 'wide' : band,
        columns,
        excludeComponentId: component.component_id,
    });
    if (!isAreaFree(area, occupied, columns)) {
        const blocker = occupied.find((taken) => (
            !(area.columnStart + area.columnSpan - 1 < taken.columnStart
                || area.columnStart > taken.columnEnd
                || area.rowStart + area.rowSpan - 1 < taken.rowStart
                || area.rowStart > taken.rowEnd)
        ));
        throw new Error(
            `flow-ui editor: cells ${area.columnStart}/${area.rowStart} +${area.columnSpan}x${area.rowSpan}`
            + ` are taken by ${blocker ? blocker.componentId : 'the grid edge'}`,
        );
    }
}

function applyPlacementSet({ surface, component, command, rootId }) {
    if (command.componentId === rootId) {
        throw new Error('flow-ui editor: root placement cannot be changed by gesture');
    }
    const parent = findParentComponent(surface, command.componentId);
    if (effectiveParentMode(parent, surface.components) !== 'grid') {
        throw new Error(`flow-ui editor: ${component.type} parent is not an authorable grid`);
    }
    const policy = resolveInteractionPolicy({
        component,
        parent,
        rootComponentId: rootId,
        components: surface.components,
    });
    if (!policy.canMove && !policy.canResizeInline && !policy.canResizeBlock) {
        throw new Error(`flow-ui editor: ${component.type} rejects placement gestures`);
    }
    const band = command.band || 'wide';
    const columns = parentGridColumns(parent, band === 'base' ? 'wide' : band);
    const patch = command.patch || {};
    validatePlacementPatch(patch, columns, policy);
    assertCellsFree({ surface, parent, component, band, columns, patch });
    applyPlacementPatchToComponent(component, band, patch);
}

/**
 * Apply a semantic layout command. Fail-closed on illegal targets/patches.
 *
 * @param {object} document
 * @param {{
 *   kind: 'placement.set' | 'layout.set' | 'children.move',
 *   surfaceId: string,
 *   componentId: string,
 *   band?: string,
 *   patch?: object,
 *   layout?: object,
 *   targetParentId?: string,
 *   index?: number,
 * }} command
 */
export function applyLayoutCommand(document, command) {
    if (!document || typeof document !== 'object') {
        throw new Error('flow-ui editor: document required');
    }
    if (!command || typeof command !== 'object') {
        throw new Error('flow-ui editor: command required');
    }
    const next = clone(document);
    const surface = next.surfaces?.[command.surfaceId];
    if (!surface) {
        throw new Error(`flow-ui editor: surface ${command.surfaceId} not found`);
    }
    const rootId = surface.root_component_id || 'root';
    const component = surface.components?.[command.componentId];
    if (!component) {
        throw new Error('flow-ui editor: command target not found');
    }

    if (command.kind === 'placement.set') {
        applyPlacementSet({
            surface,
            component,
            command,
            rootId,
        });
    } else if (command.kind === 'layout.set') {
        component.container_layout = clone(command.layout);
    } else if (command.kind === 'children.move') {
        applyChildrenMove({ surface, command, rootId });
    } else {
        throw new Error(`flow-ui editor: unknown layout command ${command.kind}`);
    }

    next.revision = Number(next.revision || 0) + 1;
    return next;
}

/** Reparent: detach from the current parent, attach to targetParentId at index. */
function applyChildrenMove({ surface, command, rootId }) {
    if (command.componentId === rootId) {
        throw new Error('flow-ui editor: root cannot be reparented');
    }
    const targetParentId = command.targetParentId;
    if (typeof targetParentId !== 'string' || targetParentId.length === 0) {
        throw new Error('flow-ui editor: targetParentId required for children.move');
    }
    const targetParent = surface.components[targetParentId];
    if (!targetParent) {
        throw new Error('flow-ui editor: reparent target not found');
    }
    if (targetParent.kind !== 'container') {
        throw new Error(`flow-ui editor: ${targetParent.type} cannot receive children`);
    }
    // A component must never become its own descendant.
    let probeId = targetParentId;
    while (probeId) {
        if (probeId === command.componentId) {
            throw new Error('flow-ui editor: reparent would create a cycle');
        }
        const probeParent = findParentComponent(surface, probeId);
        probeId = probeParent ? probeParent.component_id : null;
    }
    const currentParent = findParentComponent(surface, command.componentId);
    if (!currentParent) {
        throw new Error('flow-ui editor: reparent source parent not found');
    }
    const index = command.index;
    if (!Number.isInteger(index) || index < 0) {
        throw new Error('flow-ui editor: children.move requires non-negative integer index');
    }
    currentParent.children = (currentParent.children || [])
        .filter((childId) => childId !== command.componentId);
    const nextChildren = [...(targetParent.children || [])]
        .filter((childId) => childId !== command.componentId);
    nextChildren.splice(Math.min(index, nextChildren.length), 0, command.componentId);
    targetParent.children = nextChildren;
    if (effectiveParentMode(targetParent, surface.components) !== 'grid') return;
    // The cell belongs to the new parent grid, so it is resolved after attach: an
    // explicit drop cell from the canvas, otherwise the first free row there.
    const component = surface.components[command.componentId];
    const patch = command.patch && typeof command.patch === 'object'
        && Object.keys(command.patch).length > 0
        ? command.patch
        : freeCellPatch({ surface, parent: targetParent, component, band: command.band || 'wide' });
    applyPlacementSet({
        surface,
        component,
        command: { ...command, kind: 'placement.set', patch },
        rootId,
    });
}

/** Cells for a component that just entered a grid: keep its columns, drop to a free row. */
function freeCellPatch({ surface, parent, component, band }) {
    const resolvedBand = band === 'base' ? 'wide' : band;
    const columns = parentGridColumns(parent, resolvedBand);
    const cells = placementCells(component.placement, resolvedBand, columns);
    const occupied = occupiedAreas({
        parent,
        components: surface.components,
        band: resolvedBand,
        columns,
        excludeComponentId: component.component_id,
    });
    const area = {
        columnStart: cells.columnStart,
        columnSpan: cells.columnEnd - cells.columnStart + 1,
        rowStart: 1,
        rowSpan: cells.rowEnd - cells.rowStart + 1,
    };
    return {
        column_start: area.columnStart,
        column_span: area.columnSpan >= columns ? 'full' : area.columnSpan,
        row_start: firstFreeRow(area, occupied, columns),
        row_span: area.rowSpan,
    };
}
