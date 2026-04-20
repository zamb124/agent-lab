/**
 * flows-trigger-editor-modal — создание/редактирование триггера flow.
 *
 * Три таба: «Конфигурация» (id, name, тип, type-specific config),
 * «Input Mapping» (state-path → payload-path) и «Output Actions»
 * (массив каналов рассылки ответа агента).
 *
 * Контракт:
 *   props: { flowId: string, trigger: TriggerResponse | null }
 *   submit: useOp('flows/trigger_create' | 'flows/trigger_update'),
 *           затем useOp('flows/triggers_list').run({ flow_id }) для перезагрузки.
 *
 * Источник правды для типов триггера, каналов и output-actions —
 * локальные const-таблицы; ключи name/desc/label берутся из i18n
 * `flows:trigger_editor_modal.*`.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import { asString } from '../_helpers/flows-resolvers.js';

const TRIGGER_ID_PATTERN = /^[a-z][a-z0-9_]*$/;

const TRIGGER_TYPES = Object.freeze([
    { id: 'telegram', icon: 'send',     color: '#0088cc', nameKey: 'type_telegram', descKey: 'type_telegram_desc' },
    { id: 'cron',     icon: 'clock',    color: '#f59e0b', nameKey: 'type_cron',     descKey: 'type_cron_desc' },
    { id: 'webhook',  icon: 'globe',    color: '#8b5cf6', nameKey: 'type_webhook',  descKey: 'type_webhook_desc' },
    { id: 'email',    icon: 'mail',     color: '#ea4335', nameKey: 'type_email',    descKey: 'type_email_desc' },
    { id: 'redis',    icon: 'database', color: '#dc382d', nameKey: 'type_redis',    descKey: 'type_redis_desc' },
]);

const CHANNEL_TYPES = Object.freeze([
    { id: 'telegram', labelKey: 'channel_telegram' },
    { id: 'email',    labelKey: 'channel_email' },
    { id: 'webhook',  labelKey: 'channel_webhook' },
]);

const OUTPUT_ACTIONS = Object.freeze([
    { id: 'send_message',  labelKey: 'action_send_message' },
    { id: 'send_photo',    labelKey: 'action_send_photo' },
    { id: 'send_document', labelKey: 'action_send_document' },
]);

const MAPPING_EXAMPLES = Object.freeze({
    telegram: [
        { path: 'message.text',          descKey: 'examples_telegram_text' },
        { path: 'message.chat.id',       descKey: 'examples_telegram_chat_id' },
        { path: 'message.from.id',       descKey: 'examples_telegram_user_id' },
        { path: 'message.from.username', descKey: 'examples_telegram_username' },
    ],
    webhook: [
        { path: 'body.data',         descKey: 'examples_webhook_body' },
        { path: 'headers.X-Custom',  descKey: 'examples_webhook_header' },
        { path: 'query.param',       descKey: 'examples_webhook_query' },
    ],
    cron: [
        { path: 'scheduled_time', descKey: 'examples_cron_scheduled_time' },
    ],
    email: [
        { path: 'from',    descKey: 'examples_email_from' },
        { path: 'subject', descKey: 'examples_email_subject' },
        { path: 'body',    descKey: 'examples_email_body' },
    ],
    redis: [
        { path: 'channel', descKey: 'examples_redis_channel' },
        { path: 'data',    descKey: 'examples_redis_data' },
    ],
});

export class FlowsTriggerEditorModal extends PlatformFormModal {
    static modalKind = 'flows.trigger_editor';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        flowId: { type: String },
        trigger: { type: Object },
        _activeTab: { state: true },
        _triggerId: { state: true },
        _name: { state: true },
        _type: { state: true },
        _enabled: { state: true },
        _config: { state: true },
        _outputMapping: { state: true },
        _outputActions: { state: true },
        _hydrated: { state: true },
        _validationError: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            :host { --modal-max-width: 920px; }

            .tabs {
                display: flex;
                gap: var(--space-1);
                margin-bottom: var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
            }
            .tab {
                padding: var(--space-2) var(--space-4);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                border: none;
                background: none;
                cursor: pointer;
                border-bottom: 2px solid transparent;
                margin-bottom: -1px;
                transition: color var(--duration-fast) var(--easing-default),
                            border-color var(--duration-fast) var(--easing-default);
            }
            .tab:hover { color: var(--text-primary); }
            .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .field > label { font-size: var(--text-sm); color: var(--text-secondary); font-weight: var(--font-medium); }
            .field > .hint { font-size: var(--text-xs); color: var(--text-tertiary); }
            .field input,
            .field select,
            .field textarea {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font: inherit;
                width: 100%;
                box-sizing: border-box;
            }
            .field textarea { min-height: 96px; resize: vertical; font-family: var(--font-mono); font-size: var(--text-xs); }

            .checkbox-row { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }

            .trigger-type-selector {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }
            .trigger-type-option {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-4);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: border-color var(--duration-fast) var(--easing-default),
                            background var(--duration-fast) var(--easing-default);
                text-align: center;
                background: transparent;
            }
            .trigger-type-option:hover {
                border-color: var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
            }
            .trigger-type-option.active {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            .trigger-type-icon {
                width: 40px; height: 40px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-md);
            }
            .trigger-type-name { font-size: var(--text-sm); font-weight: var(--font-medium); color: var(--text-primary); }
            .trigger-type-desc { font-size: var(--text-xs); color: var(--text-tertiary); }

            .config-section {
                padding: var(--space-4);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-4);
            }
            .config-section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin-bottom: var(--space-3);
            }
            .config-intro { font-size: var(--text-sm); color: var(--text-secondary); margin: 0 0 var(--space-3); }

            .mapping-row {
                display: grid;
                grid-template-columns: 1fr auto 1fr auto;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .mapping-arrow { color: var(--text-tertiary); font-family: var(--font-mono); }
            .mapping-empty {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .mapping-add-row {
                display: flex; justify-content: space-between; align-items: center;
                margin-bottom: var(--space-2);
            }
            .mapping-legend { font-size: var(--text-xs); color: var(--text-tertiary); }

            .icon-btn {
                background: transparent;
                border: none;
                cursor: pointer;
                color: var(--text-tertiary);
                padding: var(--space-1);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-sm);
            }
            .icon-btn:hover { color: var(--accent); background: var(--glass-tint-subtle); }
            .icon-btn.danger:hover { color: var(--error); }

            .examples-list { font-size: var(--text-sm); font-family: var(--font-mono); }
            .examples-row { padding: var(--space-1) 0; display: flex; gap: var(--space-3); }
            .examples-row code { color: var(--accent); }
            .examples-row .desc { color: var(--text-tertiary); }

            .output-action-item {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-2);
            }
            .output-action-content { flex: 1; min-width: 0; }
            .output-action-header {
                display: flex; gap: var(--space-2); margin-bottom: var(--space-2);
            }
            .output-action-header select { width: auto; min-width: 140px; }

            .add-btn {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-subtle);
                border: 1px dashed var(--border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                width: 100%;
                justify-content: center;
                font: inherit;
            }
            .add-btn:hover { background: var(--accent-subtle); color: var(--accent); border-color: var(--accent); }

            .form-error {
                padding: var(--space-2) var(--space-3);
                margin-bottom: var(--space-3);
                color: var(--error);
                background: rgba(239, 68, 68, 0.08);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.flowId = '';
        this.trigger = null;
        this._activeTab = 'config';
        this._triggerId = '';
        this._name = '';
        this._type = '';
        this._enabled = true;
        this._config = {};
        this._outputMapping = [];
        this._outputActions = [];
        this._hydrated = false;
        this._validationError = '';
        this._createOp = this.useOp('flows/trigger_create');
        this._updateOp = this.useOp('flows/trigger_update');
        this._listOp = this.useOp('flows/triggers_list');
    }

    updated(changed) {
        super.updated?.(changed);
        if (this._hydrated) return;
        if (changed.has('trigger') || changed.has('flowId')) {
            this._hydrate();
        }
    }

    _hydrate() {
        const t = this.trigger;
        if (t) {
            this._triggerId = t.trigger_id;
            this._name = t.name;
            this._type = t.type;
            this._enabled = Boolean(t.enabled);
            this._config = { ...t.config };
            const mapping = Object.keys(t.output_mapping).length > 0 ? t.output_mapping : t.input_mapping;
            this._outputMapping = Object.entries(mapping).map(([state, payload]) => ({ state, payload }));
            this._outputActions = t.output_actions.map((a) => ({
                channel: a.channel,
                action: a.action,
                mapping: { ...a.mapping },
                config: { ...a.config },
                condition: a.condition === null ? '' : a.condition,
            }));
        } else {
            this._triggerId = '';
            this._name = '';
            this._type = '';
            this._enabled = true;
            this._config = {};
            this._outputMapping = [];
            this._outputActions = [];
        }
        this._hydrated = true;
    }

    renderHeader() {
        return this.t(this.trigger ? 'trigger_editor_modal.title_edit' : 'trigger_editor_modal.title_create');
    }

    renderBody() {
        return html`
            <div class="tabs">
                <button type="button" class="tab ${this._activeTab === 'config' ? 'active' : ''}" @click=${() => this._setTab('config')}>
                    ${this.t('trigger_editor_modal.tab_config')}
                </button>
                <button type="button" class="tab ${this._activeTab === 'mapping' ? 'active' : ''}" @click=${() => this._setTab('mapping')}>
                    ${this.t('trigger_editor_modal.tab_mapping')}
                </button>
                <button type="button" class="tab ${this._activeTab === 'output' ? 'active' : ''}" @click=${() => this._setTab('output')}>
                    ${this.t('trigger_editor_modal.tab_output')}
                </button>
            </div>

            ${this._validationError ? html`<div class="form-error">${this._validationError}</div>` : ''}

            ${this._activeTab === 'config' ? this._renderConfigTab() : ''}
            ${this._activeTab === 'mapping' ? this._renderMappingTab() : ''}
            ${this._activeTab === 'output' ? this._renderOutputTab() : ''}
        `;
    }

    _renderConfigTab() {
        const editing = Boolean(this.trigger);
        return html`
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_id')}</label>
                <input
                    type="text"
                    .value=${this._triggerId}
                    ?disabled=${editing}
                    placeholder=${this.t('trigger_editor_modal.field_id_placeholder')}
                    @input=${(e) => { this._triggerId = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_name')}</label>
                <input
                    type="text"
                    .value=${this._name}
                    placeholder=${this.t('trigger_editor_modal.field_name_placeholder')}
                    @input=${(e) => { this._name = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_type')}</label>
                <div class="trigger-type-selector">
                    ${TRIGGER_TYPES.map((tp) => html`
                        <div
                            class="trigger-type-option ${this._type === tp.id ? 'active' : ''}"
                            @click=${() => this._selectType(tp.id)}
                        >
                            <div class="trigger-type-icon" style="background: ${tp.color}20; color: ${tp.color};">
                                <platform-icon name=${tp.icon} size="24"></platform-icon>
                            </div>
                            <div class="trigger-type-name">${this.t(`trigger_editor_modal.${tp.nameKey}`)}</div>
                            <div class="trigger-type-desc">${this.t(`trigger_editor_modal.${tp.descKey}`)}</div>
                        </div>
                    `)}
                </div>
            </div>

            <div class="checkbox-row">
                <input
                    type="checkbox"
                    id="flows-trigger-enabled"
                    .checked=${this._enabled}
                    @change=${(e) => { this._enabled = e.target.checked; this.isDirty = true; }}
                />
                <label for="flows-trigger-enabled">${this.t('trigger_editor_modal.field_enabled')}</label>
            </div>

            ${this._renderTypeSpecificConfig()}
        `;
    }

    _renderTypeSpecificConfig() {
        switch (this._type) {
            case 'telegram': return this._renderTelegramConfig();
            case 'cron':     return this._renderCronConfig();
            case 'webhook':  return this._renderWebhookConfig();
            case 'email':    return this._renderEmailConfig();
            case 'redis':    return this._renderRedisConfig();
            default:         return '';
        }
    }

    _renderTelegramConfig() {
        const c = this._config;
        const allowedUsers = Array.isArray(c.allowed_users) ? c.allowed_users.join(', ') : asString(c.allowed_users);
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.section_telegram')}</div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_bot_token')}</label>
                    <input
                        type="text"
                        .value=${asString(c.bot_token)}
                        placeholder=${this.t('trigger_editor_modal.field_bot_token_placeholder')}
                        @input=${(e) => this._setConfig('bot_token', e.target.value)}
                    />
                    <span class="hint">${this.t('trigger_editor_modal.hint_bot_token')}</span>
                </div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_allowed_users')}</label>
                    <input
                        type="text"
                        .value=${allowedUsers}
                        placeholder=${this.t('trigger_editor_modal.field_allowed_users_placeholder')}
                        @input=${(e) => this._setConfigList('allowed_users', e.target.value, 'int')}
                    />
                    <span class="hint">${this.t('trigger_editor_modal.hint_allowed_users')}</span>
                </div>
            </div>
        `;
    }

    _renderCronConfig() {
        const c = this._config;
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.section_cron')}</div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_cron')}</label>
                    <input
                        type="text"
                        .value=${asString(c.cron)}
                        placeholder=${this.t('trigger_editor_modal.field_cron_placeholder')}
                        @input=${(e) => this._setConfig('cron', e.target.value)}
                    />
                    <span class="hint">${this.t('trigger_editor_modal.hint_cron')}</span>
                </div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_timezone')}</label>
                    <input
                        type="text"
                        .value=${asString(c.timezone)}
                        placeholder=${this.t('trigger_editor_modal.field_timezone_placeholder')}
                        @input=${(e) => this._setConfig('timezone', e.target.value)}
                    />
                </div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_initial_content')}</label>
                    <input
                        type="text"
                        .value=${asString(c.initial_content)}
                        placeholder=${this.t('trigger_editor_modal.field_initial_content_placeholder')}
                        @input=${(e) => this._setConfig('initial_content', e.target.value)}
                    />
                </div>
            </div>
        `;
    }

    _renderWebhookConfig() {
        const c = this._config;
        const allowedIps = Array.isArray(c.allowed_ips) ? c.allowed_ips.join(', ') : asString(c.allowed_ips);
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.section_webhook')}</div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_secret_token')}</label>
                    <input
                        type="text"
                        .value=${asString(c.secret_token)}
                        placeholder=${this.t('trigger_editor_modal.field_secret_token_placeholder')}
                        @input=${(e) => this._setConfig('secret_token', e.target.value)}
                    />
                    <span class="hint">${this.t('trigger_editor_modal.hint_secret_token')}</span>
                </div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_allowed_ips')}</label>
                    <input
                        type="text"
                        .value=${allowedIps}
                        placeholder=${this.t('trigger_editor_modal.field_allowed_ips_placeholder')}
                        @input=${(e) => this._setConfigList('allowed_ips', e.target.value, 'string')}
                    />
                    <span class="hint">${this.t('trigger_editor_modal.hint_allowed_ips')}</span>
                </div>
            </div>
        `;
    }

    _renderEmailConfig() {
        const c = this._config;
        const provider = typeof c.provider === 'string' && c.provider.length > 0 ? c.provider : 'imap';
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.section_email')}</div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_provider')}</label>
                    <select
                        .value=${provider}
                        @change=${(e) => this._setConfig('provider', e.target.value)}
                    >
                        <option value="imap" ?selected=${provider === 'imap'}>${this.t('trigger_editor_modal.provider_imap')}</option>
                        <option value="mailgun" ?selected=${provider === 'mailgun'}>${this.t('trigger_editor_modal.provider_mailgun')}</option>
                    </select>
                </div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_imap_host')}</label>
                    <input
                        type="text"
                        .value=${asString(c.imap_host)}
                        placeholder=${this.t('trigger_editor_modal.field_imap_host_placeholder')}
                        @input=${(e) => this._setConfig('imap_host', e.target.value)}
                    />
                </div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_imap_user')}</label>
                    <input
                        type="text"
                        .value=${asString(c.imap_user)}
                        placeholder=${this.t('trigger_editor_modal.field_imap_user_placeholder')}
                        @input=${(e) => this._setConfig('imap_user', e.target.value)}
                    />
                </div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_imap_password')}</label>
                    <input
                        type="password"
                        .value=${asString(c.imap_password)}
                        placeholder=${this.t('trigger_editor_modal.field_imap_password_placeholder')}
                        @input=${(e) => this._setConfig('imap_password', e.target.value)}
                    />
                </div>
            </div>
        `;
    }

    _renderRedisConfig() {
        const c = this._config;
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.section_redis')}</div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_channel')}</label>
                    <input
                        type="text"
                        .value=${asString(c.channel)}
                        placeholder=${this.t('trigger_editor_modal.field_channel_placeholder')}
                        @input=${(e) => this._setConfig('channel', e.target.value)}
                    />
                </div>
                <div class="checkbox-row">
                    <input
                        type="checkbox"
                        id="flows-trigger-redis-pattern"
                        .checked=${Boolean(c.pattern)}
                        @change=${(e) => this._setConfig('pattern', e.target.checked)}
                    />
                    <label for="flows-trigger-redis-pattern">${this.t('trigger_editor_modal.field_pattern')}</label>
                </div>
                <span class="hint">${this.t('trigger_editor_modal.hint_pattern')}</span>
            </div>
        `;
    }

    _renderMappingTab() {
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.mapping_section_title')}</div>
                <p class="config-intro">${this.t('trigger_editor_modal.mapping_intro')}</p>

                <div class="mapping-add-row">
                    <span style="font-weight: var(--font-medium); color: var(--text-secondary);">
                        ${this.t('trigger_editor_modal.mapping_label')}
                    </span>
                    <button type="button" class="add-btn" style="width: auto;" @click=${this._addMapping}>
                        + ${this.t('trigger_editor_modal.mapping_add')}
                    </button>
                </div>

                ${this._outputMapping.length === 0
                    ? html`<div class="mapping-empty">${this.t('trigger_editor_modal.mapping_empty')}</div>`
                    : this._outputMapping.map((m, idx) => html`
                        <div class="mapping-row">
                            <input
                                type="text"
                                .value=${m.state}
                                placeholder=${this.t('trigger_editor_modal.mapping_placeholder_state')}
                                @input=${(e) => this._updateMapping(idx, 'state', e.target.value)}
                                style="padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); border: 1px solid var(--glass-border-subtle); background: var(--glass-tint-subtle); color: var(--text-primary);"
                            />
                            <span class="mapping-arrow">→</span>
                            <input
                                type="text"
                                .value=${m.payload}
                                placeholder=${this.t('trigger_editor_modal.mapping_placeholder_payload')}
                                @input=${(e) => this._updateMapping(idx, 'payload', e.target.value)}
                                style="padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); border: 1px solid var(--glass-border-subtle); background: var(--glass-tint-subtle); color: var(--text-primary);"
                            />
                            <button
                                type="button"
                                class="icon-btn danger"
                                title=${this.t('trigger_editor_modal.mapping_remove_title')}
                                @click=${() => this._removeMapping(idx)}
                            >
                                <platform-icon name="trash" size="16"></platform-icon>
                            </button>
                        </div>
                    `)}

                <div class="mapping-legend">${this.t('trigger_editor_modal.mapping_legend')}</div>
            </div>

            <div class="config-section">
                <div class="config-section-title">
                    ${this._type
                        ? this.t('trigger_editor_modal.examples_section_title', { type: this._type })
                        : this.t('trigger_editor_modal.examples_select_type')}
                </div>
                ${this._renderMappingExamples()}
            </div>
        `;
    }

    _renderMappingExamples() {
        const examples = this._type ? MAPPING_EXAMPLES[this._type] : null;
        if (!examples || examples.length === 0) {
            return html`<p class="config-intro">${this.t('trigger_editor_modal.examples_select_type')}</p>`;
        }
        return html`
            <div class="examples-list">
                ${examples.map((ex) => html`
                    <div class="examples-row">
                        <code>${ex.path}</code>
                        <span class="desc">— ${this.t(`trigger_editor_modal.${ex.descKey}`)}</span>
                    </div>
                `)}
            </div>
        `;
    }

    _renderOutputTab() {
        return html`
            <div class="config-section-title">${this.t('trigger_editor_modal.output_section_title')}</div>
            <p class="config-intro">${this.t('trigger_editor_modal.output_intro')}</p>

            ${this._outputActions.map((action, idx) => this._renderOutputAction(action, idx))}

            <button type="button" class="add-btn" @click=${this._addOutputAction}>
                <platform-icon name="plus" size="16"></platform-icon>
                ${this.t('trigger_editor_modal.output_add')}
            </button>
        `;
    }

    _renderOutputAction(action, idx) {
        const mappingEntries = Object.entries(action.mapping);
        return html`
            <div class="output-action-item">
                <div class="output-action-content">
                    <div class="output-action-header">
                        <select
                            .value=${action.channel}
                            @change=${(e) => this._updateOutputAction(idx, 'channel', e.target.value)}
                        >
                            ${CHANNEL_TYPES.map((ch) => html`
                                <option value=${ch.id} ?selected=${ch.id === action.channel}>
                                    ${this.t(`trigger_editor_modal.${ch.labelKey}`)}
                                </option>
                            `)}
                        </select>
                        <select
                            .value=${action.action}
                            @change=${(e) => this._updateOutputAction(idx, 'action', e.target.value)}
                        >
                            ${OUTPUT_ACTIONS.map((a) => html`
                                <option value=${a.id} ?selected=${a.id === action.action}>
                                    ${this.t(`trigger_editor_modal.${a.labelKey}`)}
                                </option>
                            `)}
                        </select>
                    </div>

                    <div class="field">
                        <label>${this.t('trigger_editor_modal.output_mapping_label')}</label>
                        ${mappingEntries.length === 0
                            ? html`<div class="mapping-empty">${this.t('trigger_editor_modal.mapping_empty')}</div>`
                            : mappingEntries.map(([key, value]) => html`
                                <div class="mapping-row">
                                    <input
                                        type="text"
                                        .value=${key}
                                        placeholder=${this.t('trigger_editor_modal.output_mapping_param_placeholder')}
                                        @change=${(e) => this._renameOutputMappingKey(idx, key, e.target.value)}
                                        style="padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); border: 1px solid var(--glass-border-subtle); background: var(--glass-tint-subtle); color: var(--text-primary);"
                                    />
                                    <span class="mapping-arrow">→</span>
                                    <input
                                        type="text"
                                        .value=${value}
                                        placeholder=${this.t('trigger_editor_modal.output_mapping_value_placeholder')}
                                        @input=${(e) => this._setOutputMappingValue(idx, key, e.target.value)}
                                        style="padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); border: 1px solid var(--glass-border-subtle); background: var(--glass-tint-subtle); color: var(--text-primary);"
                                    />
                                    <button
                                        type="button"
                                        class="icon-btn danger"
                                        title=${this.t('trigger_editor_modal.mapping_remove_title')}
                                        @click=${() => this._removeOutputMappingKey(idx, key)}
                                    >
                                        <platform-icon name="trash" size="16"></platform-icon>
                                    </button>
                                </div>
                            `)}
                        <button type="button" class="add-btn" @click=${() => this._addOutputMappingKey(idx)}>
                            + ${this.t('trigger_editor_modal.output_mapping_add')}
                        </button>
                    </div>

                    <div class="field">
                        <label>${this.t('trigger_editor_modal.output_condition_label')}</label>
                        <input
                            type="text"
                            .value=${action.condition}
                            placeholder=${this.t('trigger_editor_modal.output_condition_placeholder')}
                            @input=${(e) => this._updateOutputAction(idx, 'condition', e.target.value)}
                        />
                    </div>
                </div>
                <button
                    type="button"
                    class="icon-btn danger"
                    title=${this.t('trigger_editor_modal.output_action_remove_title')}
                    @click=${() => this._removeOutputAction(idx)}
                >
                    <platform-icon name="trash" size="16"></platform-icon>
                </button>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button @click=${() => this.close()}>
                    ${this.t('trigger_editor_modal.action_cancel')}
                </platform-button>
                <platform-button
                    variant="primary"
                    ?disabled=${this._createOp.busy || this._updateOp.busy}
                    @click=${this._performSave}
                >
                    ${this.trigger
                        ? this.t('trigger_editor_modal.action_save')
                        : this.t('trigger_editor_modal.action_create')}
                </platform-button>
            </div>
        `;
    }

    _setTab(tab) {
        this._activeTab = tab;
    }

    _selectType(typeId) {
        this._type = typeId;
        this.isDirty = true;
    }

    _setConfig(key, value) {
        this._config = { ...this._config, [key]: value };
        this.isDirty = true;
    }

    _setConfigList(key, raw, kind) {
        const items = raw
            .split(',')
            .map((s) => s.trim())
            .filter((s) => s.length > 0);
        const list = kind === 'int' ? items.map((s) => Number.parseInt(s, 10)).filter((n) => Number.isFinite(n)) : items;
        this._setConfig(key, list);
    }

    _addMapping() {
        this._outputMapping = [...this._outputMapping, { state: '', payload: '' }];
        this.isDirty = true;
    }

    _updateMapping(idx, field, value) {
        this._outputMapping = this._outputMapping.map((m, i) => (i === idx ? { ...m, [field]: value } : m));
        this.isDirty = true;
    }

    _removeMapping(idx) {
        this._outputMapping = this._outputMapping.filter((_, i) => i !== idx);
        this.isDirty = true;
    }

    _addOutputAction() {
        this._outputActions = [
            ...this._outputActions,
            { channel: 'telegram', action: 'send_message', mapping: {}, config: {}, condition: '' },
        ];
        this.isDirty = true;
    }

    _updateOutputAction(idx, field, value) {
        this._outputActions = this._outputActions.map((a, i) => (i === idx ? { ...a, [field]: value } : a));
        this.isDirty = true;
    }

    _removeOutputAction(idx) {
        this._outputActions = this._outputActions.filter((_, i) => i !== idx);
        this.isDirty = true;
    }

    _addOutputMappingKey(idx) {
        const action = this._outputActions[idx];
        const taken = new Set(Object.keys(action.mapping));
        let base = 'param';
        let key = base;
        let n = 1;
        while (taken.has(key)) {
            key = `${base}_${n}`;
            n += 1;
        }
        this._updateOutputAction(idx, 'mapping', { ...action.mapping, [key]: '' });
    }

    _setOutputMappingValue(idx, key, value) {
        const action = this._outputActions[idx];
        this._updateOutputAction(idx, 'mapping', { ...action.mapping, [key]: value });
    }

    _renameOutputMappingKey(idx, oldKey, newKey) {
        const trimmed = newKey.trim();
        if (trimmed === oldKey) return;
        if (trimmed.length === 0) return;
        const action = this._outputActions[idx];
        const next = {};
        for (const [k, v] of Object.entries(action.mapping)) {
            next[k === oldKey ? trimmed : k] = v;
        }
        this._updateOutputAction(idx, 'mapping', next);
    }

    _removeOutputMappingKey(idx, key) {
        const action = this._outputActions[idx];
        const next = { ...action.mapping };
        delete next[key];
        this._updateOutputAction(idx, 'mapping', next);
    }

    validateForm() {
        if (!this._triggerId.trim()) {
            return { trigger_id: this.t('trigger_editor_modal.error_id_required') };
        }
        if (!TRIGGER_ID_PATTERN.test(this._triggerId.trim())) {
            return { trigger_id: this.t('trigger_editor_modal.error_id_invalid') };
        }
        if (!this._name.trim()) {
            return { name: this.t('trigger_editor_modal.error_name_required') };
        }
        if (!this._type) {
            return { type: this.t('trigger_editor_modal.error_type_required') };
        }
        return {};
    }

    async _performSave() {
        const errors = this.validateForm();
        if (Object.keys(errors).length > 0) {
            this._validationError = Object.values(errors)[0];
            return;
        }
        this._validationError = '';

        const outputMapping = {};
        for (const m of this._outputMapping) {
            const state = m.state.trim();
            const payload = m.payload.trim();
            if (state.length > 0 && payload.length > 0) {
                outputMapping[state] = payload;
            }
        }

        const outputActions = this._outputActions.map((a) => ({
            channel: a.channel,
            action: a.action,
            mapping: a.mapping,
            config: a.config,
            condition: a.condition.trim(),
        }));

        const body = {
            trigger_id: this._triggerId.trim(),
            name: this._name.trim(),
            type: this._type,
            enabled: this._enabled,
            config: this._config,
            output_mapping: outputMapping,
            output_actions: outputActions,
        };

        if (this.trigger) {
            await this._updateOp.run({
                flow_id: this.flowId,
                trigger_id: this._triggerId.trim(),
                body: {
                    name: body.name,
                    enabled: body.enabled,
                    config: body.config,
                    output_mapping: body.output_mapping,
                    output_actions: body.output_actions,
                },
            });
        } else {
            await this._createOp.run({ flow_id: this.flowId, body });
        }
        await this._listOp.run({ flow_id: this.flowId });
        this.closeAfterSave();
    }
}

customElements.define('flows-trigger-editor-modal', FlowsTriggerEditorModal);
registerModalKind(FlowsTriggerEditorModal.modalKind, 'flows-trigger-editor-modal');
