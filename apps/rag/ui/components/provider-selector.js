/**
 * Provider Selector - dropdown для выбора RAG провайдера
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { RagStore } from '../store/rag.store.js';

export class ProviderSelector extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-block;
                position: relative;
            }
            
            .selector {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-4);
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                transition: all 0.2s;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            
            .selector:hover {
                border-color: var(--accent);
            }
            
            .dropdown {
                position: absolute;
                top: calc(100% + 8px);
                right: 0;
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                padding: var(--space-2);
                min-width: 200px;
                box-shadow: var(--glass-shadow-medium);
                z-index: 100;
            }
            
            .dropdown-item {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            
            .dropdown-item:hover {
                background: var(--glass-solid-medium);
            }
            
            .dropdown-item.active {
                background: var(--accent);
                color: white;
            }
            
            .badge {
                font-size: var(--text-xs);
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                background: var(--success);
                color: white;
            }
            
            .arrow {
                font-size: var(--text-xs);
                transition: transform 0.2s;
            }
            
            .arrow.open {
                transform: rotate(180deg);
            }
        `
    ];
    
    constructor() {
        super();
        this._dropdownOpen = false;
        
        this.state = this.use(s => ({
            providers: s.providers.list,
            currentProvider: s.providers.current,
            loading: s.providers.loading,
        }));
    }
    
    async connectedCallback() {
        super.connectedCallback();
        
        const ragApi = this.services.get('ragApi');
        await RagStore.loadProviders(ragApi);
        
        document.addEventListener('click', this._handleClickOutside);
    }
    
    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._handleClickOutside);
    }
    
    _handleClickOutside = (e) => {
        if (!this.contains(e.target)) {
            this._dropdownOpen = false;
            this.requestUpdate();
        }
    }
    
    _toggleDropdown(e) {
        e.stopPropagation();
        this._dropdownOpen = !this._dropdownOpen;
        this.requestUpdate();
    }
    
    async _selectProvider(providerName) {
        if (providerName === this.state.value.currentProvider) {
            this._dropdownOpen = false;
            this.requestUpdate();
            return;
        }
        
        const ragApi = this.services.get('ragApi');
        await RagStore.switchProvider(ragApi, providerName);
        this._dropdownOpen = false;
        this.requestUpdate();
    }
    
    render() {
        const { providers, currentProvider, loading } = this.state.value;
        
        if (loading) {
            return html`<div class="selector">Loading...</div>`;
        }
        
        const current = providers.find(p => p.name === currentProvider);
        
        return html`
            <div class="selector" @click=${this._toggleDropdown}>
                <span>Provider: ${current?.name || 'Unknown'}</span>
                <span class="arrow ${this._dropdownOpen ? 'open' : ''}">▼</span>
            </div>
            
            ${this._dropdownOpen ? html`
                <div class="dropdown">
                    ${providers.map(provider => html`
                        <div 
                            class="dropdown-item ${provider.name === currentProvider ? 'active' : ''}"
                            @click=${(e) => {
                                e.stopPropagation();
                                this._selectProvider(provider.name);
                            }}
                        >
                            <span>${provider.name}</span>
                            ${provider.is_default ? html`
                                <span class="badge">default</span>
                            ` : ''}
                        </div>
                    `)}
                </div>
            ` : ''}
        `;
    }
}

customElements.define('provider-selector', ProviderSelector);
