/**
 * Модальное окно для создания API ключа
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/glass-modal.js';
import { FrontendStore } from '../store/frontend.store.js';

export class CreateApiKeyModal extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        formStyles,
        buttonStyles,
        css`
            .scopes-list {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }

            .success-message {
                text-align: center;
                padding: 16px 0;
            }

            .success-icon {
                width: 64px;
                height: 64px;
                margin: 0 auto 16px;
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 28px;
                color: white;
                box-shadow: 0 8px 24px rgba(16, 185, 129, 0.3);
            }

            .success-title {
                font-size: 20px;
                font-weight: 600;
                color: rgba(0, 0, 0, 0.85);
                margin: 0 0 8px 0;
            }

            .key-display {
                background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(5, 150, 105, 0.12) 100%);
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 12px;
                padding: 16px;
                margin: 20px 0;
                word-break: break-all;
                font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
                font-size: 13px;
                color: #059669;
                text-align: left;
            }

            .warning-text {
                font-size: 13px;
                color: rgba(0, 0, 0, 0.5);
                text-align: center;
                margin-top: 16px;
                line-height: 1.5;
            }

            .warning-text strong {
                color: #f59e0b;
            }

            .actions-row {
                display: flex;
                gap: 12px;
            }

            .actions-row .btn {
                flex: 1;
            }

            @media (prefers-color-scheme: dark) {
                .success-title {
                    color: rgba(255, 255, 255, 0.95);
                }

                .key-display {
                    background: rgba(16, 185, 129, 0.12);
                    border-color: rgba(16, 185, 129, 0.25);
                    color: #34d399;
                }

                .warning-text {
                    color: rgba(255, 255, 255, 0.5);
                }
            }
        `
    ];

    constructor() {
        super();
        this._open = true;
        this._loading = false;
        this._name = '';
        this._scopes = [];
        this._createdKey = null;
        
        this._availableScopes = [
            { id: 'agents:read', name: 'Чтение агентов', description: 'Просмотр списка и деталей агентов' },
            { id: 'agents:write', name: 'Управление агентами', description: 'Создание, редактирование и удаление агентов' },
            { id: 'agents:execute', name: 'Запуск агентов', description: 'Выполнение агентов и получение результатов' },
            { id: 'api:read', name: 'Чтение API', description: 'Доступ к чтению через API' },
            { id: 'api:write', name: 'Запись API', description: 'Доступ к изменению через API' },
        ];
    }

    _toggleScope(scopeId) {
        const index = this._scopes.indexOf(scopeId);
        if (index === -1) {
            this._scopes = [...this._scopes, scopeId];
        } else {
            this._scopes = this._scopes.filter((s) => s !== scopeId);
        }
        this.requestUpdate();
    }

    async _handleCreate() {
        if (!this._name.trim()) {
            this.error('Введите название ключа');
            return;
        }

        if (this._scopes.length === 0) {
            this.error('Выберите хотя бы одну область доступа');
            return;
        }

        this._loading = true;
        this.requestUpdate();
        
        const result = await this.services.get('apiKeys').create(this._name.trim(), this._scopes);
        
        FrontendStore.setApiKeysLoading(true);
        const keys = await this.services.get('apiKeys').list();
        FrontendStore.setApiKeys(keys);
        
        this._createdKey = result;
        this._loading = false;
        this.success('API ключ успешно создан');
        this.requestUpdate();
    }

    async _handleCopy() {
        await navigator.clipboard.writeText(this._createdKey.key);
        this.success('Ключ скопирован в буфер обмена');
    }

    _handleClose() {
        this._open = false;
        this.dispatchEvent(new CustomEvent('close'));
        if (this._createdKey) {
            this.dispatchEvent(new CustomEvent('created', { detail: this._createdKey }));
        }
    }

    render() {
        return html`
            <glass-modal 
                ?open=${this._open} 
                @close=${this._handleClose}
                size="md"
            >
                <span slot="title">
                    ${this._createdKey ? 'Ключ создан' : 'Создать API ключ'}
                </span>
                
                <div slot="content">
                    ${this._createdKey ? this._renderSuccess() : this._renderForm()}
                </div>
                
                <div slot="actions">
                    ${this._createdKey ? this._renderSuccessActions() : this._renderFormActions()}
                </div>
            </glass-modal>
        `;
    }

    _renderForm() {
        return html`
            <div class="form-group">
                <label class="form-label">Название ключа</label>
                <input
                    class="form-input"
                    type="text"
                    placeholder="Мой API ключ"
                    .value=${this._name}
                    @input=${(e) => { this._name = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                />
            </div>

            <div class="form-group">
                <label class="form-label">Области доступа</label>
                <div class="scopes-list">
                    ${this._availableScopes.map((scope) => html`
                        <div
                            class="form-item ${this._scopes.includes(scope.id) ? 'selected' : ''}"
                            @click=${() => !this._loading && this._toggleScope(scope.id)}
                        >
                            <div class="form-checkbox">
                                ${this._scopes.includes(scope.id) ? '✓' : ''}
                            </div>
                            <div class="form-item-content">
                                <div class="form-item-title">${scope.name}</div>
                                <div class="form-item-description">${scope.description}</div>
                            </div>
                        </div>
                    `)}
                </div>
            </div>
        `;
    }

    _renderFormActions() {
        return html`
            <div class="actions-row">
                <button
                    class="btn btn-secondary"
                    @click=${this._handleClose}
                    ?disabled=${this._loading}
                >
                    Отмена
                </button>
                <button
                    class="btn btn-primary"
                    @click=${this._handleCreate}
                    ?disabled=${this._loading}
                >
                    ${this._loading ? 'Создание...' : 'Создать ключ'}
                </button>
            </div>
        `;
    }

    _renderSuccess() {
        return html`
            <div class="success-message">
                <div class="success-icon">✓</div>
                <h3 class="success-title">API ключ создан!</h3>

                <div class="key-display">${this._createdKey.key}</div>

                <button class="btn btn-primary" style="width: 100%;" @click=${this._handleCopy}>
                    Скопировать ключ
                </button>

                <p class="warning-text">
                    <strong>Важно:</strong> Сохраните этот ключ в безопасном месте.<br/>
                    Он больше не будет показан.
                </p>
            </div>
        `;
    }

    _renderSuccessActions() {
        return html`
            <button class="btn btn-primary" style="width: 100%;" @click=${this._handleClose}>
                Готово
            </button>
        `;
    }
}

customElements.define('create-api-key-modal', CreateApiKeyModal);
