/**
 * ProviderSelector — список включённых RAG-провайдеров и текущего
 * `rag.default_provider` из slice `rag/providers`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { OpController } from '@platform/lib/base/use-resource.js';

interface RagProviderItem {
    name?: unknown;
    is_default?: unknown;
    [key: string]: unknown;
}
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class ProviderSelector extends PlatformElement {
    static i18nNamespace = 'rag';

    private _providers: OpController;

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            }
            .card {
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }
            .card.active {
                border-color: var(--accent);
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .card-name {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .card.active .card-name { color: var(--accent); }
            .badges { display: inline-flex; gap: var(--space-1); align-items: center; }
            .badge {
                font-size: var(--text-xs);
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                background: var(--glass-solid-strong);
                color: var(--text-tertiary);
            }
            .badge.active { background: var(--accent); color: var(--platform-btn-primary-text); }
            .empty { color: var(--text-tertiary); font-size: var(--text-sm); }
        `,
    ];

    constructor() {
        super();
        this._providers = this.useOp('rag/providers');
    }

    override connectedCallback() {
        super.connectedCallback();
        if (!this._providers.lastResult && !this._providers.busy) {
            this._providers.run({});
        }
    }

    override render() {
        const state = this._providers.state as Record<string, unknown>;
        const items = Array.isArray(state.items) ? state.items as RagProviderItem[] : [];
        const current = state.current;

        if (this._providers.busy && items.length === 0) {
            return html`<div class="empty"><glass-spinner></glass-spinner></div>`;
        }

        return html`
            <div class="grid">
                ${items.map((p) => {
                    const isActive = p.name === current;
                    return html`
                        <div class="card ${isActive ? 'active' : ''}">
                            <div class="card-name">
                                <platform-icon name="folder" size="14"></platform-icon>
                                <span>${p.name}</span>
                            </div>
                            <div class="badges">
                                ${p.is_default ? html`<span class="badge">${this.t('settings_view.providers_default_badge')}</span>` : ''}
                                ${isActive
                                    ? html`<span class="badge active">${this.t('settings_view.providers_active_badge')}</span>`
                                    : ''}
                            </div>
                        </div>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('provider-selector', ProviderSelector);
