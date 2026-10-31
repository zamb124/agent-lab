/**
 * graph-canvas — обёртка над `3d-force-graph` (window.ForceGraph3D, lazy npm-чанк).
 *
 * Презентационный компонент: всё состояние графа приходит через properties,
 * взаимодействие наружу — DOM-события `node-click`, `node-dblclick`,
 * `node-contextmenu`, `link-click`, `canvas-click`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import {
    aggregateIncidentWeightsByNode,
    computeGraphNodeDisplaySize,
    createGraphLinkLabelPlane,
    createGraphNodeLabelSprite,
    createGraphTextSprite,
    maxIncidentWeightOrOne,
    positionGraphLinkLabelMesh,
    finiteOrZero,
    firstGraphText,
} from './graph-3d-helpers.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';
import type {
} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

import { cssVar } from '@platform/lib/utils/css-var.js';
const GRAPH_PRESETS = {
    dense: { charge: -60, linkWidth: 0.8, nodeRelSize: 5 },
    readable: { charge: -120, linkWidth: 1.5, nodeRelSize: 6 },
    presentation: { charge: -180, linkWidth: 2.2, nodeRelSize: 7 },
};
const GRAPH_WORLD_RADIUS = 220;
const MIN_CAMERA_DISTANCE = 760;
const ADAPTIVE_LABEL_DISTANCE = 900;

interface ForceGraphApi {
    backgroundColor(color: string): this;
    cooldownTicks(count: number): this;
    warmupTicks(count: number): this;
    showNavInfo(show: boolean): this;
    nodeLabel(readLabel: () => string): this;
    nodeVal(readValue: (node: Record<string, unknown>) => number): this;
    linkLabel(readLabel: () => string): this;
    nodeThreeObject(): (node: Record<string, unknown>) => unknown;
    nodeThreeObject(build: (node: Record<string, unknown>) => unknown): this;
    nodeThreeObjectExtend(extend: boolean): this;
    linkColor(readColor: (link: Record<string, unknown>) => string): this;
    linkWidth(readWidth: (link: Record<string, unknown>) => number): this;
    linkOpacity(readOpacity: (link: Record<string, unknown>) => number): this;
    linkThreeObjectExtend(extend: boolean): this;
    linkThreeObject(): (link: Record<string, unknown>) => unknown;
    linkThreeObject(build: (link: Record<string, unknown>) => unknown): this;
    linkPositionUpdate(update: (
        mesh: { visible: boolean },
        coords: { start: unknown; end: unknown },
        link: Record<string, unknown>,
    ) => boolean): this;
    linkDirectionalArrowLength(readLength: (link: Record<string, unknown>) => number): this;
    linkDirectionalArrowRelPos(position: number): this;
    linkDirectionalArrowColor(readColor: (link: Record<string, unknown>) => string | null): this;
    linkDirectionalParticles(readCount: (link: Record<string, unknown>) => number): this;
    linkDirectionalParticleWidth(readWidth: (link: Record<string, unknown>) => number): this;
    linkDirectionalParticleSpeed(speed: number): this;
    enableNodeDrag(enabled: boolean): this;
    onNodeClick(handle: (node: Record<string, unknown>, event: unknown) => void): this;
    onNodeHover(handle: (node: Record<string, unknown> | null) => void): this;
    onLinkClick(handle: (link: Record<string, unknown>) => void): this;
    onNodeDragEnd(handle: (node: Record<string, unknown>) => void): this;
    onEngineStop(handle: () => void): this;
    d3VelocityDecay(value: number): this;
    d3Force(name: string, force?: unknown): { strength(value: number): unknown };
    nodeRelSize(size: number): this;
    width(px: number): this;
    height(px: number): this;
    zoomToFit(durationMs: number, paddingPx: number): this;
    graphData(data?: unknown): { nodes?: Record<string, unknown>[] };
    cameraPosition(
        position?: { x: number; y: number; z: number },
        lookAt?: { x: number; y: number; z: number },
        durationMs?: number,
    ): { x: number; y: number; z: number };
    _destructor(): void;
}

function graphNumber(value: unknown, fallback: number): number {
    return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function graphText(value: unknown): string {
    return typeof value === 'string' ? value : '';
}

function firstRecordText(record: Record<string, unknown>, keys: readonly string[], fallback: string): string {
    for (const key of keys) {
        const value = record[key];
        if (typeof value === 'string' && value.trim().length > 0) return value;
    }
    return fallback;
}

function isVec3(value: unknown): value is { x: number; y: number; z: number } {
    return isPlainRecord(value)
        && typeof value.x === 'number'
        && typeof value.y === 'number'
        && typeof value.z === 'number';
}

export class CRMGraphCanvas extends PlatformElement {
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        graphNodes: { type: Array },
        graphEdges: { type: Array },
        shortestPathEdges: { type: Array },
        graphPreset: { type: String },
        labelMode: { type: String },
        selectedNodeId: { type: String },
        selectedEdgeId: { type: String },
        pathSourceId: { type: String },
        pathTargetId: { type: String },
        nodeColorFn: { state: true },
        edgeDirectedFn: { state: true },
        relationshipTypeColors: { state: true },
        incidentWeightSubtitleFn: { attribute: false },
        /** Плоский объект type_id → локализованное имя типа связи (подпись на ребре). */
        relationshipTypeLabels: { type: Object },
    };
    declare graphNodes: Record<string, unknown>[];
    declare graphEdges: Record<string, unknown>[];
    declare shortestPathEdges: Record<string, unknown>[];
    declare graphPreset: string;
    declare labelMode: string;
    declare selectedNodeId: string;
    declare selectedEdgeId: string;
    declare pathSourceId: string;
    declare pathTargetId: string;
    declare nodeColorFn: (node: Record<string, unknown>) => string;
    declare edgeDirectedFn: (edge: Record<string, unknown>) => boolean;
    declare relationshipTypeColors: Map<string, string>;
    declare incidentWeightSubtitleFn: ((weight: number) => string) | null;
    declare relationshipTypeLabels: Record<string, unknown>;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; width: 100%; height: 100%; position: relative; }
            .graph-canvas { position: absolute; inset: 0; background: var(--bg-secondary); }
        `,
    ];

    private _themeSelect: SelectController<string | undefined> | null = null;
    private _lastAppliedTheme: string | null = null;
    private _graphInstance: ForceGraphApi | null;
    private _graphContainerEl: HTMLElement | null;
    private _resizeObserver: ResizeObserver | null;
    private _autoFitPending: boolean;
    private _hoveredNodeId: string;
    private _lastClickNodeId: string;
    private _lastClickTimestamp: number;

    constructor() {
        super();
        this.graphNodes = [];
        this.graphEdges = [];
        this.shortestPathEdges = [];
        this.graphPreset = 'readable';
        this.labelMode = 'adaptive';
        this.selectedNodeId = '';
        this.selectedEdgeId = '';
        this.pathSourceId = '';
        this.pathTargetId = '';
        this.nodeColorFn = () => cssVar('--accent-tertiary', '#8b5cf6');
        this.edgeDirectedFn = () => true;
        this.relationshipTypeColors = new Map();
        this.incidentWeightSubtitleFn = null;
        this.relationshipTypeLabels = {};
        this._graphInstance = null;
        this._graphContainerEl = null;
        this._resizeObserver = null;
        this._autoFitPending = false;
        this._hoveredNodeId = '';
        this._lastClickNodeId = '';
        this._lastClickTimestamp = 0;
    }

    override render(): TemplateResult {
        return html`<div class="graph-canvas" id="graph-canvas"></div>`;
    }

    override firstUpdated(changed: PropertyValues<this>): void {
        void this._ensureGraphVendor().then(() => {
            this._initGraph();
            this._syncGraph();
        });
        this._themeSelect = this.select((state) => state.theme.mode);
        const canvasEl = this.renderRoot?.querySelector('#graph-canvas');
        if (canvasEl) {
            canvasEl.addEventListener('contextmenu', (event: Event) => {
                event.preventDefault();
                if (!this._hoveredNodeId) {
                    return;
                }
                if (!(event instanceof MouseEvent)) {
                    throw new Error('graph-canvas: contextmenu requires a mouse event');
                }
                this.emit('node-contextmenu', {
                    node: { id: this._hoveredNodeId },
                    screenX: event.clientX,
                    screenY: event.clientY,
                });
            });
            canvasEl.addEventListener('click', () => {
                this.emit('canvas-click', {});
            });
        }
    }

    override updated(changed: PropertyValues<this>): void {
        if (
            changed.has('graphNodes')
            || changed.has('graphEdges')
            || changed.has('shortestPathEdges')
            || changed.has('graphPreset')
        ) {
            this._syncGraph();
        }
        const selectionOrLabelsChanged = (
            changed.has('selectedNodeId')
            || changed.has('selectedEdgeId')
            || changed.has('pathSourceId')
            || changed.has('pathTargetId')
            || changed.has('labelMode')
        );
        if (selectionOrLabelsChanged && this._graphInstance) {
            this._graphInstance.nodeThreeObject(this._graphInstance.nodeThreeObject());
            this._graphInstance.linkThreeObject(this._graphInstance.linkThreeObject());
        }
        if (changed.has('incidentWeightSubtitleFn') && this._graphInstance) {
            this._graphInstance.nodeThreeObject(this._graphInstance.nodeThreeObject());
        }
        const themeValue = this._themeSelect === null ? undefined : this._themeSelect.value;
        const themeName: string | null = themeValue === undefined ? null : themeValue;
        if (this._lastAppliedTheme !== themeName) {
            this._lastAppliedTheme = themeName;
            if (this._graphInstance) {
                this._applyThemeToCanvas();
            }
        }
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        this._themeSelect = null;
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        this._graphContainerEl = null;
        if (this._graphInstance) {
            this._graphInstance._destructor();
            this._graphInstance = null;
        }
    }

    flyToNode(node: Record<string, unknown>): void {
        if (!this._graphInstance) {
            return;
        }
        let targetNode: Record<string, unknown> = node;
        if (typeof node === 'object' && node.id && (node.x === undefined)) {
            const graphData = this._graphInstance.graphData();
            if (graphData && Array.isArray(graphData.nodes)) {
                targetNode = graphData.nodes.find((n: Record<string, unknown>) => n.id === node.id) || node;
            }
        }
        const nx = finiteOrZero(targetNode.x);
        const ny = finiteOrZero(targetNode.y);
        const nz = finiteOrZero(targetNode.z);
        const cam = this._graphInstance.cameraPosition();
        const dx = cam.x - nx;
        const dy = cam.y - ny;
        const dz = cam.z - nz;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        const flyDistance = 120;
        const scale = dist > 0 ? flyDistance / dist : 1;
        this._graphInstance.cameraPosition(
            { x: nx + dx * scale, y: ny + dy * scale, z: nz + dz * scale },
            { x: nx, y: ny, z: nz },
            800,
        );
    }

    fitToViewport() {
        this._fitGraphToViewport(250, 80);
    }

    refreshLabels() {
        if (!this._graphInstance) {
            return;
        }
        this._graphInstance.nodeThreeObject(this._graphInstance.nodeThreeObject());
        this._graphInstance.linkThreeObject(this._graphInstance.linkThreeObject());
    }

    _applyThemeToCanvas() {
        if (!this._graphInstance) {
            return;
        }
        const canvasBg = cssVar('--bg-secondary', '#1a1a2e');
        this._graphInstance.backgroundColor(canvasBg);
        this._graphInstance.nodeThreeObject(this._graphInstance.nodeThreeObject());
        this._graphInstance.linkThreeObject(this._graphInstance.linkThreeObject());
    }

    _buildGraphDataForScene() {
        const highlightedEdgeIds = new Set(this.shortestPathEdges.map((edge: Record<string, unknown>) => {
            const sourceId = firstRecordText(edge, ['source_id', 'source_entity_id', 'source'], '');
            const targetId = firstRecordText(edge, ['target_id', 'target_entity_id', 'target'], '');
            const relationType = firstRecordText(edge, ['relationship_type', 'type'], 'related');
            return firstRecordText(edge, ['edge_id', 'relationship_id', 'id'], `${sourceId}:${targetId}:${relationType}`);
        }));
        const weightByNodeId = aggregateIncidentWeightsByNode(this.graphEdges);
        const maxWeight = maxIncidentWeightOrOne(weightByNodeId);
        const nodes = this.graphNodes.map((node: Record<string, unknown>) => {
            const entityId = graphText(node.entity_id);
            const nodeId = entityId.length > 0 ? entityId : graphText(node.id);
            const stored = weightByNodeId.get(nodeId);
            const totalWeight = stored === undefined ? 0 : stored;
            const rawLevel = typeof node.level === 'number' && Number.isFinite(node.level) ? node.level : 1;
            const sizingLevel = rawLevel === 0 ? 0 : 1;
            const graphNode: Record<string, unknown> = {
                ...node,
                id: nodeId,
                name: node.name || node.label || nodeId,
                color: this.nodeColorFn(node),
                incident_weight_sum: totalWeight,
                size: computeGraphNodeDisplaySize(sizingLevel, totalWeight, maxWeight),
            };
            return graphNode;
        });
        if (nodes.length === 1 && nodes[0]) {
            nodes[0].x = 0;
            nodes[0].y = 0;
            nodes[0].z = 0;
        }
        const links = this.graphEdges.map((edge: Record<string, unknown>) => {
            const source = firstRecordText(edge, ['source_id', 'source_entity_id', 'source'], '');
            const target = firstRecordText(edge, ['target_id', 'target_entity_id', 'target'], '');
            const relationType = firstRecordText(edge, ['relationship_type', 'type'], 'related');
            const edgeId = firstRecordText(edge, ['edge_id', 'relationship_id', 'id'], `${source}:${target}:${relationType}`);
            const directed = this.edgeDirectedFn(edge);
            return {
                ...edge,
                id: edgeId,
                source,
                target,
                relation_type: relationType,
                directed,
                path_kind: typeof edge.path_kind === 'string' && edge.path_kind.length > 0 ? edge.path_kind : null,
                highlighted: highlightedEdgeIds.has(edgeId),
            };
        });
        return { nodes, links };
    }

    _initGraph() {
        const factory = window.ForceGraph3D;
        if (typeof factory !== 'function') {
            throw new Error('ForceGraph3D is not available in window');
        }
        const container = this.renderRoot?.querySelector('#graph-canvas');
        if (!(container instanceof HTMLElement)) {
            throw new Error('Graph canvas container is not available');
        }
        this._graphContainerEl = container;
        const canvasBg = cssVar('--bg-secondary', '#1a1a2e');
        const graph = factory()(container)
            .backgroundColor(canvasBg)
            .cooldownTicks(120)
            .warmupTicks(80)
            .showNavInfo(false)
            .nodeLabel(() => '')
            .nodeVal((node: Record<string, unknown>) => Math.cbrt(graphNumber(node.size, 1)))
            .linkLabel(() => '')
            .nodeThreeObject((node: Record<string, unknown>) => {
                if (!window.THREE) {
                    return null;
                }
                const THREE = window.THREE;
                const nodeRelSize = GRAPH_PRESETS[this.graphPreset as keyof typeof GRAPH_PRESETS].nodeRelSize;
                const baseRadius = Math.cbrt(graphNumber(node.size, 1)) * nodeRelSize * 0.5;
                const isSelected = typeof node.id === 'string' && node.id.length > 0 && node.id === this.selectedNodeId;
                const selectionScale = isSelected ? 1.2 : 1;
                const radius = baseRadius * selectionScale;
                const geometry = new THREE.SphereGeometry(radius, 32, 24);
                const baseColor = node.color || cssVar('--accent-tertiary', '#8b5cf6');
                const material = new THREE.MeshStandardMaterial({
                    color: baseColor,
                    emissive: isSelected ? 0x3d8cff : 0x000000,
                    emissiveIntensity: isSelected ? 0.65 : 0,
                    roughness: isSelected ? 0.42 : 0.75,
                    metalness: isSelected ? 0.12 : 0.05,
                });
                const sphere = new THREE.Mesh(geometry, material);
                const group = new THREE.Group();
                group.add(sphere);
                if (isSelected) {
                    const ringGeom = new THREE.TorusGeometry(radius * 1.08, Math.max(0.35, radius * 0.07), 10, 48);
                    const ringMat = new THREE.MeshBasicMaterial({
                        color: 0x6eb6ff,
                        transparent: true,
                        opacity: 0.92,
                    });
                    const ring = new THREE.Mesh(ringGeom, ringMat);
                    ring.rotation.x = Math.PI / 2;
                    group.add(ring);
                }
                const labelColor = cssVar('--text-primary', '#f0f4ff');
                const subtitleColor = cssVar('--text-secondary', '#d4dae8');
                const weightSum = typeof node.incident_weight_sum === 'number' && Number.isFinite(node.incident_weight_sum)
                    ? node.incident_weight_sum
                    : 0;
                let subtitle = '';
                if (typeof this.incidentWeightSubtitleFn === 'function') {
                    subtitle = this.incidentWeightSubtitleFn(weightSum);
                }
                const sprite = subtitle
                    ? createGraphNodeLabelSprite({
                        title: firstGraphText([node.name, node.id]),
                        subtitle,
                        titleColor: labelColor,
                        subtitleColor,
                        titleFontSize: 24,
                        subtitleFontSize: 14,
                        maxTitleLength: 28,
                        maxSubtitleLength: 32,
                    })
                    : this._createTextSprite(firstGraphText([node.name, node.id]), labelColor, 24);
                if (sprite) {
                    sprite.visible = this._shouldShowNodeLabel(node);
                    sprite.position.set(0, radius + 3, 0);
                    group.add(sprite);
                }
                return group;
            })
            .nodeThreeObjectExtend(false)
            .linkColor((link: Record<string, unknown>) => {
                if (link.path_kind === 'directed') return cssVar('--success', '#10b981');
                if (link.path_kind === 'undirected') return cssVar('--warning', '#f59e0b');
                if (link.path_kind === 'both') return cssVar('--success', '#10b981');
                if (link.highlighted) return '#ff6b6b';
                const typeColor = this.relationshipTypeColors.get(graphText(link.relation_type));
                if (typeColor) return typeColor;
                return cssVar('--text-tertiary', 'rgba(255, 255, 255, 0.45)');
            })
            .linkWidth((link: Record<string, unknown>) => {
                if (link.path_kind === 'directed' || link.path_kind === 'undirected' || link.path_kind === 'both') {
                    return 4;
                }
                if (link.highlighted) return 4;
                const edgeWeight = typeof link.weight === 'number' && Number.isFinite(link.weight) ? link.weight : 1;
                const weightWidth = Math.max(0.8, Math.min(4, edgeWeight * 1.5));
                if (this._isLinkNearSelectedNode(link)) {
                    return weightWidth + 1.4;
                }
                return weightWidth;
            })
            .linkOpacity((link: Record<string, unknown>) => {
                if (link.path_kind === 'directed' || link.path_kind === 'undirected' || link.path_kind === 'both') {
                    return 0.95;
                }
                if (link.highlighted || link.id === this.selectedEdgeId) return 0.95;
                if (this._isLinkNearSelectedNode(link)) return 0.75;
                return 0.45;
            })
            .linkThreeObjectExtend(true)
            .linkThreeObject((link: Record<string, unknown>) => {
                const linkLabelColor = cssVar('--text-secondary', '#d4dae8');
                const typeKey = typeof link.relation_type === 'string' && link.relation_type.trim().length > 0
                    ? link.relation_type.trim()
                    : 'related';
                const human = this._resolveLinkRelationshipLabel(typeKey);
                const mesh = createGraphLinkLabelPlane(human, linkLabelColor, 17, 30);
                if (!mesh) return null;
                mesh.visible = this._shouldShowLinkLabel(link);
                return mesh;
            })
            .linkPositionUpdate((mesh: { visible: boolean }, { start, end }: { start: unknown; end: unknown }, link: Record<string, unknown>) => {
                if (!isVec3(start) || !isVec3(end)) return false;
                mesh.visible = this._shouldShowLinkLabel(link);
                if (!mesh.visible) return true;
                const cam = this._graphInstance ? this._graphInstance.cameraPosition() : null;
                positionGraphLinkLabelMesh(mesh, start, end, cam);
                return true;
            })
            .linkDirectionalArrowLength((link: Record<string, unknown>) => {
                if (link.path_kind === 'undirected') return 0;
                return link.directed ? 8 : 0;
            })
            .linkDirectionalArrowRelPos(0.88)
            .linkDirectionalArrowColor((link: Record<string, unknown>) => {
                if (link.path_kind === 'directed') return cssVar('--success', '#10b981');
                if (link.path_kind === 'both') return cssVar('--success', '#10b981');
                const typeColor = this.relationshipTypeColors.get(graphText(link.relation_type));
                if (typeColor) return typeColor;
                return null;
            })
            .linkDirectionalParticles((link: Record<string, unknown>) => {
                if (link.highlighted) return 4;
                if (link.directed) return 2;
                return 0;
            })
            .linkDirectionalParticleWidth((link: Record<string, unknown>) => (link.highlighted ? 3 : 1.5))
            .linkDirectionalParticleSpeed(0.006)
            .enableNodeDrag(true)
            .onNodeClick((node: Record<string, unknown>, event: unknown) => this._onCanvasNodeClick(node, event))
            .onNodeHover((node: Record<string, unknown>) => {
                this._hoveredNodeId = node ? firstGraphText([node.id]) : '';
            })
            .onLinkClick((link: Record<string, unknown>) => {
                this.emit('link-click', { link });
            })
            .onNodeDragEnd((node: Record<string, unknown>) => {
                node.fx = node.x;
                node.fy = node.y;
                node.fz = node.z;
            })
            .onEngineStop(() => {
                if (!this._graphInstance) return;
                const currentGraphData = this._graphInstance.graphData();
                if (!currentGraphData || !Array.isArray(currentGraphData.nodes)) return;
                if (currentGraphData.nodes.length <= 1) {
                    this._autoFitPending = false;
                    this._applySingleNodeCamera();
                    return;
                }
                if (this._autoFitPending) {
                    this._autoFitPending = false;
                    this._fitGraphToViewport(300, 90);
                }
            });
        graph.d3Force('charge').strength(GRAPH_PRESETS[this.graphPreset as keyof typeof GRAPH_PRESETS].charge);
        graph.d3VelocityDecay(0.5);
        graph.d3Force('box', this._createBoundingForce(GRAPH_WORLD_RADIUS));
        graph.nodeRelSize(GRAPH_PRESETS[this.graphPreset as keyof typeof GRAPH_PRESETS].nodeRelSize);
        this._graphInstance = graph;
        this._applyGraphDimensionsFromContainer();
        this._resizeObserver = new ResizeObserver(() => {
            this._applyGraphDimensionsFromContainer();
        });
        this._resizeObserver.observe(container);
    }

    _applyGraphDimensionsFromContainer() {
        if (!this._graphInstance || !this._graphContainerEl) return;
        const widthPx = this._graphContainerEl.clientWidth;
        const heightPx = this._graphContainerEl.clientHeight;
        if (widthPx <= 0 || heightPx <= 0) return;
        this._graphInstance.width(widthPx);
        this._graphInstance.height(heightPx);
    }

    _createBoundingForce(worldRadius: number): (alpha: number) => void {
        let nodes: Record<string, unknown>[] = [];
        const force = (alpha: number) => {
            const restoringStrength = 0.12 * alpha;
            nodes.forEach((node: Record<string, unknown>) => {
                const x = node.x;
                const y = node.y;
                const z = node.z;
                if (typeof x !== 'number' || typeof y !== 'number' || typeof z !== 'number') return;
                if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return;
                const distance = Math.sqrt((x ** 2) + (y ** 2) + (z ** 2));
                if (distance <= worldRadius || distance === 0) return;
                const overshoot = distance - worldRadius;
                const nx = x / distance;
                const ny = y / distance;
                const nz = z / distance;
                const pull = overshoot * restoringStrength;
                const vx = graphNumber(node.vx, 0) - nx * pull;
                const vy = graphNumber(node.vy, 0) - ny * pull;
                const vz = graphNumber(node.vz, 0) - nz * pull;
                node.vx = vx;
                node.vy = vy;
                node.vz = vz;
            });
        };
        force.initialize = (simNodes: Record<string, unknown>[]) => {
            nodes = simNodes;
        };
        return force;
    }

    _fitGraphToViewport(durationMs = 260, paddingPx = 90) {
        if (!this._graphInstance) return;
        this._graphInstance.zoomToFit(durationMs, paddingPx);
        requestAnimationFrame(() => {
            this._enforceMinCameraDistance(MIN_CAMERA_DISTANCE);
        });
    }

    _enforceMinCameraDistance(minDistance: number): void {
        if (!this._graphInstance) return;
        const position = this._graphInstance.cameraPosition();
        if (!position) return;
        const distance = Math.sqrt((position.x ** 2) + (position.y ** 2) + (position.z ** 2));
        if (!Number.isFinite(distance) || distance >= minDistance) return;
        if (distance === 0) {
            this._graphInstance.cameraPosition({ x: 0, y: 0, z: minDistance }, { x: 0, y: 0, z: 0 }, 180);
            return;
        }
        const scale = minDistance / distance;
        this._graphInstance.cameraPosition(
            { x: position.x * scale, y: position.y * scale, z: position.z * scale },
            { x: 0, y: 0, z: 0 },
            180,
        );
    }

    _applySingleNodeCamera() {
        if (!this._graphInstance) return;
        this._graphInstance.cameraPosition({ x: 0, y: 0, z: MIN_CAMERA_DISTANCE }, { x: 0, y: 0, z: 0 }, 220);
    }

    _syncGraph() {
        if (!this._graphInstance) return;
        const graphData = this._buildGraphDataForScene();
        if (graphData.nodes.length === 1) {
            const singleNode = graphData.nodes[0];
            if (singleNode === undefined) {
                throw new Error('graph-canvas: single node missing');
            }
            singleNode.x = 0;
            singleNode.y = 0;
            singleNode.z = 0;
            singleNode.fx = 0;
            singleNode.fy = 0;
            singleNode.fz = 0;
            this._autoFitPending = false;
        }
        this._graphInstance.graphData(graphData);
        this._graphInstance.d3Force('charge').strength(GRAPH_PRESETS[this.graphPreset as keyof typeof GRAPH_PRESETS].charge);
        this._graphInstance.nodeRelSize(GRAPH_PRESETS[this.graphPreset as keyof typeof GRAPH_PRESETS].nodeRelSize);
        if (graphData.nodes.length === 0) return;
        if (graphData.nodes.length === 1) {
            this._applySingleNodeCamera();
            return;
        }
        this._autoFitPending = true;
    }

    /**
     * Ленивая загрузка three.js и 3d-force-graph из npm-чанков: тот же
     * инстанс `three` внутри ForceGraph3D — один shared-чанк в сборке.
     */
    async _ensureGraphVendor(): Promise<void> {
        if (typeof window.ForceGraph3D === 'function' && window.THREE) {
            return;
        }
        const [three, fg] = await Promise.all([import('three'), import('3d-force-graph')]);
        window.THREE = three;
        window.ForceGraph3D = fg.default;
    }

    _onCanvasNodeClick(node: Record<string, unknown>, event: unknown): void {
        const now = Date.now();
        const clickedId = graphText(node.id);
        const isDoubleClick = this._lastClickNodeId === clickedId && (now - this._lastClickTimestamp) < 380;
        this._lastClickNodeId = clickedId;
        this._lastClickTimestamp = now;
        if (isDoubleClick) {
            this.emit('node-dblclick', { node });
            return;
        }
        this.emit('node-click', { node, event });
    }

    _resolveLinkRelationshipLabel(typeKey: unknown): string {
        const k = typeof typeKey === 'string' ? typeKey.trim() : '';
        if (k.length === 0) {
            return 'related';
        }
        const map = this.relationshipTypeLabels;
        if (map && typeof map === 'object' && Object.prototype.hasOwnProperty.call(map, k)) {
            const v = map[k];
            if (typeof v === 'string' && v.trim().length > 0) {
                return v.trim();
            }
        }
        return k;
    }

    _shouldShowNodeLabel(node: Record<string, unknown>): boolean {
        if (this.labelMode !== 'adaptive') return false;
        const isImportant = node.id === this.selectedNodeId
            || node.id === this.pathSourceId
            || node.id === this.pathTargetId;
        if (isImportant) return true;
        if (this.graphNodes.length <= 80) return true;
        const distance = this._getCameraDistance();
        if (distance < ADAPTIVE_LABEL_DISTANCE && this.graphNodes.length <= 220) return true;
        return false;
    }

    _shouldShowLinkLabel(link: Record<string, unknown>): boolean {
        if (this.labelMode !== 'adaptive') return false;
        if (link.id === this.selectedEdgeId || link.highlighted) return true;
        if (this.graphEdges.length <= 16 && this._getCameraDistance() < ADAPTIVE_LABEL_DISTANCE * 0.82) return true;
        return false;
    }

    _getCameraDistance(): number {
        if (!this._graphInstance) return MIN_CAMERA_DISTANCE;
        const position = this._graphInstance.cameraPosition();
        if (!position) return MIN_CAMERA_DISTANCE;
        const distance = Math.sqrt((position.x ** 2) + (position.y ** 2) + (position.z ** 2));
        if (!Number.isFinite(distance) || distance <= 0) return MIN_CAMERA_DISTANCE;
        return distance;
    }

    _getLinkEndpointId(endpoint: unknown): string {
        if (typeof endpoint === 'string') return endpoint;
        if (isPlainRecord(endpoint)) {
            return firstGraphText([endpoint.id, endpoint.entity_id]);
        }
        return '';
    }

    _isLinkNearSelectedNode(link: Record<string, unknown>): boolean {
        if (!this.selectedNodeId) return false;
        const sourceId = this._getLinkEndpointId(link.source);
        const targetId = this._getLinkEndpointId(link.target);
        return sourceId === this.selectedNodeId || targetId === this.selectedNodeId;
    }

    _createTextSprite(text: string, color = '#f2f5ff', fontSize = 22, maxLength = 28) {
        return createGraphTextSprite(text, color, fontSize, maxLength);
    }
}

customElements.define('crm-graph-canvas', CRMGraphCanvas);
