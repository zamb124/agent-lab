/**
 * Namespace Card - карточка namespace
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { RagStore } from '../store/rag.store.js';
import '@platform/lib/components/platform-icon.js';

export class NamespaceCard extends PlatformElement {
    static properties = {
        namespace: { type: Object },
    };
    
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .card {
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-6);
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                overflow: hidden;
            }
            
            .card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(135deg, var(--accent) 0%, transparent 100%);
                opacity: 0;
                transition: opacity 0.3s;
                pointer-events: none;
            }
            
            .card:hover {
                transform: translateY(-4px);
                box-shadow: var(--glass-shadow-medium);
                border-color: var(--accent);
            }
            
            .card:hover::before {
                opacity: 0.05;
            }
            
            .card-header {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }
            
            .icon-wrapper {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-subtle);
                border-radius: var(--radius-lg);
                color: var(--accent);
            }
            
            .title {
                font-size: var(--text-lg);
                font-weight: 600;
                color: var(--text-primary);
                flex: 1;
            }
            
            .stats {
                display: flex;
                gap: var(--space-5);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .stat {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .stat-value {
                font-weight: 600;
                color: var(--text-primary);
            }
        `
    ];
    
    constructor() {
        super();
        this.namespace = null;
    }
    
    _onClick() {
        RagStore.selectNamespace(this.namespace.namespace_id);
    }
    
    render() {
        if (!this.namespace) return html``;
        
        return html`
            <div class="card" @click=${this._onClick}>
                <div class="card-header">
                    <div class="icon-wrapper">
                        <platform-icon name="folder" size="24"></platform-icon>
                    </div>
                    <div class="title">${this.namespace.name}</div>
                </div>
                <div class="stats">
                    <div class="stat">
                        <platform-icon file-icon name="text" size="16"></platform-icon>
                        <span class="stat-value">${this.namespace.document_count || 0}</span>
                        <span>documents</span>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('namespace-card', NamespaceCard);
