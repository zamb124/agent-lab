/**
 * flows-flow-canvas — native SVG канвас flow editor.
 *
 * Слои (z по порядку): grid → sticky-notes → edges → guides → nodes → context-menu.
 *
 * Источники state:
 *   - useOp('flows/editor').state.skillsData.{nodes,edges} — граф;
 *   - useOp('flows/editor').state.activeTool — select|pan;
 *   - useOp('flows/editor').state.viewBox — pan/zoom;
 *   - useOp('flows/editor').state.selectedNodeId / multiSelection;
 *   - useOp('flows/editor').state.{runningNodeIds,completedNodeIds,erroredNodes} — push из flows/run/*;
 *   - useOp('flows/editor').state.breakpointNodeIds / breakpointHitNodeId — flows/breakpoint/hit;
 *   - useOp('flows/editor').state.entryNodeId — entry-нода;
 *   - useOp('flows/editor').state.stickyNotes / smartGuides / smartGuidesEnabled.
 *
 * UX:
 *   - drag нод pointermove с snap-to-guide;
 *   - drag-create узла из <flows-node-types-sidebar>:
 *     `application/x-flow-node-type` для нод, `application/x-flow-resource-type` для ресурсов;
 *   - draw edges с output-порта на input-порт;
 *   - zoom: ctrl + wheel; pan: пробел/middle-mouse-drag/tool=pan;
 *   - select: click; multi-select: shift+drag по фону → bounding-rect;
 *   - hotkeys (вешаются на document): Del/Ctrl+A/Ctrl+D/F2/Enter/Esc/стрелки/Shift+S;
 *   - правый клик → диспатч `openContextMenu` через slice; <flows-canvas-context-menu>
 *     рендерится оверлеем и эмитит `action`/`close`.
 */

import { html, css, svg } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { getNodeTypeMeta, getCategoryToken } from '../../constants/node-icons.js';
import { renderEdgeLabel } from './flows-edge-label.js';
import './flows-canvas-context-menu.js';
import './flows-sticky-note.js';

const NODE_W = 200;
const NODE_H = 72;
const NODE_RADIUS = 12;
const PORT_R = 6;
const SNAP_THRESHOLD = 4;
const GRID_STEP = 24;
const STICKY_W = 200;
const STICKY_H = 140;

