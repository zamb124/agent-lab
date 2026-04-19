/**
 * GraphPage — экран графа знаний CRM.
 *
 * Layout: единый canvas-stage с overlay-картами:
 *   - graph-canvas (3D ForceGraph3D);
 *   - graph-search-pill (top-left): поиск + минимальная релевантность + view-mode
 *     (influence / related / path);
 *   - graph-timeline (left): фильтр диапазона created_at;
 *   - graph-toolbar (top-right): действия + переключатели панелей;
 *   - graph-legend (bottom-left): палитра entity_type + контекст;
 *   - graph-context-menu: открытие карточки, фокус, маршрут / граф от узла;
 *   - meta-pills: режим/глубина/узлы/связи.
 *
 * Все доменные данные — через фабрики платформы:
 *
 *   - useResource('crm/entity_types')         — палитра по entity_type;
 *   - useResource('crm/relationship_types')   — справочник типов связей;
 *   - useOp('crm/timeline_bounds')            — границы шкалы времени;
 *   - useOp('crm/entities_lookup')            — список сущностей и seed-нот для
 *     overview-режима;
 *   - useOp('crm/overview_graph')             — overview по списку сущностей и
 *     по результатам entitySearchOp;
 *   - useOp('crm/influence_graph')            — influence по выбранному корню;
 *   - useOp('crm/related_entities')           — окружение корня;
 *   - useOp('crm/entity_relationships')       — рёбра в режиме related;
 *   - useOp('crm/shortest_path')              — кратчайший путь;
 *   - useOp('crm/entity_search')              — поиск по запросу.
 *
 * UI-команды (модалки, тосты, навигация) — только через helpers `PlatformPage`
 * (`openModal`, `toast`, `navigate`). Никаких прямых dispatch UI/ROUTER/AUTH,
 * httpRequest, fetch, services.* / store / features.
 *
 * Live-обновления:
 *   - подписка на `CoreEvents.UI_NAMESPACE_CHANGED` — полная перезагрузка;
 *   - подписки на `crm/entity/updated`, `crm/relationship/created`,
 *     `crm/entity_merge/succeeded` — точечная перерисовка графа.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '../components/graph-canvas.js';
import '../components/graph-search-pill.js';
import '../components/graph-timeline.js';
import '../components/graph-toolbar.js';
import '../components/graph-legend.js';
import '../components/graph-context-menu.js';

const VIEW_MODES = ['influence', 'related', 'path'];
const PANEL_IDS = ['search', 'timeline', 'legend', 'meta'];
const PANELS_STORAGE_KEY = 'crm_graph_panels';
const TIMELINE_SEEDED_KEY = 'crm_graph_timeline_seeded';
const SEARCH_DEBOUNCE_MS = 400;
const TIMELINE_RELOAD_DEBOUNCE_MS = 220;

function _isMobileViewport() {
    return typeof window !== 'undefined' && window.innerWidth <= 767;
}

function _resolvePanelVisibility() {
    const isMobile = _isMobileViewport();
    const defaults = {
        search: !isMobile,
        timeline: !isMobile,
        legend: !isMobile,
        meta: !isMobile,
    };
    if (typeof localStorage === 'undefined') return defaults;
    const raw = localStorage.getItem(PANELS_STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return defaults;
    const resolved = {};
    PANEL_IDS.forEach((panelId) => {
        resolved[panelId] = typeof parsed[panelId] === 'boolean' ? parsed[panelId] : defaults[panelId];
    });
    return resolved;
}

function _persistPanelVisibility(panels) {
    if (typeof localStorage === 'undefined') return;
    localStorage.setItem(PANELS_STORAGE_KEY, JSON.stringify(panels));
}

function _parseTimestamp(rawValue) {
    if (!rawValue) return null;
    const ts = Date.parse(rawValue);
    return Number.isFinite(ts) ? ts : null;
}

function _getEdgeId(edge) {
    const edgeId = edge.edge_id || edge.relationship_id || edge.id;
    if (typeof edgeId === 'string' && edgeId.trim().length > 0) {
        return edgeId;
    }
    const sourceId = edge.source_id || edge.source_entity_id || edge.source;
    const targetId = edge.target_id || edge.target_entity_id || edge.target;
    const relationType = edge.relationship_type || edge.type || 'related';
    return `${sourceId}:${targetId}:${relationType}`;
}

export class CRMGraphPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _viewMode: { state: true },
        _selectedRootId: { state: true },
        _maxDepth: { state: true },
        _pathSourceId: { state: true },
        _pathTargetId: { state: true },
        _pathMaxDepth: { state: true },
        _entitySearchQuery: { state: true },
        _searchMode: { state: true },
        _minScore: { state: true },
        _relationshipTypeFilter: { state: true },
        _relatedDirection: { state: true },
        _selectedNodeId: { state: true },
        _selectedEdgeId: { state: true },
        _graphPreset: { state: true },
        _labelMode: { state: true },
        _timelineStartPercent: { state: true },
        _timelineEndPercent: { state: true },
        _timelineMinTimestamp: { state: true },
        _timelineMaxTimestamp: { state: true },
        _panelVisibility: { state: true },
        _contextMenu: { state: true },
        _graphNodes: { state: true },
        _graphEdges: { state: true },
        _shortestPathEdges: { state: true },
        _defaultOverviewActive: { state: true },
        _overviewSeedEntityIds: { state: true },
        _canvasPathState: { state: true },
        _canvasPathHint: { state: true },
        _mergeAnchorId: { state: true },
        _entitiesById: { state: true },
        _loading: { state: true },
    };

    static styles = [
        PlatformPage.styles,
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

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: var(--space-2) var(--space-3) 0;
            }

            .canvas-stage {
                position: relative;
                flex: 1;
                width: 100%;
                min-height: 560px;
                background: var(--bg-secondary);
            }

            crm-graph-canvas {
                position: absolute;
                inset: 0;
                z-index: 0;
            }

            .overlay-card {
                position: absolute;
                z-index: 12;
                color: var(--text-primary);
                pointer-events: auto;
                transition: opacity 0.18s ease;
            }

            .panel-hidden {
                display: none !important;
            }

            crm-graph-search-pill {
                position: absolute;
                z-index: 12;
                top: 20px;
                left: 20px;
            }

            crm-graph-timeline {
                position: absolute;
                z-index: 12;
                top: 80px;
                left: 16px;
            }

            crm-graph-toolbar {
                position: absolute;
                top: 16px;
                right: 16px;
                z-index: 14;
            }

            crm-graph-legend {
                position: absolute;
                left: 16px;
                bottom: 16px;
                z-index: 12;
                max-width: 460px;
            }

            crm-graph-context-menu {
                position: absolute;
                z-index: 20;
            }

            .overlay-meta {
                position: absolute;
                top: 20px;
                right: 70px;
                z-index: 12;
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 6px 10px;
                font-size: 11px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: 14px;
                backdrop-filter: blur(6px);
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

            .empty-search-state,
            .empty-data-state {
                position: absolute;
                z-index: 11;
                left: 50%;
                top: 50%;
                transform: translate(-50%, -50%);
                padding: 12px 16px;
                border-radius: 12px;
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: 13px;
                backdrop-filter: blur(8px);
                text-align: center;
                max-width: 80%;
            }

            .empty-data-state h3 {
                margin: 0 0 4px;
                color: var(--text-primary);
            }

            .empty-data-state p {
                margin: 0 0 12px;
                color: var(--text-secondary);
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
                border: 1px solid var(--accent);
                background: var(--accent);
                color: var(--text-on-accent, #fff);
                border-radius: 22px;
                padding: 8px 24px;
                font-size: 14px;
                cursor: pointer;
            }

            .loading-overlay {
                position: absolute;
                z-index: 13;
                top: 12px;
                left: 50%;
                transform: translateX(-50%);
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 6px 14px;
                border-radius: 999px;
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-secondary);
                font-size: 12px;
                backdrop-filter: blur(6px);
            }

            @media (max-width: 767px) {
                :host { border: none; border-radius: 0; }
                .canvas-stage { min-height: 400px; }
                crm-graph-search-pill { top: 8px; left: 8px; }
                crm-graph-toolbar { top: 8px; right: 8px; }
                crm-graph-legend { left: 8px; bottom: 8px; }
                .overlay-meta { display: none; }
            }
        `,
    ];

    constructor() {
        super();
        this._viewMode = 'influence';
        this._selectedRootId = '';
        this._maxDepth = 5;
        this._pathSourceId = '';
        this._pathTargetId = '';
        this._pathMaxDepth = 10;
        this._entitySearchQuery = '';
        this._searchMode = 'hybrid';
        this._minScore = 0.0;
        this._relationshipTypeFilter = '';
        this._relatedDirection = 'both';
        this._selectedNodeId = '';
        this._selectedEdgeId = '';
        this._graphPreset = 'readable';
        this._labelMode = 'adaptive';
        this._timelineStartPercent = 0;
        this._timelineEndPercent = 100;
        this._timelineMinTimestamp = 0;
        this._timelineMaxTimestamp = 0;
        this._panelVisibility = _resolvePanelVisibility();
        this._contextMenu = null;
        this._graphNodes = [];
        this._relatedNodesPending = [];
        this._relatedNodeIds = new Set();
        this._graphEdges = [];
        this._shortestPathEdges = [];
        this._defaultOverviewActive = true;
        this._overviewSeedEntityIds = [];
        this._canvasPathState = 'idle';
        this._canvasPathHint = '';
        this._mergeAnchorId = '';
        this._entitiesById = new Map();
        this._loading = false;
        this._searchDebounceTimer = null;
        this._timelineReloadTimer = null;
        this._pendingPathLookups = null;
        this._lastNamespaceLoaded = undefined;

        this._entityTypes = this.useResource('crm/entity_types', { autoload: true });
        this._relationshipTypes = this.useResource('crm/relationship_types', { autoload: true });
        this._timelineBoundsOp = this.useOp('crm/timeline_bounds');
        this._entitiesLookupOp = this.useOp('crm/entities_lookup');
        this._overviewOp = this.useOp('crm/overview_graph');
        this._influenceOp = this.useOp('crm/influence_graph');
        this._relatedOp = this.useOp('crm/related_entities');
        this._entityRelOp = this.useOp('crm/entity_relationships');
        this._shortestPathOp = this.useOp('crm/shortest_path');
        this._entitySearchOp = this.useOp('crm/entity_search');

        this._namespaceSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') return 'all';
            const cid = user.company_id;
            const map = s.ui.namespace.selectionByCompany;
            const sel = map[cid];
            if (sel === 'all' || sel === undefined) return 'all';
            return sel;
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this._canvasPathHint = this.t('graph_page.hint_browse');

        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => this._reloadAll());
        this.useEvent('crm/entity/updated', () => this._reloadCurrentMode());
        this.useEvent('crm/entity/removed', () => this._reloadAll());
        this.useEvent('crm/relationship/created', () => this._reloadCurrentMode());
        this.useEvent('crm/relationship/removed', () => this._reloadCurrentMode());
        this.useEvent('crm/entity_merge/succeeded', () => this._reloadAll());

        this.useEvent(this._timelineBoundsOp.op.events.SUCCEEDED, (event) => this._onTimelineBoundsLoaded(event.payload.result));
        this.useEvent(this._entitiesLookupOp.op.events.SUCCEEDED, (event) => this._onEntitiesLookupLoaded(event.payload.result));
        this.useEvent(this._overviewOp.op.events.SUCCEEDED, (event) => this._onGraphResponse(event.payload.result));
        this.useEvent(this._influenceOp.op.events.SUCCEEDED, (event) => this._onGraphResponse(event.payload.result));
        this.useEvent(this._relatedOp.op.events.SUCCEEDED, (event) => this._onRelatedLoaded(event.payload.result));
        this.useEvent(this._entityRelOp.op.events.SUCCEEDED, (event) => this._onEntityRelationshipsLoaded(event.payload.result));
        this.useEvent(this._shortestPathOp.op.events.SUCCEEDED, (event) => this._onShortestPathLoaded(event.payload.result));
        this.useEvent(this._entitySearchOp.op.events.SUCCEEDED, (event) => this._onSearchLoaded(event.payload.result));

        this.useEvent(this._timelineBoundsOp.op.events.FAILED, (event) => {
            this._loading = false;
            this.toast('crm:graph_page.err_timeline', { type: 'error', vars: { message: event.payload.message } });
        });
        this.useEvent(this._shortestPathOp.op.events.FAILED, (event) => {
            this._loading = false;
            this.toast('crm:graph_page.err_path_build', { type: 'error', vars: { message: event.payload.message } });
        });
        this.useEvent(this._overviewOp.op.events.FAILED, () => { this._loading = false; });
        this.useEvent(this._influenceOp.op.events.FAILED, () => { this._loading = false; });
        this.useEvent(this._relatedOp.op.events.FAILED, () => { this._loading = false; });
        this.useEvent(this._entityRelOp.op.events.FAILED, () => { this._loading = false; });
        this.useEvent(this._entitiesLookupOp.op.events.FAILED, () => { this._loading = false; });
        this.useEvent(this._entitySearchOp.op.events.FAILED, () => { this._loading = false; });

        this._reloadAll();
    }

    disconnectedCallback() {
        if (this._searchDebounceTimer) {
            clearTimeout(this._searchDebounceTimer);
            this._searchDebounceTimer = null;
        }
        if (this._timelineReloadTimer) {
            clearTimeout(this._timelineReloadTimer);
            this._timelineReloadTimer = null;
        }
        super.disconnectedCallback();
    }

    _currentNamespace() {
        const sel = this._namespaceSel.value;
        return sel === 'all' ? null : sel;
    }

    _reloadAll() {
        this._loading = true;
        const namespace = this._currentNamespace();
        this._lastNamespaceLoaded = namespace;
        this._entityTypes.load({ namespace: namespace === null ? undefined : namespace });
        this._timelineBoundsOp.run({ namespace: namespace === null ? undefined : namespace });
    }

    _onTimelineBoundsLoaded(bounds) {
        const minTs = _parseTimestamp(bounds && bounds.min_created_at);
        const maxTs = _parseTimestamp(bounds && bounds.max_created_at);
        const total = Number(bounds && bounds.total_entities);
        if (!Number.isFinite(total) || total <= 0 || minTs === null || maxTs === null) {
            this._timelineMinTimestamp = 0;
            this._timelineMaxTimestamp = 0;
            this._timelineStartPercent = 0;
            this._timelineEndPercent = 100;
        } else {
            this._timelineMinTimestamp = minTs;
            this._timelineMaxTimestamp = maxTs;
            this._applyDefaultTimelineTodayIfNeeded();
        }
        const namespace = this._currentNamespace();
        const timelineParams = this._getTimelineQueryParams();
        this._entitiesLookupOp.run({
            namespace: namespace === null ? undefined : namespace,
            limit: 120,
            ...timelineParams,
        });
    }

    _applyDefaultTimelineTodayIfNeeded() {
        if (typeof sessionStorage === 'undefined') return;
        if (sessionStorage.getItem(TIMELINE_SEEDED_KEY)) return;
        if (!this._timelineMinTimestamp || !this._timelineMaxTimestamp) {
            sessionStorage.setItem(TIMELINE_SEEDED_KEY, '1');
            return;
        }
        const span = Math.max(1, this._timelineMaxTimestamp - this._timelineMinTimestamp);
        const now = new Date();
        const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0).getTime();
        const endOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999).getTime();
        let startPercent = ((startOfDay - this._timelineMinTimestamp) / span) * 100;
        let endPercent = ((endOfDay - this._timelineMinTimestamp) / span) * 100;
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
        sessionStorage.setItem(TIMELINE_SEEDED_KEY, '1');
    }

    _onEntitiesLookupLoaded(response) {
        const items = response && Array.isArray(response.items) ? response.items : [];
        const map = new Map();
        items.forEach((item) => {
            if (item && typeof item.entity_id === 'string') {
                map.set(item.entity_id, item);
            }
        });
        this._entitiesById = map;
        this._overviewSeedEntityIds = items
            .filter((item) => item && item.entity_type === 'note')
            .map((item) => item.entity_id)
            .slice(0, 20);

        if (!this._selectedRootId && items.length > 0) {
            this._selectedRootId = items[0].entity_id;
        }
        if (!this._pathSourceId && items.length > 0) {
            this._pathSourceId = this._selectedRootId;
        }
        if (!this._pathTargetId && items.length > 1) {
            const target = items.find((entity) => entity.entity_id !== this._pathSourceId);
            this._pathTargetId = target ? target.entity_id : items[0].entity_id;
        }
        this._rebuildGraphByMode();
    }

    _onGraphResponse(response) {
        if (!response || typeof response !== 'object') {
            this._graphNodes = [];
            this._graphEdges = [];
            this._loading = false;
            return;
        }
        this._graphNodes = Array.isArray(response.nodes) ? response.nodes : [];
        this._graphEdges = Array.isArray(response.edges) ? response.edges : [];
        this._shortestPathEdges = [];
        this._loading = false;
    }

    _onRelatedLoaded(response) {
        if (!response || typeof response !== 'object') {
            this._loading = false;
            return;
        }
        const nodeMap = new Map();
        const rootEntity = this._entitiesById.get(this._selectedRootId);
        if (rootEntity) {
            nodeMap.set(this._selectedRootId, {
                entity_id: rootEntity.entity_id,
                entity_type: rootEntity.entity_type,
                name: rootEntity.name,
                level: 0,
                access: true,
                created_at: typeof rootEntity.created_at === 'string' ? rootEntity.created_at : null,
                attributes: rootEntity.attributes && typeof rootEntity.attributes === 'object' ? rootEntity.attributes : {},
            });
        }
        ['incoming', 'outgoing', 'undirected'].forEach((bucket) => {
            const collection = response[bucket];
            if (!Array.isArray(collection)) return;
            collection.forEach((node) => {
                if (node && typeof node.entity_id === 'string') {
                    nodeMap.set(node.entity_id, node);
                }
            });
        });
        this._relatedNodeIds = new Set(nodeMap.keys());
        this._relatedNodesPending = Array.from(nodeMap.values());
        const namespace = this._currentNamespace();
        this._entityRelOp.run({
            entityId: this._selectedRootId,
            params: { namespace: namespace === null ? undefined : namespace },
        });
    }

    _onEntityRelationshipsLoaded(response) {
        if (!response || !Array.isArray(response.relationships)) {
            this._loading = false;
            return;
        }
        const relationType = this._relationshipTypeFilter.trim();
        const allowed = this._relatedNodeIds;
        const filtered = response.relationships.filter((edge) => {
            const source = edge.source_entity_id;
            const target = edge.target_entity_id;
            if (!allowed.has(source) || !allowed.has(target)) return false;
            if (relationType.length > 0 && edge.relationship_type !== relationType) return false;
            return true;
        });
        this._graphNodes = this._relatedNodesPending;
        this._graphEdges = filtered;
        this._shortestPathEdges = [];
        this._loading = false;
    }

    _onShortestPathLoaded(response) {
        if (!response || !Array.isArray(response.path) || !Array.isArray(response.edges)) {
            this._loading = false;
            return;
        }
        const undirectedPath = Array.isArray(response.undirected_path) ? response.undirected_path : [];
        const undirectedEdges = Array.isArray(response.undirected_edges) ? response.undirected_edges : [];
        const directedExists = response.exists === true && response.path.length > 0;
        const undirectedExists = response.undirected_exists === true && undirectedPath.length > 0;
        if (!directedExists && !undirectedExists) {
            this._shortestPathEdges = [];
            this._graphNodes = [];
            this._graphEdges = [];
            this._canvasPathHint = this.t('graph_page.hint_route_not_found');
            this.toast('crm:graph_page.warn_path_not_found', {
                type: 'warning',
                vars: { source: this._pathSourceId, target: this._pathTargetId },
            });
            this._loading = false;
            return;
        }
        const merged = this._mergePathEdgesByKind(response.edges, undirectedEdges);
        this._shortestPathEdges = merged;
        const allPathNodeIds = Array.from(new Set([...response.path, ...undirectedPath]));
        const nodes = allPathNodeIds.map((entityId, index) => {
            const entity = this._entitiesById.get(entityId);
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
                created_at: typeof entity.created_at === 'string' ? entity.created_at : null,
                attributes: entity.attributes && typeof entity.attributes === 'object' ? entity.attributes : {},
            };
        });
        this._graphNodes = nodes;
        this._graphEdges = merged;
        this._canvasPathState = 'built';
        this._canvasPathHint = this.t('graph_page.hint_routes_dual');
        this._loading = false;
    }

    _mergePathEdgesByKind(directedEdges, undirectedEdges) {
        const merged = new Map();
        directedEdges.forEach((edge) => {
            merged.set(_getEdgeId(edge), { ...edge, path_kind: 'directed' });
        });
        undirectedEdges.forEach((edge) => {
            const id = _getEdgeId(edge);
            const existing = merged.get(id);
            if (!existing) {
                merged.set(id, { ...edge, path_kind: 'undirected' });
                return;
            }
            merged.set(id, { ...existing, path_kind: 'both' });
        });
        return Array.from(merged.values());
    }

    _onSearchLoaded(response) {
        const all = response && Array.isArray(response.items) ? response.items : [];
        const items = this._minScore > 0
            ? all.filter((entry) => (typeof entry.score === 'number' ? entry.score : 0) >= this._minScore)
            : all;
        if (items.length === 0) {
            this._graphNodes = [];
            this._graphEdges = [];
            this.toast('crm:graph.search_empty', { type: 'warning' });
            this._loading = false;
            return;
        }
        const entityIds = items
            .map((entry) => entry.entity_id)
            .filter((id) => typeof id === 'string' && id.length > 0);
        const namespace = this._currentNamespace();
        const timelineParams = this._getTimelineQueryParams();
        const payload = {
            entity_ids: entityIds,
            max_depth: this._maxDepth,
            ...timelineParams,
        };
        if (namespace !== null) payload.namespace = namespace;
        if (this._relationshipTypeFilter.trim().length > 0) {
            payload.relationship_types = this._relationshipTypeFilter.trim();
        }
        this._overviewOp.run(payload);
    }

    _reloadCurrentMode() {
        this._rebuildGraphByMode();
    }

    _getTimelineQueryParams() {
        if (!this._timelineMinTimestamp || !this._timelineMaxTimestamp) return {};
        if (this._timelineStartPercent <= 0 && this._timelineEndPercent >= 100) return {};
        const span = Math.max(1, this._timelineMaxTimestamp - this._timelineMinTimestamp);
        const fromTs = this._timelineMinTimestamp + (span * (this._timelineStartPercent / 100));
        const toTs = this._timelineMinTimestamp + (span * (this._timelineEndPercent / 100));
        return {
            created_at_from: new Date(fromTs).toISOString(),
            created_at_to: new Date(toTs).toISOString(),
        };
    }

    _rebuildGraphByMode() {
        if (this._entitySearchQuery.trim().length > 0) {
            this._executeSearch();
            return;
        }
        if (this._viewMode === 'influence' && this._defaultOverviewActive) {
            this._buildOverviewGraph();
            return;
        }
        if (!this._selectedRootId) {
            this._graphNodes = [];
            this._graphEdges = [];
            this._loading = false;
            return;
        }
        if (this._viewMode === 'influence') {
            this._buildInfluenceGraph();
            return;
        }
        if (this._viewMode === 'related') {
            this._buildRelatedGraph();
            return;
        }
        if (this._viewMode === 'path') {
            this._buildPathGraph();
            return;
        }
    }

    _buildOverviewGraph() {
        if (this._overviewSeedEntityIds.length === 0) {
            this._graphNodes = [];
            this._graphEdges = [];
            this._shortestPathEdges = [];
            this._loading = false;
            return;
        }
        this._loading = true;
        const namespace = this._currentNamespace();
        const timelineParams = this._getTimelineQueryParams();
        const payload = {
            entity_ids: this._overviewSeedEntityIds,
            max_depth: this._maxDepth,
            ...timelineParams,
        };
        if (namespace !== null) payload.namespace = namespace;
        if (this._relationshipTypeFilter.trim().length > 0) {
            payload.relationship_types = this._relationshipTypeFilter.trim();
        }
        this._overviewOp.run(payload);
    }

    _buildInfluenceGraph() {
        this._loading = true;
        const namespace = this._currentNamespace();
        const params = {
            max_depth: this._maxDepth,
            ...this._getTimelineQueryParams(),
        };
        if (namespace !== null) params.namespace = namespace;
        if (this._relationshipTypeFilter.trim().length > 0) {
            params.relationship_types = this._relationshipTypeFilter.trim();
        }
        this._influenceOp.run({ entityId: this._selectedRootId, params });
    }

    _buildRelatedGraph() {
        this._loading = true;
        const params = {
            direction: this._relatedDirection,
            ...this._getTimelineQueryParams(),
        };
        if (this._relationshipTypeFilter.trim().length > 0) {
            params.relationship_type = this._relationshipTypeFilter.trim();
        }
        this._relatedOp.run({ entityId: this._selectedRootId, params });
    }

    _buildPathGraph() {
        if (!this._pathSourceId || !this._pathTargetId) {
            this._loading = false;
            return;
        }
        if (this._pathSourceId === this._pathTargetId) {
            this.toast('crm:graph_page.warn_source_target_same', { type: 'warning' });
            this._loading = false;
            return;
        }
        this._loading = true;
        const namespace = this._currentNamespace();
        const payload = {
            source_id: this._pathSourceId,
            target_id: this._pathTargetId,
            max_depth: this._pathMaxDepth,
            ...this._getTimelineQueryParams(),
        };
        if (namespace !== null) payload.namespace = namespace;
        this._shortestPathOp.run(payload);
    }

    _executeSearch() {
        this._loading = true;
        const namespace = this._currentNamespace();
        const payload = {
            q: this._entitySearchQuery.trim(),
            search_mode: this._searchMode,
            limit: 50,
        };
        if (namespace !== null) payload.namespace = namespace;
        this._entitySearchOp.run(payload);
    }

    _getEntityTypeColors() {
        const colors = new Map();
        this._entityTypes.items.forEach((item) => {
            const typeId = typeof item.type_id === 'string' ? item.type_id.trim() : '';
            if (!typeId) return;
            const color = typeof item.color === 'string' ? item.color.trim() : '';
            if (color) colors.set(typeId, color);
        });
        return colors;
    }

    _getRelationshipTypeColors() {
        const colors = new Map();
        this._relationshipTypes.items.forEach((item) => {
            const typeId = typeof item.type_id === 'string' ? item.type_id.trim() : '';
            if (!typeId) return;
            const color = typeof item.color === 'string' ? item.color.trim() : '';
            if (color) colors.set(typeId, color);
        });
        return colors;
    }

    _nodeColor(node) {
        if (node && node.access === false) return '#7f7f8f';
        const entityType = node && typeof node.entity_type === 'string' ? node.entity_type.trim() : '';
        if (!entityType) return '#bca8ff';
        const colors = this._getEntityTypeColors();
        return colors.get(entityType) || '#bca8ff';
    }

    _isEdgeDirected(edge) {
        if (typeof edge.is_directed === 'boolean') return edge.is_directed;
        const relType = edge.relationship_type || edge.type;
        const relationshipType = this._relationshipTypes.items.find((item) => item.type_id === relType);
        if (!relationshipType) return true;
        return relationshipType.is_directed !== false;
    }

    _incidentWeightSubtitle(sum) {
        if (typeof sum !== 'number' || !Number.isFinite(sum) || sum <= 0) return '';
        const value = sum.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 });
        return this.t('graph_page.incident_weight_subtitle', { value });
    }

    _onTimelineChange(event) {
        this._timelineStartPercent = event.detail.startPercent;
        this._timelineEndPercent = event.detail.endPercent;
        if (this._timelineReloadTimer) clearTimeout(this._timelineReloadTimer);
        this._timelineReloadTimer = setTimeout(() => {
            this._timelineReloadTimer = null;
            this._reloadAll();
        }, TIMELINE_RELOAD_DEBOUNCE_MS);
    }

    _onSearchInput(event) {
        this._entitySearchQuery = event.detail.query;
        if (this._searchDebounceTimer) clearTimeout(this._searchDebounceTimer);
        this._searchDebounceTimer = setTimeout(() => {
            this._searchDebounceTimer = null;
            this._rebuildGraphByMode();
        }, SEARCH_DEBOUNCE_MS);
    }

    _onSearchClear() {
        this._entitySearchQuery = '';
        if (this._searchDebounceTimer) {
            clearTimeout(this._searchDebounceTimer);
            this._searchDebounceTimer = null;
        }
        this._rebuildGraphByMode();
    }

    _onSearchSubmit() {
        if (this._searchDebounceTimer) {
            clearTimeout(this._searchDebounceTimer);
            this._searchDebounceTimer = null;
        }
        this._rebuildGraphByMode();
    }

    _onSearchModeChange(event) {
        this._searchMode = event.detail.mode;
        if (this._entitySearchQuery.trim().length > 0) this._rebuildGraphByMode();
    }

    _onMinScoreChange(event) {
        this._minScore = event.detail.minScore;
        if (this._entitySearchQuery.trim().length > 0) this._rebuildGraphByMode();
    }

    _onSearchRefresh() {
        this._reloadAll();
    }

    _onModeChange(event) {
        this._viewMode = event.detail.mode;
        if (this._viewMode !== 'influence') this._defaultOverviewActive = false;
        if (this._viewMode !== 'path') {
            this._canvasPathState = 'idle';
            this._canvasPathHint = this.t('graph_page.hint_browse');
        }
        this._rebuildGraphByMode();
    }

    _onCanvasNodeClick(event) {
        const node = event.detail.node;
        const nativeEvent = event.detail.event;
        if (!node || typeof node.id !== 'string') return;
        this._selectedNodeId = node.id;
        if (nativeEvent?.altKey) {
            this._openEntityModal(node.id);
            return;
        }
        if (nativeEvent?.shiftKey) {
            if (!this._mergeAnchorId) {
                this._mergeAnchorId = node.id;
                this.toast('crm:graph_page.merge_anchor_set', { type: 'info' });
                return;
            }
            if (this._mergeAnchorId === node.id) {
                this._mergeAnchorId = '';
                return;
            }
            this._openMergeModal(this._mergeAnchorId, node.id);
            this._mergeAnchorId = '';
            return;
        }
        if (this._canvasPathState === 'pick_source') {
            this._pathSourceId = node.id;
            this._pathTargetId = '';
            this._canvasPathState = 'pick_target';
            this._canvasPathHint = this.t('graph_page.hint_click_target');
            return;
        }
        if (this._canvasPathState === 'pick_target') {
            if (node.id === this._pathSourceId) {
                this._canvasPathHint = this.t('graph_page.hint_pick_other_target');
                this.toast('crm:graph_page.warn_source_target_same', { type: 'warning' });
                return;
            }
            this._pathTargetId = node.id;
            this._canvasPathState = 'built';
            this._buildPathGraph();
            return;
        }
    }

    _onCanvasNodeDblClick(event) {
        const canvas = this.renderRoot?.querySelector('crm-graph-canvas');
        if (canvas && event.detail.node) canvas.flyToNode(event.detail.node);
    }

    _onCanvasLinkClick(event) {
        const link = event.detail.link;
        this._selectedEdgeId = link && link.id ? link.id : '';
    }

    _onCanvasContextMenu(event) {
        this._showContextMenu(event.detail.screenX, event.detail.screenY, event.detail.node?.id || '', '');
    }

    _onCanvasClick() {
        this._hideContextMenu();
    }

    _showContextMenu(screenX, screenY, nodeId, edgeId) {
        const stage = this.renderRoot?.querySelector('.canvas-stage');
        if (!stage) return;
        const rect = stage.getBoundingClientRect();
        const x = Math.min(screenX - rect.left, rect.width - 180);
        const y = Math.min(screenY - rect.top, rect.height - 120);
        this._contextMenu = { x, y, nodeId, edgeId };
    }

    _hideContextMenu() {
        this._contextMenu = null;
    }

    _onContextAction(event) {
        const { action, nodeId } = event.detail;
        if (action === 'open-entity' && nodeId) {
            this._openEntityModal(nodeId);
        } else if (action === 'focus' && nodeId) {
            const canvas = this.renderRoot?.querySelector('crm-graph-canvas');
            if (canvas) canvas.flyToNode({ id: nodeId });
        } else if (action === 'path-from' && nodeId) {
            this._pathSourceId = nodeId;
            this._pathTargetId = '';
            this._viewMode = 'path';
            this._canvasPathState = 'pick_target';
            this._canvasPathHint = this.t('graph_page.hint_click_target');
        } else if (action === 'graph-from' && nodeId) {
            this._defaultOverviewActive = false;
            this._selectedRootId = nodeId;
            this._viewMode = 'influence';
            this._rebuildGraphByMode();
        }
        this._hideContextMenu();
    }

    _openEntityModal(entityId) {
        this.openModal('crm.entity', { mode: 'edit', id: entityId });
    }

    _openMergeModal(entityIdA, entityIdB) {
        this.openModal('crm.entity_merge', { entityIdA, entityIdB });
    }

    _onToolbarAction(event) {
        const actionId = event.detail.actionId;
        if (actionId === 'fit') {
            const canvas = this.renderRoot?.querySelector('crm-graph-canvas');
            if (canvas) canvas.fitToViewport();
            return;
        }
        if (actionId === 'path_mode') {
            this._canvasPathState = 'pick_source';
            this._canvasPathHint = this.t('graph_page.hint_click_source');
            this._viewMode = 'path';
            this._entitySearchQuery = '';
            this._shortestPathEdges = [];
            this._pathSourceId = '';
            this._pathTargetId = '';
            return;
        }
        if (actionId === 'swap_path') {
            if (!this._pathSourceId || !this._pathTargetId) return;
            const tmp = this._pathSourceId;
            this._pathSourceId = this._pathTargetId;
            this._pathTargetId = tmp;
            this._buildPathGraph();
            return;
        }
        if (actionId === 'reset_path') {
            this._canvasPathState = 'idle';
            this._canvasPathHint = this.t('graph_page.hint_browse');
            this._pathSourceId = '';
            this._pathTargetId = '';
            this._shortestPathEdges = [];
            this._rebuildGraphByMode();
            return;
        }
        if (actionId === 'depth_plus') {
            const next = Math.min(5, this._maxDepth + 1);
            if (next === this._maxDepth) return;
            this._maxDepth = next;
            this._rebuildGraphByMode();
            return;
        }
        if (actionId === 'depth_minus') {
            const next = Math.max(1, this._maxDepth - 1);
            if (next === this._maxDepth) return;
            this._maxDepth = next;
            this._rebuildGraphByMode();
            return;
        }
        if (actionId === 'filter_rel_type') {
            const types = this._relationshipTypes.items;
            if (this._relationshipTypeFilter.trim().length > 0) {
                this._relationshipTypeFilter = '';
                this._rebuildGraphByMode();
                return;
            }
            if (types.length === 0) return;
            const selectedEdge = this._graphEdges.find((edge) => _getEdgeId(edge) === this._selectedEdgeId);
            if (selectedEdge && selectedEdge.relationship_type) {
                this._relationshipTypeFilter = selectedEdge.relationship_type;
            } else {
                this._relationshipTypeFilter = types[0].type_id;
            }
            this._rebuildGraphByMode();
            return;
        }
        if (actionId === 'labels_mode') {
            this._labelMode = this._labelMode === 'adaptive' ? 'minimal' : 'adaptive';
            return;
        }
        if (actionId === 'reset_view') {
            this._entitySearchQuery = '';
            this._timelineStartPercent = 0;
            this._timelineEndPercent = 100;
            this._relationshipTypeFilter = '';
            this._viewMode = 'influence';
            this._defaultOverviewActive = true;
            this._canvasPathState = 'idle';
            this._canvasPathHint = this.t('graph_page.hint_browse');
            this._shortestPathEdges = [];
            this._reloadAll();
            return;
        }
        if (actionId === 'merge_entities') {
            if (!this._mergeAnchorId || !this._selectedNodeId) {
                this.toast('crm:graph_page.merge_need_pair', { type: 'warning' });
                return;
            }
            if (this._mergeAnchorId === this._selectedNodeId) {
                this.toast('crm:graph_page.merge_same_node', { type: 'warning' });
                return;
            }
            this._openMergeModal(this._mergeAnchorId, this._selectedNodeId);
            this._mergeAnchorId = '';
            return;
        }
    }

    _onPanelToggle(event) {
        const panelId = event.detail.panelId;
        if (!PANEL_IDS.includes(panelId)) return;
        const next = { ...this._panelVisibility, [panelId]: !this._panelVisibility[panelId] };
        this._panelVisibility = next;
        _persistPanelVisibility(next);
    }

    _onGoToImport() {
        this.navigate('namespace_imports');
    }

    render() {
        const isEmpty = this._graphNodes.length === 0;
        const isFiltered = this._timelineStartPercent > 0
            || this._timelineEndPercent < 100
            || this._entitySearchQuery.trim().length > 0
            || this._relationshipTypeFilter.trim().length > 0;
        const entityTypeColors = this._getEntityTypeColors();
        const relTypeColors = this._getRelationshipTypeColors();

        const toolbarActions = [
            { id: 'fit', label: this.t('graph_page.toolbar_fit') },
            { id: 'path_mode', label: this.t('graph_page.toolbar_path_mode') },
            { id: 'swap_path', label: this.t('graph_page.toolbar_swap') },
            { id: 'reset_path', label: this.t('graph_page.toolbar_reset_path') },
            { id: 'depth_plus', label: this.t('graph_page.toolbar_depth_plus') },
            { id: 'depth_minus', label: this.t('graph_page.toolbar_depth_minus') },
            { id: 'filter_rel_type', label: this.t('graph_page.toolbar_filter_rel_type') },
            { id: 'labels_mode', label: this.t('graph_page.toolbar_labels_mode') },
            { id: 'reset_view', label: this.t('graph_page.toolbar_reset_view') },
            { id: 'merge_entities', label: this.t('graph_page.toolbar_merge') },
        ];
        const toolbarToggles = [
            { id: 'search', label: this.t('graph_page.panel_toggle_search'), active: this._panelVisibility.search },
            { id: 'timeline', label: this.t('graph_page.panel_toggle_timeline'), active: this._panelVisibility.timeline },
            { id: 'legend', label: this.t('graph_page.panel_toggle_legend'), active: this._panelVisibility.legend },
            { id: 'meta', label: this.t('graph_page.panel_toggle_meta'), active: this._panelVisibility.meta },
        ];

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <div class="canvas-stage" @click=${this._onCanvasClick}>
                <crm-graph-canvas
                    .graphNodes=${this._graphNodes}
                    .graphEdges=${this._graphEdges}
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
                    .incidentWeightSubtitleFn=${(sum) => this._incidentWeightSubtitle(sum)}
                    @node-click=${this._onCanvasNodeClick}
                    @node-dblclick=${this._onCanvasNodeDblClick}
                    @node-contextmenu=${this._onCanvasContextMenu}
                    @link-click=${this._onCanvasLinkClick}
                    @canvas-click=${this._onCanvasClick}
                ></crm-graph-canvas>

                <crm-graph-search-pill
                    class=${this._panelVisibility.search ? '' : 'panel-hidden'}
                    .query=${this._entitySearchQuery}
                    .viewMode=${this._viewMode}
                    .modes=${VIEW_MODES}
                    .searchMode=${this._searchMode}
                    .minScore=${this._minScore}
                    @search-input=${this._onSearchInput}
                    @search-clear=${this._onSearchClear}
                    @search-submit=${this._onSearchSubmit}
                    @search-mode-change=${this._onSearchModeChange}
                    @min-score-change=${this._onMinScoreChange}
                    @mode-change=${this._onModeChange}
                    @refresh=${this._onSearchRefresh}
                ></crm-graph-search-pill>

                ${this._panelVisibility.timeline ? html`
                    <crm-graph-timeline
                        .minTimestamp=${this._timelineMinTimestamp}
                        .maxTimestamp=${this._timelineMaxTimestamp}
                        .startPercent=${this._timelineStartPercent}
                        .endPercent=${this._timelineEndPercent}
                        @timeline-change=${this._onTimelineChange}
                    ></crm-graph-timeline>
                ` : nothing}

                ${this._panelVisibility.meta ? html`
                    <div class="overlay-meta">
                        <span class="meta-pill">${this.t('graph_page.meta_mode')} ${this._viewMode}</span>
                        <span class="meta-pill">${this.t('graph_page.meta_depth')} ${this._maxDepth}</span>
                        <span class="meta-pill">${this.t('graph_page.meta_nodes')} ${this._graphNodes.length}</span>
                        <span class="meta-pill">${this.t('graph_page.meta_edges')} ${this._graphEdges.length}</span>
                    </div>
                ` : nothing}

                <crm-graph-toolbar
                    .actions=${toolbarActions}
                    .toggles=${toolbarToggles}
                    .labelMode=${this._labelMode}
                    @toolbar-action=${this._onToolbarAction}
                    @panel-toggle=${this._onPanelToggle}
                ></crm-graph-toolbar>

                ${this._panelVisibility.legend ? html`
                    <crm-graph-legend
                        .nodes=${this._graphNodes}
                        .entityTypeColors=${entityTypeColors}
                        .canvasHint=${this._canvasPathHint}
                        .selectedNodeId=${this._selectedNodeId}
                        .selectedEdgeId=${this._selectedEdgeId}
                    ></crm-graph-legend>
                ` : nothing}

                ${this._loading ? html`
                    <div class="loading-overlay">
                        <glass-spinner size="14"></glass-spinner>
                        <span>${this.t('graph.loading')}</span>
                    </div>
                ` : nothing}

                ${isEmpty && isFiltered ? html`
                    <div class="empty-search-state">${this.t('graph_page.empty_search')}</div>
                ` : nothing}

                ${isEmpty && !isFiltered && !this._loading ? html`
                    <div class="graph-empty-import-cta">
                        <span>${this.t('graph_page.empty_import_hint')}</span>
                        <button type="button" @click=${this._onGoToImport}>
                            ${this.t('graph_page.empty_import_cta')}
                        </button>
                    </div>
                ` : nothing}

                <crm-graph-context-menu
                    .x=${this._contextMenu ? this._contextMenu.x : 0}
                    .y=${this._contextMenu ? this._contextMenu.y : 0}
                    .nodeId=${this._contextMenu ? this._contextMenu.nodeId : ''}
                    .edgeId=${this._contextMenu ? this._contextMenu.edgeId : ''}
                    .visible=${this._contextMenu !== null}
                    @ctx-action=${this._onContextAction}
                ></crm-graph-context-menu>
            </div>
        `;
    }
}

customElements.define('crm-graph-page', CRMGraphPage);
