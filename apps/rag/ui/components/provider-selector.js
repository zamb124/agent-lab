/**
 * ProviderSelector — выбор активного RAG-провайдера на странице настроек.
 *
 * Чтение списка и текущего провайдера — из slice фабрики `rag/providers`
 * (`useOp`); переключение — `useOp('rag/provider_switch').run({ providerName })`.
 * Список загружается фабрикой при первом mount (sidebar или эта страница —
 * что окажется раньше).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class ProviderSelector extends PlatformElement {
    static i18nNamespace = 'rag';

    static styles = [
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
            .badge.active { background: var(--accent); color: var(--text-inverse); }
            .switch-btn {
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                color: var(--text-primary);
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .switch-btn:hover:not(:disabled) {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            .switch-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .empty { color: var(--text-tertiary); font-size: var(--text-sm); }
        `,
    ];

    constructor() {
        super();
        this._providers = this.useOp('rag/providers');
        this._switch = this.useOp('rag/provider_switch');
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this._providers.lastResult && !this._providers.busy) {
            this._providers.run(null);
        }
    }

    _onSelect(name) {
        if (name === this._providers.state.current) return;
        this._switch.run({ providerName: name });
    }

    render() {
        const items = this._providers.state.items;
        const current = this._providers.state.current;
        const switching = this._switch.busy;

        if (this._providers.busy && items.length === 0) {
            return html`<div class="empty">${this.t('settings_view.providers_loading')}</div>`;
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
                                    : html`<button class="switch-btn"
                                                   ?disabled=${switching}
                                                   @click=${() => this._onSelect(p.name)}>
                                        ${this.t('settings_view.providers_switch_button')}
                                    </button>`}
                            </div>
                        </div>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('provider-selector', ProviderSelector);
