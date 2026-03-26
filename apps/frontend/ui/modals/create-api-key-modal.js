/**
 * Модальное окно для создания API ключа
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/platform-icon.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { FrontendStore } from '../store/frontend.store.js';

const ALLOWED_API_KEY_SCOPES = [
    'agents:read',
    'agents:write',
    'crm:read',
    'crm:write',
    'rag:read',
    'rag:write',
    'billing:read',
];

const ALLOWED_SCOPE_SET = new Set(ALLOWED_API_KEY_SCOPES);

export class CreateApiKeyModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .scopes-list {
                display: flex;
                flex-direction: column;
                gap: 10px;
                width: 100%;
                min-width: 0;
            }

            .scope-label {
                position: relative;
                display: flex;
                align-items: stretch;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
                gap: var(--space-3, 14px);
                margin: 0;
                cursor: pointer;
                text-align: left;
            }

            .scope-label .form-item {
                flex: 1 1 auto;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
                user-select: none;
            }

            .scope-label:focus-within {
                outline: none;
            }

            .scope-label:has(.scope-checkbox:focus-visible) .form-item {
                box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.25);
            }

            .scope-checkbox {
                position: absolute;
                inset: 0;
                width: 100%;
                height: 100%;
                margin: 0;
                padding: 0;
                opacity: 0;
                cursor: pointer;
                z-index: 2;
                appearance: none;
                -webkit-appearance: none;
                border: none;
                background: transparent;
            }

            .form-item .form-item-title {
                color: var(--text-primary);
            }

            .form-item .form-item-description {
                color: var(--text-tertiary);
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
                color: var(--text-primary);
                margin: 0 0 8px 0;
            }

            .key-row {
                display: flex;
                align-items: stretch;
                gap: var(--space-2, 8px);
                margin: 20px 0;
                min-width: 0;
            }

            .key-display {
                flex: 1;
                min-width: 0;
                margin: 0;
                background: var(--accent-subtle);
                border: 1px solid var(--border-default);
                border-radius: 12px;
                padding: 12px 14px;
                word-break: break-all;
                font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
                font-size: 13px;
                color: var(--accent);
                text-align: left;
                display: flex;
                align-items: center;
            }

            .copy-key-btn {
                flex-shrink: 0;
                width: 44px;
                min-height: 44px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md, 12px);
                background: var(--glass-tint-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition:
                    background 0.15s ease,
                    border-color 0.15s ease,
                    color 0.15s ease;
            }

            .copy-key-btn:hover:not(:disabled) {
                background: var(--glass-tint-medium);
                border-color: var(--accent);
                color: var(--accent);
            }

            .copy-key-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .copy-key-btn platform-icon {
                display: block;
            }

            .warning-text {
                font-size: 13px;
                color: var(--text-tertiary);
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

        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.open = true;
        this._loading = false;
        this._name = '';
        this._scopes = [];
        this._createdKey = null;

        this._availableScopes = [
            { id: 'agents:read', name: 'Чтение агентов (Flows)', description: 'Просмотр flows и связанных данных' },
            { id: 'agents:write', name: 'Запись агентов (Flows)', description: 'Создание и изменение flows' },
            { id: 'crm:read', name: 'Чтение CRM', description: 'Просмотр сущностей и графа' },
            { id: 'crm:write', name: 'Запись CRM', description: 'Создание и изменение данных CRM' },
            { id: 'rag:read', name: 'Чтение RAG', description: 'Просмотр документов и поиск' },
            { id: 'rag:write', name: 'Запись RAG', description: 'Загрузка и изменение коллекций' },
            { id: 'billing:read', name: 'Чтение биллинга', description: 'Просмотр баланса и тарифа' },
        ];
    }

    _onScopeChange(scopeId, checked) {
        if (this._loading) {
            return;
        }
        if (checked) {
            if (!this._scopes.includes(scopeId)) {
                this._scopes = [...this._scopes, scopeId];
            }
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

        const scopes = this._scopes.filter((s) => ALLOWED_SCOPE_SET.has(s));
        if (scopes.length === 0) {
            this.error('Выберите хотя бы одну область доступа');
            return;
        }

        this._loading = true;
        this.requestUpdate();

        try {
            const result = await this.services.get('apiKeys').create(this._name.trim(), scopes);

            const secret = result.secret;
            if (!secret) {
                throw new Error('Сервер не вернул секрет ключа');
            }

            this._createdKey = { ...result, key: secret };

            const prefix = secret.length >= 12 ? secret.slice(0, 12) : secret;
            const createdAt = new Date().toISOString();
            const listRow = {
                key_id: result.key_id,
                name: result.name,
                key_prefix: prefix,
                scopes: result.scopes,
                created_at: createdAt,
                last_used: null,
                company_id: '',
                created_by: '',
            };
            const prev = FrontendStore.state.entities.apiKeys.keys;
            FrontendStore.setApiKeys([
                listRow,
                ...prev.filter((k) => k.key_id !== result.key_id),
            ]);

            this.success('API ключ успешно создан');
            this.requestUpdate();
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
            this.requestUpdate();
        } finally {
            this._loading = false;
            this.requestUpdate();
        }
    }

    async _copyToClipboard(text) {
        if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
            try {
                await navigator.clipboard.writeText(text);
                return;
            } catch {
                // Secure Context может отказать — пробуем execCommand
            }
        }
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.cssText = 'position:fixed;left:-9999px;top:0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        try {
            const ok = document.execCommand('copy');
            if (!ok) {
                throw new Error('Команда копирования не выполнена');
            }
        } finally {
            document.body.removeChild(ta);
        }
    }

    async _handleCopy() {
        const text = this._createdKey?.key;
        if (!text) {
            this.error('Нет данных ключа для копирования');
            return;
        }
        try {
            await this._copyToClipboard(text);
            this.success('Ключ скопирован в буфер обмена');
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(
                `Не удалось скопировать: ${msg}. Откройте сайт по HTTPS или скопируйте ключ вручную.`,
            );
        }
    }

    close() {
        this.open = false;
        super.close();
        this.dispatchEvent(new CustomEvent('close'));
        if (this._createdKey) {
            this.dispatchEvent(new CustomEvent('created', { detail: this._createdKey }));
        }
    }

    _handleClose() {
        this.close();
    }

    renderHeader() {
        return this._createdKey ? 'Ключ создан' : 'Создать API ключ';
    }

    renderBody() {
        return this._createdKey ? this._renderSuccess() : this._renderForm();
    }

    renderFooter() {
        return this._createdKey ? html`` : this._renderFormActions();
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
                        <label class="scope-label">
                            <div
                                class="form-item ${this._scopes.includes(scope.id) ? 'selected' : ''}"
                            >
                                <div class="form-checkbox" aria-hidden="true">
                                    ${this._scopes.includes(scope.id) ? '✓' : ''}
                                </div>
                                <div class="form-item-content">
                                    <div class="form-item-title">${scope.name}</div>
                                    <div class="form-item-description">${scope.description}</div>
                                </div>
                            </div>
                            <input
                                class="scope-checkbox"
                                type="checkbox"
                                .checked=${this._scopes.includes(scope.id)}
                                @change=${(e) => this._onScopeChange(scope.id, e.target.checked)}
                                ?disabled=${this._loading}
                            />
                        </label>
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

                <div class="key-row">
                    <div class="key-display">${this._createdKey.key}</div>
                    <button
                        type="button"
                        class="copy-key-btn"
                        title="Скопировать ключ"
                        aria-label="Скопировать ключ"
                        @click=${this._handleCopy}
                    >
                        <platform-icon name="copy" size="20"></platform-icon>
                    </button>
                </div>

                <p class="warning-text">
                    <strong>Важно:</strong> Сохраните этот ключ в безопасном месте.<br/>
                    Он больше не будет показан.
                </p>
            </div>
        `;
    }

}

customElements.define('create-api-key-modal', CreateApiKeyModal);
