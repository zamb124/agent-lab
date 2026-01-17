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
        name: 'Core',
        items: [
            { type: 'react_node', name: 'Agent', icon: 'agent', color: '#f59e0b', description: 'Реактивный агент с LLM' },
            { type: 'code', name: 'Code Node', icon: 'code', color: '#8b5cf6', description: 'Python функция' },
        ]
    },
    {
        id: 'tools',
        name: 'Tools',
        items: [
            { type: 'external_api', name: 'External API', icon: 'globe', color: '#06b6d4', description: 'HTTP API вызов' },
            { type: 'mcp', name: 'MCP Tool', icon: 'plug', color: '#8b5cf6', description: 'MCP сервер tool' },
        ]
    },
    {
        id: 'integrations',
        name: 'Integrations',
        items: [
            { type: 'remote_agent', name: 'Remote Agent', icon: 'cloud', color: '#3b82f6', description: 'Внешний A2A агент' },
            { type: 'agent', name: 'Agent Node', icon: 'workflow', color: '#ec4899', description: 'Вызов другого агента' },
        ]
    },
    {
        id: 'channels',
        name: 'Channels',
        items: [
            { type: 'channel', name: 'Channel', icon: 'send', color: '#10b981', description: 'Отправка в каналы (Telegram, Email)' },
        ]
    },
    {
        id: 'resources',
        name: 'Resources',
        items: [
            { type: 'code', name: 'Code', icon: 'code', color: '#8b5cf6', description: 'Inline Python/JS код', isResource: true },
            { type: 'rag', name: 'RAG', icon: 'search', color: '#3b82f6', description: 'RAG namespace для поиска', isResource: true },
            { type: 'files', name: 'Files', icon: 'folder', color: '#f59e0b', description: 'S3/MinIO файловое хранилище', isResource: true },
            { type: 'prompt', name: 'Prompt', icon: 'chat', color: '#10b981', description: 'Шаблон промпта', isResource: true },
            { type: 'llm', name: 'LLM', icon: 'bot', color: '#ec4899', description: 'LLM модель', isResource: true },
            { type: 'secret', name: 'Secret', icon: 'key', color: '#ef4444', description: 'Секрет из переменных', isResource: true },
            { type: 'http', name: 'HTTP', icon: 'globe', color: '#06b6d4', description: 'HTTP endpoint', isResource: true },
            { type: 'cache', name: 'Cache', icon: 'database', color: '#14b8a6', description: 'Redis cache namespace', isResource: true },
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

    _getFilteredCategories() {
        if (!this._searchQuery) {
            return NODE_CATEGORIES;
        }
        
        return NODE_CATEGORIES.map(cat => ({
            ...cat,
            items: cat.items.filter(item => 
                item.name.toLowerCase().includes(this._searchQuery) ||
                item.description.toLowerCase().includes(this._searchQuery)
            )
        })).filter(cat => cat.items.length > 0);
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
                title=${item.description}
            >
                <div 
                    class="node-icon" 
                    style="background: ${bgColor}; color: ${item.color};"
                >
                    <platform-icon name=${item.icon} size="16"></platform-icon>
                </div>
                <div class="node-info">
                    <div class="node-name">${item.name}</div>
                </div>
            </div>
        `;
    }

    _renderCategory(category, showDivider = false) {
        return html`
            ${showDivider ? html`<div class="category-divider"></div>` : ''}
            <div class="category">
                <div class="category-header">${category.name}</div>
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
                    <span class="triggers-title">Triggers</span>
                    <button class="add-trigger-btn" @click=${this._onAddTrigger} title="Добавить триггер">
                        <platform-icon name="plus" size="12"></platform-icon>
                    </button>
                </div>
                ${triggerEntries.length === 0 ? html`
                    <div class="triggers-empty">Нет триггеров</div>
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
                        placeholder="Search nodes..."
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

