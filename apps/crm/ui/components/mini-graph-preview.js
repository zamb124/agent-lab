import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import { createGraphTextSprite, createMatteSphereNodeGroup } from './graph-3d-helpers.js';

const API_MAX_DEPTH = 5;
const MINI_NODE_REL_SIZE = 4;

function _resolveNodeColor(node) {
    if (node.access === false) {
        return '#7f7f8f';
    }
    const entityType = typeof node.entity_type === 'string' ? node.entity_type.trim() : '';
    if (!entityType) {
        return '#bca8ff';
    }
    const entityTypes = CRMStore.state.entities.entityTypes;
    if (!Array.isArray(entityTypes)) {
        return '#bca8ff';
    }
    const match = entityTypes.find((t) => t.type_id === entityType);
    if (!match || typeof match.color !== 'string' || !match.color.trim()) {
        return '#bca8ff';
    }
    return match.color.trim();
}

function _normalizeLevel(rawNode, rootEntityId, nodeId) {
    if (typeof rawNode.level === 'number' && Number.isFinite(rawNode.level)) {
        return Math.max(0, Math.floor(rawNode.level));
    }
    if (nodeId === rootEntityId) {
        return 0;
    }
    return 1;
}

function _edgeDirected(edge) {
    if (typeof edge.is_directed === 'boolean') {
        return edge.is_directed;
    }
    if (typeof edge.directed === 'boolean') {
        return edge.directed;
    }
    return false;
}

function _relationshipTypeLabel(typeId) {
    if (typeof typeId !== 'string' || typeId.trim().length === 0) {
        return 'related';
    }
    const types = CRMStore.state.entities.relationshipTypes;
    if (!Array.isArray(types)) {
        return typeId;
    }
    const match = types.find((t) => t.type_id === typeId);
    if (match && typeof match.name === 'string' && match.name.trim().length > 0) {
        return match.name.trim();
    }
    return typeId;
}

export class MiniGraphPreview extends PlatformElement {
    static properties = {
        entityId: { type: String },
        maxDepth: { type: Number },
        initialDisplayDepth: { type: Number },
        fillContainer: { type: Boolean, reflect: true },
        width: { type: String },
        height: { type: String },
        _loading: { state: true },
        _error: { state: true },
        _fetchedNodes: { state: true },
        _fetchedEdges: { state: true },
        _displayDepth: { state: true },
    };

    static styles = [
        ...PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                border-radius: 12px;
                overflow: hidden;
                border: 1px solid var(--glass-border-subtle);
                min-height: 0;
            }

            :host([fill-container]) {
                flex: 1 1 auto;
                min-height: 0;
                height: auto;
                max-height: 100%;
                align-self: stretch;
            }

            .mini-depth-toolbar {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                flex-shrink: 0;
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
            }

            .mini-depth-label {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                min-width: 7rem;
                text-align: center;
            }

