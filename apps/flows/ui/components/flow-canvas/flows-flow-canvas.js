/**
 * flows-flow-canvas — native SVG канвас для flow.
 *
 * Источники state:
 *   - useOp('flows/editor').state.skillsData.{nodes,edges}
 *   - useOp('flows/editor').state.activeTool / selectedNodeId
 *
 * UX:
 *   - drag нод на pointermove (после pointerdown);
 *   - drag-create узла: drop из <flows-node-types-sidebar>
 *     (`application/x-flow-node-type`);
 *   - drag edges с output-порта на input-порт;
 *   - zoom: wheel + ctrl, viewBox локально в компоненте;
 *   - pan: пробел или активный tool='pan';
 *   - клик на узел → editor.selectNode;
 *   - правый клик на ребро → openModal('flows.edge_condition', { edgeId });
 *   - правый клик на узел → openModal('flows.incoming_policy', { nodeId });
 *
 * Light DOM: чтобы CSS-классы могли подсвечивать активные узлы из глобальных
 * стилей, и selection menu могла портироваться через openModal.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const NODE_W = 160;
const NODE_H = 56;
const PORT_R = 6;
const NODE_TYPE_DEFAULT = 'code';

function nodeId() {
    return 'n_' + Math.random().toString(36).slice(2, 9);
}

function pathFor(srcX, srcY, dstX, dstY) {
    const dx = Math.abs(dstX - srcX) * 0.6;
    return `M ${srcX} ${srcY} C ${srcX + dx} ${srcY} ${dstX - dx} ${dstY} ${dstX} ${dstY}`;
}

export class FlowsFlowCanvas extends PlatformElement {
    static properties = {
        flowId: { type: String },
        skillId: { type: String },
        _viewBox: { state: true },
        _drag: { state: true },
        _connection: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; flex: 1; min-width: 0; min-height: 0; position: relative; overflow: hidden; }
            svg { width: 100%; height: 100%; user-select: none; cursor: default; }
            svg.tool-pan { cursor: grab; }
            svg.tool-pan.panning { cursor: grabbing; }
            .node-rect {
                fill: var(--glass-solid-medium);
                stroke: var(--border-subtle);
                stroke-width: 1.5;
                rx: 8; ry: 8;
                transition: stroke 0.1s, fill 0.1s;
            }
            .node-rect[selected] {
                stroke: var(--accent);
                stroke-width: 2;
            }
            .node-rect:hover {
                fill: var(--glass-solid-strong);
            }
            .node-label {
                fill: var(--text-primary);
                font-size: 12px;
                font-family: var(--font-sans, sans-serif);
                pointer-events: none;
                user-select: none;
            }
            .port {
                fill: var(--accent);
                stroke: white;
                stroke-width: 1;
                cursor: crosshair;
            }
            .port:hover { fill: var(--accent-hover); }
            .edge {
                fill: none;
                stroke: var(--text-tertiary);
                stroke-width: 2;
            }
            .edge:hover { stroke: var(--accent); }
            .edge-temp {
                fill: none;
                stroke: var(--accent);
                stroke-width: 2;
                stroke-dasharray: 4 4;
                pointer-events: none;
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.skillId = 'base';
        this._viewBox = { x: 0, y: 0, w: 1200, h: 800 };
        this._drag = null;
        this._connection = null;
        this._editor = this.useOp('flows/editor');
    }

    _getNodes() {
        const data = this._editor.state?.skillsData;
        return data?.nodes || {};
    }

    _getEdges() {
        const data = this._editor.state?.skillsData;
        return Array.isArray(data?.edges) ? data.edges : [];
    }

    _portCoords(node, side) {
        const x = side === 'in' ? node.pos_x || 0 : (node.pos_x || 0) + NODE_W;
        const y = (node.pos_y || 0) + NODE_H / 2;
        return { x, y };
    }

    _onWheel(e) {
        if (!e.ctrlKey) return;
        e.preventDefault();
        const factor = e.deltaY > 0 ? 1.1 : 0.9;
        const newW = this._viewBox.w * factor;
        const newH = this._viewBox.h * factor;
        const dx = (newW - this._viewBox.w) / 2;
        const dy = (newH - this._viewBox.h) / 2;
        this._viewBox = {
            x: this._viewBox.x - dx,
            y: this._viewBox.y - dy,
            w: newW,
            h: newH,
        };
    }

    _onPointerDownNode(e, nodeId) {
        if (e.button !== 0) return;
        e.stopPropagation();
        this._editor.selectNode({ nodeId });
        const nodes = this._getNodes();
        const node = nodes[nodeId];
        if (!node) return;
        this._drag = {
            type: 'node',
            nodeId,
            startX: e.clientX,
            startY: e.clientY,
            origX: node.pos_x || 0,
            origY: node.pos_y || 0,
        };
        this.renderRoot.querySelector('svg').setPointerCapture(e.pointerId);
    }

    _onPointerDownPort(e, nodeId, side) {
        if (e.button !== 0 || side !== 'out') return;
        e.stopPropagation();
        const node = this._getNodes()[nodeId];
        if (!node) return;
        const start = this._portCoords(node, 'out');
        this._connection = { fromNode: nodeId, x1: start.x, y1: start.y, x2: start.x, y2: start.y };
        this.renderRoot.querySelector('svg').setPointerCapture(e.pointerId);
    }

    _onPointerMove(e) {
        if (this._drag?.type === 'node') {
            const dx = e.clientX - this._drag.startX;
            const dy = e.clientY - this._drag.startY;
            const nodes = { ...this._getNodes() };
            const node = nodes[this._drag.nodeId];
            if (!node) return;
            nodes[this._drag.nodeId] = {
                ...node,
                pos_x: this._drag.origX + dx,
                pos_y: this._drag.origY + dy,
            };
            const data = this._editor.state.skillsData;
            this._editor.updateSkillsData({ data: { ...data, nodes } });
        } else if (this._connection) {
            const svg = this.renderRoot.querySelector('svg');
            const pt = svg.createSVGPoint();
            pt.x = e.clientX;
            pt.y = e.clientY;
            const ctm = svg.getScreenCTM();
            if (!ctm) return;
            const local = pt.matrixTransform(ctm.inverse());
            this._connection = { ...this._connection, x2: local.x, y2: local.y };
        }
    }

    _onPointerUp(e) {
        if (this._drag?.type === 'node') {
            this._editor.pushHistory({ snapshot: { ...this._editor.state.skillsData } });
            this._editor.setDirty({ dirty: true });
        } else if (this._connection) {
            const target = this.renderRoot.elementFromPoint(e.clientX, e.clientY);
            const targetNodeId = target?.dataset?.nodeId;
            const targetSide = target?.dataset?.portSide;
            if (targetNodeId && targetSide === 'in' && targetNodeId !== this._connection.fromNode) {
                const data = this._editor.state.skillsData;
                const edges = [...(data.edges || []), { from_node: this._connection.fromNode, to_node: targetNodeId }];
                this._editor.updateSkillsData({ data: { ...data, edges } });
                this._editor.pushHistory({ snapshot: { ...data, edges } });
                this._editor.setDirty({ dirty: true });
            }
        }
        this._drag = null;
        this._connection = null;
    }

    _onContextMenuNode(e, nodeId) {
        e.preventDefault();
        this.openModal('flows.incoming_policy', { nodeId });
    }

    _onContextMenuEdge(e, edgeIndex) {
        e.preventDefault();
        this.openModal('flows.edge_condition', { edgeIndex });
    }

    _onDragOver(e) {
        if (e.dataTransfer.types.includes('application/x-flow-node-type')) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        }
    }

    _onDrop(e) {
        const nodeType = e.dataTransfer.getData('application/x-flow-node-type');
        if (!nodeType) return;
        e.preventDefault();
        const svg = this.renderRoot.querySelector('svg');
        const pt = svg.createSVGPoint();
        pt.x = e.clientX;
        pt.y = e.clientY;
        const ctm = svg.getScreenCTM();
        if (!ctm) return;
        const local = pt.matrixTransform(ctm.inverse());
        const data = this._editor.state.skillsData || { nodes: {}, edges: [] };
        const id = nodeId();
        const newNode = {
            type: nodeType || NODE_TYPE_DEFAULT,
            name: nodeType,
            pos_x: local.x - NODE_W / 2,
            pos_y: local.y - NODE_H / 2,
            config: {},
        };
        const nodes = { ...(data.nodes || {}), [id]: newNode };
        this._editor.updateSkillsData({ data: { ...data, nodes } });
        this._editor.pushHistory({ snapshot: { ...data, nodes } });
        this._editor.setDirty({ dirty: true });
        this._editor.selectNode({ nodeId: id });
    }

    render() {
        const editorState = this._editor.state || {};
        const skillsData = editorState.skillsData || { nodes: {}, edges: [] };
        const nodes = skillsData.nodes || {};
        const edges = Array.isArray(skillsData.edges) ? skillsData.edges : [];
        const selectedNodeId = editorState.selectedNodeId;
        const activeTool = editorState.activeTool || 'select';
        const vb = `${this._viewBox.x} ${this._viewBox.y} ${this._viewBox.w} ${this._viewBox.h}`;
        return html`
            <svg
                viewBox=${vb}
                class=${activeTool === 'pan' ? 'tool-pan' : ''}
                @wheel=${this._onWheel}
                @pointermove=${this._onPointerMove}
                @pointerup=${this._onPointerUp}
                @dragover=${this._onDragOver}
                @drop=${this._onDrop}
            >
                ${edges.map((edge, i) => {
                    const fromNode = nodes[edge.from_node || edge.from];
                    const toNode = nodes[edge.to_node || edge.to];
                    if (!fromNode || !toNode) return '';
                    const start = this._portCoords(fromNode, 'out');
                    const end = this._portCoords(toNode, 'in');
                    return html`
                        <path
                            class="edge"
                            d=${pathFor(start.x, start.y, end.x, end.y)}
                            @contextmenu=${(e) => this._onContextMenuEdge(e, i)}
                        ></path>
                    `;
                })}
                ${this._connection
                    ? html`<path class="edge-temp" d=${pathFor(this._connection.x1, this._connection.y1, this._connection.x2, this._connection.y2)}></path>`
                    : ''}
                ${Object.entries(nodes).map(([id, node]) => {
                    const x = node.pos_x || 0;
                    const y = node.pos_y || 0;
                    return html`
                        <g
                            transform=${`translate(${x}, ${y})`}
                            @pointerdown=${(e) => this._onPointerDownNode(e, id)}
                            @contextmenu=${(e) => this._onContextMenuNode(e, id)}
                        >
                            <rect
                                class="node-rect"
                                x="0" y="0" width=${NODE_W} height=${NODE_H}
                                ?selected=${selectedNodeId === id}
                            ></rect>
                            <text class="node-label" x="12" y="22">${node.name || id}</text>
                            <text class="node-label" x="12" y="40" style="opacity:0.6;font-size:10px">${node.type || ''}</text>
                            <circle
                                class="port"
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
                })}
            </svg>
        `;
    }
}

customElements.define('flows-flow-canvas', FlowsFlowCanvas);
