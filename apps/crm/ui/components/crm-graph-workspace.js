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
 *   - Query `?root=<entity_id>` на маршруте `graph` — сразу корень influence,
 *     без overview-пресета (мини-превью «Открыть полностью»).
 *   - useOp('crm/overview_graph')             — overview по списку сущностей и
 *     по результатам entitySearchOp;
 *   - useOp('crm/influence_graph')            — influence по выбранному корню;
 *   - useOp('crm/related_entities')           — окружение корня;
 *   - useOp('crm/entity_relationships')       — рёбра в режиме related;
 *   - useOp('crm/shortest_path')              — кратчайший путь;
 *   - useOp('crm/entity_search')              — поиск по запросу.
 *
 * UI-команды (модалки, тосты, навигация) — только через helpers базы
 * (`openModal`, `toast`, `navigate`). Никаких прямых dispatch UI/ROUTER/AUTH,
 * httpRequest, fetch, services.* / store / features.
 *
 * Live-обновления — полный набор push-событий для обоих canvas-view.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { selectCrmApiNamespace, crmNamespaceForOptionalQuery } from '../utils/crm-namespace-select.js';
import { clampTimelinePercents } from '../utils/crm-timeline-range.js';
import { buildRelationshipTypeLabelMapFromItems } from '../utils/crm-relationship-type-labels.js';
import {
    buildGraphWorkspaceSearch,
    parseGraphWorkspaceQuery,
} from '../utils/graph-view-mode.js';
import {
    buildEntityTypeColorMapFromItems,
    buildEntityTypeIconMapFromItems,
} from '../utils/crm-entity-type-visuals.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import './graph-canvas.js';
import './mindmap-canvas.js';
import './graph-search-pill.js';
import './graph-timeline.js';
import './graph-toolbar.js';
import './graph-legend.js';
import './graph-context-menu.js';

const VIEW_MODES = ['influence', 'related', 'path'];
const PANEL_IDS = ['search', 'timeline', 'legend', 'meta'];
const SEARCH_DEBOUNCE_MS = 400;
const TIMELINE_RELOAD_DEBOUNCE_MS = 220;

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

