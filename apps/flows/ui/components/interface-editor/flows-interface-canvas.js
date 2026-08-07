/**
 * Editor artboard over the production iframe: semantic drag/resize, palette
 * drag-and-drop insert, reparent by drop into another container, multi-select,
 * context menu, inline text editing, rulers and fit zoom.
 * The production DOM is never mutated — all edits are semantic commands.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/flow-ui/rendering/production-render-frame.js';
import '@platform/lib/flow-ui/editor/layout-grid-overlay.js';
import '@platform/lib/flow-ui/editor/rulers-guides-overlay.js';
import '@platform/lib/flow-ui/editor/selection-overlay.js';
import {
    buildFlowUIDataFlowMarks,
} from '@platform/lib/flow-ui/editor/data-flow-marks.js';
import '@platform/lib/flow-ui/editor/data-flow-overlay.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import { FLOW_UI_VIEWPORT_PROFILES, containerBand } from '@platform/lib/flow-ui/layout/viewport-profiles.js';
import { framePointFromOverlay } from '@platform/lib/flow-ui/editor/overlay-coordinate-space.js';
import {
    effectiveParentMode,
    findParentComponent,
    isAuthorableDropTarget,
    parentGridColumns,
    resolveInteractionPolicy,
} from '@platform/lib/flow-ui/editor/layout-capabilities.js';
import {
    currentArea,
    proposeGridDrop,
    proposeGridMove,
    proposeGridResize,
    proposeKeyboardStep,
} from '@platform/lib/flow-ui/editor/layout-gesture.js';
import { createGridGeometry } from '@platform/lib/flow-ui/layout/grid-geometry.js';
import { occupiedAreas } from '@platform/lib/flow-ui/layout/grid-occupancy.js';
import {
    projectInsertPreview,
    proposeGridInsert,
} from '@platform/lib/flow-ui/layout/grid-insert.js';
import { activeSurface, defaultColumnSpan, findParentId } from './interface-editor-domain.js';
import { FLOW_UI_DND_MIME } from './flows-interface-palette.js';

const INLINE_EDITABLE = Object.freeze({
    Text: 'text',
    Heading: 'text',
    Markdown: 'content',
    Button: 'label',
});

export class FlowsInterfaceCanvas extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        document: { attribute: false },
        state: { attribute: false },
        flowId: { type: String },
        branchId: { type: String },
        selectionRect: { attribute: false },
        ghostRect: { attribute: false },
        targetCell: { attribute: false },
        targetCellValid: { attribute: false },
        previewRects: { attribute: false },
        interactionHandles: { attribute: false },
        _contextMenu: { state: true },
        _inlineEdit: { state: true },
        _fitZoom: { state: true },
        _dropTargetId: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host {
            display: block;
            min-width: 0;
            min-height: 0;
            overflow: auto;
            background-color: var(--bg-elevated);
            background-image: radial-gradient(
                circle,
                color-mix(in srgb, var(--text-tertiary) 12%, transparent) 1px,
                transparent 1px
            );
            background-size: 24px 24px;
        }
        .stage {
            min-width: 100%;
            min-height: 100%;
            display: grid;
            place-items: center;
            padding: 28px;
            box-sizing: border-box;
        }
        .zoom { position: relative; transform-origin: top center; }
        .artboard {
            position: relative;
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-lg);
            overflow: hidden;
            box-shadow: 0 4px 16px color-mix(in srgb, var(--text-primary) 8%, transparent);
        }
        flow-ui-production-render-frame,
        platform-flow-ui { display: block; width: 100%; height: 100%; }
        .artboard[data-edit='true'] flow-ui-production-render-frame { pointer-events: none; }
        .hit-layer { position: absolute; inset: 0; z-index: 15; cursor: default; }
        .run { width: min(100%, 1200px); height: calc(100vh - 230px); min-height: 560px; }
        .context-menu {
            position: fixed;
            z-index: 50;
            min-width: 180px;
            padding: 4px;
            border: 1px solid var(--border-default);
            border-radius: var(--radius-md);
            background: var(--glass-solid-strong);
            box-shadow: var(--shadow-lg);
            display: grid;
        }
        .context-menu .menu-item {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-primary);
            font-size: 12px;
            text-align: left;
            padding: 7px 9px;
            border-radius: 7px;
            cursor: pointer;
        }
        .context-menu .menu-item:hover { background: var(--glass-solid-medium); }
        .context-menu .menu-item:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
        .context-menu .menu-item[data-danger="true"] { color: var(--error); }
        .context-menu .sep { height: 1px; background: var(--border-subtle); margin: 3px 6px; }
        .inline-edit {
            position: absolute;
            z-index: 30;
            border: 1.5px solid var(--accent);
            border-radius: 6px;
            background: var(--bg-elevated);
            color: var(--text-primary);
            font: inherit;
            padding: 4px 6px;
            resize: none;
            box-sizing: border-box;
        }
        .inline-edit:focus { outline: none; }
    `];

    constructor() {
        super();
        this.document = null;
        this.state = {};
        this.flowId = '';
        this.branchId = 'default';
        this.selectionRect = null;
        this.ghostRect = null;
        this.targetCell = null;
        this.targetCellValid = true;
        this.previewRects = Object.freeze([]);
        this.interactionHandles = Object.freeze([]);
        this._inspectedComponents = Object.freeze([]);
        this._gesture = null;
        this._contextMenu = null;
        this._inlineEdit = null;
        this._fitZoom = 1;
        this._dropTargetId = '';
        this._resizeObserver = null;
        this._onKeyDown = (event) => this._handleKeyDown(event);
        this._onGlobalPointerDown = () => { this._contextMenu = null; };
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('keydown', this._onKeyDown);
        window.addEventListener('pointerdown', this._onGlobalPointerDown);
        this._resizeObserver = new ResizeObserver(() => this._recomputeFitZoom());
        this._resizeObserver.observe(this);
    }

    disconnectedCallback() {
        window.removeEventListener('keydown', this._onKeyDown);
        window.removeEventListener('pointerdown', this._onGlobalPointerDown);
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('state') || changed.has('document')) {
            this._syncSelectionRect();
            this._syncHandles();
        }
    }

    _viewport() {
        if (this.state?.viewportProfile === 'custom') {
            const width = Number(this.state.customWidth || 1440);
            const height = Number(this.state.customHeight || 900);
            return { css_width: width, css_height: height, band: containerBand(width) };
        }
        return FLOW_UI_VIEWPORT_PROFILES[this.state?.viewportProfile]
            || FLOW_UI_VIEWPORT_PROFILES['desktop-wide'];
    }

    _recomputeFitZoom() {
        const vp = this._viewport();
        const box = this.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) return;
        const scale = Math.min(
            (box.width - 88) / vp.css_width,
            (box.height - 88) / vp.css_height,
        );
        this._fitZoom = Math.max(0.1, Math.min(2, scale));
    }

    _zoomFactor() {
        if (this.state?.zoom === 'fit') return this._fitZoom;
        const zoom = Number(this.state?.zoom || 1);
        if (!Number.isFinite(zoom) || zoom <= 0) {
            throw new Error(`flows-interface-canvas: invalid zoom ${String(this.state?.zoom)}`);
        }
        return zoom;
    }

    _band() {
        return this._viewport().band || 'wide';
    }

    _surface() {
        if (!this.document) return null;
        return activeSurface(this.document);
    }

    _surfaceId(surface) {
        if (surface?.surface_id) return surface.surface_id;
        const page = this.document?.pages?.[this.document.active_page_id];
        if (page?.root_surface_id) return page.root_surface_id;
        throw new Error('flows-interface-canvas: surface_id missing');
    }

    _selectedIds() {
        const ids = this.state?.selectedComponentIds;
        if (Array.isArray(ids) && ids.length) return ids;
        return typeof this.state?.selectedComponentId === 'string'
            ? [this.state.selectedComponentId]
            : [];
    }

    _selectedComponent() {
        const surface = this._surface();
        const id = this.state?.selectedComponentId;
        if (!surface || typeof id !== 'string') return null;
        return surface.components?.[id] || null;
    }

    _syncHandles() {
        const component = this._selectedComponent();
        const surface = this._surface();
        if (!component || !surface || this._selectedIds().length > 1) {
            this.interactionHandles = Object.freeze([]);
            return;
        }
        const parent = findParentComponent(surface, component.component_id);
        const policy = resolveInteractionPolicy({
            component,
            parent,
            rootComponentId: surface.root_component_id || 'root',
            components: surface.components,
        });
        this.interactionHandles = policy.handles;
    }

    _syncSelectionRect() {
        const selectedId = this.state?.selectedComponentId;
        if (typeof selectedId !== 'string' || selectedId === '') {
            this.selectionRect = null;
            return;
        }
        const surface = this._surface();
        const rootId = surface?.root_component_id || 'root';
        const vp = this._viewport();
        if (selectedId === rootId) {
            this.selectionRect = { x: 0, y: 0, width: vp.css_width, height: vp.css_height };
            return;
        }
        const selected = this._inspectedComponents.find((item) => item.componentId === selectedId);
        this.selectionRect = selected
            ? {
                x: selected.rect.x,
                y: selected.rect.y,
                width: selected.rect.width,
                height: selected.rect.height,
            }
            : null;
    }

    _structureRects() {
        const hoveredId = this.state?.hoveredComponentId || '';
        if (!hoveredId) {
            return Object.freeze([]);
        }
        const selectedIds = new Set(this._selectedIds());
        const byId = new Map(
            this._inspectedComponents.map((item) => [item.componentId, item]),
        );
        const surface = this._surface();
        const chainIds = [];
        let currentId = hoveredId;
        const seen = new Set();
        while (currentId && !seen.has(currentId)) {
            seen.add(currentId);
            if (!selectedIds.has(currentId)) {
                chainIds.push(currentId);
            }
            currentId = findParentId(surface, currentId);
        }
        return Object.freeze(
            chainIds
                .map((componentId) => {
                    const item = byId.get(componentId);
                    if (!item?.rect) return null;
                    return Object.freeze({
                        componentId,
                        rect: item.rect,
                        selected: false,
                    });
                })
                .filter((item) => item !== null),
        );
    }

    _dataFlowMarks() {
        return buildFlowUIDataFlowMarks(this._surface(), this._inspectedComponents);
    }

    _committed(event) {
        const frame = this.renderRoot.querySelector('flow-ui-production-render-frame');
        if (!frame || typeof frame.inspect !== 'function') {
            throw new Error('flows-interface-canvas: production frame inspect unavailable');
        }
        const inspection = frame.inspect();
        this._inspectedComponents = Array.isArray(inspection.components)
            ? Object.freeze(inspection.components)
            : Object.freeze([]);
        this._syncSelectionRect();
        this._syncHandles();
        this._clearGestureOverlays();
        this.emit('canvas-committed', {
            ...event.detail,
            revision: this.document?.revision,
            inspection,
        });
    }

    _layoutPoint(clientX, clientY) {
        const artboard = this.renderRoot?.querySelector('.artboard');
        if (!artboard) {
            throw new Error('flows-interface-canvas: artboard missing');
        }
        const box = artboard.getBoundingClientRect();
        return framePointFromOverlay({ x: clientX, y: clientY }, box, this._zoomFactor());
    }

    _hitComponent(layoutX, layoutY, { containersOnly = false, excludeIds = null } = {}) {
        const surface = this._surface();
        let hit = null;
        let hitArea = Number.POSITIVE_INFINITY;
        for (const item of this._inspectedComponents) {
            if (excludeIds && excludeIds.has(item.componentId)) continue;
            if (containersOnly) {
                const component = surface?.components?.[item.componentId];
                if (!component || component.kind !== 'container') continue;
            }
            const rect = item.rect;
            if (
                layoutX < rect.x
                || layoutX > rect.x + rect.width
                || layoutY < rect.y
                || layoutY > rect.y + rect.height
            ) {
                continue;
            }
            const area = rect.width * rect.height;
            if (area < hitArea) {
                hit = item;
                hitArea = area;
            }
        }
        return hit;
    }

    _locked(componentId) {
        return (this.state?.lockedComponentIds || []).includes(componentId);
    }

    _select(event) {
        if (this.state?.previewMode === true || this.state?.runMode === true) return;
        if (this._gesture) return;
        const point = this._layoutPoint(event.clientX, event.clientY);
        const vp = this._viewport();
        const insideArtboard = point.x >= 0 && point.y >= 0
            && point.x <= vp.css_width && point.y <= vp.css_height;
        const hit = this._hitComponent(point.x, point.y);
        const surface = this._surface();
        const rootId = surface?.root_component_id || 'root';
        let componentId = hit?.componentId || (insideArtboard ? rootId : null);
        if (componentId && this._locked(componentId)) componentId = rootId;
        if (!componentId) return;
        this.emit('component-select', { componentId, additive: event.shiftKey === true });
    }

    _hover(event) {
        if (this.state?.previewMode === true || this.state?.runMode === true) return;
        if (this._gesture) return;
        const point = this._layoutPoint(event.clientX, event.clientY);
        const vp = this._viewport();
        const insideArtboard = point.x >= 0 && point.y >= 0
            && point.x <= vp.css_width && point.y <= vp.css_height;
        if (!insideArtboard) {
            if (this.state?.hoveredComponentId) {
                this.emit('component-hover', { componentId: '' });
            }
            return;
        }
        const hit = this._hitComponent(point.x, point.y);
        const componentId = hit?.componentId || '';
        if (componentId === (this.state?.hoveredComponentId || '')) return;
        this.emit('component-hover', { componentId });
    }

    _hoverLeave() {
        if (this.state?.hoveredComponentId) {
            this.emit('component-hover', { componentId: '' });
        }
    }

    _openContextMenu(event) {
        if (this.state?.previewMode === true || this.state?.runMode === true) return;
        event.preventDefault();
        event.stopPropagation();
        const point = this._layoutPoint(event.clientX, event.clientY);
        const hit = this._hitComponent(point.x, point.y);
        const surface = this._surface();
        const rootId = surface?.root_component_id || 'root';
        const componentId = hit?.componentId || rootId;
        if (!this._selectedIds().includes(componentId)) {
            this.emit('component-select', { componentId, additive: false });
        }
        this._contextMenu = { x: event.clientX, y: event.clientY, componentId };
    }

    _contextAction(name, detail = {}) {
        const menu = this._contextMenu;
        this._contextMenu = null;
        if (!menu) return;
        this.emit(name, { componentId: menu.componentId, ...detail });
    }

    _openComponentMenu(event) {
        this._contextMenu = null;
        this.emit('component-menu-open', event.detail);
    }

    _openInlineEdit(event) {
        if (this.state?.previewMode === true || this.state?.runMode === true) return;
        const point = this._layoutPoint(event.clientX, event.clientY);
        const hit = this._hitComponent(point.x, point.y);
        if (!hit) return;
        const surface = this._surface();
        const component = surface?.components?.[hit.componentId];
        const propertyName = component ? INLINE_EDITABLE[component.type] : null;
        if (!component || !propertyName) return;
        const raw = component.properties?.[propertyName];
        this._inlineEdit = {
            componentId: component.component_id,
            name: propertyName,
            value: raw == null ? '' : String(raw),
            rect: hit.rect,
        };
        this.updateComplete.then(() => {
            const input = this.renderRoot.querySelector('.inline-edit');
            input?.focus();
            input?.select();
        });
    }

    _commitInlineEdit(value) {
        const edit = this._inlineEdit;
        this._inlineEdit = null;
        if (!edit) return;
        if (String(value) === edit.value) return;
        this.emit('component-inline-edit', {
            componentId: edit.componentId,
            name: edit.name,
            value: String(value),
        });
    }

    /**
     * The grid of a container, built from its real rendered content box.
     * One geometry for hit-testing, ghosting, target highlight and commit, so
     * the highlighted cell is always the cell that gets written.
     */
    _geometry(parent) {
        if (!parent || effectiveParentMode(parent, this._surface()?.components) !== 'grid') return null;
        const inspected = this._inspectedComponents.find(
            (item) => item.componentId === parent.component_id,
        );
        if (!inspected?.contentRect) return null;
        if (!(inspected.contentRect.width > 0)) return null;
        return createGridGeometry({
            contentRect: inspected.contentRect,
            columns: parentGridColumns(parent, this._band()),
            columnGap: inspected.columnGap,
            rowGap: inspected.rowGap,
            rowTracks: inspected.rowTracks,
        });
    }

    /** Geometry of the page root grid — what the grid overlay draws. */
    _rootGeometry() {
        const surface = this._surface();
        const rootId = surface?.root_component_id || 'root';
        return this._geometry(surface?.components?.[rootId]);
    }

    _occupied(parent, excludeComponentId) {
        const surface = this._surface();
        if (!surface) return Object.freeze([]);
        return occupiedAreas({
            parent,
            components: surface.components,
            band: this._band(),
            columns: parentGridColumns(parent, this._band()),
            excludeComponentId,
        });
    }

    /**
     * Cell aimed at by a drop into `container`: the cell under the pointer with the
     * given column span. Used by reparent, where the moved element must find a free
     * cell instead of pushing siblings around.
     */
    _dropProposal(container, point, columnSpan, excludeComponentId = null) {
        const geometry = this._geometry(container);
        if (!geometry) return null;
        return proposeGridDrop({
            geometry,
            point,
            columnSpan,
            occupied: this._occupied(container, excludeComponentId),
        });
    }

    /**
     * Palette insert: the row always opens up, and the preview shows where the
     * siblings end up so the author sees the result before dropping.
     */
    _insertProposal(container, point, type) {
        const geometry = this._geometry(container);
        if (!geometry) return null;
        const occupied = this._occupied(container, null);
        const proposal = proposeGridInsert({
            geometry,
            point,
            columnSpan: defaultColumnSpan(type),
            occupied,
        });
        return Object.freeze({
            ...proposal,
            targetCell: geometry.rectOf(proposal.area),
            previewRects: Object.freeze(
                projectInsertPreview({ occupied, shifted: proposal.shifted })
                    .map((item) => Object.freeze({
                        componentId: item.componentId,
                        rect: geometry.rectOf(item),
                    })),
            ),
        });
    }

    _paletteDragOver(event) {
        if (![...event.dataTransfer.types].includes(FLOW_UI_DND_MIME)) return;
        event.preventDefault();
        const point = this._layoutPoint(event.clientX, event.clientY);
        const surface = this._surface();
        const rootId = surface?.root_component_id || 'root';
        const hit = this._hitComponent(point.x, point.y, { containersOnly: true });
        const targetId = hit?.componentId || rootId;
        const container = surface?.components?.[targetId];
        if (!isAuthorableDropTarget(container, surface?.components)) {
            this._dropTargetId = '';
            this.targetCell = null;
            this.targetCellValid = true;
            event.dataTransfer.dropEffect = 'none';
            return;
        }
        const proposal = this._insertProposal(container, point, this._paletteDragType(event));
        this._dropTargetId = proposal === null ? '' : targetId;
        this.targetCell = proposal === null ? null : proposal.targetCell;
        this.targetCellValid = true;
        this.previewRects = proposal === null ? Object.freeze([]) : proposal.previewRects;
        event.dataTransfer.dropEffect = proposal === null ? 'none' : 'copy';
    }

    /**
     * During `dragover` the payload is unreadable, so the palette also exposes the
     * dragged type as a MIME suffix (`<mime>:<type>`) for the drop preview.
     */
    _paletteDragType(event) {
        const typed = [...event.dataTransfer.types]
            .find((entry) => entry.startsWith(`${FLOW_UI_DND_MIME}:`));
        if (!typed) {
            throw new Error('flows-interface-canvas: palette drag is missing its typed MIME');
        }
        return typed.slice(FLOW_UI_DND_MIME.length + 1);
    }

    _paletteDrop(event) {
        const type = event.dataTransfer.getData(FLOW_UI_DND_MIME);
        const targetParentId = this._dropTargetId;
        this._clearDropPreview();
        if (!type || !targetParentId) return;
        event.preventDefault();
        const surface = this._surface();
        const container = surface?.components?.[targetParentId];
        if (!isAuthorableDropTarget(container, surface?.components)) return;
        const point = this._layoutPoint(event.clientX, event.clientY);
        const proposal = this._insertProposal(container, point, type);
        if (proposal === null) return;
        this.emit('component-drop', {
            type,
            targetParentId,
            index: (container.children || []).length,
            area: proposal.area,
            shifted: proposal.shifted,
        });
    }

    _clearDropPreview() {
        this.targetCell = null;
        this.targetCellValid = true;
        this.previewRects = Object.freeze([]);
        this._dropTargetId = '';
    }

    _gestureStart(event) {
        const component = this._selectedComponent();
        const surface = this._surface();
        if (!component || !surface || !this.selectionRect) {
            throw new Error('flows-interface-canvas: gesture requires selection');
        }
        const parent = findParentComponent(surface, component.component_id);
        const policy = resolveInteractionPolicy({
            component,
            parent,
            rootComponentId: surface.root_component_id || 'root',
            components: surface.components,
        });
        const kind = event.detail.kind;
        if (kind === 'move' && !policy.canMove) {
            throw new Error('flows-interface-canvas: move forbidden for selection');
        }
        if (kind !== 'move' && !policy.canResizeInline && !policy.canResizeBlock) {
            throw new Error('flows-interface-canvas: resize forbidden for selection');
        }
        const geometry = this._geometry(parent);
        if (!geometry) {
            throw new Error('flows-interface-canvas: gesture requires a rendered parent grid');
        }
        const point = this._layoutPoint(event.detail.clientX, event.detail.clientY);
        this._gesture = {
            kind,
            componentId: component.component_id,
            policy,
            parent,
            geometry,
            occupied: this._occupied(parent, component.component_id),
            surfaceId: this._surfaceId(surface),
            pointerStart: point,
            startRect: { ...this.selectionRect },
            placement: component.placement || { base: {}, overrides: {} },
            columnSpan: currentArea({
                placement: component.placement || { base: {}, overrides: {} },
                band: this._band(),
                columns: geometry.columns,
                policy,
            }).columnSpan,
            reparentTargetId: null,
            reparentArea: null,
            lastProposal: null,
        };
        this.ghostRect = { ...this.selectionRect };
        this.targetCell = null;
        this.targetCellValid = true;
    }

    _gestureMove(event) {
        if (!this._gesture) return;
        const point = this._layoutPoint(event.detail.clientX, event.detail.clientY);
        // Reparent affordance: while moving over a foreign container, aim at its cell.
        if (this._gesture.kind === 'move') {
            const targetId = this._reparentTarget(point);
            if (targetId) {
                const container = this._surface()?.components?.[targetId];
                const proposal = this._dropProposal(
                    container,
                    point,
                    this._gesture.columnSpan,
                    this._gesture.componentId,
                );
                this.ghostRect = null;
                this.targetCell = proposal
                    ? proposal.targetCell
                    : { ...this._inspectedComponents.find((item) => item.componentId === targetId).rect };
                this.targetCellValid = proposal ? proposal.valid : true;
                this._gesture.lastProposal = null;
                this._gesture.reparentTargetId = targetId;
                this._gesture.reparentArea = proposal?.valid ? proposal.area : null;
                return;
            }
            this._gesture.reparentTargetId = null;
            this._gesture.reparentArea = null;
        }
        const proposal = this._propose(point);
        this.ghostRect = proposal.ghostRect;
        this.targetCell = proposal.targetCell;
        this.targetCellValid = proposal.valid;
        this._gesture.lastProposal = proposal;
    }

    _reparentTarget(point) {
        const gesture = this._gesture;
        const surface = this._surface();
        if (!gesture || !surface) return null;
        const exclude = new Set([gesture.componentId]);
        const collect = (id) => {
            for (const childId of surface.components?.[id]?.children || []) {
                exclude.add(childId);
                collect(childId);
            }
        };
        collect(gesture.componentId);
        const hit = this._hitComponent(point.x, point.y, { containersOnly: true, excludeIds: exclude });
        if (!hit) return null;
        if (hit.componentId === gesture.parent?.component_id) return null;
        // Feeds and shells are runtime-owned containers, not drop targets.
        if (!isAuthorableDropTarget(surface.components?.[hit.componentId], surface.components)) return null;
        return hit.componentId;
    }

    _propose(pointerNow, gestureSession = null) {
        const gesture = gestureSession || this._gesture;
        if (!gesture) {
            throw new Error('flows-interface-canvas: gesture required for propose');
        }
        const session = {
            geometry: gesture.geometry,
            startRect: gesture.startRect,
            pointerStart: gesture.pointerStart,
            pointerNow,
            placement: gesture.placement,
            band: this._band(),
            policy: gesture.policy,
            occupied: gesture.occupied,
        };
        return gesture.kind === 'move'
            ? proposeGridMove(session)
            : proposeGridResize({ ...session, kind: gesture.kind });
    }

    _clearGestureOverlays() {
        this.ghostRect = null;
        this.targetCell = null;
        this.targetCellValid = true;
        this.previewRects = Object.freeze([]);
    }

    _gestureEnd(event) {
        if (!this._gesture) return;
        const gesture = this._gesture;
        this._gesture = null;
        if (event.detail.cancelled === true) {
            this._clearGestureOverlays();
            return;
        }
        const point = this._layoutPoint(event.detail.clientX, event.detail.clientY);

        if (gesture.kind === 'move' && gesture.reparentTargetId) {
            const container = this._surface()?.components?.[gesture.reparentTargetId];
            const area = gesture.reparentArea;
            this._clearGestureOverlays();
            if (!container || !area) return;
            this.emit('layout-command', {
                kind: 'children.move',
                surfaceId: gesture.surfaceId,
                componentId: gesture.componentId,
                targetParentId: gesture.reparentTargetId,
                index: (container.children || []).length,
                band: this._band(),
                patch: this._areaPatch(area),
            });
            return;
        }

        const proposal = gesture.lastProposal || this._propose(point, gesture);
        this._clearGestureOverlays();
        // Occupied cells: the gesture simply does not commit, siblings never move.
        if (!proposal.valid) return;
        if (Object.keys(proposal.patch).length === 0) return;
        this.emit('layout-command', {
            kind: 'placement.set',
            surfaceId: gesture.surfaceId,
            componentId: gesture.componentId,
            band: this._band(),
            patch: proposal.patch,
        });
    }

    _areaPatch(area) {
        return {
            column_start: area.columnStart,
            column_span: area.columnSpan,
            row_start: area.rowStart,
            row_span: area.rowSpan,
        };
    }

    _handleKeyDown(event) {
        if (this.state?.previewMode === true || this.state?.runMode === true) return;
        if (event.target && event.target !== this && event.target.closest?.('input,textarea,select,[contenteditable]')) {
            return;
        }
        if (event.key === 'Escape') {
            if (this._inlineEdit) { this._inlineEdit = null; event.preventDefault(); return; }
            if (this._contextMenu) { this._contextMenu = null; event.preventDefault(); return; }
            if (this._gesture) {
                this._gesture = null;
                this._clearGestureOverlays();
                event.preventDefault();
                return;
            }
        }
        const keys = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']);
        if (!keys.has(event.key)) return;

        const component = this._selectedComponent();
        const surface = this._surface();
        if (!component || !surface) return;
        const parent = findParentComponent(surface, component.component_id);
        const policy = resolveInteractionPolicy({
            component,
            parent,
            rootComponentId: surface.root_component_id || 'root',
            components: surface.components,
        });
        if (effectiveParentMode(parent, surface.components) !== 'grid') return;
        const band = this._band();
        const step = proposeKeyboardStep({
            key: event.key,
            shift: event.shiftKey === true,
            policy,
            placement: component.placement || { base: {}, overrides: {} },
            band,
            columns: parentGridColumns(parent, band),
            occupied: this._occupied(parent, component.component_id),
        });
        if (!step) return;
        event.preventDefault();
        this.emit('layout-command', {
            kind: 'placement.set',
            surfaceId: this._surfaceId(surface),
            componentId: component.component_id,
            band,
            patch: step.patch,
        });
    }

    _menuItem(labelKey, eventName, danger = false) {
        return html`<span
            class="menu-item"
            role="menuitem"
            tabindex="0"
            data-danger=${danger ? 'true' : 'false'}
            @click=${() => this._contextAction(eventName)}
            @keydown=${(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    this._contextAction(eventName);
                }
            }}
        >${this.t(labelKey)}</span>`;
    }

    _renderContextMenu() {
        const menu = this._contextMenu;
        if (!menu) return nothing;
        const surface = this._surface();
        const rootId = surface?.root_component_id || 'root';
        const isRoot = menu.componentId === rootId;
        return html`<div
            class="context-menu"
            style=${`left:${menu.x}px;top:${menu.y}px`}
            role="menu"
            @pointerdown=${(event) => event.stopPropagation()}
        >
            ${!isRoot ? html`
                ${this._menuItem('interface_editor.menu_duplicate', 'component-duplicate')}
                ${this._menuItem('interface_editor.menu_copy', 'component-copy')}
            ` : nothing}
            ${this._menuItem('interface_editor.menu_paste', 'component-paste')}
            ${!isRoot ? html`
                ${this._menuItem('interface_editor.menu_wrap_section', 'component-wrap')}
                <div class="sep"></div>
                ${this._menuItem('interface_editor.menu_delete', 'component-delete-request', true)}
            ` : nothing}
        </div>`;
    }

    _renderInlineEdit() {
        const edit = this._inlineEdit;
        if (!edit) return nothing;
        const style = `left:${edit.rect.x}px;top:${edit.rect.y}px;`
            + `width:${Math.max(edit.rect.width, 120)}px;`
            + `min-height:${Math.max(edit.rect.height, 30)}px`;
        return html`<textarea
            class="inline-edit"
            data-canon="inline-edit"
            style=${style}
            .value=${edit.value}
            @keydown=${(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    this._commitInlineEdit(event.target.value);
                }
                if (event.key === 'Escape') this._inlineEdit = null;
            }}
            @blur=${(event) => this._commitInlineEdit(event.target.value)}
        ></textarea>`;
    }

    render() {
        const s = this.state || {};
        if (s.runMode) {
            return html`<div class="stage">
                <platform-flow-ui
                    class="run"
                    flow-id=${this.flowId}
                    branch-id=${this.branchId === 'base' ? 'default' : (this.branchId || 'default')}
                    base-url="/flows"
                    display=${s.targetSurface || 'page'}
                    profile="editor_test"
                ></platform-flow-ui>
            </div>`;
        }
        const vp = this._viewport();
        const zoom = this._zoomFactor();
        const editing = s.previewMode !== true;
        return html`<div class="stage">
            <div
                class="zoom"
                style=${`width:${vp.css_width}px;height:${vp.css_height}px;transform:scale(${zoom})`}
            >
                <div
                    class="artboard"
                    data-edit=${editing ? 'true' : 'false'}
                    style=${`width:${vp.css_width}px;height:${vp.css_height}px`}
                >
                    <flow-ui-production-render-frame
                        .document=${this.document}
                        display=${s.targetSurface || 'page'}
                        profile="editor_test"
                        .readonly=${editing}
                        .selectedComponentId=${s.selectedComponentId}
                        @parity-ready=${this._committed}
                    ></flow-ui-production-render-frame>
                    ${editing
                        ? html`
                            <div
                                class="hit-layer"
                                @click=${this._select}
                                @pointermove=${this._hover}
                                @pointerleave=${this._hoverLeave}
                                @dblclick=${this._openInlineEdit}
                                @contextmenu=${this._openContextMenu}
                                @dragover=${this._paletteDragOver}
                                @dragleave=${() => this._clearDropPreview()}
                                @drop=${this._paletteDrop}
                            ></div>
                            <flow-ui-layout-grid-overlay
                                .visible=${s.gridVisible}
                                .geometry=${this._rootGeometry()}
                            ></flow-ui-layout-grid-overlay>
                            <flow-ui-rulers-guides-overlay
                                .rulersVisible=${s.rulersVisible === true}
                                .baselineVisible=${s.baselineVisible === true}
                                .guidesVisible=${s.guidesVisible === true}
                                .guides=${s.guides || []}
                                .width=${vp.css_width}
                                .height=${vp.css_height}
                                @guides-change=${(event) => this.emit('guides-change', event.detail)}
                            ></flow-ui-rulers-guides-overlay>
                            <flow-ui-data-flow-overlay
                                .visible=${s.dataFlowVisible === true}
                                .bindings=${this._dataFlowMarks()}
                            ></flow-ui-data-flow-overlay>
                            <flow-ui-selection-overlay
                                .rect=${this.selectionRect}
                                .label=${s.selectedComponentId || ''}
                                .handles=${this.interactionHandles}
                                .ghostRect=${this.ghostRect}
                                .targetCell=${this.targetCell}
                                .targetCellValid=${this.targetCellValid}
                                .previewRects=${this.previewRects}
                                .structureRects=${this._structureRects()}
                                .hoveredComponentId=${s.hoveredComponentId || ''}
                                .menuEnabled=${!this._gesture}
                                .menuLabel=${this.t('interface_editor.component_menu')}
                                .interactive=${true}
                                @selection-gesture-start=${this._gestureStart}
                                @selection-gesture-move=${this._gestureMove}
                                @selection-gesture-end=${this._gestureEnd}
                                @component-menu-open=${this._openComponentMenu}
                            ></flow-ui-selection-overlay>
                            ${this._renderInlineEdit()}
                        `
                        : nothing}
                </div>
            </div>
            ${this._renderContextMenu()}
        </div>`;
    }
}

if (!customElements.get('flows-interface-canvas')) {
    customElements.define('flows-interface-canvas', FlowsInterfaceCanvas);
}
