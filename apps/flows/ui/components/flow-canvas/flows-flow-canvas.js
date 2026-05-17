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
 *   - useOp('flows/editor').state.{runningEdgeIndices,completedEdgeIndices,failedEdgeIndices} — edge_executed / node_*;
 *   - useOp('flows/editor').state.breakpointNodeIds / breakpointHitNodeId — flows/breakpoint/hit;
 *   - useOp('flows/editor').state.entryNodeId — entry-нода;
 *   - useOp('flows/editor').state.stickyNotes / smartGuides / smartGuidesEnabled.
 *
 * UX:
 *   - drag нод pointermove с snap-to-guide;
 *   - drag-create узла из <flows-node-types-sidebar>:
 *     `application/x-flow-node-type` для нод, `application/x-flow-resource-type` для ресурсов
 *     (drop на канву / порт / тело ноды; ресурс на ноде — flow resource + ссылка в node.resources;
 *      ресурс на пустой канве — flow resource + нода type `resource` с привязкой);
 *   - draw edges с output-порта на input-порт;
 *   - zoom: ctrl + wheel; pan: пробел/middle-mouse-drag/tool=pan;
 *   - select: click; multi-select: shift+drag по фону → bounding-rect;
 *   - hotkeys (вешаются на document): Del/Ctrl+A/Ctrl+D/F2/Enter/Esc/стрелки/Shift+S;
 *   - правый клик → диспатч `openContextMenu` через slice; <flows-canvas-context-menu>
 *     рендерится оверлеем и эмитит `action`/`close`.
 */

import { html, css, svg } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveUiIconFile } from '@platform/lib/utils/file-icons.js';
import { getNodeTypeMeta, getCategoryToken } from '../../constants/node-icons.js';
import { renderEdgeLabel } from './flows-edge-label.js';
import './flows-canvas-context-menu.js';
import './flows-sticky-note.js';
import '../common/flows-code-language-icon.js';
import {
    asNumber,
    asString,
    asArray,
    asObject,
    isPlainObject,
    getBranchData,
    getBranchNodes,
    getBranchEdges,
    getEdgeEndpoints,
    colorOrDefault,
} from '../../_helpers/flows-resolvers.js';
import { parseMcpToolIdToNodeConfig } from '../../_helpers/flows-mcp-tool-registry.js';
import {
    FLOW_NODE_W as NODE_W,
    FLOW_NODE_H as NODE_H,
    getNodeCanvasHeight,
    computeFitViewBox,
    FLOWS_EDITOR_DEFAULT_VIEWBOX,
} from '../../_helpers/flows-viewbox.js';
import {
    normalizedLlmToolsForCanvas,
    getToolRefVisualMeta,
    getToolLabel,
    inferToolRefLanguage,
    MAX_CHIPS_SHOWN,
} from '../../_helpers/flows-tool-visual.js';
import { getBlankCodeNodeConfig } from '../../_helpers/code-node-defaults.js';
import { getBlankExternalApiNodeConfig } from '../../_helpers/flows-external-api-defaults.js';
const NODE_RADIUS = 12;
const PORT_R = 6;
const SNAP_THRESHOLD = 4;
const GRID_STEP = 24;
const STICKY_W = 200;
const STICKY_H = 140;
const STICKY_COLLAPSED_H = 32;

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

function rectBoundaryAnchor(rect, target) {
    const cx = rect.x + rect.w / 2;
    const cy = rect.y + rect.h / 2;
    const dx = target.x - cx;
    const dy = target.y - cy;
    if (dx === 0 && dy === 0) return { x: cx, y: cy };
    const sx = dx === 0 ? Infinity : (rect.w / 2) / Math.abs(dx);
    const sy = dy === 0 ? Infinity : (rect.h / 2) / Math.abs(dy);
    const scale = Math.min(sx, sy);
    return {
        x: cx + dx * scale,
        y: cy + dy * scale,
    };
}

function attachPathFor(srcX, srcY, dstX, dstY) {
    const dx = dstX - srcX;
    const dy = dstY - srcY;
    if (Math.abs(dx) >= Math.abs(dy)) {
        const dir = dx >= 0 ? 1 : -1;
        const c = Math.max(36, Math.abs(dx) * 0.45);
        return `M ${srcX} ${srcY} C ${srcX + dir * c} ${srcY} ${dstX - dir * c} ${dstY} ${dstX} ${dstY}`;
    }
    const dir = dy >= 0 ? 1 : -1;
    const c = Math.max(36, Math.abs(dy) * 0.45);
    return `M ${srcX} ${srcY} C ${srcX} ${srcY + dir * c} ${dstX} ${dstY - dir * c} ${dstX} ${dstY}`;
}

export class FlowsFlowCanvas extends PlatformElement {
    static properties = {
        flowId: { type: String },
        branchId: { type: String },
        _drag: { state: true },
        _connection: { state: true },
        _selectionRect: { state: true },
        _spacePressed: { state: true },
        _pan: { state: true },
        _hoverEdgeIndex: { state: true },
        _paletteDndActive: { state: true },
        _paletteDndHoverNodeId: { state: true },
        _paletteDndMode: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; flex: 1; min-width: 0; min-height: 0; position: relative; overflow: hidden; }
            svg.canvas-host {
                width: 100%; height: 100%;
                user-select: none;
                cursor: grab;
                background: var(--bg-elevated);
            }
            svg.canvas-host[data-pan-active] { cursor: grabbing; }

            .grid-pattern path {
                fill: var(--border-subtle);
                opacity: 0.4;
            }

            /* Node */
            g.node {
                --node-accent: var(--accent);
                --node-surface: color-mix(in oklab, var(--glass-solid-strong) 88%, var(--node-accent) 12%);
                --node-border: color-mix(in oklab, var(--glass-border-medium) 70%, var(--node-accent) 30%);
                --node-glow: color-mix(in srgb, var(--node-accent) 34%, transparent);
                transition: opacity var(--motion-duration-micro) var(--motion-ease-standard);
            }
            g.node[data-inherited] { opacity: 0.78; }
            g.node .node-aura {
                fill: var(--node-accent);
                opacity: 0;
                pointer-events: none;
                transition: opacity var(--motion-duration-enter) var(--motion-ease-standard);
            }
            g.node .node-card {
                fill: var(--node-surface);
                stroke: var(--node-border);
                stroke-width: 1.25;
                filter: drop-shadow(0 10px 24px rgba(0, 0, 0, 0.18));
                transition:
                    stroke var(--motion-duration-micro) var(--motion-ease-standard),
                    filter var(--motion-duration-micro) var(--motion-ease-standard),
                    fill var(--motion-duration-micro) var(--motion-ease-standard);
                vector-effect: non-scaling-stroke;
            }
            g.node .node-sheen {
                fill: rgba(255, 255, 255, 0.24);
                opacity: 0.42;
                pointer-events: none;
            }
            g.node:hover .node-aura {
                opacity: 0.11;
            }
            g.node:hover .node-card {
                stroke: color-mix(in oklab, var(--node-accent) 58%, var(--glass-border-strong) 42%);
                filter:
                    drop-shadow(0 14px 30px rgba(0, 0, 0, 0.24))
                    drop-shadow(0 0 14px var(--node-glow));
            }
            g.node[data-inherited] .node-card {
                stroke-dasharray: 5 4;
            }
            g.node[data-selected] .node-aura,
            g.node[data-multi-selected] .node-aura {
                opacity: 0.18;
            }
            g.node[data-selected] .node-card,
            g.node[data-multi-selected] .node-card {
                stroke: var(--node-accent);
                stroke-width: 2;
                filter:
                    drop-shadow(0 16px 34px rgba(0, 0, 0, 0.26))
                    drop-shadow(0 0 18px var(--node-glow));
            }
            g.node[data-multi-selected] .node-card {
                stroke-dasharray: 6 3;
            }
            g.node[data-state="running"] .node-card {
                stroke: var(--info);
                stroke-width: 2;
                animation: nodePulseRunning 1.4s ease-in-out infinite;
                filter:
                    drop-shadow(0 16px 34px rgba(0, 0, 0, 0.26))
                    drop-shadow(0 0 18px color-mix(in srgb, var(--info) 36%, transparent));
            }
            g.node[data-state="completed"] .node-card {
                stroke: var(--success);
                stroke-width: 1.75;
            }
            g.node[data-state="error"] .node-card {
                stroke: var(--error);
                stroke-width: 2;
                filter:
                    drop-shadow(0 16px 34px rgba(0, 0, 0, 0.24))
                    drop-shadow(0 0 16px color-mix(in srgb, var(--error) 34%, transparent));
            }
            g.node[data-state="breakpoint-hit"] .node-card {
                stroke: var(--warning);
                stroke-width: 2;
                animation: nodePulseRunning 1s ease-in-out infinite;
                filter:
                    drop-shadow(0 16px 34px rgba(0, 0, 0, 0.24))
                    drop-shadow(0 0 16px color-mix(in srgb, var(--warning) 34%, transparent));
            }

            @keyframes nodePulseRunning {
                0%, 100% { stroke-opacity: 1; }
                50%      { stroke-opacity: 0.45; }
            }

