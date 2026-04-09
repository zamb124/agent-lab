/**
 * API Keys Page - Управление API ключами
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FrontendStore } from '../../store/frontend.store.js';
import '../../modals/create-api-key-modal.js';
import '@platform/lib/components/layout/page-header.js';

export class ApiKeysPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .page-container {
                max-width: 1200px;
                margin: 0 auto;
            }


            .primary-button {
                padding: var(--space-3) var(--space-6);
                background: var(--accent);
                color: white;
                border: none;
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .primary-button:hover {
                transform: scale(1.05);
                box-shadow: 0 8px 24px rgba(153, 166, 249, 0.4);
            }

            .keys-grid {
                display: grid;
                gap: var(--space-4);
            }

            .key-card {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-6);
                backdrop-filter: blur(20px);
                transition: all var(--duration-normal);
            }

            .key-card:hover {
                background: var(--glass-solid-strong);
                border-color: var(--glass-border-medium);
            }

            .key-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-4);
            }

            .key-name {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0;
            }

            .key-actions {
                display: flex;
                gap: var(--space-2);
            }

            .icon-button {
                width: 36px;
                height: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .icon-button:hover {
                background: var(--glass-solid-medium);
                transform: scale(1.1);
            }

            .icon-button.danger:hover {
                background: var(--error-subtle);
                border-color: var(--error);
                color: var(--error);
            }

            .key-prefix {
                font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-3);
            }

            .key-scopes {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                margin-bottom: var(--space-3);
            }

            .scope-badge {
                padding: var(--space-1) var(--space-3);
                background: var(--accent-subtle);
                border: 1px solid var(--accent);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                color: var(--accent);
            }

            .key-meta {
                display: flex;
                gap: var(--space-6);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }

            .meta-item {
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }

            .empty-state {
                text-align: center;
                padding: var(--space-16) var(--space-6);
                color: var(--text-secondary);
            }

            .empty-icon {
                font-size: 64px;
                margin-bottom: var(--space-4);
            }

            .empty-title {
                font-size: var(--text-2xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-2) 0;
            }

            .empty-description {
                font-size: var(--text-base);
                margin: 0 0 var(--space-6) 0;
            }

            .info-box {
                background: var(--accent-subtle);
                border: 1px solid var(--accent);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                margin-bottom: var(--space-6);
                color: var(--text-primary);
                font-size: var(--text-sm);
                line-height: 1.6;
            }

            .info-box strong {
                color: var(--accent);
            }

            .loading-state {
                text-align: center;
                padding: var(--space-12);
                color: var(--text-secondary);
            }

            @media (max-width: 768px) {
                .page-header {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: var(--space-4);
                }

                .key-header {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: var(--space-3);
                }

                .key-meta {
                    flex-direction: column;
                    gap: var(--space-2);
                }
            }
        `
    ];

    constructor() {
        super();
        this.state = this.use((s) => ({
            keys: s.entities.apiKeys.keys,
            loading: s.entities.apiKeys.loading,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this._loadKeys();
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    async _loadKeys() {
        const { keys } = this.state.value;
        if (keys.length > 0) return;
        
        FrontendStore.setApiKeysLoading(true);
        const apiKeys = await this.services.get('apiKeys').list();
        FrontendStore.setApiKeys(apiKeys);
    }

    async _reloadKeys() {
        FrontendStore.setApiKeysLoading(true);
        const apiKeys = await this.services.get('apiKeys').list();
        FrontendStore.setApiKeys(apiKeys);
    }

    render() {
        const td = (key, params) => this.i18n.t(key, params ?? {});
        return html`
            <page-header 
                title=${td('api_keys_page.title')} 
                subtitle=${td('api_keys_page.subtitle')}
            >
                <button slot="actions" class="primary-button" @click=${this._onCreateClick}>
                    ${td('api_keys_page.create')}
                </button>
            </page-header>

            <div class="info-box">
                <strong>${td('api_keys_page.info_lead')}</strong>
                ${td('api_keys_page.info_body')}
            </div>

            ${this._renderContent()}
        `;
    }

    _renderContent() {
        const td = (key, params) => this.i18n.t(key, params ?? {});
        const { loading, keys } = this.state.value;
        
        if (loading) {
            return html`<div class="loading-state">${td('console_home.loading')}</div>`;
        }

        if (keys.length === 0) {
            return html`
                <div class="empty-state">
                    <div class="empty-icon">K</div>
                    <h2 class="empty-title">${td('api_keys_page.empty_title')}</h2>
                    <p class="empty-description">
                        ${td('api_keys_page.empty_description')}
                    </p>
                    <button class="primary-button" @click=${this._onCreateClick}>
                        ${td('api_keys_page.create_key')}
                    </button>
                </div>
            `;
        }

        return html`
            <div class="keys-grid">
                ${keys.map((key) => this._renderKeyCard(key))}
            </div>
        `;
    }

    _renderKeyCard(key) {
        const t = (k, p) => this.i18n.t(k, p ?? {});
        return html`
            <div class="key-card">
                <div class="key-header">
                    <h3 class="key-name">${key.name}</h3>
                    <div class="key-actions">
                        <button 
                            class="icon-button" 
                            title=${t('api_keys_page.copy_title')}
                            @click=${() => this._onCopyKey(key)}
                        >
                            C
                        </button>
                        <button 
                            class="icon-button" 
                            title=${t('api_keys_page.edit_title')}
                            @click=${() => this._onEditKey(key)}
                        >
                            E
                        </button>
                        <button 
                            class="icon-button danger" 
                            title=${t('api_keys_page.revoke_title')}
                            @click=${() => this._onRevokeKey(key)}
                        >
                            X
                        </button>
                    </div>
                </div>

                <div class="key-prefix">${key.key_prefix}--------</div>

                <div class="key-scopes">
                    ${key.scopes.map((scope) => html`
                        <span class="scope-badge">${scope}</span>
                    `)}
                </div>

                <div class="key-meta">
                    <div class="meta-item">
                        <span>${t('api_keys_page.created')} ${this._formatDate(key.created_at)}</span>
                    </div>
                    ${key.last_used ? html`
                        <div class="meta-item">
                            <span>${t('api_keys_page.used')} ${this._formatDate(key.last_used)}</span>
                        </div>
                    ` : html`
                        <div class="meta-item">
                            <span>${t('api_keys_page.never_used')}</span>
                        </div>
                    `}
                </div>
            </div>
        `;
    }

    _formatDate(dateStr) {
        const date = new Date(dateStr);
        const loc = this.i18n.getCurrentLocale() === 'en' ? 'en-US' : 'ru-RU';
        return date.toLocaleDateString(loc, {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
        });
    }

    _onCreateClick() {
        const modal = document.createElement('create-api-key-modal');
        document.body.appendChild(modal);
        modal.addEventListener('close', () => modal.remove());
    }

    _onCopyKey(key) {
        this.info(this.i18n.t('api_keys_page.info_no_full_key', {}));
    }

    _onEditKey(key) {
        this.info(this.i18n.t('api_keys_page.info_wip', {}));
    }

    async _onRevokeKey(key) {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        const confirmed = confirm(td('api_keys_page.confirm_revoke', { name: key.name }));
        if (!confirmed) return;
        
        await this.services.get('apiKeys').revoke(key.key_id);
        await this._reloadKeys();
        this.success(td('api_keys_page.toast_revoked'));
    }
}

customElements.define('api-keys-page', ApiKeysPage);
