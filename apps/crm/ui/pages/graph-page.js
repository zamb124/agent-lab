import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { resolveObjectName } from '@platform/lib/utils/entity-ref.js';
import { CRMStore } from '../store/crm.store.js';

const VIEW_MODES = ['influence', 'related', 'path'];

const GRAPH_PANELS_STORAGE_KEY = 'crm_graph_panels';
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
        _timelineStartPercent: { state: true },
        _timelineEndPercent: { state: true },
        _timelineMinTimestamp: { state: true },
        _timelineMaxTimestamp: { state: true },
        _panelVisibility: { state: true },
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

            .canvas-layout {
                width: 100%;
                height: 100%;
                min-height: 0;
            }

            .canvas-stage {
                position: relative;
                width: 100%;
                height: 100%;
                min-height: 560px;
                background: radial-gradient(circle at top, rgba(130, 130, 180, 0.18), rgba(20, 20, 35, 0.75));
            }

            .canvas-stage .graph-canvas {
                position: absolute;
                inset: 0;
            }

            .overlay-card {
                position: absolute;
                z-index: 12;
                background: rgba(16, 20, 31, 0.58);
                border: 1px solid rgba(156, 166, 191, 0.22);
                border-radius: 14px;
                backdrop-filter: blur(6px);
                color: #eef2ff;
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

            .toolbar-separator {
                width: 20px;
                height: 2px;
                background: rgba(127, 214, 255, 0.4);
                border-radius: 1px;
                margin: 4px auto;
            }

            .icon-btn.toggle-btn {
                border-style: dashed;
                border-color: rgba(156, 166, 191, 0.3);
            }

            .icon-btn.toggle-btn.active {
                border-style: solid;
                border-color: rgba(127, 214, 255, 0.6);
            }

            .overlay-search {
                position: absolute;
                z-index: 12;
                top: 20px;
                left: 20px;
                display: flex;
                align-items: center;
                gap: 8px;
                pointer-events: none;
            }

            .search-pill {
                display: flex;
                align-items: center;
                gap: 0;
                background: rgba(16, 20, 31, 0.62);
                border: 1px solid rgba(156, 166, 191, 0.28);
                border-radius: 999px;
                overflow: hidden;
                pointer-events: auto;
                backdrop-filter: blur(6px);
            }

            .search-pill input {
                border: none;
                background: transparent;
                color: #eef2ff;
                font-size: 13px;
                padding: 8px 14px;
                width: 180px;
                outline: none;
            }

            .search-pill input::placeholder {
                color: rgba(200, 210, 240, 0.5);
            }

            .search-pill .pill-icon-btn {
                width: 32px;
                height: 32px;
                border: none;
                background: transparent;
                color: rgba(200, 210, 240, 0.7);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }

            .search-pill .pill-icon-btn:hover {
                color: #eef2ff;
            }

            .search-pill .pill-icon-btn svg {
                width: 14px;
                height: 14px;
                fill: none;
                stroke: currentColor;
                stroke-width: 2;
                stroke-linecap: round;
                stroke-linejoin: round;
            }

            .mode-pills {
                display: flex;
                align-items: center;
                gap: 4px;
                pointer-events: auto;
            }

            .mode-pill {
                display: inline-flex;
                align-items: center;
                padding: 5px 10px;
                border-radius: 999px;
                border: 1px solid rgba(156, 166, 191, 0.28);
                background: rgba(16, 20, 31, 0.52);
                backdrop-filter: blur(6px);
                color: rgba(200, 210, 240, 0.75);
                font-size: 12px;
                cursor: pointer;
                transition: background 0.14s, color 0.14s;
            }

            .mode-pill:hover {
                background: rgba(40, 52, 80, 0.8);
                color: #eef2ff;
            }

            .mode-pill.active {
                background: rgba(46, 86, 125, 0.85);
                border-color: rgba(127, 214, 255, 0.55);
                color: #eef2ff;
            }

            .timeline-overlay {
                top: 160px;
                left: 16px;
                width: 94px;
                padding: 10px 8px;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 8px;
            }

            .timeline-title {
                font-size: 11px;
                color: #d5dff9;
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }

            .timeline-sliders {
                position: relative;
                width: 28px;
                height: 220px;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .timeline-track {
                position: absolute;
                width: 3px;
                height: 100%;
                border-radius: 2px;
                background: rgba(156, 166, 191, 0.35);
            }

            .timeline-track-active {
                position: absolute;
                width: 3px;
                border-radius: 2px;
                background: rgba(127, 214, 255, 0.55);
            }

            .timeline-slider {
                position: absolute;
                width: 220px;
                height: 28px;
                margin: 0;
                transform: rotate(-90deg);
                transform-origin: center center;
                background: transparent;
                pointer-events: none;
                -webkit-appearance: none;
                appearance: none;
            }

            .timeline-slider::-webkit-slider-runnable-track {
                background: transparent;
                height: 4px;
            }

            .timeline-slider::-webkit-slider-thumb {
                pointer-events: auto;
                -webkit-appearance: none;
                appearance: none;
                width: 16px;
                height: 16px;
                border-radius: 50%;
                background: #7fd6ff;
                cursor: pointer;
                border: 2px solid rgba(255, 255, 255, 0.6);
                margin-top: -6px;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
            }

            .timeline-slider.start {
                z-index: 2;
            }

            .timeline-slider.end {
                z-index: 1;
            }

            .timeline-slider.end::-webkit-slider-thumb {
                background: #f2c94c;
            }

            .timeline-label {
                font-size: 10px;
                color: #d0dbf8;
                text-align: center;
                line-height: 1.2;
            }

            .timeline-reset-icon {
                width: 24px;
                height: 24px;
                border: 1px solid rgba(156, 166, 191, 0.3);
                border-radius: 6px;
                background: rgba(27, 34, 52, 0.7);
                color: rgba(200, 210, 240, 0.7);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                pointer-events: auto;
                transition: background 0.14s;
            }

            .timeline-reset-icon:hover {
                background: rgba(58, 75, 113, 0.95);
                color: #eef2ff;
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
                border: 1px solid rgba(156, 166, 191, 0.4);
                background: rgba(27, 34, 52, 0.9);
                color: #d8deef;
            }

            .icon-toolbar {
                position: absolute;
                top: 16px;
                right: 16px;
                z-index: 14;
                display: flex;
                flex-direction: column;
                gap: 4px;
                padding: 6px;
                border-radius: 12px;
                background: rgba(16, 20, 31, 0.58);
                border: 1px solid rgba(156, 166, 191, 0.22);
                backdrop-filter: blur(6px);
                pointer-events: auto;
                max-height: calc(100% - 32px);
                overflow-y: auto;
                scrollbar-width: none;
            }

            .icon-toolbar::-webkit-scrollbar {
                display: none;
            }

            .icon-btn {
                width: 28px;
                height: 28px;
                border-radius: 7px;
                border: 1px solid rgba(156, 166, 191, 0.4);
                background: rgba(27, 34, 52, 0.86);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: #e7ecff;
                cursor: pointer;
                transition: background 0.16s ease, transform 0.16s ease;
            }

            .icon-btn:hover {
                background: rgba(58, 75, 113, 0.95);
                transform: translateY(-1px);
            }

            .icon-btn.active {
                border-color: rgba(127, 214, 255, 0.8);
                background: rgba(46, 86, 125, 0.95);
            }

            .icon-btn svg {
                width: 14px;
                height: 14px;
                fill: none;
                stroke: currentColor;
                stroke-width: 1.8;
                stroke-linecap: round;
                stroke-linejoin: round;
            }

            .legend-overlay {
                left: 16px;
                bottom: 16px;
                padding: 10px;
                display: flex;
                flex-direction: column;
                gap: 8px;
                width: min(420px, calc(100% - 100px));
            }

            .legend-row {
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }

            .empty-search-state {
                position: absolute;
                z-index: 11;
                left: 50%;
                top: 50%;
                transform: translate(-50%, -50%);
                padding: 12px 16px;
                border-radius: 12px;
                border: 1px solid rgba(194, 112, 112, 0.56);
                background: rgba(54, 23, 28, 0.84);
                color: #f7d7d7;
                font-size: 13px;
                backdrop-filter: blur(8px);
            }

            .advanced-drawer {
                position: absolute;
                right: 16px;
                bottom: 16px;
                z-index: 15;
                width: min(720px, calc(100% - 32px));
                max-height: min(58vh, 540px);
                overflow: auto;
                border: 1px solid rgba(156, 166, 191, 0.22);
                border-radius: 12px;
                background: rgba(13, 17, 27, 0.72);
                backdrop-filter: blur(6px);
                pointer-events: auto;
            }

            .advanced-drawer > summary {
                list-style: none;
                cursor: pointer;
                padding: 10px 12px;
                font-size: 13px;
                font-weight: 600;
                border-bottom: 1px solid rgba(156, 166, 191, 0.3);
                color: #dbe4ff;
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
                    top: auto;
                    bottom: 56px;
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
                    width: min(480px, calc(100% - 32px));
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
                    top: auto;
                    bottom: 48px;
                    left: 8px;
                    width: 72px;
                    padding: 6px;
                }

                .timeline-sliders {
                    height: 120px;
                }

                .timeline-slider {
                    width: 120px;
                }

                .legend-overlay {
                    left: 8px;
                    bottom: 8px;
                    width: calc(100% - 96px);
                    padding: 6px 8px;
                }

                .legend-row {
                    gap: 6px;
                }

                .advanced-drawer {
                    right: 8px;
                    bottom: 8px;
                    width: calc(100% - 16px);
                    max-height: min(36vh, 320px);
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
        this._timelineStartPercent = 0;
        this._timelineEndPercent = 100;
        this._timelineMinTimestamp = 0;
        this._timelineMaxTimestamp = 0;
        this._panelVisibility = _resolvePanelVisibility();
        this._graphInstance = null;
        this._autoFitPending = false;
        this._timelineReloadTimer = null;
        this._entityTypePaletteNamespace = '';
        this._lastClickNodeId = '';
        this._lastClickTimestamp = 0;
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
        this._onTimelineStartInput = this._onTimelineStartInput.bind(this);
        this._onTimelineEndInput = this._onTimelineEndInput.bind(this);
        this._resetTimelineFilter = this._resetTimelineFilter.bind(this);
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
            || changedProperties.has('_entitySearchQuery')
            || changedProperties.has('_timelineStartPercent')
            || changedProperties.has('_timelineEndPercent')
        ) {
            this._syncGraph();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._timelineReloadTimer) {
            clearTimeout(this._timelineReloadTimer);
            this._timelineReloadTimer = null;
        }
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

    _buildGraphDataForScene() {
        const visibleGraph = this._getVisibleGraphSnapshot();
        const highlightedEdgeIds = new Set(this._shortestPathEdges.map((edge) => this._getEdgeId(edge)));
        const nodes = visibleGraph.nodes.map((node) => ({
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
        const links = visibleGraph.edges.map((edge) => {
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
            throw new Error('Graph canvas is not available');
        }
        this._graphInstance = factory()(container)
            .backgroundColor('rgba(0,0,0,0)')
            .cooldownTicks(120)
            .warmupTicks(80)
            .showNavInfo(false)
            .nodeLabel(() => '')
            .nodeColor((node) => node.color)
            .nodeVal((node) => node.size)
            .linkLabel(() => '')
            .nodeThreeObject((node) => {
                const sprite = this._createTextSprite(node.name || node.id || '', '#f0f4ff', 24);
                if (!sprite) {
                    return null;
                }
                sprite.visible = this._shouldShowNodeLabel(node);
                sprite.position.set(0, (node.size || 1.6) * 1.9, 0);
                return sprite;
            })
            .nodeThreeObjectExtend(true)
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
                return '#9ba3bf';
            })
            .linkWidth((link) => {
                if (link.path_kind === 'directed' || link.path_kind === 'undirected' || link.path_kind === 'both') {
                    return 4;
                }
                if (link.highlighted) {
                    return 4;
                }
                if (this._isLinkNearSelectedNode(link)) {
                    return 2.8;
                }
                return GRAPH_PRESETS[this._graphPreset].linkWidth + 0.6;
            })
            .linkOpacity((link) => {
                if (link.path_kind === 'directed' || link.path_kind === 'undirected' || link.path_kind === 'both') {
                    return 0.95;
                }
                if (link.highlighted || link.id === this._selectedEdgeId) {
                    return 0.95;
                }
                if (this._isLinkNearSelectedNode(link)) {
                    return 0.65;
                }
                return 0.3;
            })
            .linkThreeObjectExtend(true)
            .linkThreeObject((link) => {
                const sprite = this._createTextSprite(link.relation_type || 'related', '#d4dae8', 20);
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
                return link.directed ? 3 : 0;
            })
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
                    this._autoFitPending = false;
                    this._applySingleNodeCamera();
                    return;
                }
                if (this._autoFitPending) {
                    this._autoFitPending = false;
                    this._fitGraphToViewport(300, 90);
                }
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

    _togglePanel(panelId) {
        const nextVisibility = { ...this._panelVisibility };
        nextVisibility[panelId] = !nextVisibility[panelId];
        this._panelVisibility = nextVisibility;
        _savePanelVisibility(nextVisibility);
    }

    _onTimelineStartInput(event) {
        const value = Number(event.target.value);
        this._timelineStartPercent = Math.max(0, Math.min(this._timelineEndPercent, value));
        this._scheduleTimelineReload();
    }

    _onTimelineEndInput(event) {
        const value = Number(event.target.value);
        this._timelineEndPercent = Math.min(100, Math.max(this._timelineStartPercent, value));
        this._scheduleTimelineReload();
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
                this.error(`Ошибка таймлайна: ${message}`);
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
        this._canvasPathHint = 'Режим обзора';
        this._shortestPathEdges = [];
        await this._rebuildGraphByMode();
    }

    async _onToolbarAction(actionId) {
        if (actionId === 'fit') {
            this._fitGraphToViewport(250, 80);
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
        throw new Error(`Unsupported toolbar action: ${actionId}`);
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
        this._entitySearchQuery = '';
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
        if (this._graphEdges.length <= 16 && this._getCameraDistance() < ADAPTIVE_LABEL_DISTANCE * 0.82) {
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

    _createTextSprite(text, color = '#f2f5ff', fontSize = 22, maxLength = 28) {
        if (!window.THREE || typeof window.THREE.CanvasTexture !== 'function' || typeof window.THREE.Sprite !== 'function') {
            return null;
        }
        const baseText = typeof text === 'string' && text.trim().length > 0 ? text.trim() : 'entity';
        const labelText = baseText.length > maxLength ? `${baseText.slice(0, maxLength - 1)}…` : baseText;
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        if (!context) {
            return null;
        }
        context.font = `700 ${fontSize}px Inter, sans-serif`;
        const textWidth = Math.max(24, Math.ceil(context.measureText(labelText).width));
        canvas.width = textWidth + 18;
        canvas.height = fontSize + 12;
        context.font = `700 ${fontSize}px Inter, sans-serif`;
        context.fillStyle = color;
        context.textBaseline = 'middle';
        context.shadowColor = 'rgba(5, 7, 12, 0.95)';
        context.shadowBlur = 6;
        context.lineWidth = 4;
        context.strokeStyle = 'rgba(5, 7, 12, 0.92)';
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

    _onCanvasNodeClick(node, event) {
        this._selectedNodeId = node.id;
        this._attachmentEntityId = node.id;
        const now = Date.now();
        const isDoubleClick = this._lastClickNodeId === node.id && (now - this._lastClickTimestamp) < 380;
        this._lastClickNodeId = node.id;
        this._lastClickTimestamp = now;
        if (isDoubleClick) {
            this._flyToNode(node);
            return;
        }
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
                this._canvasPathHint = 'Выбери другую сущность для target';
                this.warning('Source и target должны быть разными');
                return;
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

    _flyToNode(node) {
        if (!this._graphInstance) {
            return;
        }
        const nodeX = node.x || 0;
        const nodeY = node.y || 0;
        const nodeZ = node.z || 0;
        const flyDistance = 120;
        this._graphInstance.cameraPosition(
            { x: nodeX, y: nodeY, z: nodeZ + flyDistance },
            { x: nodeX, y: nodeY, z: nodeZ },
            800,
        );
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
            await this._ensureEntityTypePaletteLoaded(namespaceName);
            const timelineBounds = await crmApi.getEntityTimelineBounds({ namespace: namespaceName });
            this._applyTimelineBounds(timelineBounds);
            const timelineParams = this._getTimelineQueryParams();
            const entities = await crmApi.getEntities({ namespace: namespaceName, limit: 120, ...timelineParams });
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
        const seedIds = seedEntities.map((entity) => entity.entity_id);
        const relationshipType = this._getRelationshipFilter();
        const timelineParams = this._getTimelineQueryParams();
        const response = await this.crmApi.getOverviewGraph(seedIds, {
            max_depth: this._maxDepth,
            relationship_types: relationshipType,
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
        const params = { max_depth: this._maxDepth, ...this._getTimelineQueryParams() };
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
            this._canvasPathHint = 'Маршрут не найден';
            this.warning(`Маршрут не найден: ${this._pathSourceId} -> ${this._pathTargetId}`);
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
        this._canvasPathHint = 'Маршруты построены: directed + undirected';
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
            this._clearCanvasSearchFilter();
            return;
        }
        const snapshot = this._getVisibleGraphSnapshot();
        if (snapshot.isEmpty) {
            this.warning('По фильтру ничего не найдено');
            return;
        }
        this.success(`Отфильтровано узлов: ${snapshot.nodes.length}`);
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

    _renderLegend(visibleNodes = []) {
        const colorsByType = this._getNamespaceEntityTypeColors();
        const visibleTypes = Array.from(new Set(
            visibleNodes
                .map((node) => (typeof node.entity_type === 'string' ? node.entity_type.trim() : ''))
                .filter((typeId) => typeId.length > 0 && typeId !== 'hidden'),
        ));
        return html`
            ${visibleTypes.map((typeId) => html`
                <div class="legend-item"><span class="legend-dot" style="background:${colorsByType.get(typeId)}"></span>${typeId}</div>
            `)}
            <div class="legend-item"><span class="legend-dot" style="background:#7f7f8f"></span> Hidden</div>
            <div class="legend-item"><span class="legend-dot" style="background:#41d36d"></span> Path directed</div>
            <div class="legend-item"><span class="legend-dot" style="background:#f2c94c"></span> Path undirected</div>
        `;
    }

    _renderToolbarIcon(actionId) {
        if (actionId === 'fit') {
            return html`<svg viewBox="0 0 24 24"><path d="M8 3H3v5"/><path d="M3 3l6 6"/><path d="M16 3h5v5"/><path d="M21 3l-6 6"/><path d="M8 21H3v-5"/><path d="M3 21l6-6"/><path d="M16 21h5v-5"/><path d="M21 21l-6-6"/></svg>`;
        }
        if (actionId === 'path_mode') {
            return html`<svg viewBox="0 0 24 24"><circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 17c4-6 5-9 10-10"/></svg>`;
        }
        if (actionId === 'swap_path') {
            return html`<svg viewBox="0 0 24 24"><path d="M4 7h14"/><path d="M14 3l4 4-4 4"/><path d="M20 17H6"/><path d="M10 13l-4 4 4 4"/></svg>`;
        }
        if (actionId === 'reset_path') {
            return html`<svg viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M7 6l1 14h8l1-14"/></svg>`;
        }
        if (actionId === 'depth_plus') {
            return html`<svg viewBox="0 0 24 24"><path d="M4 12h16"/><path d="M12 4v16"/></svg>`;
        }
        if (actionId === 'depth_minus') {
            return html`<svg viewBox="0 0 24 24"><path d="M4 12h16"/></svg>`;
        }
        if (actionId === 'filter_rel_type') {
            return html`<svg viewBox="0 0 24 24"><path d="M4 5h16"/><path d="M7 12h10"/><path d="M10 19h4"/></svg>`;
        }
        if (actionId === 'labels_mode') {
            return html`<svg viewBox="0 0 24 24"><path d="M4 18l4-12h2l4 12"/><path d="M6 13h6"/><path d="M16 8h4"/><path d="M18 8v10"/></svg>`;
        }
        if (actionId === 'reset_view') {
            return html`<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v5h5"/></svg>`;
        }
        if (actionId === 'toggle_search') {
            return html`<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>`;
        }
        if (actionId === 'toggle_timeline') {
            return html`<svg viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M8 7l4-4 4 4"/><path d="M8 17l4 4 4-4"/></svg>`;
        }
        if (actionId === 'toggle_legend') {
            return html`<svg viewBox="0 0 24 24"><path d="M4 6h16"/><path d="M4 12h10"/><path d="M4 18h6"/></svg>`;
        }
        if (actionId === 'toggle_meta') {
            return html`<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M12 12v4"/></svg>`;
        }
        throw new Error(`Unknown icon action: ${actionId}`);
    }

    render() {
        const operations = this._getBackendOperations();
        const coverageMatrix = this._getCoverageMatrix();
        const coveredNativeCount = coverageMatrix.filter((item) => item.status === 'covered_by_native_ui').length;
        const coveredJsonCount = coverageMatrix.filter((item) => item.status === 'covered_by_json_runner_only').length;
        const uncoveredCount = coverageMatrix.filter((item) => item.status === 'not_covered').length;
        const relationshipTypes = this._getRelationshipTypes();
        const visibleGraph = this._getVisibleGraphSnapshot();
        const timelineSpan = Math.max(1, this._timelineMaxTimestamp - this._timelineMinTimestamp);
        const timelineFromTimestamp = this._timelineMinTimestamp + (timelineSpan * (this._timelineStartPercent / 100));
        const timelineToTimestamp = this._timelineMinTimestamp + (timelineSpan * (this._timelineEndPercent / 100));
        const toolbarActions = [
            { id: 'fit', label: 'Вписать граф' },
            { id: 'path_mode', label: 'Режим выбора маршрута' },
            { id: 'swap_path', label: 'Поменять source/target' },
            { id: 'reset_path', label: 'Сбросить маршрут' },
            { id: 'depth_plus', label: 'Увеличить глубину' },
            { id: 'depth_minus', label: 'Уменьшить глубину' },
            { id: 'filter_rel_type', label: 'Фильтр по типу связи' },
            { id: 'labels_mode', label: 'Переключить режим лейблов' },
            { id: 'reset_view', label: 'Сбросить вид' },
        ];
        return html`
            <div class="canvas-layout">
                <section class="canvas-stage">
                    <div id="graph-canvas" class="graph-canvas"></div>

                    <div class="overlay-search ${this._panelVisibility.search ? '' : 'panel-hidden'}">
                        <div class="search-pill">
                            <input
                                type="text"
                                .value=${this._entitySearchQuery}
                                placeholder="Фильтр..."
                                @input=${this._onSearchQueryInput}
                                @keydown=${(e) => e.key === 'Escape' && this._clearCanvasSearchFilter()}
                            />
                            ${this._entitySearchQuery.trim()
                                ? html`<button class="pill-icon-btn" type="button" title="Очистить" @click=${this._clearCanvasSearchFilter}><svg viewBox="0 0 24 24"><path d="M18 6L6 18"/><path d="M6 6l12 12"/></svg></button>`
                                : html`<button class="pill-icon-btn" type="button" title="Обновить граф" @click=${this._loadGraphData}><svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v5h5"/></svg></button>`
                            }
                        </div>
                        <div class="mode-pills">
                            ${VIEW_MODES.map((mode) => html`
                                <button class="mode-pill ${this._viewMode === mode ? 'active' : ''}" type="button" @click=${() => { this._viewMode = mode; if (mode !== 'influence') { this._defaultOverviewActive = false; } if (mode !== 'path') { this._canvasPathState = 'idle'; this._canvasPathHint = 'Режим обзора'; } this._rebuildGraphByMode(); }}>
                                    ${mode === 'influence' ? 'influence' : mode === 'related' ? 'related' : 'path'}
                                </button>
                            `)}
                        </div>
                    </div>

                    <div class="overlay-card timeline-overlay ${this._panelVisibility.timeline ? '' : 'panel-hidden'}">
                        <div class="timeline-title">Timeline</div>
                        <div class="timeline-label">${this._formatTimelineLabel(this._timelineMaxTimestamp)}</div>
                        <div class="timeline-sliders">
                            <div class="timeline-track"></div>
                            <div
                                class="timeline-track-active"
                                style="top:${100 - this._timelineEndPercent}%;bottom:${this._timelineStartPercent}%"
                            ></div>
                            <input
                                class="timeline-slider start"
                                type="range"
                                min="0"
                                max="100"
                                step="1"
                                .value=${String(this._timelineStartPercent)}
                                @input=${this._onTimelineStartInput}
                            />
                            <input
                                class="timeline-slider end"
                                type="range"
                                min="0"
                                max="100"
                                step="1"
                                .value=${String(this._timelineEndPercent)}
                                @input=${this._onTimelineEndInput}
                            />
                        </div>
                        <div class="timeline-label">${this._formatTimelineLabel(this._timelineMinTimestamp)}</div>
                        <button class="pill-icon-btn timeline-reset-icon" type="button" title="Сброс timeline" @click=${this._resetTimelineFilter}>
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v5h5"/></svg>
                        </button>
                    </div>

                    <div class="overlay-card overlay-meta ${this._panelVisibility.meta ? '' : 'panel-hidden'}">
                        <span class="meta-pill">режим: ${this._viewMode}</span>
                        <span class="meta-pill">глубина: ${this._maxDepth}</span>
                        <span class="meta-pill">узлов: ${visibleGraph.nodes.length}</span>
                        <span class="meta-pill">связей: ${visibleGraph.edges.length}</span>
                    </div>

                    <div class="icon-toolbar">
                        ${toolbarActions.map((action) => html`
                            <button
                                class="icon-btn ${action.id === 'labels_mode' && this._labelMode === 'adaptive' ? 'active' : ''}"
                                type="button"
                                title=${action.label}
                                aria-label=${action.label}
                                @click=${() => this._onToolbarAction(action.id)}
                            >
                                ${this._renderToolbarIcon(action.id)}
                            </button>
                        `)}
                        <div class="toolbar-separator"></div>
                        <button class="icon-btn toggle-btn ${this._panelVisibility.search ? 'active' : ''}" type="button" title="Показать/скрыть поиск" @click=${() => this._togglePanel('search')}>${this._renderToolbarIcon('toggle_search')}</button>
                        <button class="icon-btn toggle-btn ${this._panelVisibility.timeline ? 'active' : ''}" type="button" title="Показать/скрыть timeline" @click=${() => this._togglePanel('timeline')}>${this._renderToolbarIcon('toggle_timeline')}</button>
                        <button class="icon-btn toggle-btn ${this._panelVisibility.legend ? 'active' : ''}" type="button" title="Показать/скрыть легенду" @click=${() => this._togglePanel('legend')}>${this._renderToolbarIcon('toggle_legend')}</button>
                        <button class="icon-btn toggle-btn ${this._panelVisibility.meta ? 'active' : ''}" type="button" title="Показать/скрыть статистику" @click=${() => this._togglePanel('meta')}>${this._renderToolbarIcon('toggle_meta')}</button>
                    </div>

                    <div class="overlay-card legend-overlay ${this._panelVisibility.legend ? '' : 'panel-hidden'}">
                        <div class="legend-row">${this._renderLegend(visibleGraph.nodes)}</div>
                        <div class="legend-row">
                            <span class="canvas-hint">${this._canvasPathHint}</span>
                            <span class="node-pill">node: ${this._selectedNodeId || '—'}</span>
                            <span class="node-pill">edge: ${this._selectedEdgeId || '—'}</span>
                        </div>
                    </div>

                    ${visibleGraph.isFiltered && visibleGraph.isEmpty ? html`
                        <div class="empty-search-state">По текущему фильтру совпадений нет</div>
                    ` : ''}

                    <details class="advanced-drawer">
                        <summary>Advanced операции и диагностика</summary>
                        <div class="advanced-content">
                            <details class="section-collapsible">
                                <summary>Backend runner</summary>
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
                                <summary>Быстрые native действия</summary>
                                <div class="section-collapsible-content">
                                    <div class="row">
                                        <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._focusSelectedNode}>Фокус на выбранном узле</button>
                                        <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._expandFromSelected}>Раскрыть соседей</button>
                                        <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._isolateSelectedNeighborhood}>Оставить окружение</button>
                                        <button class="btn btn-secondary" type="button" ?disabled=${this._backendLoading} @click=${this._revealNextLevel}>Следующий уровень</button>
                                    </div>
                                    <div class="section-grid">
                                        <input class="toolbar-input" type="text" .value=${this._attachmentEntityId} placeholder="entity_id для вложения" @input=${this._onAttachmentEntityIdInput} />
                                        <input type="file" @change=${this._onAttachmentFileChange} />
                                    </div>
                                    <button class="btn btn-secondary" type="button" @click=${this._uploadAttachment}>Загрузить вложение</button>
                                </div>
                            </details>

                            <div class="section">
                                <div class="section-title">Результат операции</div>
                                <div class="result-box">${this._backendOperationResult || 'Пока нет выполненных операций'}</div>
                            </div>
                        </div>
                    </details>
                </section>
            </div>
        `;
    }
}

customElements.define('graph-page', GraphPage);
