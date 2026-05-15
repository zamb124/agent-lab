/**
 * NamespaceCard — карточка namespace в сетке `/rag`.
 *
 * Клик навигирует на страницу деталей `namespace_detail` через core-router.
 * Source of truth для имени — поле `name` из бэкенд-модели Namespace.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class NamespaceCard extends PlatformElement {
    static i18nNamespace = 'rag';

    static properties = {
        namespace: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .card {
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-6);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                position: relative; overflow: hidden;
            }
            .card::before {
                content: ''; position: absolute; inset: 0;
                background: linear-gradient(135deg, var(--accent) 0%, transparent 100%);
                opacity: 0; transition: opacity 0.3s; pointer-events: none;
            }
            .card:hover { transform: translateY(-4px); box-shadow: var(--glass-shadow-medium); border-color: var(--accent); }
            .card:hover::before { opacity: 0.05; }
            .card-header {
                display: flex; align-items: center; gap: var(--space-3);
                margin-bottom: var(--space-4);
            }
            .icon-wrapper {
                width: 40px; height: 40px;
                display: flex; align-items: center; justify-content: center;
                background: var(--accent-subtle);
                border-radius: var(--radius-lg);
                color: var(--accent);
            }
            .title { font-size: var(--text-lg); font-weight: 600; color: var(--text-primary); flex: 1; }
            .description {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                line-height: 1.5;
                margin-top: var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this.namespace = null;
    }

    _onClick() {
        if (!this.namespace) {
            throw new Error('NamespaceCard: namespace prop is empty, cannot navigate');
        }
        this.navigate('namespace_detail', { namespaceId: this.namespace.name });
    }

    render() {
        if (!this.namespace) return html``;
        return html`
            <div class="card" @click=${this._onClick}>
                <div class="card-header">
                    <div class="icon-wrapper"><platform-icon name="folder" size="24"></platform-icon></div>
                    <div class="title">${this.namespace.name}</div>
                </div>
                ${typeof this.namespace.description === 'string' && this.namespace.description.length > 0
                    ? html`<div class="description">${this.namespace.description}</div>`
                    : ''}
            </div>
        `;
    }
}

customElements.define('namespace-card', NamespaceCard);