export class CRMGraphWorkspace extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        _canvasView: { state: true },
        _graphDataMode: { state: true },
        _mindmapErrorKey: { state: true },
        _rootLabelMindmap: { state: true },
        _fitNonce: { state: true },
        _highlightNodeIds: { state: true },
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
        PlatformElement.styles,
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

            crm-graph-canvas,
            crm-mindmap-canvas {
                position: absolute;
                inset: 0;
                z-index: 0;
            }

            .mindmap-overlay-title {
                position: absolute;
                z-index: 12;
                top: 20px;
                left: 20px;
                max-width: min(420px, calc(100% - 120px));
                padding: 12px 14px;
                border-radius: 14px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                backdrop-filter: blur(8px);
                pointer-events: none;
                color: var(--text-primary);
            }

            .mindmap-overlay-title h2 {
                margin: 0;
                font-size: var(--text-sm);
                font-weight: 700;
                letter-spacing: 0.02em;
            }

            .mindmap-overlay-title .root-line {
                margin-top: 6px;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .state-overlay {
                position: absolute;
                inset: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-4);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                text-align: center;
                z-index: 18;
                pointer-events: none;
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
                top: 50%;
                left: 16px;
                transform: translateY(-50%);
                max-height: calc(100% - 32px);
            }

            crm-graph-toolbar {
                position: absolute;
                top: 72px;
                right: 16px;
                z-index: 14;
                --graph-toolbar-max-height-slop: 88px;
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
                .canvas-stage { min-height: 0; }
                crm-graph-search-pill { top: 8px; left: 8px; }
                crm-graph-timeline {
                    top: 50%;
                    left: 8px;
                    transform: translateY(-50%);
                    max-height: calc(100% - 16px);
                }
                crm-graph-toolbar {
                    top: 8px;
                    right: 8px;
                    --graph-toolbar-max-height-slop: 24px;
                }
                crm-graph-legend { left: 8px; bottom: 8px; }
                .overlay-meta { display: none; }
            }
        `,
    ];

    constructor() {
        super();
        this._canvasView = 'mindmap';
        this._mindmapErrorKey = '';
        this._rootLabelMindmap = '';
        this._fitNonce = 0;
        this._highlightNodeIds = [];
        this._pendingSearchFocusId = '';
        this._graphDataMode = 'influence';
        this._selectedRootId = '';
        this._maxDepth = 4;
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
        this._crmNamespaceSel = this.select(selectCrmApiNamespace);
        this._routerSel = this.select((s) => ({
            routeKey: s.router.routeKey,
            params: s.router.params,
            search: s.router.search,
        }));

        this._graphUi = this.useSlice('crm/graph_ui');
        this._graphView = this.useSlice('crm/graph_view');
        this._entityTypes = this.useResource('crm/entity_types', { autoload: false });
        this._relationshipTypes = this.useResource('crm/relationship_types', { autoload: true });
        this._timelineBoundsOp = this.useOp('crm/timeline_bounds');
        this._entitiesLookupOp = this.useOp('crm/entities_lookup');
        this._overviewOp = this.useOp('crm/overview_graph');
        this._influenceOp = this.useOp('crm/influence_graph');
        this._relatedOp = this.useOp('crm/related_entities');
        this._entityRelOp = this.useOp('crm/entity_relationships');
        this._shortestPathOp = this.useOp('crm/shortest_path');
        this._entitySearchOp = this.useOp('crm/entity_search');
        this._personOp = this.useOp('crm/person_entity_self');
    }

    connectedCallback() {
        super.connectedCallback();
        this._canvasPathHint = this.t('graph_page.hint_browse');

        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => {
            this._onGraphRouterChanged();
        });

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

        this._bootstrapGraphWorkspaceFromRouter();
        this._normalizeBareGraphUrl();
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

    /**
     * @param {unknown} searchRaw
     * @returns {string | null}
     */
    _readGraphRootFromSearch(searchRaw) {
        const parsed = parseGraphWorkspaceQuery(typeof searchRaw === 'string' ? searchRaw : '');
        return parsed.root;
    }

    _bootstrapGraphWorkspaceFromRouter() {
        const r = this._routerSel.value;
        if (typeof r.routeKey !== 'string' || r.routeKey !== 'graph') {
            return;
        }
        const rawSearch = typeof r.search === 'string' ? r.search : '';
        const parsed = parseGraphWorkspaceQuery(rawSearch);
        this._canvasView = parsed.view;
        const gv = this._graphView.value;
        if (parsed.view !== gv.viewMode) {
            this._graphView.setViewMode({ viewMode: parsed.view });
        }
        if (parsed.depth !== null) {
            this._maxDepth = parsed.depth;
            if (parsed.depth !== gv.maxDepth) {
                this._graphView.setMaxDepth({ maxDepth: parsed.depth });
            }
        } else {
            this._maxDepth = gv.maxDepth;
        }
        const si = gv.searchInput;
        if (parsed.query.length > 0) {
            this._entitySearchQuery = parsed.query;
        } else {
            this._entitySearchQuery = si.query;
            this._searchMode = si.mode;
            this._minScore = si.minScore;
        }
        if (parsed.root !== null) {
            this._selectedRootId = parsed.root;
            this._defaultOverviewActive = false;
        }
    }

    _normalizeBareGraphUrl() {
        const r = this._routerSel.value;
        if (typeof r.routeKey !== 'string' || r.routeKey !== 'graph') {
            return;
        }
        const raw = typeof r.search === 'string' ? r.search : '';
        if (raw !== '' && raw !== '?') {
            return;
        }
        const gv = this._graphView.value.viewMode;
        const root =
            typeof this._selectedRootId === 'string' && this._selectedRootId.trim().length > 0
                ? this._selectedRootId.trim()
                : null;
        const s = buildGraphWorkspaceSearch({
            view: gv,
            root,
            depth: this._maxDepth,
            query: this._entitySearchQuery,
        });
        this.navigate('graph', {}, { search: s, replace: true });
    }

    _onGraphRouterChanged() {
        const r = this._routerSel.value;
        if (typeof r.routeKey !== 'string' || r.routeKey !== 'graph') {
            return;
        }
        const parsed = parseGraphWorkspaceQuery(typeof r.search === 'string' ? r.search : '');
        let dirty = false;
        if (parsed.view !== this._canvasView) {
            this._canvasView = parsed.view;
            this._graphView.setViewMode({ viewMode: parsed.view });
            dirty = true;
        }
        if (parsed.depth !== null && parsed.depth !== this._maxDepth) {
            this._maxDepth = parsed.depth;
            this._graphView.setMaxDepth({ maxDepth: parsed.depth });
            dirty = true;
        }
        if (parsed.root !== null && parsed.root !== this._selectedRootId) {
            this._selectedRootId = parsed.root;
            this._defaultOverviewActive = false;
            dirty = true;
        }
        if (parsed.query !== this._entitySearchQuery) {
            this._entitySearchQuery = parsed.query;
            dirty = true;
        }
        if (dirty) {
            this._rebuildGraphByMode();
        }
    }

    _syncGraphLocationSearch() {
        const r = this._routerSel.value;
        if (typeof r.routeKey !== 'string' || r.routeKey !== 'graph') {
            return;
        }
        const rootRaw = this._selectedRootId;
        const root =
            typeof rootRaw === 'string' && rootRaw.trim().length > 0 ? rootRaw.trim() : null;
        const s = buildGraphWorkspaceSearch({
            view: this._canvasView,
            root,
            depth: this._maxDepth,
            query: this._entitySearchQuery,
        });
        this.navigate('graph', {}, { search: s, replace: true });
    }

    /**
     * @param {unknown} graph
     * @param {string} rootId
     * @returns {string}
     */
    _rootLabelFromGraph(graph, rootId) {
        const nodes = graph && Array.isArray(graph.nodes) ? graph.nodes : [];
        for (const raw of nodes) {
            if (!raw || typeof raw !== 'object') {
                continue;
            }
            const idRaw = raw.entity_id !== undefined ? raw.entity_id : raw.id;
            const id = typeof idRaw === 'string' ? idRaw.trim() : '';
            if (id !== rootId) {
                continue;
            }
            const nameRaw = raw.name !== undefined ? raw.name : raw.label;
            if (typeof nameRaw === 'string' && nameRaw.trim().length > 0) {
                return nameRaw.trim();
            }
            return rootId;
        }
        return rootId;
    }

    /**
     * @returns {string}
     */
    _mindmapErrorBannerText() {
        const k = this._mindmapErrorKey;
        if (k.length === 0) {
            return '';
        }
        if (k === 'mindmap.err_person') {
            return this.t('mindmap.err_person');
        }
        if (k === 'mindmap.err_invalid_root') {
            return this.t('mindmap.err_invalid_root');
        }
        if (k === 'mindmap.err_graph') {
            return this.t('mindmap.err_graph');
        }
        if (k === 'mindmap.empty') {
            return this.t('mindmap.empty');
        }
        throw new Error('CRMGraphWorkspace: unknown mindmap error key');
    }

    updated(changed) {
        super.updated(changed);
    }

    _currentNamespace() {
        return this._crmNamespaceSel.value;
    }

    _reloadAll() {
        this._loading = true;
        const namespace = this._currentNamespace();
        this._lastNamespaceLoaded = namespace;
        const nq = crmNamespaceForOptionalQuery(namespace);
        this._entityTypes.load({ namespace: nq });
        this._timelineBoundsOp.run({ namespace: nq });
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
            this._timelineStartPercent = 0;
            this._timelineEndPercent = 100;
        }
        const namespace = this._currentNamespace();
        const timelineParams = this._getTimelineQueryParams();
        const nq = crmNamespaceForOptionalQuery(namespace);
        this._entitiesLookupOp.run({
            namespace: nq,
            limit: 120,
            ...timelineParams,
        });
    }

    async _onEntitiesLookupLoaded(response) {
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

        if (this._canvasView === 'mindmap') {
            this._mindmapErrorKey = '';
            let rootId = this._readGraphRootFromSearch(this._routerSel.value.search);
            if (rootId === null) {
                const person = await this._personOp.run(null);
                if (person === null) {
                    this._loading = false;
                    this._mindmapErrorKey = 'mindmap.err_person';
                    return;
                }
                if (!person || typeof person !== 'object') {
                    throw new Error('CRMGraphWorkspace: person_entity_self invalid response');
                }
                const entityIdRaw = person.entity_id !== undefined ? person.entity_id : person.id;
                const entityId = typeof entityIdRaw === 'string' ? entityIdRaw.trim() : '';
                if (entityId.length === 0) {
                    throw new Error('CRMGraphWorkspace: person entity id missing');
                }
                rootId = entityId;
            }
            this._selectedRootId = rootId;
            this._defaultOverviewActive = false;
            this._rootLabelMindmap = rootId;
            if (!this._pathSourceId && items.length > 0) {
                this._pathSourceId = this._selectedRootId;
            }
            if (!this._pathTargetId && items.length > 1) {
                const target = items.find((entity) => entity.entity_id !== this._pathSourceId);
                this._pathTargetId = target ? target.entity_id : items[0].entity_id;
            }
            this._rebuildGraphByMode();
            return;
        }

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
            if (this._canvasView === 'mindmap') {
                this._mindmapErrorKey = 'mindmap.err_graph';
            }
            return;
        }
        this._graphNodes = Array.isArray(response.nodes) ? response.nodes : [];
        this._graphEdges = Array.isArray(response.edges) ? response.edges : [];
        this._shortestPathEdges = [];
        this._loading = false;
        if (this._canvasView === 'mindmap') {
            const rid = typeof this._selectedRootId === 'string' ? this._selectedRootId.trim() : '';
            if (rid.length > 0) {
                this._rootLabelMindmap = this._rootLabelFromGraph(response, rid);
            }
            if (this._graphNodes.length === 0) {
                this._mindmapErrorKey = 'mindmap.empty';
            } else {
                this._mindmapErrorKey = '';
            }
        }
        const pending = this._pendingSearchFocusId;
        if (typeof pending === 'string' && pending.length > 0) {
            this._pendingSearchFocusId = '';
            const nodeHit = this._graphNodes.some((n) => {
                if (!n || typeof n !== 'object') {
                    return false;
                }
                const eid = n.entity_id !== undefined ? n.entity_id : n.id;
                return typeof eid === 'string' && eid.trim() === pending;
            });
            if (nodeHit) {
                this._selectedNodeId = pending;
                this._highlightNodeIds = [pending];
                queueMicrotask(() => {
                    const mm = this.renderRoot?.querySelector('crm-mindmap-canvas');
                    if (mm && this._canvasView === 'mindmap' && typeof mm.expandToNode === 'function') {
                        mm.expandToNode(pending);
                    }
                    if (mm && this._canvasView === 'mindmap' && typeof mm.flyToNode === 'function') {
                        mm.flyToNode(pending);
                    }
                    const c = this.renderRoot?.querySelector('crm-graph-canvas');
                    if (c && this._canvasView === '3d' && typeof c.flyToNode === 'function') {
                        c.flyToNode({ id: pending });
                    }
                });
            }
        }
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
        const nq = crmNamespaceForOptionalQuery(namespace);
        this._entityRelOp.run({
            entityId: this._selectedRootId,
            params: { namespace: nq },
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
        // Порог min score действует только для узлов с числовым score из поиска; узлы без score не трактуем как 0.
        const items = this._minScore > 0
            ? all.filter((entry) => {
                if (typeof entry.score !== 'number') {
                    return true;
                }
                return entry.score >= this._minScore;
            })
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
        const focusId = entityIds.length > 0 ? entityIds[0] : '';
        this._pendingSearchFocusId = typeof focusId === 'string' ? focusId : '';
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
        if (this._canvasView === 'mindmap') {
            this._defaultOverviewActive = false;
        }
        if (this._entitySearchQuery.trim().length > 0) {
            this._executeSearch();
            return;
        }
        if (this._graphDataMode === 'influence' && this._defaultOverviewActive) {
            this._buildOverviewGraph();
            return;
        }
        if (!this._selectedRootId) {
            this._graphNodes = [];
            this._graphEdges = [];
            this._loading = false;
            return;
        }
        if (this._graphDataMode === 'influence') {
            this._buildInfluenceGraph();
            return;
        }
        if (this._graphDataMode === 'related') {
            this._buildRelatedGraph();
            return;
        }
        if (this._graphDataMode === 'path') {
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
        const d = event.detail;
        let sp = d && typeof d.startPercent === 'number' ? d.startPercent : this._timelineStartPercent;
        let ep = d && typeof d.endPercent === 'number' ? d.endPercent : this._timelineEndPercent;
        if (this._timelineMinTimestamp > 0 && this._timelineMaxTimestamp > this._timelineMinTimestamp) {
            const c = clampTimelinePercents(sp, ep, this._timelineMinTimestamp, this._timelineMaxTimestamp);
            sp = c.startPercent;
            ep = c.endPercent;
        }
        this._timelineStartPercent = sp;
        this._timelineEndPercent = ep;
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
        this._graphDataMode = event.detail.mode;
        if (this._graphDataMode !== 'influence') this._defaultOverviewActive = false;
        if (this._graphDataMode !== 'path') {
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

    _applyGraphFromNode(nodeId) {
        const id = typeof nodeId === 'string' ? nodeId.trim() : '';
        if (id.length === 0) {
            throw new Error('CRMGraphWorkspace._applyGraphFromNode: nodeId required');
        }
        this._defaultOverviewActive = false;
        this._selectedRootId = id;
        this._graphDataMode = 'influence';
        this._entitySearchQuery = '';
        if (this._searchDebounceTimer) {
            clearTimeout(this._searchDebounceTimer);
            this._searchDebounceTimer = null;
        }
        const si = this._graphView.value.searchInput;
        this._graphView.setSearchInput({
            searchInput: {
                query: '',
                mode: si.mode,
                minScore: si.minScore,
            },
        });
        this._selectedNodeId = id;
        this._syncGraphLocationSearch();
        this._rebuildGraphByMode();
    }

    _onContextAction(event) {
        const { action, nodeId } = event.detail;
        if (action === 'open-entity' && nodeId) {
            this._openEntityModal(nodeId);
        } else if (action === 'focus' && nodeId) {
            if (this._canvasView === 'mindmap') {
                const mm = this.renderRoot?.querySelector('crm-mindmap-canvas');
                if (mm && typeof mm.expandToNode === 'function') {
                    mm.expandToNode(nodeId);
                }
                if (mm && typeof mm.flyToNode === 'function') {
                    mm.flyToNode(nodeId);
                }
            } else {
                const canvas = this.renderRoot?.querySelector('crm-graph-canvas');
                if (canvas) canvas.flyToNode({ id: nodeId });
            }
        } else if (action === 'path-from' && nodeId) {
            this._pathSourceId = nodeId;
            this._pathTargetId = '';
            this._graphDataMode = 'path';
            this._canvasPathState = 'pick_target';
            this._canvasPathHint = this.t('graph_page.hint_click_target');
        } else if (action === 'graph-from' && nodeId) {
            this._applyGraphFromNode(nodeId);
        }
        this._hideContextMenu();
    }

    _onMindmapNodeClick(event) {
        const d = event.detail;
        const node = d && d.node;
        const nativeEvent = d && d.event;
        if (!node || typeof node.id !== 'string') {
            return;
        }
        const id = node.id.trim();
        if (id.length === 0) {
            return;
        }
        if (nativeEvent && (nativeEvent.altKey || nativeEvent.shiftKey)) {
            this._onCanvasNodeClick({ detail: { node: { id }, event: nativeEvent } });
            return;
        }
        if (this._graphDataMode === 'path'
            && (this._canvasPathState === 'pick_source' || this._canvasPathState === 'pick_target')) {
            this._onCanvasNodeClick({ detail: { node: { id }, event: nativeEvent } });
            return;
        }
        if (nativeEvent && typeof nativeEvent.detail === 'number' && nativeEvent.detail > 1) {
            return;
        }
        this._applyGraphFromNode(id);
    }

    _onMindmapNodeDblClick(event) {
        const node = event.detail && event.detail.node;
        if (!node || typeof node.id !== 'string') {
            return;
        }
        const mm = this.renderRoot?.querySelector('crm-mindmap-canvas');
        if (mm && typeof mm.flyToNode === 'function') {
            mm.flyToNode(node.id);
        }
    }

    _onMindmapNodeContextMenu(event) {
        const d = event.detail;
        const node = d && d.node;
        const id = node && typeof node.id === 'string' ? node.id : '';
        const sx = typeof d.screenX === 'number' ? d.screenX : 0;
        const sy = typeof d.screenY === 'number' ? d.screenY : 0;
        this._showContextMenu(sx, sy, id, '');
    }

    _onCanvasViewFromToolbar(event) {
        const d = event.detail;
        const v = d && d.canvasView;
        if (v !== '3d' && v !== 'mindmap') {
            return;
        }
        if (v === this._canvasView) {
            return;
        }
        this._canvasView = v;
        this._graphView.setViewMode({ viewMode: v });
        this._syncGraphLocationSearch();
        this._reloadAll();
    }

    _openEntityModal(entityId) {
        this.navigate('entity', { itemId: entityId }, { search: '?edit=1' });
    }

    _openMergeModal(entityIdA, entityIdB) {
        this.openModal('crm.entity_merge', { entityIdA, entityIdB });
    }

    _onToolbarAction(event) {
        const actionId = event.detail.actionId;
        if (actionId === 'fit') {
            if (this._canvasView === 'mindmap') {
                this._fitNonce += 1;
                return;
            }
            const canvas = this.renderRoot?.querySelector('crm-graph-canvas');
            if (canvas) canvas.fitToViewport();
            return;
        }
        if (actionId === 'path_mode') {
            this._canvasPathState = 'pick_source';
            this._canvasPathHint = this.t('graph_page.hint_click_source');
            this._graphDataMode = 'path';
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
            this._graphView.setMaxDepth({ maxDepth: next });
            this._syncGraphLocationSearch();
            this._rebuildGraphByMode();
            return;
        }
        if (actionId === 'depth_minus') {
            const next = Math.max(1, this._maxDepth - 1);
            if (next === this._maxDepth) return;
            this._maxDepth = next;
            this._graphView.setMaxDepth({ maxDepth: next });
            this._syncGraphLocationSearch();
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
            this._graphDataMode = 'influence';
            this._defaultOverviewActive = this._canvasView !== 'mindmap';
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
        const cur = this._graphUi.value.panels;
        const next = { ...cur, [panelId]: !cur[panelId] };
        this._graphUi.setPanels({ panels: next });
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
        const relationshipLabelsPlain = buildRelationshipTypeLabelMapFromItems(this._relationshipTypes.items);
        const entityTypeColorsMap = buildEntityTypeColorMapFromItems(this._entityTypes.items);
        const entityTypeIconsMap = buildEntityTypeIconMapFromItems(this._entityTypes.items);
        const colorsPlain = Object.fromEntries(entityTypeColorsMap);
        const iconsPlain = Object.fromEntries(entityTypeIconsMap);

        const pathActions = [
            { id: 'path_mode', label: this.t('graph_page.toolbar_path_mode') },
            { id: 'swap_path', label: this.t('graph_page.toolbar_swap') },
            { id: 'reset_path', label: this.t('graph_page.toolbar_reset_path') },
        ];
        const labelsAction = { id: 'labels_mode', label: this.t('graph_page.toolbar_labels_mode') };
        const toolbarActions = [
            { id: 'fit', label: this.t('graph_page.toolbar_fit') },
            ...(this._canvasView === '3d' ? pathActions : []),
            { id: 'depth_plus', label: this.t('graph_page.toolbar_depth_plus') },
            { id: 'depth_minus', label: this.t('graph_page.toolbar_depth_minus') },
            { id: 'filter_rel_type', label: this.t('graph_page.toolbar_filter_rel_type') },
            ...(this._canvasView === '3d' ? [labelsAction] : []),
            { id: 'reset_view', label: this.t('graph_page.toolbar_reset_view') },
            { id: 'merge_entities', label: this.t('graph_page.toolbar_merge') },
        ];
        const toolbarToggles = [
            { id: 'search', label: this.t('graph_page.panel_toggle_search'), active: this._graphUi.value.panels.search },
            { id: 'timeline', label: this.t('graph_page.panel_toggle_timeline'), active: this._graphUi.value.panels.timeline },
            { id: 'legend', label: this.t('graph_page.panel_toggle_legend'), active: this._graphUi.value.panels.legend },
            { id: 'meta', label: this.t('graph_page.panel_toggle_meta'), active: this._graphUi.value.panels.meta },
        ];

        const rid = typeof this._selectedRootId === 'string' ? this._selectedRootId.trim() : '';
        const showMindmapCanvas =
            this._canvasView === 'mindmap'
            && this._mindmapErrorKey.length === 0
            && this._graphNodes.length > 0
            && rid.length > 0;

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <div class="canvas-stage" @click=${this._onCanvasClick}>
                ${this._canvasView === '3d'
                    ? html`
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
                              .relationshipTypeLabels=${relationshipLabelsPlain}
                              .incidentWeightSubtitleFn=${(sum) => this._incidentWeightSubtitle(sum)}
                              @node-click=${this._onCanvasNodeClick}
                              @node-dblclick=${this._onCanvasNodeDblClick}
                              @node-contextmenu=${this._onCanvasContextMenu}
                              @link-click=${this._onCanvasLinkClick}
                              @canvas-click=${this._onCanvasClick}
                          ></crm-graph-canvas>
                      `
                    : nothing}
                ${this._canvasView === 'mindmap' && showMindmapCanvas
                    ? html`
                          <crm-mindmap-canvas
                              .graphNodes=${this._graphNodes}
                              .graphEdges=${this._graphEdges}
                              .rootEntityId=${rid}
                              .entityTypeColors=${colorsPlain}
                              .entityTypeIcons=${iconsPlain}
                              .relationshipTypeLabels=${relationshipLabelsPlain}
                              defaultAccent="#6366f1"
                              .fitNonce=${this._fitNonce}
                              .selectedNodeId=${this._selectedNodeId}
                              .highlightNodeIds=${this._highlightNodeIds}
                              @node-click=${this._onMindmapNodeClick}
                              @node-dblclick=${this._onMindmapNodeDblClick}
                              @node-contextmenu=${this._onMindmapNodeContextMenu}
                              @link-click=${this._onCanvasLinkClick}
                              @canvas-click=${this._onCanvasClick}
                          ></crm-mindmap-canvas>
                      `
                    : nothing}

                ${this._canvasView === 'mindmap'
                    ? html`
                          <div class="mindmap-overlay-title">
                              <h2>${this.t('mindmap.overlay_title')}</h2>
                              <div class="root-line">${this._rootLabelMindmap}</div>
                          </div>
                      `
                    : nothing}

                <crm-graph-search-pill
                    class=${this._graphUi.value.panels.search ? '' : 'panel-hidden'}
                    .query=${this._entitySearchQuery}
                    .viewMode=${this._graphDataMode}
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

                ${this._graphUi.value.panels.timeline ? html`
                    <crm-graph-timeline
                        .minTimestamp=${this._timelineMinTimestamp}
                        .maxTimestamp=${this._timelineMaxTimestamp}
                        .startPercent=${this._timelineStartPercent}
                        .endPercent=${this._timelineEndPercent}
                        @timeline-change=${this._onTimelineChange}
                    ></crm-graph-timeline>
                ` : nothing}

                ${this._graphUi.value.panels.meta ? html`
                    <div class="overlay-meta">
                        <span class="meta-pill">${this.t('graph_page.meta_canvas')} ${this.t(`graph.view_mode_${this._canvasView}`)}</span>
                        <span class="meta-pill">${this.t('graph_page.meta_mode')} ${this.t(`graph.view_mode_${this._graphDataMode}`)}</span>
                        <span class="meta-pill">${this.t('graph_page.meta_depth')} ${this._maxDepth}</span>
                        <span class="meta-pill">${this.t('graph_page.meta_nodes')} ${this._graphNodes.length}</span>
                        <span class="meta-pill">${this.t('graph_page.meta_edges')} ${this._graphEdges.length}</span>
                    </div>
                ` : nothing}

                <crm-graph-toolbar
                    .actions=${toolbarActions}
                    .toggles=${toolbarToggles}
                    .labelMode=${this._labelMode}
                    .canvasView=${this._canvasView}
                    @view-mode-change=${this._onCanvasViewFromToolbar}
                    @toolbar-action=${this._onToolbarAction}
                    @panel-toggle=${this._onPanelToggle}
                ></crm-graph-toolbar>

                ${this._graphUi.value.panels.legend ? html`
                    <crm-graph-legend
                        .nodes=${this._graphNodes}
                        .entityTypeColors=${entityTypeColors}
                        .canvasHint=${this._canvasView === 'mindmap' ? this.t('mindmap.overlay_title') : this._canvasPathHint}
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

                ${this._canvasView === 'mindmap' && !this._loading && this._mindmapErrorKey.length > 0 ? html`
                    <div class="state-overlay">
                        <platform-icon name="alert" size="32"></platform-icon>
                        <span>${this._mindmapErrorBannerText()}</span>
                    </div>
                ` : nothing}

                ${isEmpty && isFiltered ? html`
                    <div class="empty-search-state">${this.t('graph_page.empty_search')}</div>
                ` : nothing}

                ${isEmpty && !isFiltered && !this._loading && this._canvasView === '3d' ? html`
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

customElements.define('crm-graph-workspace', CRMGraphWorkspace);
