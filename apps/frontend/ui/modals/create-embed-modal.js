/**
 * Модалка создания / редактирования embed — полный wizard конфигурации виджета.
 *
 * Если передан `embedConfig` — режим редактирования (PATCH /configs/{embed_id}).
 * Без него — режим создания (POST /configs).
 *
 * Поля соответствуют CreateEmbedConfigRequest/UpdateEmbedConfigRequest
 * (apps/frontend/api/embed_configs.py): в т.ч. greeting_message, placeholder.
 *
 * Branch (branch_id): список из flow.branches в ответе GET /flows/api/v1/flows/.
 * Заблокирован для external и для LOCAL без веток (бэк подставит default).
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

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
            .form-grid > .full { grid-column: 1 / -1; }
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
            input[type=color] { width: 60px; height: 36px; padding: 0; border-radius: var(--radius-md); border: 1px solid var(--glass-border-subtle); }
        `,
    ];

    static properties = {
        ...PlatformFormModal.properties,
        embedConfig: { type: Object },
        _name: { state: true },
        _flowId: { state: true },
        _branchId: { state: true },
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
        _landingVisible: { state: true },
        _landingCardImageUrl: { state: true },
        _landingSortOrder: { state: true },
        _guestMaxUserMessages: { state: true },
        _voiceEnabled: { state: true },
        _voiceDefaultOn: { state: true },
    };

    constructor() {
        super();
        this.embedConfig = null;
        this._name = '';
        this._flowId = '';
        this._branchId = 'default';
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
        this._landingVisible = false;
        this._landingCardImageUrl = '';
        this._landingSortOrder = 0;
        this._guestMaxUserMessages = '';
        this._voiceEnabled = true;
        this._voiceDefaultOn = false;
        this.size = 'lg';
        this._configs = this.useResource('frontend/embed_configs');
        this._catalog = this.useOp('frontend/flows_catalog');
        this._activeCompanySel = this.select((s) => s.companies.active);
        this._loaded = false;
        this._populated = false;
    }

    _isSystemCompany() {
        const c = this._activeCompanySel.value;
        return c !== null && typeof c === 'object' && c.company_id === 'system';
    }

    _resetCreateFormFields() {
        this._name = '';
        this._flowId = '';
        this._branchId = 'default';
        this._theme = 'dark';
        this._position = 'bottom-right';
        this._interfaceLocale = 'auto';
        this._allowedOrigins = '';
        this._showLauncher = true;
        this._branding = true;
        this._primaryColor = '#6366f1';
        this._assistantTitle = '';
        this._greetingMessage = '';
        this._landingVisible = false;
        this._landingCardImageUrl = '';
        this._landingSortOrder = 0;
        this._guestMaxUserMessages = '';
        this._voiceEnabled = true;
        this._voiceDefaultOn = false;
        this._placeholder = this.t('embed_create_modal.default_message_placeholder');
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
        if (changed.has('open') && this.open && !this.embedConfig) {
            this._populated = false;
            this._resetCreateFormFields();
        }
        if (changed.has('embedConfig')) {
            this._populated = false;
        }
        if (this.embedConfig && !this._populated) {
            this._populated = true;
            const c = this.embedConfig;
            if (typeof c.name === 'string') this._name = c.name;
            if (typeof c.flow_id === 'string') this._flowId = c.flow_id;
            if (typeof c.branch_id === 'string') this._branchId = c.branch_id;
            if (typeof c.theme === 'string') this._theme = c.theme;
            if (typeof c.position === 'string') this._position = c.position;
            if (typeof c.interface_locale === 'string') this._interfaceLocale = c.interface_locale;
            if (Array.isArray(c.allowed_origins)) {
                this._allowedOrigins = c.allowed_origins.join('\n');
            }
            this._showLauncher = c.show_launcher !== false;
            this._branding = c.branding !== false;
            if (typeof c.primary_color === 'string') this._primaryColor = c.primary_color;
            if (typeof c.assistant_title === 'string') this._assistantTitle = c.assistant_title;
            if (typeof c.greeting_message === 'string') this._greetingMessage = c.greeting_message;
            if (typeof c.placeholder === 'string' && c.placeholder.trim() !== '') {
                this._placeholder = c.placeholder;
            } else {
                this._placeholder = this.t('embed_create_modal.default_message_placeholder');
            }
            if (typeof c.landing_visible === 'boolean') this._landingVisible = c.landing_visible;
            if (typeof c.landing_card_image_url === 'string') this._landingCardImageUrl = c.landing_card_image_url;
            if (typeof c.landing_sort_order === 'number') this._landingSortOrder = c.landing_sort_order;
            if (typeof c.guest_max_user_messages === 'number' && Number.isFinite(c.guest_max_user_messages)) {
                this._guestMaxUserMessages = String(Math.trunc(c.guest_max_user_messages));
            } else {
                this._guestMaxUserMessages = '';
            }
            this._voiceEnabled = c.voice_enabled === true;
            this._voiceDefaultOn = c.voice_default_on === true;
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

    /**
     * Ветки flow в API: `branches: { [branch_id]: { name, ... } }`.
     */
    _branchEntriesFromFlow(flow) {
        if (!flow) return [];
        const branches = flow.branches;
        if (branches && typeof branches === 'object' && !Array.isArray(branches)) {
            const raw = Object.entries(branches);
            if (raw.length > 0) {
                const mapped = raw.map(([id, v]) => ({
                    id,
                    name:
                        v && typeof v === 'object' && typeof v.name === 'string' && v.name !== ''
                            ? v.name
                            : id,
                }));
                mapped.sort((a, b) => {
                    if (a.id === 'default') return -1;
                    if (b.id === 'default') return 1;
                    return a.id.localeCompare(b.id);
                });
                return mapped;
            }
        }
        return [];
    }

    _flowBranches() {
        return this._branchEntriesFromFlow(this._selectedFlow());
    }

    _initialBranchIdForFlow(flow) {
        const entries = this._branchEntriesFromFlow(flow);
        if (entries.length === 0) return 'default';
        const ids = entries.map((e) => e.id);
        if (ids.includes('default')) return 'default';
        return entries[0].id;
    }

    _branchSelectorEnabled() {
        const flow = this._selectedFlow();
        if (!flow) return false;
        if (flow.type === 'external') return false;
        return this._flowBranches().length > 0;
    }

    validateForm() {
        const errors = {};
        if (!this._name.trim()) errors.name = this.t('embed_create_modal.err_name');
        if (!this._flowId) errors.flow_id = this.t('embed_create_modal.err_flow');
        if (this._isSystemCompany() && this._landingVisible && !this._landingCardImageUrl.trim()) {
            errors.landing_image = this.t('embed_create_modal.err_landing_image');
        }
        if (this._guestMaxUserMessages.trim() !== '') {
            const n = Number(this._guestMaxUserMessages.trim());
            if (!Number.isFinite(n) || Math.trunc(n) !== n || n < 1 || n > 500) {
                errors.guest_max_user_messages = this.t('embed_create_modal.err_guest_max_user_messages');
            }
        }
        if (!this._placeholder.trim()) {
            errors.placeholder = this.t('embed_create_modal.err_message_placeholder');
        }
        if (
            this._flowId
            && !this._catalog.busy
            && this._flows().length > 0
            && !this._flows().some((f) => f.flow_id === this._flowId)
        ) {
            errors.flow_id = this.t('embed_create_modal.err_flow_stale');
        }
        return errors;
    }

    _parseOrigins() {
        return this._allowedOrigins
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean);
    }

    /**
     * Ожидает завершения create/update коллекции по causation_id (без закрытия модалки при ошибке).
     * @returns {Promise<{ ok: true } | { ok: false, message: string }>}
     */
    _awaitEmbedWrite(isEdit, payload) {
        const ev = this._configs.resource.events;
        const bus = this.bus;
        if (isEdit) {
            const requested = this._configs.update(this.embedConfig.embed_id, payload);
            if (!requested || typeof requested.id !== 'string') {
                return Promise.resolve({ ok: false, message: this.t('embed_create_modal.err_save_dispatch') });
            }
            const rid = requested.id;
            return new Promise((resolve) => {
                let offOk = null;
                let offFail = null;
                const done = (out) => {
                    if (typeof offOk === 'function') offOk();
                    if (typeof offFail === 'function') offFail();
                    resolve(out);
                };
                offOk = bus.subscribeType(ev.UPDATED, (e) => {
                    if (!e.meta || e.meta.causation_id !== rid) return;
                    done({ ok: true });
                });
                offFail = bus.subscribeType(ev.UPDATE_FAILED, (e) => {
                    if (!e.meta || e.meta.causation_id !== rid) return;
                    const msg = e.payload && typeof e.payload.message === 'string' && e.payload.message !== ''
                        ? e.payload.message
                        : this.t('embed_create_modal.err_save_generic');
                    done({ ok: false, message: msg });
                });
            });
        }
        const requested = this._configs.create(payload);
        if (!requested || typeof requested.id !== 'string') {
            return Promise.resolve({ ok: false, message: this.t('embed_create_modal.err_save_concurrent') });
        }
        const rid = requested.id;
        return new Promise((resolve) => {
            let offOk = null;
            let offFail = null;
            const done = (out) => {
                if (typeof offOk === 'function') offOk();
                if (typeof offFail === 'function') offFail();
                resolve(out);
            };
            offOk = bus.subscribeType(ev.CREATED, (e) => {
                if (!e.meta || e.meta.causation_id !== rid) return;
                done({ ok: true });
            });
            offFail = bus.subscribeType(ev.CREATE_FAILED, (e) => {
                if (!e.meta || e.meta.causation_id !== rid) return;
                const msg = e.payload && typeof e.payload.message === 'string' && e.payload.message !== ''
                    ? e.payload.message
                    : this.t('embed_create_modal.err_save_generic');
                done({ ok: false, message: msg });
            });
        });
    }

    async handleSubmit() {
        const isEdit = !!this.embedConfig;
        const sys = this._isSystemCompany();
        const landingOn = sys && this._landingVisible;
        const gtrim = this._guestMaxUserMessages.trim();
        let guest_max_user_messages = null;
        if (gtrim !== '') {
            const gn = Number(gtrim);
            if (!Number.isFinite(gn)) {
                throw new Error('embed_create_modal: guest_max_user_messages must be a finite number');
            }
            guest_max_user_messages = Math.trunc(gn);
        }
        const payload = {
            name: this._name.trim(),
            flow_id: this._flowId,
            branch_id: this._branchSelectorEnabled() ? this._branchId : 'default',
            allowed_origins: this._parseOrigins(),
            theme: this._theme,
            position: this._position,
            show_launcher: this._showLauncher,
            branding: this._branding,
            primary_color: this._primaryColor,
            assistant_title: this._assistantTitle.trim() || null,
            greeting_message: this._greetingMessage.trim() || null,
            interface_locale: this._interfaceLocale,
            placeholder: this._placeholder.trim(),
            landing_visible: landingOn,
            landing_card_image_url: landingOn ? this._landingCardImageUrl.trim() : null,
            landing_sort_order: landingOn ? this._landingSortOrder : 0,
            guest_max_user_messages,
            voice_enabled: this._voiceEnabled,
            voice_default_on: this._voiceEnabled && this._voiceDefaultOn,
        };
        const result = await this._awaitEmbedWrite(isEdit, payload);
        if (!result.ok) {
            this.formErrors = { submit: result.message };
            this.toast('embed_create_modal.toast_save_failed', {
                type: 'error',
                vars: { detail: result.message },
            });
            return;
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
        const branchEnabled = this._branchSelectorEnabled();
        const branches = this._flowBranches();
        return html`
            <form @submit=${this._onSubmit}>
                <div class="form-grid">
                    ${this.renderFieldError('submit')}
                    <div class="full">
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('embed_create_modal.label_name')}
                            .value=${this._name}
                            .placeholder=${this.t('embed_create_modal.placeholder_name')}
                            .hint=${this.t('embed_create_modal.name_hint')}
                            @change=${(e) => { this._name = e.detail.value; this.isDirty = true; }}
                        ></platform-field>
                        ${this.renderFieldError('name')}
                    </div>

                    <div>
                        ${flowsLoading
                            ? html`<platform-field
                                  type="enum"
                                  mode="edit"
                                  .label=${this.t('embed_create_modal.label_flow')}
                                  .value=${''}
                                  .config=${{ values: [] }}
                                  ?disabled=${true}
                                  .placeholder=${this.t('embed_create_modal.loading_flows')}
                              ></platform-field>`
                            : html`<platform-field
                                  type="enum"
                                  mode="edit"
                                  .label=${this.t('embed_create_modal.label_flow')}
                                  .value=${this._flowId}
                                  .config=${{
                                      values: [
                                          { value: '', label: this.t('embed_create_modal.flow_placeholder') },
                                          ...flows.map((f) => ({
                                              value: f.flow_id,
                                              label: typeof f.name === 'string' && f.name !== '' ? f.name : f.flow_id,
                                          })),
                                      ],
                                  }}
                                  .hint=${this.t('embed_create_modal.flow_hint')}
                                  @change=${(e) => {
                                      this._flowId = e.detail.value;
                                      this._branchId = this._initialBranchIdForFlow(this._selectedFlow());
                                      this.isDirty = true;
                                  }}
                              ></platform-field>`}
                        ${this.renderFieldError('flow_id')}
                    </div>

                    <div>
                        ${branchEnabled
                            ? html`<platform-field
                                  type="enum"
                                  mode="edit"
                                  .label=${this.t('embed_create_modal.label_branch')}
                                  .value=${this._branchId}
                                  .config=${{
                                      values: branches.map((s) => ({ value: s.id, label: s.name })),
                                  }}
                                  .hint=${this.t('embed_create_modal.branch_hint')}
                                  @change=${(e) => { this._branchId = e.detail.value; this.isDirty = true; }}
                              ></platform-field>`
                            : html`<platform-field
                                  type="enum"
                                  mode="edit"
                                  .label=${this.t('embed_create_modal.label_branch')}
                                  .value=${''}
                                  .config=${{ values: [] }}
                                  ?disabled=${true}
                                  .hint=${this.t('embed_create_modal.branch_default_hint')}
                              ></platform-field>`}
                    </div>

                    ${this._isSystemCompany()
                        ? html`
                              <div class="form-group full">
                                  <label class="switch-row">
                                      <input
                                          type="checkbox"
                                          .checked=${this._landingVisible}
                                          @change=${(e) => {
                                              this._landingVisible = e.target.checked;
                                              this.isDirty = true;
                                          }}
                                      />
                                      <span>${this.t('embed_create_modal.label_landing_visible')}</span>
                                  </label>
                                  <div class="hint">${this.t('embed_create_modal.landing_visible_hint')}</div>
                              </div>
                              ${this._landingVisible
                                  ? html`
                                        <div class="full">
                                            <platform-field
                                                type="string"
                                                input-type="url"
                                                mode="edit"
                                                .label=${this.t('embed_create_modal.label_landing_card_image_url')}
                                                .value=${this._landingCardImageUrl}
                                                .placeholder=${this.t('embed_create_modal.placeholder_landing_card_image_url')}
                                                .hint=${this.t('embed_create_modal.landing_card_image_hint')}
                                                @change=${(e) => {
                                                    this._landingCardImageUrl = e.detail.value;
                                                    this.isDirty = true;
                                                }}
                                            ></platform-field>
                                            ${this.renderFieldError('landing_image')}
                                        </div>
                                        <platform-field
                                            type="integer"
                                            mode="edit"
                                            .label=${this.t('embed_create_modal.label_landing_sort_order')}
                                            .value=${this._landingSortOrder}
                                            .hint=${this.t('embed_create_modal.landing_sort_order_hint')}
                                            @change=${(e) => {
                                                this._landingSortOrder = typeof e.detail.value === 'number' ? e.detail.value : 0;
                                                this.isDirty = true;
                                            }}
                                        ></platform-field>
                                    `
                                  : ''}
                          `
                        : ''}

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

                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('embed_create_modal.label_assistant_title')}
                        .value=${this._assistantTitle}
                        .placeholder=${this.t('embed_create_modal.placeholder_assistant_title')}
                        .hint=${this.t('embed_create_modal.assistant_title_hint')}
                        @change=${(e) => { this._assistantTitle = e.detail.value; this.isDirty = true; }}
                    ></platform-field>

                    <div class="full">
                        <platform-field
                            type="text"
                            mode="edit"
                            .label=${this.t('embed_create_modal.label_greeting_message')}
                            .value=${this._greetingMessage}
                            .placeholder=${this.t('embed_create_modal.placeholder_greeting_message')}
                            .hint=${this.t('embed_create_modal.greeting_message_hint')}
                            @change=${(e) => { this._greetingMessage = e.detail.value; this.isDirty = true; }}
                        ></platform-field>
                    </div>

                    <div class="full">
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('embed_create_modal.label_message_placeholder')}
                            .value=${this._placeholder}
                            .placeholder=${this.t('embed_create_modal.default_message_placeholder')}
                            .hint=${this.t('embed_create_modal.message_placeholder_hint')}
                            @change=${(e) => { this._placeholder = e.detail.value; this.isDirty = true; }}
                        ></platform-field>
                        ${this.renderFieldError('placeholder')}
                    </div>

                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('embed_create_modal.label_interface_locale')}
                        .value=${this._interfaceLocale}
                        .config=${{
                            values: LOCALES.map((l) => ({
                                value: l.value,
                                label: this.t(`embed_create_modal.${l.key}`),
                            })),
                        }}
                        .hint=${this.t('embed_create_modal.interface_locale_hint')}
                        @change=${(e) => { this._interfaceLocale = e.detail.value; this.isDirty = true; }}
                    ></platform-field>

                    <div class="form-group full">
                        <label class="form-label">${this.t('embed_create_modal.section_voice')}</label>
                        <label class="switch-row">
                            <input
                                type="checkbox"
                                .checked=${this._voiceEnabled}
                                @change=${(e) => {
                                    this._voiceEnabled = e.target.checked;
                                    if (!this._voiceEnabled) {
                                        this._voiceDefaultOn = false;
                                    }
                                    this.isDirty = true;
                                }}
                            />
                            <span>${this.t('embed_create_modal.label_voice_enabled')}</span>
                        </label>
                        <div class="hint">${this.t('embed_create_modal.voice_enabled_hint')}</div>
                    </div>

                    <div class="form-group full">
                        <label class="switch-row">
                            <input
                                type="checkbox"
                                ?disabled=${!this._voiceEnabled}
                                .checked=${this._voiceDefaultOn}
                                @change=${(e) => { this._voiceDefaultOn = e.target.checked; this.isDirty = true; }}
                            />
                            <span>${this.t('embed_create_modal.label_voice_default_on')}</span>
                        </label>
                        <div class="hint">${this.t('embed_create_modal.voice_default_on_hint')}</div>
                    </div>

                    <div class="full">
                        <platform-field
                            type="text"
                            mode="edit"
                            .label=${this.t('embed_create_modal.label_allowed_origins')}
                            .value=${this._allowedOrigins}
                            .placeholder=${this.t('embed_create_modal.placeholder_allowed_origins')}
                            .hint=${this.t('embed_create_modal.allowed_origins_hint')}
                            @change=${(e) => { this._allowedOrigins = e.detail.value; this.isDirty = true; }}
                        ></platform-field>
                    </div>

                    <div>
                        <platform-field
                            type="integer"
                            mode="edit"
                            .label=${this.t('embed_create_modal.label_guest_max_user_messages')}
                            .value=${this._guestMaxUserMessages}
                            .placeholder=${this.t('embed_create_modal.placeholder_guest_max_user_messages')}
                            .hint=${this.t('embed_create_modal.guest_max_user_messages_hint')}
                            @change=${(e) => { this._guestMaxUserMessages = String(e.detail.value); this.isDirty = true; }}
                        ></platform-field>
                        ${this.renderFieldError('guest_max_user_messages')}
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
