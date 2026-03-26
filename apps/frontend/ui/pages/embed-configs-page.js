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
                padding: var(--space-6);
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
        await this.updateComplete;
        await this._loadConfigs();
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
        this.info('Функция редактирования в разработке');
    }

    _handleGetCode(embedId) {
        const modal = document.createElement('embed-code-modal');
        document.body.appendChild(modal);
        modal.show(embedId);
        modal.addEventListener('close', () => modal.remove());
    }

    async _handleDelete(embedId) {
        const confirmed = confirm('Удалить виджет? Это действие нельзя отменить.');
        if (!confirmed) return;
        
        await this.services.get('embed').deleteConfig(embedId);
        await this._reloadConfigs();
        this.success('Виджет удален');
    }

    render() {
        const { loading, configs } = this.state.value;
        
        if (loading) {
            return html`<div class="loading-state">Загрузка...</div>`;
        }

        if (configs.length === 0) {
            return html`
                <page-header title="Встраиваемые виджеты">
                    <button slot="actions" class="primary-button" @click=${this._handleCreate}>Создать виджет</button>
                </page-header>
                <div class="empty-state">
                    <div class="empty-icon">E</div>
                    <h2 class="empty-title">Нет виджетов</h2>
                    <p class="empty-description">Создайте первый встраиваемый виджет</p>
                    <button class="primary-button" @click=${this._handleCreate}>
                        Создать виджет
                    </button>
                </div>
            `;
        }

        return html`
            <page-header title="Встраиваемые виджеты">
                <button slot="actions" class="primary-button" @click=${this._handleCreate}>Создать виджет</button>
            </page-header>
            
            <div class="configs-table">
                <table>
                    <thead>
                        <tr>
                            <th>Название</th>
                            <th>Flow</th>
                            <th>Skill</th>
                            <th>Статус</th>
                            <th>Использований</th>
                            <th>Действия</th>
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
                                            title="Получить код"
                                        >
                                            C
                                        </button>
                                        <button 
                                            class="btn-icon" 
                                            @click=${() => this._handleEdit(config.embed_id)}
                                            title="Редактировать"
                                        >
                                            E
                                        </button>
                                        <button 
                                            class="btn-icon" 
                                            @click=${() => this._handleDelete(config.embed_id)}
                                            title="Удалить"
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
