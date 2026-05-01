/**
 * Create / edit embed modal — полный wizard конфигурации виджета.
 *
 * Если передан `embedConfig` — режим редактирования (PATCH /configs/{embed_id}).
 * Без него — режим создания (POST /configs).
 *
 * Поля соответствуют CreateEmbedConfigRequest/UpdateEmbedConfigRequest
 * (apps/frontend/api/embed_configs.py): name, flow_id, branch_id,
 * allowed_origins, theme, position, show_launcher, primary_color,
 * greeting_message, assistant_title, interface_locale, placeholder, branding.
 *
 * Skill заблокирован для external flows и flows без skills (бэк подставит default).
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

const POSITIONS = Object.freeze([
    { value: 'bottom-right', key: 'pos_br' },
    { value: 'bottom-left',  key: 'pos_bl' },
    { value: 'center',       key: 'pos_center' },
    { value: 'fullscreen',   key: 'pos_full' },
]);

const THEMES = Object.freeze([
    { value: 'light', key: 'theme_light' },
    { value: 'dark',  key: 'theme_dark' },
    { value: 'auto',  key: 'theme_auto' },
]);

const LOCALES = Object.freeze([
    { value: 'auto', key: 'locale_auto' },
    { value: 'ru',   key: 'locale_ru' },
    { value: 'en',   key: 'locale_en' },
]);

export class FrontendCreateEmbedModal extends PlatformFormModal {
    static modalKind = 'frontend.embed_create';

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
            .form-grid .form-group.full { grid-column: 1 / -1; }
            .hint { font-size: var(--text-xs); color: var(--text-tertiary); margin-top: 4px; }
            .radio-row { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .radio-row label {
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer; font-size: var(--text-sm);
                display: flex; align-items: center; gap: var(--space-2);
            }
            .radio-row label.checked { background: var(--glass-solid-medium); border-color: var(--accent); }
            .switch-row { display: flex; align-items: center; gap: var(--space-2); }
            textarea.form-input { min-height: 70px; font-family: var(--font-mono); font-size: var(--text-xs); }
            input[type=color] { width: 60px; height: 36px; padding: 0; border-radius: var(--radius-md); border: 1px solid var(--glass-border-subtle); }
        `,
    ];

    static properties = {
        ...PlatformFormModal.properties,
        embedConfig: { type: Object },
        _name: { state: true },
        _flowId: { state: true },
        _skillId: { state: true },
        _theme: { state: true },
        _position: { state: true },
        _interfaceLocale: { state: true },
        _allowedOrigins: { state: true },
        _showLauncher: { state: true },
        _branding: { state: true },
        _primaryColor: { state: true },
        _assistantTitle: { state: true },
        _greetingMessage: { state: true },
        _placeholder: { state: true },
    };

    constructor() {
        super();
        this.embedConfig = null;
        this._name = '';
        this._flowId = '';
        this._skillId = 'default';
        this._theme = 'dark';
        this._position = 'bottom-right';
        this._interfaceLocale = 'auto';
        this._allowedOrigins = '';
        this._showLauncher = true;
        this._branding = true;
        this._primaryColor = '#6366f1';
        this._assistantTitle = '';
        this._greetingMessage = '';
        this._placeholder = '';
        this.size = 'lg';
        this._configs = this.useResource('frontend/embed_configs');
        this._catalog = this.useOp('frontend/flows_catalog');
        this._loaded = false;
        this._populated = false;
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        const isEdit = !!this.embedConfig;
        this.title = isEdit
            ? this.t('embed_create_modal.header_edit')
            : this.t('embed_create_modal.header');
        if (changed.has('open') && this.open && !this._loaded) {
            this._loaded = true;
            this._catalog.run(null);
        }
        if (changed.has('embedConfig') && this.embedConfig && !this._populated) {
            this._populated = true;
            const c = this.embedConfig;
            const _str = (v, def) => (typeof v === 'string' && v !== '' ? v : def);
            this._name = _str(c.name, '');
            this._flowId = _str(c.flow_id, '');
            this._skillId = _str(c.branch_id, 'default');
            this._theme = _str(c.theme, 'dark');
            this._position = _str(c.position, 'bottom-right');
            this._interfaceLocale = _str(c.interface_locale, 'auto');
            this._allowedOrigins = Array.isArray(c.allowed_origins) ? c.allowed_origins.join('\n') : '';
            this._showLauncher = c.show_launcher !== false;
            this._branding = c.branding !== false;
            this._primaryColor = _str(c.primary_color, '#6366f1');
            this._assistantTitle = _str(c.assistant_title, '');
            this._greetingMessage = _str(c.greeting_message, '');
            this._placeholder = _str(c.placeholder, '');
        }
    }

    _flows() {
        const r = this._catalog.lastResult;
        if (!r || !Array.isArray(r.flows)) return [];
        return r.flows;
    }

    _selectedFlow() {
        const found = this._flows().find((f) => f.flow_id === this._flowId);
        return found ? found : null;
    }

    _flowSkills() {
        const flow = this._selectedFlow();
        if (!flow) return [];
        const skills = flow.skills;
        if (Array.isArray(skills)) return skills.map((s) => ({ id: s, name: s }));
        if (!skills || typeof skills !== 'object') return [];
        return Object.entries(skills).map(([id, v]) => ({
            id,
            name: (v && typeof v.name === 'string' && v.name !== '') ? v.name : id,
        }));
    }

    _skillSelectorEnabled() {
        const flow = this._selectedFlow();
        if (!flow) return false;
        if (flow.type === 'external') return false;
        return this._flowSkills().length > 0;
    }

    validateForm() {
        const errors = {};
        if (!this._name.trim()) errors.name = this.t('embed_create_modal.err_name');
        if (!this._flowId) errors.flow_id = this.t('embed_create_modal.err_flow');
        return errors;
    }

    _parseOrigins() {
        return this._allowedOrigins
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean);
    }

    async handleSubmit() {
        const isEdit = !!this.embedConfig;
        const payload = {
            name: this._name.trim(),
            flow_id: this._flowId,
            branch_id: this._skillSelectorEnabled() ? this._skillId : 'default',
            allowed_origins: this._parseOrigins(),
            theme: this._theme,
            position: this._position,
            show_launcher: this._showLauncher,
            branding: this._branding,
            primary_color: this._primaryColor,
            assistant_title: this._assistantTitle.trim() || null,
            greeting_message: this._greetingMessage.trim() || null,
            interface_locale: this._interfaceLocale,
            placeholder: this._placeholder.trim() || null,
        };
        if (isEdit) {
            this._configs.update(this.embedConfig.embed_id, payload);
        } else {
            this._configs.create(payload);
        }
        this.closeAfterSave();
    }

    _renderRadioRow(items, current, onPick, namespace = 'embed_create_modal') {
        return html`
            <div class="radio-row">
                ${items.map((item) => html`
                    <label class=${current === item.value ? 'checked' : ''}>
                        <input
                            type="radio"
                            .checked=${current === item.value}
                            @change=${() => { onPick(item.value); this.isDirty = true; }}
                        />
                        ${this.t(`${namespace}.${item.key}`)}
                    </label>
                `)}
            </div>
        `;
    }

    renderBody() {
        const flows = this._flows();
        const flowsLoading = this._catalog.busy;
        const skillEnabled = this._skillSelectorEnabled();
        const skills = this._flowSkills();
        return html`
            <form @submit=${this._onSubmit}>
                <div class="form-grid">
                    <div class="form-group full">
                        <label class="form-label">${this.t('embed_create_modal.label_name')}</label>
                        <input
                            class="form-input"
                            name="name"
                            .value=${this._name}
                            placeholder=${this.t('embed_create_modal.placeholder_name')}
                            @input=${(e) => { this._name = e.target.value; this.isDirty = true; }}
                            autofocus
                        />
                        <div class="hint">${this.t('embed_create_modal.name_hint')}</div>
                        ${this.renderFieldError('name')}
                    </div>

                    <div class="form-group">
                        <label class="form-label">${this.t('embed_create_modal.label_flow')}</label>
                        ${flowsLoading
                            ? html`<div class="hint">${this.t('embed_create_modal.loading_flows')}</div>`
                            : html`
                                <select
                                    class="form-select"
                                    .value=${this._flowId}
                                    @change=${(e) => { this._flowId = e.target.value; this._skillId = 'default'; this.isDirty = true; }}
                                >
                                    <option value="">${this.t('embed_create_modal.flow_placeholder')}</option>
                                    ${flows.map((f) => html`
                                        <option value=${f.flow_id} ?selected=${this._flowId === f.flow_id}>
                                            ${typeof f.name === 'string' && f.name !== '' ? f.name : f.flow_id}
                                        </option>
                                    `)}
                                </select>
                            `}
                        <div class="hint">${this.t('embed_create_modal.flow_hint')}</div>
                        ${this.renderFieldError('flow_id')}
                    </div>

                    <div class="form-group">
                        <label class="form-label">${this.t('embed_create_modal.label_skill')}</label>
                        ${skillEnabled
                            ? html`
                                <select
                                    class="form-select"
                                    .value=${this._skillId}
                                    @change=${(e) => { this._skillId = e.target.value; this.isDirty = true; }}
                                >
                                    ${branches.map((s) => html`
                                        <option value=${s.id} ?selected=${this._skillId === s.id}>${s.name}</option>
                                    `)}
                                </select>
                                <div class="hint">${this.t('embed_create_modal.skill_hint')}</div>
                            `
                            : html`<div class="hint">${this.t('embed_create_modal.skill_default_hint')}</div>`}
                    </div>

                    <div class="form-group full">
                        <label class="form-label">${this.t('embed_create_modal.position_label')}</label>
                        ${this._renderRadioRow(POSITIONS, this._position, (v) => { this._position = v; })}
                    </div>

                    <div class="form-group full">
                        <label class="form-label" aria-label=${this.t('embed_create_modal.theme_group_aria')}>
                            ${this.t('embed_create_modal.theme_label')}
                        </label>
                        ${this._renderRadioRow(THEMES, this._theme, (v) => { this._theme = v; })}
                    </div>

                    <div class="form-group">
                        <label class="form-label">${this.t('embed_create_modal.label_assistant_title')}</label>
                        <input
                            class="form-input"
                            .value=${this._assistantTitle}
                            placeholder=${this.t('embed_create_modal.placeholder_assistant_title')}
                            @input=${(e) => { this._assistantTitle = e.target.value; this.isDirty = true; }}
                        />
                        <div class="hint">${this.t('embed_create_modal.assistant_title_hint')}</div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">${this.t('embed_create_modal.label_interface_locale')}</label>
                        <select
                            class="form-select"
                            .value=${this._interfaceLocale}
                            @change=${(e) => { this._interfaceLocale = e.target.value; this.isDirty = true; }}
                        >
                            ${LOCALES.map((l) => html`
                                <option value=${l.value} ?selected=${this._interfaceLocale === l.value}>
                                    ${this.t(`embed_create_modal.${l.key}`)}
                                </option>
                            `)}
                        </select>
                        <div class="hint">${this.t('embed_create_modal.interface_locale_hint')}</div>
                    </div>

                    <div class="form-group full">
                        <label class="form-label">${this.t('embed_create_modal.label_allowed_origins')}</label>
                        <textarea
                            class="form-input"
                            .value=${this._allowedOrigins}
                            placeholder=${this.t('embed_create_modal.placeholder_allowed_origins')}
                            @input=${(e) => { this._allowedOrigins = e.target.value; this.isDirty = true; }}
                        ></textarea>
                        <div class="hint">${this.t('embed_create_modal.allowed_origins_hint')}</div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">primary_color</label>
                        <input
                            type="color"
                            .value=${this._primaryColor}
                            @input=${(e) => { this._primaryColor = e.target.value; this.isDirty = true; }}
                        />
                    </div>

                    <div class="form-group">
                        <label class="switch-row">
                            <input
                                type="checkbox"
                                .checked=${this._showLauncher}
                                @change=${(e) => { this._showLauncher = e.target.checked; this.isDirty = true; }}
                            />
                            <span>${this.t('embed_create_modal.label_show_launcher')}</span>
                        </label>
                        <div class="hint">${this.t('embed_create_modal.show_launcher_hint')}</div>
                    </div>
                </div>
            </form>
        `;
    }

    renderFooter() {
        const isEdit = !!this.embedConfig;
        const canSubmit = this._name.trim().length > 0 && !!this._flowId && !this.loading;
        const submitLabel = isEdit
            ? (this.loading ? this.t('embed_create_modal.saving') : this.t('embed_create_modal.save'))
            : (this.loading ? this.t('embed_create_modal.creating') : this.t('embed_create_modal.submit'));
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('embed_create_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${!canSubmit}
                    @click=${() => this._performSave()}
                >
                    ${submitLabel}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-create-embed-modal', FrontendCreateEmbedModal);
registerModalKind(FrontendCreateEmbedModal.modalKind, 'frontend-create-embed-modal');
