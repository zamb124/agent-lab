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
                box-shadow: 0 8px 24px rgba(16, 185, 129, 0.4);
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
        this._loadKeys();
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
        return html`
            <page-header 
                title="API Ключи" 
                subtitle="Управление ключами для интеграций с платформой"
            >
                <button slot="actions" class="primary-button" @click=${this._onCreateClick}>
                    + Создать ключ
                </button>
            </page-header>

            <div class="info-box">
                <strong>Важно:</strong> Секретный ключ показывается только один раз при создании.
                Сохраните его в безопасном месте. Если ключ утерян, создайте новый.
            </div>

            ${this._renderContent()}
        `;
    }

    _renderContent() {
        const { loading, keys } = this.state.value;
        
        if (loading) {
            return html`<div class="loading-state">Загрузка...</div>`;
        }

        if (keys.length === 0) {
            return html`
                <div class="empty-state">
                    <div class="empty-icon">K</div>
                    <h2 class="empty-title">Нет API ключей</h2>
                    <p class="empty-description">
                        Создайте первый ключ для интеграции с платформой
                    </p>
                    <button class="primary-button" @click=${this._onCreateClick}>
                        Создать ключ
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
        return html`
            <div class="key-card">
                <div class="key-header">
                    <h3 class="key-name">${key.name}</h3>
                    <div class="key-actions">
                        <button 
                            class="icon-button" 
                            title="Копировать"
                            @click=${() => this._onCopyKey(key)}
                        >
                            C
                        </button>
                        <button 
                            class="icon-button" 
                            title="Редактировать"
                            @click=${() => this._onEditKey(key)}
                        >
                            E
                        </button>
                        <button 
                            class="icon-button danger" 
                            title="Отозвать"
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
                        <span>Создан: ${this._formatDate(key.created_at)}</span>
                    </div>
                    ${key.last_used ? html`
                        <div class="meta-item">
                            <span>Использован: ${this._formatDate(key.last_used)}</span>
                        </div>
                    ` : html`
                        <div class="meta-item">
                            <span>Никогда не использовался</span>
                        </div>
                    `}
                </div>
            </div>
        `;
    }

    _formatDate(dateStr) {
        const date = new Date(dateStr);
        return date.toLocaleDateString('ru-RU', {
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
        this.info('Полный ключ недоступен. Показан только при создании.');
    }

    _onEditKey(key) {
        this.info('Функция в разработке');
    }

    async _onRevokeKey(key) {
        const confirmed = confirm(`Отозвать ключ "${key.name}"? Это действие нельзя отменить.`);
        if (!confirmed) return;
        
        await this.services.get('apiKeys').revoke(key.key_id);
        await this._reloadKeys();
        this.success('API ключ отозван');
    }
}

customElements.define('api-keys-page', ApiKeysPage);