function genId(prefix) {
    return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

function pathFor(srcX, srcY, dstX, dstY) {
    const dx = Math.abs(dstX - srcX) * 0.6;
    return `M ${srcX} ${srcY} C ${srcX + dx} ${srcY} ${dstX - dx} ${dstY} ${dstX} ${dstY}`;
}

function midpoint(srcX, srcY, dstX, dstY) {
    return { x: (srcX + dstX) / 2, y: (srcY + dstY) / 2 };
}

export class FlowsFlowCanvas extends PlatformElement {
    static properties = {
        flowId: { type: String },
        skillId: { type: String },
        _drag: { state: true },
        _connection: { state: true },
        _selectionRect: { state: true },
        _spacePressed: { state: true },
        _pan: { state: true },
        _hoverEdgeIndex: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; flex: 1; min-width: 0; min-height: 0; position: relative; overflow: hidden; }
            svg.canvas-host {
                width: 100%; height: 100%;
                user-select: none;
                cursor: default;
                background: var(--bg-secondary, var(--bg-primary));
            }
            svg.canvas-host[data-tool="pan"] { cursor: grab; }
            svg.canvas-host[data-pan-active] { cursor: grabbing; }

            .grid-pattern path {
                fill: var(--border-subtle);
                opacity: 0.4;
            }

            /* Node */
            g.node { transition: opacity 150ms; }
            g.node[data-inherited] { opacity: 0.7; }
            g.node .node-card {
                fill: var(--glass-solid-strong);
                stroke: var(--border-subtle);
                stroke-width: 1.5;
                transition: stroke 0.12s, filter 0.12s;
            }
            g.node:hover .node-card {
                stroke: var(--glass-border-medium);
                filter: drop-shadow(0 4px 16px rgba(0, 0, 0, 0.18));
            }
            g.node[data-selected] .node-card {
                stroke: var(--accent);
                stroke-width: 2;
            }
            g.node[data-multi-selected] .node-card {
                stroke: var(--accent);
                stroke-width: 2;
                stroke-dasharray: 6 3;
            }
            g.node[data-state="running"] .node-card {
                stroke: var(--info);
                stroke-width: 2;
                animation: nodePulseRunning 1.4s ease-in-out infinite;
            }
            g.node[data-state="completed"] .node-card {
                stroke: var(--success);
                stroke-width: 1.5;
            }
            g.node[data-state="error"] .node-card {
                stroke: var(--error);
                stroke-width: 2;
                filter: drop-shadow(0 0 8px var(--error));
            }
            g.node[data-state="breakpoint-hit"] .node-card {
                stroke: var(--warning);
                stroke-width: 2;
                animation: nodePulseRunning 1s ease-in-out infinite;
            }

            @keyframes nodePulseRunning {
                0%, 100% { stroke-opacity: 1; }
                50%      { stroke-opacity: 0.45; }
            }

            .node-icon-wrap {
                width: 36px; height: 36px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-sm);
            }
            .node-icon-wrap[data-cat="core"]         { background: var(--accent-subtle); color: var(--accent); }
            .node-icon-wrap[data-cat="integrations"] { background: var(--info-bg); color: var(--info); }
            .node-icon-wrap[data-cat="flow"]         { background: var(--accent-secondary-subtle); color: var(--accent-secondary); }
            .node-icon-wrap[data-cat="hitl"]         { background: var(--warning-bg); color: var(--warning); }
            .node-card-content {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                width: 100%; height: 100%;
                box-sizing: border-box;
                font-family: var(--font-sans);
            }
            .node-meta { display: flex; flex-direction: column; min-width: 0; flex: 1; }
            .node-name {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
            }
            .node-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                white-space: nowrap;
            }

            /* Badges */
            .badge-entry {
                fill: var(--accent);
            }
            .badge-bp-circle {
                fill: var(--warning);
                stroke: var(--bg-primary);
                stroke-width: 1.5;
            }
            .badge-inherited {
                fill: var(--text-tertiary);
            }

            /* Ports */
            .port {
                fill: var(--accent);
                stroke: var(--bg-primary);
                stroke-width: 1.5;
                cursor: crosshair;
                transition: r 120ms, fill 120ms;
            }
            .port:hover { fill: var(--accent-hover); }
            .port.in { fill: var(--text-tertiary); }
            .port.in:hover { fill: var(--accent); }

            /* Edges */
            .edge {
                fill: none;
                stroke: var(--text-tertiary);
                stroke-width: 2;
                cursor: pointer;
                transition: stroke 0.12s, stroke-width 0.12s;
            }
            .edge:hover, .edge[data-hover] {
                stroke: var(--accent);
                stroke-width: 3;
            }
            .edge[data-selected] {
                stroke: var(--accent);
                stroke-width: 3;
            }
            .edge-end-marker {
                fill: var(--text-tertiary);
                opacity: 0.6;
            }
            .edge-end-text {
                font-size: 10px;
                font-family: var(--font-mono);
                fill: var(--text-tertiary);
                pointer-events: none;
            }
            .edge-temp {
                fill: none;
                stroke: var(--accent);
                stroke-width: 2;
                stroke-dasharray: 4 4;
                pointer-events: none;
            }
            .edge-label .label-bg {
                fill: var(--glass-solid-strong);
                stroke: var(--glass-border-subtle);
                stroke-width: 1;
            }
            .edge-label .label-text {
                font-family: var(--font-mono);
                font-size: 10px;
                fill: var(--text-secondary);
                pointer-events: none;
            }
            .edge-label { cursor: pointer; }
            .edge-label:hover .label-bg { stroke: var(--accent); }

            /* Selection rect */
            .selection-box {
                fill: var(--accent-subtle);
                stroke: var(--accent);
                stroke-width: 1;
                stroke-dasharray: 4 2;
                opacity: 0.5;
                pointer-events: none;
            }

            /* Smart guides */
            .smart-guide {
                stroke: var(--accent-hover);
                stroke-width: 1;
                stroke-dasharray: 2 2;
                opacity: 0.7;
                pointer-events: none;
            }

            /* Sticky note layer */
            .sticky-host { width: 100%; height: 100%; }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.skillId = 'base';
        this._drag = null;
        this._connection = null;
        this._selectionRect = null;
        this._spacePressed = false;
        this._pan = null;
        this._hoverEdgeIndex = -1;
        this._editor = this.useOp('flows/editor');
        this._bulkDelete = this.useOp('flows/editor_bulk_delete');
        this._stickyUpsert = this.useOp('flows/sticky_note_upsert');
        this._onDocKeyDown = this._onDocKeyDown.bind(this);
        this._onDocKeyUp = this._onDocKeyUp.bind(this);
        this._stickyResize = null;
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('keydown', this._onDocKeyDown);
        document.addEventListener('keyup', this._onDocKeyUp);
    }

    disconnectedCallback() {
        document.removeEventListener('keydown', this._onDocKeyDown);
        document.removeEventListener('keyup', this._onDocKeyUp);
        super.disconnectedCallback();
    }

    _state() { return this._editor.state || {}; }
    _skillsData() { return this._state().skillsData || { nodes: {}, edges: [] }; }
    _nodes() { return this._skillsData().nodes || {}; }
    _edges() { return Array.isArray(this._skillsData().edges) ? this._skillsData().edges : []; }
    _viewBox() { return this._state().viewBox || { x: 0, y: 0, w: 1600, h: 1000 }; }

    _portCoords(node, side) {
        const x = side === 'in' ? Number(node.pos_x) || 0 : (Number(node.pos_x) || 0) + NODE_W;
        const y = (Number(node.pos_y) || 0) + NODE_H / 2;
        return { x, y };
    }

    _localPoint(clientX, clientY) {
        const svgEl = this.renderRoot.querySelector('svg.canvas-host');
        if (!svgEl) return { x: 0, y: 0 };
        const pt = svgEl.createSVGPoint();
        pt.x = clientX; pt.y = clientY;
        const ctm = svgEl.getScreenCTM();
        if (!ctm) return { x: 0, y: 0 };
        const local = pt.matrixTransform(ctm.inverse());
        return { x: local.x, y: local.y };
    }

    /* ===== Document hotkeys ===== */
    _onDocKeyDown(e) {
        const tag = (e.target && e.target.tagName) || '';
        const isEditable = tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable);
        if (isEditable) return;
        if (e.code === 'Space') {
            this._spacePressed = true;
            return;
        }
        const cmd = e.metaKey || e.ctrlKey;
        if ((e.key === 'Delete' || e.key === 'Backspace')) {
            e.preventDefault();
            this._deleteSelection();
            return;
        }
        if (cmd && e.key.toLowerCase() === 'a') {
            e.preventDefault();
            this._selectAll();
            return;
        }
        if (cmd && e.key.toLowerCase() === 'd') {
            e.preventDefault();
            this._duplicateSelection();
            return;
        }
        if (cmd && e.key.toLowerCase() === 'z' && !e.shiftKey) {
            e.preventDefault();
            this._editor.undo({});
            return;
        }
        if (cmd && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))) {
            e.preventDefault();
            this._editor.redo({});
            return;
        }
        if (e.key === 'F2' || e.key === 'Enter') {
            const sel = this._state().selectedNodeId;
            if (sel) {
                e.preventDefault();
                this._editor.selectNode({ nodeId: sel });
            }
            return;
        }
        if (e.key === 'Escape') {
            e.preventDefault();
            this._editor.setMultiSelection({ nodeIds: [] });
            this._editor.closePanel({});
            return;
        }
        if (e.shiftKey && e.key.toLowerCase() === 's') {
            e.preventDefault();
            this._addStickyNoteAtCenter();
            return;
        }
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
            this._moveSelectionByArrow(e.key);
            e.preventDefault();
        }
    }

    _onDocKeyUp(e) {
        if (e.code === 'Space') this._spacePressed = false;
    }

    /* ===== Hotkey actions ===== */
    _deleteSelection() {
        const ids = this._state().multiSelection || [];
        const single = this._state().selectedNodeId;
        const targetIds = ids.length > 0 ? ids : (single ? [single] : []);
        if (targetIds.length === 0) return;
        if (!this.flowId) return;
        void this._bulkDelete.run({ flow_id: this.flowId, node_ids: targetIds });
        const data = this._skillsData();
        const newNodes = { ...(data.nodes || {}) };
        for (const id of targetIds) delete newNodes[id];
        const newEdges = (data.edges || []).filter((e) => {
            const from = e.from_node || e.from;
            const to = e.to_node || e.to;
            return !targetIds.includes(from) && !targetIds.includes(to);
        });
        const next = { ...data, nodes: newNodes, edges: newEdges };
        this._editor.updateSkillsData({ data: next });
        this._editor.pushHistory({ snapshot: next });
        this._editor.setDirty({ dirty: true });
        this._editor.setMultiSelection({ nodeIds: [] });
        this._editor.closePanel({});
    }

    _selectAll() {
        const ids = Object.keys(this._nodes());
        this._editor.setMultiSelection({ nodeIds: ids });
    }

    _duplicateSelection() {
        const ids = this._state().multiSelection || [];
        const single = this._state().selectedNodeId;
        const targetIds = ids.length > 0 ? ids : (single ? [single] : []);
        if (targetIds.length === 0) return;
        const data = this._skillsData();
        const nodes = { ...(data.nodes || {}) };
        const newIds = [];
        for (const id of targetIds) {
            const orig = nodes[id];
            if (!orig) continue;
            const copyId = genId('n');
            nodes[copyId] = {
                ...orig,
                pos_x: (Number(orig.pos_x) || 0) + 30,
                pos_y: (Number(orig.pos_y) || 0) + 30,
            };
            newIds.push(copyId);
        }
        const next = { ...data, nodes };
        this._editor.updateSkillsData({ data: next });
        this._editor.pushHistory({ snapshot: next });
        this._editor.setDirty({ dirty: true });
        this._editor.setMultiSelection({ nodeIds: newIds });
    }

    _moveSelectionByArrow(key) {
        const ids = this._state().multiSelection || [];
        const single = this._state().selectedNodeId;
        const targetIds = ids.length > 0 ? ids : (single ? [single] : []);
        if (targetIds.length === 0) return;
        const dx = key === 'ArrowLeft' ? -10 : key === 'ArrowRight' ? 10 : 0;
        const dy = key === 'ArrowUp' ? -10 : key === 'ArrowDown' ? 10 : 0;
        const data = this._skillsData();
        const nodes = { ...(data.nodes || {}) };
        for (const id of targetIds) {
            if (!nodes[id]) continue;
            nodes[id] = { ...nodes[id], pos_x: (Number(nodes[id].pos_x) || 0) + dx, pos_y: (Number(nodes[id].pos_y) || 0) + dy };
        }
        const next = { ...data, nodes };
        this._editor.updateSkillsData({ data: next });
        this._editor.setDirty({ dirty: true });
    }

    _addStickyNoteAtCenter() {
        const vb = this._viewBox();
        const cx = vb.x + vb.w / 2 - STICKY_W / 2;
        const cy = vb.y + vb.h / 2 - STICKY_H / 2;
        const note = {
            id: genId('sn'),
            x: cx, y: cy, width: STICKY_W, height: STICKY_H,
            text: '',
            color_token: 'warning_bg',
        };
        this._editor.addStickyNote({ note });
        this._persistStickyNotes([...(this._state().stickyNotes || []), note]);
    }

    _persistStickyNotes(notes) {
        if (!this.flowId) return;
        void this._stickyUpsert.run({ flow_id: this.flowId, sticky_notes: notes });
    }

    /* ===== Wheel zoom ===== */
    _onWheel(e) {
        if (!e.ctrlKey && !e.metaKey) return;
        e.preventDefault();
        const factor = e.deltaY > 0 ? 1.1 : 0.9;
        const vb = this._viewBox();
        const newW = vb.w * factor;
        const newH = vb.h * factor;
        const dx = (newW - vb.w) / 2;
        const dy = (newH - vb.h) / 2;
        this._editor.setViewBox({ viewBox: { x: vb.x - dx, y: vb.y - dy, w: newW, h: newH } });
    }

    /* ===== Pointer events ===== */
    _onPointerDownNode(e, nodeId) {
        if (e.button !== 0) return;
        e.stopPropagation();
        const isMulti = this._state().multiSelection.includes(nodeId);
        if (e.shiftKey) {
            const ids = this._state().multiSelection;
            const next = ids.includes(nodeId) ? ids.filter((x) => x !== nodeId) : [...ids, nodeId];
            this._editor.setMultiSelection({ nodeIds: next });
        } else if (!isMulti) {
            this._editor.selectNode({ nodeId });
        }
        const node = this._nodes()[nodeId];
        if (!node) return;
        const nodes = this._nodes();
        const draggedIds = this._state().multiSelection.length > 0 ? this._state().multiSelection : [nodeId];
        const offsets = {};
        for (const id of draggedIds) {
            if (!nodes[id]) continue;
            offsets[id] = { x: Number(nodes[id].pos_x) || 0, y: Number(nodes[id].pos_y) || 0 };
        }
        this._drag = {
            type: 'node',
            primaryId: nodeId,
            ids: draggedIds,
            offsets,
            startX: e.clientX, startY: e.clientY,
        };
        this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(e.pointerId);
    }

    _onPointerDownPort(e, nodeId, side) {
        if (e.button !== 0 || side !== 'out') return;
        e.stopPropagation();
        const node = this._nodes()[nodeId];
        if (!node) return;
        const start = this._portCoords(node, 'out');
        this._connection = { fromNode: nodeId, x1: start.x, y1: start.y, x2: start.x, y2: start.y };
        this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(e.pointerId);
    }

    _onPointerDownBackground(e) {
        if (e.button === 1 || (e.button === 0 && (this._spacePressed || this._state().activeTool === 'pan'))) {
            e.preventDefault();
            const vb = this._viewBox();
            this._pan = { startClientX: e.clientX, startClientY: e.clientY, origVB: { ...vb } };
            this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(e.pointerId);
            return;
        }
        if (e.button === 0 && e.shiftKey) {
            const local = this._localPoint(e.clientX, e.clientY);
            this._selectionRect = { x0: local.x, y0: local.y, x1: local.x, y1: local.y };
            this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(e.pointerId);
            return;
        }
        if (e.button === 0) {
            this._editor.setMultiSelection({ nodeIds: [] });
            this._editor.closePanel({});
        }
    }

    _onPointerMove(e) {
        if (this._pan) {
            const vb = this._pan.origVB;
            const svgEl = this.renderRoot.querySelector('svg.canvas-host');
            const rect = svgEl.getBoundingClientRect();
            const scaleX = vb.w / rect.width;
            const scaleY = vb.h / rect.height;
            const dx = (e.clientX - this._pan.startClientX) * scaleX;
            const dy = (e.clientY - this._pan.startClientY) * scaleY;
            this._editor.setViewBox({ viewBox: { x: vb.x - dx, y: vb.y - dy, w: vb.w, h: vb.h } });
            return;
        }
        if (this._drag?.type === 'node') {
            const local = this._localPoint(e.clientX, e.clientY);
            const startLocal = this._localPoint(this._drag.startX, this._drag.startY);
            const dx = local.x - startLocal.x;
            const dy = local.y - startLocal.y;
            const data = this._skillsData();
            const nodes = { ...(data.nodes || {}) };
            const guides = [];
            for (const id of this._drag.ids) {
                const orig = this._drag.offsets[id];
                if (!orig || !nodes[id]) continue;
                let newX = orig.x + dx;
                let newY = orig.y + dy;
                if (this._state().smartGuidesEnabled !== false && id === this._drag.primaryId) {
                    const snap = this._snapToGuides(newX, newY, id, nodes);
                    newX = snap.x; newY = snap.y;
                    guides.push(...snap.guides);
                }
                nodes[id] = { ...nodes[id], pos_x: newX, pos_y: newY };
            }
            this._editor.updateSkillsData({ data: { ...data, nodes } });
            this._editor.setSmartGuides({ guides });
            return;
        }
        if (this._connection) {
            const local = this._localPoint(e.clientX, e.clientY);
            this._connection = { ...this._connection, x2: local.x, y2: local.y };
            return;
        }
        if (this._selectionRect) {
            const local = this._localPoint(e.clientX, e.clientY);
            this._selectionRect = { ...this._selectionRect, x1: local.x, y1: local.y };
            return;
        }
        if (this._stickyResize) {
            const local = this._localPoint(e.clientX, e.clientY);
            const startLocal = this._localPoint(this._stickyResize.startClientX, this._stickyResize.startClientY);
            const dx = local.x - startLocal.x;
            const dy = local.y - startLocal.y;
            const notes = (this._state().stickyNotes || []).map((n) => n.id === this._stickyResize.noteId
                ? { ...n, width: Math.max(80, this._stickyResize.origW + dx), height: Math.max(60, this._stickyResize.origH + dy) }
                : n);
            this._editor.updateStickyNote({ note: notes.find((n) => n.id === this._stickyResize.noteId) });
            this._stickyResize.lastNotes = notes;
        }
    }

    _onPointerUp(e) {
        if (this._pan) {
            this._pan = null;
            return;
        }
        if (this._drag?.type === 'node') {
            this._editor.pushHistory({ snapshot: { ...this._skillsData() } });
            this._editor.setDirty({ dirty: true });
            this._editor.setSmartGuides({ guides: [] });
            this._drag = null;
            return;
        }
        if (this._connection) {
            const target = this.renderRoot.elementFromPoint(e.clientX, e.clientY);
            const targetNodeId = target?.dataset?.nodeId;
            const targetSide = target?.dataset?.portSide;
            if (targetNodeId && targetSide === 'in' && targetNodeId !== this._connection.fromNode) {
                const data = this._skillsData();
                const edges = [...(data.edges || []), { from_node: this._connection.fromNode, to_node: targetNodeId }];
                const next = { ...data, edges };
                this._editor.updateSkillsData({ data: next });
                this._editor.pushHistory({ snapshot: next });
                this._editor.setDirty({ dirty: true });
            }
            this._connection = null;
            return;
        }
        if (this._selectionRect) {
            const r = this._selectionRect;
            const minX = Math.min(r.x0, r.x1);
            const maxX = Math.max(r.x0, r.x1);
            const minY = Math.min(r.y0, r.y1);
            const maxY = Math.max(r.y0, r.y1);
            const ids = [];
            const nodes = this._nodes();
            for (const [id, node] of Object.entries(nodes)) {
                const nx = Number(node.pos_x) || 0;
                const ny = Number(node.pos_y) || 0;
                if (nx + NODE_W >= minX && nx <= maxX && ny + NODE_H >= minY && ny <= maxY) {
                    ids.push(id);
                }
            }
            this._editor.setMultiSelection({ nodeIds: ids });
            this._selectionRect = null;
            return;
        }
        if (this._stickyResize) {
            const notes = this._stickyResize.lastNotes || this._state().stickyNotes;
            this._persistStickyNotes(notes);
            this._stickyResize = null;
        }
    }

    /* ===== Smart guides snap ===== */
    _snapToGuides(x, y, draggedId, nodes) {
        let snappedX = x;
        let snappedY = y;
        const guides = [];
        const right = x + NODE_W;
        const bottom = y + NODE_H;
        const cx = x + NODE_W / 2;
        const cy = y + NODE_H / 2;
        for (const [id, node] of Object.entries(nodes)) {
            if (id === draggedId) continue;
            const nx = Number(node.pos_x) || 0;
            const ny = Number(node.pos_y) || 0;
            const ncx = nx + NODE_W / 2;
            const ncy = ny + NODE_H / 2;
            const nright = nx + NODE_W;
            const nbottom = ny + NODE_H;
            if (Math.abs(x - nx) <= SNAP_THRESHOLD) { snappedX = nx; guides.push({ axis: 'v', at: nx }); }
            else if (Math.abs(right - nright) <= SNAP_THRESHOLD) { snappedX = nright - NODE_W; guides.push({ axis: 'v', at: nright }); }
            else if (Math.abs(cx - ncx) <= SNAP_THRESHOLD) { snappedX = ncx - NODE_W / 2; guides.push({ axis: 'v', at: ncx }); }
            if (Math.abs(y - ny) <= SNAP_THRESHOLD) { snappedY = ny; guides.push({ axis: 'h', at: ny }); }
            else if (Math.abs(bottom - nbottom) <= SNAP_THRESHOLD) { snappedY = nbottom - NODE_H; guides.push({ axis: 'h', at: nbottom }); }
            else if (Math.abs(cy - ncy) <= SNAP_THRESHOLD) { snappedY = ncy - NODE_H / 2; guides.push({ axis: 'h', at: ncy }); }
        }
        return { x: snappedX, y: snappedY, guides };
    }

    /* ===== Context menu ===== */
    _onContextMenu(e, target, targetId) {
        e.preventDefault();
        e.stopPropagation();
        this._editor.openContextMenu({ menu: { x: e.clientX, y: e.clientY, target, targetId: targetId || '' } });
    }

    _onContextMenuAction(e) {
        const detail = e.detail || {};
        const kind = detail.kind;
        const target = detail.target;
        const targetId = detail.targetId;
        this._handleMenuAction(kind, target, targetId);
    }

    _handleMenuAction(kind, target, targetId) {
        const data = this._skillsData();
        if (target === 'node' && targetId) {
            if (kind === 'open_properties') { this._editor.selectNode({ nodeId: targetId }); return; }
            if (kind === 'toggle_entry') {
                const next = { ...data, entry: data.entry === targetId ? null : targetId };
                this._editor.updateSkillsData({ data: next });
                this._editor.setDirty({ dirty: true });
                this._editor.pushHistory({ snapshot: next });
                return;
            }
            if (kind === 'toggle_breakpoint') { this._editor.toggleBreakpoint({ nodeId: targetId }); return; }
            if (kind === 'duplicate') { this._editor.setMultiSelection({ nodeIds: [targetId] }); this._duplicateSelection(); return; }
            if (kind === 'delete') { this._editor.setMultiSelection({ nodeIds: [targetId] }); this._deleteSelection(); return; }
            if (kind === 'advanced_incoming_policy') { this.openModal('flows.incoming_policy', { nodeId: targetId }); return; }
        }
        if (target === 'edge') {
            const edgeIndex = Number(targetId);
            if (kind === 'edit_condition') { this.openModal('flows.edge_condition', { edgeIndex }); return; }
            if (kind === 'delete_edge') {
                const edges = (data.edges || []).filter((_, i) => i !== edgeIndex);
                const next = { ...data, edges };
                this._editor.updateSkillsData({ data: next });
                this._editor.pushHistory({ snapshot: next });
                this._editor.setDirty({ dirty: true });
                return;
            }
        }
        if (target === 'background') {
            if (kind === 'add_sticky') { this._addStickyNoteAtCenter(); return; }
            if (kind === 'fit_view') { this._fitView(); return; }
            if (kind === 'reset_zoom') {
                const vb = this._viewBox();
                this._editor.setViewBox({ viewBox: { x: vb.x, y: vb.y, w: 1600, h: 1000 } });
                return;
            }
            if (kind === 'select_all') { this._selectAll(); return; }
            if (kind === 'show_shortcuts') { this.openModal('flows.canvas_help', {}); return; }
        }
    }

    _fitView() {
        const nodes = Object.values(this._nodes());
        if (nodes.length === 0) return;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const n of nodes) {
            const x = Number(n.pos_x) || 0;
            const y = Number(n.pos_y) || 0;
            if (x < minX) minX = x;
            if (y < minY) minY = y;
            if (x + NODE_W > maxX) maxX = x + NODE_W;
            if (y + NODE_H > maxY) maxY = y + NODE_H;
        }
        const pad = 80;
        this._editor.setViewBox({ viewBox: { x: minX - pad, y: minY - pad, w: (maxX - minX) + pad * 2, h: (maxY - minY) + pad * 2 } });
    }

    /* ===== DnD создание ===== */
    _onDragOver(e) {
        const types = e.dataTransfer.types;
        if (types.includes('application/x-flow-node-type') || types.includes('application/x-flow-resource-type')) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        }
    }

    _onDrop(e) {
        const nodeType = e.dataTransfer.getData('application/x-flow-node-type');
        const resourceType = e.dataTransfer.getData('application/x-flow-resource-type');
        if (!nodeType && !resourceType) return;
        e.preventDefault();
        const local = this._localPoint(e.clientX, e.clientY);
        const data = this._skillsData();
        if (nodeType) {
            const id = genId('n');
            const newNode = {
                type: nodeType,
                name: nodeType,
                pos_x: local.x - NODE_W / 2,
                pos_y: local.y - NODE_H / 2,
                config: {},
            };
            const nodes = { ...(data.nodes || {}), [id]: newNode };
            const next = { ...data, nodes };
            this._editor.updateSkillsData({ data: next });
            this._editor.pushHistory({ snapshot: next });
            this._editor.setDirty({ dirty: true });
            this._editor.selectNode({ nodeId: id });
            return;
        }
        if (resourceType) {
            const id = genId('r');
            const resources = { ...(data.resources || {}), [id]: { type: resourceType, name: resourceType, config: {} } };
            const next = { ...data, resources };
            this._editor.updateSkillsData({ data: next });
            this._editor.pushHistory({ snapshot: next });
            this._editor.setDirty({ dirty: true });
            this._editor.selectResource({ resourceId: id });
        }
    }

    /* ===== Sticky notes drag/edit/delete ===== */
    _onStickyChange(e) {
        const detail = e.detail;
        if (!detail || !detail.noteId) return;
        const notes = (this._state().stickyNotes || []).map((n) => n.id === detail.noteId ? { ...n, text: detail.text } : n);
        this._editor.updateStickyNote({ note: notes.find((n) => n.id === detail.noteId) });
        this._persistStickyNotes(notes);
    }

    _onStickyRemove(e) {
        const noteId = e.detail?.noteId;
        if (!noteId) return;
        this._editor.removeStickyNote({ id: noteId });
        const notes = (this._state().stickyNotes || []).filter((n) => n.id !== noteId);
        this._persistStickyNotes(notes);
    }

    _onStickyResizeStart(e, note) {
        const detail = e.detail;
        if (!detail) return;
        this._stickyResize = {
            noteId: detail.noteId,
            startClientX: detail.x,
            startClientY: detail.y,
            origW: note.width,
            origH: note.height,
        };
        this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(0);
    }

    _onStickyDragStart(e, note) {
        if (e.button !== 0) return;
        e.stopPropagation();
        this._drag = {
            type: 'sticky',
            noteId: note.id,
            startX: e.clientX, startY: e.clientY,
            origX: note.x, origY: note.y,
        };
        this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(e.pointerId);
    }

    /* ===== Render ===== */
    _renderNode(id, node) {
        const x = Number(node.pos_x) || 0;
        const y = Number(node.pos_y) || 0;
        const meta = getNodeTypeMeta(node.type);
        const state = this._state();
        const isSelected = state.selectedNodeId === id;
        const isMulti = (state.multiSelection || []).includes(id) && (state.multiSelection || []).length > 1;
        const isEntry = state.entryNodeId === id || (state.skillsData && state.skillsData.entry === id);
        const hasBp = (state.breakpointNodeIds || []).includes(id);
        const isBpHit = state.breakpointHitNodeId === id;
        let runtimeState = null;
        if (isBpHit) runtimeState = 'breakpoint-hit';
        else if ((state.runningNodeIds || []).includes(id)) runtimeState = 'running';
        else if (state.erroredNodes && state.erroredNodes[id]) runtimeState = 'error';
        else if ((state.completedNodeIds || []).includes(id)) runtimeState = 'completed';
        const isInherited = (state.inheritedNodeIds || []).includes(id);

        return svg`
            <g
                class="node"
                transform=${`translate(${x}, ${y})`}
                ?data-selected=${isSelected}
                ?data-multi-selected=${isMulti}
                ?data-inherited=${isInherited}
                data-state=${runtimeState || ''}
                @pointerdown=${(e) => this._onPointerDownNode(e, id)}
                @contextmenu=${(e) => this._onContextMenu(e, 'node', id)}
                @dblclick=${() => this._editor.selectNode({ nodeId: id })}
            >
                <rect class="node-card" x="0" y="0" width=${NODE_W} height=${NODE_H} rx=${NODE_RADIUS} ry=${NODE_RADIUS}></rect>
                <foreignObject x="0" y="0" width=${NODE_W} height=${NODE_H}>
                    <div xmlns="http://www.w3.org/1999/xhtml" class="node-card-content">
                        <div class="node-icon-wrap" data-cat=${meta.category}>
                            <platform-icon name=${meta.icon} size="18"></platform-icon>
                        </div>
                        <div class="node-meta">
                            <div class="node-name">${node.name || id}</div>
                            <div class="node-type">${node.type || ''}</div>
                        </div>
                    </div>
                </foreignObject>
                ${isEntry ? svg`<polygon class="badge-entry" points="0,0 14,0 0,14"></polygon>` : ''}
                ${hasBp ? svg`<circle class="badge-bp-circle" cx=${NODE_W - 8} cy="8" r="5"></circle>` : ''}
                ${isInherited ? svg`<text class="badge-inherited" x="6" y=${NODE_H - 6} font-size="10">↑</text>` : ''}
                <circle
                    class="port in"
                    cx="0" cy=${NODE_H / 2} r=${PORT_R}
                    data-node-id=${id} data-port-side="in"
                ></circle>
                <circle
                    class="port"
                    cx=${NODE_W} cy=${NODE_H / 2} r=${PORT_R}
                    data-node-id=${id} data-port-side="out"
                    @pointerdown=${(e) => this._onPointerDownPort(e, id, 'out')}
                ></circle>
            </g>
        `;
    }

    _renderEdge(edge, i, nodes) {
        const fromId = edge.from_node || edge.from;
        const toId = edge.to_node || edge.to;
        const fromNode = nodes[fromId];
        const toNode = nodes[toId];
        if (!fromNode || !toNode) return svg``;
        const start = this._portCoords(fromNode, 'out');
        const end = this._portCoords(toNode, 'in');
        const condition = edge.condition || '';
        const mid = midpoint(start.x, start.y, end.x, end.y);
        return svg`
            <g class="edge-group">
                <path
                    class="edge"
                    d=${pathFor(start.x, start.y, end.x, end.y)}
                    @contextmenu=${(e) => this._onContextMenu(e, 'edge', String(i))}
                    @pointerenter=${() => { this._hoverEdgeIndex = i; }}
                    @pointerleave=${() => { this._hoverEdgeIndex = -1; }}
                ></path>
                ${condition ? renderEdgeLabel({
                    edgeId: i,
                    x: mid.x,
                    y: mid.y,
                    condition,
                    onClick: () => this.openModal('flows.edge_condition', { edgeIndex: i }),
                }) : ''}
            </g>
        `;
    }

    _renderVirtualEnd(node) {
        const start = this._portCoords(node, 'out');
        const endX = start.x + 60;
        const endY = start.y;
        return svg`
            <g class="edge-group">
                <path class="edge" d=${pathFor(start.x, start.y, endX, endY)}></path>
                <circle class="edge-end-marker" cx=${endX + 8} cy=${endY} r="8"></circle>
                <text class="edge-end-text" x=${endX + 8} y=${endY + 3} text-anchor="middle">END</text>
            </g>
        `;
    }

    _renderSmartGuides() {
        const guides = this._state().smartGuides || [];
        const vb = this._viewBox();
        return guides.map((g, i) => g.axis === 'v'
            ? svg`<line class="smart-guide" x1=${g.at} y1=${vb.y} x2=${g.at} y2=${vb.y + vb.h}></line>`
            : svg`<line class="smart-guide" x1=${vb.x} y1=${g.at} x2=${vb.x + vb.w} y2=${g.at}></line>`);
    }

    _renderStickyNotes() {
        const notes = this._state().stickyNotes || [];
        return notes.map((note) => svg`
            <foreignObject
                x=${note.x} y=${note.y}
                width=${note.width || STICKY_W} height=${note.height || STICKY_H}
                @pointerdown=${(e) => this._onStickyDragStart(e, note)}
            >
                <flows-sticky-note
                    xmlns="http://www.w3.org/1999/xhtml"
                    note-id=${note.id}
                    .text=${note.text || ''}
                    color-token=${note.color_token || 'warning_bg'}
                    .width=${note.width || STICKY_W}
                    .height=${note.height || STICKY_H}
                    @change=${this._onStickyChange}
                    @remove=${this._onStickyRemove}
                    @resize-start=${(e) => this._onStickyResizeStart(e, note)}
                ></flows-sticky-note>
            </foreignObject>
        `);
    }

    _renderSelectionRect() {
        if (!this._selectionRect) return '';
        const r = this._selectionRect;
        const x = Math.min(r.x0, r.x1);
        const y = Math.min(r.y0, r.y1);
        const w = Math.abs(r.x1 - r.x0);
        const h = Math.abs(r.y1 - r.y0);
        return svg`<rect class="selection-box" x=${x} y=${y} width=${w} height=${h}></rect>`;
    }

    _renderContextMenu() {
        const menu = this._state().contextMenu;
        if (!menu) return '';
        return html`
            <flows-canvas-context-menu
                .x=${menu.x}
                .y=${menu.y}
                target=${menu.target}
                target-id=${menu.targetId || ''}
                @action=${this._onContextMenuAction}
                @close=${() => this._editor.closeContextMenu({})}
            ></flows-canvas-context-menu>
        `;
    }

    render() {
        const state = this._state();
        const skillsData = state.skillsData || { nodes: {}, edges: [] };
        const nodes = skillsData.nodes || {};
        const edges = Array.isArray(skillsData.edges) ? skillsData.edges : [];
        const activeTool = state.activeTool || 'select';
        const vb = this._viewBox();
        const vbStr = `${vb.x} ${vb.y} ${vb.w} ${vb.h}`;
        const panActive = Boolean(this._pan);

        const fromIds = new Set(edges.map((e) => e.from_node || e.from));
        const orphanNodes = Object.entries(nodes).filter(([id]) => !fromIds.has(id));

        return html`
            <svg
                class="canvas-host"
                viewBox=${vbStr}
                data-tool=${activeTool}
                ?data-pan-active=${panActive}
                @wheel=${this._onWheel}
                @pointerdown=${this._onPointerDownBackground}
                @pointermove=${this._onPointerMove}
                @pointerup=${this._onPointerUp}
                @dragover=${this._onDragOver}
                @drop=${this._onDrop}
                @contextmenu=${(e) => this._onContextMenu(e, 'background', '')}
            >
                <defs>
                    <pattern id="canvas-grid" width=${GRID_STEP} height=${GRID_STEP} patternUnits="userSpaceOnUse">
                        <path d="M 1 0 L 1 1 L 0 1" class="grid-pattern" stroke-width="0"></path>
                        <circle cx="0" cy="0" r="0.8" class="grid-pattern"></circle>
                    </pattern>
                </defs>
                <rect x=${vb.x} y=${vb.y} width=${vb.w} height=${vb.h} fill="url(#canvas-grid)"></rect>

                <g class="sticky-layer">${this._renderStickyNotes()}</g>

                <g class="edges-layer">
                    ${edges.map((edge, i) => this._renderEdge(edge, i, nodes))}
                    ${orphanNodes.map(([id, n]) => this._renderVirtualEnd(n))}
                    ${this._connection
                        ? svg`<path class="edge-temp" d=${pathFor(this._connection.x1, this._connection.y1, this._connection.x2, this._connection.y2)}></path>`
                        : ''}
                </g>

                <g class="guides-layer">${this._renderSmartGuides()}</g>

                <g class="nodes-layer">
                    ${Object.entries(nodes).map(([id, node]) => this._renderNode(id, node))}
                </g>

                ${this._renderSelectionRect()}
            </svg>
            ${this._renderContextMenu()}
        `;
    }
}

customElements.define('flows-flow-canvas', FlowsFlowCanvas);
