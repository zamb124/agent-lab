/**
 * Namespace Card - карточка namespace
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { RagStore } from '../store/rag.store.js';

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

            .status-breakdown {
                margin-top: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
            }

            .status-breakdown span + span::before {
                content: ' · ';
            }
        `
    ];
    
    constructor() {
        super();
        this.namespace = null;
    }
    
    _onClick() {
        const id = this.namespace.namespace_id ?? this.namespace.name;
        RagStore.selectNamespace(id);
    }

    /**
     * Всего документов: агрегат из document_status_counts (тот же источник, что строка «готово»).
     * Поле document_count в ответе GET /namespaces для identity-Namespace не заполняется.
     */
    _effectiveDocumentCount() {
        const c = this.namespace.document_status_counts;
        if (c && typeof c === 'object') {
            return (
                (c.pending ?? 0) +
                (c.processing ?? 0) +
                (c.completed ?? 0) +
                (c.failed ?? 0)
            );
        }
        return this.namespace.document_count ?? 0;
    }

    _statusCountsSubtitle() {
        const c = this.namespace.document_status_counts;
        if (!c || typeof c !== 'object') {
            return null;
        }
        const parts = [];
        if (c.completed > 0) {
            parts.push(html`<span>готово: <strong>${c.completed}</strong></span>`);
        }
        if (c.processing > 0) {
            parts.push(html`<span>в работе: <strong>${c.processing}</strong></span>`);
        }
        if (c.pending > 0) {
            parts.push(html`<span>ожидают: <strong>${c.pending}</strong></span>`);
        }
        if (c.failed > 0) {
            parts.push(html`<span>ошибки: <strong>${c.failed}</strong></span>`);
        }
        return parts.length ? html`<div class="status-breakdown">${parts}</div>` : null;
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
                        <platform-icon name="file" size="16"></platform-icon>
                        <span class="stat-value">${this._effectiveDocumentCount()}</span>
                        <span>документов</span>
                    </div>
                </div>
                ${this._statusCountsSubtitle()}
            </div>
        `;
    }
}

customElements.define('namespace-card', NamespaceCard);
