/**
 * Модальное окно для создания виджета
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { FrontendStore } from '../store/frontend.store.js';

export class CreateEmbedModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .position-options {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 12px;
            }

            .position-option {
                padding: 16px;
                background: rgba(0, 0, 0, 0.02);
                border: 2px solid rgba(0, 0, 0, 0.06);
                border-radius: 14px;
                cursor: pointer;
                transition: all 0.2s ease;
                text-align: center;
            }

            .position-option:hover {
                background: rgba(0, 0, 0, 0.04);
                border-color: rgba(0, 0, 0, 0.1);
            }

            .position-option.selected {
                background: rgba(16, 185, 129, 0.08);
                border-color: rgba(16, 185, 129, 0.4);
            }

            .position-icon {
                font-size: 24px;
                margin-bottom: 8px;
                color: rgba(0, 0, 0, 0.6);
            }

            .position-option.selected .position-icon {
                color: #10b981;
            }

            .position-label {
                font-size: 13px;
                font-weight: 500;
                color: rgba(0, 0, 0, 0.7);
            }

            .actions-row {
                display: flex;
                gap: 12px;
            }

            .actions-row .btn {
                flex: 1;
            }

            @media (prefers-color-scheme: dark) {
                .position-option {
                    background: rgba(255, 255, 255, 0.03);
                    border-color: rgba(255, 255, 255, 0.08);
                }

                .position-option:hover {
                    background: rgba(255, 255, 255, 0.06);
                    border-color: rgba(255, 255, 255, 0.12);
                }

                .position-option.selected {
                    background: rgba(16, 185, 129, 0.12);
                    border-color: rgba(16, 185, 129, 0.4);
                }

                .position-icon {
                    color: rgba(255, 255, 255, 0.6);
                }

                .position-label {
                    color: rgba(255, 255, 255, 0.7);
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.open = true;
        this._loading = false;
        this._name = '';
        this._agentId = '';
        this._position = 'bottom-right';
        this._theme = 'dark';
    }

    async _handleCreate() {
        if (!this._name.trim()) {
            this.error('Введите название виджета');
            return;
        }

        if (!this._agentId.trim()) {
            this.error('Введите ID агента');
            return;
        }

        this._loading = true;
        this.requestUpdate();

        await this.services.get('embed').create({
            name: this._name.trim(),
            flow_id: this._agentId.trim(),
            position: this._position,
            theme: this._theme,
            status: 'active',
        });

        FrontendStore.setEmbedLoading(true);
        const configs = await this.services.get('embed').list();
        FrontendStore.setEmbedConfigs(configs);

        this.success('Виджет успешно создан');
        this._handleClose();
        this.dispatchEvent(new CustomEvent('created'));
    }

    close() {
        this.open = false;
        super.close();
        this.dispatchEvent(new CustomEvent('close'));
    }

    _handleClose() {
        this.close();
    }

    renderHeader() {
        return 'Создать виджет';
    }

    renderBody() {
        return html`
            <div class="form-group">
                <label class="form-label">Название виджета</label>
                <input
                    class="form-input"
                    type="text"
                    placeholder="Чат-поддержка"
                    .value=${this._name}
                    @input=${(e) => { this._name = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                />
                <div class="form-hint">Краткое описание виджета</div>
            </div>

            <div class="form-group">
                <label class="form-label">ID агента</label>
                <input
                    class="form-input"
                    type="text"
                    placeholder="support-agent"
                    .value=${this._agentId}
                    @input=${(e) => { this._agentId = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                />
                <div class="form-hint">Агент, который будет обрабатывать запросы</div>
            </div>

            <div class="form-group">
                <label class="form-label">Позиция на странице</label>
                <div class="position-options">
                    ${this._renderPositionOption('bottom-right', '↘', 'Справа внизу')}
                    ${this._renderPositionOption('bottom-left', '↙', 'Слева внизу')}
                    ${this._renderPositionOption('center', '◎', 'По центру')}
                    ${this._renderPositionOption('fullscreen', '⛶', 'На весь экран')}
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">Тема оформления</label>
                <select
                    class="form-select"
                    .value=${this._theme}
                    @change=${(e) => { this._theme = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                >
                    <option value="dark">Темная</option>
                    <option value="light">Светлая</option>
                    <option value="auto">Автоматическая</option>
                </select>
            </div>
        `;
    }

    renderFooter() {
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
                    ${this._loading ? 'Создание...' : 'Создать виджет'}
                </button>
            </div>
        `;
    }

    _renderPositionOption(value, icon, label) {
        return html`
            <div
                class="position-option ${this._position === value ? 'selected' : ''}"
                @click=${() => { if (!this._loading) { this._position = value; this.requestUpdate(); }}}
            >
                <div class="position-icon">${icon}</div>
                <div class="position-label">${label}</div>
            </div>
        `;
    }
}

customElements.define('create-embed-modal', CreateEmbedModal);
