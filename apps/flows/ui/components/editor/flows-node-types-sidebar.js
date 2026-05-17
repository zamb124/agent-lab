/**
 * flows-node-types-sidebar — палитра типов нод и ресурсов для drag-into-canvas.
 *
 * Источники:
 *   - useOp('flows/node_types').lastResult — runtime-ноды с category
 *     (`core` | `tools` | `integrations` | `channels`).
 *   - useOp('flows/resource_types').lastResult — ресурсные типы (раздел «Ресурсы»).
 *   - useOp('flows/triggers_list').run({ flow_id }) — триггеры flow для
 *     отдельной секции в шапке сайдбара.
 * Кнопка «Лимиты и речь» над секцией триггеров — показ/скрытие панели
 * `flows-flow-property-panel` в правом столбе (событие `toggle-flow-settings`).
 *
 * Поиск фильтрует все категории + ресурсы (по name / description / type),
 * категории без совпадений скрываются.
 *
 * Drag: dataTransfer `application/x-flow-node-type` для нод и
 * `application/x-flow-resource-type` для ресурсов.
 *
 * Тип ноды `resource` в палитре не показываем: нода-ресурс на канве создаётся
 * только перетаскиванием записи из секции «Ресурсы» (конкретный resource type),
 * иначе дублирует смысл и путает.
 *
 * UI-actions: «+» — новый триггер; карандаш/мусор в строке — редактирование / удаление.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import { getNodeTypeMeta, getCategoryToken } from '../../constants/node-icons.js';
import { getTriggerTypeRowVisual } from '../../constants/trigger-types.js';
import { asArray, asString } from '../../_helpers/flows-resolvers.js';

const NODE_CATEGORY_ORDER = Object.freeze(['core', 'tools', 'integrations', 'channels']);

const CATEGORY_TO_TOKEN_KEY = Object.freeze({
    core: 'core',
    tools: 'core',
    integrations: 'integrations',
    channels: 'flow',
    resources: 'flow',
});

export class FlowsNodeTypesSidebar extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        flowSettingsActive: { type: Boolean, attribute: 'flow-settings-active' },
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

            /* Triggers */
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
                width: 24px; height: 24px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .add-btn:hover { background: var(--accent-subtle); color: var(--accent); border-color: var(--accent); }
            .triggers-empty {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2);
                text-align: center;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
            }
            .trigger-row {
                display: flex; align-items: center; justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-2);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                font-size: var(--text-sm);
                line-height: 1.25;
                color: var(--text-primary);
                min-width: 0;
                box-sizing: border-box;
            }
            .trigger-row-main {
                display: flex; align-items: center; gap: var(--space-2);
                min-width: 0;
                flex: 1;
            }
            .trigger-type-icon-wrap {
                width: 22px;
                height: 22px;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                box-sizing: border-box;
            }
            .trigger-row-label {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                line-height: 1.25;
            }
            .trigger-row-actions {
                display: inline-flex;
                align-items: center;
                flex-shrink: 0;
                gap: var(--space-1);
            }
            .trigger-row-actions .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 22px;
                height: 22px;
                min-width: 22px;
                min-height: 22px;
                box-sizing: border-box;
                padding: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .trigger-row-actions .icon-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
            }
            .trigger-row-actions .icon-btn.danger:hover {
                color: var(--error, #f43f5e);
                border-color: var(--error, #f43f5e);
            }

            button.trigger-row {
                appearance: none;
                margin: 0;
                font: inherit;
                color: inherit;
                width: 100%;
                text-align: left;
                cursor: pointer;
            }
            button.trigger-row.is-active {
                border-color: var(--accent);
                box-shadow: 0 0 0 1px color-mix(in oklab, var(--accent) 40%, transparent);
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
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                line-height: 1.25;
            }
            .search-input:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 2px var(--accent-subtle);
            }

            /* Categories */
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

            /* Node type card */
            .node-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-height: 42px;
                padding: 6px 8px;
                border-radius: var(--radius-sm);
                border: 1px solid transparent;
                background: transparent;
                box-sizing: border-box;
                cursor: grab;
                transition: var(--motion-transition-interactive);
            }
            .node-item:hover {
                background: color-mix(in oklab, var(--glass-solid-medium) 86%, var(--accent) 8%);
                border-color: var(--glass-border-subtle);
                box-shadow:
                    0 7px 18px rgba(0, 0, 0, 0.12),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
                transform: translateY(-1px);
            }
            .node-item:active { cursor: grabbing; }
            .node-icon {
                width: 30px;
                height: 30px;
                flex-shrink: 0;
                border-radius: var(--radius-sm);
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow:
                    inset 0 1px 0 rgba(255, 255, 255, 0.12),
                    0 3px 10px rgba(0, 0, 0, 0.1);
            }
            .node-name {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-medium);
                min-width: 0;
                line-height: 1.2;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
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
        this.flowSettingsActive = false;
        this._query = '';
        this._nodeTypesOp = this.useOp('flows/node_types');
        this._resourceTypesOp = this.useOp('flows/resource_types');
        this._triggersOp = this.useOp('flows/triggers_list');
        this._removeTriggerOp = this.useOp('flows/trigger_remove');
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
        return asString(text).toLowerCase().includes(this._query.toLowerCase());
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
        this.openModal('flows.trigger_editor', { flowId: this.flowId, trigger: null });
    }

    _editTrigger(tr) {
        if (!this.flowId) return;
        if (!tr || typeof tr.trigger_id !== 'string' || tr.trigger_id.length === 0) {
            throw new Error('FlowsNodeTypesSidebar._editTrigger: trigger with trigger_id required');
        }
        this.openModal('flows.trigger_editor', { flowId: this.flowId, trigger: tr });
    }

    async _deleteTrigger(tr) {
        if (!this.flowId) return;
        if (!tr || typeof tr.trigger_id !== 'string' || tr.trigger_id.length === 0) {
            throw new Error('FlowsNodeTypesSidebar._deleteTrigger: trigger with trigger_id required');
        }
        const ok = await platformConfirm(
            this.t('triggers_modal.delete_message', { id: tr.trigger_id }),
            {
                title: this.t('triggers_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('triggers_modal.action_delete'),
                cancelText: this.t('triggers_modal.action_cancel'),
            },
        );
        if (!ok) return;
        await this._removeTriggerOp.run({ flow_id: this.flowId, trigger_id: tr.trigger_id });
        void this._triggersOp.run({ flow_id: this.flowId });
    }

    _toggleFlowSettingsPanel() {
        if (!this.flowId) return;
        this.emit('toggle-flow-settings', {});
    }

    _renderFlowSettingsPanelToggle() {
        if (!this.flowId) return '';
        const flowTok = getCategoryToken('flow');
        const wrapBg = `color-mix(in oklab, ${flowTok} 14%, transparent)`;
        return html`
            <div class="triggers-section">
                <button
                    type="button"
                    class="trigger-row ${this.flowSettingsActive ? 'is-active' : ''}"
                    aria-pressed=${this.flowSettingsActive ? 'true' : 'false'}
                    title=${this.t('node_types_sidebar.flow_settings_toggle_hint')}
                    @click=${this._toggleFlowSettingsPanel}
                >
                    <div class="trigger-row-main">
                        <div
                            class="trigger-type-icon-wrap"
                            style="background:${wrapBg};color:${flowTok};"
                            aria-hidden="true"
                        >
                            <platform-icon name="adjustment" size="12"></platform-icon>
                        </div>
                        <span class="trigger-row-label">${this.t('flow_property_panel.card_title')}</span>
                    </div>
                </button>
            </div>
        `;
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
                    : triggerItems.map((tr) => {
                        const tv = getTriggerTypeRowVisual(tr.type);
                        return html`
                        <div class="trigger-row">
                            <div class="trigger-row-main">
                                <div
                                    class="trigger-type-icon-wrap"
                                    style="background:${tv.wrapBg};color:${tv.wrapFg};"
                                    aria-hidden="true"
                                >
                                    <platform-icon name=${tv.icon} size="12"></platform-icon>
                                </div>
                                <span class="trigger-row-label">${tr.name || tr.trigger_id}</span>
                            </div>
                            <div class="trigger-row-actions" @click=${(e) => e.stopPropagation()}>
                                <button
                                    type="button"
                                    class="icon-btn"
                                    title=${this.t('triggers_modal.action_edit')}
                                    aria-label=${this.t('triggers_modal.action_edit')}
                                    @click=${() => this._editTrigger(tr)}
                                >
                                    <platform-icon name="edit" size="12"></platform-icon>
                                </button>
                                <button
                                    type="button"
                                    class="icon-btn danger"
                                    title=${this.t('triggers_modal.action_delete')}
                                    aria-label=${this.t('triggers_modal.action_delete')}
                                    @click=${() => this._deleteTrigger(tr)}
                                >
                                    <platform-icon name="trash" size="12"></platform-icon>
                                </button>
                            </div>
                        </div>
                    `;
                    })}
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
                    data-canon="search-as-you-type"
                    .value=${this._query}
                    placeholder=${this.t('node_types_sidebar.search_placeholder')}
                    @input=${(e) => { this._query = e.target.value; }}
                />
            </div>
        `;
    }

    _renderCategory(titleKey, items, dragHandler, categoryKey) {
        if (items.length === 0) return '';
        const tokenKey = CATEGORY_TO_TOKEN_KEY[categoryKey];
        const categoryToken = getCategoryToken(typeof tokenKey === 'string' && tokenKey.length > 0 ? tokenKey : 'core');
        return html`
            <div class="category">
                <div class="category-header">${this.t(titleKey)}</div>
                <div class="category-items">
                    ${items.map((it) => {
                        const meta = getNodeTypeMeta(it.type);
                        const iconName = meta.icon !== 'box' ? meta.icon : (typeof it.icon === 'string' && it.icon.length > 0 ? it.icon : 'box');
                        const tokenColor = getCategoryToken(meta.category) !== getCategoryToken('core') || categoryKey === 'core'
                            ? getCategoryToken(meta.category)
                            : categoryToken;
                        const style = `background: color-mix(in oklab, ${tokenColor} 14%, transparent); color: ${tokenColor};`;
                        return html`
                            <div
                                class="node-item"
                                draggable="true"
                                title=${it.description || it.name || it.type}
                                @dragstart=${(e) => dragHandler.call(this, e, it.type)}
                            >
                                <div class="node-icon" style=${style}>
                                    <platform-icon name=${iconName} size="16"></platform-icon>
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
        const paletteNodeTypes = nodeTypes.filter((it) => it && it.type !== 'resource');
        const filteredNodes = this._filterItems(paletteNodeTypes);
        const filteredResources = this._filterItems(resourceTypes);

        const grouped = new Map();
        for (const item of filteredNodes) {
            const cat = typeof item.category === 'string' && item.category !== '' ? item.category : 'core';
            if (!grouped.has(cat)) grouped.set(cat, []);
            grouped.get(cat).push(item);
        }

        return html`
            ${this._renderFlowSettingsPanelToggle()}
            ${this._renderTriggers()}
            ${this._renderSearch()}
            ${NODE_CATEGORY_ORDER.map((cat) => this._renderCategory(this._categoryTitleKey(cat), asArray(grouped.get(cat)), this._onDragNodeType, cat))}
            ${filteredResources.length > 0 ? html`<div class="category-divider"></div>` : ''}
            ${this._renderCategory('node_types_sidebar.category_resources', filteredResources, this._onDragResourceType, 'resources')}
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
