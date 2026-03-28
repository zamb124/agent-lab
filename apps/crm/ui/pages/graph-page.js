import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { resolveObjectName } from '@platform/lib/utils/entity-ref.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

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
            }

            .toolbar-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .toolbar-select {
                min-width: 180px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .refresh-btn {
                padding: var(--space-2) var(--space-4);
                min-height: 36px;
                font-size: var(--text-sm);
                border-radius: var(--radius-md);
            }

            .toolbar-search {
                min-width: 220px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .stats {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
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

            .content {
                flex: 1;
                display: grid;
                grid-template-columns: 1fr 1fr;
                grid-template-rows: minmax(0, 1fr) auto;
                min-height: 0;
                gap: var(--space-3);
                padding: var(--space-4);
                overflow: auto;
            }

            .path-panel {
                grid-column: 1 / -1;
            }

            .path-toolbar {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }

            .path-select {
                min-width: 0;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .path-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .panel {
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                overflow: hidden;
                display: flex;
                flex-direction: column;
                min-height: 0;
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

            .panel-count {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                background: var(--crm-surface-tint-strong);
                border-radius: var(--radius-full);
                padding: var(--space-1) var(--space-2);
            }

            .panel-body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-2);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .node-item,
            .edge-item {
                display: grid;
                gap: var(--space-1);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
            }

            .node-item {
                cursor: pointer;
            }

            .node-item:hover {
                border-color: var(--crm-selected-stroke);
            }

            .node-name {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }

            .node-meta,
            .edge-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .edge-relation {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .empty {
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                gap: var(--space-2);
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-8);
            }

            @media (max-width: 1023px) {
                .content {
                    grid-template-columns: 1fr;
                    grid-template-rows: auto;
                }

                .stats {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }

            @media (max-width: 767px) {
                :host {
                    border: none;
                    border-radius: 0;
                }

                .toolbar {
                    padding: var(--space-3);
                }

                .stats {
                    padding: var(--space-3);
                    grid-template-columns: 1fr;
                }

                .content {
                    padding: var(--space-3);
                }

                .path-toolbar {
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
        this._maxDepth = 2;
        this._loading = false;
        this._graphNodes = [];
        this._graphEdges = [];
        this._pathSourceId = '';
        this._pathTargetId = '';
        this._shortestPathEdges = [];
        this._findingPath = false;
        this._entitySearchQuery = '';
    }

    async firstUpdated() {
        await this._loadGraphData();
    }

    async _loadGraphData() {
        this._loading = true;
        const crmApi = this.crmApi;
        const namespaceName = resolveObjectName(CRMStore.state.namespaces.current, null);
        const entities = await crmApi.getEntities({ namespace: namespaceName, limit: 200 });
        this._entities = Array.isArray(entities) ? entities : [];
        if (!this._selectedRootId && this._entities.length > 0) {
            const currentEntityId = CRMStore.state.entities.currentEntityId;
            this._selectedRootId = currentEntityId || this._entities[0].entity_id;
        }
        if (this._pathSourceId.length === 0 && this._entities.length > 0) {
            this._pathSourceId = this._selectedRootId || this._entities[0].entity_id;
        }
        if (this._pathTargetId.length === 0 && this._entities.length > 1) {
            const secondEntity = this._entities.find((entity) => entity.entity_id !== this._pathSourceId);
            this._pathTargetId = secondEntity ? secondEntity.entity_id : this._entities[0].entity_id;
        }
        await this._loadRelationshipsForFallback(namespaceName);
        await this._rebuildGraph();
        this._loading = false;
    }

    async _loadRelationshipsForFallback(namespaceName) {
        if (typeof this._selectedRootId !== 'string' || this._selectedRootId.trim().length === 0) {
            this._relationships = [];
            return;
        }
        const crmApi = this.crmApi;
        const response = await crmApi.getEntityRelationships(this._selectedRootId, { namespace: namespaceName });
        if (Array.isArray(response)) {
            this._relationships = response;
            return;
        }
        if (!response || typeof response !== 'object' || !Array.isArray(response.relationships)) {
            throw new Error('Entity relationships must be array');
        }
        this._relationships = response.relationships;
    }

    async _rebuildGraph() {
        if (!this._selectedRootId) {
            this._graphNodes = [];
            this._graphEdges = [];
            return;
        }

        const crmApi = this.crmApi;
        const influence = await crmApi.getInfluenceGraph(this._selectedRootId, { max_depth: this._maxDepth });
        const nodes = Array.isArray(influence.nodes) ? influence.nodes : [];
        const edges = Array.isArray(influence.edges) ? influence.edges : [];
        if (nodes.length === 0 && edges.length === 0) {
            const fallbackGraph = this._buildFallbackGraph();
            this._graphNodes = fallbackGraph.nodes;
            this._graphEdges = fallbackGraph.edges;
            return;
        }
        this._graphNodes = nodes;
        this._graphEdges = edges;
        this._relationships = edges;
    }

    _buildFallbackGraph() {
        const entityMap = new Map(this._entities.map((entity) => [entity.entity_id, entity]));
        const adjacency = new Map();
        for (const relationship of this._relationships) {
            if (!adjacency.has(relationship.source_entity_id)) {
                adjacency.set(relationship.source_entity_id, []);
            }
            if (!adjacency.has(relationship.target_entity_id)) {
                adjacency.set(relationship.target_entity_id, []);
            }
            adjacency.get(relationship.source_entity_id).push(relationship.target_entity_id);
            adjacency.get(relationship.target_entity_id).push(relationship.source_entity_id);
        }

        const queue = [{ id: this._selectedRootId, depth: 0 }];
        const visited = new Set([this._selectedRootId]);
        while (queue.length > 0) {
            const current = queue.shift();
            if (current.depth >= this._maxDepth) {
                continue;
            }
            const neighbors = adjacency.get(current.id) || [];
            for (const neighborId of neighbors) {
                if (visited.has(neighborId)) {
                    continue;
                }
                visited.add(neighborId);
                queue.push({ id: neighborId, depth: current.depth + 1 });
            }
        }

        const nodes = Array.from(visited)
            .map((entityId) => entityMap.get(entityId))
            .filter(Boolean);
        const edges = this._relationships.filter(
            (relationship) => visited.has(relationship.source_entity_id) && visited.has(relationship.target_entity_id),
        );
        return { nodes, edges };
    }

    async _onRootChange(event) {
        this._selectedRootId = event.target.value;
        const namespaceName = resolveObjectName(CRMStore.state.namespaces.current, null);
        await this._loadRelationshipsForFallback(namespaceName);
        await this._rebuildGraph();
    }

    async _onDepthChange(event) {
        this._maxDepth = Number(event.target.value);
        await this._rebuildGraph();
    }

    async _onRefresh() {
        await this._loadGraphData();
    }

    _onSearchQueryInput(event) {
        this._entitySearchQuery = event.target.value;
    }

    async _onSearchEntity() {
        const query = this._entitySearchQuery.trim();
        if (query.length === 0) {
            throw new Error('Search query is required');
        }
        const crmApi = this.crmApi;
        const namespaceName = resolveObjectName(CRMStore.state.namespaces.current, null);
        const response = await crmApi.searchEntities(query, { namespace: namespaceName, limit: 20 });
        const result = Array.isArray(response) ? response : response?.entities;
        if (!Array.isArray(result) || result.length === 0) {
            throw new Error('Search returned no entities');
        }
        const foundEntity = result[0];
        if (typeof foundEntity.entity_id !== 'string' || foundEntity.entity_id.trim().length === 0) {
            throw new Error('Search entity_id is required');
        }
        this._selectedRootId = foundEntity.entity_id;
        this._pathSourceId = foundEntity.entity_id;
        await this._loadRelationshipsForFallback(namespaceName);
        await this._rebuildGraph();
    }

    _onPathSourceChange(event) {
        this._pathSourceId = event.target.value;
    }

    _onPathTargetChange(event) {
        this._pathTargetId = event.target.value;
    }

    async _onFindShortestPath() {
        if (this._pathSourceId.length === 0 || this._pathTargetId.length === 0) {
            throw new Error('Both source and target entities are required');
        }
        if (this._pathSourceId === this._pathTargetId) {
            throw new Error('Source and target entities must be different');
        }
        this._findingPath = true;
        const crmApi = this.crmApi;
        const namespaceName = resolveObjectName(CRMStore.state.namespaces.current, null);
        try {
            const response = await crmApi.getShortestPath(this._pathSourceId, this._pathTargetId, {
                namespace: namespaceName,
            });
            if (!response || typeof response !== 'object') {
                throw new Error('Shortest path response must be object');
            }
            const candidateEdges = response.path_relationships || response.relationships || response.edges || response.path;
            if (!Array.isArray(candidateEdges)) {
                throw new Error('Shortest path relationships must be array');
            }
            this._shortestPathEdges = candidateEdges;
        } finally {
            this._findingPath = false;
        }
    }

    _onOpenEntity(entityId) {
        CRMStore.setCurrentView('entities');
        CRMStore.setCurrentEntity(entityId);
    }

    _resolveEntity(entityId) {
        return this._entities.find((entity) => entity.entity_id === entityId) || null;
    }

    _getRelationshipTypeConfig(typeId) {
        const relationshipTypes = CRMStore.state.entities.relationshipTypes;
        if (!Array.isArray(relationshipTypes)) {
            throw new Error('relationshipTypes must be array');
        }
        if (typeof typeId !== 'string' || typeId.trim().length === 0) {
            return null;
        }
        return relationshipTypes.find((item) => item?.type_id === typeId) || null;
    }

    _getRelationshipTypeLabel(typeId) {
        const config = this._getRelationshipTypeConfig(typeId);
        if (config && typeof config.name === 'string' && config.name.trim().length > 0) {
            return config.name.trim();
        }
        return typeId;
    }

    _getRelationshipArrow(typeId) {
        const config = this._getRelationshipTypeConfig(typeId);
        if (config && config.is_directed === false) {
            return '<->';
        }
        return '->';
    }

    _renderNodes() {
        if (this._graphNodes.length === 0) {
            return html`
                <div class="empty">
                    <platform-icon name="network" size="28"></platform-icon>
                    <div>Нет данных графа для выбранного узла</div>
                </div>
            `;
        }
        return this._graphNodes.map((node) => {
            const entityId = node.entity_id || node.id;
            const name = node.name || node.label || entityId;
            const type = node.entity_type || node.type || 'entity';
            return html`
                <button class="node-item" type="button" @click=${() => this._onOpenEntity(entityId)}>
                    <div class="node-name">${name}</div>
                    <div class="node-meta">${type}</div>
                </button>
            `;
        });
    }

    _renderEdges() {
        if (this._graphEdges.length === 0) {
            return html`
                <div class="empty">
                    <platform-icon name="circular-connection" size="28"></platform-icon>
                    <div>Связи пока не найдены</div>
                </div>
            `;
        }
        return this._graphEdges.map((edge) => {
            const sourceId = edge.source_entity_id || edge.source_id || edge.source;
            const targetId = edge.target_entity_id || edge.target_id || edge.target;
            const sourceEntity = this._resolveEntity(sourceId);
            const targetEntity = this._resolveEntity(targetId);
            const sourceName = sourceEntity?.name || sourceId;
            const targetName = targetEntity?.name || targetId;
            const relationType = edge.relationship_type || edge.type || 'related';
            const relationLabel = this._getRelationshipTypeLabel(relationType);
            const relationArrow = this._getRelationshipArrow(relationType);
            return html`
                <div class="edge-item">
                    <div class="edge-relation">${sourceName} ${relationArrow} ${targetName}</div>
                    <div class="edge-meta">${relationLabel}</div>
                </div>
            `;
        });
    }

    _renderShortestPathEdges() {
        if (this._shortestPathEdges.length === 0) {
            return html`
                <div class="empty">
                    <platform-icon name="route" size="24"></platform-icon>
                    <div>Путь не построен</div>
                </div>
            `;
        }
        return html`<div class="path-list">${this._shortestPathEdges.map((edge) => {
            const sourceId = edge.source_entity_id || edge.source_id || edge.source;
            const targetId = edge.target_entity_id || edge.target_id || edge.target;
            const sourceName = this._resolveEntity(sourceId)?.name || sourceId;
            const targetName = this._resolveEntity(targetId)?.name || targetId;
            const relationType = edge.relationship_type || edge.type || 'related';
            return html`
                <div class="edge-item">
                    <div class="edge-relation">${sourceName} ${this._getRelationshipArrow(relationType)} ${targetName}</div>
                    <div class="edge-meta">${this._getRelationshipTypeLabel(relationType)}</div>
                </div>
            `;
        })}</div>`;
    }

    render() {
        return html`
            <div class="toolbar">
                <div class="toolbar-title">
                    <platform-icon name="network" size="18"></platform-icon>
                    <span>Граф связей</span>
                </div>
                <div class="toolbar-control">
                    <span class="toolbar-label">Корневой узел</span>
                    <select class="toolbar-select" .value=${this._selectedRootId} @change=${this._onRootChange}>
                        ${this._entities.map((entity) => html`
                            <option value=${entity.entity_id}>${entity.name}</option>
                        `)}
                    </select>
                </div>
                <div class="toolbar-control">
                    <span class="toolbar-label">Глубина</span>
                    <select class="toolbar-select" .value=${String(this._maxDepth)} @change=${this._onDepthChange}>
                        <option value="1">1 уровень</option>
                        <option value="2">2 уровня</option>
                        <option value="3">3 уровня</option>
                        <option value="4">4 уровня</option>
                        <option value="5">5 уровней</option>
                    </select>
                </div>
                <button class="btn btn-secondary refresh-btn" type="button" @click=${this._onRefresh}>
                    Обновить
                </button>
                <input
                    class="toolbar-search"
                    type="text"
                    placeholder="Поиск сущности..."
                    .value=${this._entitySearchQuery}
                    @input=${this._onSearchQueryInput}
                />
                <button class="btn btn-secondary refresh-btn" type="button" @click=${this._onSearchEntity}>
                    Найти
                </button>
            </div>

            <div class="stats">
                <div class="stat-card">
                    <div class="stat-label">Сущностей</div>
                    <div class="stat-value">${this._entities.length}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Узлов в графе</div>
                    <div class="stat-value">${this._graphNodes.length}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Связей в графе</div>
                    <div class="stat-value">${this._graphEdges.length}</div>
                </div>
            </div>

            <div class="content">
                <section class="panel">
                    <div class="panel-header">
                        <div class="panel-title">Узлы</div>
                        <div class="panel-count">${this._graphNodes.length}</div>
                    </div>
                    <div class="panel-body">
                        ${this._loading ? html`<div class="empty">Загрузка графа...</div>` : this._renderNodes()}
                    </div>
                </section>

                <section class="panel">
                    <div class="panel-header">
                        <div class="panel-title">Связи</div>
                        <div class="panel-count">${this._graphEdges.length}</div>
                    </div>
                    <div class="panel-body">
                        ${this._loading ? html`<div class="empty">Загрузка связей...</div>` : this._renderEdges()}
                    </div>
                </section>

                <section class="panel path-panel">
                    <div class="panel-header">
                        <div class="panel-title">Кратчайший путь</div>
                        <div class="panel-count">${this._shortestPathEdges.length}</div>
                    </div>
                    <div class="panel-body">
                        <div class="path-toolbar">
                            <select class="path-select" .value=${this._pathSourceId} @change=${this._onPathSourceChange}>
                                ${this._entities.map((entity) => html`
                                    <option value=${entity.entity_id}>От: ${entity.name}</option>
                                `)}
                            </select>
                            <select class="path-select" .value=${this._pathTargetId} @change=${this._onPathTargetChange}>
                                ${this._entities.map((entity) => html`
                                    <option value=${entity.entity_id}>До: ${entity.name}</option>
                                `)}
                            </select>
                            <button
                                class="btn btn-secondary"
                                type="button"
                                ?disabled=${this._findingPath}
                                @click=${this._onFindShortestPath}
                            >
                                ${this._findingPath ? 'Поиск...' : 'Построить путь'}
                            </button>
                        </div>
                        ${this._renderShortestPathEdges()}
                    </div>
                </section>
            </div>
        `;
    }
}

customElements.define('graph-page', GraphPage);
