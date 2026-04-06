import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { resolveObjectName } from '@platform/lib/utils/entity-ref.js';
import { CRMStore } from '../store/crm.store.js';
import '../modals/entity-modal.js';
import '../modals/entity-merge-modal.js';
import '../components/graph-canvas.js';
import '../components/graph-timeline.js';
import '../components/graph-toolbar.js';
import '../components/graph-context-menu.js';
import '../components/graph-legend.js';
import '../components/graph-search-pill.js';
import '../components/mini-graph-preview.js';

const VIEW_MODES = ['influence', 'related', 'path'];

const GRAPH_PANELS_STORAGE_KEY = 'crm_graph_panels';
const GRAPH_TIMELINE_SEEDED_KEY = 'crm_graph_timeline_seeded';
const PANEL_IDS = ['search', 'timeline', 'legend', 'meta'];

function _loadPanelVisibility() {
    const raw = localStorage.getItem(GRAPH_PANELS_STORAGE_KEY);
    if (!raw) {
        return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
        return null;
    }
    return parsed;
}

function _savePanelVisibility(panels) {
    localStorage.setItem(GRAPH_PANELS_STORAGE_KEY, JSON.stringify(panels));
}

function _isMobileViewport() {
    return window.innerWidth <= 767;
}

function _getDefaultPanelVisibility() {
    const isMobile = _isMobileViewport();
    return {
        search: !isMobile,
        timeline: !isMobile,
        legend: !isMobile,
        meta: !isMobile,
    };
}

