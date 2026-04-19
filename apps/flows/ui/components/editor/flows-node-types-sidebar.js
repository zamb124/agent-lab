/**
 * flows-node-types-sidebar — палитра типов нод и ресурсов для drag-into-canvas.
 *
 * Источники:
 *   - useOp('flows/node_types').lastResult — runtime-ноды с category
 *     (`core` | `tools` | `integrations` | `channels`).
 *   - useOp('flows/resource_types').lastResult — ресурсные типы (раздел «Ресурсы»).
 *   - useOp('flows/triggers_list').run({ flow_id }) — триггеры flow для
 *     отдельной секции в шапке сайдбара.
 *
 * Поиск фильтрует все категории + ресурсы (по name / description / type),
 * категории без совпадений скрываются.
 *
 * Drag: dataTransfer `application/x-flow-node-type` для нод и
 * `application/x-flow-resource-type` для ресурсов.
 *
 * UI-actions: клик по «+» в секции «Триггеры» — `this.openModal('flows.trigger_editor', { flowId })`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

const NODE_CATEGORY_ORDER = Object.freeze(['core', 'tools', 'integrations', 'channels']);

export class FlowsNodeTypesSidebar extends PlatformElement {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        _query: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 240px;
                flex-shrink: 0;
                padding: var(--space-3) var(--space-2);
                gap: var(--space-3);
                border-right: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                overflow-y: auto;
            }

            /* Триггеры */
            .triggers-section {
                display: flex; flex-direction: column; gap: var(--space-2);
                padding: 0 var(--space-2);
            }
            .triggers-header {
                display: flex; align-items: center; justify-content: space-between;
            }
            .triggers-title {
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--text-tertiary);
                font-weight: var(--font-semibold);
            }
            .add-btn {
                width: 22px; height: 22px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .add-btn:hover { background: var(--accent-subtle); color: var(--accent); border-color: var(--accent); }
            .triggers-empty {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2);
                text-align: center;
                border-radius: var(--radius-sm);
                background: var(--glass-solid-subtle);
            }
            .trigger-row {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2);
                border-radius: var(--radius-sm);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }

            /* Search */
            .search-box {
                position: relative;
                padding: 0 var(--space-2);
            }
            .search-box .search-icon {
                position: absolute;
                left: calc(var(--space-2) + 8px);
                top: 50%;
                transform: translateY(-50%);
                color: var(--text-tertiary);
                pointer-events: none;
            }
            .search-input {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-2) var(--space-2) calc(var(--space-2) + 22px);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
            }
            .search-input:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 2px var(--accent-subtle);
            }

            /* Категории */
            .category {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .category-header {
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--text-tertiary);
                font-weight: var(--font-semibold);
                padding: 0 var(--space-2);
                margin-bottom: 2px;
            }
            .category-divider {
                height: 1px;
                background: var(--border-subtle);
                margin: var(--space-2) var(--space-2);
            }
            .category-items {
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            /* Карточка типа */
            .node-item {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2);
                border-radius: var(--radius-sm);
                cursor: grab;
                transition: background var(--duration-fast);
            }
            .node-item:hover { background: var(--glass-solid-medium); }
            .node-item:active { cursor: grabbing; }
            .node-icon {
                width: 28px; height: 28px;
                flex-shrink: 0;
                border-radius: var(--radius-sm);
                display: flex; align-items: center; justify-content: center;
            }
            .node-name {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }
            .empty-row {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2);
                text-align: center;
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this._query = '';
        this._nodeTypesOp = this.useOp('flows/node_types');
        this._resourceTypesOp = this.useOp('flows/resource_types');
        this._triggersOp = this.useOp('flows/triggers_list');
    }

    connectedCallback() {
        super.connectedCallback();
        void this._nodeTypesOp.run({});
        void this._resourceTypesOp.run({});
        if (this.flowId) void this._triggersOp.run({ flow_id: this.flowId });
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (changed.has('flowId') && this.flowId) {
            void this._triggersOp.run({ flow_id: this.flowId });
        }
    }

    _matchQuery(text) {
        if (this._query.length === 0) return true;
        return String(text || '').toLowerCase().includes(this._query.toLowerCase());
    }

    _filterItems(items) {
        if (this._query.length === 0) return items;
        return items.filter((it) => this._matchQuery(it.name) || this._matchQuery(it.description) || this._matchQuery(it.type));
    }

    _onDragNodeType(e, type) {
        if (typeof type !== 'string' || type === '') return;
        e.dataTransfer.setData('application/x-flow-node-type', type);
        e.dataTransfer.effectAllowed = 'copy';
    }

    _onDragResourceType(e, type) {
        if (typeof type !== 'string' || type === '') return;
        e.dataTransfer.setData('application/x-flow-resource-type', type);
        e.dataTransfer.effectAllowed = 'copy';
    }

    _addTrigger() {
        if (!this.flowId) return;
        this.openModal('flows.trigger_editor', { flowId: this.flowId });
    }

    _renderTriggers() {
        const result = this._triggersOp.lastResult;
        const triggerItems = Array.isArray(result && result.items)
            ? result.items
            : (Array.isArray(result) ? result : []);
        return html`
            <div class="triggers-section">
                <div class="triggers-header">
                    <span class="triggers-title">${this.t('node_types_sidebar.triggers')}</span>
                    <button class="add-btn" type="button" title=${this.t('node_types_sidebar.add_trigger')} @click=${this._addTrigger}>
                        <platform-icon name="plus" size="12"></platform-icon>
                    </button>
                </div>
                ${triggerItems.length === 0
                    ? html`<div class="triggers-empty">${this.t('node_types_sidebar.no_triggers')}</div>`
                    : triggerItems.map((tr) => html`
                        <div class="trigger-row">
                            <platform-icon name="bell-ring" size="14"></platform-icon>
                            <span>${tr.name || tr.trigger_id}</span>
                        </div>
                    `)}
            </div>
        `;
    }

    _renderSearch() {
        return html`
            <div class="search-box">
                <platform-icon class="search-icon" name="search" size="14"></platform-icon>
                <input
                    type="text"
                    class="search-input"
                    .value=${this._query}
                    placeholder=${this.t('node_types_sidebar.search_placeholder')}
                    @input=${(e) => { this._query = e.target.value; }}
                />
            </div>
        `;
    }

    _renderCategory(titleKey, items, dragHandler) {
        if (items.length === 0) return '';
        return html`
            <div class="category">
                <div class="category-header">${this.t(titleKey)}</div>
                <div class="category-items">
                    ${items.map((it) => {
                        const color = typeof it.color === 'string' && it.color !== '' ? it.color : '#94a3b8';
                        const bg = `${color}20`;
                        return html`
                            <div
                                class="node-item"
                                draggable="true"
                                title=${it.description || it.name || it.type}
                                @dragstart=${(e) => dragHandler.call(this, e, it.type)}
                            >
                                <div class="node-icon" style=${`background:${bg};color:${color};`}>
                                    <platform-icon name=${it.icon || 'box'} size="16"></platform-icon>
                                </div>
                                <div class="node-name">${it.name || it.type}</div>
                            </div>
                        `;
                    })}
                </div>
            </div>
        `;
    }

    _categoryTitleKey(category) {
        return `node_types_sidebar.category_${category}`;
    }

    render() {
        const nodeTypes = Array.isArray(this._nodeTypesOp.lastResult) ? this._nodeTypesOp.lastResult : [];
        const resourceTypes = Array.isArray(this._resourceTypesOp.lastResult) ? this._resourceTypesOp.lastResult : [];
        const filteredNodes = this._filterItems(nodeTypes);
        const filteredResources = this._filterItems(resourceTypes);

        const grouped = new Map();
        for (const item of filteredNodes) {
            const cat = typeof item.category === 'string' && item.category !== '' ? item.category : 'core';
            if (!grouped.has(cat)) grouped.set(cat, []);
            grouped.get(cat).push(item);
        }

        return html`
            ${this._renderTriggers()}
            ${this._renderSearch()}
            ${NODE_CATEGORY_ORDER.map((cat) => this._renderCategory(this._categoryTitleKey(cat), grouped.get(cat) || [], this._onDragNodeType))}
            ${filteredResources.length > 0 ? html`<div class="category-divider"></div>` : ''}
            ${this._renderCategory('node_types_sidebar.category_resources', filteredResources, this._onDragResourceType)}
            ${this._nodeTypesOp.busy && nodeTypes.length === 0
                ? html`<div class="empty-row"><glass-spinner></glass-spinner></div>`
                : ''}
            ${(filteredNodes.length === 0 && filteredResources.length === 0 && nodeTypes.length > 0)
                ? html`<div class="empty-row">${this.t('node_types_sidebar.empty_search')}</div>`
                : ''}
        `;
    }
}

customElements.define('flows-node-types-sidebar', FlowsNodeTypesSidebar);
