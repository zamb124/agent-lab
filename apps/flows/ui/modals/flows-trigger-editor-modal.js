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

import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-cron-field.js';
import '@platform/lib/components/platform-timezone-picker.js';
import { asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import { TRIGGER_TYPES } from '../constants/trigger-types.js';

const TRIGGER_ID_PATTERN = /^[a-zA-Z][a-zA-Z0-9_-]*$/;

const CHANNEL_TYPES = Object.freeze([
    { id: 'telegram', labelKey: 'channel_telegram' },
    { id: 'email',    labelKey: 'channel_email' },
    { id: 'webhook',  labelKey: 'channel_webhook' },
]);

/**
 * Куда доставлять ответ flow — привязываем к типу входа: Telegram-вход = только ответ в Telegram
 * (отдельные сценарии: cron / webhook / redis с другими графами).
 */
function outputChannelTypesForTrigger(triggerType) {
    if (triggerType === 'telegram') {
        return CHANNEL_TYPES.filter((c) => c.id === 'telegram');
    }
    if (triggerType === 'email') {
        return CHANNEL_TYPES.filter((c) => c.id === 'email');
    }
    return [...CHANNEL_TYPES];
}

/**
 * Вкладка «Вывод» не показывается для cron: пост-рассылка не используется.
 * @param {string} typeId
 * @returns {boolean}
 */
function showTriggerOutputTab(typeId) {
    return typeId.length > 0 && typeId !== 'cron';
}

const OUTPUT_ACTIONS = Object.freeze([
    { id: 'send_message',  labelKey: 'action_send_message' },
    { id: 'send_photo',    labelKey: 'action_send_photo' },
    { id: 'send_document', labelKey: 'action_send_document' },
]);

/**
 * @param {string} [triggerId]
 */
function defaultTelegramOutputAction(triggerId) {
    const tid = String(triggerId || '').trim();
    const recipient = tid.length > 0
        ? `@state:triggers.${tid}.context.chat_id`
        : '';
    return {
        channel: 'telegram',
        action: 'send_message',
        mapping: {
            recipient,
            text: '@state:response',
        },
        config: { parse_mode: 'HTML' },
        condition: '',
    };
}

/**
 * @param {Record<string, string>} a
 * @param {Record<string, string>} b
 */
function _mappingEqual(a, b) {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    for (const k of ka) {
        if (a[k] !== b[k]) return false;
    }
    return true;
}

/**
 * @param {object} a
 * @param {string} a.channel
 * @param {string} a.action
 * @param {Record<string, string>} a.mapping
 * @param {Record<string, string>} a.config
 * @param {string} a.condition
 * @param {string} [triggerId]
 */
function isDefaultTelegramOutputActionForm(a, triggerId) {
    if (a.channel !== 'telegram' || a.action !== 'send_message') return false;
    if (String(a.condition).trim().length > 0) return false;
    const d = defaultTelegramOutputAction(triggerId);
    if (!_mappingEqual(a.mapping, d.mapping)) return false;
    const c = a.config;
    if (Object.keys(c).length === 0) return true;
    if (Object.keys(c).length === 1 && c.parse_mode === 'HTML') return true;
    return false;
}

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
        _outputTelegramExpanded: { state: true },
        _postFlowOutputEnabled: { state: true },
        _hydrated: { state: true },
        _validationError: { state: true },
        _verifyHintText: { state: true },
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
            .switch-row { display: flex; align-items: center; margin-bottom: var(--space-3); }

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
                flex-wrap: wrap;
            }
            .output-action-header select {
                width: auto;
                min-width: 160px;
                max-width: 100%;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font: inherit;
                box-sizing: border-box;
            }
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
            .header-trigger-actions {
                display: flex;
                gap: var(--space-1);
                align-items: center;
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
        this._outputTelegramExpanded = false;
        this._postFlowOutputEnabled = true;
        this._branchId = 'default';
        this._hydrated = false;
        this._validationError = '';
        this._verifyHintText = '';
        this._createOp = this.useOp('flows/trigger_create');
        this._updateOp = this.useOp('flows/trigger_update');
        this._listOp = this.useOp('flows/triggers_list');
        this._verifyOp = this.useOp('flows/trigger_verify');
        this._reregisterOp = this.useOp('flows/trigger_reregister');
        this._editor = this.useOp('flows/editor');
        this._flowsCat = this.useResource('flows/flows', { autoload: false });
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId') && this.flowId) {
            this._ensureFlowForBranches();
        }
        if (this._hydrated) return;
        if (changed.has('trigger') || changed.has('flowId')) {
            this._hydrate();
        }
    }

    _ensureFlowForBranches() {
        if (!this.flowId) return;
        const ed = this._editor.state;
        const fromEditor = isPlainObject(ed.flowConfig) && ed.flowConfig.flow_id === this.flowId;
        if (fromEditor) return;
        const cat = this._flowsCat.byId;
        if (isPlainObject(cat) && isPlainObject(cat[this.flowId])) return;
        void this._flowsCat.get(this.flowId);
    }

    _flowConfigForBranchPicker() {
        if (!this.flowId) return null;
        const ed = this._editor.state;
        if (isPlainObject(ed.flowConfig) && ed.flowConfig.flow_id === this.flowId) {
            return ed.flowConfig;
        }
        const row = this._flowsCat.byId[this.flowId];
        if (isPlainObject(row)) return row;
        return null;
    }

    _branchSelectRows() {
        const out = [
            { value: 'default', label: this.t('trigger_editor_modal.branch_option_default') },
        ];
        const flow = this._flowConfigForBranchPicker();
        if (!isPlainObject(flow) || !isPlainObject(flow.branches)) {
            if (!out.some((o) => o.value === this._branchId) && asString(this._branchId).length > 0) {
                out.push({ value: this._branchId, label: this._branchId });
            }
            return out;
        }
        for (const [id, sk] of Object.entries(flow.branches)) {
            if (id === 'default') {
                continue;
            }
            if (typeof id !== 'string' || id.length === 0) {
                throw new Error('flows-trigger-editor-modal: branch key must be non-empty string');
            }
            const title = isPlainObject(sk) && typeof sk.name === 'string' && sk.name.length > 0
                ? sk.name
                : id;
            out.push({ value: id, label: `${title} (${id})` });
        }
        if (!out.some((o) => o.value === this._branchId) && asString(this._branchId).length > 0) {
            out.push({ value: this._branchId, label: this._branchId });
        }
        return out;
    }

    _hydrate() {
        this._verifyHintText = '';
        const t = this.trigger;
        if (t) {
            this._triggerId = t.trigger_id;
            this._name = t.name;
            this._type = t.type;
            this._enabled = Boolean(t.enabled);
            if (typeof t.branch_id === 'string' && t.branch_id.length > 0) {
                this._branchId = t.branch_id;
            } else {
                this._branchId = 'default';
            }
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
            this._postFlowOutputEnabled = t.post_flow_output_enabled !== false;
        } else {
            this._triggerId = '';
            this._name = '';
            this._type = '';
            this._enabled = true;
            this._branchId = 'default';
            this._config = {};
            this._outputMapping = [];
            this._outputActions = [];
            this._postFlowOutputEnabled = true;
        }
        if (this._type === 'telegram' && this._outputActions.length === 0 && this._postFlowOutputEnabled) {
            if (this._triggerId.trim().length > 0) {
                this._outputActions = [defaultTelegramOutputAction(this._triggerId)];
            }
        }
        this._outputTelegramExpanded = false;
        if (!showTriggerOutputTab(this._type) && this._activeTab === 'output') {
            this._activeTab = 'config';
        }
        this._hydrated = true;
    }

    renderHeader() {
        return this.t(this.trigger ? 'trigger_editor_modal.title_edit' : 'trigger_editor_modal.title_create');
    }

    renderHeaderActions() {
        const canReregister = Boolean(this.trigger)
            && asString(this._triggerId).length > 0
            && this._enabled;
        const reregisterDisabled = !canReregister
            || this._reregisterOp.busy
            || this._verifyOp.busy;
        return html`
            <platform-help-hint
                class="trigger-verify-hint"
                wide
                .text=${this._verifyHintText}
                .label=${this.t('trigger_editor_modal.verify_tooltip_label')}
            >
                <div class="header-trigger-actions">
                    <button
                        type="button"
                        class="header-btn verify-trigger-hint-btn"
                        ?disabled=${this._verifyOp.busy || this._reregisterOp.busy}
                        title=${this.t('trigger_editor_modal.verify_btn_title')}
                        aria-label=${this.t('trigger_editor_modal.verify_btn_title')}
                        @click=${(e) => {
            e.stopPropagation();
            void this._onTriggerVerify();
        }}
                    >
                        <platform-icon name="check" size="16"></platform-icon>
                    </button>
                    <button
                        type="button"
                        class="header-btn"
                        ?disabled=${reregisterDisabled}
                        title=${this.t('trigger_editor_modal.reregister_btn_title')}
                        aria-label=${this.t('trigger_editor_modal.reregister_btn_title')}
                        @click=${(e) => {
            e.stopPropagation();
            void this._onTriggerReregister();
        }}
                    >
                        <platform-icon name="rotate-ccw" size="16"></platform-icon>
                    </button>
                </div>
            </platform-help-hint>
        `;
    }

    /**
     * @param {unknown} v
     * @returns {string}
     */
    _stringifyVerifyPayload(v) {
        if (v !== null && typeof v === 'object') {
            return JSON.stringify(v, null, 2);
        }
        if (typeof v === 'string') {
            return v;
        }
        if (v === null || v === undefined) {
            return '';
        }
        return String(v);
    }

    _focusVerifyHintButton() {
        const root = this.shadowRoot;
        if (!root) {
            return;
        }
        const h = root.querySelector('platform-help-hint.trigger-verify-hint');
        const b = h?.querySelector('button.verify-trigger-hint-btn');
        if (b instanceof HTMLElement) {
            b.focus();
        }
    }

    async _onTriggerVerify() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            this._verifyHintText = this.t('trigger_editor_modal.verify_error_no_flow');
            this.requestUpdate();
            await this.updateComplete;
            this._focusVerifyHintButton();
            return;
        }
        if (typeof this._type !== 'string' || this._type.length === 0) {
            this._verifyHintText = this.t('trigger_editor_modal.verify_error_no_type');
            this.requestUpdate();
            await this.updateComplete;
            this._focusVerifyHintButton();
            return;
        }
        if (!isPlainObject(this._config)) {
            throw new Error('flows-trigger-editor-modal: _config must be a plain object');
        }
        const body = {
            type: this._type,
            config: { ...this._config },
            branch_id: this._branchId,
        };
        const tid = asString(this._triggerId);
        if (tid.length > 0) {
            body.trigger_id = tid;
        }
        const r = await this._verifyOp.run({ flow_id: this.flowId, body });
        if (r === null) {
            const errMsg = this._verifyOp.error;
            this._verifyHintText = errMsg && errMsg.length > 0
                ? this.t('trigger_editor_modal.verify_error_http', { message: errMsg })
                : this.t('trigger_editor_modal.verify_error_network');
        } else {
            this._verifyHintText = this._stringifyVerifyPayload(r);
        }
        this.requestUpdate();
        await this.updateComplete;
        this._focusVerifyHintButton();
    }

    async _onTriggerReregister() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        if (!this.trigger) {
            return;
        }
        const tid = asString(this._triggerId);
        if (tid.length === 0) {
            return;
        }
        if (!this._enabled) {
            return;
        }
        await this._reregisterOp.run({ flow_id: this.flowId, trigger_id: tid });
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
                ${showTriggerOutputTab(this._type)
        ? html`
                <button type="button" class="tab ${this._activeTab === 'output' ? 'active' : ''}" @click=${() => this._setTab('output')}>
                    ${this.t('trigger_editor_modal.tab_output')}
                </button>
                `
        : nothing}
            </div>

            ${this._validationError ? html`<div class="form-error">${this._validationError}</div>` : ''}

            ${this._activeTab === 'config' ? this._renderConfigTab() : ''}
            ${this._activeTab === 'mapping' ? this._renderMappingTab() : ''}
            ${this._activeTab === 'output' && showTriggerOutputTab(this._type) ? this._renderOutputTab() : ''}
        `;
    }

    _renderConfigTab() {
        const editing = Boolean(this.trigger);
        return html`
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_branch')}</label>
                <select
                    .value=${this._branchId}
                    @change=${(e) => {
                    this._branchId = e.target.value;
                    this.isDirty = true;
                }}
                >
                    ${this._branchSelectRows().map(
        (o) => html`<option value=${o.value}>${o.label}</option>`,
    )}
                </select>
                <span class="hint">${this.t('trigger_editor_modal.hint_branch')}</span>
            </div>

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

            <div class="switch-row">
                <platform-switch
                    .checked=${this._enabled}
                    .label=${this.t('trigger_editor_modal.field_enabled')}
                    @change=${(e) => { this._enabled = e.detail.value; this.isDirty = true; }}
                ></platform-switch>
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
                    <platform-cron-field
                        .value=${asString(c.cron)}
                        placeholder=${this.t('trigger_editor_modal.field_cron_placeholder')}
                        @input=${(e) => this._setConfig('cron', e.detail.value)}
                        @change=${(e) => this._setConfig('cron', e.detail.value)}
                    ></platform-cron-field>
                    <span class="hint">${this.t('trigger_editor_modal.hint_cron')}</span>
                </div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_timezone')}</label>
                    <platform-timezone-picker
                        .value=${asString(c.timezone)}
                        placeholder=${this.t('trigger_editor_modal.field_timezone_placeholder')}
                        @input=${(e) => this._setConfig('timezone', e.detail.value)}
                        @change=${(e) => this._setConfig('timezone', e.detail.value)}
                    ></platform-timezone-picker>
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
        if (!showTriggerOutputTab(this._type)) {
            return nothing;
        }
        const showGeneralOutputIntro
            = Boolean(this._type)
            && this._type !== 'telegram'
            && (this._type === 'email' || ['webhook', 'redis'].includes(this._type));
        const compactTelegram
            = this._postFlowOutputEnabled
            && this._type === 'telegram'
            && this._outputActions.length === 1
            && isDefaultTelegramOutputActionForm(this._outputActions[0], this._triggerId)
            && !this._outputTelegramExpanded;
        if (!this._postFlowOutputEnabled) {
            return html`
                <div class="switch-row" style="align-items: flex-start; gap: var(--space-3);">
                    <label style="min-width: 0;">
                        <span class="config-section-title" style="display: block; margin-bottom: var(--space-1);">
                            ${this.t('trigger_editor_modal.post_flow_output_label')}
                        </span>
                        <span class="hint">${this.t('trigger_editor_modal.post_flow_output_hint')}</span>
                    </label>
                    <platform-switch
                        .checked=${this._postFlowOutputEnabled}
                        @change=${(e) => {
                            this._postFlowOutputEnabled = e.detail.value;
                            this.isDirty = true;
                        }}
                    ></platform-switch>
                </div>
            `;
        }
        if (compactTelegram) {
            return html`
                <div class="switch-row" style="align-items: flex-start; gap: var(--space-3); margin-bottom: var(--space-4);">
                    <label style="min-width: 0;">
                        <span class="config-section-title" style="display: block; margin-bottom: var(--space-1);">
                            ${this.t('trigger_editor_modal.post_flow_output_label')}
                        </span>
                        <span class="hint">${this.t('trigger_editor_modal.post_flow_output_hint')}</span>
                    </label>
                    <platform-switch
                        .checked=${this._postFlowOutputEnabled}
                        @change=${(e) => {
                            this._postFlowOutputEnabled = e.detail.value;
                            this.isDirty = true;
                        }}
                    ></platform-switch>
                </div>
                <div class="config-section-title">${this.t('trigger_editor_modal.output_section_title')}</div>
                <p class="config-intro">${this.t('trigger_editor_modal.output_telegram_auto')}</p>
                <button
                    type="button"
                    class="add-btn"
                    @click=${() => { this._outputTelegramExpanded = true; this.isDirty = true; }}
                >
                    ${this.t('trigger_editor_modal.output_telegram_customize')}
                </button>
            `;
        }
        return html`
            <div class="switch-row" style="align-items: flex-start; gap: var(--space-3); margin-bottom: var(--space-4);">
                <label style="min-width: 0;">
                    <span class="config-section-title" style="display: block; margin-bottom: var(--space-1);">
                        ${this.t('trigger_editor_modal.post_flow_output_label')}
                    </span>
                    <span class="hint">${this.t('trigger_editor_modal.post_flow_output_hint')}</span>
                </label>
                <platform-switch
                    .checked=${this._postFlowOutputEnabled}
                    @change=${(e) => {
                        this._postFlowOutputEnabled = e.detail.value;
                        this.isDirty = true;
                    }}
                ></platform-switch>
            </div>
            <div class="config-section-title">${this.t('trigger_editor_modal.output_section_title')}</div>
            ${showGeneralOutputIntro
                ? html`<p class="config-intro">${this.t('trigger_editor_modal.output_intro')}</p>`
                : nothing}
            ${this._outputActions.map((action, idx) => this._renderOutputAction(action, idx))}

            <button type="button" class="add-btn" @click=${this._addOutputAction}>
                <platform-icon name="plus" size="16"></platform-icon>
                ${this.t('trigger_editor_modal.output_add')}
            </button>
        `;
    }

    _renderOutputAction(action, idx) {
        const channelOptions = outputChannelTypesForTrigger(this._type);
        const allowedIds = new Set(channelOptions.map((c) => c.id));
        const showLegacyChannel = !allowedIds.has(action.channel);
        const mappingEntries = Object.entries(action.mapping);
        return html`
            <div class="output-action-item">
                <div class="output-action-content">
                    <div class="output-action-header">
                        <select
                            .value=${action.channel}
                            @change=${(e) => this._updateOutputAction(idx, 'channel', e.target.value)}
                        >
                            ${showLegacyChannel
                                ? html`<option value=${action.channel} ?selected=${true}>
                                    ${action.channel} (${this.t('trigger_editor_modal.output_channel_legacy')})
                                </option>`
                                : nothing}
                            ${channelOptions.map((ch) => html`
                                <option value=${ch.id} ?selected=${ch.id === action.channel && !showLegacyChannel}>
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
                        <span class="hint">${this.t('trigger_editor_modal.output_condition_hint')}</span>
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
        return html``;
    }

    renderSaveHeaderButton() {
        const busy = this._createOp.busy || this._updateOp.busy;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: busy,
            title: busy ? this.t('modal.saving') : this._saveHeaderTitle(),
        });
    }

    _setTab(tab) {
        if (tab === 'output' && !showTriggerOutputTab(this._type)) {
            return;
        }
        this._activeTab = tab;
    }

    _selectType(typeId) {
        this._verifyHintText = '';
        this._type = typeId;
        this._outputTelegramExpanded = false;
        if (typeId === 'cron') {
            this._postFlowOutputEnabled = false;
            if (this._activeTab === 'output') {
                this._activeTab = 'config';
            }
        } else if (this._postFlowOutputEnabled && typeId === 'telegram' && this._outputActions.length === 0) {
            if (this._triggerId.trim().length > 0) {
                this._outputActions = [defaultTelegramOutputAction(this._triggerId)];
            }
        }
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
        const ch = outputChannelTypesForTrigger(this._type);
        const defaultChannel = ch[0] ? ch[0].id : 'telegram';
        const next
            = this._type === 'telegram' && defaultChannel === 'telegram'
                ? defaultTelegramOutputAction(this._triggerId)
                : { channel: defaultChannel, action: 'send_message', mapping: {}, config: {}, condition: '' };
        this._outputActions = [...this._outputActions, next];
        this._outputTelegramExpanded = true;
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
        if (!this._branchId.trim()) {
            return { branch_id: this.t('trigger_editor_modal.error_branch_required') };
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

        const outTab = showTriggerOutputTab(this._type);
        const postFlow = outTab && this._postFlowOutputEnabled;
        const outputActions = postFlow
            ? this._outputActions.map((a) => {
                const c = a.condition.trim();
                return {
                    channel: a.channel,
                    action: a.action,
                    mapping: a.mapping,
                    config: a.config,
                    condition: c.length > 0 ? c : null,
                };
            })
            : [];

        const body = {
            trigger_id: this._triggerId.trim(),
            name: this._name.trim(),
            type: this._type,
            enabled: this._enabled,
            config: this._config,
            output_mapping: outputMapping,
            output_actions: outputActions,
            post_flow_output_enabled: postFlow,
            branch_id: this._branchId.trim(),
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
                    post_flow_output_enabled: body.post_flow_output_enabled,
                    branch_id: body.branch_id,
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