            .node-icon-wrap {
                width: 38px;
                height: 38px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 10px;
                border: 1px solid color-mix(in oklab, var(--node-accent) 24%, var(--glass-border-subtle));
                background: color-mix(in oklab, var(--node-accent) 13%, var(--glass-solid-medium));
                color: var(--node-accent);
                box-sizing: border-box;
                box-shadow:
                    inset 0 1px 0 rgba(255, 255, 255, 0.14),
                    0 4px 12px color-mix(in srgb, var(--node-accent) 16%, transparent);
                flex: 0 0 auto;
                overflow: hidden;
                position: relative;
            }
            .node-icon-wrap[data-language-icon] {
                background: color-mix(in oklab, var(--glass-solid-strong) 84%, var(--node-accent) 16%);
            }
            .canvas-icon {
                width: var(--canvas-icon-size, 16px);
                height: var(--canvas-icon-size, 16px);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex: 0 0 auto;
                line-height: 1;
            }
            .canvas-icon-img {
                width: 100%;
                height: 100%;
                display: block;
                object-fit: contain;
            }
            .canvas-icon-img[data-failed] {
                display: none;
            }
            .canvas-icon-fallback {
                width: 100%;
                height: 100%;
                display: none;
                align-items: center;
                justify-content: center;
                color: currentColor;
                font-size: 11px;
                font-weight: var(--font-bold);
                letter-spacing: 0;
            }
            .canvas-icon-img[data-failed] + .canvas-icon-fallback {
                display: inline-flex;
            }
            .node-card-content {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: 10px 12px 9px 15px;
                width: 100%; height: 100%;
                box-sizing: border-box;
                font-family: var(--font-sans);
            }
            .node-card-content.has-tools {
                flex-direction: column;
                align-items: stretch;
                gap: 7px;
            }
            .node-card-main {
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-3);
                min-width: 0;
                flex: 1;
                min-height: 44px;
            }
            .node-tools-row {
                display: flex;
                flex-direction: row;
                flex-wrap: wrap;
                align-items: center;
                gap: 6px;
                flex-shrink: 0;
                padding: 0 0 0 50px;
            }
            .node-tool-chip {
                --tool-accent: var(--node-accent);
                width: 28px;
                height: 28px;
                border-radius: var(--radius-full);
                border: 1px solid color-mix(in oklab, var(--tool-accent) 22%, var(--glass-border-subtle));
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                margin: 0;
                cursor: pointer;
                flex-shrink: 0;
                box-sizing: border-box;
                color: var(--tool-accent);
                background: color-mix(in oklab, var(--tool-accent) 12%, var(--glass-solid-medium));
                box-shadow:
                    0 2px 8px rgba(0, 0, 0, 0.12),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
                transition:
                    border-color var(--motion-duration-micro) var(--motion-ease-standard),
                    box-shadow var(--motion-duration-micro) var(--motion-ease-standard),
                    transform var(--motion-duration-micro) var(--motion-ease-standard);
            }
            .node-tool-chip:hover {
                transform: translateY(-1px);
                border-color: color-mix(in oklab, var(--tool-accent) 46%, var(--glass-border-strong));
                box-shadow:
                    0 5px 14px color-mix(in srgb, var(--tool-accent) 24%, transparent),
                    inset 0 1px 0 rgba(255, 255, 255, 0.12);
            }
            .node-tool-chip[data-cat="core"] { --tool-accent: var(--accent); }
            .node-tool-chip[data-cat="code"] { --tool-accent: var(--success); }
            .node-tool-chip[data-cat="integrations"] { --tool-accent: var(--info); }
            .node-tool-chip[data-cat="flow"] { --tool-accent: var(--accent-secondary); }
            .node-tool-chip[data-cat="hitl"] { --tool-accent: var(--warning); }
            .node-tool-chip[data-language-icon] {
                color: inherit;
            }
            .node-tool-chip[data-language-icon] flows-code-language-icon {
                flex: 0 0 auto;
            }
            .node-tools-more {
                font-size: var(--text-xs);
                color: color-mix(in oklab, var(--node-accent) 46%, var(--text-tertiary));
                padding: 0 5px;
                flex-shrink: 0;
                font-weight: var(--font-semibold);
            }
            .node-meta {
                display: flex;
                flex-direction: column;
                min-width: 0;
                flex: 1;
                gap: 4px;
            }
            .node-name {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.2;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
            }
            .node-type {
                align-self: flex-start;
                max-width: 100%;
                box-sizing: border-box;
                padding: 2px 7px;
                border-radius: var(--radius-full);
                border: 1px solid color-mix(in oklab, var(--node-accent) 18%, var(--glass-border-subtle));
                background: color-mix(in oklab, var(--node-accent) 9%, transparent);
                color: color-mix(in oklab, var(--node-accent) 44%, var(--text-secondary));
                font-size: 10px;
                font-weight: var(--font-semibold);
                line-height: 1.15;
                letter-spacing: 0;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            /* Badges */
            .badge-bp-circle {
                fill: var(--warning);
                stroke: var(--bg-primary);
                stroke-width: 1.5;
            }
            .badge-inherited {
                fill: var(--text-tertiary);
            }

            /* Fan-in badge on input port (>=2 incoming edges) */
            .badge-fanin-bg {
                fill: var(--accent);
                stroke: var(--bg-primary);
                stroke-width: 2;
                cursor: pointer;
                transition: filter 120ms;
            }
            .badge-fanin-bg[data-policy="all"] {
                fill: var(--accent-hover);
            }
            .badge-fanin-bg:hover {
                filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.25));
            }
            .badge-fanin-icon {
                fill: var(--bg-primary);
                pointer-events: none;
            }

            /* Ports */
            .port {
                fill: var(--node-accent, var(--accent));
                stroke: var(--glass-solid-strong);
                stroke-width: 2;
                cursor: crosshair;
                filter:
                    drop-shadow(0 2px 6px rgba(0, 0, 0, 0.22))
                    drop-shadow(0 0 8px color-mix(in srgb, var(--node-accent, var(--accent)) 26%, transparent));
                transform-box: fill-box;
                transform-origin: center;
                transition:
                    fill var(--motion-duration-micro) var(--motion-ease-standard),
                    transform var(--motion-duration-micro) var(--motion-ease-standard),
                    filter var(--motion-duration-micro) var(--motion-ease-standard);
                vector-effect: non-scaling-stroke;
            }
            .port:hover {
                fill: var(--accent-hover);
                transform: scale(1.18);
            }
            .port.in {
                fill: color-mix(in oklab, var(--node-accent, var(--accent)) 38%, var(--text-tertiary));
            }
            .port.in:hover {
                fill: var(--node-accent, var(--accent));
            }

            /* Edges */
            .edge {
                fill: none;
                stroke: color-mix(in oklab, var(--text-tertiary) 78%, var(--accent) 22%);
                stroke-width: 2;
                stroke-linecap: round;
                pointer-events: none;
                filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.12));
                transition:
                    stroke var(--motion-duration-micro) var(--motion-ease-standard),
                    stroke-width var(--motion-duration-micro) var(--motion-ease-standard),
                    filter var(--motion-duration-micro) var(--motion-ease-standard);
                vector-effect: non-scaling-stroke;
            }
            .edge-hit {
                fill: none;
                stroke: transparent;
                stroke-width: 18;
                cursor: pointer;
                pointer-events: stroke;
            }
            .edge-group:hover .edge {
                stroke: var(--accent);
                stroke-width: 3;
                filter:
                    drop-shadow(0 3px 8px rgba(0, 0, 0, 0.18))
                    drop-shadow(0 0 10px color-mix(in srgb, var(--accent) 24%, transparent));
            }
            .edge:hover, .edge[data-hover] {
                stroke: var(--accent);
                stroke-width: 3;
            }
            .edge[data-selected] {
                stroke: var(--accent);
                stroke-width: 3;
            }
            .edge.inherited {
                stroke-dasharray: 6 4;
                opacity: 0.6;
            }
            .edge[data-run-state='running'] {
                stroke: var(--info);
                stroke-width: 2.5;
                opacity: 1;
                animation: canvasEdgeRunPulse 1.2s ease-in-out infinite;
            }
            .edge[data-run-state='completed'] {
                stroke: var(--success);
                stroke-width: 2.5;
                opacity: 1;
            }
            .edge[data-run-state='failed'] {
                stroke: var(--error);
                stroke-width: 2.5;
                opacity: 1;
            }
            @keyframes canvasEdgeRunPulse {
                0%, 100% { stroke-opacity: 1; }
                50% { stroke-opacity: 0.55; }
            }
            .edge-end-marker {
                fill: var(--text-tertiary);
                opacity: 0.7;
            }
            .edge-end-text {
                font-size: 12px;
                font-weight: 700;
                font-family: var(--font-mono);
                fill: var(--bg-primary);
                pointer-events: none;
            }
            .edge-start-marker {
                fill: var(--accent);
                opacity: 0.95;
            }
            .edge-start-text {
                font-size: 10px;
                font-weight: 700;
                font-family: var(--font-mono);
                fill: var(--bg-primary);
                pointer-events: none;
                letter-spacing: 0;
            }
            .edge-temp {
                fill: none;
                stroke: var(--accent);
                stroke-width: 2;
                stroke-dasharray: 4 4;
                stroke-linecap: round;
                pointer-events: none;
            }
            .edge-label .label-bg {
                fill: color-mix(in oklab, var(--glass-solid-strong) 88%, var(--accent) 12%);
                stroke: color-mix(in oklab, var(--glass-border-subtle) 68%, var(--accent) 32%);
                stroke-width: 1;
                filter: drop-shadow(0 6px 12px rgba(0, 0, 0, 0.16));
            }
            .edge-label .label-text {
                font-family: var(--font-mono);
                font-size: 10px;
                font-weight: var(--font-semibold);
                letter-spacing: 0;
                fill: color-mix(in oklab, var(--accent) 38%, var(--text-secondary));
                pointer-events: none;
            }
            .edge-label { cursor: pointer; pointer-events: all; }
            .edge-label .label-bg { pointer-events: all; }
            .edge-label--empty .label-text { fill: var(--text-tertiary); }
            .edge-label:hover .label-bg {
                stroke: var(--accent);
                filter:
                    drop-shadow(0 8px 16px rgba(0, 0, 0, 0.18))
                    drop-shadow(0 0 10px color-mix(in srgb, var(--accent) 22%, transparent));
            }

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

            /* Sticky → node attach line */
            .sticky-attach-line {
                fill: none;
                stroke: color-mix(in oklab, var(--accent-secondary) 62%, var(--text-tertiary));
                stroke-width: 1.25;
                stroke-linecap: round;
                stroke-dasharray: 6 6;
                opacity: 0.52;
                pointer-events: none;
                vector-effect: non-scaling-stroke;
            }

            /* Link mode: highlight all nodes as clickable */
            svg.canvas-host[data-link-mode] g.node .node-card {
                stroke: var(--accent);
                stroke-dasharray: 4 3;
            }
            svg.canvas-host[data-link-mode] g.node:hover .node-card {
                stroke: var(--accent-hover);
                filter: drop-shadow(0 0 12px var(--accent));
            }
            svg.canvas-host[data-link-mode] { cursor: crosshair; }

            svg.canvas-host[data-palette-dnd-active] { cursor: copy; }
            g.node[data-palette-drop-target] .node-card {
                stroke: var(--success);
                stroke-width: 2.5;
                filter: drop-shadow(0 0 12px color-mix(in srgb, var(--success) 38%, transparent));
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._drag = null;
        this._connection = null;
        this._selectionRect = null;
        this._spacePressed = false;
        this._pan = null;
        this._hoverEdgeIndex = -1;
        this._paletteDndActive = false;
        this._paletteDndHoverNodeId = null;
        this._paletteDndMode = null;
        this._editor = this.useOp('flows/editor');
        this._bulkDelete = this.useOp('flows/editor_bulk_delete');
        this._stickyUpsert = this.useOp('flows/sticky_note_upsert');
        this._onDocKeyDown = this._onDocKeyDown.bind(this);
        this._onDocKeyUp = this._onDocKeyUp.bind(this);
        this._stickyResize = null;
        this._stickyLinkMode = null;
        this._pointerDownAt = null;
        this._pointerMoved = false;
        this._lastAutoFitKey = null;
        this._onDocumentDragEnd = this._onDocumentDragEnd.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('keydown', this._onDocKeyDown);
        document.addEventListener('keyup', this._onDocKeyUp);
        document.addEventListener('dragend', this._onDocumentDragEnd);
    }

    disconnectedCallback() {
        document.removeEventListener('keydown', this._onDocKeyDown);
        document.removeEventListener('keyup', this._onDocKeyUp);
        document.removeEventListener('dragend', this._onDocumentDragEnd);
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        const state = this._editor.state;
        if (!state) return;
        const fid = state.flowId;
        if (typeof fid !== 'string' || fid.length === 0) return;
        const sid = typeof state.currentBranchId === 'string' && state.currentBranchId.length > 0
            ? state.currentBranchId
            : 'base';
        const key = `${fid}:${sid}`;
        if (this._lastAutoFitKey === key) return;
        this._lastAutoFitKey = key;
        requestAnimationFrame(() => {
            this._fitView();
        });
    }

    _state() { return asObject(this._editor.state); }
    _branchData() { return getBranchData(this._state()); }
    _nodes() { return getBranchNodes(this._state()); }
    _edges() { return getBranchEdges(this._state()); }
    _viewBox() {
        const vb = this._state().viewBox;
        return isPlainObject(vb) ? vb : { x: 0, y: 0, w: 1600, h: 1000 };
    }

    _iconAssetSrc(name) {
        const file = resolveUiIconFile(name);
        return `/static/core/assets/icons/${encodeURIComponent(file)}.svg`;
    }

    _iconFallbackLabel(name) {
        if (name === 'python') return 'Py';
        if (name === 'javascript') return 'JS';
        if (name === 'typescript') return 'TS';
        if (name === 'go') return 'Go';
        if (name === 'csharp') return 'C#';
        if (name === 'code') return '<>';
        if (name === 'tool') return 'T';
        return '';
    }

    _onCanvasIconError(event) {
        const target = event.currentTarget;
        if (target instanceof HTMLImageElement) {
            target.dataset.failed = 'true';
        }
    }

    _renderCanvasIcon(name, size, fallbackLabel = '') {
        const iconName = typeof name === 'string' && name.length > 0 ? name : 'tool';
        const label = fallbackLabel.length > 0 ? fallbackLabel : this._iconFallbackLabel(iconName);
        return html`
            <span class="canvas-icon" data-icon=${iconName} style=${`--canvas-icon-size: ${size}px`}>
                <img
                    class="canvas-icon-img"
                    src=${this._iconAssetSrc(iconName)}
                    alt=""
                    draggable="false"
                    @error=${this._onCanvasIconError}
                >
                <span class="canvas-icon-fallback">${label}</span>
            </span>
        `;
    }

    _renderCodeLanguageIcon(language, size) {
        return html`<flows-code-language-icon language=${language} size=${size}></flows-code-language-icon>`;
    }

    _portCoords(node, side) {
        const px = asNumber(node.pos_x);
        const x = side === 'in' ? px : px + NODE_W;
        const h = getNodeCanvasHeight(node);
        const y = asNumber(node.pos_y) + h / 2;
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

    _inferPaletteDndMode(e) {
        const types = e.dataTransfer?.types;
        if (!types) return null;
        const hasNode = types.includes('application/x-flow-node-type');
        const hasRes = types.includes('application/x-flow-resource-type');
        if (hasRes) return 'resource';
        if (hasNode) return 'node';
        return null;
    }

    _clearPaletteDndVisual() {
        if (!this._paletteDndActive && this._paletteDndHoverNodeId == null && this._paletteDndMode == null) {
            return;
        }
        this._paletteDndActive = false;
        this._paletteDndHoverNodeId = null;
        this._paletteDndMode = null;
        this.requestUpdate();
    }

    _onDocumentDragEnd() {
        this._clearPaletteDndVisual();
    }

    _findNodeAtLocal(local) {
        const nodes = this._nodes();
        let hit = null;
        for (const [id, node] of Object.entries(nodes)) {
            const x = asNumber(node.pos_x);
            const y = asNumber(node.pos_y);
            const w = NODE_W;
            const h = getNodeCanvasHeight(node);
            if (local.x >= x && local.x <= x + w && local.y >= y && local.y <= y + h) {
                hit = id;
            }
        }
        return hit;
    }

    /* ===== Document hotkeys ===== */
    _onDocKeyDown(e) {
        const path = typeof e.composedPath === 'function' ? e.composedPath() : [];
        const isEditable = path.some((el) => {
            if (!(el instanceof HTMLElement)) return false;
            const tag = el.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
            if (el.isContentEditable) return true;
            return false;
        });
        if (isEditable) return;
        if (e.code === 'Space') {
            this._spacePressed = true;
            return;
        }
        const cmd = e.metaKey || e.ctrlKey;
        if ((e.key === 'Delete' || e.key === 'Backspace')) {
            const hasSelection = Boolean(this._state().selectedNodeId) || asArray(this._state().multiSelection).length > 0;
            if (!hasSelection) return;
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
            if (this._stickyLinkMode) {
                this._stickyLinkMode = null;
                this.toast('flows:canvas.sticky_note.link_mode_cancelled', { type: 'info' });
                this.requestUpdate();
                return;
            }
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
        const ids = asArray(this._state().multiSelection);
        const single = this._state().selectedNodeId;
        const targetIds = ids.length > 0 ? ids : (single ? [single] : []);
        if (targetIds.length === 0) return;
        if (!this.flowId) return;
        const inheritedIds = asArray(this._state().inheritedNodeIds);
        const deletableIds = targetIds.filter((id) => !inheritedIds.includes(id));
        if (deletableIds.length === 0) {
            this.toast('flows:toast.cant_delete_inherited', { type: 'warning' });
            return;
        }
        if (deletableIds.length < targetIds.length) {
            this.toast('flows:toast.cant_delete_inherited', { type: 'warning' });
        }
        void this._bulkDelete.run({ flow_id: this.flowId, node_ids: deletableIds });
        const data = this._branchData();
        const newNodes = { ...asObject(data.nodes) };
        for (const id of deletableIds) delete newNodes[id];
        const newEdges = asArray(data.edges).filter((edge) => {
            const { from, to } = getEdgeEndpoints(edge);
            return !deletableIds.includes(from) && !deletableIds.includes(to);
        });
        const next = { ...data, nodes: newNodes, edges: newEdges };
        this._editor.updateBranchData({ data: next });
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
        const ids = asArray(this._state().multiSelection);
        const single = this._state().selectedNodeId;
        const targetIds = ids.length > 0 ? ids : (single ? [single] : []);
        if (targetIds.length === 0) return;
        const data = this._branchData();
        const nodes = { ...asObject(data.nodes) };
        const newIds = [];
        for (const id of targetIds) {
            const orig = nodes[id];
            if (!orig) continue;
            const copyId = genId('n');
            nodes[copyId] = {
                ...orig,
                pos_x: asNumber(orig.pos_x) + 30,
                pos_y: asNumber(orig.pos_y) + 30,
            };
            newIds.push(copyId);
        }
        const next = { ...data, nodes };
        this._editor.updateBranchData({ data: next });
        this._editor.pushHistory({ snapshot: next });
        this._editor.setDirty({ dirty: true });
        this._editor.setMultiSelection({ nodeIds: newIds });
    }

    _moveSelectionByArrow(key) {
        const ids = asArray(this._state().multiSelection);
        const single = this._state().selectedNodeId;
        const targetIds = ids.length > 0 ? ids : (single ? [single] : []);
        if (targetIds.length === 0) return;
        const dx = key === 'ArrowLeft' ? -10 : key === 'ArrowRight' ? 10 : 0;
        const dy = key === 'ArrowUp' ? -10 : key === 'ArrowDown' ? 10 : 0;
        const data = this._branchData();
        const nodes = { ...asObject(data.nodes) };
        for (const id of targetIds) {
            if (!nodes[id]) continue;
            nodes[id] = {
                ...nodes[id],
                pos_x: asNumber(nodes[id].pos_x) + dx,
                pos_y: asNumber(nodes[id].pos_y) + dy,
            };
        }
        const next = { ...data, nodes };
        this._editor.updateBranchData({ data: next });
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
        this._persistStickyNotes([...asArray(this._state().stickyNotes), note]);
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
        this._pointerDownAt = { x: e.clientX, y: e.clientY, button: e.button };
        this._pointerMoved = false;
        if (e.button !== 0) return;
        e.stopPropagation();
        if (this._stickyLinkMode) {
            const linkNoteId = this._stickyLinkMode.noteId;
            this._attachStickyToNode(linkNoteId, nodeId);
            return;
        }
        const node = this._nodes()[nodeId];
        if (!node) return;
        const nodes = this._nodes();
        const currentMulti = asArray(this._state().multiSelection);
        const isInMulti = currentMulti.includes(nodeId);
        const draggedIds = isInMulti && currentMulti.length > 0 ? currentMulti : [nodeId];
        const offsets = {};
        for (const id of draggedIds) {
            if (!nodes[id]) continue;
            offsets[id] = { x: asNumber(nodes[id].pos_x), y: asNumber(nodes[id].pos_y) };
        }
        this._drag = {
            type: 'node',
            primaryId: nodeId,
            ids: draggedIds,
            offsets,
            startX: e.clientX, startY: e.clientY,
            shiftKey: e.shiftKey,
        };
        this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(e.pointerId);
    }

    _onPointerDownPort(e, nodeId, side) {
        this._pointerDownAt = { x: e.clientX, y: e.clientY, button: e.button };
        this._pointerMoved = false;
        if (e.button !== 0 || side !== 'out') return;
        e.stopPropagation();
        const node = this._nodes()[nodeId];
        if (!node || this._isResourceNode(node)) return;
        const start = this._portCoords(node, 'out');
        this._connection = { fromNode: nodeId, x1: start.x, y1: start.y, x2: start.x, y2: start.y };
        this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(e.pointerId);
    }

    _onPointerDownBackground(e) {
        this._pointerDownAt = { x: e.clientX, y: e.clientY, button: e.button };
        this._pointerMoved = false;
        if (e.button === 0 && e.shiftKey) {
            const local = this._localPoint(e.clientX, e.clientY);
            this._selectionRect = { x0: local.x, y0: local.y, x1: local.x, y1: local.y };
            this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(e.pointerId);
            return;
        }
        if (e.button === 0 || e.button === 1) {
            e.preventDefault();
            const vb = this._viewBox();
            this._pan = { startClientX: e.clientX, startClientY: e.clientY, origVB: { ...vb } };
            this.renderRoot.querySelector('svg.canvas-host').setPointerCapture(e.pointerId);
        }
    }

    _onPointerMove(e) {
        if (this._pointerDownAt && !this._pointerMoved) {
            const dx = e.clientX - this._pointerDownAt.x;
            const dy = e.clientY - this._pointerDownAt.y;
            if (dx * dx + dy * dy > 16) this._pointerMoved = true;
        }
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
            const data = this._branchData();
            const nodes = { ...asObject(data.nodes) };
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
            this._editor.updateBranchData({ data: { ...data, nodes } });
            this._editor.setSmartGuides({ guides });
            return;
        }
        if (this._drag?.type === 'sticky') {
            const local = this._localPoint(e.clientX, e.clientY);
            const startLocal = this._localPoint(this._drag.startX, this._drag.startY);
            const dx = local.x - startLocal.x;
            const dy = local.y - startLocal.y;
            const next = asArray(this._state().stickyNotes).map((n) => n.id === this._drag.noteId
                ? { ...n, x: this._drag.origX + dx, y: this._drag.origY + dy }
                : n);
            const moved = next.find((n) => n.id === this._drag.noteId);
            if (moved) this._editor.updateStickyNote({ note: moved });
            this._drag.lastNotes = next;
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
            const notes = asArray(this._state().stickyNotes).map((n) => n.id === this._stickyResize.noteId
                ? { ...n, width: Math.max(80, this._stickyResize.origW + dx), height: Math.max(60, this._stickyResize.origH + dy) }
                : n);
            this._editor.updateStickyNote({ note: notes.find((n) => n.id === this._stickyResize.noteId) });
            this._stickyResize.lastNotes = notes;
        }
    }

    _onPointerUp(e) {
        if (this._pan) {
            const wasClick = !this._pointerMoved && this._pan.origVB && this._pointerDownAt?.button === 0;
            this._pan = null;
            if (wasClick) {
                this._editor.setMultiSelection({ nodeIds: [] });
                this._editor.closePanel({});
            }
            this._pointerDownAt = null;
            return;
        }
        if (this._drag?.type === 'sticky') {
            const drag = this._drag;
            this._drag = null;
            if (this._pointerMoved) {
                const notes = Array.isArray(drag.lastNotes) ? drag.lastNotes : asArray(this._state().stickyNotes);
                this._persistStickyNotes(notes);
            }
            this._pointerDownAt = null;
            return;
        }
        if (this._drag?.type === 'node') {
            const drag = this._drag;
            this._drag = null;
            this._editor.setSmartGuides({ guides: [] });
            if (this._pointerMoved) {
                this._editor.pushHistory({ snapshot: { ...this._branchData() } });
                this._editor.setDirty({ dirty: true });
            } else {
                const nodeId = drag.primaryId;
                const currentMulti = asArray(this._state().multiSelection);
                if (drag.shiftKey) {
                    const next = currentMulti.includes(nodeId)
                        ? currentMulti.filter((x) => x !== nodeId)
                        : [...currentMulti, nodeId];
                    this._editor.setMultiSelection({ nodeIds: next });
                } else {
                    this._editor.selectNode({ nodeId });
                }
            }
            this._pointerDownAt = null;
            return;
        }
        if (this._connection) {
            const target = this.renderRoot.elementFromPoint(e.clientX, e.clientY);
            const targetNodeId = target?.dataset?.nodeId;
            const targetSide = target?.dataset?.portSide;
            if (targetNodeId && targetSide === 'in' && targetNodeId !== this._connection.fromNode) {
                const nodes = this._nodes();
                const fromNodeId = this._connection.fromNode;
                const fromN = nodes[fromNodeId];
                const toN = nodes[targetNodeId];
                if (this._isResourceNode(fromN) || this._isResourceNode(toN)) {
                    this.toast('flows:canvas.resource_node_no_edges', { type: 'warning' });
                } else {
                    const data = this._branchData();
                    const edges = [...asArray(data.edges), { from_node: fromNodeId, to_node: targetNodeId }];
                    const next = { ...data, edges };
                    this._editor.updateBranchData({ data: next });
                    this._editor.pushHistory({ snapshot: next });
                    this._editor.setDirty({ dirty: true });
                }
            }
            this._connection = null;
            this._pointerDownAt = null;
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
                const nx = asNumber(node.pos_x);
                const ny = asNumber(node.pos_y);
                const nh = getNodeCanvasHeight(node);
                if (nx + NODE_W >= minX && nx <= maxX && ny + nh >= minY && ny <= maxY) {
                    ids.push(id);
                }
            }
            this._editor.setMultiSelection({ nodeIds: ids });
            this._selectionRect = null;
            this._pointerDownAt = null;
            return;
        }
        if (this._stickyResize) {
            const notes = Array.isArray(this._stickyResize.lastNotes)
                ? this._stickyResize.lastNotes
                : asArray(this._state().stickyNotes);
            this._persistStickyNotes(notes);
            this._stickyResize = null;
        }
        this._pointerDownAt = null;
    }

    /* ===== Smart guides snap ===== */
    _snapToGuides(x, y, draggedId, nodes) {
        let snappedX = x;
        let snappedY = y;
        const guides = [];
        const draggedNode = nodes[draggedId];
        const hSelf = draggedNode ? getNodeCanvasHeight(draggedNode) : NODE_H;
        const right = x + NODE_W;
        const bottom = y + hSelf;
        const cx = x + NODE_W / 2;
        const cy = y + hSelf / 2;
        for (const [id, node] of Object.entries(nodes)) {
            if (id === draggedId) continue;
            const nx = asNumber(node.pos_x);
            const ny = asNumber(node.pos_y);
            const nh = getNodeCanvasHeight(node);
            const ncx = nx + NODE_W / 2;
            const ncy = ny + nh / 2;
            const nright = nx + NODE_W;
            const nbottom = ny + nh;
            if (Math.abs(x - nx) <= SNAP_THRESHOLD) { snappedX = nx; guides.push({ axis: 'v', at: nx }); }
            else if (Math.abs(right - nright) <= SNAP_THRESHOLD) { snappedX = nright - NODE_W; guides.push({ axis: 'v', at: nright }); }
            else if (Math.abs(cx - ncx) <= SNAP_THRESHOLD) { snappedX = ncx - NODE_W / 2; guides.push({ axis: 'v', at: ncx }); }
            if (Math.abs(y - ny) <= SNAP_THRESHOLD) { snappedY = ny; guides.push({ axis: 'h', at: ny }); }
            else if (Math.abs(bottom - nbottom) <= SNAP_THRESHOLD) { snappedY = nbottom - hSelf; guides.push({ axis: 'h', at: nbottom }); }
            else if (Math.abs(cy - ncy) <= SNAP_THRESHOLD) { snappedY = ncy - hSelf / 2; guides.push({ axis: 'h', at: ncy }); }
        }
        return { x: snappedX, y: snappedY, guides };
    }

    /* ===== Context menu ===== */
    _onContextMenu(e, target, targetId) {
        e.preventDefault();
        e.stopPropagation();
        if (this._drag || this._connection || this._pan || this._selectionRect || this._stickyResize) return;
        if (this._pointerMoved) return;
        this._editor.openContextMenu({ menu: { x: e.clientX, y: e.clientY, target, targetId: asString(targetId) } });
    }

    _onContextMenuAction(e) {
        const detail = isPlainObject(e.detail) ? e.detail : {};
        const kind = detail.kind;
        const target = detail.target;
        const targetId = detail.targetId;
        this._handleMenuAction(kind, target, targetId);
    }

    _handleMenuAction(kind, target, targetId) {
        const data = this._branchData();
        if (target === 'node' && targetId) {
            if (kind === 'open_properties') { this._editor.selectNode({ nodeId: targetId }); return; }
            if (kind === 'toggle_entry') {
                const next = { ...data, entry: data.entry === targetId ? null : targetId };
                this._editor.updateBranchData({ data: next });
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
                const edges = asArray(data.edges).filter((_, i) => i !== edgeIndex);
                const next = { ...data, edges };
                this._editor.updateBranchData({ data: next });
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
                const d = FLOWS_EDITOR_DEFAULT_VIEWBOX;
                this._editor.setViewBox({
                    viewBox: {
                        x: vb.x + vb.w / 2 - d.w / 2,
                        y: vb.y + vb.h / 2 - d.h / 2,
                        w: d.w,
                        h: d.h,
                    },
                });
                return;
            }
            if (kind === 'select_all') { this._selectAll(); return; }
            if (kind === 'show_shortcuts') { this.openModal('flows.canvas_help', {}); return; }
        }
    }

    _fitView() {
        const nodes = Object.values(this._nodes());
        const vb = computeFitViewBox(nodes);
        if (vb === null) {
            this._editor.setViewBox({ viewBox: { ...FLOWS_EDITOR_DEFAULT_VIEWBOX } });
            return;
        }
        this._editor.setViewBox({ viewBox: vb });
    }

    /* ===== Drag-and-drop create ===== */
    _onDragOver(e) {
        const mode = this._inferPaletteDndMode(e);
        if (!mode) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        let dirty = false;
        if (!this._paletteDndActive) {
            this._paletteDndActive = true;
            dirty = true;
        }
        if (this._paletteDndMode !== mode) {
            this._paletteDndMode = mode;
            dirty = true;
        }
        if (mode === 'resource') {
            const local = this._localPoint(e.clientX, e.clientY);
            const hit = this._findNodeAtLocal(local);
            if (this._paletteDndHoverNodeId !== hit) {
                this._paletteDndHoverNodeId = hit;
                dirty = true;
            }
        } else if (this._paletteDndHoverNodeId != null) {
            this._paletteDndHoverNodeId = null;
            dirty = true;
        }
        if (dirty) this.requestUpdate();
    }

    _onNodeCardDragOver(e, nodeId) {
        const mode = this._inferPaletteDndMode(e);
        if (!mode) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'copy';
        let dirty = false;
        if (!this._paletteDndActive) {
            this._paletteDndActive = true;
            dirty = true;
        }
        if (this._paletteDndMode !== mode) {
            this._paletteDndMode = mode;
            dirty = true;
        }
        if (mode === 'resource' && this._paletteDndHoverNodeId !== nodeId) {
            this._paletteDndHoverNodeId = nodeId;
            dirty = true;
        }
        if (dirty) this.requestUpdate();
    }

    _onNodeCardDragLeave(e, nodeId) {
        const mode = this._inferPaletteDndMode(e);
        if (mode !== 'resource') return;
        const rel = e.relatedTarget;
        if (rel instanceof Node && e.currentTarget.contains(rel)) return;
        if (this._paletteDndHoverNodeId === nodeId) {
            this._paletteDndHoverNodeId = null;
            this.requestUpdate();
        }
    }

    _onNodeCardDrop(e, nodeId) {
        const nodeType = e.dataTransfer.getData('application/x-flow-node-type');
        const resourceType = e.dataTransfer.getData('application/x-flow-resource-type');
        if (!nodeType && !resourceType) return;
        e.preventDefault();
        e.stopPropagation();
        this._clearPaletteDndVisual();
        const local = this._localPoint(e.clientX, e.clientY);
        this._applyPaletteDrop({ local, nodeType, resourceType, htmlTargetNodeId: nodeId });
    }

    _onDrop(e) {
        const nodeType = e.dataTransfer.getData('application/x-flow-node-type');
        const resourceType = e.dataTransfer.getData('application/x-flow-resource-type');
        if (!nodeType && !resourceType) return;
        e.preventDefault();
        this._clearPaletteDndVisual();
        const local = this._localPoint(e.clientX, e.clientY);
        this._applyPaletteDrop({ local, nodeType, resourceType, htmlTargetNodeId: null });
    }

    _applyPaletteDrop(ctx) {
        const { local, nodeType, resourceType, htmlTargetNodeId } = ctx;
        const data = this._branchData();
        if (nodeType) {
            if (nodeType === 'code') {
                this._onDropCodeNode({ local });
                return;
            }
            if (nodeType === 'flow') {
                this._onDropFlowNode({ local });
                return;
            }
            if (nodeType === 'mcp') {
                this._onDropMcpNode({ local });
                return;
            }
            const id = genId('n');
            const base = {
                type: nodeType,
                name: nodeType,
                pos_x: local.x - NODE_W / 2,
                pos_y: local.y - NODE_H / 2,
            };
            const newNode =
                nodeType === 'external_api'
                    ? { ...base, ...getBlankExternalApiNodeConfig() }
                    : { ...base, config: {} };
            const nodes = { ...asObject(data.nodes), [id]: newNode };
            const next = { ...data, nodes };
            this._editor.updateBranchData({ data: next });
            this._editor.pushHistory({ snapshot: next });
            this._editor.setDirty({ dirty: true });
            this._editor.selectNode({ nodeId: id });
            return;
        }
        if (resourceType) {
            const rid = genId('r');
            const flowResources = { ...asObject(data.resources), [rid]: { type: resourceType, name: resourceType, config: {} } };
            let nextNodes = { ...asObject(data.nodes) };
            let attachId = typeof htmlTargetNodeId === 'string' && htmlTargetNodeId.length > 0
                ? htmlTargetNodeId
                : this._findNodeAtLocal(local);
            if (!nextNodes[attachId]) {
                attachId = null;
            }
            let newWrapperNodeId = null;
            if (attachId) {
                const target = nextNodes[attachId];
                const prevRes = isPlainObject(target.resources) ? { ...target.resources } : {};
                prevRes[rid] = { resource_id: rid };
                nextNodes = { ...nextNodes, [attachId]: { ...target, resources: prevRes } };
            } else {
                newWrapperNodeId = genId('n');
                nextNodes = {
                    ...nextNodes,
                    [newWrapperNodeId]: {
                        type: 'resource',
                        name: resourceType,
                        pos_x: local.x - NODE_W / 2,
                        pos_y: local.y - NODE_H / 2,
                        resources: { [rid]: { resource_id: rid } },
                    },
                };
            }
            let next = { ...data, resources: flowResources, nodes: nextNodes };
            if (newWrapperNodeId !== null) {
                const ent = typeof next.entry === 'string' ? next.entry : '';
                if (ent.length === 0 || !nextNodes[ent]) {
                    next = { ...next, entry: newWrapperNodeId };
                }
            }
            this._editor.updateBranchData({ data: next });
            this._editor.pushHistory({ snapshot: next });
            this._editor.setDirty({ dirty: true });
            if (attachId) {
                this._editor.selectNode({ nodeId: attachId });
                const tnode = nextNodes[attachId];
                const nm = typeof tnode.name === 'string' && tnode.name.length > 0 ? tnode.name : attachId;
                this.toast('flows:canvas.resource_attached_to_node', { type: 'success', vars: { resource: resourceType, node: nm } });
            } else if (newWrapperNodeId !== null) {
                this._editor.selectNode({ nodeId: newWrapperNodeId });
                this.toast('flows:canvas.resource_dropped_new_node', { type: 'success', vars: { resource: resourceType } });
            }
        }
    }

    _onDropCodeNode(ctx) {
        const { local } = ctx;
        const nodeId = genId('n');
        this.openModal('flows.code_node_drop', {
            onNew: () => {
                this._placeCodeNode(
                    { nodeId, local, name: 'code', config: getBlankCodeNodeConfig() },
                );
            },
            onChooseTemplates: () => {
                this.openModal('flows.code_node_templates', {
                    onCommit: (detail) => {
                        if (!detail || typeof detail !== 'object' || !isPlainObject(detail.config)) {
                            throw new Error('flows-flow-canvas: code template commit must include config');
                        }
                        const nm = typeof detail.nodeName === 'string' && detail.nodeName.length > 0
                            ? detail.nodeName
                            : 'code';
                        this._placeCodeNode(
                            { nodeId, local, name: nm, config: detail.config },
                        );
                    },
                });
            },
        });
    }

    _placeCodeNode(p) {
        const { nodeId, local, name, config } = p;
        const data = this._branchData();
        const newNode = {
            type: 'code',
            name,
            pos_x: local.x - NODE_W / 2,
            pos_y: local.y - NODE_H / 2,
            ...config,
        };
        const nodes = { ...asObject(data.nodes), [nodeId]: newNode };
        const next = { ...data, nodes };
        this._editor.updateBranchData({ data: next });
        this._editor.pushHistory({ snapshot: next });
        this._editor.setDirty({ dirty: true });
        this._editor.selectNode({ nodeId });
    }

    _onDropFlowNode(ctx) {
        const { local } = ctx;
        const nodeId = genId('n');
        this.openModal('flows.tool_picker', {
            pickMode: 'flow_only',
            onPick: (detail) => {
                if (!detail || typeof detail !== 'object' || detail.kind !== 'flow') {
                    return;
                }
                const flowId = detail.tool_id;
                if (typeof flowId !== 'string' || flowId.length === 0) {
                    return;
                }
                const item = detail.item;
                let name = flowId;
                if (item && typeof item === 'object' && typeof item.title === 'string' && item.title.length > 0) {
                    name = item.title;
                }
                this._placeFlowNode({ nodeId, local, name, flowId });
            },
        });
    }

    _placeFlowNode(p) {
        const { nodeId, local, name, flowId } = p;
        const data = this._branchData();
        const newNode = {
            type: 'flow',
            name,
            pos_x: local.x - NODE_W / 2,
            pos_y: local.y - NODE_H / 2,
            config: { flow_id: flowId, branch_id: 'default' },
        };
        const nodes = { ...asObject(data.nodes), [nodeId]: newNode };
        const next = { ...data, nodes };
        this._editor.updateBranchData({ data: next });
        this._editor.pushHistory({ snapshot: next });
        this._editor.setDirty({ dirty: true });
        this._editor.selectNode({ nodeId });
    }

    _onDropMcpNode(ctx) {
        const { local } = ctx;
        const nodeId = genId('n');
        this.openModal('flows.tool_picker', {
            pickMode: 'mcp_only',
            onPick: (detail) => {
                if (!detail || typeof detail !== 'object') {
                    return;
                }
                if (detail.kind !== 'tool') {
                    return;
                }
                const toolId = detail.tool_id;
                if (typeof toolId !== 'string' || toolId.length === 0) {
                    return;
                }
                const parsed = parseMcpToolIdToNodeConfig(toolId);
                const item = detail.item;
                let name = 'mcp';
                if (isPlainObject(item) && typeof item.title === 'string' && item.title.length > 0) {
                    name = item.title;
                } else if (parsed.tool_name.length > 0) {
                    name = parsed.tool_name;
                }
                this._placeMcpNode({
                    nodeId,
                    local,
                    name,
                    server_id: parsed.server_id,
                    tool_name: parsed.tool_name,
                    headers: {},
                    state_mapping: {},
                });
            },
        });
    }

    _placeMcpNode(p) {
        const { nodeId, local, name, server_id, tool_name, headers, state_mapping } = p;
        if (typeof server_id !== 'string' || server_id.length === 0) {
            throw new Error('flows-flow-canvas: _placeMcpNode server_id required');
        }
        if (typeof tool_name !== 'string' || tool_name.length === 0) {
            throw new Error('flows-flow-canvas: _placeMcpNode tool_name required');
        }
        if (!isPlainObject(headers)) {
            throw new Error('flows-flow-canvas: _placeMcpNode headers must be a plain object');
        }
        if (!isPlainObject(state_mapping)) {
            throw new Error('flows-flow-canvas: _placeMcpNode state_mapping must be a plain object');
        }
        const data = this._branchData();
        const newNode = {
            type: 'mcp',
            name,
            pos_x: local.x - NODE_W / 2,
            pos_y: local.y - NODE_H / 2,
            server_id,
            tool_name,
            headers,
            state_mapping,
        };
        const nodes = { ...asObject(data.nodes), [nodeId]: newNode };
        const next = { ...data, nodes };
        this._editor.updateBranchData({ data: next });
        this._editor.pushHistory({ snapshot: next });
        this._editor.setDirty({ dirty: true });
        this._editor.selectNode({ nodeId });
    }

    /* ===== Sticky notes drag/edit/delete ===== */
    _onStickyChange(e) {
        const detail = e.detail;
        if (!detail || !detail.noteId) return;
        const notes = asArray(this._state().stickyNotes).map((n) => n.id === detail.noteId ? { ...n, text: detail.text } : n);
        this._editor.updateStickyNote({ note: notes.find((n) => n.id === detail.noteId) });
        this._persistStickyNotes(notes);
    }

    _onStickyRemove(e) {
        const noteId = e.detail?.noteId;
        if (!noteId) return;
        this._editor.removeStickyNote({ id: noteId });
        const notes = asArray(this._state().stickyNotes).filter((n) => n.id !== noteId);
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
        const svg = this.renderRoot.querySelector('svg.canvas-host');
        if (svg && typeof detail.pointerId === 'number') {
            try {
                svg.setPointerCapture(detail.pointerId);
            } catch (err) {
                // pointer мог уже быть отпущен — продолжаем без capture, pointermove/up на window это переживут
            }
        }
    }

    _onStickyDragStart(e, note) {
        const detail = e.detail;
        if (!detail) return;
        this._drag = {
            type: 'sticky',
            noteId: detail.noteId,
            startX: detail.x,
            startY: detail.y,
            origX: asNumber(note.x),
            origY: asNumber(note.y),
        };
        this._pointerDownAt = { x: detail.x, y: detail.y, button: 0 };
        this._pointerMoved = false;
        const svg = this.renderRoot.querySelector('svg.canvas-host');
        if (svg && typeof detail.pointerId === 'number') {
            try { svg.setPointerCapture(detail.pointerId); } catch (err) { /* pointer already released */ }
        }
    }

    _onStickyCollapseToggle(e) {
        const detail = e.detail;
        if (!detail || !detail.noteId) return;
        const notes = asArray(this._state().stickyNotes).map((n) => n.id === detail.noteId
            ? { ...n, collapsed: Boolean(detail.collapsed) }
            : n);
        const updated = notes.find((n) => n.id === detail.noteId);
        if (updated) this._editor.updateStickyNote({ note: updated });
        this._persistStickyNotes(notes);
    }

    _onStickyLinkToggle(e) {
        const detail = e.detail;
        if (!detail || !detail.noteId) return;
        if (detail.isLinked) {
            const notes = asArray(this._state().stickyNotes).map((n) => n.id === detail.noteId
                ? { ...n, attached_node_id: null }
                : n);
            const updated = notes.find((n) => n.id === detail.noteId);
            if (updated) this._editor.updateStickyNote({ note: updated });
            this._persistStickyNotes(notes);
            this._stickyLinkMode = null;
            this.requestUpdate();
            return;
        }
        if (this._stickyLinkMode?.noteId === detail.noteId) {
            this._stickyLinkMode = null;
            this.toast('flows:canvas.sticky_note.link_mode_cancelled', { type: 'info' });
        } else {
            this._stickyLinkMode = { noteId: detail.noteId };
            this.toast('flows:canvas.sticky_note.link_mode_hint', { type: 'info' });
        }
        this.requestUpdate();
    }

    _attachStickyToNode(noteId, nodeId) {
        const notes = asArray(this._state().stickyNotes).map((n) => n.id === noteId
            ? { ...n, attached_node_id: nodeId }
            : n);
        const updated = notes.find((n) => n.id === noteId);
        if (updated) this._editor.updateStickyNote({ note: updated });
        this._persistStickyNotes(notes);
        this._stickyLinkMode = null;
        this.requestUpdate();
    }

    /** Нода `resource` не соединяется рёбрами исполнения. */
    _isResourceNode(node) {
        return isPlainObject(node) && node.type === 'resource';
    }

    /* ===== Render ===== */
    _renderFanInBadge(id, node) {
        const policy = node.incoming_policy === 'all' ? 'all' : 'any';
        const h = getNodeCanvasHeight(node);
        const cy = h / 2;
        const r = 11;
        const iconSize = 14;
        const scale = iconSize / 24;
        const tx = -iconSize / 2;
        const ty = cy - iconSize / 2;
        const iconAny = svg`
            <g class="badge-fanin-icon" transform=${`translate(${tx}, ${ty}) scale(${scale})`}>
                <path d="m4 13h16a1 1 0 0 0 0-2h-16a1 1 0 0 0 0 2z"></path>
                <path d="m20 5h-16a1 1 0 0 0 0 2h16a1 1 0 0 0 0-2z"></path>
                <path d="m4 19h16a1 1 0 0 0 0-2h-16a1 1 0 0 0 0 2z"></path>
            </g>
        `;
        const iconAll = svg`
            <g class="badge-fanin-icon" transform=${`translate(${tx}, ${ty}) scale(${scale})`}>
                <path d="m20 14.3c1.2 0 2.3-1 2.3-2.3s-1-2.3-2.3-2.3-2.3 1-2.3 2.3 1.1 2.3 2.3 2.3z"></path>
                <path d="m20 6.3c1.2 0 2.3-1 2.3-2.3s-1-2.3-2.3-2.3-2.3 1-2.3 2.3 1.1 2.3 2.3 2.3z"></path>
                <path d="m20 22.3c1.2 0 2.3-1 2.3-2.3s-1-2.3-2.3-2.3-2.3 1-2.3 2.3 1.1 2.3 2.3 2.3z"></path>
                <path d="m4 14.3c1.2 0 2.3-1 2.3-2.3s-1.1-2.2-2.3-2.2-2.3 1-2.3 2.3 1.1 2.2 2.3 2.2z"></path>
                <path d="m19 12.8c.4 0 .8-.3.8-.8s-.3-.8-.8-.8h-7.3v-4.2c0-1.6.7-2.3 2.3-2.3h5c.4 0 .8-.3.8-.8s-.4-.6-.8-.6h-5c-2.4 0-3.8 1.3-3.8 3.8v4.3h-5.2c-.4 0-.8.3-.8.8s.3.8.8.8h5.3v4c0 2.4 1.3 3.8 3.8 3.8h5c.4 0 .8-.3.8-.8s-.3-.8-.8-.8h-5c-1.6 0-2.3-.7-2.3-2.3v-4.3h7.2z"></path>
            </g>
        `;
        return svg`
            <g
                @dblclick=${(e) => this._onFanInDblClick(e, id)}
                @pointerdown=${(e) => e.stopPropagation()}
                @contextmenu=${(e) => this._onContextMenu(e, 'node', id)}
            >
                <circle
                    class="badge-fanin-bg"
                    cx="0" cy=${cy} r=${r}
                    data-node-id=${id}
                    data-port-side="in"
                    data-policy=${policy}
                ></circle>
                ${policy === 'all' ? iconAll : iconAny}
            </g>
        `;
    }

    _renderNode(id, node, inDegree) {
        const x = asNumber(node.pos_x);
        const y = asNumber(node.pos_y);
        const h = getNodeCanvasHeight(node);
        const canvasTools = normalizedLlmToolsForCanvas(node);
        const maxShown = MAX_CHIPS_SHOWN;
        const visibleTools = canvasTools.slice(0, maxShown);
        const moreTools = canvasTools.length - visibleTools.length;
        const meta = getNodeTypeMeta(node.type);
        const nodeStyle = `--node-accent: ${getCategoryToken(meta.category)};`;
        const isCodeNode = node.type === 'code';
        const nodeIcon = isCodeNode
            ? this._renderCodeLanguageIcon(node.language, 28)
            : this._renderCanvasIcon(meta.icon, 18);
        const state = this._state();
        const multi = asArray(state.multiSelection);
        const isSelected = state.selectedNodeId === id;
        const isMulti = multi.includes(id) && multi.length > 1;
        const hasBp = asArray(state.breakpointNodeIds).includes(id);
        const isBpHit = state.breakpointHitNodeId === id;
        let runtimeState = null;
        if (isBpHit) runtimeState = 'breakpoint-hit';
        else if (asArray(state.runningNodeIds).includes(id)) runtimeState = 'running';
        else if (isPlainObject(state.erroredNodes) && state.erroredNodes[id]) runtimeState = 'error';
        else if (asArray(state.completedNodeIds).includes(id)) runtimeState = 'completed';
        const isInherited = asArray(state.inheritedNodeIds).includes(id);
        const isResource = this._isResourceNode(node);
        const showFanInEffective = !isResource && inDegree >= 2;
        const hasToolStrip = canvasTools.length > 0;
        const foBody = html`
            <div
                xmlns="http://www.w3.org/1999/xhtml"
                class="node-card-content ${hasToolStrip ? 'has-tools' : ''}"
                style=${nodeStyle}
                @dragover=${(ev) => this._onNodeCardDragOver(ev, id)}
                @dragleave=${(ev) => this._onNodeCardDragLeave(ev, id)}
                @drop=${(ev) => this._onNodeCardDrop(ev, id)}
            >
                <div class="node-card-main">
                    <div
                        class="node-icon-wrap"
                        data-cat=${meta.category}
                        ?data-language-icon=${isCodeNode}
                    >
                        ${nodeIcon}
                    </div>
                    <div class="node-meta">
                        <div class="node-name">${typeof node.name === 'string' && node.name.length > 0 ? node.name : id}</div>
                        <div class="node-type">${asString(node.type)}</div>
                    </div>
                </div>
                ${hasToolStrip ? html`
                    <div class="node-tools-row">
                        ${visibleTools.map((ref) => {
                            const tm = getToolRefVisualMeta(ref);
                            const tid = ref.tool_id;
                            const label = getToolLabel(ref);
                            const inferredLanguage = inferToolRefLanguage(ref);
                            const isLanguageTool = inferredLanguage.length > 0;
                            const chipStyle = `--tool-accent: ${getCategoryToken(tm.category)};`;
                            const chipIcon = isLanguageTool
                                ? this._renderCodeLanguageIcon(inferredLanguage, 24)
                                : this._renderCanvasIcon(tm.icon, 14);
                            return html`
                                <button
                                    type="button"
                                    class="node-tool-chip"
                                    data-cat=${tm.category}
                                    ?data-language-icon=${isLanguageTool}
                                    style=${chipStyle}
                                    title=${label}
                                    @pointerdown=${(e) => {
                                        e.stopPropagation();
                                        this._editor.selectNode({ nodeId: id, openToolId: tid });
                                    }}
                                >
                                    ${chipIcon}
                                </button>
                            `;
                        })}
                        ${moreTools > 0 ? html`<span class="node-tools-more">+${moreTools}</span>` : ''}
                    </div>
                ` : ''}
            </div>
        `;

        return svg`
            <g
                class="node"
                transform=${`translate(${x}, ${y})`}
                ?data-selected=${isSelected}
                ?data-multi-selected=${isMulti}
                ?data-inherited=${isInherited}
                data-cat=${meta.category}
                data-state=${asString(runtimeState)}
                style=${nodeStyle}
                ?data-palette-drop-target=${this._paletteDndMode === 'resource' && this._paletteDndHoverNodeId === id}
                @pointerdown=${(e) => this._onPointerDownNode(e, id)}
                @contextmenu=${(e) => this._onContextMenu(e, 'node', id)}
                @dblclick=${() => this._editor.selectNode({ nodeId: id })}
            >
                <rect class="node-aura" x="-5" y="-5" width=${NODE_W + 10} height=${h + 10} rx=${NODE_RADIUS + 5} ry=${NODE_RADIUS + 5}></rect>
                <rect class="node-card" x="0" y="0" width=${NODE_W} height=${h} rx=${NODE_RADIUS} ry=${NODE_RADIUS}></rect>
                <rect class="node-sheen" x="10" y="1" width=${NODE_W - 20} height="1.5" rx="1" ry="1"></rect>
                <foreignObject x="0" y="0" width=${NODE_W} height=${h}>${foBody}</foreignObject>
                ${hasBp ? svg`<circle class="badge-bp-circle" cx=${NODE_W - 8} cy="8" r="5"></circle>` : ''}
                ${isInherited ? svg`<text class="badge-inherited" x="6" y=${h - 6} font-size="10">↑</text>` : ''}
                ${showFanInEffective
                    ? this._renderFanInBadge(id, node)
                    : (!isResource ? svg`
                        <circle
                            class="port in"
                            cx="0" cy=${h / 2} r=${PORT_R}
                            data-node-id=${id} data-port-side="in"
                        ></circle>
                    ` : '')}
                ${!isResource ? svg`
                <circle
                    class="port"
                    cx=${NODE_W} cy=${h / 2} r=${PORT_R}
                    data-node-id=${id} data-port-side="out"
                    @pointerdown=${(e) => this._onPointerDownPort(e, id, 'out')}
                ></circle>
                ` : ''}
            </g>
        `;
    }

    _onFanInDblClick(e, nodeId) {
        e.preventDefault();
        e.stopPropagation();
        this.openModal('flows.incoming_policy', { nodeId });
    }

    _renderEdge(edge, i, nodes) {
        const { from: fromId, to: toId } = getEdgeEndpoints(edge);
        const fromNode = nodes[fromId];
        const toNode = nodes[toId];
        if (!fromNode || !toNode) return svg``;
        const start = this._portCoords(fromNode, 'out');
        const end = this._portCoords(toNode, 'in');
        const condition = edge.condition === undefined ? null : edge.condition;
        const mid = midpoint(start.x, start.y, end.x, end.y);
        const editorState = this._state();
        const inheritedKeys = Array.isArray(editorState.inheritedEdgeKeys) ? editorState.inheritedEdgeKeys : [];
        const edgeKey = `${fromId}->${toId}`;
        const isInherited = inheritedKeys.includes(edgeKey);
        const edgeClass = isInherited ? 'edge inherited' : 'edge';
        const failE = asArray(editorState.failedEdgeIndices);
        const runE = asArray(editorState.runningEdgeIndices);
        const compE = asArray(editorState.completedEdgeIndices);
        let runState = null;
        if (failE.includes(i)) {
            runState = 'failed';
        } else if (compE.includes(i)) {
            runState = 'completed';
        } else if (runE.includes(i)) {
            runState = 'running';
        }
        const d = pathFor(start.x, start.y, end.x, end.y);
        return svg`
            <g class="edge-group">
                <path
                    class="edge-hit"
                    d=${d}
                    @contextmenu=${(e) => this._onContextMenu(e, 'edge', String(i))}
                    @dblclick=${(e) => this._onEdgeDblClick(e, toId)}
                    @pointerenter=${() => { this._hoverEdgeIndex = i; }}
                    @pointerleave=${() => { this._hoverEdgeIndex = -1; }}
                ></path>
                <path
                    class=${edgeClass}
                    d=${d}
                    data-run-state=${runState != null ? runState : ''}
                ></path>
                ${renderEdgeLabel({
                    edgeId: i,
                    x: mid.x,
                    y: mid.y,
                    condition,
                    onOpen: () => this.openModal('flows.edge_condition', { edgeIndex: i }),
                })}
            </g>
        `;
    }

    _onEdgeDblClick(e, nodeId) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof nodeId !== 'string' || nodeId.length === 0) return;
        this.openModal('flows.incoming_policy', { nodeId });
    }

    _renderVirtualEnd(node) {
        const start = this._portCoords(node, 'out');
        const markerR = 18;
        const gap = 24;
        const cx = start.x + gap + markerR;
        const cy = start.y;
        return svg`
            <g class="edge-group">
                <path class="edge" d=${pathFor(start.x, start.y, cx - markerR, cy)}></path>
                <circle class="edge-end-marker" cx=${cx} cy=${cy} r=${markerR}></circle>
                <text class="edge-end-text" x=${cx} y=${cy + 4} text-anchor="middle">END</text>
            </g>
        `;
    }

    _renderVirtualStart(node) {
        const end = this._portCoords(node, 'in');
        const markerR = 18;
        const gap = 24;
        const cx = end.x - gap - markerR;
        const cy = end.y;
        return svg`
            <g class="edge-group">
                <circle class="edge-start-marker" cx=${cx} cy=${cy} r=${markerR}></circle>
                <text class="edge-start-text" x=${cx} y=${cy + 4} text-anchor="middle">START</text>
                <path class="edge" d=${pathFor(cx + markerR, cy, end.x, end.y)}></path>
            </g>
        `;
    }

    _renderSmartGuides() {
        const guides = asArray(this._state().smartGuides);
        const vb = this._viewBox();
        return guides.map((g, i) => g.axis === 'v'
            ? svg`<line class="smart-guide" x1=${g.at} y1=${vb.y} x2=${g.at} y2=${vb.y + vb.h}></line>`
            : svg`<line class="smart-guide" x1=${vb.x} y1=${g.at} x2=${vb.x + vb.w} y2=${g.at}></line>`);
    }

    _renderStickyNotes() {
        const notes = asArray(this._state().stickyNotes);
        const linkPendingId = typeof this._stickyLinkMode?.noteId === 'string' ? this._stickyLinkMode.noteId : '';
        return notes.map((note) => {
            const collapsed = Boolean(note.collapsed);
            const wRaw = Number(note.width);
            const w = Number.isFinite(wRaw) && wRaw > 0 ? wRaw : STICKY_W;
            const hRaw = Number(note.height);
            const h = collapsed ? STICKY_COLLAPSED_H : (Number.isFinite(hRaw) && hRaw > 0 ? hRaw : STICKY_H);
            const attached = typeof note.attached_node_id === 'string' ? note.attached_node_id : '';
            return svg`
                <foreignObject x=${note.x} y=${note.y} width=${w} height=${h}>
                    <flows-sticky-note
                        xmlns="http://www.w3.org/1999/xhtml"
                        note-id=${note.id}
                        .text=${asString(note.text)}
                        color-token=${colorOrDefault(note.color_token, 'warning_bg')}
                        .width=${w}
                        .height=${h}
                        ?collapsed=${collapsed}
                        attached-node-id=${attached}
                        ?link-pending=${linkPendingId === note.id}
                        @drag-start=${(e) => this._onStickyDragStart(e, note)}
                        @change=${this._onStickyChange}
                        @collapse-toggle=${this._onStickyCollapseToggle}
                        @link-toggle=${this._onStickyLinkToggle}
                        @remove=${this._onStickyRemove}
                        @resize-start=${(e) => this._onStickyResizeStart(e, note)}
                    ></flows-sticky-note>
                </foreignObject>
            `;
        });
    }

    _renderStickyAttachLines() {
        const notes = asArray(this._state().stickyNotes);
        const nodes = this._nodes();
        const out = [];
        for (const note of notes) {
            const nodeId = typeof note.attached_node_id === 'string' ? note.attached_node_id : '';
            if (!nodeId) continue;
            const node = nodes[nodeId];
            if (!node) continue;
            const collapsed = Boolean(note.collapsed);
            const wRaw = Number(note.width);
            const w = Number.isFinite(wRaw) && wRaw > 0 ? wRaw : STICKY_W;
            const hRaw = Number(note.height);
            const h = collapsed ? STICKY_COLLAPSED_H : (Number.isFinite(hRaw) && hRaw > 0 ? hRaw : STICKY_H);
            const noteRect = { x: asNumber(note.x), y: asNumber(note.y), w, h };
            const nodeH = getNodeCanvasHeight(node);
            const nodeRect = { x: asNumber(node.pos_x), y: asNumber(node.pos_y), w: NODE_W, h: nodeH };
            const noteCenter = { x: noteRect.x + noteRect.w / 2, y: noteRect.y + noteRect.h / 2 };
            const nodeCenter = { x: nodeRect.x + nodeRect.w / 2, y: nodeRect.y + nodeRect.h / 2 };
            const start = rectBoundaryAnchor(noteRect, nodeCenter);
            const end = rectBoundaryAnchor(nodeRect, noteCenter);
            const d = attachPathFor(start.x, start.y, end.x, end.y);
            out.push(svg`<path class="sticky-attach-line" d=${d}></path>`);
        }
        return out;
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
        const nodes = this._nodes();
        const tid = typeof menu.targetId === 'string' ? menu.targetId : '';
        const resourceNode = menu.target === 'node' && tid.length > 0 && this._isResourceNode(nodes[tid]);
        return html`
            <flows-canvas-context-menu
                .x=${menu.x}
                .y=${menu.y}
                target=${menu.target}
                target-id=${asString(menu.targetId)}
                .resourceNode=${resourceNode}
                @action=${this._onContextMenuAction}
                @close=${() => this._editor.closeContextMenu({})}
            ></flows-canvas-context-menu>
        `;
    }

    render() {
        const state = this._state();
        const skillsData = getBranchData(state);
        const nodes = getBranchNodes(state);
        const edges = getBranchEdges(state);
        const activeTool = typeof state.activeTool === 'string' && state.activeTool.length > 0 ? state.activeTool : 'select';
        const vb = this._viewBox();
        const vbStr = `${vb.x} ${vb.y} ${vb.w} ${vb.h}`;
        const panActive = Boolean(this._pan);
        const linkMode = Boolean(this._stickyLinkMode);

        const fromIds = new Set();
        for (const edge of edges) {
            const { from, to } = getEdgeEndpoints(edge);
            if (!from || !to) continue;
            if (!nodes[from] || !nodes[to]) continue;
            fromIds.add(from);
        }
        const orphanNodes = Object.entries(nodes).filter(([nid, n]) => !fromIds.has(nid) && !this._isResourceNode(n));
        const entryId = typeof state.entryNodeId === 'string' && state.entryNodeId.length > 0
            ? state.entryNodeId
            : (typeof skillsData.entry === 'string' && skillsData.entry.length > 0 ? skillsData.entry : null);
        const entryNode = entryId && nodes[entryId] ? nodes[entryId] : null;

        const inDegrees = new Map();
        for (const edge of edges) {
            const { to } = getEdgeEndpoints(edge);
            if (!to) continue;
            const prev = inDegrees.has(to) ? inDegrees.get(to) : 0;
            inDegrees.set(to, prev + 1);
        }

        return html`
            <svg
                class="canvas-host"
                viewBox=${vbStr}
                data-tool=${activeTool}
                ?data-pan-active=${panActive}
                ?data-link-mode=${linkMode}
                ?data-palette-dnd-active=${this._paletteDndActive}
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
                <rect x="-1000000" y="-1000000" width="2000000" height="2000000" fill="url(#canvas-grid)"></rect>

                <g class="sticky-attach-layer">${this._renderStickyAttachLines()}</g>

                <g class="sticky-layer">${this._renderStickyNotes()}</g>

                <g class="edges-layer">
                    ${edges.map((edge, i) => this._renderEdge(edge, i, nodes))}
                    ${entryNode ? this._renderVirtualStart(entryNode) : ''}
                    ${orphanNodes.map(([id, n]) => this._renderVirtualEnd(n))}
                    ${this._connection
                        ? svg`<path class="edge-temp" d=${pathFor(this._connection.x1, this._connection.y1, this._connection.x2, this._connection.y2)}></path>`
                        : ''}
                </g>

                <g class="guides-layer">${this._renderSmartGuides()}</g>

                <g class="nodes-layer">
                    ${Object.entries(nodes).map(([id, node]) => this._renderNode(id, node, inDegrees.has(id) ? inDegrees.get(id) : 0))}
                </g>

                ${this._renderSelectionRect()}
            </svg>
            ${this._renderContextMenu()}
        `;
    }
}

customElements.define('flows-flow-canvas', FlowsFlowCanvas);
