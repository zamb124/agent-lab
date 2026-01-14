/**
 * Namespace List - список namespaces
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { RagStore } from '../store/rag.store.js';
import '@platform/lib/components/layout/page-header.js';

export class NamespaceList extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
                gap: var(--space-6);
                flex-grow: 1;
            }
            
            .empty {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                flex-grow: 1;
                text-align: center;
                padding: var(--space-12);
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
            
            .loading {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                flex-grow: 1;
                padding: var(--space-12);
            }
            
            .loading-spinner {
                width: 48px;
                height: 48px;
                border: 4px solid var(--glass-border-subtle);
                border-top: 4px solid var(--accent);
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-bottom: var(--space-4);
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .loading-text {
                font-size: var(--text-base);
                color: var(--text-secondary);
            }
        `
    ];
    
    constructor() {
        super();
        this.state = this.use(s => ({
            namespaces: s.namespaces.list,
            loading: s.loading,
        }));
    }
    
    async connectedCallback() {
        super.connectedCallback();
        
        const ragApi = this.services.get('ragApi');
        await RagStore.loadNamespaces(ragApi);
    }
    
    async _createNamespace() {
        const modal = document.createElement('namespace-create-modal');
        document.body.appendChild(modal);
        
        try {
            const data = await modal.waitForSubmit();
            
            const ragApi = this.services.get('ragApi');
            const currentProvider = RagStore.state.providers.current;
            
            await ragApi.createNamespace(data.name, data.description, currentProvider);
            this.success(`Namespace "${data.name}" создан`);
            
            await RagStore.loadNamespaces(ragApi);
        } catch (error) {
            if (error.message !== 'cancelled') {
                console.error('[NamespaceList] Failed to create namespace:', error);
                this.error('Не удалось создать namespace');
                throw error;
            }
        } finally {
            modal.remove();
        }
    }
    
    render() {
        const { namespaces, loading } = this.state.value;
        
        if (loading) {
            return html`
                <div class="loading">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">Loading namespaces...</div>
                </div>
            `;
        }
        
        return html`
            <page-header 
                title="Namespaces" 
                subtitle="Manage your document namespaces"
            >
                <button slot="actions" class="btn btn-primary" @click=${this._createNamespace}>
                    <platform-icon name="plus" size="18"></platform-icon>
                    <span>Создать namespace</span>
                </button>
            </page-header>
            
            ${namespaces.length ? html`
                <div class="grid">
                    ${namespaces.map(ns => html`
                        <namespace-card
                            .namespace=${ns}
                        ></namespace-card>
                    `)}
                </div>
            ` : html`
                <div class="empty">
                    <div class="empty-icon">
                        <platform-icon name="folder" size="64"></platform-icon>
                    </div>
                    <div class="empty-text">No namespaces found</div>
                    <div class="empty-hint">Create your first namespace to get started</div>
                </div>
            `}
        `;
    }
}

customElements.define('namespace-list', NamespaceList);
