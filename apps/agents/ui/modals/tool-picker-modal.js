/**
 * ToolPickerModal - модалка для выбора tools и agents из "магазина"
 * Группировка по тегам, fullscreen режим
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class ToolPickerModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            .picker-layout {
                display: flex;
                height: 100%;
                min-height: 500px;
            }
            
            .picker-sidebar {
                width: 220px;
                flex-shrink: 0;
                padding: var(--space-4);
                border-right: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow-y: auto;
            }
            
            .sidebar-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-bottom: var(--space-2);
            }
            
            .tag-btn {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                text-align: left;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .tag-btn:hover {
                background: var(--glass-tint-medium);
            }
            
            .tag-btn.active {
                background: var(--accent);
                color: white;
            }
            
            .tag-count {
                font-size: var(--text-xs);
                opacity: 0.7;
                background: rgba(0, 0, 0, 0.1);
                padding: 2px var(--space-2);
                border-radius: var(--radius-sm);
            }
            
            .tag-btn.active .tag-count {
                background: rgba(255, 255, 255, 0.2);
            }
            
            .tag-btn-reason {
                background: var(--warning-bg);
                color: var(--warning);
                font-weight: var(--font-semibold);
                border: 1px solid var(--warning-border);
            }
            
            .tag-btn-reason:hover {
                background: rgba(245, 158, 11, 0.25);
            }
            
            .tag-btn-reason.active {
                background: var(--warning);
                color: white;
                border-color: var(--warning);
            }
            
            .picker-main {
                flex: 1;
                padding: var(--space-4);
                overflow-y: auto;
            }
            
            .picker-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-4);
            }
            
            .selected-counter {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            
            .picker-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-4);
            }
            
            .picker-empty {
                text-align: center;
                padding: var(--space-8);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            
            .picker-card {
                background: var(--glass-solid-subtle);
                border: 2px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .picker-card:hover {
                border-color: var(--accent);
                transform: translateY(-2px);
                box-shadow: var(--glass-shadow-medium);
            }
            
            .picker-card.selected {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            
            .card-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .card-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                border-radius: var(--radius-md);
                background: var(--glass-tint-medium);
            }
            
            .picker-card.is-tool .card-icon {
                color: var(--accent);
            }
            
            .picker-card.is-agent .card-icon {
                color: var(--accent-tertiary);
            }
            
            .card-type-badge {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                background: var(--glass-tint-medium);
                color: var(--text-tertiary);
            }
            
            .picker-card.is-agent .card-type-badge {
                background: var(--accent-tertiary-subtle);
                color: var(--accent-tertiary);
            }
            
            .card-check {
                margin-left: auto;
                color: var(--accent);
            }
            
            .card-body {
                flex: 1;
            }
            
            .card-title {
                margin: 0 0 var(--space-1) 0;
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            
            .card-description {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: var(--leading-normal);
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }
            
            .card-footer {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }
            
            .card-tags {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            
            .card-tag {
                font-size: var(--text-xs);
                padding: 2px var(--space-2);
                border-radius: var(--radius-sm);
                background: var(--glass-tint-medium);
                color: var(--text-tertiary);
            }
            
            .card-permission {
                font-size: var(--text-xs);
                padding: 2px var(--space-2);
                border-radius: var(--radius-sm);
                background: var(--warning-bg);
                color: var(--warning);
                margin-left: auto;
            }

            /* Responsive - Tablet */
            @media (max-width: 768px) {
                .picker-layout {
                    flex-direction: column;
                    min-height: auto;
                }
                
                .picker-sidebar {
                    width: 100%;
                    flex-direction: row;
                    flex-wrap: wrap;
                    border-right: none;
                    border-bottom: 1px solid var(--border-subtle);
                    padding: var(--space-3);
                }
                
                .sidebar-title {
                    width: 100%;
                    margin-bottom: var(--space-1);
                }
                
                .tag-btn {
                    padding: var(--space-2);
                    font-size: var(--text-xs);
                }
                
                .picker-grid {
                    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                    gap: var(--space-3);
                }
            }

            /* Responsive - Mobile */
            @media (max-width: 480px) {
                .picker-grid {
                    grid-template-columns: 1fr;
                }
                
                .picker-card {
                    padding: var(--space-3);
                }
            }
        `
    ];

    static properties = {
        selectedTools: { type: Set },
        initialSelection: { type: Array },
        loading: { type: Boolean },
        allItems: { type: Array },
        activeTag: { type: String },
    };

    constructor() {
        super();
        this.selectedTools = new Set();
        this.initialSelection = [];
        this.allItems = [];
        this.activeTag = 'all';
        this.loading = false;
        this.title = 'Добавить инструменты';
        this.size = 'full';
    }

    renderHeader() {
        return this.title;
    }

    connectedCallback() {
        super.connectedCallback();
        
        if (this.initialSelection && this.initialSelection.length > 0) {
            this.selectedTools = new Set(this.initialSelection);
        }
        
        this._loadItems();
    }

    async _loadItems() {
        this.loading = true;
        
        try {
            const items = await this.a2a.get('/api/v1/tools/all');
            this.allItems = items || [];
        } catch (error) {
            this.error(`Ошибка загрузки инструментов: ${error.message}`);
            this.allItems = [];
        }
        
        this.loading = false;
    }

    _isReasonTool(item) {
        return item.tool_type === 'reason' || 
               item.tool_type === 'exit' || 
               item.tool_id === 'reason' || 
               item.tool_id === 'final_answer';
    }

    _getAllTags() {
        const tags = new Set();
        this.allItems.forEach(item => {
            if (this._isReasonTool(item)) {
                return;
            }
            (item.tags || ['misc']).forEach(t => tags.add(t));
        });
        return Array.from(tags).sort();
    }

    _getFilteredItems() {
        if (this.activeTag === 'all') {
            return this.allItems;
        }
        if (this.activeTag === 'reason') {
            return this.allItems.filter(item => this._isReasonTool(item));
        }
        return this.allItems.filter(item => 
            !this._isReasonTool(item) && (item.tags || ['misc']).includes(this.activeTag)
        );
    }

    _onTagClick(tag) {
        this.activeTag = tag;
    }

    _onCardClick(item) {
        const toolId = item.tool_id;
        if (this.selectedTools.has(toolId)) {
            this.selectedTools.delete(toolId);
        } else {
            this.selectedTools.add(toolId);
        }
        this.selectedTools = new Set(this.selectedTools);
    }

    _onSave() {
        this.emit('tools-selected', { tools: Array.from(this.selectedTools) });
        this.close();
    }

    _renderTags() {
        const tags = this._getAllTags();
        const tagLabels = {
            'all': 'Все',
            'reason': 'Reason',
            'misc': 'Общие',
            'math': 'Математика',
            'docs': 'Документы',
            'api': 'API интеграции',
            'validation': 'Валидация',
            'agent': 'Агенты'
        };

        const reasonCount = this.allItems.filter(i => this._isReasonTool(i)).length;
        
        return html`
            <div class="sidebar-title">Категории</div>
            
            <button 
                class="tag-btn ${this.activeTag === 'all' ? 'active' : ''}" 
                @click=${() => this._onTagClick('all')}
            >
                <span>Все</span>
                <span class="tag-count">${this.allItems.length}</span>
            </button>
            
            ${reasonCount > 0 ? html`
                <button 
                    class="tag-btn tag-btn-reason ${this.activeTag === 'reason' ? 'active' : ''}" 
                    @click=${() => this._onTagClick('reason')}
                >
                    <span>Reason</span>
                    <span class="tag-count">${reasonCount}</span>
                </button>
            ` : ''}
            
            ${tags.map(tag => {
                const label = tagLabels[tag] || tag;
                const count = this.allItems.filter(i => !this._isReasonTool(i) && (i.tags || ['misc']).includes(tag)).length;
                return html`
                    <button 
                        class="tag-btn ${this.activeTag === tag ? 'active' : ''}" 
                        @click=${() => this._onTagClick(tag)}
                    >
                        <span>${label}</span>
                        <span class="tag-count">${count}</span>
                    </button>
                `;
            })}
        `;
    }

    _renderCard(item) {
        const isSelected = this.selectedTools.has(item.tool_id);
        const isAgent = item.item_type === 'agent';
        
        const tagsHtml = (item.tags || ['misc']).map(tag => 
            html`<span class="card-tag">${tag}</span>`
        );

        return html`
            <div 
                class="picker-card ${isSelected ? 'selected' : ''} ${isAgent ? 'is-agent' : 'is-tool'}"
                @click=${() => this._onCardClick(item)}
            >
                <div class="card-header">
                    <span class="card-icon">
                        <platform-icon name="${isAgent ? 'agent' : 'tool'}" size="20"></platform-icon>
                    </span>
                    <span class="card-type-badge">${isAgent ? 'Agent' : 'Tool'}</span>
                    ${isSelected ? html`
                        <span class="card-check">
                            <platform-icon name="check" size="16"></platform-icon>
                        </span>
                    ` : ''}
                </div>
                <div class="card-body">
                    <h4 class="card-title">${item.title || item.tool_id}</h4>
                    <p class="card-description">${item.description || ''}</p>
                </div>
                <div class="card-footer">
                    <div class="card-tags">${tagsHtml}</div>
                    ${item.permission ? html`
                        <span class="card-permission">${Array.isArray(item.permission) ? item.permission.join(', ') : item.permission}</span>
                    ` : ''}
                </div>
            </div>
        `;
    }

    _renderCards() {
        const items = this._getFilteredItems();
        
        if (items.length === 0) {
            return html`<div class="picker-empty">Нет инструментов</div>`;
        }
        
        return html`
            <div class="picker-grid">
                ${items.map(item => this._renderCard(item))}
            </div>
        `;
    }

    renderBody() {
        if (this.loading) {
            return html`
                <div class="picker-layout" style="align-items: center; justify-content: center;">
                    <platform-spinner size="60"></platform-spinner>
                </div>
            `;
        }
        
        return html`
            <div class="picker-layout">
                <aside class="picker-sidebar">
                    ${this._renderTags()}
                </aside>
                <main class="picker-main">
                    <div class="picker-header">
                        <span class="selected-counter">Выбрано: ${this.selectedTools.size}</span>
                    </div>
                    ${this._renderCards()}
                </main>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <button type="button" class="btn btn-secondary" @click=${this.close}>
                Отмена
            </button>
            <button type="button" class="btn btn-primary" @click=${this._onSave}>
                Добавить (${this.selectedTools.size})
            </button>
        `;
    }
}

customElements.define('tool-picker-modal', ToolPickerModal);
