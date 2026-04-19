/**
 * API Keys page — управление API ключами компании.
 *
 * Источник данных — ресурс 'frontend/api_keys' (createResourceCollection),
 * подключённый через `this.useResource(...)`. Страница не знает про httpRequest,
 * не описывает селекторов, не дёргает CoreEvents и не импортирует объект ресурса.
 * Поле `lastSecret` живёт в том же slice (extraReducer ресурса) и показывается в
 * баннере до явного `dismissSecret()`.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { FrontendCreateApiKeyModal } from '../../modals/create-api-key-modal.js';
import { FrontendEditApiKeyModal } from '../../modals/edit-api-key-modal.js';

export class FrontendApiKeysPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .info-banner {
                display: flex; gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-left: 3px solid var(--info);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-4);
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
            .info-banner strong { color: var(--text-primary); margin-right: var(--space-1); }

            .secret-banner {
                display: flex; flex-direction: column; gap: var(--space-2);
                padding: var(--space-4);
                background: rgba(59, 130, 246, 0.08);
                border: 1px solid rgba(59, 130, 246, 0.4);
                border-radius: var(--radius-lg);
                margin-bottom: var(--space-4);
            }
            .secret-banner .head {
                display: flex; align-items: center; justify-content: space-between;
                color: var(--text-primary); font-weight: var(--font-semibold);
            }
            .secret-banner .warning { color: var(--warning); font-size: var(--text-xs); }
            .secret-banner .secret {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                font-family: var(--font-mono); font-size: var(--text-sm);
                color: var(--text-primary);
                word-break: break-all;
            }
            .secret-banner .actions { display: flex; gap: var(--space-2); }

            .btn {
                padding: var(--space-2) var(--space-4);
                background: var(--accent); color: white; border: none;
                border-radius: var(--radius-md); cursor: pointer;
                font-size: var(--text-sm); font-weight: var(--font-medium);
            }
            .btn:hover { filter: brightness(1.1); }
            .btn-ghost {
                background: transparent; color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
            }
            .btn-ghost:hover { color: var(--text-primary); border-color: var(--accent); }
            .btn-danger { color: var(--error); }

            table { width: 100%; border-collapse: collapse; margin-top: var(--space-4); }
            th, td { padding: var(--space-3); border-bottom: 1px solid var(--glass-border-subtle); text-align: left; }
            th { color: var(--text-tertiary); font-size: var(--text-xs); text-transform: uppercase; }
            td { color: var(--text-primary); font-size: var(--text-sm); vertical-align: middle; }
            code { font-family: var(--font-mono); color: var(--text-secondary); }

            .empty {
                padding: var(--space-8) var(--space-6);
                text-align: center; color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                margin-top: var(--space-4);
            }
            .empty .empty-title { color: var(--text-primary); font-weight: var(--font-semibold); margin-bottom: var(--space-2); }

            .scopes-cell { display: flex; flex-wrap: wrap; gap: var(--space-1); }
            .scope-tag {
                padding: 2px 8px;
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                font-size: var(--text-xs); color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this._keys = this.useResource('frontend/api_keys', { autoload: true });
    }

    _create() {
        this.openModal(FrontendCreateApiKeyModal);
    }

    _rename(key) {
        this.openModal(FrontendEditApiKeyModal, { item: key });
    }

    async _revoke(key) {
        const ok = await platformConfirm(
            this.t('api_keys_page.confirm_revoke', { name: key.name }),
            {
                title: this.t('api_keys_page.revoke_title'),
                variant: 'danger',
                confirmText: this.t('api_keys_page.revoke'),
                cancelText: this.t('api_key_modal.cancel'),
                confirmVariant: 'danger',
            },
        );
        if (!ok) return;
        this._keys.remove(key.key_id);
    }

    _copySecret(secret) {
        this.copyToClipboard(secret, {
            success_i18n_key: 'api_key_modal.toast_key_copied',
            error_i18n_key: 'api_key_modal.err_copy_failed',
        });
    }

    _dismissSecret() {
        this._keys.dismissSecret();
    }

    _renderInfoBanner() {
        return html`
            <div class="info-banner">
                <span><strong>${this.t('api_keys_page.info_lead')}</strong>${this.t('api_keys_page.info_body')}</span>
            </div>
        `;
    }

    _renderSecretBanner(lastSecret) {
        if (!lastSecret || !lastSecret.secret) return '';
        return html`
            <div class="secret-banner">
                <div class="head">
                    <span>${this.t('api_key_modal.success_title')}</span>
                    <button class="btn btn-ghost" @click=${this._dismissSecret}>×</button>
                </div>
                <div class="warning">
                    <strong>${this.t('api_key_modal.warning_lead')}</strong>
                    ${this.t('api_keys_page.info_body')}
                </div>
                <div class="secret">
                    <code>${lastSecret.secret}</code>
                </div>
                <div class="actions">
                    <button class="btn" @click=${() => this._copySecret(lastSecret.secret)}>
                        ${this.t('api_keys_page.copy_title')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderEmpty() {
        return html`
            <div class="empty">
                <div class="empty-title">${this.t('api_keys_page.empty_title')}</div>
                <div>${this.t('api_keys_page.empty_description')}</div>
            </div>
        `;
    }

    _renderRow(k) {
        return html`
            <tr>
                <td>${k.name}</td>
                <td><code>${k.key_prefix || k.key_id}</code></td>
                <td>
                    <div class="scopes-cell">
                        ${(k.scopes || []).map((s) => html`<span class="scope-tag">${s}</span>`)}
                    </div>
                </td>
                <td>${k.created_at ? new Date(k.created_at).toLocaleDateString() : ''}</td>
                <td>
                    <button class="btn btn-ghost" @click=${() => this._rename(k)}>
                        ${this.t('api_keys_page.edit_title')}
                    </button>
                    <button class="btn btn-ghost btn-danger" @click=${() => this._revoke(k)}>
                        ${this.t('api_keys_page.revoke')}
                    </button>
                </td>
            </tr>
        `;
    }

    render() {
        const list = this._keys.items;
        const loading = this._keys.loading;
        const lastSecret = this._keys.state.lastSecret;
        return html`
            <page-header
                title=${this.t('api_keys_page.title')}
                subtitle=${this.t('api_keys_page.subtitle')}
            >
                <button slot="actions" class="btn" @click=${this._create}>
                    ${this.t('api_keys_page.create')}
                </button>
            </page-header>
            ${this._renderInfoBanner()}
            ${this._renderSecretBanner(lastSecret)}
            ${loading && list.length === 0
                ? html`<div class="empty"><glass-spinner></glass-spinner></div>`
                : list.length === 0
                    ? this._renderEmpty()
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('api_keys_page.col_name')}</th>
                                <th>${this.t('api_keys_page.col_key')}</th>
                                <th>${this.t('api_keys_page.col_scopes')}</th>
                                <th>${this.t('api_keys_page.col_created')}</th>
                                <th></th>
                            </tr></thead>
                            <tbody>
                                ${list.map((k) => this._renderRow(k))}
                            </tbody>
                        </table>
                    `
            }
        `;
    }
}

customElements.define('frontend-api-keys-page', FrontendApiKeysPage);
