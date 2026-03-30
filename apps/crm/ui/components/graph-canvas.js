import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const GRAPH_PRESETS = {
    dense: { charge: -60, linkWidth: 0.8, nodeRelSize: 5 },
    readable: { charge: -120, linkWidth: 1.5, nodeRelSize: 6 },
    presentation: { charge: -180, linkWidth: 2.2, nodeRelSize: 7 },
};
const GRAPH_WORLD_RADIUS = 220;
const MIN_CAMERA_DISTANCE = 760;
const ADAPTIVE_LABEL_DISTANCE = 900;

export class GraphCanvas extends PlatformElement {
    static properties = {
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
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; width: 100%; height: 100%; position: relative; }
            .graph-canvas { position: absolute; inset: 0; background: var(--bg-secondary); }
        `,
    ];

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
        this.nodeColorFn = () => '#bca8ff';
        this.edgeDirectedFn = () => true;
        this.relationshipTypeColors = new Map();
        this._graphInstance = null;
        this._autoFitPending = false;
        this._hoveredNodeId = '';
        this._lastClickNodeId = '';
        this._lastClickTimestamp = 0;
        this._themeChangeHandler = null;
    }

    render() {
        return html`<div class="graph-canvas" id="graph-canvas"></div>`;
    }

    firstUpdated() {
        this._assertOfflineVendorSetup();
        this._initGraph();
        this._syncGraph();
        this._themeChangeHandler = () => this._applyThemeToCanvas();
        window.addEventListener('theme-change', this._themeChangeHandler);
        const canvasEl = this.renderRoot?.querySelector('#graph-canvas');
        if (canvasEl) {
            canvasEl.addEventListener('contextmenu', (event) => {
                event.preventDefault();
                if (this._hoveredNodeId) {
                    this.emit('node-contextmenu', {
                        node: { id: this._hoveredNodeId },
                        screenX: event.clientX,
                        screenY: event.clientY,
                    });
                }
            });
            canvasEl.addEventListener('click', () => {
                this.emit('canvas-click', {});
            });
        }
    }

    updated(changedProperties) {
        if (
            changedProperties.has('graphNodes')
            || changedProperties.has('graphEdges')
            || changedProperties.has('shortestPathEdges')
            || changedProperties.has('graphPreset')
        ) {
            this._syncGraph();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._themeChangeHandler) {
            window.removeEventListener('theme-change', this._themeChangeHandler);
            this._themeChangeHandler = null;
        }
        if (this._graphInstance) {
            this._graphInstance._destructor();
            this._graphInstance = null;
        }
    }

    flyToNode(node) {
        if (!this._graphInstance) {
            return;
        }
        let targetNode = node;
        if (typeof node === 'object' && node.id && (node.x === undefined)) {
            const graphData = this._graphInstance.graphData();
            if (graphData && Array.isArray(graphData.nodes)) {
                targetNode = graphData.nodes.find((n) => n.id === node.id) || node;
            }
        }
        const nx = targetNode.x || 0;
        const ny = targetNode.y || 0;
        const nz = targetNode.z || 0;
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
        const canvasBg = getComputedStyle(document.documentElement).getPropertyValue('--bg-secondary').trim() || '#1a1a2e';
        this._graphInstance.backgroundColor(canvasBg);
        this._graphInstance.nodeThreeObject(this._graphInstance.nodeThreeObject());
        this._graphInstance.linkThreeObject(this._graphInstance.linkThreeObject());
    }

    _buildGraphDataForScene() {
        const highlightedEdgeIds = new Set(this.shortestPathEdges.map((edge) => {
            const edgeId = edge.edge_id || edge.relationship_id || edge.id;
            if (typeof edgeId === 'string' && edgeId.trim().length > 0) {
                return edgeId;
            }
            const sourceId = edge.source_id || edge.source_entity_id || edge.source;
            const targetId = edge.target_id || edge.target_entity_id || edge.target;
            const relationType = edge.relationship_type || edge.type || 'related';
            return `${sourceId}:${targetId}:${relationType}`;
        }));
        const weightByNodeId = new Map();
        this.graphEdges.forEach((edge) => {
            const sourceId = edge.source_id || edge.source_entity_id || edge.source;
            const targetId = edge.target_id || edge.target_entity_id || edge.target;
            const edgeWeight = typeof edge.weight === 'number' && Number.isFinite(edge.weight) ? edge.weight : 1;
            weightByNodeId.set(sourceId, (weightByNodeId.get(sourceId) || 0) + edgeWeight);
            weightByNodeId.set(targetId, (weightByNodeId.get(targetId) || 0) + edgeWeight);
        });
        const maxWeight = Math.max(1, ...weightByNodeId.values());
        const nodes = this.graphNodes.map((node) => {
            const nodeId = node.entity_id || node.id;
            const totalWeight = weightByNodeId.get(nodeId) || 0;
            const weightRatio = totalWeight / maxWeight;
            const baseSize = node.level === 0 ? 2.2 : 1.4;
            const weightBonus = weightRatio * 3.5;
            return {
                ...node,
                id: nodeId,
                name: node.name || node.label || nodeId,
                color: this.nodeColorFn(node),
                size: baseSize + weightBonus,
            };
        });
        if (nodes.length === 1) {
            nodes[0].x = 0;
            nodes[0].y = 0;
            nodes[0].z = 0;
        }
        const links = this.graphEdges.map((edge) => {
            const source = edge.source_id || edge.source_entity_id || edge.source;
            const target = edge.target_id || edge.target_entity_id || edge.target;
            const edgeId = edge.edge_id || edge.relationship_id || edge.id
                || `${source}:${target}:${edge.relationship_type || edge.type || 'related'}`;
            const relationType = edge.relationship_type || edge.type || 'related';
            const directed = this.edgeDirectedFn(edge);
            return {
                ...edge,
                id: edgeId,
                source,
                target,
                relation_type: relationType,
                directed,
                path_kind: edge.path_kind || null,
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
        if (!container) {
            throw new Error('Graph canvas container is not available');
        }
        const canvasBg = getComputedStyle(document.documentElement).getPropertyValue('--bg-secondary').trim() || '#1a1a2e';
        this._graphInstance = factory()(container)
            .backgroundColor(canvasBg)
            .cooldownTicks(120)
            .warmupTicks(80)
            .showNavInfo(false)
            .nodeLabel(() => '')
            .nodeVal((node) => node.size)
            .linkLabel(() => '')
            .nodeThreeObject((node) => {
                if (!window.THREE) {
                    return null;
                }
                const THREE = window.THREE;
                const nodeRelSize = GRAPH_PRESETS[this.graphPreset].nodeRelSize;
                const radius = Math.cbrt(node.size || 1) * nodeRelSize * 0.5;
                const geometry = new THREE.SphereGeometry(radius, 32, 24);
                const material = new THREE.MeshStandardMaterial({
                    color: node.color || '#bca8ff',
                    roughness: 0.75,
                    metalness: 0.05,
                });
                const sphere = new THREE.Mesh(geometry, material);
                const group = new THREE.Group();
                group.add(sphere);
                const labelColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#f0f4ff';
                const sprite = this._createTextSprite(node.name || node.id || '', labelColor, 24);
                if (sprite) {
                    sprite.visible = this._shouldShowNodeLabel(node);
                    sprite.position.set(0, radius + 3, 0);
                    group.add(sprite);
                }
                return group;
            })
            .nodeThreeObjectExtend(false)
            .linkColor((link) => {
                if (link.path_kind === 'directed') {
                    return '#41d36d';
                }
                if (link.path_kind === 'undirected') {
                    return '#f2c94c';
                }
                if (link.path_kind === 'both') {
                    return '#9adf5d';
                }
                if (link.highlighted) {
                    return '#ff6b6b';
                }
                const typeColor = this.relationshipTypeColors.get(link.relation_type);
                if (typeColor) {
                    return typeColor;
                }
                return '#9ba3bf';
            })
            .linkWidth((link) => {
                if (link.path_kind === 'directed' || link.path_kind === 'undirected' || link.path_kind === 'both') {
                    return 4;
                }
                if (link.highlighted) {
                    return 4;
                }
                const edgeWeight = typeof link.weight === 'number' && Number.isFinite(link.weight) ? link.weight : 1;
                const weightWidth = Math.max(0.8, Math.min(4, edgeWeight * 1.5));
                if (this._isLinkNearSelectedNode(link)) {
                    return weightWidth + 1.4;
                }
                return weightWidth;
            })
            .linkOpacity((link) => {
                if (link.path_kind === 'directed' || link.path_kind === 'undirected' || link.path_kind === 'both') {
                    return 0.95;
                }
                if (link.highlighted || link.id === this.selectedEdgeId) {
                    return 0.95;
                }
                if (this._isLinkNearSelectedNode(link)) {
                    return 0.75;
                }
                return 0.45;
            })
            .linkThreeObjectExtend(true)
            .linkThreeObject((link) => {
                const linkLabelColor = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary').trim() || '#d4dae8';
                const sprite = this._createTextSprite(link.relation_type || 'related', linkLabelColor, 20);
                if (!sprite) {
                    return null;
                }
                sprite.visible = this._shouldShowLinkLabel(link);
                return sprite;
            })
            .linkPositionUpdate((sprite, { start, end }, link) => {
                if (!sprite || !start || !end) {
                    return false;
                }
                sprite.visible = this._shouldShowLinkLabel(link);
                const middlePosition = {
                    x: start.x + ((end.x - start.x) / 2),
                    y: start.y + ((end.y - start.y) / 2),
                    z: start.z + ((end.z - start.z) / 2),
                };
                sprite.position.set(middlePosition.x, middlePosition.y, middlePosition.z);
                return true;
            })
            .linkDirectionalArrowLength((link) => {
                if (link.path_kind === 'undirected') {
                    return 0;
                }
                return link.directed ? 8 : 0;
            })
            .linkDirectionalArrowRelPos(0.88)
            .linkDirectionalArrowColor((link) => {
                if (link.path_kind === 'directed') {
                    return '#41d36d';
                }
                if (link.path_kind === 'both') {
                    return '#9adf5d';
                }
                const typeColor = this.relationshipTypeColors.get(link.relation_type);
                if (typeColor) {
                    return typeColor;
                }
                return null;
            })
            .linkDirectionalParticles((link) => {
                if (link.highlighted) {
                    return 4;
                }
                if (link.directed) {
                    return 2;
                }
                return 0;
            })
            .linkDirectionalParticleWidth((link) => (link.highlighted ? 3 : 1.5))
            .linkDirectionalParticleSpeed(0.006)
            .enableNodeDrag(true)
            .onNodeClick((node, event) => this._onCanvasNodeClick(node, event))
            .onNodeHover((node) => {
                this._hoveredNodeId = node ? (node.id || '') : '';
            })
            .onLinkClick((link) => {
                this.emit('link-click', { link });
            })
            .onNodeDragEnd((node) => {
                node.fx = node.x;
                node.fy = node.y;
                node.fz = node.z;
            })
            .onEngineStop(() => {
                if (!this._graphInstance) {
                    return;
                }
                const currentGraphData = this._graphInstance.graphData();
                if (!currentGraphData || !Array.isArray(currentGraphData.nodes)) {
                    return;
                }
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
        this._graphInstance.d3Force('charge').strength(GRAPH_PRESETS[this.graphPreset].charge);
        this._graphInstance.d3VelocityDecay(0.5);
        this._graphInstance.d3Force('box', this._createBoundingForce(GRAPH_WORLD_RADIUS));
        this._graphInstance.nodeRelSize(GRAPH_PRESETS[this.graphPreset].nodeRelSize);
    }

    _createBoundingForce(worldRadius) {
        let nodes = [];
        const force = (alpha) => {
            const restoringStrength = 0.12 * alpha;
            nodes.forEach((node) => {
                const hasCoordinates = [node.x, node.y, node.z].every((value) => typeof value === 'number' && Number.isFinite(value));
                if (!hasCoordinates) {
                    return;
                }
                const distance = Math.sqrt((node.x ** 2) + (node.y ** 2) + (node.z ** 2));
                if (distance <= worldRadius || distance === 0) {
                    return;
                }
                const overshoot = distance - worldRadius;
                const nx = node.x / distance;
                const ny = node.y / distance;
                const nz = node.z / distance;
                const pull = overshoot * restoringStrength;
                if (typeof node.vx !== 'number' || !Number.isFinite(node.vx)) {
                    node.vx = 0;
                }
                if (typeof node.vy !== 'number' || !Number.isFinite(node.vy)) {
                    node.vy = 0;
                }
                if (typeof node.vz !== 'number' || !Number.isFinite(node.vz)) {
                    node.vz = 0;
                }
                node.vx -= nx * pull;
                node.vy -= ny * pull;
                node.vz -= nz * pull;
            });
        };
        force.initialize = (simNodes) => {
            nodes = simNodes;
        };
        return force;
    }

    _fitGraphToViewport(durationMs = 260, paddingPx = 90) {
        if (!this._graphInstance) {
            return;
        }
        this._graphInstance.zoomToFit(durationMs, paddingPx);
        requestAnimationFrame(() => {
            this._enforceMinCameraDistance(MIN_CAMERA_DISTANCE);
        });
    }

    _enforceMinCameraDistance(minDistance) {
        if (!this._graphInstance) {
            return;
        }
        const position = this._graphInstance.cameraPosition();
        if (!position) {
            return;
        }
        const distance = Math.sqrt((position.x ** 2) + (position.y ** 2) + (position.z ** 2));
        if (!Number.isFinite(distance) || distance >= minDistance) {
            return;
        }
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
        if (!this._graphInstance) {
            return;
        }
        this._graphInstance.cameraPosition({ x: 0, y: 0, z: MIN_CAMERA_DISTANCE }, { x: 0, y: 0, z: 0 }, 220);
    }

    _syncGraph() {
        if (!this._graphInstance) {
            return;
        }
        const graphData = this._buildGraphDataForScene();
        if (graphData.nodes.length === 1) {
            const singleNode = graphData.nodes[0];
            singleNode.x = 0;
            singleNode.y = 0;
            singleNode.z = 0;
            singleNode.fx = 0;
            singleNode.fy = 0;
            singleNode.fz = 0;
            this._autoFitPending = false;
        }
        this._graphInstance.graphData(graphData);
        this._graphInstance.d3Force('charge').strength(GRAPH_PRESETS[this.graphPreset].charge);
        this._graphInstance.nodeRelSize(GRAPH_PRESETS[this.graphPreset].nodeRelSize);
        if (graphData.nodes.length === 0) {
            return;
        }
        if (graphData.nodes.length === 1) {
            if (this._graphInstance) {
                this._applySingleNodeCamera();
            }
            return;
        }
        this._autoFitPending = true;
    }

    _assertOfflineVendorSetup() {
        const expectedSrc = '/crm/ui/vendor/3d-force-graph/3d-force-graph.min.js';
        const hasExpectedScript = Array.from(document.scripts).some((script) => {
            if (typeof script.src !== 'string') {
                return false;
            }
            return script.src.includes(expectedSrc);
        });
        if (!hasExpectedScript) {
            throw new Error(`Offline vendor script is required: ${expectedSrc}`);
        }
        if (typeof window.ForceGraph3D !== 'function') {
            throw new Error('ForceGraph3D is not loaded from offline vendor script');
        }
    }

    _onCanvasNodeClick(node, event) {
        const now = Date.now();
        const isDoubleClick = this._lastClickNodeId === node.id && (now - this._lastClickTimestamp) < 380;
        this._lastClickNodeId = node.id;
        this._lastClickTimestamp = now;
        if (isDoubleClick) {
            this.emit('node-dblclick', { node });
            return;
        }
        this.emit('node-click', { node, event });
    }

    _shouldShowNodeLabel(node) {
        if (this.labelMode !== 'adaptive') {
            return false;
        }
        const isImportant = node.id === this.selectedNodeId
            || node.id === this.pathSourceId
            || node.id === this.pathTargetId;
        if (isImportant) {
            return true;
        }
        if (this.graphNodes.length <= 80) {
            return true;
        }
        const distance = this._getCameraDistance();
        if (distance < ADAPTIVE_LABEL_DISTANCE && this.graphNodes.length <= 220) {
            return true;
        }
        return false;
    }

    _shouldShowLinkLabel(link) {
        if (this.labelMode !== 'adaptive') {
            return false;
        }
        if (link.id === this.selectedEdgeId || link.highlighted) {
            return true;
        }
        if (this.graphEdges.length <= 16 && this._getCameraDistance() < ADAPTIVE_LABEL_DISTANCE * 0.82) {
            return true;
        }
        return false;
    }

    _getCameraDistance() {
        if (!this._graphInstance) {
            return MIN_CAMERA_DISTANCE;
        }
        const position = this._graphInstance.cameraPosition();
        if (!position) {
            return MIN_CAMERA_DISTANCE;
        }
        const distance = Math.sqrt((position.x ** 2) + (position.y ** 2) + (position.z ** 2));
        if (!Number.isFinite(distance) || distance <= 0) {
            return MIN_CAMERA_DISTANCE;
        }
        return distance;
    }

    _getLinkEndpointId(endpoint) {
        if (typeof endpoint === 'string') {
            return endpoint;
        }
        if (endpoint && typeof endpoint === 'object') {
            return endpoint.id || endpoint.entity_id || '';
        }
        return '';
    }

    _isLinkNearSelectedNode(link) {
        if (!this.selectedNodeId) {
            return false;
        }
        const sourceId = this._getLinkEndpointId(link.source);
        const targetId = this._getLinkEndpointId(link.target);
        return sourceId === this.selectedNodeId || targetId === this.selectedNodeId;
    }

    _createTextSprite(text, color = '#f2f5ff', fontSize = 22, maxLength = 28) {
        if (!window.THREE || typeof window.THREE.CanvasTexture !== 'function' || typeof window.THREE.Sprite !== 'function') {
            throw new Error('THREE.js is not available for text sprite rendering');
        }
        const baseText = typeof text === 'string' && text.trim().length > 0 ? text.trim() : 'entity';
        const labelText = baseText.length > maxLength ? `${baseText.slice(0, maxLength - 1)}\u2026` : baseText;
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        if (!context) {
            throw new Error('Cannot create 2d canvas context for text sprite');
        }
        context.font = `700 ${fontSize}px Inter, sans-serif`;
        const textWidth = Math.max(24, Math.ceil(context.measureText(labelText).width));
        canvas.width = textWidth + 18;
        canvas.height = fontSize + 12;
        context.font = `700 ${fontSize}px Inter, sans-serif`;
        context.fillStyle = color;
        context.textBaseline = 'middle';
        const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
        context.shadowColor = isDark ? 'rgba(5, 7, 12, 0.95)' : 'rgba(255, 255, 255, 0.95)';
        context.shadowBlur = 6;
        context.lineWidth = 4;
        context.strokeStyle = isDark ? 'rgba(5, 7, 12, 0.92)' : 'rgba(255, 255, 255, 0.92)';
        context.strokeText(labelText, 8, canvas.height / 2);
        context.fillText(labelText, 8, canvas.height / 2);
        const texture = new window.THREE.CanvasTexture(canvas);
        texture.needsUpdate = true;
        const material = new window.THREE.SpriteMaterial({
            map: texture,
            transparent: true,
            depthTest: false,
            depthWrite: false,
        });
        const sprite = new window.THREE.Sprite(material);
        sprite.scale.set(canvas.width * 0.07, canvas.height * 0.07, 1);
        sprite.renderOrder = 999;
        return sprite;
    }
}

customElements.define('graph-canvas', GraphCanvas);
