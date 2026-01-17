/**
 * CodeDocsModal - модалка документации для редактора кода
 * Показывает globals, modules, state fields по контексту
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

export class CodeDocsModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 800px;
            }
            
            .docs-tabs {
                display: flex;
                gap: var(--space-1);
                padding: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
            }
            
            .docs-tab {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: transparent;
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .docs-tab:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            
            .docs-tab.active {
                color: var(--accent);
                background: var(--accent-bg);
                border-color: var(--accent);
            }
            
            .docs-content {
                padding: var(--space-4);
                max-height: 60vh;
                overflow-y: auto;
            }
            
            .docs-section {
                margin-bottom: var(--space-4);
            }
            
            .docs-section:last-child {
                margin-bottom: 0;
            }
            
            .docs-section-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            
            .docs-item {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-2);
            }
            
            .docs-item:last-child {
                margin-bottom: 0;
            }
            
            .docs-item-name {
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--accent);
                min-width: 120px;
                flex-shrink: 0;
            }
            
            .docs-item-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                flex-shrink: 0;
            }
            
            .docs-item-desc {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                flex: 1;
            }
            
            .modules-grid {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            
            .module-tag {
                padding: var(--space-1) var(--space-2);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
            }
            
            .loading {
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-8);
                color: var(--text-tertiary);
            }
            
            .empty-state {
                text-align: center;
                padding: var(--space-6);
                color: var(--text-tertiary);
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        language: { type: String },
        nodeType: { type: String },
        perspective: { type: String },
        _activeTab: { type: String, state: true },
        _docsData: { type: Object, state: true },
        _loading: { type: Boolean, state: true },
    };

    constructor() {
        super();
        this.size = 'lg';
        this.language = 'python';
        this.nodeType = 'code';
        this.perspective = 'editor';
        this._activeTab = 'globals';
        this._docsData = null;
        this._loading = false;
    }

    async showModal(options = {}) {
        this.language = options.language || 'python';
        this.nodeType = options.nodeType || 'code';
        this.perspective = options.perspective || 'editor';
        this._activeTab = 'globals';
        super.showModal();
        await this._loadDocs();
    }

    async _loadDocs() {
        this._loading = true;
        try {
            const params = new URLSearchParams({
                language: this.language,
                perspective: this.perspective,
            });
            this._docsData = await this.a2a.get(`/api/v1/code/completions?${params}`);
        } catch (e) {
            console.error('Failed to load docs:', e);
            this._docsData = null;
        } finally {
            this._loading = false;
        }
    }

    _setTab(tab) {
        this._activeTab = tab;
    }

    _getLanguageLabel() {
        return this.language === 'javascript' ? 'JavaScript' : 'Python';
    }

    renderHeader() {
        return html`
            <div class="modal-icon info">
                <platform-icon name="book-open" size="24"></platform-icon>
            </div>
            <span>Документация - ${this._getLanguageLabel()}</span>
        `;
    }

    renderBody() {
        if (this._loading) {
            return html`<div class="loading">Загрузка...</div>`;
        }
        
        if (!this._docsData) {
            return html`<div class="empty-state">Не удалось загрузить документацию</div>`;
        }
        
        return html`
            <div class="docs-tabs">
                <button 
                    class="docs-tab ${this._activeTab === 'globals' ? 'active' : ''}"
                    @click=${() => this._setTab('globals')}
                >
                    Globals
                </button>
                <button 
                    class="docs-tab ${this._activeTab === 'modules' ? 'active' : ''}"
                    @click=${() => this._setTab('modules')}
                >
                    Modules
                </button>
                <button 
                    class="docs-tab ${this._activeTab === 'state' ? 'active' : ''}"
                    @click=${() => this._setTab('state')}
                >
                    State
                </button>
                <button 
                    class="docs-tab ${this._activeTab === 'builtins' ? 'active' : ''}"
                    @click=${() => this._setTab('builtins')}
                >
                    Builtins
                </button>
            </div>
            
            <div class="docs-content">
                ${this._renderTabContent()}
            </div>
        `;
    }

    _renderTabContent() {
        switch (this._activeTab) {
            case 'globals':
                return this._renderGlobals();
            case 'modules':
                return this._renderModules();
            case 'state':
                return this._renderState();
            case 'builtins':
                return this._renderBuiltins();
            default:
                return '';
        }
    }

    _renderGlobals() {
        const globals = this._docsData?.globals || [];
        
        if (globals.length === 0) {
            return html`<div class="empty-state">Нет доступных глобальных переменных</div>`;
        }
        
        return html`
            <div class="docs-section">
                <div class="docs-section-title">
                    <platform-icon name="variable" size="16"></platform-icon>
                    Глобальные переменные
                </div>
                ${globals.map(g => html`
                    <div class="docs-item">
                        <span class="docs-item-name">${g.name}</span>
                        <span class="docs-item-type">${g.type}</span>
                        <span class="docs-item-desc">${g.doc}</span>
                    </div>
                `)}
            </div>
        `;
    }

    _renderModules() {
        const modules = this._docsData?.modules || [];
        const moduleMethods = this._docsData?.module_methods || {};
        
        if (modules.length === 0) {
            return html`<div class="empty-state">Нет доступных модулей</div>`;
        }
        
        return html`
            <div class="docs-section">
                <div class="docs-section-title">
                    <platform-icon name="package" size="16"></platform-icon>
                    Доступные модули
                </div>
                <div class="modules-grid">
                    ${modules.map(m => html`
                        <span class="module-tag">${m}</span>
                    `)}
                </div>
            </div>
            
            ${Object.entries(moduleMethods).map(([moduleName, methods]) => html`
                <div class="docs-section">
                    <div class="docs-section-title">${moduleName}</div>
                    ${methods.slice(0, 10).map(m => html`
                        <div class="docs-item">
                            <span class="docs-item-name">${m.name}</span>
                            <span class="docs-item-type">${m.type}</span>
                            <span class="docs-item-desc">${m.doc}</span>
                        </div>
                    `)}
                    ${methods.length > 10 ? html`
                        <div class="docs-item">
                            <span class="docs-item-desc">...и ещё ${methods.length - 10} методов</span>
                        </div>
                    ` : ''}
                </div>
            `)}
        `;
    }

    _renderState() {
        const stateFields = this._docsData?.state_fields || [];
        
        if (stateFields.length === 0) {
            return html`<div class="empty-state">Нет доступных полей state</div>`;
        }
        
        return html`
            <div class="docs-section">
                <div class="docs-section-title">
                    <platform-icon name="database" size="16"></platform-icon>
                    Поля ExecutionState
                </div>
                ${stateFields.map(f => html`
                    <div class="docs-item">
                        <span class="docs-item-name">state["${f.name}"]</span>
                        <span class="docs-item-type">${f.type}${f.readonly ? ' (readonly)' : ''}</span>
                        <span class="docs-item-desc">${f.description}</span>
                    </div>
                `)}
            </div>
        `;
    }

    _renderBuiltins() {
        const builtins = this._docsData?.builtins || [];
        
        if (builtins.length === 0) {
            return html`<div class="empty-state">Нет доступных builtins</div>`;
        }
        
        return html`
            <div class="docs-section">
                <div class="docs-section-title">
                    <platform-icon name="code" size="16"></platform-icon>
                    Встроенные функции
                </div>
                <div class="modules-grid">
                    ${builtins.map(b => html`
                        <span class="module-tag">${b}</span>
                    `)}
                </div>
            </div>
        `;
    }

    renderFooter() {
        return null;
    }
}

customElements.define('code-docs-modal', CodeDocsModal);
