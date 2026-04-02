/**
 * Страница управления встраиваемыми виджетами
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FrontendStore } from '../store/frontend.store.js';
import '../modals/create-embed-modal.js';
import '../modals/embed-code-modal.js';
import '@platform/lib/components/layout/page-header.js';

export class EmbedConfigsPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .configs-table {
                background: var(--glass-solid-medium);
                border-radius: var(--radius-lg);
                overflow: hidden;
            }
            
            table {
                width: 100%;
                border-collapse: collapse;
            }
            
            th {
                text-align: left;
                padding: var(--space-4);
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }
            
            td {
                padding: var(--space-4);
                border-top: 1px solid var(--border-subtle);
                color: var(--text-primary);
            }
            
            .status-badge {
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }
            
            .status-badge.active {
                background: var(--success-subtle);
                color: var(--success);
            }
            
            .status-badge.disabled {
                background: var(--error-subtle);
                color: var(--error);
            }
            
            .actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .btn-icon {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: transparent;
                border: 1px solid var(--border-default);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            
            .btn-icon:hover {
                background: var(--glass-solid-subtle);
                border-color: var(--accent);
            }

            .primary-button {
                padding: var(--space-3) var(--space-6);
                background: var(--accent);
                color: white;
                border: none;
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .primary-button:hover {
                transform: scale(1.05);
                box-shadow: 0 8px 24px rgba(16, 185, 129, 0.4);
            }

            .loading-state {
                text-align: center;
                padding: var(--space-12);
                color: var(--text-secondary);
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
        `
    ];

    constructor() {
        super();
        this.state = this.use((s) => ({
            configs: s.entities.embed.configs,
            loading: s.entities.embed.loading,
        }));
    }

    async connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        await this.updateComplete;
        await this._loadConfigs();
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    async _loadConfigs() {
        const { configs } = this.state.value;
        if (configs.length > 0) return;
        
        FrontendStore.setEmbedLoading(true);
        const embedConfigs = await this.services.get('embed').list();
        FrontendStore.setEmbedConfigs(embedConfigs);
    }

    async _reloadConfigs() {
        FrontendStore.setEmbedLoading(true);
        const embedConfigs = await this.services.get('embed').list();
        FrontendStore.setEmbedConfigs(embedConfigs);
    }

    _handleCreate() {
        const modal = document.createElement('create-embed-modal');
        document.body.appendChild(modal);
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('created', async () => {
            await this._reloadConfigs();
        });
    }

    _handleEdit(embedId) {
        this.info(this.i18n.t('embed_page.info_wip', {}));
    }

    _handleGetCode(embedId) {
        const modal = document.createElement('embed-code-modal');
        document.body.appendChild(modal);
        modal.show(embedId);
        modal.addEventListener('close', () => modal.remove());
    }

    async _handleDelete(embedId) {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        const confirmed = confirm(td('embed_page.confirm_delete'));
        if (!confirmed) return;
        
        await this.services.get('embed').deleteConfig(embedId);
        await this._reloadConfigs();
        this.success(td('embed_page.toast_deleted'));
    }

    render() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        const { loading, configs } = this.state.value;
        
        if (loading) {
            return html`<div class="loading-state">${td('console_home.loading')}</div>`;
        }

        if (configs.length === 0) {
            return html`
                <page-header title=${td('embed_page.title')}>
                    <button slot="actions" class="primary-button" @click=${this._handleCreate}>${td('embed_page.create')}</button>
                </page-header>
                <div class="empty-state">
                    <div class="empty-icon">E</div>
                    <h2 class="empty-title">${td('embed_page.empty_title')}</h2>
                    <p class="empty-description">${td('embed_page.empty_description')}</p>
                    <button class="primary-button" @click=${this._handleCreate}>
                        ${td('embed_page.create')}
                    </button>
                </div>
            `;
        }

        return html`
            <page-header title=${td('embed_page.title')}>
                <button slot="actions" class="primary-button" @click=${this._handleCreate}>${td('embed_page.create')}</button>
            </page-header>
            
            <div class="configs-table">
                <table>
                    <thead>
                        <tr>
                            <th>${td('embed_page.col_name')}</th>
                            <th>${td('embed_page.col_flow')}</th>
                            <th>${td('embed_page.col_skill')}</th>
                            <th>${td('embed_page.col_status')}</th>
                            <th>${td('embed_page.col_usage')}</th>
                            <th>${td('embed_page.col_actions')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${configs.map((config) => html`
                            <tr>
                                <td>${config.name}</td>
                                <td>${config.flow_id}</td>
                                <td>${config.skill_id}</td>
                                <td>
                                    <span class="status-badge ${config.status}">
                                        ${config.status}
                                    </span>
                                </td>
                                <td>${config.usage_count}</td>
                                <td>
                                    <div class="actions">
                                        <button 
                                            class="btn-icon" 
                                            @click=${() => this._handleGetCode(config.embed_id)}
                                            title=${td('embed_page.get_code')}
                                        >
                                            C
                                        </button>
                                        <button 
                                            class="btn-icon" 
                                            @click=${() => this._handleEdit(config.embed_id)}
                                            title=${td('embed_page.edit')}
                                        >
                                            E
                                        </button>
                                        <button 
                                            class="btn-icon" 
                                            @click=${() => this._handleDelete(config.embed_id)}
                                            title=${td('embed_page.delete')}
                                        >
                                            X
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        `;
    }
}

customElements.define('embed-configs-page', EmbedConfigsPage);
