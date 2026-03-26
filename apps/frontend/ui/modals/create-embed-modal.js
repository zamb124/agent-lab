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

            .flows-hint {
                font-size: var(--text-xs, 12px);
                color: var(--text-tertiary);
                margin-top: var(--space-2);
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
        this._flowId = '';
        this._skillId = 'default';
        this._flows = [];
        this._flowsLoading = true;
        this._position = 'bottom-right';
        this._theme = 'dark';
    }

    async connectedCallback() {
        super.connectedCallback();
        await this._loadFlows();
    }

    async _loadFlows() {
        this._flowsLoading = true;
        this.requestUpdate();
        try {
            this._flows = await this.services.get('flowsCatalog').listFlows();
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
            this._flows = [];
        }
        this._flowsLoading = false;
        this.requestUpdate();
    }

    _selectedFlow() {
        return this._flows.find((f) => f.flow_id === this._flowId) ?? null;
    }

    _skillChoices() {
        const flow = this._selectedFlow();
        if (!flow || flow.type !== 'local' || !flow.skills) {
            return [];
        }
        return Object.entries(flow.skills);
    }

    _onFlowChange(e) {
        this._flowId = e.target.value;
        const flow = this._selectedFlow();
        if (!flow || flow.type !== 'local') {
            this._skillId = 'default';
            this.requestUpdate();
            return;
        }
        const entries = flow.skills ? Object.keys(flow.skills) : [];
        if (entries.length === 0) {
            this._skillId = 'default';
            this.requestUpdate();
            return;
        }
        if (!entries.includes(this._skillId)) {
            this._skillId = entries.includes('default') ? 'default' : entries[0];
        }
        this.requestUpdate();
    }

    _onSkillChange(e) {
        this._skillId = e.target.value;
        this.requestUpdate();
    }

    async _handleCreate() {
        if (!this._name.trim()) {
            this.error('Введите название виджета');
            return;
        }

        if (!this._flowId.trim()) {
            this.error('Выберите flow');
            return;
        }

        const flow = this._selectedFlow();
        if (!flow) {
            this.error('Выберите корректный flow');
            return;
        }

        let skillId = 'default';
        if (flow.type === 'local' && flow.skills && Object.keys(flow.skills).length > 0) {
            skillId = this._skillId;
        }

        this._loading = true;
        this.requestUpdate();

        try {
            await this.services.get('embed').create({
                name: this._name.trim(),
                flow_id: this._flowId.trim(),
                skill_id: skillId,
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
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        } finally {
            this._loading = false;
            this.requestUpdate();
        }
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
        if (this._flowsLoading) {
            return html`<div class="loading-hint">Загрузка списка flows...</div>`;
        }

        const skillEntries = this._skillChoices();
        const showSkill = skillEntries.length > 0;

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
                <label class="form-label">Flow (агент)</label>
                <select
                    class="form-select"
                    .value=${this._flowId}
                    @change=${(e) => this._onFlowChange(e)}
                    ?disabled=${this._loading}
                >
                    <option value="">Выберите flow</option>
                    ${this._flows.map(
                        (f) => html`
                            <option value=${f.flow_id}>${f.name} (${f.flow_id})</option>
                        `,
                    )}
                </select>
                <div class="form-hint">Список из сервиса flows для текущей компании</div>
            </div>

            ${showSkill
                ? html`
                      <div class="form-group">
                          <label class="form-label">Skill</label>
                          <select
                              class="form-select"
                              .value=${this._skillId}
                              @change=${(e) => this._onSkillChange(e)}
                              ?disabled=${this._loading}
                          >
                              ${skillEntries.map(
                                  ([skillId, skill]) => html`
                                      <option value=${skillId}>
                                          ${skill.name ? `${skill.name} (${skillId})` : skillId}
                                      </option>
                                  `,
                              )}
                          </select>
                          <div class="form-hint">Точка входа внутри flow</div>
                      </div>
                  `
                : this._flowId
                  ? html`
                        <div class="form-group flows-hint">
                            Skill: default (внешний flow или нет skills в конфиге).
                        </div>
                    `
                  : ''}

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
                    ?disabled=${this._loading || this._flowsLoading}
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