function _resolvePanelVisibility() {
    const stored = _loadPanelVisibility();
    const defaults = _getDefaultPanelVisibility();
    if (!stored) {
        return defaults;
    }
    const resolved = {};
    PANEL_IDS.forEach((panelId) => {
        resolved[panelId] = typeof stored[panelId] === 'boolean' ? stored[panelId] : defaults[panelId];
    });
    return resolved;
}


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
        _timelineStartPercent: { state: true },
        _timelineEndPercent: { state: true },
        _timelineMinTimestamp: { state: true },
        _timelineMaxTimestamp: { state: true },
        _panelVisibility: { state: true },
        _contextMenu: { state: true },
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

            .toolbar-select,
            .toolbar-input,
            .textarea {
                min-width: 160px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-primary);
                font-size: var(--text-sm);
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



            .canvas-layout {
                flex: 1;
                width: 100%;
                height: 100%;
                min-width: 0;
                min-height: 0;
            }

            .canvas-stage {
                position: relative;
                width: 100%;
                height: 100%;
                min-height: 560px;
                background: var(--bg-secondary);
            }

            /* .graph-canvas lives in <graph-canvas> shadow; stretch the host to fill the stage */
            .canvas-stage > graph-canvas {
                position: absolute;
                inset: 0;
                z-index: 0;
                min-width: 0;
                min-height: 0;
            }

            .overlay-card {
                position: absolute;
                z-index: 12;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: 14px;
                backdrop-filter: blur(6px);
                color: var(--text-primary);
                transition: opacity 0.18s ease, transform 0.18s ease;
                pointer-events: none;
            }

            .overlay-card button,
            .overlay-card input,
            .overlay-card select,
            .overlay-card textarea,
            .overlay-card summary,
            .overlay-card .timeline-slider::-webkit-slider-thumb {
                pointer-events: auto;
            }

            .panel-hidden,
            .overlay-card.panel-hidden,
            .overlay-search.panel-hidden {
                display: none !important;
            }


            graph-search-pill {
                position: absolute;
                z-index: 12;
                top: 20px;
                left: 20px;
            }

            graph-timeline {
                top: 60px;
                left: 16px;
            }

            .overlay-meta {
                top: 20px;
                right: 62px;
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 6px 10px;
                font-size: 11px;
            }

            .meta-pill {
                display: inline-flex;
                align-items: center;
                padding: 4px 8px;
                border-radius: 999px;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }

            graph-toolbar {
                position: absolute;
                top: 16px;
                right: 16px;
                z-index: 14;
            }

            graph-legend {
                left: 16px;
                bottom: 16px;
            }

            graph-context-menu {
                position: absolute;
                z-index: 20;
            }

            .empty-search-state {
                position: absolute;
                z-index: 11;
                left: 50%;
                top: 50%;
                transform: translate(-50%, -50%);
                padding: 12px 16px;
                border-radius: 12px;
                border: 1px solid var(--crm-danger-stroke);
                background: var(--crm-danger-bg);
                color: var(--text-primary);
                font-size: 13px;
                backdrop-filter: blur(8px);
            }

            .graph-empty-import-cta {
                position: absolute;
                z-index: 10;
                left: 50%;
                bottom: 72px;
                transform: translateX(-50%);
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 8px;
                padding: 12px 16px;
                border-radius: 12px;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                font-size: 13px;
                max-width: min(360px, 90vw);
                text-align: center;
                backdrop-filter: blur(8px);
            }

            .graph-empty-import-cta button {
                border: 1px solid var(--crm-button-primary-bg);
                background: var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 13px;
                cursor: pointer;
            }

            .advanced-drawer {
                position: absolute;
                right: 16px;
                bottom: 16px;
                z-index: 15;
                width: auto;
                max-width: min(720px, calc(100% - 32px));
                max-height: min(58vh, 540px);
                overflow: auto;
                border: 1px solid var(--glass-border-subtle);
                border-radius: 12px;
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(6px);
                pointer-events: auto;
            }

            .advanced-drawer > summary {
                list-style: none;
                cursor: pointer;
                padding: 10px 12px;
                font-size: 13px;
                font-weight: 600;
                border-bottom: 1px solid var(--glass-border-subtle);
                color: var(--text-primary);
            }

            .advanced-drawer > summary::-webkit-details-marker {
                display: none;
            }

            .advanced-content {
                padding: 12px;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }

            @media (max-width: 1199px) {
                .search-pill input {
                    width: 140px;
                }

                .overlay-meta {
                    top: 20px;
                    right: 72px;
                    flex-wrap: wrap;
                    max-width: 260px;
                }

                .timeline-overlay {
                    top: 60px;
                    left: 16px;
                }

                .timeline-sliders {
                    height: 160px;
                }

                .timeline-slider {
                    width: 160px;
                }

                .legend-overlay {
                    width: min(320px, calc(100% - 140px));
                }

                .advanced-drawer {
                    max-width: min(480px, calc(100% - 32px));
                    max-height: min(40vh, 380px);
                }
            }

            @media (max-width: 767px) {
                :host {
                    border: none;
                    border-radius: 0;
                }

                .canvas-stage {
                    min-height: 400px;
                }

                .overlay-search {
                    top: 8px;
                    left: 8px;
                    flex-wrap: wrap;
                }

                .search-pill input {
                    width: 100px;
                }

                .mode-pills {
                    gap: 3px;
                }

                .mode-pill {
                    font-size: 11px;
                    padding: 4px 8px;
                }

                .overlay-meta {
                    display: none;
                }

                .icon-toolbar {
                    top: 8px;
                    right: 8px;
                    padding: 4px;
                    gap: 4px;
                }

                .icon-btn {
                    width: 28px;
                    height: 28px;
                }

                .timeline-overlay {
                    top: 52px;
                    left: 8px;
                    width: 48px;
                    padding: 4px;
                }

                .timeline-sliders {
                    height: 100px;
                }

                .timeline-slider {
                    width: 100px;
                }

                .legend-overlay {
                    left: 8px;
                    bottom: 8px;
                    width: calc(100% - 60px);
                    padding: 6px 8px;
                }

                .legend-row {
                    gap: 6px;
                }

                .advanced-drawer {
                    right: 8px;
                    bottom: 8px;
                    width: 36px;
                    max-width: 36px;
                    max-height: 36px;
                    overflow: hidden;
                    border-radius: var(--radius-lg);
                    padding: 0;
                }

                .advanced-drawer > summary {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    width: 36px;
                    height: 36px;
                    padding: 0;
                    font-size: 0;
                    color: var(--text-secondary);
                    border-bottom: none;
                }

                .advanced-drawer > summary::after {
                    content: '!';
                    font-size: 16px;
                    font-weight: 700;
                    color: var(--text-secondary);
                }

                .advanced-drawer[open] {
                    width: calc(100% - 16px);
                    max-width: calc(100% - 16px);
                    max-height: min(50vh, 400px);
                    border-radius: 12px;
                    overflow: auto;
                    z-index: 20;
                }

                .advanced-drawer[open] > summary {
                    width: 100%;
                    height: auto;
                    padding: 10px 12px;
                    font-size: 13px;
                    justify-content: flex-start;
                    border-bottom: 1px solid var(--glass-border-subtle);
                }

                .advanced-drawer[open] > summary::after {
                    content: none;
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
        this._relationshipType = 'related_to';
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
        this._overviewSeedEntityIds = [];
        this._showSidePanel = false;
        this._canvasPathState = 'idle';
        this._canvasPathHint = this.i18n.t('graph_page.hint_browse');
        this._labelMode = 'adaptive';
        this._timelineStartPercent = 0;
        this._timelineEndPercent = 100;
        this._timelineMinTimestamp = 0;
        this._timelineMaxTimestamp = 0;
        this._panelVisibility = _resolvePanelVisibility();
        /** @type {string} первая сущность для слияния (Shift+клик) */
        this._mergeAnchorId = '';
        this._contextMenu = null;
        this._timelineReloadTimer = null;
        this._entityTypePaletteNamespace = '';
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
        this._toggleSidePanel = this._toggleSidePanel.bind(this);
        this._startCanvasPathPicking = this._startCanvasPathPicking.bind(this);
        this._resetCanvasPathPicking = this._resetCanvasPathPicking.bind(this);
        this._swapCanvasPathEndpoints = this._swapCanvasPathEndpoints.bind(this);
        this._onCanvasNodeClick = this._onCanvasNodeClick.bind(this);
        this._toggleLabelMode = this._toggleLabelMode.bind(this);
        this._resetTimelineFilter = this._resetTimelineFilter.bind(this);
    }

    async firstUpdated() {
        await this._loadGraphData();
    }

    _goToKnowledgeImport() {
        const c = CRMStore.state.namespaces.current;
        const name = typeof c === 'string' && c.trim()
            ? c.trim()
            : (c && typeof c === 'object' && typeof c.name === 'string' && c.name.trim() ? c.name.trim() : 'default');
        CRMStore.setSettingsNamespaceSelection(name);
        CRMStore.setCurrentView('namespace_imports');
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._timelineReloadTimer) {
            clearTimeout(this._timelineReloadTimer);
            this._timelineReloadTimer = null;
        }
    }

    _getRelationshipTypes() {
        const relationshipTypes = CRMStore.state.entities.relationshipTypes;
        if (!Array.isArray(relationshipTypes)) {
            throw new Error('relationshipTypes must be array');
        }
        return relationshipTypes;
    }

    _getRelationshipTypeColors() {
        const colorsByType = new Map();
        this._getRelationshipTypes().forEach((item) => {
            const typeId = typeof item?.type_id === 'string' ? item.type_id.trim() : '';
            if (!typeId) {
                return;
            }
            const colorValue = typeof item.color === 'string' ? item.color.trim() : '';
            if (colorValue) {
                colorsByType.set(typeId, colorValue);
            }
        });
        return colorsByType;
    }

    _getNamespaceName() {
        return resolveObjectName(CRMStore.state.namespaces.current, null);
    }

    _getEntityMap() {
        return new Map(this._entities.map((entity) => [entity.entity_id, entity]));
    }

    _parseTimestamp(rawValue) {
        if (!rawValue) {
            return null;
        }
        const timestamp = Date.parse(rawValue);
        if (!Number.isFinite(timestamp)) {
            return null;
        }
        return timestamp;
    }

    _applyTimelineBounds(bounds) {
        if (!bounds || typeof bounds !== 'object') {
            throw new Error('Timeline bounds response must be object');
        }
        const minTimestamp = this._parseTimestamp(bounds.min_created_at);
        const maxTimestamp = this._parseTimestamp(bounds.max_created_at);
        const totalEntities = Number(bounds.total_entities);
        if (!Number.isFinite(totalEntities) || totalEntities < 0) {
            throw new Error('total_entities must be non-negative number');
        }
        if (totalEntities === 0 || minTimestamp === null || maxTimestamp === null) {
            this._timelineMinTimestamp = 0;
            this._timelineMaxTimestamp = 0;
            this._timelineStartPercent = 0;
            this._timelineEndPercent = 100;
            return;
        }
        this._timelineMinTimestamp = minTimestamp;
        this._timelineMaxTimestamp = maxTimestamp;
        this._timelineStartPercent = Math.max(0, Math.min(100, this._timelineStartPercent));
        this._timelineEndPercent = Math.max(this._timelineStartPercent, Math.min(100, this._timelineEndPercent));
    }

    _applyDefaultTimelineTodayIfNeeded() {
        if (typeof sessionStorage === 'undefined') {
            return;
        }
        if (sessionStorage.getItem(GRAPH_TIMELINE_SEEDED_KEY)) {
            return;
        }
        if (!this._timelineMinTimestamp || !this._timelineMaxTimestamp) {
            sessionStorage.setItem(GRAPH_TIMELINE_SEEDED_KEY, '1');
            return;
        }
        const span = Math.max(1, this._timelineMaxTimestamp - this._timelineMinTimestamp);
        const now = new Date();
        const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0);
        const endOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);
        let startPercent = ((startOfDay.getTime() - this._timelineMinTimestamp) / span) * 100;
        let endPercent = ((endOfDay.getTime() - this._timelineMinTimestamp) / span) * 100;
        startPercent = Math.max(0, Math.min(100, startPercent));
        endPercent = Math.max(0, Math.min(100, endPercent));
        if (endPercent < startPercent) {
            const tmp = startPercent;
            startPercent = endPercent;
            endPercent = tmp;
        }
        if (endPercent - startPercent < 0.5) {
            endPercent = Math.min(100, startPercent + 0.5);
        }
        this._timelineStartPercent = startPercent;
        this._timelineEndPercent = endPercent;
        sessionStorage.setItem(GRAPH_TIMELINE_SEEDED_KEY, '1');
    }

    _isNodeInTimelineWindow(node) {
        if (!this._timelineMinTimestamp || !this._timelineMaxTimestamp) {
            return true;
        }
        if (this._timelineStartPercent <= 0 && this._timelineEndPercent >= 100) {
            return true;
        }
        const nodeRawTimestamp = node.created_at || node.createdAt || null;
        const nodeTimestamp = this._parseTimestamp(nodeRawTimestamp);
        if (nodeTimestamp === null) {
            return false;
        }
        const timelineSpan = Math.max(1, this._timelineMaxTimestamp - this._timelineMinTimestamp);
        const fromTimestamp = this._timelineMinTimestamp + (timelineSpan * (this._timelineStartPercent / 100));
        const toTimestamp = this._timelineMinTimestamp + (timelineSpan * (this._timelineEndPercent / 100));
        return nodeTimestamp >= fromTimestamp && nodeTimestamp <= toTimestamp;
    }

    _formatTimelineLabel(timestamp) {
        if (!timestamp) {
            return '—';
        }
        const dateValue = new Date(timestamp);
        return dateValue.toLocaleDateString('ru-RU');
    }

    async _ensureEntityTypePaletteLoaded(namespaceName) {
        const cachedTypes = CRMStore.state.entities.entityTypes;
        const hasCachedTypes = Array.isArray(cachedTypes) && cachedTypes.length > 0;
        if (hasCachedTypes && this._entityTypePaletteNamespace === (namespaceName || '')) {
            return;
        }
        if (typeof CRMStore.loadEntityTypes !== 'function') {
            return;
        }
        await CRMStore.loadEntityTypes(this.crmApi, namespaceName || null);
        this._entityTypePaletteNamespace = namespaceName || '';
    }

    _getTimelineQueryParams() {
        if (!this._timelineMinTimestamp || !this._timelineMaxTimestamp) {
            return {};
        }
        if (this._timelineStartPercent <= 0 && this._timelineEndPercent >= 100) {
            return {};
        }
        const timelineSpan = Math.max(1, this._timelineMaxTimestamp - this._timelineMinTimestamp);
        const fromTimestamp = this._timelineMinTimestamp + (timelineSpan * (this._timelineStartPercent / 100));
        const toTimestamp = this._timelineMinTimestamp + (timelineSpan * (this._timelineEndPercent / 100));
        return {
            created_at_from: new Date(fromTimestamp).toISOString(),
            created_at_to: new Date(toTimestamp).toISOString(),
        };
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

    _getNamespaceEntityTypeColors() {
        const entityTypes = CRMStore.state.entities.entityTypes;
        if (!Array.isArray(entityTypes)) {
            throw new Error('entityTypes must be array');
        }
        const colorsByType = new Map();
        entityTypes.forEach((item) => {
            const typeId = typeof item?.type_id === 'string' ? item.type_id.trim() : '';
            if (!typeId) {
                return;
            }
            const colorValue = typeof item.color === 'string' ? item.color.trim() : '';
            if (colorValue) {
                colorsByType.set(typeId, colorValue);
            }
        });
        return colorsByType;
    }

    _graphIncidentWeightSubtitle(sum) {
        if (typeof sum !== 'number' || !Number.isFinite(sum) || sum <= 0) {
            return '';
        }
        const value = sum.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 });
        return this.i18n.t('graph_page.incident_weight_subtitle', { value });
    }

    _nodeColor(node) {
        if (node.access === false) {
            return '#7f7f8f';
        }
        const entityType = typeof node.entity_type === 'string' ? node.entity_type.trim() : '';
        if (!entityType) {
            return '#bca8ff';
        }
        const colorsByType = this._getNamespaceEntityTypeColors();
        return colorsByType.get(entityType) || '#bca8ff';
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

    _getVisibleGraphSnapshot() {
        const query = this._entitySearchQuery.trim().toLowerCase();
        if (!query) {
            return {
                nodes: this._graphNodes,
                edges: this._graphEdges,
                isFiltered: this._timelineStartPercent > 0 || this._timelineEndPercent < 100,
                isEmpty: this._graphNodes.length === 0,
            };
        }
        const matchedNodeIds = new Set();
        this._graphNodes.forEach((node) => {
            const nodeId = node.entity_id || node.id || '';
            const nodeName = node.name || node.label || '';
            const nodeType = node.entity_type || '';
            const haystack = `${String(nodeName)} ${String(nodeId)} ${String(nodeType)}`.toLowerCase();
            if (haystack.includes(query)) {
                matchedNodeIds.add(nodeId);
            }
        });
        if (matchedNodeIds.size === 0) {
            return {
                nodes: [],
                edges: [],
                isFiltered: true,
                isEmpty: true,
            };
        }
        const nodes = this._graphNodes.filter((node) => matchedNodeIds.has(node.entity_id || node.id));
        const edges = this._graphEdges.filter((edge) => {
            const sourceId = edge.source_id || edge.source_entity_id || edge.source;
            const targetId = edge.target_id || edge.target_entity_id || edge.target;
            return matchedNodeIds.has(sourceId) && matchedNodeIds.has(targetId);
        });
        return {
            nodes,
            edges,
            isFiltered: true,
            isEmpty: false,
        };
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

    _clearCanvasSearchFilter() {
        this._entitySearchQuery = '';
    }

    _showContextMenu(screenX, screenY, nodeId, edgeId) {
        const container = this.renderRoot?.querySelector('.canvas-stage');
        if (!container) {
            return;
        }
        const rect = container.getBoundingClientRect();
        const posX = Math.min(screenX - rect.left, rect.width - 180);
        const posY = Math.min(screenY - rect.top, rect.height - 120);
        this._contextMenu = { x: posX, y: posY, nodeId, edgeId };
    }

    _hideContextMenu() {
        this._contextMenu = null;
    }

    _onCanvasStageClick(event) {
        const advancedDrawer = this.renderRoot?.querySelector('.advanced-drawer');
        if (advancedDrawer && advancedDrawer.open && !event.composedPath().includes(advancedDrawer)) {
            advancedDrawer.open = false;
        }
    }

    _openMergeModal(entityIdA, entityIdB) {
        const a = typeof entityIdA === 'string' ? entityIdA.trim() : '';
        const b = typeof entityIdB === 'string' ? entityIdB.trim() : '';
        if (!a || !b || a === b) {
            throw new Error('Merge requires two distinct entity IDs');
        }
        const modal = document.createElement('entity-merge-modal');
        modal.entityIdA = a;
        modal.entityIdB = b;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('merged', () => {
            this._loadGraphData().catch((error) => {
                const message = error instanceof Error ? error.message : String(error);
                this.error(this.i18n.t('graph_page.err_timeline', { message }));
            });
        });
    }

    _openEntityModal(entityId) {
        this._hideContextMenu();
        const entity = this._resolveEntityById(entityId);
        const modal = document.createElement('entity-modal');
        if (entity) {
            modal.entityId = entityId;
            modal.entity = entity;
        } else {
            modal.entityId = entityId;
        }
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('saved', async () => {
            await this._loadGraphData();
        });
    }

    _setPathSourceFromContext(nodeId) {
        this._hideContextMenu();
        this._pathSourceId = nodeId;
        this._canvasPathState = 'pick_target';
        this._canvasPathHint = this.i18n.t('graph_page.hint_click_target');
        this._viewMode = 'path';
    }

    _focusNodeFromContext(nodeId) {
        this._hideContextMenu();
        this._selectedNodeId = nodeId;
        this._focusSelectedNode();
    }

    _togglePanel(panelId) {
        const nextVisibility = { ...this._panelVisibility };
        nextVisibility[panelId] = !nextVisibility[panelId];
        this._panelVisibility = nextVisibility;
        _savePanelVisibility(nextVisibility);
    }

    _resetTimelineFilter() {
        this._timelineStartPercent = 0;
        this._timelineEndPercent = 100;
        this._scheduleTimelineReload();
    }

    _scheduleTimelineReload() {
        if (this._timelineReloadTimer) {
            clearTimeout(this._timelineReloadTimer);
        }
        this._timelineReloadTimer = setTimeout(() => {
            this._timelineReloadTimer = null;
            this._loadGraphData().catch((error) => {
                const message = error instanceof Error ? error.message : String(error);
                this.error(this.i18n.t('graph_page.err_timeline', { message }));
            });
        }, 220);
    }

    async _changeDepthDelta(delta) {
        const nextDepth = Math.max(1, Math.min(5, this._maxDepth + delta));
        if (nextDepth === this._maxDepth) {
            return;
        }
        this._maxDepth = nextDepth;
        await this._rebuildGraphByMode();
    }

    async _toggleRelationshipTypeQuickFilter() {
        const relationshipTypes = this._getRelationshipTypes();
        if (this._relationshipTypeFilter.trim().length > 0) {
            this._relationshipTypeFilter = '';
            await this._rebuildGraphByMode();
            return;
        }
        if (relationshipTypes.length === 0) {
            throw new Error('Relationship types are required for quick filter');
        }
        const selectedEdge = this._graphEdges.find((edge) => this._getEdgeId(edge) === this._selectedEdgeId);
        if (selectedEdge && selectedEdge.relationship_type) {
            this._relationshipTypeFilter = selectedEdge.relationship_type;
            await this._rebuildGraphByMode();
            return;
        }
        this._relationshipTypeFilter = relationshipTypes[0].type_id;
        await this._rebuildGraphByMode();
    }

    async _resetCanvasView() {
        this._entitySearchQuery = '';
        this._resetTimelineFilter();
        this._relationshipTypeFilter = '';
        this._viewMode = 'influence';
        this._defaultOverviewActive = true;
        this._canvasPathState = 'idle';
        this._canvasPathHint = this.i18n.t('graph_page.hint_browse');
        this._shortestPathEdges = [];
        await this._rebuildGraphByMode();
    }

    async _onToolbarAction(actionId) {
        if (actionId === 'fit') {
            const canvas = this.renderRoot?.querySelector('graph-canvas');
            if (canvas) { canvas.fitToViewport(); }
            return;
        }
        if (actionId === 'path_mode') {
            this._startCanvasPathPicking();
            return;
        }
        if (actionId === 'swap_path') {
            await this._swapCanvasPathEndpoints();
            return;
        }
        if (actionId === 'reset_path') {
            await this._resetCanvasPathPicking();
            return;
        }
        if (actionId === 'depth_plus') {
            await this._changeDepthDelta(1);
            return;
        }
        if (actionId === 'depth_minus') {
            await this._changeDepthDelta(-1);
            return;
        }
        if (actionId === 'filter_rel_type') {
            await this._toggleRelationshipTypeQuickFilter();
            return;
        }
        if (actionId === 'labels_mode') {
            this._toggleLabelMode();
            return;
        }
        if (actionId === 'reset_view') {
            await this._resetCanvasView();
            return;
        }
        if (actionId === 'merge_entities') {
            if (!this._mergeAnchorId || !this._selectedNodeId) {
                this.warning(this.i18n.t('graph_page.merge_need_pair'));
                return;
            }
            if (this._mergeAnchorId === this._selectedNodeId) {
                this.warning(this.i18n.t('graph_page.merge_same_node'));
                return;
            }
            this._openMergeModal(this._mergeAnchorId, this._selectedNodeId);
            this._mergeAnchorId = '';
            return;
        }
        throw new Error(`Unsupported toolbar action: ${actionId}`);
    }

    _toggleLabelMode() {
        this._labelMode = this._labelMode === 'adaptive' ? 'minimal' : 'adaptive';
    }

    _startCanvasPathPicking() {
        this._canvasPathState = 'pick_source';
        this._canvasPathHint = this.i18n.t('graph_page.hint_click_source');
        this._viewMode = 'path';
        this._entitySearchQuery = '';
        this._shortestPathEdges = [];
        this._pathSourceId = '';
        this._pathTargetId = '';
        this._showSidePanel = false;
    }

    async _resetCanvasPathPicking() {
        this._canvasPathState = 'idle';
        this._canvasPathHint = this.i18n.t('graph_page.hint_browse');
        this._pathSourceId = '';
        this._pathTargetId = '';
        this._shortestPathEdges = [];
        await this._rebuildGraphByMode();
    }

    async _swapCanvasPathEndpoints() {
        if (!this._pathSourceId || !this._pathTargetId) {
            throw new Error('Select source and target');
        }
        const sourceId = this._pathSourceId;
        this._pathSourceId = this._pathTargetId;
        this._pathTargetId = sourceId;
        await this._buildPathGraph();
    }


    _mergePathEdgesByKind(directedEdges, undirectedEdges) {
        const merged = new Map();
        directedEdges.forEach((edge) => {
            const edgeId = this._getEdgeId(edge);
            merged.set(edgeId, { ...edge, path_kind: 'directed' });
        });
        undirectedEdges.forEach((edge) => {
            const edgeId = this._getEdgeId(edge);
            const existing = merged.get(edgeId);
            if (!existing) {
                merged.set(edgeId, { ...edge, path_kind: 'undirected' });
                return;
            }
            merged.set(edgeId, { ...existing, path_kind: 'both' });
        });
        return Array.from(merged.values());
    }


    _onCanvasNodeClick(node, event) {
        this._selectedNodeId = node.id;
        this._attachmentEntityId = node.id;
        if (event?.altKey) {
            this._onOpenEntity(node.id);
            return;
        }
        if (event?.shiftKey) {
            const id = node.id;
            if (!this._mergeAnchorId) {
                this._mergeAnchorId = id;
                this.info(this.i18n.t('graph_page.merge_anchor_set'));
                return;
            }
            if (this._mergeAnchorId === id) {
                this._mergeAnchorId = '';
                return;
            }
            this._openMergeModal(this._mergeAnchorId, id);
            this._mergeAnchorId = '';
            return;
        }
        if (this._canvasPathState === 'pick_source') {
            this._pathSourceId = node.id;
            this._pathTargetId = '';
            this._canvasPathState = 'pick_target';
            this._canvasPathHint = this.i18n.t('graph_page.hint_click_target');
            return;
        }
        if (this._canvasPathState === 'pick_target') {
            if (node.id === this._pathSourceId) {
                this._canvasPathHint = this.i18n.t('graph_page.hint_pick_other_target');
                this.warning(this.i18n.t('graph_page.warn_source_target_same'));
                return;
            }
            this._pathTargetId = node.id;
            this._canvasPathState = 'built';
            this._canvasPathHint = this.i18n.t('graph_page.hint_route_built');
            this._buildPathGraph().catch((error) => {
                const message = error instanceof Error ? error.message : String(error);
                this.error(this.i18n.t('graph_page.err_path_build', { message }));
            });
            return;
        }
        this._canvasPathHint = this.i18n.t('graph_page.hint_browse');
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
            this.success(this.i18n.t('graph_page.success_action', { action: actionLabel }));
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this._backendOperationResult = `Error: ${message}`;
            this.error(this.i18n.t('graph_page.err_operation_named', { action: actionLabel, message }));
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
        const canvas = this.renderRoot?.querySelector('graph-canvas');
        if (!canvas) {
            throw new Error('graph-canvas element is not available');
        }
        canvas.flyToNode({ id: this._selectedNodeId });
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
            await this._ensureEntityTypePaletteLoaded(namespaceName);
            const timelineBounds = await crmApi.getEntityTimelineBounds({ namespace: namespaceName });
            this._applyTimelineBounds(timelineBounds);
            this._applyDefaultTimelineTodayIfNeeded();
            const timelineParams = this._getTimelineQueryParams();
            const entities = await crmApi.getEntities({ namespace: namespaceName, limit: 120, ...timelineParams });
            const noteEntities = await crmApi.getEntities({
                namespace: namespaceName,
                entity_type: 'note',
                limit: 20,
                ...timelineParams,
            });
            this._entities = Array.isArray(entities) ? entities : [];
            this._overviewSeedEntityIds = Array.isArray(noteEntities)
                ? noteEntities.map((item) => item.entity_id)
                : [];
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
        const seedIds = this._overviewSeedEntityIds;
        if (seedIds.length === 0) {
            this._graphNodes = [];
            this._graphEdges = [];
            this._shortestPathEdges = [];
            return;
        }
        const relationshipType = this._getRelationshipFilter();
        const timelineParams = this._getTimelineQueryParams();
        const namespaceName = this._getNamespaceName();
        const response = await this.crmApi.getOverviewGraph(seedIds, {
            max_depth: this._maxDepth,
            relationship_types: relationshipType,
            namespace: namespaceName || null,
            ...timelineParams,
        });
        if (!response || typeof response !== 'object') {
            throw new Error('Overview graph response must be object');
        }
        if (!Array.isArray(response.nodes) || !Array.isArray(response.edges)) {
            throw new Error('Overview graph response must contain nodes and edges arrays');
        }
        this._shortestPathEdges = [];
        this._graphNodes = response.nodes;
        this._graphEdges = response.edges;
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
        const namespaceName = this._getNamespaceName();
        const params = {
            max_depth: this._maxDepth,
            namespace: namespaceName || null,
            ...this._getTimelineQueryParams(),
        };
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
        const params = { direction: this._relatedDirection, ...this._getTimelineQueryParams() };
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
            created_at: rootEntity.created_at || null,
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
                ...this._getTimelineQueryParams(),
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
        if (!Array.isArray(response.undirected_path)) {
            throw new Error('Shortest path must include undirected_path array');
        }
        if (!Array.isArray(response.undirected_edges)) {
            throw new Error('Shortest path must include undirected_edges array');
        }
        const directedExists = response.exists === true && response.path.length > 0;
        const undirectedExists = response.undirected_exists === true && response.undirected_path.length > 0;
        if (!directedExists && !undirectedExists) {
            this._shortestPathEdges = [];
            this._canvasPathHint = this.i18n.t('graph_page.hint_route_not_found');
            this.warning(this.i18n.t('graph_page.warn_path_not_found', { source: this._pathSourceId, target: this._pathTargetId }));
            return;
        }
        const mergedPathEdges = this._mergePathEdgesByKind(response.edges, response.undirected_edges);
        this._shortestPathEdges = mergedPathEdges;
        const entityMap = this._getEntityMap();
        const mergedPathNodeIds = Array.from(new Set([...response.path, ...response.undirected_path]));
        const nodes = mergedPathNodeIds.map((entityId, index) => {
            const entity = entityMap.get(entityId);
            if (!entity) {
                return {
                    entity_id: entityId,
                    entity_type: 'hidden',
                    name: 'Hidden',
                    level: index,
                    access: false,
                    created_at: null,
                    attributes: null,
                };
            }
            return {
                entity_id: entity.entity_id,
                entity_type: entity.entity_type,
                name: entity.name,
                level: index,
                access: true,
                created_at: entity.created_at || null,
                attributes: entity.attributes || {},
            };
        });
        this._graphNodes = nodes;
        this._graphEdges = mergedPathEdges;
        this._canvasPathState = 'built';
        this._canvasPathHint = this.i18n.t('graph_page.hint_routes_dual');
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
            this._canvasPathHint = this.i18n.t('graph_page.hint_browse');
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
            this._clearCanvasSearchFilter();
            return;
        }
        const snapshot = this._getVisibleGraphSnapshot();
        if (snapshot.isEmpty) {
            this.warning(this.i18n.t('graph_page.warn_filter_empty'));
            return;
        }
        this.success(this.i18n.t('graph_page.success_filtered', { count: String(snapshot.nodes.length) }));
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
            { id: 'createRelationship', label: 'Relationships: create', method: 'createRelationship', args: '[{"source_entity_id":"source","target_entity_id":"target","relationship_type":"related_to","weight":1.0}]' },
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
            this.success(this.i18n.t('graph_page.success_operation', { label: operation.label }));
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this._backendOperationResult = `Error: ${message}`;
            this.error(this.i18n.t('graph_page.err_operation', { message }));
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

    render() {
        const operations = this._getBackendOperations();
        const coverageMatrix = this._getCoverageMatrix();
        const coveredNativeCount = coverageMatrix.filter((item) => item.status === 'covered_by_native_ui').length;
        const coveredJsonCount = coverageMatrix.filter((item) => item.status === 'covered_by_json_runner_only').length;
        const uncoveredCount = coverageMatrix.filter((item) => item.status === 'not_covered').length;
        const visibleGraph = this._getVisibleGraphSnapshot();
        const entityTypeColors = this._getNamespaceEntityTypeColors();
        const relTypeColors = this._getRelationshipTypeColors();
        const toolbarActions = [
            { id: 'fit', label: this.i18n.t('graph_page.toolbar_fit') },
            { id: 'path_mode', label: this.i18n.t('graph_page.toolbar_path_mode') },
            { id: 'swap_path', label: this.i18n.t('graph_page.toolbar_swap') },
            { id: 'reset_path', label: this.i18n.t('graph_page.toolbar_reset_path') },
            { id: 'depth_plus', label: this.i18n.t('graph_page.toolbar_depth_plus') },
            { id: 'depth_minus', label: this.i18n.t('graph_page.toolbar_depth_minus') },
            { id: 'filter_rel_type', label: this.i18n.t('graph_page.toolbar_filter_rel_type') },
            { id: 'labels_mode', label: this.i18n.t('graph_page.toolbar_labels_mode') },
            { id: 'reset_view', label: this.i18n.t('graph_page.toolbar_reset_view') },
            { id: 'merge_entities', label: this.i18n.t('graph_page.toolbar_merge') },
        ];
        const toolbarToggles = [
            { id: 'search', label: this.i18n.t('graph_page.panel_toggle_search'), active: this._panelVisibility.search },
            { id: 'timeline', label: this.i18n.t('graph_page.panel_toggle_timeline'), active: this._panelVisibility.timeline },
            { id: 'legend', label: this.i18n.t('graph_page.panel_toggle_legend'), active: this._panelVisibility.legend },
            { id: 'meta', label: this.i18n.t('graph_page.panel_toggle_meta'), active: this._panelVisibility.meta },
        ];
        return html`
            <div class="canvas-layout">
                <section class="canvas-stage" @click=${this._onCanvasStageClick}>
                    <graph-canvas
                        .graphNodes=${visibleGraph.nodes}
                        .graphEdges=${visibleGraph.edges}
                        .shortestPathEdges=${this._shortestPathEdges}
                        .graphPreset=${this._graphPreset}
                        .labelMode=${this._labelMode}
                        .selectedNodeId=${this._selectedNodeId}
                        .selectedEdgeId=${this._selectedEdgeId}
                        .pathSourceId=${this._pathSourceId}
                        .pathTargetId=${this._pathTargetId}
                        .nodeColorFn=${(node) => this._nodeColor(node)}
                        .edgeDirectedFn=${(edge) => this._isEdgeDirected(edge)}
                        .relationshipTypeColors=${relTypeColors}
                        .incidentWeightSubtitleFn=${(sum) => this._graphIncidentWeightSubtitle(sum)}
                        @node-click=${(e) => this._onCanvasNodeClick(e.detail.node, e.detail.event)}
                        @node-dblclick=${(e) => { const canvas = this.renderRoot?.querySelector('graph-canvas'); if (canvas) { canvas.flyToNode(e.detail.node); } }}
                        @node-contextmenu=${(e) => this._showContextMenu(e.detail.screenX, e.detail.screenY, e.detail.node?.id, null)}
                        @canvas-click=${() => this._hideContextMenu()}
                        @link-click=${(e) => { this._selectedEdgeId = e.detail.link?.id || ''; }}
                    ></graph-canvas>

                    <graph-search-pill
                        class="${this._panelVisibility.search ? '' : 'panel-hidden'}"
                        .query=${this._entitySearchQuery}
                        .viewMode=${this._viewMode}
                        .modes=${VIEW_MODES}
                        @search-input=${(e) => { this._entitySearchQuery = e.detail.query; }}
                        @search-clear=${this._clearCanvasSearchFilter}
                        @mode-change=${(e) => { this._viewMode = e.detail.mode; if (e.detail.mode !== 'influence') { this._defaultOverviewActive = false; } if (e.detail.mode !== 'path') { this._canvasPathState = 'idle'; this._canvasPathHint = this.i18n.t('graph_page.hint_browse'); } this._rebuildGraphByMode(); }}
                        @refresh=${this._loadGraphData}
                    ></graph-search-pill>

                    <graph-timeline
                        class="overlay-card ${this._panelVisibility.timeline ? '' : 'panel-hidden'}"
                        .minTimestamp=${this._timelineMinTimestamp}
                        .maxTimestamp=${this._timelineMaxTimestamp}
                        .startPercent=${this._timelineStartPercent}
                        .endPercent=${this._timelineEndPercent}
                        @timeline-change=${(e) => { this._timelineStartPercent = e.detail.startPercent; this._timelineEndPercent = e.detail.endPercent; this._scheduleTimelineReload(); }}
                    ></graph-timeline>

                    <div class="overlay-card overlay-meta ${this._panelVisibility.meta ? '' : 'panel-hidden'}">
                        <span class="meta-pill">${this.i18n.t('graph_page.meta_mode')} ${this._viewMode}</span>
                        <span class="meta-pill">${this.i18n.t('graph_page.meta_depth')} ${this._maxDepth}</span>
                        <span class="meta-pill">${this.i18n.t('graph_page.meta_nodes')} ${visibleGraph.nodes.length}</span>
                        <span class="meta-pill">${this.i18n.t('graph_page.meta_edges')} ${visibleGraph.edges.length}</span>
                    </div>

                    <graph-toolbar
                        .actions=${toolbarActions}
                        .toggles=${toolbarToggles}
                        .labelMode=${this._labelMode}
                        @toolbar-action=${(e) => this._onToolbarAction(e.detail.actionId)}
                        @panel-toggle=${(e) => this._togglePanel(e.detail.panelId)}
                    ></graph-toolbar>

                    <graph-legend
                        class="overlay-card ${this._panelVisibility.legend ? '' : 'panel-hidden'}"
                        .nodes=${visibleGraph.nodes}
                        .entityTypeColors=${entityTypeColors}
                        .canvasHint=${this._canvasPathHint}
                        .selectedNodeId=${this._selectedNodeId}
                        .selectedEdgeId=${this._selectedEdgeId}
                    ></graph-legend>

                    ${visibleGraph.isFiltered && visibleGraph.isEmpty ? html`
                        <div class="empty-search-state">${this.i18n.t('graph_page.empty_search')}</div>
                    ` : ''}

                    ${!visibleGraph.isFiltered && visibleGraph.isEmpty ? html`
                        <div class="graph-empty-import-cta">
                            <span>${this.i18n.t('graph_page.empty_import_hint')}</span>
                            <button type="button" @click=${this._goToKnowledgeImport}>
                                ${this.i18n.t('graph_page.empty_import_cta')}
                            </button>
                        </div>
                    ` : ''}

                    <graph-context-menu
                        .x=${this._contextMenu?.x || 0}
                        .y=${this._contextMenu?.y || 0}
                        .nodeId=${this._contextMenu?.nodeId || ''}
                        .edgeId=${this._contextMenu?.edgeId || ''}
                        .visible=${this._contextMenu !== null}
                        @ctx-action=${(e) => {
                            const { action, nodeId } = e.detail;
                            if (action === 'open-entity') { this._openEntityModal(nodeId); }
                            if (action === 'focus') { this._focusNodeFromContext(nodeId); }
                            if (action === 'path-from') { this._setPathSourceFromContext(nodeId); }
                            if (action === 'graph-from') { this._hideContextMenu(); this._defaultOverviewActive = false; this._selectedRootId = nodeId; this._rebuildGraphByMode(); }
                        }}
                    ></graph-context-menu>

                    <details class="advanced-drawer">
                        <summary>${this.i18n.t('graph_page.advanced_summary')}</summary>
                        <div class="advanced-content">
                            <details class="section-collapsible">
                                <summary>Backend runner</summary>
                                <div class="section-collapsible-content">
                                    <select class="toolbar-select" .value=${this._backendOperationId} @change=${this._onBackendOperationChange}>
                                        ${operations.map((item) => html`<option value=${item.id}>${item.label}</option>`)}
                                    </select>
                                    <textarea class="textarea" .value=${this._backendOperationArgs} @input=${this._onBackendArgsInput}></textarea>
                                    <div class="row">
                                        <button class="btn btn-secondary" type="button" @click=${this._injectSelectedNodeToArgs}>${this.i18n.t('graph_page.inject_selected')}</button>
                                        <button class="btn btn-primary" type="button" ?disabled=${this._backendLoading} @click=${this._runBackendOperation}>
                                            ${this._backendLoading ? this.i18n.t('graph_page.executing') : this.i18n.t('graph_page.execute')}
                                        </button>
                                    </div>
                                </div>
                            </details>

                            <details class="section-collapsible">
                                <summary>${this.i18n.t('graph_page.api_matrix')}</summary>
                                <div class="section-collapsible-content">
                                    <div class="small">native: ${coveredNativeCount}, json-only: ${coveredJsonCount}, not-covered: ${uncoveredCount}</div>
                                    <div class="result-box">${coverageMatrix.map((item) => `${item.method} -> ${item.status}`).join('\n')}</div>
                                </div>
                            </details>

                            <details class="section-collapsible">
                                <summary>${this.i18n.t('graph_page.quick_native')}</summary>
                                <div class="section-collapsible-content">
                                    <div class="row">
                                        <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._focusSelectedNode}>${this.i18n.t('graph_page.focus_selected')}</button>
                                        <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._expandFromSelected}>${this.i18n.t('graph_page.expand_neighbors')}</button>
                                        <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._isolateSelectedNeighborhood}>${this.i18n.t('graph_page.isolate_neighborhood')}</button>
                                        <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._revealNextLevel}>${this.i18n.t('graph_page.next_level')}</button>
                                    </div>
                                    <div class="section-grid">
                                        <input class="toolbar-input" type="text" .value=${this._attachmentEntityId} placeholder=${this.i18n.t('graph_page.attach_placeholder')} @input=${this._onAttachmentEntityIdInput} />
                                        <input type="file" @change=${this._onAttachmentFileChange} />
                                    </div>
                                    <button class="btn btn-secondary" type="button" @click=${this._uploadAttachment}>${this.i18n.t('graph_page.upload_attachment')}</button>
                                </div>
                            </details>

                            <div class="section">
                                <div class="section-title">${this.i18n.t('graph_page.op_result_title')}</div>
                                <div class="result-box">${this._backendOperationResult || this.i18n.t('graph_page.op_result_empty')}</div>
                            </div>
                        </div>
                    </details>
                </section>
            </div>
        `;
    }
}

customElements.define('graph-page', GraphPage);
