import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { resolveObjectName } from '@platform/lib/utils/entity-ref.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

const VIEW_MODES = ['influence', 'related', 'path'];

const GRAPH_PRESETS = {
    dense: { charge: -60, linkWidth: 0.8, nodeRelSize: 5 },
    readable: { charge: -120, linkWidth: 1.5, nodeRelSize: 6 },
    presentation: { charge: -180, linkWidth: 2.2, nodeRelSize: 7 },
};
const GRAPH_WORLD_RADIUS = 220;
const MIN_CAMERA_DISTANCE = 760;
const ADAPTIVE_LABEL_DISTANCE = 900;

export class GraphPage extends PlatformElement {
    static properties = {
        _entities: { state: true },
        _relationships: { state: true },
        _selectedRootId: { state: true },
        _maxDepth: { state: true },
        _loading: { state: true },
        _graphNodes: { state: true },
        _graphEdges: { state: true },
        _pathSourceId: { state: true },
        _pathTargetId: { state: true },
        _shortestPathEdges: { state: true },
        _findingPath: { state: true },
        _entitySearchQuery: { state: true },
        _viewMode: { state: true },
        _relatedDirection: { state: true },
        _relationshipTypeFilter: { state: true },
        _pathMaxDepth: { state: true },
        _selectedNodeId: { state: true },
        _selectedEdgeId: { state: true },
        _graphPreset: { state: true },
        _backendOperationId: { state: true },
        _backendOperationArgs: { state: true },
        _backendOperationResult: { state: true },
        _backendLoading: { state: true },
        _attachmentEntityId: { state: true },
        _attachmentFile: { state: true },
        _entityFormId: { state: true },
        _entityFormName: { state: true },
        _entityFormType: { state: true },
        _entityFormNamespace: { state: true },
        _entityFormDescription: { state: true },
        _relationshipFormId: { state: true },
        _relationshipSourceId: { state: true },
        _relationshipTargetId: { state: true },
        _relationshipType: { state: true },
        _grantEntityId: { state: true },
        _grantNamespace: { state: true },
        _grantUserId: { state: true },
        _grantCompanyId: { state: true },
        _grantRole: { state: true },
        _grantId: { state: true },
        _accessRequestEntityId: { state: true },
        _accessRequestId: { state: true },
        _accessRequestMessage: { state: true },
        _accessRequestDepth: { state: true },
        _namespaceNameInput: { state: true },
        _namespaceTemplateIdInput: { state: true },
        _namespaceDescriptionInput: { state: true },
        _isFullscreen: { state: true },
        _defaultOverviewActive: { state: true },
        _showSidePanel: { state: true },
        _canvasPathState: { state: true },
        _canvasPathHint: { state: true },
        _labelMode: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke-strong);
                border-radius: var(--radius-2xl);
                overflow: hidden;
            }

            .layout {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
            }

            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-4);
                border-bottom: 1px solid var(--crm-stroke);
                background: var(--crm-surface-tint);
                flex-wrap: wrap;
            }

            .toolbar-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-right: var(--space-2);
            }

            .toolbar-control {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .toolbar-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .toolbar-select,
            .toolbar-input,
            .json-input,
            .textarea {
                min-width: 160px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .toolbar-input {
                min-width: 220px;
            }

            .stats {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: var(--space-3);
                padding: var(--space-4);
                border-bottom: 1px solid var(--crm-stroke);
            }

            .stat-card {
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
            }

            .stat-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
            }

            .stat-value {
                font-size: var(--text-xl);
                color: var(--text-primary);
                font-weight: var(--font-semibold);
            }

            .workspace {
                flex: 1;
                display: grid;
                grid-template-columns: minmax(0, 1fr) 320px;
                min-height: 0;
                gap: var(--space-3);
                padding: var(--space-4);
                overflow: hidden;
            }

            .graph-panel,
            .control-panel {
                min-height: 0;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                border-radius: var(--radius-lg);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            .control-panel.hidden {
                display: none;
            }

            .panel-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3);
                border-bottom: 1px solid var(--crm-stroke);
            }

            .panel-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .graph-canvas {
                flex: 1;
                min-height: 0;
                position: relative;
                background: radial-gradient(circle at top, rgba(130, 130, 180, 0.18), rgba(20, 20, 35, 0.75));
            }

            .legend {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
            }

            .legend-item {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .legend-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
            }

            .control-body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
            }

            .section {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .section-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-2);
            }

            .textarea {
                width: 100%;
                min-height: 96px;
                resize: vertical;
                font-family: monospace;
                line-height: 1.4;
            }

            .result-box {
                font-family: monospace;
                font-size: var(--text-xs);
                white-space: pre-wrap;
                word-break: break-word;
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
                max-height: 220px;
                overflow: auto;
            }

            .small {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .row {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .section-collapsible {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                overflow: hidden;
            }

            .section-collapsible > summary {
                list-style: none;
                cursor: pointer;
                padding: var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                border-bottom: 1px solid var(--crm-stroke);
            }

            .section-collapsible > summary::-webkit-details-marker {
                display: none;
            }

            .section-collapsible[open] > summary {
                background: var(--crm-surface-tint);
            }

            .section-collapsible-content {
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .layout.fullscreen .toolbar,
            .layout.fullscreen .stats,
            .layout.fullscreen .control-panel {
                display: none;
            }

            .layout.fullscreen .workspace {
                grid-template-columns: 1fr;
                padding: 0;
                gap: 0;
                height: 100%;
            }

            .layout.fullscreen .graph-panel {
                border: none;
                border-radius: 0;
            }

            .node-pill {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-full);
                background: var(--crm-surface-tint-strong);
                border: 1px solid var(--crm-stroke);
                font-size: var(--text-xs);
            }

            .canvas-hint {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-full);
                background: var(--crm-surface-tint-strong);
                border: 1px solid var(--crm-stroke);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            @media (max-width: 1199px) {
                .workspace {
                    grid-template-columns: 1fr;
                    overflow: auto;
                }

                .graph-panel {
                    min-height: 440px;
                }
            }

            @media (max-width: 767px) {
                :host {
                    border: none;
                    border-radius: 0;
                }

                .toolbar,
                .stats,
                .workspace {
                    padding: var(--space-3);
                }

                .stats {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }

                .section-grid {
                    grid-template-columns: 1fr;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._entities = [];
        this._relationships = [];
        this._selectedRootId = '';
        this._maxDepth = 5;
        this._loading = false;
        this._graphNodes = [];
        this._graphEdges = [];
        this._pathSourceId = '';
        this._pathTargetId = '';
        this._shortestPathEdges = [];
        this._findingPath = false;
        this._entitySearchQuery = '';
        this._viewMode = 'influence';
        this._relatedDirection = 'both';
        this._relationshipTypeFilter = '';
        this._pathMaxDepth = 10;
        this._selectedNodeId = '';
        this._selectedEdgeId = '';
        this._graphPreset = 'readable';
        this._backendOperationId = 'getEntities';
        this._backendOperationArgs = '[{"limit":100}]';
        this._backendOperationResult = '';
        this._backendLoading = false;
        this._attachmentEntityId = '';
        this._attachmentFile = null;
        this._entityFormId = '';
        this._entityFormName = '';
        this._entityFormType = 'contact';
        this._entityFormNamespace = 'default';
        this._entityFormDescription = '';
        this._relationshipFormId = '';
        this._relationshipSourceId = '';
        this._relationshipTargetId = '';
        this._relationshipType = 'knows';
        this._grantEntityId = '';
        this._grantNamespace = 'default';
        this._grantUserId = '';
        this._grantCompanyId = '';
        this._grantRole = 'viewer';
        this._grantId = '';
        this._accessRequestEntityId = '';
        this._accessRequestId = '';
        this._accessRequestMessage = '';
        this._accessRequestDepth = 1;
        this._namespaceNameInput = '';
        this._namespaceTemplateIdInput = '';
        this._namespaceDescriptionInput = '';
        this._isFullscreen = false;
        this._defaultOverviewActive = true;
        this._showSidePanel = false;
        this._canvasPathState = 'idle';
        this._canvasPathHint = 'Режим обзора';
        this._labelMode = 'adaptive';
        this._graphInstance = null;
        this._onSearchQueryInput = this._onSearchQueryInput.bind(this);
        this._onModeChange = this._onModeChange.bind(this);
        this._onRootChange = this._onRootChange.bind(this);
        this._onDepthChange = this._onDepthChange.bind(this);
        this._onPathDepthChange = this._onPathDepthChange.bind(this);
        this._onRelationshipTypeFilterChange = this._onRelationshipTypeFilterChange.bind(this);
        this._onRelatedDirectionChange = this._onRelatedDirectionChange.bind(this);
        this._onPathSourceChange = this._onPathSourceChange.bind(this);
        this._onPathTargetChange = this._onPathTargetChange.bind(this);
        this._onPresetChange = this._onPresetChange.bind(this);
        this._onSearchEntity = this._onSearchEntity.bind(this);
        this._onBackendOperationChange = this._onBackendOperationChange.bind(this);
        this._onBackendArgsInput = this._onBackendArgsInput.bind(this);
        this._injectSelectedNodeToArgs = this._injectSelectedNodeToArgs.bind(this);
        this._runBackendOperation = this._runBackendOperation.bind(this);
        this._onAttachmentEntityIdInput = this._onAttachmentEntityIdInput.bind(this);
        this._onAttachmentFileChange = this._onAttachmentFileChange.bind(this);
        this._uploadAttachment = this._uploadAttachment.bind(this);
        this._loadGraphData = this._loadGraphData.bind(this);
        this._buildPathGraph = this._buildPathGraph.bind(this);
        this._focusSelectedNode = this._focusSelectedNode.bind(this);
        this._expandFromSelected = this._expandFromSelected.bind(this);
        this._isolateSelectedNeighborhood = this._isolateSelectedNeighborhood.bind(this);
        this._revealNextLevel = this._revealNextLevel.bind(this);
        this._onSimpleInput = this._onSimpleInput.bind(this);
        this._createEntityNative = this._createEntityNative.bind(this);
        this._updateEntityNative = this._updateEntityNative.bind(this);
        this._deleteEntityNative = this._deleteEntityNative.bind(this);
        this._createRelationshipNative = this._createRelationshipNative.bind(this);
        this._deleteRelationshipNative = this._deleteRelationshipNative.bind(this);
        this._grantEntityUserNative = this._grantEntityUserNative.bind(this);
        this._grantEntityCompanyNative = this._grantEntityCompanyNative.bind(this);
        this._grantEntityPublicNative = this._grantEntityPublicNative.bind(this);
        this._grantNamespaceUserNative = this._grantNamespaceUserNative.bind(this);
        this._grantNamespaceCompanyNative = this._grantNamespaceCompanyNative.bind(this);
        this._grantNamespacePublicNative = this._grantNamespacePublicNative.bind(this);
        this._revokeGrantNative = this._revokeGrantNative.bind(this);
        this._createAccessRequestNative = this._createAccessRequestNative.bind(this);
        this._listAccessRequestsNative = this._listAccessRequestsNative.bind(this);
        this._approveAccessRequestNative = this._approveAccessRequestNative.bind(this);
        this._rejectAccessRequestNative = this._rejectAccessRequestNative.bind(this);
        this._createNamespaceNative = this._createNamespaceNative.bind(this);
        this._loadNamespaceOverviewNative = this._loadNamespaceOverviewNative.bind(this);
        this._toggleFullscreen = this._toggleFullscreen.bind(this);
        this._fitGraphToViewport = this._fitGraphToViewport.bind(this);
        this._toggleSidePanel = this._toggleSidePanel.bind(this);
        this._startCanvasPathPicking = this._startCanvasPathPicking.bind(this);
        this._resetCanvasPathPicking = this._resetCanvasPathPicking.bind(this);
        this._swapCanvasPathEndpoints = this._swapCanvasPathEndpoints.bind(this);
        this._onCanvasNodeClick = this._onCanvasNodeClick.bind(this);
        this._toggleLabelMode = this._toggleLabelMode.bind(this);
    }

    async firstUpdated() {
        this._assertOfflineVendorSetup();
        await this._loadGraphData();
        this._initGraph();
        this._syncGraph();
    }

    updated(changedProperties) {
        if (
            changedProperties.has('_graphNodes')
            || changedProperties.has('_graphEdges')
            || changedProperties.has('_shortestPathEdges')
            || changedProperties.has('_graphPreset')
        ) {
            this._syncGraph();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._graphInstance) {
            this._graphInstance._destructor();
            this._graphInstance = null;
        }
    }

    _getRelationshipTypes() {
        const relationshipTypes = CRMStore.state.entities.relationshipTypes;
        if (!Array.isArray(relationshipTypes)) {
            throw new Error('relationshipTypes must be array');
        }
        return relationshipTypes;
    }

    _getNamespaceName() {
        return resolveObjectName(CRMStore.state.namespaces.current, null);
    }

    _getEntityMap() {
        return new Map(this._entities.map((entity) => [entity.entity_id, entity]));
    }

    _getEdgeId(edge) {
        const edgeId = edge.edge_id || edge.relationship_id || edge.id;
        if (typeof edgeId === 'string' && edgeId.trim().length > 0) {
            return edgeId;
        }
        const sourceId = edge.source_id || edge.source_entity_id || edge.source;
        const targetId = edge.target_id || edge.target_entity_id || edge.target;
        const relationType = edge.relationship_type || edge.type || 'related';
        return `${sourceId}:${targetId}:${relationType}`;
    }

    _resolveEntityById(entityId) {
        return this._entities.find((entity) => entity.entity_id === entityId) || null;
    }

    _nodeColor(node) {
        if (node.access === false) {
            return '#7f7f8f';
        }
        if (node.entity_type === 'note') {
            return '#ffb457';
        }
        if (node.entity_type === 'contact') {
            return '#7ac7ff';
        }
        if (node.entity_type === 'task') {
            return '#8ce9a2';
        }
        return '#bca8ff';
    }

    _isEdgeDirected(edge) {
        if (typeof edge.is_directed === 'boolean') {
            return edge.is_directed;
        }
        const relationTypeId = edge.relationship_type || edge.type;
        const relationshipType = this._getRelationshipTypes().find((item) => item.type_id === relationTypeId);
        if (!relationshipType) {
            return true;
        }
        return relationshipType.is_directed !== false;
    }

    _buildGraphDataForScene() {
        const highlightedEdgeIds = new Set(this._shortestPathEdges.map((edge) => this._getEdgeId(edge)));
        const nodes = this._graphNodes.map((node) => ({
            ...node,
            id: node.entity_id || node.id,
            name: node.name || node.label || node.entity_id || node.id,
            color: this._nodeColor(node),
            size: node.level === 0 ? 2.2 : 1.4,
        }));
        if (nodes.length === 1) {
            nodes[0].x = 0;
            nodes[0].y = 0;
            nodes[0].z = 0;
        }
        const links = this._graphEdges.map((edge) => {
            const source = edge.source_id || edge.source_entity_id || edge.source;
            const target = edge.target_id || edge.target_entity_id || edge.target;
            const edgeId = this._getEdgeId(edge);
            const relationType = edge.relationship_type || edge.type || 'related';
            const directed = this._isEdgeDirected(edge);
            return {
                ...edge,
                id: edgeId,
                source,
                target,
                relation_type: relationType,
                directed,
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
            throw new Error('Graph canvas is not available');
        }
        this._graphInstance = factory()(container)
            .backgroundColor('rgba(0,0,0,0)')
            .cooldownTicks(120)
            .warmupTicks(80)
            .showNavInfo(false)
            .nodeLabel((node) => {
                if (!this._shouldShowNodeLabel(node)) {
                    return '';
                }
                return node.name || node.id || '';
            })
            .nodeColor((node) => node.color)
            .nodeVal((node) => node.size)
            .linkLabel((link) => {
                if (!this._shouldShowLinkLabel(link)) {
                    return '';
                }
                return link.relation_type || link.id || '';
            })
            .linkColor((link) => (link.highlighted ? '#ff6b6b' : '#9ba3bf'))
            .linkWidth((link) => {
                if (link.highlighted) {
                    return 4;
                }
                if (this._isLinkNearSelectedNode(link)) {
                    return 2.8;
                }
                return GRAPH_PRESETS[this._graphPreset].linkWidth + 0.6;
            })
            .linkOpacity((link) => {
                if (link.highlighted || link.id === this._selectedEdgeId) {
                    return 0.95;
                }
                if (this._isLinkNearSelectedNode(link)) {
                    return 0.65;
                }
                return 0.3;
            })
            .linkDirectionalArrowLength((link) => (link.directed ? 3 : 0))
            .linkDirectionalArrowRelPos(1)
            .linkDirectionalParticles((link) => (link.highlighted ? 4 : 0))
            .linkDirectionalParticleWidth(3)
            .enableNodeDrag(true)
            .onNodeClick((node, event) => this._onCanvasNodeClick(node, event))
            .onNodeHover(() => {})
            .onLinkClick((link) => {
                this._selectedEdgeId = link.id;
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
                    this._applySingleNodeCamera();
                    return;
                }
                this._fitGraphToViewport(300, 70);
            });
        this._graphInstance.d3Force('charge').strength(GRAPH_PRESETS[this._graphPreset].charge);
        this._graphInstance.d3VelocityDecay(0.5);
        this._graphInstance.d3Force('box', this._createBoundingForce(GRAPH_WORLD_RADIUS));
        this._graphInstance.nodeRelSize(GRAPH_PRESETS[this._graphPreset].nodeRelSize);
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
        this._graphInstance.centerAt(0, 0, 0);
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
        }
        this._graphInstance.graphData(graphData);
        this._graphInstance.d3Force('charge').strength(GRAPH_PRESETS[this._graphPreset].charge);
        this._graphInstance.nodeRelSize(GRAPH_PRESETS[this._graphPreset].nodeRelSize);
        if (graphData.nodes.length === 0) {
            return;
        }
        if (graphData.nodes.length === 1) {
            if (this._graphInstance) {
                this._applySingleNodeCamera();
            }
            return;
        }
        requestAnimationFrame(() => {
            if (!this._graphInstance) {
                return;
            }
            this._fitGraphToViewport(260, 90);
        });
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

    _onSimpleInput(event) {
        const fieldName = event.target.dataset.field;
        if (!fieldName) {
            throw new Error('data-field is required for simple input binding');
        }
        this[fieldName] = event.target.value;
    }

    _toggleFullscreen() {
        this._isFullscreen = !this._isFullscreen;
    }

    _toggleSidePanel() {
        this._showSidePanel = !this._showSidePanel;
    }

    _toggleLabelMode() {
        this._labelMode = this._labelMode === 'adaptive' ? 'minimal' : 'adaptive';
        if (!this._graphInstance) {
            return;
        }
        this._graphInstance.nodeThreeObject(this._graphInstance.nodeThreeObject());
        this._graphInstance.linkThreeObject(this._graphInstance.linkThreeObject());
    }

    _startCanvasPathPicking() {
        this._canvasPathState = 'pick_source';
        this._canvasPathHint = 'Кликни на первую сущность (source)';
        this._viewMode = 'path';
        this._shortestPathEdges = [];
        this._pathSourceId = '';
        this._pathTargetId = '';
        this._showSidePanel = false;
    }

    async _resetCanvasPathPicking() {
        this._canvasPathState = 'idle';
        this._canvasPathHint = 'Режим обзора';
        this._pathSourceId = '';
        this._pathTargetId = '';
        this._shortestPathEdges = [];
        await this._rebuildGraphByMode();
    }

    async _swapCanvasPathEndpoints() {
        if (!this._pathSourceId || !this._pathTargetId) {
            throw new Error('Нужно выбрать source и target');
        }
        const sourceId = this._pathSourceId;
        this._pathSourceId = this._pathTargetId;
        this._pathTargetId = sourceId;
        await this._buildPathGraph();
    }

    _shouldShowNodeLabel(node) {
        if (this._labelMode !== 'adaptive') {
            return false;
        }
        const isImportant = node.id === this._selectedNodeId
            || node.id === this._pathSourceId
            || node.id === this._pathTargetId;
        if (isImportant) {
            return true;
        }
        if (this._graphNodes.length <= 80) {
            return true;
        }
        const distance = this._getCameraDistance();
        if (distance < ADAPTIVE_LABEL_DISTANCE && this._graphNodes.length <= 220) {
            return true;
        }
        return false;
    }

    _shouldShowLinkLabel(link) {
        if (this._labelMode !== 'adaptive') {
            return false;
        }
        if (link.id === this._selectedEdgeId || link.highlighted) {
            return true;
        }
        if (this._graphEdges.length <= 70 && this._getCameraDistance() < ADAPTIVE_LABEL_DISTANCE * 0.9) {
            return true;
        }
        return false;
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
        if (!this._selectedNodeId) {
            return false;
        }
        const sourceId = this._getLinkEndpointId(link.source);
        const targetId = this._getLinkEndpointId(link.target);
        return sourceId === this._selectedNodeId || targetId === this._selectedNodeId;
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

    _onCanvasNodeClick(node, event) {
        this._selectedNodeId = node.id;
        this._attachmentEntityId = node.id;
        if (event?.altKey) {
            this._onOpenEntity(node.id);
            return;
        }
        if (this._canvasPathState === 'pick_source') {
            this._pathSourceId = node.id;
            this._pathTargetId = '';
            this._canvasPathState = 'pick_target';
            this._canvasPathHint = 'Кликни на вторую сущность (target)';
            return;
        }
        if (this._canvasPathState === 'pick_target') {
            if (node.id === this._pathSourceId) {
                throw new Error('Source и target должны быть разными');
            }
            this._pathTargetId = node.id;
            this._canvasPathState = 'built';
            this._canvasPathHint = 'Маршрут построен';
            this._buildPathGraph().catch((error) => {
                const message = error instanceof Error ? error.message : String(error);
                this.error(`Ошибка построения маршрута: ${message}`);
            });
            return;
        }
        this._canvasPathHint = 'Режим обзора';
    }

    _getNativeOperationIds() {
        return new Set([
            'getEntities',
            'searchEntities',
            'createEntity',
            'updateEntity',
            'deleteEntity',
            'createRelationship',
            'deleteRelationship',
            'getInfluenceGraph',
            'getRelatedEntities',
            'getShortestPath',
            'grantToUser',
            'grantToCompany',
            'makeEntityPublic',
            'grantNamespaceToUser',
            'grantNamespaceToCompany',
            'makeNamespacePublic',
            'revokeGrant',
            'createAccessRequest',
            'approveAccessRequest',
            'rejectAccessRequest',
            'getNamespaces',
            'createNamespace',
            'getNamespaceTemplates',
            'getNamespaceGrants',
            'getEntityAttachments',
            'uploadAttachment',
            'deleteAttachment',
        ]);
    }

    _getCoverageMatrix() {
        if (!this.crmApi) {
            throw new Error('crmApi service is required to build coverage matrix');
        }
        const nativeOperations = this._getNativeOperationIds();
        const operationsByMethod = new Map();
        this._getBackendOperations().forEach((operation) => {
            operationsByMethod.set(operation.method, operation);
        });
        const ownMethodNames = Object.keys(this.crmApi)
            .filter((methodName) => typeof this.crmApi[methodName] === 'function');
        const prototypeRef = Object.getPrototypeOf(this.crmApi);
        const prototypeMethodNames = prototypeRef && prototypeRef !== Object.prototype
            ? Object.getOwnPropertyNames(prototypeRef)
                .filter((methodName) => methodName !== 'constructor' && typeof this.crmApi[methodName] === 'function')
            : [];
        const apiMethodNames = Array.from(new Set([...ownMethodNames, ...prototypeMethodNames]));
        return apiMethodNames.map((methodName) => {
            const operation = operationsByMethod.get(methodName);
            if (!operation) {
                return {
                    id: methodName,
                    label: methodName,
                    method: methodName,
                    status: 'not_covered',
                };
            }
            const status = nativeOperations.has(operation.method)
                ? 'covered_by_native_ui'
                : 'covered_by_json_runner_only';
            return {
                ...operation,
                status,
            };
        });
    }

    async _executeNativeAction(actionLabel, executor) {
        this._backendLoading = true;
        try {
            const result = await executor();
            this._backendOperationResult = JSON.stringify(result, null, 2);
            await this._loadGraphData();
            this.success(`Выполнено: ${actionLabel}`);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this._backendOperationResult = `Error: ${message}`;
            this.error(`Ошибка операции ${actionLabel}: ${message}`);
        } finally {
            this._backendLoading = false;
        }
    }

    async _createEntityNative() {
        if (!this._entityFormName.trim()) {
            throw new Error('Entity name is required');
        }
        await this._executeNativeAction('create entity', () => this.crmApi.createEntity({
            entity_type: this._entityFormType.trim(),
            name: this._entityFormName.trim(),
            namespace: this._entityFormNamespace.trim(),
            description: this._entityFormDescription.trim() || null,
            attributes: {},
        }));
    }

    async _updateEntityNative() {
        if (!this._entityFormId.trim()) {
            throw new Error('Entity ID is required');
        }
        if (!this._entityFormName.trim()) {
            throw new Error('Entity name is required');
        }
        await this._executeNativeAction('update entity', () => this.crmApi.updateEntity(
            this._entityFormId.trim(),
            { name: this._entityFormName.trim(), description: this._entityFormDescription.trim() || null },
        ));
    }

    async _deleteEntityNative() {
        if (!this._entityFormId.trim()) {
            throw new Error('Entity ID is required');
        }
        await this._executeNativeAction('delete entity', () => this.crmApi.deleteEntity(this._entityFormId.trim()));
    }

    async _createRelationshipNative() {
        if (!this._relationshipSourceId.trim() || !this._relationshipTargetId.trim() || !this._relationshipType.trim()) {
            throw new Error('Source, target and relationship type are required');
        }
        await this._executeNativeAction('create relationship', () => this.crmApi.createRelationship({
            source_entity_id: this._relationshipSourceId.trim(),
            target_entity_id: this._relationshipTargetId.trim(),
            relationship_type: this._relationshipType.trim(),
            weight: 1.0,
        }));
    }

    async _deleteRelationshipNative() {
        if (!this._relationshipFormId.trim()) {
            throw new Error('Relationship ID is required');
        }
        await this._executeNativeAction('delete relationship', () => this.crmApi.deleteRelationship(this._relationshipFormId.trim()));
    }

    async _grantEntityUserNative() {
        if (!this._grantEntityId.trim() || !this._grantUserId.trim()) {
            throw new Error('Entity ID and user ID are required');
        }
        await this._executeNativeAction('grant entity to user', () => this.crmApi.grantToUser(
            this._grantEntityId.trim(),
            this._grantUserId.trim(),
            this._grantRole.trim(),
        ));
    }

    async _grantEntityCompanyNative() {
        if (!this._grantEntityId.trim() || !this._grantCompanyId.trim()) {
            throw new Error('Entity ID and company ID are required');
        }
        await this._executeNativeAction('grant entity to company', () => this.crmApi.grantToCompany(
            this._grantEntityId.trim(),
            this._grantCompanyId.trim(),
            this._grantRole.trim(),
        ));
    }

    async _grantEntityPublicNative() {
        if (!this._grantEntityId.trim()) {
            throw new Error('Entity ID is required');
        }
        await this._executeNativeAction('make entity public', () => this.crmApi.makeEntityPublic(this._grantEntityId.trim()));
    }

    async _grantNamespaceUserNative() {
        if (!this._grantNamespace.trim() || !this._grantUserId.trim()) {
            throw new Error('Namespace and user ID are required');
        }
        await this._executeNativeAction('grant namespace to user', () => this.crmApi.grantNamespaceToUser(
            this._grantNamespace.trim(),
            this._grantUserId.trim(),
            this._grantRole.trim(),
        ));
    }

    async _grantNamespaceCompanyNative() {
        if (!this._grantNamespace.trim() || !this._grantCompanyId.trim()) {
            throw new Error('Namespace and company ID are required');
        }
        await this._executeNativeAction('grant namespace to company', () => this.crmApi.grantNamespaceToCompany(
            this._grantNamespace.trim(),
            this._grantCompanyId.trim(),
            this._grantRole.trim(),
        ));
    }

    async _grantNamespacePublicNative() {
        if (!this._grantNamespace.trim()) {
            throw new Error('Namespace is required');
        }
        await this._executeNativeAction('make namespace public', () => this.crmApi.makeNamespacePublic(this._grantNamespace.trim()));
    }

    async _revokeGrantNative() {
        if (!this._grantId.trim()) {
            throw new Error('Grant ID is required');
        }
        await this._executeNativeAction('revoke grant', () => this.crmApi.revokeGrant(this._grantId.trim()));
    }

    async _createAccessRequestNative() {
        if (!this._accessRequestEntityId.trim()) {
            throw new Error('Entity ID is required');
        }
        await this._executeNativeAction('create access request', () => this.crmApi.createAccessRequest(
            this._accessRequestEntityId.trim(),
            this._accessRequestMessage.trim() || null,
            true,
            Number(this._accessRequestDepth),
        ));
    }

    async _listAccessRequestsNative() {
        await this._executeNativeAction('list access requests', () => this.crmApi.listAccessRequests(null));
    }

    async _approveAccessRequestNative() {
        if (!this._accessRequestId.trim()) {
            throw new Error('Request ID is required');
        }
        await this._executeNativeAction('approve access request', () => this.crmApi.approveAccessRequest(this._accessRequestId.trim()));
    }

    async _rejectAccessRequestNative() {
        if (!this._accessRequestId.trim()) {
            throw new Error('Request ID is required');
        }
        await this._executeNativeAction('reject access request', () => this.crmApi.rejectAccessRequest(this._accessRequestId.trim()));
    }

    async _createNamespaceNative() {
        if (!this._namespaceNameInput.trim()) {
            throw new Error('Namespace name is required');
        }
        if (!this._namespaceTemplateIdInput.trim()) {
            throw new Error('Template ID is required');
        }
        await this._executeNativeAction('create namespace', () => this.crmApi.createNamespace(
            this._namespaceNameInput.trim(),
            this._namespaceDescriptionInput.trim() || null,
            this._namespaceTemplateIdInput.trim(),
        ));
    }

    async _loadNamespaceOverviewNative() {
        await this._executeNativeAction('load namespace overview', async () => {
            const payload = {};
            payload.namespaces = await this.crmApi.getNamespaces();
            payload.templates = await this.crmApi.getNamespaceTemplates();
            if (this._grantNamespace.trim()) {
                payload.namespace_grants = await this.crmApi.getNamespaceGrants(this._grantNamespace.trim());
            }
            return payload;
        });
    }

    _focusSelectedNode() {
        if (!this._selectedNodeId) {
            throw new Error('Select node before focus action');
        }
        const node = this._buildGraphDataForScene().nodes.find((item) => item.id === this._selectedNodeId);
        if (!node) {
            throw new Error(`Selected node not found in scene: ${this._selectedNodeId}`);
        }
        this._graphInstance.cameraPosition(
            { x: node.x || 0, y: node.y || 0, z: (node.z || 0) + 80 },
            { x: node.x || 0, y: node.y || 0, z: node.z || 0 },
            1200,
        );
    }

    async _expandFromSelected() {
        if (!this._selectedNodeId) {
            throw new Error('Select node before expand action');
        }
        this._defaultOverviewActive = false;
        this._selectedRootId = this._selectedNodeId;
        this._maxDepth = Math.min(this._maxDepth + 1, 5);
        await this._rebuildGraphByMode();
    }

    _isolateSelectedNeighborhood() {
        if (!this._selectedNodeId) {
            throw new Error('Select node before isolate action');
        }
        const neighborhoodIds = new Set([this._selectedNodeId]);
        for (const edge of this._graphEdges) {
            const sourceId = edge.source_id || edge.source_entity_id || edge.source;
            const targetId = edge.target_id || edge.target_entity_id || edge.target;
            if (sourceId === this._selectedNodeId) {
                neighborhoodIds.add(targetId);
            }
            if (targetId === this._selectedNodeId) {
                neighborhoodIds.add(sourceId);
            }
        }
        this._graphNodes = this._graphNodes.filter((node) => neighborhoodIds.has(node.entity_id || node.id));
        this._graphEdges = this._graphEdges.filter((edge) => {
            const sourceId = edge.source_id || edge.source_entity_id || edge.source;
            const targetId = edge.target_id || edge.target_entity_id || edge.target;
            return neighborhoodIds.has(sourceId) && neighborhoodIds.has(targetId);
        });
    }

    async _revealNextLevel() {
        this._maxDepth = Math.min(this._maxDepth + 1, 5);
        await this._rebuildGraphByMode();
    }

    async _loadGraphData() {
        this._loading = true;
        try {
            const crmApi = this.crmApi;
            const namespaceName = this._getNamespaceName();
            const entities = await crmApi.getEntities({ namespace: namespaceName, limit: 400 });
            this._entities = Array.isArray(entities) ? entities : [];
            if (!this._selectedRootId && this._entities.length > 0) {
                this._selectedRootId = CRMStore.state.entities.currentEntityId || this._entities[0].entity_id;
            }
            if (!this._pathSourceId && this._entities.length > 0) {
                this._pathSourceId = this._selectedRootId;
            }
            if (!this._pathTargetId && this._entities.length > 1) {
                const target = this._entities.find((entity) => entity.entity_id !== this._pathSourceId);
                this._pathTargetId = target ? target.entity_id : this._entities[0].entity_id;
            }
            await this._rebuildGraphByMode();
        } finally {
            this._loading = false;
        }
    }

    async _rebuildGraphByMode() {
        if (!VIEW_MODES.includes(this._viewMode)) {
            throw new Error(`Unsupported graph mode: ${this._viewMode}`);
        }
        if (this._viewMode === 'influence' && this._defaultOverviewActive) {
            await this._buildLatestEntitiesInfluenceGraph();
            return;
        }
        if (!this._selectedRootId) {
            this._graphNodes = [];
            this._graphEdges = [];
            return;
        }
        if (this._viewMode === 'influence') {
            await this._buildInfluenceGraph();
            return;
        }
        if (this._viewMode === 'related') {
            await this._buildRelatedGraph();
            return;
        }
        await this._buildPathGraph();
    }

    async _buildLatestEntitiesInfluenceGraph() {
        const seedEntities = this._entities.slice(0, 20);
        if (seedEntities.length === 0) {
            this._graphNodes = [];
            this._graphEdges = [];
            this._shortestPathEdges = [];
            return;
        }
        const relationshipType = this._getRelationshipFilter();
        const params = { max_depth: this._maxDepth };
        if (relationshipType) {
            params.relationship_types = relationshipType;
        }
        const responses = await Promise.all(
            seedEntities.map((entity) => this.crmApi.getInfluenceGraph(entity.entity_id, params)),
        );
        const nodeMap = new Map();
        const edgeMap = new Map();
        for (const response of responses) {
            if (!response || typeof response !== 'object') {
                throw new Error('Influence graph response must be object');
            }
            if (!Array.isArray(response.nodes) || !Array.isArray(response.edges)) {
                throw new Error('Influence graph response must contain nodes and edges arrays');
            }
            response.nodes.forEach((node) => {
                const nodeId = node.entity_id || node.id;
                if (!nodeId) {
                    throw new Error('Graph node must have entity_id or id');
                }
                if (!nodeMap.has(nodeId)) {
                    nodeMap.set(nodeId, node);
                    return;
                }
                const existingNode = nodeMap.get(nodeId);
                if (existingNode.access === false && node.access !== false) {
                    nodeMap.set(nodeId, node);
                }
            });
            response.edges.forEach((edge) => {
                edgeMap.set(this._getEdgeId(edge), edge);
            });
        }
        this._shortestPathEdges = [];
        this._graphNodes = Array.from(nodeMap.values());
        this._graphEdges = Array.from(edgeMap.values());
    }

    _getRelationshipFilter() {
        const trimmedValue = this._relationshipTypeFilter.trim();
        if (trimmedValue.length === 0) {
            return null;
        }
        return trimmedValue;
    }

    async _buildInfluenceGraph() {
        const relationshipType = this._getRelationshipFilter();
        const params = { max_depth: this._maxDepth };
        if (relationshipType) {
            params.relationship_types = relationshipType;
        }
        const response = await this.crmApi.getInfluenceGraph(this._selectedRootId, params);
        if (!response || typeof response !== 'object') {
            throw new Error('Influence graph response must be object');
        }
        this._graphNodes = Array.isArray(response.nodes) ? response.nodes : [];
        this._graphEdges = Array.isArray(response.edges) ? response.edges : [];
        this._relationships = this._graphEdges;
    }

    async _buildRelatedGraph() {
        const relationshipType = this._getRelationshipFilter();
        const params = { direction: this._relatedDirection };
        if (relationshipType) {
            params.relationship_type = relationshipType;
        }
        const relatedResponse = await this.crmApi.getRelatedEntities(this._selectedRootId, params);
        if (!relatedResponse || typeof relatedResponse !== 'object') {
            throw new Error('Related entities response must be object');
        }
        const nodeMap = new Map();
        const rootEntity = this._resolveEntityById(this._selectedRootId);
        if (!rootEntity) {
            throw new Error(`Root entity not found in local cache: ${this._selectedRootId}`);
        }
        nodeMap.set(this._selectedRootId, {
            entity_id: rootEntity.entity_id,
            entity_type: rootEntity.entity_type,
            name: rootEntity.name,
            level: 0,
            access: true,
            attributes: rootEntity.attributes || {},
        });
        for (const bucket of ['incoming', 'outgoing', 'undirected']) {
            const collection = relatedResponse[bucket];
            if (!Array.isArray(collection)) {
                throw new Error(`Related entities bucket must be array: ${bucket}`);
            }
            for (const node of collection) {
                nodeMap.set(node.entity_id, node);
            }
        }
        const relationshipsResponse = await this.crmApi.getEntityRelationships(this._selectedRootId, { namespace: this._getNamespaceName() });
        if (!relationshipsResponse || typeof relationshipsResponse !== 'object') {
            throw new Error('Entity relationships response must be object');
        }
        if (!Array.isArray(relationshipsResponse.relationships)) {
            throw new Error('relationships must be array');
        }
        const relationType = this._getRelationshipFilter();
        const nodeIds = new Set(nodeMap.keys());
        const filteredEdges = relationshipsResponse.relationships.filter((edge) => {
            const source = edge.source_entity_id;
            const target = edge.target_entity_id;
            if (!nodeIds.has(source) || !nodeIds.has(target)) {
                return false;
            }
            if (relationType && edge.relationship_type !== relationType) {
                return false;
            }
            return true;
        });
        this._graphNodes = Array.from(nodeMap.values());
        this._graphEdges = filteredEdges;
        this._relationships = filteredEdges;
    }

    async _buildPathGraph() {
        this._defaultOverviewActive = false;
        if (!this._pathSourceId || !this._pathTargetId) {
            throw new Error('Both source and target entities are required');
        }
        if (this._pathSourceId === this._pathTargetId) {
            throw new Error('Source and target entities must be different');
        }
        this._findingPath = true;
        let response;
        try {
            response = await this.crmApi.getShortestPath(this._pathSourceId, this._pathTargetId, {
                max_depth: this._pathMaxDepth,
                namespace: this._getNamespaceName(),
            });
        } finally {
            this._findingPath = false;
        }
        if (!response || typeof response !== 'object') {
            throw new Error('Shortest path response must be object');
        }
        if (!Array.isArray(response.path)) {
            throw new Error('Shortest path must include path array');
        }
        if (!Array.isArray(response.edges)) {
            throw new Error('Shortest path must include edges array');
        }
        this._shortestPathEdges = response.edges;
        const entityMap = this._getEntityMap();
        const nodes = response.path.map((entityId, index) => {
            const entity = entityMap.get(entityId);
            if (!entity) {
                return {
                    entity_id: entityId,
                    entity_type: 'hidden',
                    name: 'Hidden',
                    level: index,
                    access: false,
                    attributes: null,
                };
            }
            return {
                entity_id: entity.entity_id,
                entity_type: entity.entity_type,
                name: entity.name,
                level: index,
                access: true,
                attributes: entity.attributes || {},
            };
        });
        this._graphNodes = nodes;
        this._graphEdges = response.edges;
        this._canvasPathState = 'built';
        this._canvasPathHint = 'Маршрут построен';
    }

    _onOpenEntity(entityId) {
        CRMStore.setCurrentView('entities');
        CRMStore.setCurrentEntity(entityId);
    }

    _onSearchQueryInput(event) {
        this._entitySearchQuery = event.target.value;
    }

    _onModeChange(event) {
        this._viewMode = event.target.value;
        if (this._viewMode !== 'influence') {
            this._defaultOverviewActive = false;
        }
        if (this._viewMode !== 'path') {
            this._canvasPathState = 'idle';
            this._canvasPathHint = 'Режим обзора';
        }
        this._rebuildGraphByMode();
    }

    _onRootChange(event) {
        this._defaultOverviewActive = false;
        this._selectedRootId = event.target.value;
        this._pathSourceId = event.target.value;
        this._rebuildGraphByMode();
    }

    _onDepthChange(event) {
        this._maxDepth = Number(event.target.value);
        this._rebuildGraphByMode();
    }

    _onPathDepthChange(event) {
        this._pathMaxDepth = Number(event.target.value);
    }

    _onRelationshipTypeFilterChange(event) {
        this._relationshipTypeFilter = event.target.value;
        this._rebuildGraphByMode();
    }

    _onRelatedDirectionChange(event) {
        this._relatedDirection = event.target.value;
        this._rebuildGraphByMode();
    }

    _onPathSourceChange(event) {
        this._pathSourceId = event.target.value;
    }

    _onPathTargetChange(event) {
        this._pathTargetId = event.target.value;
    }

    _onPresetChange(event) {
        this._graphPreset = event.target.value;
    }

    async _onSearchEntity() {
        const query = this._entitySearchQuery.trim();
        if (!query) {
            throw new Error('Search query is required');
        }
        const response = await this.crmApi.searchEntities(query, { namespace: this._getNamespaceName(), limit: 20 });
        const entities = Array.isArray(response) ? response : response?.entities;
        if (!Array.isArray(entities) || entities.length === 0) {
            throw new Error('Search returned no entities');
        }
        this._defaultOverviewActive = false;
        this._selectedRootId = entities[0].entity_id;
        this._pathSourceId = entities[0].entity_id;
        await this._rebuildGraphByMode();
        this.success(`Фокус графа: ${entities[0].name}`);
    }

    _getBackendOperations() {
        return [
            { id: 'getEntities', label: 'Entities: list', method: 'getEntities', args: '[{"limit":100}]' },
            { id: 'getEntity', label: 'Entities: get by id', method: 'getEntity', args: '["entity_id"]' },
            { id: 'createEntity', label: 'Entities: create', method: 'createEntity', args: '[{"entity_type":"contact","name":"New Contact","namespace":"default","attributes":{}}]' },
            { id: 'updateEntity', label: 'Entities: update', method: 'updateEntity', args: '["entity_id",{"name":"Updated Name"}]' },
            { id: 'deleteEntity', label: 'Entities: delete', method: 'deleteEntity', args: '["entity_id"]' },
            { id: 'searchEntities', label: 'Entities: search', method: 'searchEntities', args: '["query",{"limit":20}]' },
            { id: 'findEntitiesByText', label: 'Entities: find by text', method: 'findEntitiesByText', args: '["Any text with mentions"]' },
            { id: 'analyzeText', label: 'Entities: analyze text', method: 'analyzeText', args: '["Call John about project",null,{"checkDuplicates":true}]' },
            { id: 'getEntityTypes', label: 'Entities: list types', method: 'getEntityTypes', args: '[]' },
            { id: 'getEntityTypesByNamespace', label: 'Entities: list types by namespace', method: 'getEntityTypesByNamespace', args: '["default"]' },
            { id: 'createEntityType', label: 'Entities: create type', method: 'createEntityType', args: '[{"type_id":"custom_type","name":"Custom Type","description":"Custom"}]' },
            { id: 'getEntityCard', label: 'Entities: card', method: 'getEntityCard', args: '["entity_id"]' },
            { id: 'getEntityRelationships', label: 'Entities: relationships', method: 'getEntityRelationships', args: '["entity_id",{}]' },
            { id: 'getEntityWithRelatedEntities', label: 'Entities: with related', method: 'getEntityWithRelatedEntities', args: '["entity_id"]' },
            { id: 'getDailySummary', label: 'Entities: daily summary', method: 'getDailySummary', args: '["2026-03-29",{"forceRebuild":false}]' },
            { id: 'getRelationships', label: 'Relationships: list', method: 'getRelationships', args: '[{"limit":500}]' },
            { id: 'getRelationship', label: 'Relationships: get by id', method: 'getRelationship', args: '["relationship_id"]' },
            { id: 'createRelationship', label: 'Relationships: create', method: 'createRelationship', args: '[{"source_entity_id":"source","target_entity_id":"target","relationship_type":"knows","weight":1.0}]' },
            { id: 'deleteRelationship', label: 'Relationships: delete', method: 'deleteRelationship', args: '["relationship_id"]' },
            { id: 'getRelationshipTypes', label: 'Relationships: list types', method: 'getRelationshipTypes', args: '[]' },
            { id: 'createRelationshipType', label: 'Relationships: create type', method: 'createRelationshipType', args: '[{"type_id":"new_rel","name":"New Relation","is_directed":true}]' },
            { id: 'getInfluenceGraph', label: 'Graph: influence', method: 'getInfluenceGraph', args: '["entity_id",{"max_depth":3}]' },
            { id: 'getRelatedEntities', label: 'Graph: related', method: 'getRelatedEntities', args: '["entity_id",{"direction":"both"}]' },
            { id: 'getShortestPath', label: 'Graph: shortest path', method: 'getShortestPath', args: '["source_id","target_id",{"max_depth":10}]' },
            { id: 'getEntityGrants', label: 'Grants: list entity grants', method: 'getEntityGrants', args: '["entity_id"]' },
            { id: 'grantToUser', label: 'Grants: entity grant user', method: 'grantToUser', args: '["entity_id","user_id","viewer"]' },
            { id: 'grantToCompany', label: 'Grants: entity grant company', method: 'grantToCompany', args: '["entity_id","company_id","viewer"]' },
            { id: 'makeEntityPublic', label: 'Grants: entity public', method: 'makeEntityPublic', args: '["entity_id"]' },
            { id: 'revokeGrant', label: 'Grants: revoke', method: 'revokeGrant', args: '["grant_id"]' },
            { id: 'listAccessRequests', label: 'Access Requests: list', method: 'listAccessRequests', args: '[null]' },
            { id: 'getAccessRequest', label: 'Access Requests: get', method: 'getAccessRequest', args: '["request_id"]' },
            { id: 'createAccessRequest', label: 'Access Requests: create', method: 'createAccessRequest', args: '["entity_id","Need access",true,2]' },
            { id: 'approveAccessRequest', label: 'Access Requests: approve', method: 'approveAccessRequest', args: '["request_id"]' },
            { id: 'rejectAccessRequest', label: 'Access Requests: reject', method: 'rejectAccessRequest', args: '["request_id"]' },
            { id: 'getNamespaces', label: 'Namespaces: list', method: 'getNamespaces', args: '[]' },
            { id: 'getNamespaceEditability', label: 'Namespaces: editability', method: 'getNamespaceEditability', args: '["default"]' },
            { id: 'updateNamespace', label: 'Namespaces: update', method: 'updateNamespace', args: '["default",{"display_name":"Default"}]' },
            { id: 'getNamespaceTemplates', label: 'Namespaces: list templates', method: 'getNamespaceTemplates', args: '[]' },
            { id: 'getTemplateSchemaOptions', label: 'Namespaces: schema options', method: 'getTemplateSchemaOptions', args: '[]' },
            { id: 'getNamespaceTemplate', label: 'Namespaces: get template', method: 'getNamespaceTemplate', args: '["template_id"]' },
            { id: 'createNamespaceTemplate', label: 'Namespaces: create template', method: 'createNamespaceTemplate', args: '[{"template_id":"new_template","name":"New Template","description":"desc","types":[]}]' },
            { id: 'updateNamespaceTemplate', label: 'Namespaces: update template', method: 'updateNamespaceTemplate', args: '["template_id",{"name":"Updated Template"}]' },
            { id: 'deleteNamespaceTemplate', label: 'Namespaces: delete template', method: 'deleteNamespaceTemplate', args: '["template_id"]' },
            { id: 'upsertNamespaceTemplateType', label: 'Namespaces: upsert template type', method: 'upsertNamespaceTemplateType', args: '["template_id",{"type_id":"meeting","name":"Meeting"}]' },
            { id: 'deleteNamespaceTemplateType', label: 'Namespaces: delete template type', method: 'deleteNamespaceTemplateType', args: '["template_id","type_id"]' },
            { id: 'createNamespace', label: 'Namespaces: create', method: 'createNamespace', args: '["new_namespace","Description","template_id"]' },
            { id: 'getNamespaceGrants', label: 'Namespace grants: list', method: 'getNamespaceGrants', args: '["default"]' },
            { id: 'grantNamespaceToUser', label: 'Namespace grants: user', method: 'grantNamespaceToUser', args: '["default","user_id","viewer"]' },
            { id: 'grantNamespaceToCompany', label: 'Namespace grants: company', method: 'grantNamespaceToCompany', args: '["default","company_id","viewer"]' },
            { id: 'makeNamespacePublic', label: 'Namespace grants: public', method: 'makeNamespacePublic', args: '["default"]' },
            { id: 'getEntityAttachments', label: 'Attachments: list', method: 'getEntityAttachments', args: '["entity_id"]' },
            { id: 'uploadAttachment', label: 'Attachments: upload', method: 'uploadAttachment', args: '["entity_id","<File object from native panel>"]' },
            { id: 'deleteAttachment', label: 'Attachments: delete', method: 'deleteAttachment', args: '["entity_id","attachment_id"]' },
        ];
    }

    _onBackendOperationChange(event) {
        this._backendOperationId = event.target.value;
        const operation = this._getBackendOperations().find((item) => item.id === this._backendOperationId);
        if (!operation) {
            throw new Error(`Unknown backend operation: ${this._backendOperationId}`);
        }
        this._backendOperationArgs = operation.args;
    }

    _onBackendArgsInput(event) {
        this._backendOperationArgs = event.target.value;
    }

    _injectSelectedNodeToArgs() {
        if (!this._selectedNodeId) {
            throw new Error('Select node in graph first');
        }
        this._backendOperationArgs = this._backendOperationArgs.replace(/entity_id|source_id|target_id/g, this._selectedNodeId);
    }

    async _runBackendOperation() {
        this._backendLoading = true;
        try {
            const operation = this._getBackendOperations().find((item) => item.id === this._backendOperationId);
            if (!operation) {
                throw new Error(`Unknown operation: ${this._backendOperationId}`);
            }
            const parsedArgs = JSON.parse(this._backendOperationArgs);
            if (!Array.isArray(parsedArgs)) {
                throw new Error('Operation args must be JSON array');
            }
            const method = this.crmApi[operation.method];
            if (typeof method !== 'function') {
                throw new Error(`CRM API method is missing: ${operation.method}`);
            }
            const result = await method.apply(this.crmApi, parsedArgs);
            this._backendOperationResult = JSON.stringify(result, null, 2);
            await this._loadGraphData();
            this.success(`Операция выполнена: ${operation.label}`);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this._backendOperationResult = `Error: ${message}`;
            this.error(`Ошибка операции: ${message}`);
        } finally {
            this._backendLoading = false;
        }
    }

    _onAttachmentEntityIdInput(event) {
        this._attachmentEntityId = event.target.value;
    }

    _onAttachmentFileChange(event) {
        const file = event.target.files?.[0];
        this._attachmentFile = file || null;
    }

    async _uploadAttachment() {
        if (!this._attachmentEntityId) {
            throw new Error('Entity ID is required for attachment upload');
        }
        if (!(this._attachmentFile instanceof File)) {
            throw new Error('Attachment file is required');
        }
        await this._executeNativeAction('upload attachment', () => this.crmApi.uploadAttachment(this._attachmentEntityId, this._attachmentFile));
    }

    _renderLegend() {
        return html`
            <div class="legend-item"><span class="legend-dot" style="background:#7ac7ff"></span> Contact</div>
            <div class="legend-item"><span class="legend-dot" style="background:#ffb457"></span> Note</div>
            <div class="legend-item"><span class="legend-dot" style="background:#8ce9a2"></span> Task</div>
            <div class="legend-item"><span class="legend-dot" style="background:#bca8ff"></span> Other</div>
            <div class="legend-item"><span class="legend-dot" style="background:#7f7f8f"></span> Hidden</div>
        `;
    }

    render() {
        const operations = this._getBackendOperations();
        const coverageMatrix = this._getCoverageMatrix();
        const coveredNativeCount = coverageMatrix.filter((item) => item.status === 'covered_by_native_ui').length;
        const coveredJsonCount = coverageMatrix.filter((item) => item.status === 'covered_by_json_runner_only').length;
        const uncoveredCount = coverageMatrix.filter((item) => item.status === 'not_covered').length;
        const relationshipTypes = this._getRelationshipTypes();
        return html`
            <div class="layout ${this._isFullscreen ? 'fullscreen' : ''}">
            <div class="toolbar">
                <div class="toolbar-title">
                    <platform-icon name="network" size="18"></platform-icon>
                    <span>3D Graph Studio</span>
                </div>
                <div class="toolbar-control">
                    <span class="toolbar-label">Режим</span>
                    <select class="toolbar-select" .value=${this._viewMode} @change=${this._onModeChange}>
                        <option value="influence">Граф влияния</option>
                        <option value="related">Связанные сущности</option>
                        <option value="path">Кратчайший путь</option>
                    </select>
                </div>
                <div class="toolbar-control">
                    <span class="toolbar-label">Глубина</span>
                    <select class="toolbar-select" .value=${String(this._maxDepth)} @change=${this._onDepthChange}>
                        <option value="1">1</option>
                        <option value="2">2</option>
                        <option value="3">3</option>
                        <option value="4">4</option>
                        <option value="5">5</option>
                    </select>
                </div>
                <div class="toolbar-control">
                    <span class="toolbar-label">Preset</span>
                    <select class="toolbar-select" .value=${this._graphPreset} @change=${this._onPresetChange}>
                        <option value="dense">Плотно</option>
                        <option value="readable">Читаемо</option>
                        <option value="presentation">Презентация</option>
                    </select>
                </div>
                <input
                    class="toolbar-input"
                    type="text"
                    .value=${this._entitySearchQuery}
                    placeholder="Поиск сущности..."
                    @input=${this._onSearchQueryInput}
                />
                <button class="btn btn-secondary" type="button" @click=${this._onSearchEntity}>Найти</button>
                <button class="btn btn-secondary" type="button" @click=${this._loadGraphData}>Обновить</button>
                <button class="btn btn-secondary" type="button" @click=${this._toggleLabelMode}>
                    ${this._labelMode === 'adaptive' ? 'Лейблы: adaptive' : 'Лейблы: minimal'}
                </button>
                <button class="btn btn-secondary" type="button" @click=${this._toggleSidePanel}>
                    ${this._showSidePanel ? 'Скрыть панель' : 'Показать панель'}
                </button>
                <button class="btn btn-secondary" type="button" @click=${this._toggleFullscreen}>
                    ${this._isFullscreen ? 'Выйти из fullscreen' : 'Fullscreen графа'}
                </button>
            </div>

            <div class="stats">
                <div class="stat-card">
                    <div class="stat-label">Сущностей</div>
                    <div class="stat-value">${this._entities.length}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Узлов в сцене</div>
                    <div class="stat-value">${this._graphNodes.length}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Связей в сцене</div>
                    <div class="stat-value">${this._graphEdges.length}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Ребер в path</div>
                    <div class="stat-value">${this._shortestPathEdges.length}</div>
                </div>
            </div>

            <div class="workspace">
                <section class="graph-panel">
                    <div class="panel-header">
                        <div class="panel-title">3D Graph</div>
                        <div class="row">
                            <span class="node-pill">node: ${this._selectedNodeId || '—'}</span>
                            <span class="node-pill">edge: ${this._selectedEdgeId || '—'}</span>
                            <span class="canvas-hint">${this._canvasPathHint}</span>
                            <button class="btn btn-secondary" type="button" @click=${this._startCanvasPathPicking}>Построить маршрут</button>
                            <button class="btn btn-secondary" type="button" @click=${this._swapCanvasPathEndpoints}>Поменять точки</button>
                            <button class="btn btn-secondary" type="button" @click=${this._resetCanvasPathPicking}>Сбросить маршрут</button>
                            <button class="btn btn-secondary" type="button" @click=${() => this._fitGraphToViewport(250, 80)}>
                                Вписать граф
                            </button>
                            <button class="btn btn-secondary" type="button" @click=${this._toggleFullscreen}>
                                ${this._isFullscreen ? 'Обычный вид' : 'Fullscreen'}
                            </button>
                        </div>
                    </div>
                    <div id="graph-canvas" class="graph-canvas"></div>
                    <div class="legend">${this._renderLegend()}</div>
                </section>

                <section class="control-panel ${this._showSidePanel ? '' : 'hidden'}">
                    <div class="panel-header">
                        <div class="panel-title">Панель действий</div>
                    </div>
                    <div class="control-body">
                        <div class="section">
                            <div class="section-title">Быстрая навигация по графу</div>
                            <div class="small">Работаем с канвой: кликни по узлам для выбора и маршрута.</div>
                            <div class="section-grid">
                                <select class="toolbar-select" .value=${this._relationshipTypeFilter} @change=${this._onRelationshipTypeFilterChange}>
                                    <option value="">Все типы связей</option>
                                    ${relationshipTypes.map((item) => html`<option value=${item.type_id}>${item.name}</option>`)}
                                </select>
                                <select class="toolbar-select" .value=${this._relatedDirection} @change=${this._onRelatedDirectionChange}>
                                    <option value="both">Обе стороны</option>
                                    <option value="incoming">Входящие</option>
                                    <option value="outgoing">Исходящие</option>
                                </select>
                            </div>
                            <div class="section-grid">
                                <input class="toolbar-input" type="number" min="1" max="20" .value=${String(this._pathMaxDepth)} @input=${this._onPathDepthChange} />
                                <div class="small">Маршрут: нажми \"Построить маршрут\" в хедере канвы и кликни 2 узла</div>
                            </div>
                            <div class="row">
                                <button class="btn btn-secondary" type="button" @click=${this._focusSelectedNode}>Фокус на выбранном узле</button>
                                <button class="btn btn-secondary" type="button" @click=${this._expandFromSelected}>Раскрыть соседей</button>
                                <button class="btn btn-secondary" type="button" @click=${this._isolateSelectedNeighborhood}>Оставить только окружение</button>
                                <button class="btn btn-secondary" type="button" @click=${this._revealNextLevel}>Показать следующий уровень</button>
                            </div>
                        </div>

                        <details class="section-collapsible">
                            <summary>Расширенный backend runner (диагностика)</summary>
                            <div class="section-collapsible-content">
                                <select class="toolbar-select" .value=${this._backendOperationId} @change=${this._onBackendOperationChange}>
                                    ${operations.map((item) => html`<option value=${item.id}>${item.label}</option>`)}
                                </select>
                                <textarea class="textarea" .value=${this._backendOperationArgs} @input=${this._onBackendArgsInput}></textarea>
                                <div class="row">
                                    <button class="btn btn-secondary" type="button" @click=${this._injectSelectedNodeToArgs}>Подставить selected node</button>
                                    <button class="btn btn-primary" type="button" ?disabled=${this._backendLoading} @click=${this._runBackendOperation}>
                                        ${this._backendLoading ? 'Выполняю...' : 'Выполнить'}
                                    </button>
                                </div>
                                <div class="small">JSON-массив аргументов: каждый элемент — отдельный аргумент метода API.</div>
                            </div>
                        </details>

                        <details class="section-collapsible">
                            <summary>Матрица покрытия API</summary>
                            <div class="section-collapsible-content">
                                <div class="small">native: ${coveredNativeCount}, json-only: ${coveredJsonCount}, not-covered: ${uncoveredCount}</div>
                                <div class="result-box">${coverageMatrix.map((item) => `${item.method} -> ${item.status}`).join('\n')}</div>
                            </div>
                        </details>

                        <details class="section-collapsible">
                            <summary>Сущности</summary>
                            <div class="section-collapsible-content">
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_entityFormId" .value=${this._entityFormId} placeholder="entity_id" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" data-field="_entityFormName" .value=${this._entityFormName} placeholder="name" @input=${this._onSimpleInput} />
                                </div>
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_entityFormType" .value=${this._entityFormType} placeholder="entity_type" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" data-field="_entityFormNamespace" .value=${this._entityFormNamespace} placeholder="namespace" @input=${this._onSimpleInput} />
                                </div>
                                <input class="toolbar-input" data-field="_entityFormDescription" .value=${this._entityFormDescription} placeholder="description" @input=${this._onSimpleInput} />
                                <div class="row">
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._createEntityNative}>Создать</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._updateEntityNative}>Обновить</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._deleteEntityNative}>Удалить</button>
                                </div>
                            </div>
                        </details>

                        <details class="section-collapsible">
                            <summary>Связи</summary>
                            <div class="section-collapsible-content">
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_relationshipFormId" .value=${this._relationshipFormId} placeholder="relationship_id" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" data-field="_relationshipType" .value=${this._relationshipType} placeholder="relationship_type" @input=${this._onSimpleInput} />
                                </div>
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_relationshipSourceId" .value=${this._relationshipSourceId} placeholder="source_entity_id" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" data-field="_relationshipTargetId" .value=${this._relationshipTargetId} placeholder="target_entity_id" @input=${this._onSimpleInput} />
                                </div>
                                <div class="row">
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._createRelationshipNative}>Создать связь</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._deleteRelationshipNative}>Удалить связь</button>
                                </div>
                            </div>
                        </details>

                        <details class="section-collapsible">
                            <summary>Права доступа (grants)</summary>
                            <div class="section-collapsible-content">
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_grantEntityId" .value=${this._grantEntityId} placeholder="entity_id" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" data-field="_grantNamespace" .value=${this._grantNamespace} placeholder="namespace" @input=${this._onSimpleInput} />
                                </div>
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_grantUserId" .value=${this._grantUserId} placeholder="user_id" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" data-field="_grantCompanyId" .value=${this._grantCompanyId} placeholder="company_id" @input=${this._onSimpleInput} />
                                </div>
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_grantRole" .value=${this._grantRole} placeholder="role" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" data-field="_grantId" .value=${this._grantId} placeholder="grant_id" @input=${this._onSimpleInput} />
                                </div>
                                <div class="row">
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._grantEntityUserNative}>Entity -> User</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._grantEntityCompanyNative}>Entity -> Company</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._grantEntityPublicNative}>Entity public</button>
                                </div>
                                <div class="row">
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._grantNamespaceUserNative}>Namespace -> User</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._grantNamespaceCompanyNative}>Namespace -> Company</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._grantNamespacePublicNative}>Namespace public</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._revokeGrantNative}>Revoke</button>
                                </div>
                            </div>
                        </details>

                        <details class="section-collapsible">
                            <summary>Запросы доступа</summary>
                            <div class="section-collapsible-content">
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_accessRequestEntityId" .value=${this._accessRequestEntityId} placeholder="entity_id" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" data-field="_accessRequestId" .value=${this._accessRequestId} placeholder="request_id" @input=${this._onSimpleInput} />
                                </div>
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_accessRequestMessage" .value=${this._accessRequestMessage} placeholder="message" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" type="number" min="1" max="5" data-field="_accessRequestDepth" .value=${String(this._accessRequestDepth)} @input=${this._onSimpleInput} />
                                </div>
                                <div class="row">
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._createAccessRequestNative}>Создать</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._listAccessRequestsNative}>Список</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._approveAccessRequestNative}>Approve</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._rejectAccessRequestNative}>Reject</button>
                                </div>
                            </div>
                        </details>

                        <details class="section-collapsible">
                            <summary>Namespaces</summary>
                            <div class="section-collapsible-content">
                                <div class="section-grid">
                                    <input class="toolbar-input" data-field="_namespaceNameInput" .value=${this._namespaceNameInput} placeholder="namespace name" @input=${this._onSimpleInput} />
                                    <input class="toolbar-input" data-field="_namespaceTemplateIdInput" .value=${this._namespaceTemplateIdInput} placeholder="template_id" @input=${this._onSimpleInput} />
                                </div>
                                <input class="toolbar-input" data-field="_namespaceDescriptionInput" .value=${this._namespaceDescriptionInput} placeholder="description" @input=${this._onSimpleInput} />
                                <div class="row">
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._createNamespaceNative}>Создать namespace</button>
                                    <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._loadNamespaceOverviewNative}>Обзор namespace</button>
                                </div>
                            </div>
                        </details>

                        <details class="section-collapsible">
                            <summary>Вложения</summary>
                            <div class="section-collapsible-content">
                                <input class="toolbar-input" type="text" .value=${this._attachmentEntityId} placeholder="entity_id" @input=${this._onAttachmentEntityIdInput} />
                                <input type="file" @change=${this._onAttachmentFileChange} />
                                <button class="btn btn-secondary" type="button" @click=${this._uploadAttachment}>Загрузить файл</button>
                            </div>
                        </details>

                        <div class="section">
                            <div class="section-title">Результат операции</div>
                            <div class="result-box">${this._backendOperationResult || 'Пока нет выполненных операций'}</div>
                        </div>
                    </div>
                </section>
            </div>
            </div>
        `;
    }
}

customElements.define('graph-page', GraphPage);
