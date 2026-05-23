/**
 * Embed configs page — список встраиваемых виджетов.
 *
 * Колонки: name, embed_id, flow, branch, status, usage. Действия: get_code,
 * edit, delete. Edit открывает create-embed-modal с переданным embedConfig.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import { FrontendCreateEmbedModal } from '../modals/create-embed-modal.js';
import { FrontendEmbedCodeModal } from '../modals/embed-code-modal.js';

export class FrontendEmbedConfigsPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }

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

            table { width: 100%; border-collapse: collapse; }
            th, td {
                padding: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                text-align: left;
            }
            th {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase; letter-spacing: 0.05em;
            }
            td { color: var(--text-primary); font-size: var(--text-sm); vertical-align: middle; }
            td.actions { text-align: right; white-space: nowrap; }
            td.actions button + button { margin-left: var(--space-2); }
            td.embed-id { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-tertiary); }

            .status-tag {
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                background: var(--glass-solid-medium); color: var(--text-secondary);
            }
            .status-tag.active { background: var(--success); color: white; }
            .status-tag.disabled { background: var(--warning); color: white; }

            .empty {
                padding: var(--space-8) var(--space-6);
                text-align: center; color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .empty .empty-title { color: var(--text-primary); font-weight: var(--font-semibold); margin-bottom: var(--space-2); }

            .info-banner {
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-4);
            }
        `,
        frontendIslandPageBodyStyles,
    ];

    constructor() {
        super();
        this._configs = this.useResource('frontend/embed_configs', { autoload: true });
    }

    _create() {
        this.openModal(FrontendCreateEmbedModal);
    }

    _edit(cfg) {
        this.openModal(FrontendCreateEmbedModal, { embedConfig: cfg });
    }

    _showCode(cfg) {
        this.openModal(FrontendEmbedCodeModal, { embedId: cfg.embed_id });
    }

    _delete(cfg) {
        if (!confirm(this.t('embed_page.confirm_delete'))) return;
        this._configs.remove(cfg.embed_id);
    }

    _renderEmpty() {
        return html`
            <div class="empty">
                <div class="empty-title">${this.t('embed_page.empty_title')}</div>
                <div>${this.t('embed_page.empty_description')}</div>
            </div>
        `;
    }

    _renderRow(c) {
        const status = c.status || 'active';
        return html`
            <tr>
                <td>${c.name || c.embed_id}</td>
                <td class="embed-id">${c.embed_id}</td>
                <td>${c.flow_id || ''}</td>
                <td>${c.branch_id || ''}</td>
                <td><span class="status-tag ${status === 'active' ? 'active' : 'disabled'}">${status}</span></td>
                <td>${typeof c.usage_count === 'number' ? c.usage_count : 0}</td>
                <td class="actions">
                    <button class="btn btn-ghost" @click=${() => this._showCode(c)}>
                        ${this.t('embed_page.get_code')}
                    </button>
                    <button class="btn btn-ghost" @click=${() => this._edit(c)}>
                        ${this.t('embed_page.edit')}
                    </button>
                    <button class="btn btn-ghost btn-danger" @click=${() => this._delete(c)}>
                        ${this.t('embed_page.delete')}
                    </button>
                </td>
            </tr>
        `;
    }

    render() {
        const configs = this._configs.items;
        const loading = this._configs.loading;
        return html`
            <page-header
                title=${this.t('embed_page.title')}
                subtitle=${this.t('embed_page.subtitle')}
            >
                <button slot="actions" class="btn" @click=${this._create}>
                    ${this.t('embed_page.create')}
                </button>
            </page-header>
            <div class="page-body">
            <div class="info-banner">${this.t('embed_page.external_wizard_note')}</div>
            ${loading && configs.length === 0
                ? html`<div class="empty"><glass-spinner></glass-spinner></div>`
                : configs.length === 0
                    ? this._renderEmpty()
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('embed_page.col_name')}</th>
                                <th>${this.t('embed_page.col_embed_id')}</th>
                                <th>${this.t('embed_page.col_flow')}</th>
                                <th>${this.t('embed_page.col_branch')}</th>
                                <th>${this.t('embed_page.col_status')}</th>
                                <th>${this.t('embed_page.col_usage')}</th>
                                <th>${this.t('embed_page.col_actions')}</th>
                            </tr></thead>
                            <tbody>
                                ${configs.map((c) => this._renderRow(c))}
                            </tbody>
                        </table>
                    `
            }
            </div>
        `;
    }
}

customElements.define('frontend-embed-configs-page', FrontendEmbedConfigsPage);
