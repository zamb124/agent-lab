/**
 * Search View - поиск по документам
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { RagStore } from '../store/rag.store.js';
import '@platform/lib/components/layout/page-header.js';

export class SearchView extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        buttonStyles,
        formStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            
            .search-form {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                margin-bottom: var(--space-6);
            }
            
            .form-row {
                display: flex;
                gap: var(--space-3);
            }
            
            .search-input-wrapper {
                position: relative;
            }
            
            .search-input {
                width: 100%;
                padding-right: 100px;
            }
            
            .search-btn {
                position: absolute;
                right: 4px;
                top: 4px;
                bottom: 4px;
            }
            
            .results {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            
            .result-card {
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                transition: all var(--duration-fast);
            }
            
            .result-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
            }
            
            .result-header {
                display: flex;
                justify-content: space-between;
                align-items: start;
                margin-bottom: var(--space-3);
            }
            
            .result-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-1);
            }
            
            .result-meta {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .result-score {
                padding: var(--space-1) var(--space-2);
                background: var(--accent-subtle);
                color: var(--accent);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
            }
            
            .result-content {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.6;
            }
            
            .empty {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: var(--space-12);
                text-align: center;
            }
            
            .empty-icon {
                width: 80px;
                height: 80px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-bottom: var(--space-4);
                opacity: 0.3;
                color: var(--text-tertiary);
            }
            
            .empty-text {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            
            .empty-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
        `
    ];
    
    constructor() {
        super();
        this._query = '';
        this._selectedNamespace = '';
        this._limit = 5;
        
        this.state = this.use(s => ({
            namespaces: s.namespaces.list,
            searchResults: s.search.results,
            loading: s.loading,
        }));
    }
    
    async _handleSearch(e) {
        e.preventDefault();
        
        if (!this._query || !this._selectedNamespace) {
            this.warning('Заполните все поля');
            return;
        }
        
        const ragApi = this.services.get('ragApi');
        await RagStore.searchInNamespace(ragApi, this._selectedNamespace, this._query, this._limit);
    }
    
    _handleQueryChange(e) {
        this._query = e.target.value;
        this.requestUpdate();
    }
    
    _handleNamespaceChange(e) {
        this._selectedNamespace = e.target.value;
        this.requestUpdate();
    }
    
    _handleLimitChange(e) {
        this._limit = parseInt(e.target.value);
        this.requestUpdate();
    }
    
    render() {
        const { namespaces, searchResults, loading } = this.state.value;
        
        return html`
            <page-header 
                title="Поиск" 
                subtitle="Поиск по документам в namespaces"
            ></page-header>
            
            <form class="search-form" @submit=${this._handleSearch}>
                <div class="form-row">
                    <div class="form-group" style="flex: 1;">
                        <label class="form-label">Namespace</label>
                        <select class="form-select" @change=${this._handleNamespaceChange} .value=${this._selectedNamespace}>
                            <option value="">Выберите namespace</option>
                            ${namespaces.map(ns => html`
                                <option value=${ns.namespace_id}>${ns.name}</option>
                            `)}
                        </select>
                    </div>
                    <div class="form-group" style="max-width: 150px;">
                        <label class="form-label">Результатов</label>
                        <select class="form-select" @change=${this._handleLimitChange} .value=${String(this._limit)}>
                            <option value="3">3</option>
                            <option value="5">5</option>
                            <option value="10">10</option>
                            <option value="20">20</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Запрос</label>
                    <div class="search-input-wrapper">
                        <input 
                            class="form-input search-input"
                            type="text" 
                            placeholder="Введите поисковый запрос..."
                            .value=${this._query}
                            @input=${this._handleQueryChange}
                        />
                        <button type="submit" class="btn btn-primary search-btn" ?disabled=${loading}>
                            ${loading ? 'Поиск...' : 'Найти'}
                        </button>
                    </div>
                </div>
            </form>
            
            ${searchResults.length > 0 ? html`
                <div class="results">
                    ${searchResults.map(result => html`
                        <div class="result-card">
                            <div class="result-header">
                                <div>
                                    <div class="result-title">${result.document_name || 'Документ'}</div>
                                    <div class="result-meta">Page ${result.page || 'N/A'}</div>
                                </div>
                                <div class="result-score">${(result.score * 100).toFixed(1)}%</div>
                            </div>
                            <div class="result-content">${result.content}</div>
                        </div>
                    `)}
                </div>
            ` : !loading ? html`
                <div class="empty">
                    <div class="empty-icon">
                        <platform-icon name="eye" size="64"></platform-icon>
                    </div>
                    <div class="empty-text">Нет результатов</div>
                    <div class="empty-hint">Введите запрос для поиска</div>
                </div>
            ` : html`
                <div class="empty">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">Поиск...</div>
                </div>
            `}
        `;
    }
}

customElements.define('search-view', SearchView);
