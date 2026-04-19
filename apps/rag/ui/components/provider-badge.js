/**
 * ProviderBadge — компактный бейдж с активным RAG-провайдером.
 *
 * Используется в sidebar-е. Источник правды — slice фабрики `rag/providers`
 * (`useOp`, поле `state.current` обновляется из `extraReducer` фабрики
 * после успешной загрузки списка провайдеров).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class ProviderBadge extends PlatformElement {
    static i18nNamespace = 'rag';

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; margin-bottom: var(--space-3); }
            .badge {
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
            }
            .label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .provider-info { display: flex; align-items: center; gap: var(--space-2); }
            .status {
                display: inline-block;
                width: 8px; height: 8px;
                border-radius: 50%;
                background: var(--success);
                box-shadow: 0 0 8px var(--success);
            }
            .provider-name {
                font-weight: 600;
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            .empty {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this._providers = this.useOp('rag/providers');
    }

    render() {
        const current = this._providers.state.current;
        const loading = this._providers.busy && !current;
        return html`
            <div class="badge">
                <div class="label">${this.t('sidebar.provider_label')}</div>
                ${loading
                    ? html`<div class="empty">${this.t('sidebar.providers_loading')}</div>`
                    : html`
                        <div class="provider-info">
                            <span class="status"></span>
                            <span class="provider-name">${current}</span>
                        </div>
                    `}
            </div>
        `;
    }
}

customElements.define('provider-badge', ProviderBadge);
