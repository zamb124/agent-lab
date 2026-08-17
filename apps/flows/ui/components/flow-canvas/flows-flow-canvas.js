/**
 * flows-flow-canvas — нативный SVG-канвас редактора flow.
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
 *   - zoom: ctrl/meta + wheel (pinch на тачпаде — плавно по deltaY); pan: пробел/middle-mouse-drag/tool=pan;
 *   - select: click; multi-select: shift+drag по фону → bounding-rect;
 *   - hotkeys (вешаются на document): Del/Ctrl+A/Ctrl+D/F2/Enter/Esc/стрелки/Shift+S;
 *   - правый клик → диспатч `openContextMenu` через slice; <flows-canvas-context-menu>
 *     рендерится оверлеем и эмитит `action`/`close`.
 */

import { html, css, svg, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveUiIconFile } from '@platform/lib/utils/file-icons.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
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
    wheelZoomViewBoxFactor,
    zoomViewBoxAroundPoint,
} from '../../_helpers/flows-viewbox.js';
import {
    FLOW_TERMINAL_OUTER_R,
    FLOW_TERMINAL_INNER_R,
    terminalStartCenter,
    terminalEndCenter,
    listTerminalEndPorts,
} from '../../_helpers/flows-terminal-markers.js';
import {
    buildNodeRunViewModel,
    CANVAS_RUN_RESULT_GAP,
    CANVAS_RUN_RESULT_PILL_COLLAPSED_H,
    countNodeRunDiffChanges,
    getNodeRunResultPillHeight,
    nodeRunResultExpandKey,
    pickLatestNodeRunResult,
} from '../../_helpers/flows-node-run-result.js';
import {
    normalizedLlmToolsForCanvas,
    getToolRefVisualMeta,
    getToolLabel,
    inferToolRefLanguage,
    MAX_CHIPS_SHOWN,
} from '../../_helpers/flows-tool-visual.js';
import { getBlankCodeNodeConfig } from '../../_helpers/code-node-defaults.js';
import { getBlankExternalApiNodeConfig } from '../../_helpers/flows-external-api-defaults.js';
import { getBlankHitlNodeConfig } from '../../_helpers/flows-hitl-defaults.js';
import {
    getBlankReflectionNodeConfig,
    buildReflectionExitEdge,
    listReflectionExits,
    reflectionOutPortYFraction,
} from '../../_helpers/flows-reflection-defaults.js';
import {
    defaultResourceConfigForType,
    defaultResourceDisplayName,
    dataTableCreateRequest,
} from '../../_helpers/flows-resource-defaults.js';
import {
    canvasNodeTypeSubtitle,
    isEvaluationRoleNode,
    isPortlessCanvasNode,
} from '../../_helpers/evaluation-flow-nodes.js';
import {
    hasControlPath,
    buildDataWires,
    buildLineageSet,
    buildLineageSetFromWireKeys,
    chipRefKey,
    chipRefKeysForWireKeys,
    countNodeDataflowProblems,
    dataWireKey,
    dataWireChipKind,
    dataflowChipAnchor,
    dataflowChipKind,
    dataflowChipLabel,
    dataflowChipRect,
    dataflowNodeChipLayout,
    findOutputChipIndex,
    resolveDataWireEndpoints,
    dataWirePathFor,
    wiresForChipHover,
    DATAFLOW_CHIP_W,
    DATAFLOW_CHIP_ZONE_W,
    DATAFLOW_CHIP_INSET,
    DATAFLOW_CHIP_HOST_W,
} from '../../_helpers/flows-dataflow-canvas.js';
import { buildNodeOrbitPath, nodeOrbitPerimeter } from '../../_helpers/flows-node-orbit.js';
const NODE_RADIUS = 12;
const NODE_RUN_ORBIT_DUR = '2.2s';
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
    static i18nNamespace = 'flows';
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
        _variableDropHoverNodeId: { state: true },
        _hoverNodeId: { state: true },
        _hoverChipRef: { state: true },
        _variableWire: { state: true },
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

            /* Нода */
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
            g.node[data-state="running"] .node-aura,
            g.node[data-state="breakpoint-hit"] .node-aura {
                opacity: 0.14;
            }
            g.node[data-state="running"] .node-card {
                stroke: var(--info);
                stroke-width: 2;
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
                filter:
                    drop-shadow(0 16px 34px rgba(0, 0, 0, 0.24))
                    drop-shadow(0 0 16px color-mix(in srgb, var(--warning) 34%, transparent));
            }

            .node-run-orbit {
                pointer-events: none;
            }
            .node-run-track {
                fill: none;
                stroke-width: 1;
                stroke-linecap: round;
                vector-effect: non-scaling-stroke;
                opacity: 0.22;
            }
            .node-run-orbit[data-run-tone="info"] .node-run-track {
                stroke: color-mix(in srgb, var(--info) 55%, var(--node-accent) 45%);
            }
            .node-run-orbit[data-run-tone="warning"] .node-run-track {
                stroke: var(--warning);
            }
            .node-run-arc {
                fill: none;
                stroke-width: 2.5;
                stroke-linecap: round;
                vector-effect: non-scaling-stroke;
                stroke-dasharray: 8 92;
                animation: nodeRunArcTravel 2.2s linear infinite;
            }
            .node-run-orbit[data-run-tone="info"] .node-run-arc {
                stroke: color-mix(in srgb, var(--info) 78%, white 22%);
            }
            .node-run-orbit[data-run-tone="warning"] .node-run-arc {
                stroke: color-mix(in srgb, var(--warning) 78%, white 22%);
            }
            @keyframes nodeRunArcTravel {
                from { stroke-dashoffset: 0; }
                to { stroke-dashoffset: -100; }
            }
            .node-run-firefly-head {
                fill: white;
                opacity: 1;
            }
            .node-run-firefly-trail-1 {
                opacity: 0.55;
            }
            .node-run-firefly-trail-2 {
                opacity: 0.28;
            }
            .node-run-orbit[data-run-tone="info"] .node-run-firefly-head,
            .node-run-orbit[data-run-tone="info"] .node-run-firefly-trail {
                fill: color-mix(in srgb, var(--info) 72%, white 28%);
            }
            .node-run-orbit[data-run-tone="warning"] .node-run-firefly-head,
            .node-run-orbit[data-run-tone="warning"] .node-run-firefly-trail {
                fill: color-mix(in srgb, var(--warning) 72%, white 28%);
            }

            @keyframes nodePulseRunning {
                0%, 100% { stroke-opacity: 1; }
                50%      { stroke-opacity: 0.45; }
            }

            @media (prefers-reduced-motion: reduce) {
                g.node[data-state="running"] .node-run-orbit,
                g.node[data-state="breakpoint-hit"] .node-run-orbit {
                    display: none;
                }
                g.node[data-state="running"] .node-card,
                g.node[data-state="breakpoint-hit"] .node-card {
                    animation: nodePulseRunning 1.4s ease-in-out infinite;
                }
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
            .node-run-result foreignObject {
                pointer-events: all;
            }
            .node-run-result-pill {
                box-sizing: border-box;
                width: 100%;
                min-height: ${CANVAS_RUN_RESULT_PILL_COLLAPSED_H}px;
                padding: 6px 8px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                font-family: var(--font-sans);
                cursor: pointer;
                user-select: none;
            }
            .node-run-result-pill[data-tone='ok'] {
                border-color: var(--success-border);
                background: var(--success-bg);
            }
            .node-run-result-pill[data-tone='error'] {
                border-color: var(--error-border);
                background: var(--error-bg);
            }
            .node-run-result-pill[data-tone='running'] {
                border-color: var(--info);
                animation: nodePulseRunning 1.4s ease-in-out infinite;
            }
            .node-run-result-pill[data-expanded] {
                cursor: default;
            }
            .node-run-result-header {
                display: flex;
                align-items: flex-start;
                gap: 4px;
            }
            .node-run-result-header .node-run-result-primary {
                flex: 1;
                min-width: 0;
            }
            .node-run-result-maximize {
                flex-shrink: 0;
            }
            .node-run-result-primary {
                font-size: 11px;
                font-weight: var(--font-semibold);
                line-height: 1.35;
                color: var(--text-primary);
                word-break: break-word;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 2;
                overflow: hidden;
            }
            .node-run-result-meta {
                margin-top: 2px;
                font-size: 10px;
                line-height: 1.3;
                color: var(--text-tertiary);
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                align-items: center;
            }
            .node-run-result-run-badge {
                display: inline-flex;
                align-items: center;
                padding: 0 6px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                font-size: 10px;
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .node-run-result-change-label-row {
                display: flex;
                align-items: center;
                gap: 4px;
                min-width: 0;
            }
            .node-run-result-type-chip {
                display: inline-flex;
                align-items: center;
                flex-shrink: 0;
                padding: 0 5px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                font-size: 9px;
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: lowercase;
            }
            .node-run-result-more {
                margin-top: 2px;
                padding: 2px 0;
                font-size: 10px;
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .node-run-result-changes {
                margin: 6px 0 0;
                padding: 0;
                list-style: none;
                display: flex;
                flex-direction: column;
                gap: 4px;
            }
            .node-run-result-change {
                display: grid;
                grid-template-columns: 16px 1fr;
                gap: 4px 6px;
                align-items: start;
                font-size: 10px;
                line-height: 1.35;
            }
            .node-run-result-change-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 16px;
                height: 16px;
                border-radius: var(--radius-sm);
                font-size: 11px;
                font-weight: var(--font-bold);
                font-family: var(--font-mono);
                flex-shrink: 0;
            }
            .node-run-result-change[data-change-type='added'] .node-run-result-change-badge {
                color: var(--success);
                background: var(--success-bg);
                border: 1px solid var(--success-border);
            }
            .node-run-result-change[data-change-type='changed'] .node-run-result-change-badge {
                color: var(--warning);
                background: var(--warning-bg);
                border: 1px solid var(--warning-border);
            }
            .node-run-result-change[data-change-type='removed'] .node-run-result-change-badge {
                color: var(--error);
                background: var(--error-bg);
                border: 1px solid var(--error-border);
            }
            .node-run-result-change-body {
                min-width: 0;
            }
            .node-run-result-change-label {
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                word-break: break-word;
            }
            .node-run-result-change-detail {
                margin-top: 1px;
                font-family: var(--font-mono);
                color: var(--text-secondary);
                word-break: break-word;
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

            .node-dataflow-edge {
                opacity: 0;
                pointer-events: none;
                transition: opacity var(--motion-duration-micro) var(--motion-ease-standard);
            }
            g.node[data-dataflow-visible] .node-dataflow-edge,
            g.node[data-selected] .node-dataflow-edge,
            g.node[data-multi-selected] .node-dataflow-edge,
            .canvas-host[data-show-data-wires] g.node .node-dataflow-edge {
                opacity: 1;
            }
            .node-dataflow-edge foreignObject,
            .node-dataflow-edge .node-dataflow-stack,
            .node-dataflow-chip {
                pointer-events: none;
            }
            .node-dataflow-chip-hit {
                fill: transparent;
                stroke: transparent;
                cursor: grab;
                pointer-events: none;
            }
            g.node[data-dataflow-visible] .node-dataflow-chip-hit,
            g.node[data-selected] .node-dataflow-chip-hit,
            g.node[data-multi-selected] .node-dataflow-chip-hit,
            .canvas-host[data-show-data-wires] g.node .node-dataflow-chip-hit {
                pointer-events: all;
            }
            .node-dataflow-hover-pad {
                fill: transparent;
                stroke: transparent;
                pointer-events: all;
            }
            .node-dataflow-chip-hit:active {
                cursor: grabbing;
            }
            .node-dataflow-stack {
                display: flex;
                flex-direction: column;
                gap: 4px;
                width: 132px;
                max-width: 132px;
                height: 100%;
                overflow: visible;
                font-family: var(--font-sans);
            }
            .node-dataflow-stack[data-side="in"] {
                align-items: flex-end;
            }
            .node-dataflow-stack[data-side="out"] {
                align-items: flex-start;
            }
            .node-dataflow-chip {
                max-width: 132px;
                height: 24px;
                box-sizing: border-box;
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 0 7px;
                border-radius: 7px;
                border: 1px solid color-mix(in oklab, var(--node-accent) 22%, var(--glass-border-subtle));
                background: color-mix(in oklab, var(--glass-solid-strong) 88%, var(--node-accent) 12%);
                color: color-mix(in oklab, var(--node-accent) 42%, var(--text-secondary));
                font-size: 10px;
                font-weight: var(--font-semibold);
                line-height: 1.1;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.14);
            }
            .node-dataflow-chip[data-chip-kind="ui_value"] {
                --flows-dataflow-ui-value: var(--info);
                border-color: color-mix(in oklab, var(--flows-dataflow-ui-value) 34%, var(--glass-border-subtle));
                background: color-mix(in oklab, var(--glass-solid-strong) 86%, var(--flows-dataflow-ui-value) 14%);
                color: color-mix(in oklab, var(--flows-dataflow-ui-value) 52%, var(--text-secondary));
            }
            .node-dataflow-chip[data-chip-kind="ui_value"] .req {
                color: var(--flows-dataflow-ui-value);
            }
            .node-dataflow-chip[data-has-producer="true"] {
                height: 30px;
            }
            .node-dataflow-chip[data-status="missing"] {
                border-color: color-mix(in oklab, var(--error) 48%, var(--glass-border-subtle));
                background: color-mix(in oklab, var(--error) 13%, var(--glass-solid-strong));
                color: var(--error);
            }
            .node-dataflow-chip[data-required="true"] {
                border-color: color-mix(in oklab, var(--node-accent) 46%, var(--glass-border-subtle));
            }
            .node-dataflow-chip[data-chip-kind="ui_value"][data-required="true"] {
                border-color: color-mix(in oklab, var(--flows-dataflow-ui-value) 52%, var(--glass-border-subtle));
            }
            .node-dataflow-chip .body {
                display: flex;
                flex-direction: column;
                gap: 1px;
                min-width: 0;
            }
            .node-dataflow-chip .label-row {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                min-width: 0;
            }
            .node-dataflow-chip .req {
                flex-shrink: 0;
                color: var(--node-accent, var(--accent));
                font-weight: var(--font-bold);
            }
            .node-dataflow-chip .label {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .node-dataflow-chip .type {
                flex-shrink: 0;
                color: var(--text-tertiary);
                font-weight: var(--font-medium);
                font-size: 9px;
                opacity: 0.85;
            }
            .node-dataflow-chip .producer {
                color: var(--text-tertiary);
                font-weight: var(--font-medium);
                font-size: 9px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .node-dataflow-chip .dir {
                flex-shrink: 0;
                color: var(--text-tertiary);
            }
            .node-dataflow-chip[data-draggable="true"] {
                cursor: grab;
            }
            .node-dataflow-chip[data-draggable="true"]:active {
                cursor: grabbing;
            }
            svg.canvas-host[data-variable-wire-active] {
                cursor: crosshair;
            }
            .edge-temp.variable-wire {
                stroke: color-mix(in oklab, var(--accent) 82%, var(--success));
                stroke-width: 2.25;
            }
            g.node[data-var-drop-target] .node-card {
                stroke: var(--accent);
                stroke-width: 2.5;
            }
            g.node[data-var-drop-target] .node-aura {
                fill: color-mix(in oklab, var(--accent) 16%, transparent);
            }

            /* Бейджи */
            .badge-bp-circle {
                fill: var(--warning);
                stroke: var(--bg-primary);
                stroke-width: 1.5;
            }
            .badge-inherited {
                fill: var(--text-tertiary);
            }
            .badge-problems-bg {
                fill: var(--warning);
                stroke: var(--bg-primary);
                stroke-width: 1.5;
            }
            .badge-problems[data-severity="error"] .badge-problems-bg {
                fill: var(--error);
            }
            .badge-problems-count {
                fill: var(--bg-primary);
                font-size: 9px;
                font-weight: var(--font-bold);
                font-family: var(--font-sans);
                pointer-events: none;
            }
            g.node[data-has-errors] .node-card {
                stroke: color-mix(in oklab, var(--error) 62%, var(--glass-border-subtle));
            }

            /* Бейдж fan-in на входном порту (>=2 входящих рёбер) */
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

            /* Порты */
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
            .port-label {
                fill: var(--text-tertiary);
                font-size: 9px;
                font-weight: var(--font-medium);
                pointer-events: none;
                user-select: none;
            }
            .port[data-port-kind="pass"] {
                fill: color-mix(in oklab, var(--success) 72%, var(--node-accent, var(--accent)));
            }
            .port[data-port-kind="fail"] {
                fill: color-mix(in oklab, var(--error) 72%, var(--node-accent, var(--accent)));
            }

            /* Связи по данным (data-flow), отличаются от control-рёбер */
            .data-wires-layer {
                pointer-events: none;
            }
            .data-wire-path {
                fill: none;
                stroke: color-mix(in oklab, var(--accent) 70%, transparent);
                stroke-width: 1.75;
                stroke-dasharray: 5 4;
                stroke-linecap: round;
                opacity: 0.9;
                transition:
                    opacity var(--motion-duration-micro) var(--motion-ease-standard),
                    stroke var(--motion-duration-micro) var(--motion-ease-standard),
                    stroke-width var(--motion-duration-micro) var(--motion-ease-standard);
            }
            .data-wire-path[data-wire-kind="ui_value"] {
                stroke: color-mix(in oklab, var(--info) 72%, transparent);
            }
            .data-wire-path[data-dimmed] {
                opacity: 0.12;
            }
            .data-wire-path[data-highlighted] {
                opacity: 1;
                stroke: var(--accent);
                stroke-width: 2.5;
                stroke-dasharray: none;
                filter: drop-shadow(0 0 6px color-mix(in srgb, var(--accent) 35%, transparent));
            }
            .data-wire-path[data-wire-kind="ui_value"][data-highlighted] {
                stroke: var(--info);
                filter: drop-shadow(0 0 6px color-mix(in srgb, var(--info) 35%, transparent));
            }
            .data-wire-label[data-highlighted] {
                fill: var(--accent);
                font-size: 10px;
            }
            .node-dataflow-chip[data-wire-highlight="true"] {
                border-color: color-mix(in oklab, var(--accent) 65%, var(--glass-border-subtle));
                background: color-mix(in oklab, var(--accent) 18%, var(--glass-solid-strong));
                box-shadow: 0 0 0 1px color-mix(in oklab, var(--accent) 40%, transparent);
            }
            .node-dataflow-chip[data-chip-kind="ui_value"][data-wire-highlight="true"] {
                border-color: color-mix(in oklab, var(--info) 65%, var(--glass-border-subtle));
                background: color-mix(in oklab, var(--info) 18%, var(--glass-solid-strong));
                box-shadow: 0 0 0 1px color-mix(in oklab, var(--info) 40%, transparent);
            }
            .data-wire-label {
                fill: var(--accent);
                font-family: var(--font-sans);
                font-size: 9px;
                font-weight: var(--font-semibold);
                paint-order: stroke;
                stroke: var(--bg-primary);
                stroke-width: 3;
                transition: opacity var(--motion-duration-micro) var(--motion-ease-standard);
            }
            .data-wire-label[data-dimmed] {
                opacity: 0.12;
            }
            g.node[data-dimmed] {
                opacity: 0.28;
                transition: opacity var(--motion-duration-micro) var(--motion-ease-standard);
            }

            /* Рёбра */
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
            .terminal-marker {
                pointer-events: none;
            }
            .terminal-marker-ring {
                fill: none;
                stroke-width: 1.5;
            }
            .terminal-marker--start .terminal-marker-ring {
                stroke: color-mix(in oklab, var(--accent) 55%, transparent);
            }
            .terminal-marker--end .terminal-marker-ring {
                stroke: color-mix(in oklab, var(--text-secondary) 55%, transparent);
            }
            .terminal-marker-halo {
                pointer-events: none;
            }
            .terminal-marker--start .terminal-marker-halo {
                fill: color-mix(in oklab, var(--accent) 28%, transparent);
            }
            .terminal-marker--end .terminal-marker-halo {
                fill: color-mix(in oklab, var(--text-secondary) 22%, transparent);
            }
            .terminal-marker-disc {
                stroke-width: 1.25;
            }
            .terminal-marker--start .terminal-marker-disc {
                fill: color-mix(in oklab, var(--accent) 88%, var(--glass-solid-strong));
                stroke: color-mix(in oklab, var(--accent) 40%, white);
            }
            .terminal-marker--end .terminal-marker-disc {
                fill: var(--text-secondary);
                stroke: color-mix(in oklab, var(--text-primary) 35%, var(--text-secondary));
            }
            .terminal-marker-icon {
                fill: var(--bg-primary);
            }
            .terminal-marker--end .terminal-marker-icon {
                fill: var(--bg-primary);
            }
            .terminal-marker-label {
                font-size: 8px;
                font-weight: 700;
                font-family: var(--font-mono);
                letter-spacing: 0.06em;
                pointer-events: none;
            }
            .terminal-marker--start .terminal-marker-label {
                fill: color-mix(in oklab, var(--accent) 72%, var(--text-secondary));
            }
            .terminal-marker--end .terminal-marker-label {
                fill: var(--text-secondary);
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

            /* Прямоугольник выделения */
            .selection-box {
                fill: var(--accent-subtle);
                stroke: var(--accent);
                stroke-width: 1;
                stroke-dasharray: 4 2;
                opacity: 0.5;
                pointer-events: none;
            }

            /* Умные направляющие */
            .smart-guide {
                stroke: var(--accent-hover);
                stroke-width: 1;
                stroke-dasharray: 2 2;
                opacity: 0.7;
                pointer-events: none;
            }

            /* Слой стикеров */
            .sticky-host { width: 100%; height: 100%; }

            /* Линия привязки стикера к ноде */
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

            /* Режим привязки: подсветка всех нод как кликабельных */
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
        this._variableDropHoverNodeId = null;
        this._hoverNodeId = null;
        this._hoverChipRef = null;
        this._variableWire = null;
        this._lineageSet = null;
        this._highlightWireKeys = null;
        this._highlightChipKeys = null;
        this._editor = this.useOp('flows/editor');
        this._bulkDelete = this.useOp('flows/editor_bulk_delete');
        this._stickyUpsert = this.useOp('flows/sticky_note_upsert');
        this._dataTableCreate = this.useOp('flows/data_table_create');
        this._dataTableCreateInFlight = new Set();
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

    _reflectionExitsForNode(node) {
        if (!this._isReflectionNode(node)) {
            return [];
        }
        const policy = isPlainObject(node.critic_policy) ? node.critic_policy : null;
        return listReflectionExits(policy);
    }

    _portCoords(node, side, outPort = null) {
        const px = asNumber(node.pos_x);
        const x = side === 'in' ? px : px + NODE_W;
        const h = getNodeCanvasHeight(node);
        const exits = side === 'out' ? this._reflectionExitsForNode(node) : null;
        const fraction = side === 'out'
            ? reflectionOutPortYFraction(outPort, exits)
            : 0.5;
        const y = asNumber(node.pos_y) + h * fraction;
        return { x, y };
    }

    _isReflectionNode(node) {
        return isPlainObject(node) && node.type === 'reflection';
    }

    _resolveOutPortForEdge(fromNode, edge) {
        if (!this._isReflectionNode(fromNode) || !isPlainObject(edge)) {
            return null;
        }
        const port = edge.from_port;
        if (typeof port !== 'string' || port.length === 0) {
            return null;
        }
        const exits = this._reflectionExitsForNode(fromNode);
        if (exits.some((item) => item.id === port)) {
            return port;
        }
        return null;
    }

    _getSvgScreenScale() {
        const svgEl = this.renderRoot.querySelector('svg.canvas-host');
        if (!svgEl) return 1;
        const ctm = svgEl.getScreenCTM();
        if (!ctm) return 1;
        const scale = ctm.a;
        if (!(scale > 0)) return 1;
        return scale;
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

    _findNodeAtLocalForVariableWire(local) {
        const nodes = this._nodes();
        let hit = null;
        for (const [id, node] of Object.entries(nodes)) {
            const x = asNumber(node.pos_x);
            const y = asNumber(node.pos_y);
            const h = getNodeCanvasHeight(node);
            const left = x - DATAFLOW_CHIP_ZONE_W;
            const right = x + NODE_W + DATAFLOW_CHIP_ZONE_W;
            if (local.x >= left && local.x <= right && local.y >= y && local.y <= y + h) {
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
            const { from_node, to_node } = getEdgeEndpoints(edge);
            return !deletableIds.includes(from_node) && !deletableIds.includes(to_node);
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
        const factor = wheelZoomViewBoxFactor(e.deltaY, e.deltaMode);
        if (factor === 1) return;
        const vb = this._viewBox();
        const pivot = this._localPoint(e.clientX, e.clientY);
        this._editor.setViewBox({
            viewBox: zoomViewBoxAroundPoint(vb, factor, pivot.x, pivot.y),
        });
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

    _onPointerDownPort(e, nodeId, side, outPort = null) {
        this._pointerDownAt = { x: e.clientX, y: e.clientY, button: e.button };
        this._pointerMoved = false;
        if (e.button !== 0 || side !== 'out') return;
        e.stopPropagation();
        const node = this._nodes()[nodeId];
        if (!node || this._isPortlessNode(node)) return;
        const exits = this._reflectionExitsForNode(node);
        const resolvedPort = typeof outPort === 'string'
            && exits.some((item) => item.id === outPort)
            ? outPort
            : null;
        const start = this._portCoords(node, 'out', resolvedPort);
        this._connection = {
            fromNode: nodeId,
            fromPort: resolvedPort,
            x1: start.x,
            y1: start.y,
            x2: start.x,
            y2: start.y,
        };
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
            this._pan = {
                startClientX: e.clientX,
                startClientY: e.clientY,
                origVB: { ...vb },
                screenScale: this._getSvgScreenScale(),
            };
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
            const scale = this._pan.screenScale;
            const dx = (e.clientX - this._pan.startClientX) / scale;
            const dy = (e.clientY - this._pan.startClientY) / scale;
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
        if (this._variableWire) {
            const local = this._localPoint(e.clientX, e.clientY);
            const hit = this._findNodeAtLocalForVariableWire(local);
            let dirty = false;
            if (this._variableWire.x2 !== local.x || this._variableWire.y2 !== local.y) {
                this._variableWire = { ...this._variableWire, x2: local.x, y2: local.y };
                dirty = true;
            }
            if (this._variableDropHoverNodeId !== hit) {
                this._variableDropHoverNodeId = hit;
                dirty = true;
            }
            if (dirty) this.requestUpdate();
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
                if (this._isPortlessNode(fromN) || this._isPortlessNode(toN)) {
                    const evaluationEndpoint = this._isEvaluationNode(fromN)
                        || this._isEvaluationNode(toN);
                    this.toast(
                        evaluationEndpoint
                            ? 'flows:canvas.evaluation_node_no_edges'
                            : 'flows:canvas.resource_node_no_edges',
                        { type: 'warning' },
                    );
                } else {
                    const data = this._branchData();
                    const fromPort = this._connection.fromPort;
                    let newEdge;
                    if (
                        this._isReflectionNode(fromN)
                        && typeof fromPort === 'string'
                        && fromPort.length > 0
                    ) {
                        newEdge = buildReflectionExitEdge(fromNodeId, targetNodeId, fromPort);
                    } else {
                        newEdge = { from_node: fromNodeId, to_node: targetNodeId };
                    }
                    const edges = [...asArray(data.edges), newEdge];
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
        if (this._variableWire) {
            const wire = this._variableWire;
            this._variableWire = null;
            this._hoverChipRef = null;
            const targetNodeId = this._variableDropHoverNodeId;
            this._variableDropHoverNodeId = null;
            if (this._pointerMoved && targetNodeId && targetNodeId !== wire.fromNodeId) {
                this._openVariableMapping(wire.fromNodeId, wire.path, wire.type, targetNodeId);
            }
            this._pointerDownAt = null;
            this.requestUpdate();
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

    /* ===== Привязка к умным направляющим ===== */
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

    /* ===== Контекстное меню ===== */
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

    /* ===== Создание через drag-and-drop ===== */
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

    _isVariableDrag(e) {
        const types = e && e.dataTransfer ? e.dataTransfer.types : null;
        if (!types) return false;
        return Array.from(types).includes('application/x-flow-variable');
    }

    _onOutputChipPointerDown(e, fromNodeId, chip, chipIndex) {
        if (e.button !== 0) return;
        e.stopPropagation();
        e.preventDefault();
        const path = dataflowChipLabel(chip);
        if (!path || typeof fromNodeId !== 'string' || fromNodeId.length === 0) return;
        const fromNode = this._nodes()[fromNodeId];
        if (!fromNode) return;
        const type = chip && typeof chip.type === 'string' ? chip.type : 'any';
        const df = this._dataflowForNode(fromNodeId);
        const outputs = df && df.canvas && Array.isArray(df.canvas.outputs) ? df.canvas.outputs : [];
        const inputs = df && df.canvas && Array.isArray(df.canvas.inputs) ? df.canvas.inputs : [];
        const resolvedIndex = typeof chipIndex === 'number' && chipIndex >= 0
            ? chipIndex
            : findOutputChipIndex(outputs, path);
        const outIdx = resolvedIndex >= 0 ? resolvedIndex : 0;
        const nodeX = asNumber(fromNode.pos_x);
        const nodeY = asNumber(fromNode.pos_y);
        const nodeH = getNodeCanvasHeight(fromNode);
        const start = dataflowChipAnchor(nodeX, nodeY, nodeH, NODE_W, 'out', outIdx, inputs, outputs);
        this._pointerDownAt = { x: e.clientX, y: e.clientY, button: e.button };
        this._pointerMoved = false;
        this._hoverChipRef = null;
        this._hoverNodeId = fromNodeId;
        this._variableWire = {
            fromNodeId,
            path,
            type,
            x1: start.x,
            y1: start.y,
            x2: start.x,
            y2: start.y,
        };
        this.renderRoot.querySelector('svg.canvas-host')?.setPointerCapture(e.pointerId);
    }

    _openVariableMapping(fromNodeId, sourcePath, sourceType, targetNodeId) {
        if (!fromNodeId || !sourcePath || !targetNodeId || fromNodeId === targetNodeId) return;
        const nodes = this._nodes();
        const nameOf = (nid) => {
            const n = nodes && typeof nodes === 'object' ? nodes[nid] : null;
            return n && typeof n.name === 'string' && n.name.length > 0 ? n.name : nid;
        };
        this.openModal('flows.variable_mapping', {
            fromNodeId,
            fromNodeName: nameOf(fromNodeId),
            targetNodeId,
            targetNodeName: nameOf(targetNodeId),
            sourcePath,
            sourceType: typeof sourceType === 'string' ? sourceType : 'any',
            pathExists: hasControlPath(fromNodeId, targetNodeId, asArray(this._branchData().edges)),
        });
    }

    _onOutputChipDragStart(e, fromNodeId, chip) {
        const path = this._dataflowChipLabel(chip);
        if (!path || typeof fromNodeId !== 'string' || fromNodeId.length === 0) return;
        const type = chip && typeof chip.type === 'string' ? chip.type : 'any';
        e.dataTransfer.setData('application/x-flow-variable', JSON.stringify({ fromNode: fromNodeId, path, type }));
        e.dataTransfer.effectAllowed = 'link';
        e.stopPropagation();
    }

    _handleVariableDrop(e, targetNodeId) {
        let payload = null;
        try {
            payload = JSON.parse(e.dataTransfer.getData('application/x-flow-variable'));
        } catch {
            payload = null;
        }
        if (!payload || typeof payload !== 'object') return;
        const fromNode = typeof payload.fromNode === 'string' ? payload.fromNode : '';
        const path = typeof payload.path === 'string' ? payload.path : '';
        const type = typeof payload.type === 'string' ? payload.type : 'any';
        this._openVariableMapping(fromNode, path, type, targetNodeId);
    }

    _onNodeCardDragOver(e, nodeId) {
        if (this._isVariableDrag(e)) {
            e.preventDefault();
            e.stopPropagation();
            e.dataTransfer.dropEffect = 'link';
            if (this._variableDropHoverNodeId !== nodeId) {
                this._variableDropHoverNodeId = nodeId;
                this.requestUpdate();
            }
            return;
        }
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
        if (this._isVariableDrag(e)) {
            const rel = e.relatedTarget;
            if (rel instanceof Node && e.currentTarget.contains(rel)) return;
            if (this._variableDropHoverNodeId === nodeId) {
                this._variableDropHoverNodeId = null;
                this.requestUpdate();
            }
            return;
        }
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
        if (this._isVariableDrag(e)) {
            e.preventDefault();
            e.stopPropagation();
            this._variableDropHoverNodeId = null;
            this.requestUpdate();
            this._handleVariableDrop(e, nodeId);
            return;
        }
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
            if (nodeType === 'reflection') {
                this._placeReflectionNode({ nodeId: genId('n'), local });
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
                    : nodeType === 'hitl_node'
                        ? { ...base, ...getBlankHitlNodeConfig() }
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
            const resourceName = defaultResourceDisplayName(resourceType);
            const flowResources = {
                ...asObject(data.resources),
                [rid]: {
                    type: resourceType,
                    name: resourceName,
                    permission: [],
                    config: defaultResourceConfigForType(resourceType, rid),
                },
            };
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
                        name: resourceName,
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
            if (resourceType === 'data_table') {
                void this._autoCreateDataTableFile(rid);
            }
        }
    }

    async _autoCreateDataTableFile(resourceId) {
        if (typeof resourceId !== 'string' || resourceId.length === 0) {
            throw new Error('flows-flow-canvas: resourceId required for DataTable create');
        }
        if (this._dataTableCreateInFlight.has(resourceId)) {
            return;
        }
        const flowId = typeof this.flowId === 'string' ? this.flowId.trim() : '';
        if (flowId.length === 0) {
            throw new Error('flows-flow-canvas: flowId required for DataTable create');
        }
        const data = this._branchData();
        const resource = asObject(data.resources)[resourceId];
        if (!isPlainObject(resource)) {
            throw new Error(`flows-flow-canvas: DataTable resource not found: ${resourceId}`);
        }
        const cfg = isPlainObject(resource.config) ? resource.config : {};
        if (typeof cfg.file_id === 'string' && cfg.file_id.length > 0) {
            return;
        }
        const stem = typeof resource.name === 'string' && resource.name.trim().length > 0
            ? resource.name.trim()
            : 'data';
        this._dataTableCreateInFlight.add(resourceId);
        try {
            const created = await this._dataTableCreate.run(dataTableCreateRequest(flowId, stem));
            if (!created || typeof created.file_id !== 'string' || created.file_id.length === 0) {
                throw new Error('flows-flow-canvas: DataTable create did not return file_id');
            }
            const latest = this._branchData();
            const resources = { ...asObject(latest.resources) };
            const current = resources[resourceId];
            if (!isPlainObject(current)) {
                throw new Error(`flows-flow-canvas: DataTable resource missing after create: ${resourceId}`);
            }
            const currentCfg = isPlainObject(current.config) ? current.config : {};
            if (typeof currentCfg.file_id === 'string' && currentCfg.file_id.length > 0) {
                return;
            }
            resources[resourceId] = { ...current, config: { ...currentCfg, file_id: created.file_id } };
            this._editor.updateBranchData({ data: { ...latest, resources } });
            this._editor.setDirty({ dirty: true });
            this.toast('flows:data_table_resource_editor.toast_created', { type: 'success' });
        } finally {
            this._dataTableCreateInFlight.delete(resourceId);
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
                this.openModal('flows.tool_picker', {
                    pickMode: 'code_node',
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

    _placeReflectionNode(p) {
        const { nodeId, local } = p;
        const data = this._branchData();
        const newNode = {
            type: 'reflection',
            name: 'reflection',
            pos_x: local.x - NODE_W / 2,
            pos_y: local.y - NODE_H / 2,
            ...getBlankReflectionNodeConfig(),
        };
        const nodes = { ...asObject(data.nodes), [nodeId]: newNode };
        const next = { ...data, nodes };
        this._editor.updateBranchData({ data: next });
        this._editor.pushHistory({ snapshot: next });
        this._editor.setDirty({ dirty: true });
        this._editor.selectNode({ nodeId });
    }

    /* ===== Drag/edit/delete для sticky notes ===== */
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

    /** Tester/judge (`store.evaluation_role`) — harness-only, не execution-граф. */
    _isEvaluationNode(node) {
        return isEvaluationRoleNode(node);
    }

    /** Resource или evaluation — без портов, END и connect. */
    _isPortlessNode(node) {
        return isPortlessCanvasNode(node);
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

    _dataflowForNode(nodeId) {
        const state = this._state();
        const nodes = state?.dataflow?.nodes;
        if (!nodes || typeof nodes !== 'object') return null;
        const df = nodes[nodeId];
        return df && typeof df === 'object' ? df : null;
    }

    _dataflowChipLabel(chip) {
        return dataflowChipLabel(chip);
    }

    _nodeLabel(nodeId) {
        if (typeof nodeId !== 'string' || nodeId.length === 0) return '';
        const nodes = this._nodes();
        const node = nodes && typeof nodes === 'object' ? nodes[nodeId] : null;
        const name = node && typeof node.name === 'string' ? node.name : '';
        return name.length > 0 ? name : nodeId;
    }

    _dataflowProblems(nodeId) {
        const df = this._dataflowForNode(nodeId);
        const canvas = df && typeof df.canvas === 'object' ? df.canvas : null;
        return countNodeDataflowProblems(canvas);
    }

    _dataWires(nodes) {
        const df = this._state()?.dataflow?.nodes;
        return buildDataWires(df, nodes);
    }

    _renderDataWire(wire, nodes) {
        const fromNode = nodes[wire.from];
        const toNode = nodes[wire.to];
        if (!fromNode || !toNode) return svg``;
        const dataflowNodes = this._state()?.dataflow?.nodes;
        const endpoints = resolveDataWireEndpoints(
            wire,
            fromNode,
            toNode,
            dataflowNodes,
            NODE_W,
            getNodeCanvasHeight,
        );
        if (!endpoints) return svg``;
        const { start, end } = endpoints;
        const mid = midpoint(start.x, start.y, end.x, end.y);
        const wireKey = dataWireKey(wire);
        const wireKind = dataWireChipKind(wire);
        const chipWireHighlightActive = this._highlightWireKeys instanceof Set && this._highlightWireKeys.size > 0;
        const highlighted = chipWireHighlightActive && this._highlightWireKeys.has(wireKey);
        const dimmed = chipWireHighlightActive && !highlighted;
        return svg`
            <g class="data-wire" data-wire-key=${wireKey}>
                <path
                    class="data-wire-path"
                    data-wire-kind=${wireKind}
                    d=${dataWirePathFor(start.x, start.y, end.x, end.y)}
                    ?data-highlighted=${highlighted}
                    ?data-dimmed=${dimmed}
                ></path>
                ${wire.label ? svg`<text
                    class="data-wire-label"
                    x=${mid.x}
                    y=${mid.y - 5}
                    text-anchor="middle"
                    ?data-highlighted=${highlighted}
                    ?data-dimmed=${dimmed}
                >${wire.label}</text>` : ''}
            </g>
        `;
    }

    _onNodeMouseEnter(nodeId) {
        if (this._hoverNodeId !== nodeId) {
            this._hoverNodeId = nodeId;
            this.requestUpdate();
        }
    }

    _isPointerStillInNodeHoverZone(event, nodeId) {
        const group = this.renderRoot.querySelector(`g.node[data-node-id="${nodeId}"]`);
        if (!group || !event || !event.relatedTarget) return false;
        let el = event.relatedTarget;
        while (el) {
            if (el === group) return true;
            const parent = el.parentNode;
            if (parent) {
                el = parent;
                continue;
            }
            const root = typeof el.getRootNode === 'function' ? el.getRootNode() : null;
            const host = root && typeof root === 'object' && 'host' in root ? root.host : null;
            el = host || null;
        }
        return false;
    }

    _onNodeMouseLeave(event, nodeId) {
        if (this._variableWire && this._variableWire.fromNodeId === nodeId) return;
        if (this._variableDropHoverNodeId === nodeId) return;
        if (this._isPointerStillInNodeHoverZone(event, nodeId)) return;
        if (this._hoverNodeId === nodeId) {
            this._hoverNodeId = null;
            this.requestUpdate();
        }
    }

    _isPointerStillInChipHitZone(event, nodeId, side, chipIndex) {
        const hit = this.renderRoot.querySelector(
            `rect.node-dataflow-chip-hit[data-chip-node-id="${nodeId}"][data-chip-side="${side}"][data-chip-index="${chipIndex}"]`,
        );
        if (!hit || !event || !event.relatedTarget) return false;
        let el = event.relatedTarget;
        while (el) {
            if (el === hit) return true;
            const parent = el.parentNode;
            if (parent) {
                el = parent;
                continue;
            }
            const root = typeof el.getRootNode === 'function' ? el.getRootNode() : null;
            const host = root && typeof root === 'object' && 'host' in root ? root.host : null;
            el = host || null;
        }
        return false;
    }

    _onChipPointerEnter(nodeId, side, chipIndex) {
        if (this._variableWire) return;
        const cur = this._hoverChipRef;
        if (cur && cur.nodeId === nodeId && cur.side === side && cur.index === chipIndex) return;
        this._hoverChipRef = { nodeId, side, index: chipIndex };
        this._hoverNodeId = nodeId;
        this.requestUpdate();
    }

    _onChipPointerLeave(event, nodeId, side, chipIndex) {
        if (this._variableWire) return;
        if (this._isPointerStillInChipHitZone(event, nodeId, side, chipIndex)) return;
        const cur = this._hoverChipRef;
        if (cur && cur.nodeId === nodeId && cur.side === side && cur.index === chipIndex) {
            this._hoverChipRef = null;
            this.requestUpdate();
        }
    }

    _isDataflowVisibleForNode(nodeId, { isSelected, isMulti, showAllWires }) {
        if (showAllWires) return true;
        if (isSelected || isMulti) return true;
        if (this._hoverNodeId === nodeId) return true;
        if (this._hoverChipRef && this._hoverChipRef.nodeId === nodeId) return true;
        if (this._lineageSet && this._lineageSet.has(nodeId)) return true;
        if (this._variableWire && this._variableWire.fromNodeId === nodeId) return true;
        if (this._variableDropHoverNodeId === nodeId) return true;
        return false;
    }

    _renderNodeDataflowEdgeChips(id, h) {
        const df = this._dataflowForNode(id);
        if (!df || !df.canvas || typeof df.canvas !== 'object') return svg``;
        const inputs = Array.isArray(df.canvas.inputs) ? df.canvas.inputs : [];
        const outputs = Array.isArray(df.canvas.outputs) ? df.canvas.outputs : [];
        if (inputs.length === 0 && outputs.length === 0) return svg``;
        const layout = dataflowNodeChipLayout(h, inputs, outputs);
        const y = layout.stackY;
        const chipHostHeight = layout.chipHostHeight;
        const isChipWireHighlighted = (side, chipIndex) => {
            if (!(this._highlightChipKeys instanceof Set)) return false;
            return this._highlightChipKeys.has(chipRefKey({ nodeId: id, side, index: chipIndex }));
        };
        const renderStack = (chips, side) => html`
            <div
                xmlns="http://www.w3.org/1999/xhtml"
                class="node-dataflow-stack"
                data-side=${side}
            >
                ${chips.map((chip, chipIndex) => {
                    const label = this._dataflowChipLabel(chip);
                    const status = chip && chip.status === 'missing' ? 'missing' : 'ok';
                    const type = chip && typeof chip.type === 'string' ? chip.type : '';
                    const required = !!(chip && chip.required);
                    const producer = side === 'in' && chip && typeof chip.producer_node === 'string'
                        ? this._nodeLabel(chip.producer_node)
                        : '';
                    const title = [
                        label,
                        type ? `: ${type}` : '',
                        producer ? ` (${this.t('canvas.dataflow.from')} ${producer})` : '',
                        required ? ` — ${this.t('canvas.dataflow.required')}` : '',
                    ].join('');
                    const wireHighlighted = isChipWireHighlighted(side, chipIndex);
                    const chipKind = dataflowChipKind(chip);
                    return html`
                        <span
                            class="node-dataflow-chip"
                            data-status=${status}
                            data-chip-kind=${chipKind}
                            data-required=${required ? 'true' : 'false'}
                            data-draggable=${side === 'out' ? 'true' : 'false'}
                            data-has-producer=${side === 'in' && producer ? 'true' : 'false'}
                            data-wire-highlight=${wireHighlighted ? 'true' : 'false'}
                            title=${title}
                        >
                            <span class="body">
                                <span class="label-row">
                                    ${required ? html`<span class="req" title=${this.t('canvas.dataflow.required')}>*</span>` : ''}
                                    <span class="label">${label}</span>
                                    ${type ? html`<span class="type">${type}</span>` : ''}
                                </span>
                                ${producer ? html`<span class="producer">${this.t('canvas.dataflow.from')} ${producer}</span>` : ''}
                            </span>
                            <span class="dir" aria-hidden="true">→</span>
                        </span>
                    `;
                })}
            </div>
        `;
        const inputChipHitX = -DATAFLOW_CHIP_ZONE_W + (DATAFLOW_CHIP_HOST_W - DATAFLOW_CHIP_W);
        const renderInputHits = () => inputs.map((chip, index) => {
            const rect = dataflowChipRect(y, layout.inputHeights, index);
            return svg`
                <rect
                    class="node-dataflow-chip-hit"
                    x=${inputChipHitX}
                    y=${rect.y}
                    width=${DATAFLOW_CHIP_W}
                    height=${rect.height}
                    data-chip-node-id=${id}
                    data-chip-side="in"
                    data-chip-index=${index}
                    @pointerenter=${() => this._onChipPointerEnter(id, 'in', index)}
                    @pointerleave=${(ev) => this._onChipPointerLeave(ev, id, 'in', index)}
                ></rect>
            `;
        });
        const renderOutputHits = () => outputs.map((chip, index) => {
            const rect = dataflowChipRect(y, layout.outputHeights, index);
            const label = this._dataflowChipLabel(chip);
            return svg`
                <rect
                    class="node-dataflow-chip-hit"
                    x=${NODE_W + 8}
                    y=${rect.y}
                    width=${DATAFLOW_CHIP_W}
                    height=${rect.height}
                    data-output-path=${label}
                    data-chip-node-id=${id}
                    data-chip-side="out"
                    data-chip-index=${index}
                    @pointerenter=${() => this._onChipPointerEnter(id, 'out', index)}
                    @pointerleave=${(ev) => this._onChipPointerLeave(ev, id, 'out', index)}
                    @pointerdown=${(ev) => this._onOutputChipPointerDown(ev, id, chip, index)}
                ></rect>
            `;
        });
        return svg`
            ${inputs.length > 0 ? svg`
                <rect
                    class="node-dataflow-hover-pad"
                    x=${-DATAFLOW_CHIP_ZONE_W}
                    y=${y}
                    width=${DATAFLOW_CHIP_ZONE_W + DATAFLOW_CHIP_INSET}
                    height=${chipHostHeight}
                    @pointerenter=${() => this._onNodeMouseEnter(id)}
                    @pointerleave=${(ev) => this._onNodeMouseLeave(ev, id)}
                ></rect>
                <foreignObject class="node-dataflow-edge" x="-144" y=${y} width="136" height=${chipHostHeight}>
                    ${renderStack(inputs, 'in')}
                </foreignObject>
                ${renderInputHits()}
            ` : ''}
            ${outputs.length > 0 ? svg`
                <rect
                    class="node-dataflow-hover-pad"
                    x=${NODE_W}
                    y=${y}
                    width=${DATAFLOW_CHIP_INSET + DATAFLOW_CHIP_HOST_W}
                    height=${chipHostHeight}
                    @pointerenter=${() => this._onNodeMouseEnter(id)}
                    @pointerleave=${(ev) => this._onNodeMouseLeave(ev, id)}
                ></rect>
                <foreignObject class="node-dataflow-edge" x=${NODE_W + 8} y=${y} width="136" height=${chipHostHeight}>
                    ${renderStack(outputs, 'out')}
                </foreignObject>
                ${renderOutputHits()}
            ` : ''}
        `;
    }

    _renderNodeRunOrbit(h, runtimeState) {
        const path = buildNodeOrbitPath(NODE_W, h, NODE_RADIUS);
        const perimeter = nodeOrbitPerimeter(NODE_W, h, NODE_RADIUS);
        const tone = runtimeState === 'breakpoint-hit' ? 'warning' : 'info';
        return svg`
            <g class="node-run-orbit" data-run-tone=${tone}>
                <path class="node-run-track" d=${path}></path>
                <path
                    class="node-run-arc"
                    d=${path}
                    pathLength="100"
                    style=${`--node-run-perimeter:${perimeter}`}
                ></path>
                <circle class="node-run-firefly-trail node-run-firefly-trail-2" r="2.2" filter="url(#flows-node-firefly-glow)">
                    <animateMotion dur=${NODE_RUN_ORBIT_DUR} repeatCount="indefinite" begin="-0.14s" path=${path}></animateMotion>
                </circle>
                <circle class="node-run-firefly-trail node-run-firefly-trail-1" r="2.8" filter="url(#flows-node-firefly-glow)">
                    <animateMotion dur=${NODE_RUN_ORBIT_DUR} repeatCount="indefinite" begin="-0.07s" path=${path}></animateMotion>
                </circle>
                <circle class="node-run-firefly-head" r="3.2" filter="url(#flows-node-firefly-glow)">
                    <animateMotion dur=${NODE_RUN_ORBIT_DUR} repeatCount="indefinite" path=${path}></animateMotion>
                </circle>
            </g>
        `;
    }

    _onNodeRunResultPointerDown(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    _onNodeRunResultToggle(e, nodeId, runIndex) {
        e.preventDefault();
        e.stopPropagation();
        this._editor.toggleNodeRunResultExpand({ nodeId, runIndex });
    }

    _openNodeRunResultInspector(e, nodeId, runIndex, selectedPath) {
        e.preventDefault();
        e.stopPropagation();
        const props = { nodeId, runIndex };
        if (typeof selectedPath === 'string' && selectedPath.length > 0) {
            props.selectedPath = selectedPath;
        }
        this.openModal('flows.node_run_result', props);
    }

    _renderNodeRunResult(nodeId, cardHeight, runtimeState) {
        const state = this._state();
        if (!state.showCanvasRunResults) {
            return '';
        }
        const y = cardHeight + CANVAS_RUN_RESULT_GAP;
        if (runtimeState === 'running') {
            const pillH = CANVAS_RUN_RESULT_PILL_COLLAPSED_H;
            const body = html`
                <div
                    xmlns="http://www.w3.org/1999/xhtml"
                    class="node-run-result-pill"
                    data-tone="running"
                >
                    <div class="node-run-result-primary">${this.t('canvas_run_result.running')}</div>
                </div>
            `;
            return svg`
                <foreignObject
                    class="node-run-result"
                    x="0" y=${y} width=${NODE_W} height=${pillH}
                    @pointerdown=${this._onNodeRunResultPointerDown}
                    @dblclick=${this._onNodeRunResultPointerDown}
                >
                    ${body}
                </foreignObject>
            `;
        }
        const resultsMap = state.nodeRunResults;
        if (!isPlainObject(resultsMap)) {
            return '';
        }
        const results = resultsMap[nodeId];
        if (!Array.isArray(results) || results.length === 0) {
            return '';
        }
        const latest = pickLatestNodeRunResult(results);
        if (latest === null) {
            return '';
        }
        const kind = latest.kind;
        if (kind !== 'ok' && kind !== 'error') {
            throw new Error('flows-flow-canvas: node run result kind must be ok or error');
        }
        let runIndex = latest.run_index;
        if (typeof runIndex !== 'number' || !Number.isFinite(runIndex)) {
            runIndex = results.length - 1;
        }
        const expandKey = nodeRunResultExpandKey(nodeId, runIndex);
        const expandedKeys = asArray(state.expandedNodeRunKeys);
        const expanded = expandedKeys.includes(expandKey);
        const viewModel = buildNodeRunViewModel(latest, (key, params) => this.t(key, params));
        const pillH = getNodeRunResultPillHeight(latest, expanded, (key, params) => this.t(key, params));
        const metaParts = [];
        const durationMs = latest.duration_ms;
        if (typeof durationMs === 'number' && Number.isFinite(durationMs)) {
            metaParts.push(this.t('canvas_run_result.duration_ms', { ms: String(Math.round(durationMs)) }));
        }
        if (kind === 'ok') {
            const changeCount = countNodeRunDiffChanges(latest);
            if (changeCount > 0) {
                metaParts.push(this.t('canvas_run_result.changes_count', { count: String(changeCount) }));
            }
        }
        const changeRows = expanded && kind === 'ok' ? viewModel.changeRows : [];
        const omittedCount = expanded ? viewModel.omittedCount : 0;
        const runBadge = results.length > 1
            ? html`<article
                class="node-run-result-run-badge"
                role="button"
                tabindex="0"
                data-run-count=${String(results.length)}
                aria-label=${this.t('canvas_run_result.inspect_runs_aria', { count: String(results.length) })}
                @click=${(e) => this._openNodeRunResultInspector(e, nodeId, runIndex)}
                @keydown=${(e) => {
                    if (e.key !== 'Enter' && e.key !== ' ') return;
                    this._openNodeRunResultInspector(e, nodeId, runIndex);
                }}
            >${this.t('canvas_run_result.run_count', { count: String(results.length) })}</article>`
            : nothing;
        const body = html`
            <div
                xmlns="http://www.w3.org/1999/xhtml"
                class="node-run-result-pill"
                data-tone=${kind === 'error' ? 'error' : 'ok'}
                ?data-expanded=${expanded}
                @pointerdown=${this._onNodeRunResultPointerDown}
                @dblclick=${this._onNodeRunResultPointerDown}
                @click=${(e) => this._onNodeRunResultToggle(e, nodeId, runIndex)}
            >
                <div class="node-run-result-header">
                    <div class="node-run-result-primary">${viewModel.headline.length > 0 ? viewModel.headline : this.t('canvas_run_result.empty')}</div>
                    <platform-button
                        class="node-run-result-maximize"
                        variant="ghost"
                        icon-only
                        density="dense"
                        title=${this.t('canvas_run_result.maximize')}
                        aria-label=${this.t('canvas_run_result.maximize_aria')}
                        @click=${(e) => this._openNodeRunResultInspector(e, nodeId, runIndex)}
                    >
                        <platform-icon name="fullscreen" size="14"></platform-icon>
                    </platform-button>
                </div>
                <div class="node-run-result-meta">
                    ${metaParts.map((part) => html`<span>${part}</span>`)}
                    ${runBadge}
                </div>
                ${changeRows.length > 0 ? html`
                    <ul class="node-run-result-changes">
                        ${changeRows.map((row) => html`
                            <li>
                                <article
                                    class="node-run-result-change"
                                    role="button"
                                    tabindex="0"
                                    data-change-type=${row.changeType}
                                    data-path=${row.path}
                                    @click=${(e) => this._openNodeRunResultInspector(e, nodeId, runIndex, row.path)}
                                    @keydown=${(e) => {
                                        if (e.key !== 'Enter' && e.key !== ' ') return;
                                        this._openNodeRunResultInspector(e, nodeId, runIndex, row.path);
                                    }}
                                >
                                    <span class="node-run-result-change-badge" title=${row.badgeLabel} aria-label=${row.badgeLabel}>${row.badge}</span>
                                    <div class="node-run-result-change-body">
                                        <div class="node-run-result-change-label-row">
                                            <div class="node-run-result-change-label">${row.label}</div>
                                            <span class="node-run-result-type-chip">${row.typeLabel}</span>
                                        </div>
                                        <div class="node-run-result-change-detail">${row.detail}</div>
                                    </div>
                                </article>
                            </li>
                        `)}
                    </ul>
                ` : nothing}
                ${omittedCount > 0 ? html`
                    <article
                        class="node-run-result-more"
                        role="button"
                        tabindex="0"
                        @click=${(e) => this._openNodeRunResultInspector(e, nodeId, runIndex)}
                        @keydown=${(e) => {
                            if (e.key !== 'Enter' && e.key !== ' ') return;
                            this._openNodeRunResultInspector(e, nodeId, runIndex);
                        }}
                    >${this.t('canvas_run_result.more_changes', { count: String(omittedCount) })}</article>
                ` : nothing}
            </div>
        `;
        return svg`
            <foreignObject
                class="node-run-result"
                x="0" y=${y} width=${NODE_W} height=${pillH}
                @pointerdown=${this._onNodeRunResultPointerDown}
                @dblclick=${this._onNodeRunResultPointerDown}
            >
                ${body}
            </foreignObject>
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
        const isPortless = this._isPortlessNode(node);
        const typeSubtitle = canvasNodeTypeSubtitle(node);
        const problems = this._dataflowProblems(id);
        const showFanInEffective = !isPortless && inDegree >= 2;
        const hasToolStrip = canvasTools.length > 0;
        const showAllWires = Boolean(state.showDataWires);
        const dataflowVisible = this._isDataflowVisibleForNode(id, { isSelected, isMulti, showAllWires });
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
                        <div class="node-type">${typeSubtitle}</div>
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
                                <article
                                    class="node-tool-chip"
                                    tabindex="0"
                                    role="button"
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
                                </article>
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
                data-node-id=${id}
                data-node-type=${asString(node.type)}
                transform=${`translate(${x}, ${y})`}
                ?data-selected=${isSelected}
                ?data-multi-selected=${isMulti}
                ?data-inherited=${isInherited}
                data-cat=${meta.category}
                data-state=${asString(runtimeState)}
                style=${nodeStyle}
                ?data-has-problems=${problems.total > 0}
                ?data-has-errors=${problems.errors > 0}
                ?data-var-drop-target=${this._variableDropHoverNodeId === id}
                ?data-dataflow-visible=${dataflowVisible}
                ?data-dimmed=${this._lineageSet != null && !this._lineageSet.has(id)}
                ?data-palette-drop-target=${this._paletteDndMode === 'resource' && this._paletteDndHoverNodeId === id}
                @pointerdown=${(e) => this._onPointerDownNode(e, id)}
                @contextmenu=${(e) => this._onContextMenu(e, 'node', id)}
                @mouseenter=${() => this._onNodeMouseEnter(id)}
                @mouseleave=${(e) => this._onNodeMouseLeave(e, id)}
                @dblclick=${() => this._editor.selectNode({ nodeId: id })}
            >
                <rect class="node-aura" x="-5" y="-5" width=${NODE_W + 10} height=${h + 10} rx=${NODE_RADIUS + 5} ry=${NODE_RADIUS + 5}></rect>
                <rect class="node-card" x="0" y="0" width=${NODE_W} height=${h} rx=${NODE_RADIUS} ry=${NODE_RADIUS}></rect>
                ${runtimeState === 'running' || runtimeState === 'breakpoint-hit'
                    ? this._renderNodeRunOrbit(h, runtimeState)
                    : ''}
                <rect class="node-sheen" x="10" y="1" width=${NODE_W - 20} height="1.5" rx="1" ry="1"></rect>
                <foreignObject x="0" y="0" width=${NODE_W} height=${h}>${foBody}</foreignObject>
                ${this._renderNodeDataflowEdgeChips(id, h)}
                ${hasBp ? svg`<circle class="badge-bp-circle" cx=${NODE_W - 8} cy="8" r="5"></circle>` : ''}
                ${problems.total > 0 ? svg`
                    <g class="badge-problems" data-severity=${problems.errors > 0 ? 'error' : 'warning'} transform="translate(8, 8)">
                        <circle class="badge-problems-bg" cx="0" cy="0" r="8"></circle>
                        <text class="badge-problems-count" x="0" y="0.5" text-anchor="middle" dominant-baseline="central">${problems.total > 9 ? '9+' : problems.total}</text>
                    </g>
                ` : ''}
                ${isInherited ? svg`<text class="badge-inherited" x="6" y=${h - 6} font-size="10">↑</text>` : ''}
                ${showFanInEffective
                    ? this._renderFanInBadge(id, node)
                    : (!isPortless ? svg`
                        <circle
                            class="port in"
                            cx="0" cy=${h / 2} r=${PORT_R}
                            data-node-id=${id} data-port-side="in"
                        ></circle>
                    ` : '')}
                ${!isPortless ? this._renderOutPorts(id, node, h) : ''}
                ${this._renderNodeRunResult(id, h, runtimeState)}
            </g>
        `;
    }

    _renderOutPorts(nodeId, node, h) {
        if (this._isReflectionNode(node)) {
            const ports = this._reflectionExitsForNode(node);
            return svg`${ports.map((port, index) => {
                const cy = h * reflectionOutPortYFraction(port.id, ports);
                const kind = index === 0
                    ? 'pass'
                    : (index === ports.length - 1 ? 'fail' : 'mid');
                return svg`
                    <g class="reflection-out-port">
                        <circle
                            class="port"
                            cx=${NODE_W} cy=${cy} r=${PORT_R}
                            data-node-id=${nodeId}
                            data-port-side="out"
                            data-port-id=${port.id}
                            data-port-kind=${kind}
                            @pointerdown=${(e) => this._onPointerDownPort(e, nodeId, 'out', port.id)}
                        ></circle>
                        <text
                            class="port-label"
                            x=${NODE_W + PORT_R + 4}
                            y=${cy}
                            dominant-baseline="central"
                        >${port.label}</text>
                    </g>
                `;
            })}`;
        }
        return svg`
            <circle
                class="port"
                cx=${NODE_W} cy=${h / 2} r=${PORT_R}
                data-node-id=${nodeId} data-port-side="out"
                @pointerdown=${(e) => this._onPointerDownPort(e, nodeId, 'out')}
            ></circle>
        `;
    }

    _onFanInDblClick(e, nodeId) {
        e.preventDefault();
        e.stopPropagation();
        this.openModal('flows.incoming_policy', { nodeId });
    }

    _renderEdge(edge, i, nodes) {
        const { from_node: fromId, to_node: toId } = getEdgeEndpoints(edge);
        const fromNode = nodes[fromId];
        const toNode = nodes[toId];
        if (!fromNode || !toNode) return svg``;
        const outPort = this._resolveOutPortForEdge(fromNode, edge);
        const start = this._portCoords(fromNode, 'out', outPort);
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

    _renderVirtualEnd(node, outPort = null, nodeId) {
        if (typeof nodeId !== 'string' || nodeId.length === 0) {
            throw new Error('flows-flow-canvas: virtual END nodeId required');
        }
        const start = this._portCoords(node, 'out', outPort);
        const { cx, cy } = terminalEndCenter(start);
        const stopHalf = 5;
        const editorState = this._state();
        const endMap = editorState.endWireRunStateByNodeId;
        const runState = isPlainObject(endMap) && typeof endMap[nodeId] === 'string'
            ? endMap[nodeId]
            : null;
        return svg`
            <g class="edge-group terminal-marker terminal-marker--end">
                <path
                    class="edge"
                    data-run-state=${runState != null ? runState : ''}
                    d=${pathFor(start.x, start.y, cx - FLOW_TERMINAL_OUTER_R, cy)}
                ></path>
                <circle
                    class="terminal-marker-halo"
                    cx=${cx}
                    cy=${cy}
                    r=${FLOW_TERMINAL_OUTER_R + 2}
                    filter="url(#flows-terminal-end-glow)"
                ></circle>
                <circle
                    class="terminal-marker-ring"
                    cx=${cx}
                    cy=${cy}
                    r=${FLOW_TERMINAL_OUTER_R}
                ></circle>
                <circle
                    class="terminal-marker-disc"
                    cx=${cx}
                    cy=${cy}
                    r=${FLOW_TERMINAL_INNER_R}
                ></circle>
                <rect
                    class="terminal-marker-icon"
                    x=${cx - stopHalf}
                    y=${cy - stopHalf}
                    width=${stopHalf * 2}
                    height=${stopHalf * 2}
                    rx="1.5"
                    ry="1.5"
                ></rect>
                <text
                    class="terminal-marker-label"
                    x=${cx}
                    y=${cy + FLOW_TERMINAL_OUTER_R + 11}
                    text-anchor="middle"
                >END</text>
            </g>
        `;
    }

    _renderVirtualStart(node) {
        const end = this._portCoords(node, 'in');
        const { cx, cy } = terminalStartCenter(end);
        const editorState = this._state();
        const runState = typeof editorState.startWireRunState === 'string'
            ? editorState.startWireRunState
            : null;
        return svg`
            <g class="edge-group terminal-marker terminal-marker--start">
                <circle
                    class="terminal-marker-halo"
                    cx=${cx}
                    cy=${cy}
                    r=${FLOW_TERMINAL_OUTER_R + 2}
                    filter="url(#flows-terminal-start-glow)"
                ></circle>
                <circle
                    class="terminal-marker-ring"
                    cx=${cx}
                    cy=${cy}
                    r=${FLOW_TERMINAL_OUTER_R}
                ></circle>
                <circle
                    class="terminal-marker-disc"
                    cx=${cx}
                    cy=${cy}
                    r=${FLOW_TERMINAL_INNER_R}
                ></circle>
                <path
                    class="terminal-marker-icon"
                    d=${`M ${cx - 3.5} ${cy - 5.5} L ${cx - 3.5} ${cy + 5.5} L ${cx + 6.5} ${cy} Z`}
                ></path>
                <text
                    class="terminal-marker-label"
                    x=${cx}
                    y=${cy + FLOW_TERMINAL_OUTER_R + 11}
                    text-anchor="middle"
                >START</text>
                <path
                    class="edge"
                    data-run-state=${runState != null ? runState : ''}
                    d=${pathFor(cx + FLOW_TERMINAL_OUTER_R, cy, end.x, end.y)}
                ></path>
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
        const portlessNode = menu.target === 'node' && tid.length > 0 && this._isPortlessNode(nodes[tid]);
        return html`
            <flows-canvas-context-menu
                .x=${menu.x}
                .y=${menu.y}
                target=${menu.target}
                target-id=${asString(menu.targetId)}
                .resourceNode=${portlessNode}
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

        const terminalEnds = [];
        for (const [nid, n] of Object.entries(nodes)) {
            if (this._isPortlessNode(n)) continue;
            const ports = listTerminalEndPorts(nid, n, edges, nodes);
            for (const outPort of ports) {
                terminalEnds.push({ nodeId: nid, node: n, outPort });
            }
        }
        const entryId = typeof state.entryNodeId === 'string' && state.entryNodeId.length > 0
            ? state.entryNodeId
            : (typeof skillsData.entry === 'string' && skillsData.entry.length > 0 ? skillsData.entry : null);
        const entryNode = entryId && nodes[entryId] ? nodes[entryId] : null;

        const inDegrees = new Map();
        for (const edge of edges) {
            const { to_node } = getEdgeEndpoints(edge);
            if (!to_node) continue;
            const prev = inDegrees.has(to_node) ? inDegrees.get(to_node) : 0;
            inDegrees.set(to_node, prev + 1);
        }

        const showAllWires = Boolean(state.showDataWires);
        const hoverId = this._hoverNodeId;
        const chipHoverRef = this._hoverChipRef;
        const chipHoverActive = chipHoverRef
            && typeof chipHoverRef.nodeId === 'string'
            && chipHoverRef.nodeId.length > 0
            && (chipHoverRef.side === 'in' || chipHoverRef.side === 'out')
            && typeof chipHoverRef.index === 'number'
            && chipHoverRef.index >= 0;
        let dataWires = [];
        this._lineageSet = null;
        this._highlightWireKeys = null;
        this._highlightChipKeys = null;
        if (showAllWires || hoverId || chipHoverActive) {
            const allWires = this._dataWires(nodes);
            const dataflowNodes = state.dataflow && typeof state.dataflow === 'object'
                ? state.dataflow.nodes
                : null;
            if (chipHoverActive) {
                this._highlightWireKeys = wiresForChipHover(allWires, chipHoverRef, dataflowNodes);
                if (this._highlightWireKeys.size > 0) {
                    dataWires = allWires;
                    this._lineageSet = buildLineageSetFromWireKeys(this._highlightWireKeys, allWires);
                    this._highlightChipKeys = chipRefKeysForWireKeys(this._highlightWireKeys, allWires, dataflowNodes);
                    this._highlightChipKeys.add(chipRefKey(chipHoverRef));
                } else {
                    this._highlightChipKeys = new Set([chipRefKey(chipHoverRef)]);
                    if (showAllWires) {
                        dataWires = allWires;
                    } else if (hoverId) {
                        dataWires = allWires.filter((wire) => wire.from === hoverId || wire.to === hoverId);
                    }
                    this._lineageSet = new Set([chipHoverRef.nodeId]);
                }
            } else if (hoverId) {
                dataWires = allWires.filter((wire) => wire.from === hoverId || wire.to === hoverId);
                this._lineageSet = buildLineageSet(hoverId, dataWires);
            } else {
                dataWires = allWires;
            }
        }

        return html`
            <svg
                class="canvas-host"
                viewBox=${vbStr}
                data-tool=${activeTool}
                ?data-pan-active=${panActive}
                ?data-link-mode=${linkMode}
                ?data-palette-dnd-active=${this._paletteDndActive}
                ?data-show-data-wires=${showAllWires}
                ?data-variable-wire-active=${Boolean(this._variableWire)}
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
                    <filter id="flows-node-firefly-glow" x="-50%" y="-50%" width="200%" height="200%">
                        <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur"></feGaussianBlur>
                        <feMerge>
                            <feMergeNode in="blur"></feMergeNode>
                            <feMergeNode in="SourceGraphic"></feMergeNode>
                        </feMerge>
                    </filter>
                    <filter id="flows-terminal-start-glow" x="-80%" y="-80%" width="260%" height="260%">
                        <feGaussianBlur in="SourceGraphic" stdDeviation="3.2" result="blur"></feGaussianBlur>
                        <feMerge>
                            <feMergeNode in="blur"></feMergeNode>
                            <feMergeNode in="SourceGraphic"></feMergeNode>
                        </feMerge>
                    </filter>
                    <filter id="flows-terminal-end-glow" x="-60%" y="-60%" width="220%" height="220%">
                        <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur"></feGaussianBlur>
                        <feMerge>
                            <feMergeNode in="blur"></feMergeNode>
                            <feMergeNode in="SourceGraphic"></feMergeNode>
                        </feMerge>
                    </filter>
                </defs>
                <rect x="-1000000" y="-1000000" width="2000000" height="2000000" fill="url(#canvas-grid)"></rect>

                <g class="sticky-attach-layer">${this._renderStickyAttachLines()}</g>

                <g class="sticky-layer">${this._renderStickyNotes()}</g>

                <g class="edges-layer">
                    ${edges.map((edge, i) => this._renderEdge(edge, i, nodes))}
                    ${entryNode ? this._renderVirtualStart(entryNode) : ''}
                    ${terminalEnds.map(({ nodeId, node, outPort }) => this._renderVirtualEnd(node, outPort, nodeId))}
                    ${this._connection
                        ? svg`<path class="edge-temp" d=${pathFor(this._connection.x1, this._connection.y1, this._connection.x2, this._connection.y2)}></path>`
                        : ''}
                    ${this._variableWire
                        ? svg`<path class="edge-temp variable-wire" d=${pathFor(this._variableWire.x1, this._variableWire.y1, this._variableWire.x2, this._variableWire.y2)}></path>`
                        : ''}
                </g>

                <g class="guides-layer">${this._renderSmartGuides()}</g>

                <g class="nodes-layer">
                    ${Object.entries(nodes).map(([id, node]) => this._renderNode(id, node, inDegrees.has(id) ? inDegrees.get(id) : 0))}
                </g>

                <g class="data-wires-layer">${dataWires.map((wire) => this._renderDataWire(wire, nodes))}</g>

                ${this._renderSelectionRect()}
            </svg>
            ${this._renderContextMenu()}
        `;
    }
}

customElements.define('flows-flow-canvas', FlowsFlowCanvas);
