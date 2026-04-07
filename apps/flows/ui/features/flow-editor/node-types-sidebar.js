/**
 * NodeTypesSidebar - левый sidebar с категориями типов нод
 * Draggable items для добавления на canvas
 * Включает секцию Triggers для управления триггерами агента
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const TRIGGER_TYPES = {
    telegram: { name: 'Telegram', icon: 'send', color: '#0088cc' },
    cron: { name: 'Cron', icon: 'clock', color: '#f59e0b' },
    webhook: { name: 'Webhook', icon: 'globe', color: '#8b5cf6' },
    email: { name: 'Email', icon: 'mail', color: '#ea4335' },
    redis: { name: 'Redis', icon: 'database', color: '#dc382d' },
};

const STATUS_COLORS = {
    active: '#10b981',
    inactive: '#6b7280',
    error: '#ef4444',
};

const NODE_CATEGORIES = [
    {
        id: 'core',
        items: [
            { type: 'llm_node', paletteKey: 'llm_node', icon: 'llm_node', color: '#f59e0b' },
            { type: 'code', paletteKey: 'code_node', icon: 'code', color: '#8b5cf6' },
        ]
    },
    {
        id: 'tools',
        items: [
            { type: 'external_api', paletteKey: 'external_api', icon: 'globe', color: '#06b6d4' },
            { type: 'mcp', paletteKey: 'mcp', icon: 'plug', color: '#8b5cf6' },
        ]
    },
    {
        id: 'integrations',
        items: [
            { type: 'remote_flow', paletteKey: 'remote_flow', icon: 'cloud', color: '#3b82f6' },
            { type: 'flow', paletteKey: 'flow_node', icon: 'workflow', color: '#ec4899' },
        ]
    },
    {
        id: 'channels',
        items: [
            { type: 'channel', paletteKey: 'channel', icon: 'send', color: '#10b981' },
            { type: 'hitl_node', paletteKey: 'hitl_node', icon: 'users', color: '#0ea5e9' },
        ]
    },
    {
        id: 'resources',
        items: [
            { type: 'code', paletteKey: 'resource_code', icon: 'code', color: '#8b5cf6', isResource: true },
            { type: 'rag', paletteKey: 'resource_rag', icon: 'search', color: '#3b82f6', isResource: true },
            { type: 'files', paletteKey: 'resource_files', icon: 'folder', color: '#f59e0b', isResource: true },
            { type: 'prompt', paletteKey: 'resource_prompt', icon: 'chat', color: '#10b981', isResource: true },
            { type: 'llm', paletteKey: 'resource_llm', icon: 'bot', color: '#ec4899', isResource: true },
            { type: 'secret', paletteKey: 'resource_secret', icon: 'key', color: '#ef4444', isResource: true },
            { type: 'http', paletteKey: 'resource_http', icon: 'globe', color: '#06b6d4', isResource: true },
            { type: 'cache', paletteKey: 'resource_cache', icon: 'database', color: '#14b8a6', isResource: true },
        ]
    },
];

export class NodeTypesSidebar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
            }
            
            .sidebar {
                display: flex;
                flex-direction: column;
                height: 100%;
                padding: var(--space-3);
                gap: var(--space-4);
            }
            
            .category {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .category-header {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.08em;
                padding: 0 var(--space-2);
            }
            
            .category-items {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            
            .node-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-2);
                border-radius: var(--radius-md);
                cursor: grab;
                transition: all var(--duration-fast) var(--easing-default);
                user-select: none;
            }
            
            .node-item:hover {
                background: var(--glass-tint-medium);
            }
            
            .node-item:active {
                cursor: grabbing;
                background: var(--glass-tint-strong);
            }
            
            .node-item.dragging {
                opacity: 0.5;
            }
            
            .node-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border-radius: var(--radius-sm);
                flex-shrink: 0;
            }
            
            .node-info {
                flex: 1;
                min-width: 0;
            }
            
            .node-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            
            .search-box {
                position: relative;
                margin-bottom: var(--space-2);
            }
            
            .search-input {
                width: 100%;
                padding: var(--space-2) var(--space-3);
                padding-left: 36px;
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                outline: none;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .search-input::placeholder {
                color: var(--text-tertiary);
            }
            
            .search-input:focus {
                border-color: var(--accent);
                background: var(--glass-tint-medium);
            }
            
            .search-icon {
                position: absolute;
                left: var(--space-3);
                top: 50%;
                transform: translateY(-50%);
                color: var(--text-tertiary);
                pointer-events: none;
            }
            
            .category-divider {
                height: 1px;
                background: var(--border-subtle);
                margin: var(--space-2) 0;
            }
            
            .resource-item .node-icon {
                border-radius: 50%;
            }
            
            /* Triggers section */
            .triggers-section {
                padding-bottom: var(--space-3);
                margin-bottom: var(--space-2);
                border-bottom: 1px solid var(--border-subtle);
            }
            
            .triggers-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 var(--space-2);
                margin-bottom: var(--space-2);
            }
            
            .triggers-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.08em;
            }
            
            .add-trigger-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 22px;
                height: 22px;
                border: none;
                border-radius: var(--radius-sm);
                background: var(--accent);
                color: white;
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .add-trigger-btn:hover {
                background: var(--accent-hover);
            }
            
            .trigger-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .trigger-item:hover {
                background: var(--glass-tint-medium);
            }
            
            .trigger-icon {
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-sm);
                flex-shrink: 0;
            }
            
            .trigger-info {
                flex: 1;
                min-width: 0;
            }
            
            .trigger-name {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            
            .trigger-status {
                width: 6px;
                height: 6px;
                border-radius: 50%;
                flex-shrink: 0;
            }
            
            .triggers-empty {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2);
                text-align: center;
            }
        `
    ];

    static properties = {
        triggers: { type: Object },
    };

    constructor() {
        super();
        this._searchQuery = '';
        this._draggingItem = null;
        this.triggers = {};
    }

    _onAddTrigger() {
        this.emit('trigger-add-requested');
    }

    _onEditTrigger(triggerId) {
        this.emit('trigger-edit-requested', { triggerId });
    }

    _onSearch(e) {
        this._searchQuery = e.target.value.toLowerCase();
    }

    _paletteName(item) {
        return this.i18n.t(`node_palette.${item.paletteKey}.name`);
    }

    _paletteDesc(item) {
        return this.i18n.t(`node_palette.${item.paletteKey}.description`);
    }

    _categoryTitle(cat) {
        return this.i18n.t(`node_palette.category_${cat.id}`);
    }

    _getFilteredCategories() {
        const q = this._searchQuery.trim().toLowerCase();
        if (!q) {
            return NODE_CATEGORIES;
        }

        return NODE_CATEGORIES.map((cat) => ({
            ...cat,
            items: cat.items.filter((item) => {
                const name = this._paletteName(item).toLowerCase();
                const desc = this._paletteDesc(item).toLowerCase();
                return name.includes(q) || desc.includes(q);
            }),
        })).filter((cat) => cat.items.length > 0);
    }

    _onDragStart(e, item) {
        this._draggingItem = item;
        e.dataTransfer.setData('application/json', JSON.stringify(item));
        e.dataTransfer.effectAllowed = 'copy';
        
        e.target.classList.add('dragging');
        
        if (item.isResource) {
            this.emit('resource-drag-start', { resourceType: item });
        } else {
            this.emit('node-drag-start', { nodeType: item });
        }
    }

    _onDragEnd(e) {
        this._draggingItem = null;
        e.target.classList.remove('dragging');
    }

    _renderNodeItem(item) {
        const bgColor = item.color + '20';
        const itemClass = item.isResource ? 'node-item resource-item' : 'node-item';
        
        return html`
            <div
                class="${itemClass}"
                draggable="true"
                @dragstart=${(e) => this._onDragStart(e, item)}
                @dragend=${this._onDragEnd}
                title=${this._paletteDesc(item)}
            >
                <div 
                    class="node-icon" 
                    style="background: ${bgColor}; color: ${item.color};"
                >
                    <platform-icon name=${item.icon} size="16"></platform-icon>
                </div>
                <div class="node-info">
                    <div class="node-name">${this._paletteName(item)}</div>
                </div>
            </div>
        `;
    }

    _renderCategory(category, showDivider = false) {
        return html`
            ${showDivider ? html`<div class="category-divider"></div>` : ''}
            <div class="category">
                <div class="category-header">${this._categoryTitle(category)}</div>
                <div class="category-items">
                    ${category.items.map(item => this._renderNodeItem(item))}
                </div>
            </div>
        `;
    }

    _renderTriggerItem(triggerId, trigger) {
        const typeInfo = TRIGGER_TYPES[trigger.type] || { name: trigger.type, icon: 'box', color: '#6b7280' };
        const statusColor = STATUS_COLORS[trigger.status] || STATUS_COLORS.inactive;
        const bgColor = typeInfo.color + '20';
        
        return html`
            <div class="trigger-item" @click=${() => this._onEditTrigger(triggerId)}>
                <div class="trigger-icon" style="background: ${bgColor}; color: ${typeInfo.color};">
                    <platform-icon name="${typeInfo.icon}" size="14"></platform-icon>
                </div>
                <div class="trigger-info">
                    <div class="trigger-name">${trigger.name || triggerId}</div>
                </div>
                <div 
                    class="trigger-status" 
                    style="background: ${statusColor};"
                    title="${trigger.status || 'inactive'}"
                ></div>
            </div>
        `;
    }

    _renderTriggersSection() {
        const triggerEntries = Object.entries(this.triggers || {});
        
        return html`
            <div class="triggers-section">
                <div class="triggers-header">
                    <span class="triggers-title">${this.i18n.t('node_types_sidebar.triggers_title')}</span>
                    <button class="add-trigger-btn" @click=${this._onAddTrigger} title=${this.i18n.t('node_types_sidebar.add_trigger_title')}>
                        <platform-icon name="plus" size="12"></platform-icon>
                    </button>
                </div>
                ${triggerEntries.length === 0 ? html`
                    <div class="triggers-empty">${this.i18n.t('node_types_sidebar.empty_triggers')}</div>
                ` : triggerEntries.map(([triggerId, trigger]) => 
                    this._renderTriggerItem(triggerId, trigger)
                )}
            </div>
        `;
    }

    render() {
        const categories = this._getFilteredCategories();
        
        return html`
            <div class="sidebar">
                ${this._renderTriggersSection()}
                
                <div class="search-box">
                    <platform-icon class="search-icon" name="search" size="16"></platform-icon>
                    <input 
                        type="text" 
                        class="search-input"
                        placeholder=${this.i18n.t('node_types_sidebar.search_placeholder')}
                        .value=${this._searchQuery}
                        @input=${this._onSearch}
                    />
                </div>
                
                ${categories.map(cat => this._renderCategory(cat, cat.id === 'resources'))}
            </div>
        `;
    }
}

customElements.define('node-types-sidebar', NodeTypesSidebar);

