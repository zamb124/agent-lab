/**
 * crm-mini-graph — компактный граф влияния (3D или mind map), один запрос influence на max depth.
 *
 * Локальные кнопки +/- глубины меняют только отображаемую глубину без повторного запроса.
 * В mindmap-режиме рядом с глубиной — блок управления масштабом превью (`compactZoom`,
 * диапазон 0.5..3): кнопки `−` / процент-с-кликом-на-сброс / `+`. Текущее значение
 * прокидывается в `<crm-mindmap-canvas .compactZoom=${...}>`; событие `compact-zoom-change`
 * от canvas (Ctrl/⌘ + колесо) обновляет локальный state.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import {
    aggregateIncidentWeightsByNode,
    computeGraphNodeDisplaySize,
    createGraphLinkLabelPlane,
    createMatteSphereNodeGroup,
    maxIncidentWeightOrOne,
    positionGraphLinkLabelMesh,
} from './graph-3d-helpers.js';
import {
    buildEntityTypeColorMapFromItems,
    buildEntityTypeIconMapFromItems,
} from '../utils/crm-entity-type-visuals.js';
import { buildRelationshipTypeLabelMapFromItems } from '../utils/crm-relationship-type-labels.js';
import { buildGraphWorkspaceSearch } from '../utils/graph-view-mode.js';
import './mindmap-canvas.js';

const API_MAX_DEPTH = 5;
const MINI_NODE_REL_SIZE = 4;

export class CRMMiniGraph extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        entityId: { type: String },
        namespace: { type: String },
        /** @type {'3d' | 'mindmap'} */
        viewMode: { type: String },
        maxDepth: { type: Number },
        initialDisplayDepth: { type: Number },
        fillContainer: { type: Boolean, reflect: true, attribute: 'fill-container' },
        width: { type: String },
        height: { type: String },
        _displayDepth: { state: true },
        _fitNonce: { state: true },
        _compactZoom: { state: true },
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
                width: 100%;
                height: var(--mini-graph-host-height, 240px);
                min-height: 0;
                box-sizing: border-box;
            }

            :host([fill-container]) {
                flex: 1 1 0%;
                min-width: 0;
                min-height: 0;
                width: 100%;
                height: 100%;
                max-height: none;
                align-self: stretch;
            }

            .mini-box {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                box-sizing: border-box;
                min-height: 0;
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

            .mini-toolbar-sep {
                width: 1px;
                align-self: stretch;
                background: var(--glass-border-subtle);
                margin: 4px 4px;
            }

            .mini-zoom-label {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                min-width: 3rem;
                text-align: center;
                cursor: pointer;
            }

            .mini-zoom-label:hover {
                color: var(--text-primary);
            }

            .mini-canvas-wrap {
                flex: 1 1 0%;
                min-height: 0;
                min-width: 0;
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

            .mini-footer {
                display: flex;
                justify-content: flex-end;
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
                flex-shrink: 0;
            }

            .mini-open-full {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 6px 12px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-xs);
                font-weight: 600;
                cursor: pointer;
            }

            .mini-open-full:hover {
                background: var(--glass-solid-strong);
            }
        `,
    ];

    constructor() {
        super();
        this.entityId = '';
        this.namespace = '';
        this.viewMode = 'mindmap';
        this.maxDepth = API_MAX_DEPTH;
        this.initialDisplayDepth = 1;
        this.fillContainer = false;
        this.width = '100%';
        this.height = '240px';
        this._displayDepth = 1;
        this._fitNonce = 0;
        this._compactZoom = 1;
        this._graphInstance = null;
        this._resizeObserver = null;
        this._graphOp = this.useOp('crm/influence_graph');
        this._entityTypes = this.useResource('crm/entity_types', { autoload: false });
        this._relationshipTypes = this.useResource('crm/relationship_types', { autoload: true });
        /** Ответ GET influence-graph только для текущего экземпляра (общий slice lastResult перетирается чужими запросами). */
        this._graphPayload = null;
    }

    _syncEntityTypesForNamespace() {
        const raw = typeof this.namespace === 'string' ? this.namespace.trim() : '';
        if (raw.length === 0) {
            return;
        }
        this._entityTypes.load({ namespace: raw });
    }

    firstUpdated() {
        super.firstUpdated?.();
        this._syncEntityTypesForNamespace();
        if (this._trimEntityId().length > 0) {
            this._loadGraph();
        }
    }

    updated(changed) {
        if (changed.has('namespace')) {
            this._syncEntityTypesForNamespace();
        }
        if (changed.has('entityId')) {
            const prevRaw = changed.get('entityId');
            const prev = typeof prevRaw === 'string' ? prevRaw.trim() : '';
            const cur = this._trimEntityId();
            this._compactZoom = 1;
            if (cur.length === 0) {
                this._destroyGraphState();
            } else if (prev !== cur) {
                this._loadGraph();
            }
            return;
        }
        if (changed.has('viewMode')) {
            this._teardownThreeGraph();
            this._fitNonce += 1;
            this._compactZoom = 1;
            const id = this._trimEntityId();
            if (this.viewMode === '3d' && this._graphPayload && id.length > 0) {
                void this.updateComplete.then(() =>
                    this._ensureThree().then(() => {
                        if (this._trimEntityId() === id && this.viewMode === '3d') {
                            this._initGraph();
                        }
                    }),
                );
            }
            return;
        }
        if (changed.has('_displayDepth')) {
            if (this.viewMode === 'mindmap') {
                this._fitNonce += 1;
            } else if (this._graphInstance) {
                this._syncFilteredGraphData();
            }
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._destroyGraphState();
    }

    _resolveNodeColor(node) {
        if (node.access === false) {
            return '#7f7f8f';
        }
        const entityType = typeof node.entity_type === 'string' ? node.entity_type.trim() : '';
        if (!entityType) {
            return '#bca8ff';
        }
        const types = this._entityTypes.items;
        const match = types.find((t) => t.type_id === entityType);
        if (!match || typeof match.color !== 'string' || !match.color.trim()) {
            return '#bca8ff';
        }
        return match.color.trim();
    }

    _normalizeLevel(rawNode, rootEntityId, nodeId) {
        if (typeof rawNode.level === 'number' && Number.isFinite(rawNode.level)) {
            return Math.max(0, Math.floor(rawNode.level));
        }
        if (nodeId === rootEntityId) {
            return 0;
        }
        return 1;
    }

    _edgeDirected(edge) {
        if (typeof edge.is_directed === 'boolean') {
            return edge.is_directed;
        }
        if (typeof edge.directed === 'boolean') {
            return edge.directed;
        }
        return false;
    }

    _relationshipTypeLabel(typeId) {
        if (typeof typeId !== 'string' || typeId.trim().length === 0) {
            return 'related';
        }
        const types = this._relationshipTypes.items;
        const match = types.find((t) => t.type_id === typeId);
        if (match && typeof match.name === 'string' && match.name.trim().length > 0) {
            return match.name.trim();
        }
        return typeId;
    }

    _getFetchDepth() {
        return API_MAX_DEPTH;
    }

    _getFetchedNodes() {
        const result = this._graphPayload;
        if (!result || !Array.isArray(result.nodes)) {
            return [];
        }
        return result.nodes;
    }

    _getFetchedEdges() {
        const result = this._graphPayload;
        if (!result || !Array.isArray(result.edges)) {
            return [];
        }
        return result.edges;
    }

    _getMaxLevelInFetched() {
        const root = this._trimEntityId();
        const nodes = this._getFetchedNodes();
        if (nodes.length === 0) {
            return 0;
        }
        let maxL = 0;
        for (const raw of nodes) {
            const id = raw.entity_id || raw.id;
            if (typeof id !== 'string') {
                continue;
            }
            const level = this._normalizeLevel(raw, root, id);
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

    _trimEntityId() {
        return typeof this.entityId === 'string' ? this.entityId.trim() : '';
    }

    _openFullWorkspace() {
        const id = this._trimEntityId();
        if (id.length === 0) {
            throw new Error('CRMMiniGraph: entityId required for full graph workspace');
        }
        const vm = this._resolvedViewMode();
        const search = buildGraphWorkspaceSearch({
            view: vm,
            root: id,
            depth: null,
            query: '',
        });
        this.navigate('graph', {}, { search });
    }

    _resolvedViewMode() {
        const v = this.viewMode;
        if (v === '3d' || v === 'mindmap') {
            return v;
        }
        throw new Error('CRMMiniGraph: viewMode must be 3d or mindmap');
    }

    /**
     * Кастомные узлы (sphere + спрайты подписей) берут THREE с window.
     * Инициализация графа идёт после отложенного import three в index.html —
     * при первом открытии вкладки к моменту _initGraph окно может быть ещё без THREE.
     */
    async _ensureThree() {
        if (typeof window === 'undefined') {
            throw new Error('CRMMiniGraph._ensureThree: window is not available');
        }
        if (window.THREE && typeof window.THREE.SphereGeometry === 'function') {
            return;
        }
        const mod = await import('/crm/ui/vendor/three/three.module.min.js');
        window.THREE = mod;
    }

    async _loadGraph() {
        const id = this._trimEntityId();
        if (id.length === 0) {
            return;
        }
        this._destroyGraphState();
        const graphResult = await this._graphOp.run({
            entityId: id,
            params: { max_depth: this._getFetchDepth() },
        });
        const current = this._trimEntityId();
        if (current !== id) {
            return;
        }
        if (graphResult === null || typeof graphResult !== 'object') {
            return;
        }
        if (typeof graphResult.root_entity_id !== 'string' || graphResult.root_entity_id !== id) {
            return;
        }
        const nodes = Array.isArray(graphResult.nodes) ? graphResult.nodes : [];
        if (nodes.length === 0) {
            return;
        }
        this._graphPayload = graphResult;
        this._clampInitialDisplayDepth();
        this.requestUpdate();
        await this.updateComplete;
        if (this._trimEntityId() !== id) {
            return;
        }
        const vm = this._resolvedViewMode();
        if (vm === '3d') {
            await this._ensureThree();
            if (this._trimEntityId() !== id) {
                return;
            }
            this._initGraph();
        } else {
            this._fitNonce += 1;
        }
    }

    _normalizeSceneNodes() {
        const root = this._trimEntityId();
        if (root.length === 0) {
            throw new Error('CRMMiniGraph._normalizeSceneNodes: entityId required');
        }
        return this._getFetchedNodes().map((raw) => {
            const id = raw.entity_id || raw.id;
            if (typeof id !== 'string' || id.trim().length === 0) {
                throw new Error('Graph node must have entity_id or id');
            }
            const level = this._normalizeLevel(raw, root, id);
            return {
                ...raw,
                id,
                name: raw.name || raw.label || id,
                color: this._resolveNodeColor(raw),
                level,
            };
        });
    }

    _buildSceneData(displayDepth) {
        const allNodes = this._normalizeSceneNodes();
        const visibleNodes = allNodes.filter((n) => n.level <= displayDepth);
        const visibleIds = new Set(visibleNodes.map((n) => n.id));

        const sceneLinks = [];
        for (const edge of this._getFetchedEdges()) {
            const source = edge.source_id || edge.source_entity_id || edge.source;
            const target = edge.target_id || edge.target_entity_id || edge.target;
            if (typeof source !== 'string' || typeof target !== 'string') {
                continue;
            }
            if (!visibleIds.has(source) || !visibleIds.has(target)) {
                continue;
            }
            const directed = this._edgeDirected(edge);
            const relationType = edge.relationship_type || edge.type || 'related';
            const edgeWeight = typeof edge.weight === 'number' && Number.isFinite(edge.weight) ? edge.weight : 1;
            sceneLinks.push({
                source,
                target,
                directed,
                relation_type: relationType,
                weight: edgeWeight,
            });
        }

        const weightByNode = aggregateIncidentWeightsByNode(sceneLinks);
        const maxW = maxIncidentWeightOrOne(weightByNode);
        const nodesWithSize = visibleNodes.map((n) => {
            const total = weightByNode.get(n.id) || 0;
            const rawLevel = typeof n.level === 'number' && Number.isFinite(n.level) ? n.level : 1;
            const sizingLevel = rawLevel === 0 ? 0 : 1;
            const size = computeGraphNodeDisplaySize(sizingLevel, total, maxW);
            let graph_weight_subtitle = '';
            if (total > 0) {
                const value = total.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 });
                graph_weight_subtitle = this.t('graph_page.incident_weight_subtitle', { value });
            }
            return { ...n, size, graph_weight_subtitle };
        });

        return { nodes: nodesWithSize, links: sceneLinks };
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
            .nodeThreeObject((node) => {
                const subtitleColor = getComputedStyle(document.documentElement)
                    .getPropertyValue('--text-secondary').trim() || '#d4dae8';
                return createMatteSphereNodeGroup(node, {
                    nodeRelSize: MINI_NODE_REL_SIZE,
                    labelColor,
                    subtitleColor,
                    labelFontSize: 16,
                });
            })
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
                const label = this._relationshipTypeLabel(typeKey);
                return createGraphLinkLabelPlane(label, linkLabelColor, 13, 26);
            })
            .linkPositionUpdate((mesh, { start, end }) => {
                if (!mesh || !start || !end) {
                    return false;
                }
                const cam = this._graphInstance
                    ? this._graphInstance.cameraPosition()
                    : null;
                return positionGraphLinkLabelMesh(mesh, start, end, cam);
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
            const inst = this._graphInstance;
            if (!inst) {
                return;
            }
            const gd = inst.graphData();
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

    _teardownThreeGraph() {
        this._teardownGraphResizeObserver();
        if (this._graphInstance) {
            this._graphInstance._destructor?.();
            this._graphInstance = null;
        }
    }

    _destroyGraphState() {
        this._graphPayload = null;
        this._teardownThreeGraph();
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

    _clampCompactZoom(value) {
        const num = typeof value === 'number' && Number.isFinite(value) ? value : 1;
        return Math.max(0.5, Math.min(3, num));
    }

    _onCompactZoomOut() {
        const next = this._clampCompactZoom(this._compactZoom / 1.25);
        if (next === this._compactZoom) {
            return;
        }
        this._compactZoom = next;
    }

    _onCompactZoomIn() {
        const next = this._clampCompactZoom(this._compactZoom * 1.25);
        if (next === this._compactZoom) {
            return;
        }
        this._compactZoom = next;
    }

    _onCompactZoomReset() {
        if (this._compactZoom === 1) {
            return;
        }
        this._compactZoom = 1;
    }

    _onMindmapCompactZoomChange(e) {
        const detail = e?.detail;
        const value = detail && typeof detail === 'object' ? detail.value : null;
        if (typeof value !== 'number' || !Number.isFinite(value)) {
            return;
        }
        this._compactZoom = this._clampCompactZoom(value);
    }

    _mindmapDisplayPayload() {
        const root = this._trimEntityId();
        const payload = this._graphPayload;
        if (!payload || root.length === 0) {
            return { nodes: [], edges: [], rootId: root };
        }
        const nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
        const edges = Array.isArray(payload.edges) ? payload.edges : [];
        const depth = this._displayDepth;
        const graded = [];
        for (const raw of nodes) {
            const id = raw.entity_id || raw.id;
            if (typeof id !== 'string') {
                continue;
            }
            graded.push({
                raw,
                id,
                level: this._normalizeLevel(raw, root, id),
            });
        }
        const visibleIds = new Set(
            graded.filter((x) => x.level <= depth).map((x) => x.id),
        );
        const outNodes = graded.filter((x) => visibleIds.has(x.id)).map((x) => x.raw);
        const outEdges = edges.filter((e) => {
            const s = e.source_id || e.source_entity_id || e.source;
            const t = e.target_id || e.target_entity_id || e.target;
            return (
                typeof s === 'string'
                && typeof t === 'string'
                && visibleIds.has(s)
                && visibleIds.has(t)
            );
        });
        return { nodes: outNodes, edges: outEdges, rootId: root };
    }

    _onMindmapNodeDblClick(e) {
        const node = e.detail && e.detail.node;
        if (!node || typeof node.id !== 'string' || node.id.length === 0) {
            return;
        }
        let entityType = '';
        const payload = this._graphPayload;
        const nodes = payload && Array.isArray(payload.nodes) ? payload.nodes : [];
        const row = nodes.find((raw) => {
            const rid = raw && (raw.entity_id || raw.id);
            return typeof rid === 'string' && rid === node.id;
        });
        if (row && typeof row.entity_type === 'string' && row.entity_type.length > 0) {
            entityType = row.entity_type;
        }
        this.emit('entity-open', { entityId: node.id, entity_type: entityType });
    }

    render() {
        const maxL = this._getMaxLevelInFetched();
        const canDecrease = this._displayDepth > 1;
        const canIncrease = maxL > 0 && this._displayDepth < maxL;
        const fetchedNodes = this._getFetchedNodes();
        const error = this._graphOp.error;
        const entityIdTrim = this._trimEntityId();
        const vm = this._resolvedViewMode();

        if (entityIdTrim.length === 0) {
            return html`<div class="mini-box mini-empty">${this.t('graph.empty_need_entity')}</div>`;
        }

        const footerBtn = html`
            <button type="button" class="mini-open-full" @click=${() => this._openFullWorkspace()}>
                <platform-icon name="fullscreen" size="14"></platform-icon>
                ${this.t('graph.mini_open_full')}
            </button>
        `;

        if (this._graphOp.busy) {
            return html`
                <div class="mini-box">
                    <div class="mini-empty" style="flex:1;min-height:0;">${this.t('graph.mini_loading')}</div>
                    <div class="mini-footer">${footerBtn}</div>
                </div>
            `;
        }
        if (error) {
            return html`
                <div class="mini-box">
                    <div class="mini-empty" style="flex:1;min-height:0;">${error}</div>
                    <div class="mini-footer">${footerBtn}</div>
                </div>
            `;
        }
        if (fetchedNodes.length === 0) {
            return html`
                <div class="mini-box">
                    <div class="mini-empty" style="flex:1;min-height:0;">${this.t('graph.mini_no_edges')}</div>
                    <div class="mini-footer">${footerBtn}</div>
                </div>
            `;
        }

        const depthCap = Math.max(maxL, 1);
        const depthLabel = this.t('graph.mini_depth_level', {
            current: String(this._displayDepth),
            max: String(depthCap),
        });

        const zoomPercent = Math.round(this._compactZoom * 100);
        const canZoomOut = this._compactZoom > 0.5 + 0.001;
        const canZoomIn = this._compactZoom < 3 - 0.001;
        const zoomBlock = vm === 'mindmap'
            ? html`
                  <span class="mini-toolbar-sep" aria-hidden="true"></span>
                  <button
                      type="button"
                      class="mini-depth-btn"
                      title=${this.t('graph.mini_zoom_out')}
                      ?disabled=${!canZoomOut}
                      @click=${this._onCompactZoomOut}
                  >\u2212</button>
                  <span
                      class="mini-zoom-label"
                      title=${this.t('graph.mini_zoom_reset')}
                      @click=${this._onCompactZoomReset}
                  >${zoomPercent}%</span>
                  <button
                      type="button"
                      class="mini-depth-btn"
                      title=${this.t('graph.mini_zoom_in')}
                      ?disabled=${!canZoomIn}
                      @click=${this._onCompactZoomIn}
                  >+</button>
              `
            : nothing;

        const toolbar = html`
            <div class="mini-depth-toolbar">
                <button
                    type="button"
                    class="mini-depth-btn"
                    title=${this.t('graph.mini_depth_less')}
                    ?disabled=${!canDecrease}
                    @click=${this._onDecreaseDepth}
                >\u2212</button>
                <span class="mini-depth-label">${depthLabel}</span>
                <button
                    type="button"
                    class="mini-depth-btn"
                    title=${this.t('graph.mini_depth_more')}
                    ?disabled=${!canIncrease}
                    @click=${this._onIncreaseDepth}
                >+</button>
                ${zoomBlock}
            </div>
        `;

        if (vm === 'mindmap') {
            const mm = this._mindmapDisplayPayload();
            const colorMap = buildEntityTypeColorMapFromItems(this._entityTypes.items);
            const iconMap = buildEntityTypeIconMapFromItems(this._entityTypes.items);
            const colorsPlain = Object.fromEntries(colorMap);
            const iconsPlain = Object.fromEntries(iconMap);
            const relLabelsPlain = buildRelationshipTypeLabelMapFromItems(this._relationshipTypes.items);
            const showMm =
                mm.nodes.length > 0
                && typeof mm.rootId === 'string'
                && mm.rootId.length > 0;
            return html`
                <div class="mini-box">
                    ${toolbar}
                    <div class="mini-canvas-wrap" style="min-height:180px;">
                        ${showMm
                            ? html`
                                  <crm-mindmap-canvas
                                      compact
                                      .graphNodes=${mm.nodes}
                                      .graphEdges=${mm.edges}
                                      .rootEntityId=${mm.rootId}
                                      .entityTypeColors=${colorsPlain}
                                      .entityTypeIcons=${iconsPlain}
                                      .relationshipTypeLabels=${relLabelsPlain}
                                      defaultAccent="#6366f1"
                                      .fitNonce=${this._fitNonce}
                                      .compactZoom=${this._compactZoom}
                                      @node-dblclick=${this._onMindmapNodeDblClick}
                                      @compact-zoom-change=${this._onMindmapCompactZoomChange}
                                  ></crm-mindmap-canvas>
                              `
                            : html`<div class="mini-empty">${this.t('graph.empty_graph')}</div>`}
                    </div>
                    <div class="mini-footer">${footerBtn}</div>
                </div>
            `;
        }

        return html`
            <div class="mini-box">
                ${toolbar}
                <div class="mini-canvas-wrap">
                    <div class="mini-canvas"></div>
                </div>
                <div class="mini-footer">${footerBtn}</div>
            </div>
        `;
    }
}

customElements.define('crm-mini-graph', CRMMiniGraph);