            .mini-depth-btn {
                width: 32px;
                height: 32px;
                border: none;
                border-radius: var(--radius-full);
                background: var(--glass-tint-medium);
                color: var(--text-primary);
                font-size: 18px;
                line-height: 1;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .mini-depth-btn:hover:not(:disabled) {
                background: var(--glass-tint-strong);
            }

            .mini-depth-btn:disabled {
                opacity: 0.35;
                cursor: not-allowed;
            }

            .mini-canvas-wrap {
                flex: 1;
                min-height: 120px;
                position: relative;
            }

            .mini-canvas {
                position: absolute;
                inset: 0;
                width: 100%;
                height: 100%;
            }

            .mini-empty {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-tertiary);
                font-size: 12px;
            }
        `,
    ];

    constructor() {
        super();
        this.entityId = '';
        this.maxDepth = API_MAX_DEPTH;
        this.initialDisplayDepth = 1;
        this.fillContainer = false;
        this.width = '100%';
        this.height = '240px';
        this._loading = false;
        this._error = '';
        this._fetchedNodes = [];
        this._fetchedEdges = [];
        this._displayDepth = 1;
        this._graphInstance = null;
        this._resizeObserver = null;
    }

    firstUpdated() {
        super.firstUpdated?.();
        if (this.entityId) {
            this._loadAndRender();
        }
    }

    updated(changed) {
        if (changed.has('entityId')) {
            if (!this.entityId) {
                this._destroyGraph();
                this._fetchedNodes = [];
                this._fetchedEdges = [];
                this._error = '';
                this._loading = false;
            } else {
                const prev = changed.get('entityId');
                if (prev !== undefined && prev !== this.entityId) {
                    this._loadAndRender();
                }
            }
            return;
        }
        if (changed.has('maxDepth') && this.entityId) {
            this._loadAndRender();
            return;
        }
        if (changed.has('_displayDepth') && this._graphInstance) {
            this._syncFilteredGraphData();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._destroyGraph();
    }

    _getFetchDepth() {
        const n = this.maxDepth;
        if (typeof n !== 'number' || !Number.isFinite(n)) {
            return API_MAX_DEPTH;
        }
        return Math.min(API_MAX_DEPTH, Math.max(1, Math.floor(n)));
    }

    _getMaxLevelInFetched() {
        const root = this.entityId;
        const nodes = Array.isArray(this._fetchedNodes) ? this._fetchedNodes : [];
        if (nodes.length === 0) {
            return 0;
        }
        let maxL = 0;
        for (const raw of nodes) {
            const id = raw.entity_id || raw.id;
            if (typeof id !== 'string') {
                continue;
            }
            const level = _normalizeLevel(raw, root, id);
            if (level > maxL) {
                maxL = level;
            }
        }
        return maxL;
    }

    _clampInitialDisplayDepth() {
        const maxL = this._getMaxLevelInFetched();
        const initial = typeof this.initialDisplayDepth === 'number' && Number.isFinite(this.initialDisplayDepth)
            ? Math.floor(this.initialDisplayDepth)
            : 1;
        let d = Math.max(1, initial);
        if (maxL > 0) {
            d = Math.min(d, maxL);
        }
        this._displayDepth = d;
    }

    async _loadAndRender() {
        if (!this.entityId) {
            return;
        }
        this._loading = true;
        this._error = '';
        this._destroyGraph();
        try {
            const response = await this.crmApi.getInfluenceGraph(this.entityId, { max_depth: this._getFetchDepth() });
            const nodes = Array.isArray(response.nodes) ? response.nodes : [];
            const edges = Array.isArray(response.edges) ? response.edges : [];
            this._fetchedNodes = nodes;
            this._fetchedEdges = edges;
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this._error = message;
            this._fetchedNodes = [];
            this._fetchedEdges = [];
            this._loading = false;
            return;
        }
        this._loading = false;
        if (this._fetchedNodes.length === 0) {
            return;
        }
        this._clampInitialDisplayDepth();
        await this.updateComplete;
        this._initGraph();
    }

    _normalizeSceneNodes() {
        const root = this.entityId;
        return this._fetchedNodes.map((raw) => {
            const id = raw.entity_id || raw.id;
            if (typeof id !== 'string' || id.trim().length === 0) {
                throw new Error('Graph node must have entity_id or id');
            }
            const level = _normalizeLevel(raw, root, id);
            const isCenter = id === root;
            return {
                ...raw,
                id,
                name: raw.name || raw.label || id,
                color: _resolveNodeColor(raw),
                size: isCenter ? 2.4 : 1.2,
                level,
            };
        });
    }

    _buildSceneData(displayDepth) {
        const allNodes = this._normalizeSceneNodes();
        const visibleNodes = allNodes.filter((n) => n.level <= displayDepth);
        const visibleIds = new Set(visibleNodes.map((n) => n.id));

        const sceneLinks = [];
        for (const edge of this._fetchedEdges) {
            const source = edge.source_id || edge.source_entity_id || edge.source;
            const target = edge.target_id || edge.target_entity_id || edge.target;
            if (typeof source !== 'string' || typeof target !== 'string') {
                continue;
            }
            if (!visibleIds.has(source) || !visibleIds.has(target)) {
                continue;
            }
            const directed = _edgeDirected(edge);
            const relationType = edge.relationship_type || edge.type || 'related';
            sceneLinks.push({
                source,
                target,
                directed,
                relation_type: relationType,
            });
        }

        return { nodes: visibleNodes, links: sceneLinks };
    }

    _syncFilteredGraphData() {
        if (!this._graphInstance) {
            return;
        }
        const maxL = this._getMaxLevelInFetched();
        let depth = this._displayDepth;
        if (maxL > 0) {
            depth = Math.min(depth, maxL);
        }
        depth = Math.max(1, depth);
        if (depth !== this._displayDepth) {
            this._displayDepth = depth;
        }
        const { nodes, links } = this._buildSceneData(depth);
        if (nodes.length === 1) {
            nodes[0].x = 0;
            nodes[0].y = 0;
            nodes[0].z = 0;
            nodes[0].fx = 0;
            nodes[0].fy = 0;
            nodes[0].fz = 0;
        }
        this._graphInstance.graphData({ nodes, links });
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                this._applyGraphContainerSize();
            });
        });
    }

    _applyGraphContainerSize() {
        if (!this._graphInstance) {
            return;
        }
        const canvasEl = this.renderRoot?.querySelector('.mini-canvas');
        if (!canvasEl) {
            return;
        }
        const w = Math.max(1, Math.floor(canvasEl.clientWidth));
        const h = Math.max(1, Math.floor(canvasEl.clientHeight));
        this._graphInstance.width(w);
        this._graphInstance.height(h);
    }

    _initGraph() {
        const factory = window.ForceGraph3D;
        if (typeof factory !== 'function') {
            throw new Error('ForceGraph3D is not available in window');
        }
        const wrap = this.renderRoot?.querySelector('.mini-canvas-wrap');
        const container = this.renderRoot?.querySelector('.mini-canvas');
        if (!wrap || !container) {
            throw new Error('Mini graph canvas container not found');
        }
        const canvasBg = getComputedStyle(document.documentElement)
            .getPropertyValue('--bg-secondary').trim() || '#1a1a2e';
        const labelColor = getComputedStyle(document.documentElement)
            .getPropertyValue('--text-primary').trim() || '#f0f4ff';
        const linkLabelColor = getComputedStyle(document.documentElement)
            .getPropertyValue('--text-secondary').trim() || '#d4dae8';

        const { nodes: sceneNodes, links: sceneLinks } = this._buildSceneData(this._displayDepth);

        const linkBaseColor = '#9ba3bf';
        const linkDirectedColor = '#41d36d';

        this._graphInstance = factory()(container)
            .backgroundColor(canvasBg)
            .width(container.clientWidth)
            .height(container.clientHeight)
            .showNavInfo(false)
            .cooldownTicks(60)
            .warmupTicks(40)
            .nodeRelSize(MINI_NODE_REL_SIZE)
            .nodeColor((n) => n.color)
            .nodeVal((n) => n.size)
            .nodeLabel(() => '')
            .nodeThreeObject((node) => createMatteSphereNodeGroup(node, {
                nodeRelSize: MINI_NODE_REL_SIZE,
                labelColor,
                labelFontSize: 16,
            }))
            .nodeThreeObjectExtend(false)
            .linkColor((link) => (link.directed ? linkDirectedColor : linkBaseColor))
            .linkWidth((link) => (link.directed ? 0.9 : 0.6))
            .linkOpacity((link) => (link.directed ? 0.75 : 0.45))
            .linkDirectionalArrowLength((link) => (link.directed ? 7 : 0))
            .linkDirectionalArrowRelPos(0.88)
            .linkDirectionalArrowColor((link) => (link.directed ? linkDirectedColor : linkBaseColor))
            .linkDirectionalParticles((link) => (link.directed ? 2 : 0))
            .linkDirectionalParticleWidth(1.2)
            .linkDirectionalParticleSpeed(0.006)
            .linkThreeObjectExtend(true)
            .linkThreeObject((link) => {
                const typeKey = link.relation_type || 'related';
                const label = _relationshipTypeLabel(typeKey);
                return createGraphTextSprite(label, linkLabelColor, 13, 24);
            })
            .linkPositionUpdate((sprite, { start, end }) => {
                if (!sprite || !start || !end) {
                    return false;
                }
                const mx = start.x + (end.x - start.x) / 2;
                const my = start.y + (end.y - start.y) / 2;
                const mz = start.z + (end.z - start.z) / 2;
                sprite.position.set(mx, my, mz);
                return true;
            })
            .enableNodeDrag(true)
            .onNodeClick((node) => {
                this.emit('entity-open', { entityId: node.id });
            })
            .onNodeDragEnd((node) => {
                node.fx = node.x;
                node.fy = node.y;
                node.fz = 0;
            })
            .onEngineStop(() => {
                if (!this._graphInstance) {
                    return;
                }
                this._flattenZ();
            })
            .graphData({ nodes: sceneNodes, links: sceneLinks });

        this._graphInstance.d3Force('flatZ', () => {
            const gd = this._graphInstance.graphData();
            if (!gd?.nodes) {
                return;
            }
            gd.nodes.forEach((n) => { n.z = 0; n.fz = 0; });
        });

        requestAnimationFrame(() => {
            if (!this._graphInstance) {
                return;
            }
            const camera = this._graphInstance.camera();
            camera.position.set(0, 0, 280);
            camera.lookAt(0, 0, 0);
            const controls = this._graphInstance.controls();
            if (controls) {
                controls.enableRotate = false;
            }
            this._applyGraphContainerSize();
            this._setupGraphResizeObserver();
        });
    }

    _flattenZ() {
        if (!this._graphInstance) {
            return;
        }
        const gd = this._graphInstance.graphData();
        if (!gd?.nodes) {
            return;
        }
        gd.nodes.forEach((n) => { n.z = 0; n.fz = 0; });
    }

    _teardownGraphResizeObserver() {
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
    }

    _setupGraphResizeObserver() {
        this._teardownGraphResizeObserver();
        const wrap = this.renderRoot?.querySelector('.mini-canvas-wrap');
        if (!wrap || !this._graphInstance) {
            return;
        }
        this._resizeObserver = new ResizeObserver(() => {
            this._applyGraphContainerSize();
        });
        this._resizeObserver.observe(wrap);
    }

    _destroyGraph() {
        this._teardownGraphResizeObserver();
        if (this._graphInstance) {
            this._graphInstance._destructor?.();
            this._graphInstance = null;
        }
    }

    _onDecreaseDepth() {
        if (this._displayDepth <= 1) {
            return;
        }
        this._displayDepth -= 1;
    }

    _onIncreaseDepth() {
        const maxL = this._getMaxLevelInFetched();
        if (maxL <= 0) {
            return;
        }
        if (this._displayDepth >= maxL) {
            return;
        }
        this._displayDepth += 1;
    }

    render() {
        const fill = this.fillContainer === true;
        const boxHeight = fill ? '100%' : this.height;
        const boxFlex = fill ? 'flex:1 1 auto;min-height:0;' : '';
        const boxStyle = `width:${this.width};height:${boxHeight};${boxFlex}display:flex;flex-direction:column;box-sizing:border-box;`;
        const maxL = this._getMaxLevelInFetched();
        const canDecrease = this._displayDepth > 1;
        const canIncrease = maxL > 0 && this._displayDepth < maxL;

        if (this._loading) {
            return html`<div style="${boxStyle}" class="mini-empty">Загрузка графа...</div>`;
        }
        if (this._error) {
            return html`<div style="${boxStyle}" class="mini-empty">${this._error}</div>`;
        }
        if (!this._loading && this._fetchedNodes.length === 0 && this.entityId) {
            return html`<div style="${boxStyle}" class="mini-empty">Нет связей</div>`;
        }

        const depthCap = Math.max(maxL, 1);
        const depthLabel = `Уровень ${this._displayDepth} из ${depthCap}`;

        return html`
            <div style="${boxStyle}">
                <div class="mini-depth-toolbar">
                    <button
                        type="button"
                        class="mini-depth-btn"
                        title="Меньше уровней"
                        ?disabled=${!canDecrease}
                        @click=${this._onDecreaseDepth}
                    >\u2212</button>
                    <span class="mini-depth-label">${depthLabel}</span>
                    <button
                        type="button"
                        class="mini-depth-btn"
                        title="Больше уровней"
                        ?disabled=${!canIncrease}
                        @click=${this._onIncreaseDepth}
                    >+</button>
                </div>
                <div class="mini-canvas-wrap">
                    <div class="mini-canvas"></div>
                </div>
            </div>
        `;
    }
}

customElements.define('mini-graph-preview', MiniGraphPreview);
