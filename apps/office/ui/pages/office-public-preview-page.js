/**
 * OfficePublicPreviewPage — anonymous preview по /documents/p/:token.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-document-viewer-host.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class OfficePublicPreviewPage extends PlatformPage {
    static i18nNamespace = 'documents';

    static properties = {
        token: { type: String },
        _errorKey: { state: true },
        _loading: { state: true },
        _resolve: { state: true },
        _openConfig: { state: true },
        _catalogItems: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                background: var(--bg-gradient);
            }
            .head {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
            }
            .title {
                font-size: var(--text-md);
                font-weight: 600;
                color: var(--text-primary);
            }
            .body {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            .catalog-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
                gap: var(--space-3);
                padding: var(--space-4);
            }
            .catalog-item {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                cursor: pointer;
                text-align: left;
            }
            .catalog-item:hover {
                background: var(--glass-solid-medium);
            }
            .viewer-shell {
                flex: 1;
                min-height: 0;
            }
            .status {
                padding: var(--space-4);
                color: var(--text-secondary);
            }
            .error {
                padding: var(--space-4);
                color: var(--danger);
            }
        `,
    ];

    constructor() {
        super();
        this.token = '';
        this._errorKey = '';
        this._loading = true;
        this._resolve = null;
        this._openConfig = null;
        this._catalogItems = [];
        this._publicResolve = this.useOp('office/public_resolve');
        this._publicOpen = this.useOp('office/public_open');
        this._publicCatalogItems = this.useOp('office/public_catalog_items');
        this._publicCatalogBindingOpen = this.useOp('office/public_catalog_binding_open');
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (changed.has('token')) {
            void this._load();
        }
    }

    async _load() {
        const token = (this.token || '').trim();
        this._errorKey = '';
        this._loading = true;
        this._openConfig = null;
        this._catalogItems = [];
        if (token.length === 0) {
            this._errorKey = 'public_preview.invalidToken';
            this._loading = false;
            return;
        }
        const resolve = await this._publicResolve.run({ token });
        if (!resolve) {
            this._errorKey = 'public_preview.notFound';
            this._loading = false;
            return;
        }
        this._resolve = resolve;
        if (resolve.resource_kind === 'catalog') {
            const itemsResponse = await this._publicCatalogItems.run({ token });
            this._catalogItems = itemsResponse && Array.isArray(itemsResponse.items)
                ? itemsResponse.items
                : [];
            this._loading = false;
            return;
        }
        const openConfig = await this._publicOpen.run({ token });
        if (!openConfig) {
            this._errorKey = 'public_preview.openFailed';
            this._loading = false;
            return;
        }
        this._openConfig = openConfig;
        this._loading = false;
    }

    async _openFileItem(item) {
        const token = (this.token || '').trim();
        if (typeof item.file_id !== 'string' || item.file_id.length === 0) return;
        if (token.length === 0) return;
        this._loading = true;
        const openConfig = await this._publicCatalogBindingOpen.run({
            token,
            fileId: item.file_id,
        });
        this._loading = false;
        if (!openConfig) {
            this._errorKey = 'public_preview.openFailed';
            return;
        }
        this._openConfig = openConfig;
    }

    render() {
        const title = this._resolve && typeof this._resolve.title === 'string'
            ? this._resolve.title
            : this.t('public_preview.title');
        return html`
            <div class="head">
                <platform-icon name="doc-detail" size="20"></platform-icon>
                <span class="title">${title}</span>
            </div>
            <div class="body">
                ${this._loading ? html`<div class="status"><glass-spinner size="lg"></glass-spinner></div>` : ''}
                ${this._errorKey ? html`<div class="error">${this.t(this._errorKey)}</div>` : ''}
                ${!this._loading && !this._errorKey && this._resolve && this._resolve.resource_kind === 'catalog'
                    ? html`
                        <div class="catalog-grid">
                            ${this._catalogItems.map((item) => html`
                                <button class="catalog-item" type="button" @click=${() => this._openFileItem(item)}>
                                    <platform-icon name="file" size="24"></platform-icon>
                                    <span>${item.title}</span>
                                </button>
                            `)}
                        </div>
                        ${this._catalogItems.length === 0
                            ? html`<div class="status">${this.t('public_preview.catalogEmpty')}</div>`
                            : ''}
                    `
                    : ''}
                ${this._openConfig ? html`
                    <div class="viewer-shell">
                        <platform-document-viewer-host
                            .fileId=${this._openConfig.file_id}
                            .openConfig=${this._openConfig}
                        >
                            <glass-spinner slot="loading"></glass-spinner>
                        </platform-document-viewer-host>
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('office-public-preview-page', OfficePublicPreviewPage);
