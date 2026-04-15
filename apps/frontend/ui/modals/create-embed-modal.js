/**
 * Модальное окно для создания виджета
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/platform-icon.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { FrontendStore } from '../store/frontend.store.js';

export class CreateEmbedModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .flow-skill-row {
                display: grid;
                gap: var(--space-4, 16px);
                margin-bottom: var(--space-5, 20px);
            }

            .flow-skill-row .form-group {
                margin-bottom: 0;
            }

            .flow-skill-row--split {
                grid-template-columns: 1fr 1fr;
            }

            @media (max-width: 520px) {
                .flow-skill-row--split {
                    grid-template-columns: 1fr;
                }
            }

            .position-options {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 12px;
            }

            .position-option {
                padding: 16px;
                background: var(--glass-tint-subtle);
                border: 2px solid var(--border-subtle);
                border-radius: 14px;
                cursor: pointer;
                transition: background 0.2s ease, border-color 0.2s ease;
                text-align: center;
            }

            .position-option:hover {
                background: var(--glass-tint-medium);
                border-color: var(--border-default);
            }

            .position-option.selected {
                background: var(--accent-subtle);
                border-color: rgba(153, 166, 249, 0.4);
            }

            .position-icon {
                font-size: 24px;
                margin-bottom: 8px;
                color: var(--text-secondary);
                line-height: 1.2;
            }

            .position-option.selected .position-icon {
                color: var(--accent);
            }

            .position-label {
                font-size: 13px;
                font-weight: 500;
                color: var(--text-primary);
            }

            .position-option.selected .position-label {
                color: var(--text-primary);
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

            .theme-label-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3, 12px);
                flex-wrap: wrap;
            }

            .theme-label-row .form-label {
                margin-bottom: 0;
            }

            .theme-chips {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                flex-shrink: 0;
            }

            .theme-chip {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 44px;
                height: 40px;
                padding: 0 12px;
                box-sizing: border-box;
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md, 12px);
                background: var(--glass-tint-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition:
                    border-color 0.15s ease,
                    background 0.15s ease,
                    color 0.15s ease;
            }

            .theme-chip:hover:not(:disabled) {
                border-color: var(--border-strong);
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }

            .theme-chip.selected {
                border-color: var(--accent);
                background: var(--accent-subtle);
                color: var(--accent);
            }

            .theme-chip:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .theme-chip platform-icon {
                display: block;
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
        this._showLauncher = true;
        this._allowedOriginsText = '';
        this._assistantTitle = '';
        this._interfaceLocale = 'auto';
        this._editConfig = null;
    }

    setEditConfig(config) {
        this._editConfig = config;
        this._name = config.name;
        this._flowId = String(config.flow_id ?? config.flowId ?? '').trim();
        this._skillId = config.skill_id || 'default';
        this._position = config.position || 'bottom-right';
        this._theme = config.theme || 'dark';
        this._showLauncher = config.show_launcher !== false;
        this._allowedOriginsText = Array.isArray(config.allowed_origins) ? config.allowed_origins.join('\n') : '';
        this._assistantTitle = config.assistant_title || '';
        this._interfaceLocale = config.interface_locale || 'auto';
        this.requestUpdate();
    }

    get _isEditMode() {
        return this._editConfig !== null;
    }

    async connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        await this._loadFlows();
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    async _loadFlows() {
        this._flowsLoading = true;
        this.requestUpdate();
        try {
            const list = await this.services.get('flowsCatalog').listFlows();
            this._flows = Array.isArray(list) ? list : [];
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
            this._flows = [];
        }
        this._flowsLoading = false;
        this.requestUpdate();
    }

    _getFlowId(flow) {
        if (!flow || typeof flow !== 'object') {
            return '';
        }
        if (typeof flow.flow_id === 'string') {
            return flow.flow_id.trim();
        }
        if (typeof flow.id === 'string') {
            return flow.id.trim();
        }
        return '';
    }

    _normalizeFlowId(value) {
        return String(value ?? '').trim();
    }

    _isSameFlowId(left, right) {
        return this._normalizeFlowId(left) === this._normalizeFlowId(right);
    }

    _flowsList() {
        const flows = (Array.isArray(this._flows) ? this._flows : [])
            .map((flow) => {
                const flowId = this._getFlowId(flow);
                if (!flowId) {
                    return null;
                }
                const flowName = typeof flow.name === 'string' && flow.name.trim() ? flow.name.trim() : flowId;
                const flowType = typeof flow.type === 'string' && flow.type.trim()
                    ? flow.type.trim().toLowerCase()
                    : 'external';
                return {
                    ...flow,
                    flow_id: flowId,
                    name: flowName,
                    type: flowType,
                };
            })
            .filter((flow) => flow !== null);
        const currentFlowId = this._normalizeFlowId(this._flowId);
        if (!currentFlowId) {
            return flows;
        }
        const alreadyPresent = flows.some((f) => this._isSameFlowId(f.flow_id, currentFlowId));
        if (alreadyPresent) {
            return flows;
        }
        flows.push({
            flow_id: currentFlowId,
            name: currentFlowId,
            type: 'external',
            skills: {},
        });
        return flows;
    }

    _selectedFlow() {
        const currentFlowId = this._normalizeFlowId(this._flowId);
        if (!currentFlowId) {
            return null;
        }
        return this._flowsList().find((f) => this._isSameFlowId(f.flow_id, currentFlowId)) ?? null;
    }

    _skillChoices() {
        const flow = this._selectedFlow();
        if (!flow || flow.type !== 'local' || !flow.skills) {
            return [];
        }
        return Object.entries(flow.skills);
    }

    _onFlowChange(e) {
        this._flowId = String(e.target.value || '').trim();
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
        const td = (k, p) => this.i18n.t(k, p ?? {});
        if (!this._name.trim()) {
            this.error(td('embed_create_modal.err_name'));
            return;
        }

        if (!this._flowId.trim()) {
            this.error(td('embed_create_modal.err_flow'));
            return;
        }

        const flow = this._selectedFlow();
        if (!flow) {
            this.error(td('embed_create_modal.err_flow_invalid'));
            return;
        }

        let skillId = 'default';
        if (flow.type === 'local' && flow.skills && Object.keys(flow.skills).length > 0) {
            skillId = this._skillId;
        }

        this._loading = true;
        this.requestUpdate();

        const allowedOrigins = this._allowedOriginsText
            .split('\n')
            .map((origin) => origin.trim())
            .filter((origin) => origin.length > 0);

        const payload = {
            name: this._name.trim(),
            flow_id: this._flowId.trim(),
            skill_id: skillId,
            allowed_origins: allowedOrigins,
            position: this._position,
            theme: this._theme,
            show_launcher: this._showLauncher,
            assistant_title: this._assistantTitle.trim() || null,
            interface_locale: this._interfaceLocale,
            status: 'active',
        };

        const embedService = this.services.get('embed');

        if (this._isEditMode) {
            await embedService.update(this._editConfig.embed_id, payload);
        } else {
            await embedService.create(payload);
        }

        FrontendStore.setEmbedLoading(true);
        const page = await embedService.listConfigs();
        FrontendStore.setEmbedConfigs(page.items);

        const toastKey = this._isEditMode ? 'embed_create_modal.toast_updated' : 'embed_create_modal.toast_created';
        this.success(td(toastKey));
        this._handleClose();
        this.dispatchEvent(new CustomEvent(this._isEditMode ? 'updated' : 'created'));

        this._loading = false;
        this.requestUpdate();
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
        const key = this._isEditMode ? 'embed_create_modal.header_edit' : 'embed_create_modal.header';
        return this.i18n.t(key, {});
    }

    renderBody() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        if (this._flowsLoading) {
            return html`<div class="loading-hint">${td('embed_create_modal.loading_flows')}</div>`;
        }

        const skillEntries = this._skillChoices();
        const showSkill = skillEntries.length > 0;

        return html`
            <div class="form-group">
                <label class="form-label">${td('embed_create_modal.label_name')}</label>
                <input
                    class="form-input"
                    type="text"
                    placeholder=${td('embed_create_modal.placeholder_name')}
                    .value=${this._name}
                    @input=${(e) => { this._name = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                />
                <div class="form-hint">${td('embed_create_modal.name_hint')}</div>
            </div>

            <div class="flow-skill-row ${showSkill ? 'flow-skill-row--split' : ''}">
                <div class="form-group">
                    <label class="form-label">${td('embed_create_modal.label_flow')}</label>
                    <select
                        class="form-select"
                        .value=${this._flowId}
                        @change=${(e) => this._onFlowChange(e)}
                        ?disabled=${this._loading}
                    >
                        <option value="">${td('embed_create_modal.flow_placeholder')}</option>
                        ${this._flowsList().map(
                            (f) => html`
                                <option value=${f.flow_id} ?selected=${this._isSameFlowId(f.flow_id, this._flowId)}>
                                    ${f.name} (${f.flow_id})
                                </option>
                            `,
                        )}
                    </select>
                    <div class="form-hint">${td('embed_create_modal.flow_hint')}</div>
                </div>

                ${showSkill
                    ? html`
                          <div class="form-group">
                              <label class="form-label">${td('embed_create_modal.label_skill')}</label>
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
                              <div class="form-hint">${td('embed_create_modal.skill_hint')}</div>
                          </div>
                      `
                    : this._flowId
                      ? html`
                            <div class="form-group flows-hint">
                                ${td('embed_create_modal.skill_default_hint')}
                            </div>
                        `
                      : html``}
            </div>

            <div class="flow-skill-row flow-skill-row--split">
                <div class="form-group">
                    <label class="form-label">${td('embed_create_modal.label_assistant_title')}</label>
                    <input
                        class="form-input"
                        type="text"
                        placeholder=${td('embed_create_modal.placeholder_assistant_title')}
                        .value=${this._assistantTitle}
                        @input=${(e) => { this._assistantTitle = e.target.value; this.requestUpdate(); }}
                        ?disabled=${this._loading}
                    />
                    <div class="form-hint">${td('embed_create_modal.assistant_title_hint')}</div>
                </div>
                <div class="form-group">
                    <label class="form-label">${td('embed_create_modal.label_interface_locale')}</label>
                    <select
                        class="form-select"
                        .value=${this._interfaceLocale}
                        @change=${(e) => { this._interfaceLocale = e.target.value; this.requestUpdate(); }}
                        ?disabled=${this._loading}
                    >
                        <option value="auto">${td('embed_create_modal.locale_auto')}</option>
                        <option value="ru">${td('embed_create_modal.locale_ru')}</option>
                        <option value="en">${td('embed_create_modal.locale_en')}</option>
                    </select>
                    <div class="form-hint">${td('embed_create_modal.interface_locale_hint')}</div>
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">${td('embed_create_modal.label_allowed_origins')}</label>
                <textarea
                    class="form-textarea"
                    rows="4"
                    placeholder=${td('embed_create_modal.placeholder_allowed_origins')}
                    .value=${this._allowedOriginsText}
                    @input=${(e) => { this._allowedOriginsText = e.target.value; this.requestUpdate(); }}
                    ?disabled=${this._loading}
                ></textarea>
                <div class="form-hint">${td('embed_create_modal.allowed_origins_hint')}</div>
            </div>

            <div class="form-group">
                <label class="form-label">${td('embed_create_modal.position_label')}</label>
                <div class="position-options">
                    ${this._renderPositionOption('bottom-right', '↘', td('embed_create_modal.pos_br'))}
                    ${this._renderPositionOption('bottom-left', '↙', td('embed_create_modal.pos_bl'))}
                    ${this._renderPositionOption('center', '◎', td('embed_create_modal.pos_center'))}
                    ${this._renderPositionOption('fullscreen', '⛶', td('embed_create_modal.pos_full'))}
                </div>
            </div>

            <div class="form-group">
                <div class="theme-label-row">
                    <span class="form-label">${td('embed_create_modal.theme_label')}</span>
                    <div class="theme-chips" role="group" aria-label=${td('embed_create_modal.theme_group_aria')}>
                        ${this._renderThemeChip('light', 'sun', td('embed_create_modal.theme_light'))}
                        ${this._renderThemeChip('dark', 'moon', td('embed_create_modal.theme_dark'))}
                        ${this._renderThemeChip('auto', 'theme-auto', td('embed_create_modal.theme_auto'))}
                    </div>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">
                    <input
                        type="checkbox"
                        .checked=${this._showLauncher}
                        @change=${(e) => { this._showLauncher = e.target.checked; this.requestUpdate(); }}
                        ?disabled=${this._loading}
                    />
                    ${td('embed_create_modal.label_show_launcher')}
                </label>
                <div class="form-hint">${td('embed_create_modal.show_launcher_hint')}</div>
            </div>
        `;
    }

    renderSaveHeaderButton() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        const loadingKey = this._isEditMode ? 'embed_create_modal.saving' : 'embed_create_modal.creating';
        const submitKey = this._isEditMode ? 'embed_create_modal.save' : 'embed_create_modal.submit';
        const title = this._loading ? td(loadingKey) : td(submitKey);
        return this._renderHeaderSaveIcon({
            onClick: () => this._handleCreate(),
            disabled: this._loading || this._flowsLoading,
            title,
        });
    }

    renderFooter() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        return html`
            <div class="actions-row">
                <button
                    class="btn btn-secondary"
                    @click=${this._handleClose}
                    ?disabled=${this._loading}
                >
                    ${td('embed_create_modal.cancel')}
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

    _renderThemeChip(value, iconName, title) {
        const selected = this._theme === value;
        return html`
            <button
                type="button"
                class="theme-chip ${selected ? 'selected' : ''}"
                title=${title}
                aria-label=${title}
                aria-pressed=${selected ? 'true' : 'false'}
                ?disabled=${this._loading}
                @click=${() => {
                    if (this._loading) {
                        return;
                    }
                    this._theme = value;
                    this.requestUpdate();
                }}
            >
                <platform-icon name=${iconName} size="20"></platform-icon>
            </button>
        `;
    }
}

customElements.define('create-embed-modal', CreateEmbedModal);
