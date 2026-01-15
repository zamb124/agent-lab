/**
 * NodeTypesSidebar - левый sidebar с категориями типов нод
 * Draggable items для добавления на canvas
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const NODE_CATEGORIES = [
    {
        id: 'core',
        name: 'Core',
        items: [
            { type: 'react_node', name: 'Agent', icon: 'agent', color: '#f59e0b', description: 'Реактивный агент с LLM' },
            { type: 'function', name: 'Function', icon: 'code', color: '#8b5cf6', description: 'Python функция' },
        ]
    },
    {
        id: 'tools',
        name: 'Tools',
        items: [
            { type: 'tool', name: 'Tool', icon: 'tool', color: '#10b981', description: 'Инструмент агента' },
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
        `
    ];

    static properties = {};

    constructor() {
        super();
        this._searchQuery = '';
        this._draggingItem = null;
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
        
        this.emit('node-drag-start', { nodeType: item });
    }

    _onDragEnd(e) {
        this._draggingItem = null;
        e.target.classList.remove('dragging');
    }

    _renderNodeItem(item) {
        const bgColor = item.color + '20';
        
        return html`
            <div
                class="node-item"
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

    _renderCategory(category) {
        return html`
            <div class="category">
                <div class="category-header">${category.name}</div>
                <div class="category-items">
                    ${category.items.map(item => this._renderNodeItem(item))}
                </div>
            </div>
        `;
    }

    render() {
        const categories = this._getFilteredCategories();
        
        return html`
            <div class="sidebar">
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
                
                ${categories.map(cat => this._renderCategory(cat))}
            </div>
        `;
    }
}

customElements.define('node-types-sidebar', NodeTypesSidebar);

