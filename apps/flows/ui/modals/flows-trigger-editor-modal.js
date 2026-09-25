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
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-cron-field.js';
import '@platform/lib/components/platform-timezone-picker.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-segmented-control.js';
import { asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import { TRIGGER_TYPES } from '../_helpers/trigger-types.js';
import {
    EMAIL_FILTER_PRESETS,
    MAPPING_EXAMPLES,
    TRIGGER_SAMPLE_DOCS,
    TRIGGER_SAMPLE_PAYLOADS,
    buildTelegramCurl,
    buildWebhookCurl,
    buildWebhookEndpointUrl,
} from '../_helpers/trigger-samples.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { MAIL_EVENTS } from '@platform/lib/events/reducers/mail.js';

const TRIGGER_ID_PATTERN = /^[a-zA-Z][a-zA-Z0-9_-]*$/;

const CHANNEL_TYPES = Object.freeze([
    { id: 'telegram', labelKey: 'channel_telegram' },
    { id: 'email',    labelKey: 'channel_email' },
    { id: 'webhook',  labelKey: 'channel_webhook' },
]);

/**
 * Куда доставлять ответ flow — привязываем к типу входа: Telegram-вход = только ответ в Telegram
 * (отдельные сценарии: cron / webhook / platform_event с другими графами).
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
 * Вкладка «Вывод» не показывается для cron и platform_event: пост-рассылка не используется.
 * @param {string} typeId
 * @returns {boolean}
 */
function showTriggerOutputTab(typeId) {
    return typeId.length > 0 && typeId !== 'cron' && typeId !== 'platform_event';
}

const EVENT_FILTER_OPS = Object.freeze([
    { id: 'eq', labelKey: 'event_filter_op_eq' },
    { id: 'ne', labelKey: 'event_filter_op_ne' },
    { id: 'contains', labelKey: 'event_filter_op_contains' },
]);

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
 * Compact webhook callback preset (recipient URL filled by user).
 * @param {string} [callbackUrl]
 */
function defaultWebhookCallbackOutputAction(callbackUrl) {
    const url = String(callbackUrl || '').trim();
    return {
        channel: 'webhook',
        action: 'send_message',
        mapping: {
            recipient: url.length > 0 ? `@const:${url}` : '',
            text: '@state:response',
        },
        config: {},
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

const WEBHOOK_SECRET_HEADER_PRESETS = Object.freeze([
    'X-Trigger-Secret',
    'X-Webhook-Secret',
    'Authorization',
]);

const WEBHOOK_SECRET_HEADER_CUSTOM = 'custom';
const DEFAULT_WEBHOOK_SECRET_HEADER = 'X-Trigger-Secret';

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
        _mappingTestResultText: { state: true },
        _catalogItems: { state: true },
        _catalogLoadError: { state: true },
        _catalogEnumConfig: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        ...formStyles,
        css`
            :host { --modal-max-width: 920px; }

            .modal-tabs {
                margin-bottom: var(--space-4);
            }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .field > label { font-size: var(--text-sm); color: var(--text-secondary); font-weight: var(--font-medium); }
            .field > .hint { font-size: var(--text-xs); color: var(--text-tertiary); }

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
            .event-filter-row {
                display: grid;
                grid-template-columns: 1fr auto 1fr auto;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
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

            .examples-list { font-size: var(--text-sm); font-family: var(--font-mono); display: flex; flex-direction: column; gap: var(--space-1); }
            .examples-row {
                padding: var(--space-2) var(--space-3);
                display: flex;
                gap: var(--space-3);
                align-items: baseline;
                flex-wrap: wrap;
                cursor: pointer;
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                background: transparent;
                text-align: left;
                font: inherit;
                color: inherit;
                width: 100%;
            }
            .examples-row:hover {
                background: var(--accent-subtle);
                border-color: var(--glass-border-subtle);
            }
            .examples-row code { color: var(--accent); }
            .examples-row .desc { color: var(--text-tertiary); font-family: var(--font-sans); }
            .examples-click-hint { font-size: var(--text-xs); color: var(--text-tertiary); margin: 0 0 var(--space-2); }
            .webhook-endpoint-row {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: var(--space-2);
                align-items: end;
            }
            .dx-toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .curl-box,
            .sample-json {
                margin: 0;
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                line-height: 1.45;
                white-space: pre-wrap;
                word-break: break-word;
                overflow-x: auto;
                max-height: 280px;
            }
            .sample-docs {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin: var(--space-2) 0 0;
            }
            .sample-docs a {
                color: var(--accent);
            }
            .sample-payload-block {
                margin-top: var(--space-4);
            }

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
            .header-trigger-actions {
                display: flex;
                gap: var(--space-1);
                align-items: center;
            }
            .email-stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .email-cta {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
            }
            .email-cta-text {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.45;
            }
            .email-filter-hint {
                margin: 0;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
            }
            .email-mailbox-list,
            .email-preset-list {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .email-chip {
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                text-align: left;
                line-height: 1.35;
            }
            .email-chip:hover {
                background: var(--accent-subtle);
                border-color: var(--accent);
            }
            .email-chip.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-medium);
            }
            .email-chip-meta {
                display: block;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
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
        this._mappingTestResultText = '';
        this._catalogItems = [];
        this._catalogLoadError = '';
        this._catalogEnumConfig = Object.freeze({ values: Object.freeze([]) });
        this._catalogLoadStarted = false;
        this._catalogOp = this.useOp('flows/platform_events_catalog');
        this._createOp = this.useOp('flows/trigger_create');
        this._updateOp = this.useOp('flows/trigger_update');
        this._listOp = this.useOp('flows/triggers_list');
        this._verifyOp = this.useOp('flows/trigger_verify');
        this._reregisterOp = this.useOp('flows/trigger_reregister');
        this._testOp = this.useOp('flows/trigger_test');
        this._editor = this.useOp('flows/editor');
        this._flowsCat = this.useResource('flows/flows', { autoload: false });
        this._mailSelect = this.select((s) => s.mail);
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(MAIL_EVENTS.BINDINGS_LOADED, () => {
            if (this._type === 'email') {
                this._maybeAutofillMailboxBinding();
            }
        });
        this.useEvent(MAIL_EVENTS.BINDING_CREATED, () => {
            if (this._type === 'email') {
                this._maybeAutofillMailboxBinding();
            }
        });
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId') && this.flowId) {
            this._ensureFlowForBranches();
        }
        if (changed.has('_type') && this._type === 'platform_event') {
            this._ensurePlatformEventsCatalogLoaded();
        }
        if (this._type === 'email') {
            this._maybeAutofillMailboxBinding();
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
        this._mappingTestResultText = '';
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
            if (t.type === 'email') {
                this._config = this._normalizeEmailConfig(this._config);
                this._ensureMailLoaded();
            }
            if (t.type === 'webhook') {
                this._config = this._normalizeWebhookConfig(this._config);
            }
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
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        ?disabled=${this._verifyOp.busy || this._reregisterOp.busy}
                        title=${this.t('trigger_editor_modal.verify_btn_title')}
                        aria-label=${this.t('trigger_editor_modal.verify_btn_title')}
                        @click=${(e) => {
            e.stopPropagation();
            void this._onTriggerVerify();
        }}
                    >
                        <platform-icon name="check" size="16"></platform-icon>
                    </platform-button>
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        ?disabled=${reregisterDisabled}
                        title=${this.t('trigger_editor_modal.reregister_btn_title')}
                        aria-label=${this.t('trigger_editor_modal.reregister_btn_title')}
                        @click=${(e) => {
            e.stopPropagation();
            void this._onTriggerReregister();
        }}
                    >
                        <platform-icon name="rotate-ccw" size="16"></platform-icon>
                    </platform-button>
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
            return formatJsonPretty(v);
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
        const r = await this._verifyOp.run({ flow_id: this.flowId, ...body });
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

    _triggerTabItems() {
        const items = [
            { value: 'config', label: this.t('trigger_editor_modal.tab_config') },
            { value: 'mapping', label: this.t('trigger_editor_modal.tab_mapping') },
        ];
        if (showTriggerOutputTab(this._type)) {
            items.push({ value: 'output', label: this.t('trigger_editor_modal.tab_output') });
        }
        return items;
    }

    renderBody() {
        return html`
            <platform-segmented-control
                class="modal-tabs"
                full-width
                density="compact"
                .value=${this._activeTab}
                .items=${this._triggerTabItems()}
                aria-label=${this.t('trigger_editor_modal.tabs_aria')}
                @change=${(e) => this._setTab(e.detail.value)}
            ></platform-segmented-control>

            ${this._validationError ? html`<div class="form-error">${this._validationError}</div>` : ''}

            ${this._activeTab === 'config' ? this._renderConfigTab() : ''}
            ${this._activeTab === 'mapping' ? this._renderMappingTab() : ''}
            ${this._activeTab === 'output' && showTriggerOutputTab(this._type) ? this._renderOutputTab() : ''}
        `;
    }

    _renderConfigTab() {
        const editing = Boolean(this.trigger);
        const branchEnumConfig = { values: this._branchSelectRows() };
        return html`
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_branch')}</label>
                <platform-field
                    type="enum"
                    mode="edit"
                    .value=${this._branchId}
                    .config=${branchEnumConfig}
                    @change=${(e) => {
                        const v = e.detail.value;
                        if (typeof v !== 'string') {
                            throw new TypeError('flows-trigger-editor-modal: branch_id expects string detail.value');
                        }
                        this._branchId = v;
                        this.isDirty = true;
                    }}
                ></platform-field>
                <span class="hint">${this.t('trigger_editor_modal.hint_branch')}</span>
            </div>

            <div class="field">
                <label>${this.t('trigger_editor_modal.field_id')}</label>
                <platform-field
                    type="string"
                    mode="edit"
                    .value=${this._triggerId}
                    ?disabled=${editing}
                    placeholder=${this.t('trigger_editor_modal.field_id_placeholder')}
                    @change=${(e) => {
                        const v = e.detail.value;
                        if (typeof v !== 'string') {
                            throw new TypeError('flows-trigger-editor-modal: trigger_id expects string detail.value');
                        }
                        this._triggerId = v;
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_name')}</label>
                <platform-field
                    type="string"
                    mode="edit"
                    .value=${this._name}
                    placeholder=${this.t('trigger_editor_modal.field_name_placeholder')}
                    @change=${(e) => {
                        const v = e.detail.value;
                        if (typeof v !== 'string') {
                            throw new TypeError('flows-trigger-editor-modal: name expects string detail.value');
                        }
                        this._name = v;
                        this.isDirty = true;
                    }}
                ></platform-field>
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
            case 'platform_event': return this._renderPlatformEventConfig();
            default:         return '';
        }
    }

    _renderTelegramConfig() {
        const c = this._config;
        const allowedUsers = Array.isArray(c.allowed_users) ? c.allowed_users.join(', ') : asString(c.allowed_users);
        const origin = typeof window !== 'undefined' && window.location
            ? String(window.location.origin)
            : '';
        const flowId = asString(this.flowId);
        const triggerId = asString(this._triggerId).trim();
        const internalSecret = asString(c._secret_token || c.secret_token);
        const curl = origin && flowId
            ? buildTelegramCurl({
                origin,
                flowId,
                triggerId,
                secretToken: internalSecret,
            })
            : '';
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.section_telegram')}</div>
                <p class="config-intro">${this.t('trigger_editor_modal.telegram_intro')}</p>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_bot_token')}</label>
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${asString(c.bot_token)}
                        placeholder=${this.t('trigger_editor_modal.field_bot_token_placeholder')}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-trigger-editor-modal: bot_token expects string detail.value');
                            }
                            this._setConfig('bot_token', v);
                        }}
                    ></platform-field>
                    <span class="hint">${this.t('trigger_editor_modal.hint_bot_token')}</span>
                </div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_allowed_users')}</label>
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${allowedUsers}
                        placeholder=${this.t('trigger_editor_modal.field_allowed_users_placeholder')}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-trigger-editor-modal: allowed_users expects string detail.value');
                            }
                            this._setConfigList('allowed_users', v, 'int');
                        }}
                    ></platform-field>
                    <span class="hint">${this.t('trigger_editor_modal.hint_allowed_users')}</span>
                </div>
                ${curl ? html`
                    <div class="field">
                        <label>${this.t('trigger_editor_modal.field_ready_curl')}</label>
                        <p class="hint">${this.t('trigger_editor_modal.hint_telegram_curl')}</p>
                        <pre class="curl-box">${curl}</pre>
                        <div class="dx-toolbar">
                            <platform-button
                                variant="primary"
                                density="compact"
                                @click=${() => this._copyText(
                                    curl,
                                    'flows:trigger_editor_modal.toast_curl_copied',
                                    'flows:trigger_editor_modal.toast_curl_copy_failed',
                                )}
                            >
                                ${this.t('trigger_editor_modal.copy_curl')}
                            </platform-button>
                        </div>
                    </div>
                ` : nothing}
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
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${asString(c.initial_content)}
                        placeholder=${this.t('trigger_editor_modal.field_initial_content_placeholder')}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-trigger-editor-modal: initial_content expects string detail.value');
                            }
                            this._setConfig('initial_content', v);
                        }}
                    ></platform-field>
                </div>
            </div>
        `;
    }

    _renderWebhookConfig() {
        const c = this._normalizeWebhookConfig(this._config);
        const secretHeader = asString(c.secret_header) || DEFAULT_WEBHOOK_SECRET_HEADER;
        const headerIsCustom = !WEBHOOK_SECRET_HEADER_PRESETS.includes(secretHeader);
        const headerSelectValue = headerIsCustom ? WEBHOOK_SECRET_HEADER_CUSTOM : secretHeader;
        const allowedIps = Array.isArray(c.allowed_ips)
            ? c.allowed_ips.filter((item) => typeof item === 'string')
            : [];
        const flowId = asString(this.flowId);
        const triggerId = asString(this._triggerId).trim();
        const origin = typeof window !== 'undefined' && window.location
            ? String(window.location.origin)
            : '';
        const endpointUrl = origin
            ? buildWebhookEndpointUrl({ origin, flowId, triggerId })
            : `/flows/api/v1/triggers/webhook/${flowId}/${triggerId || '<trigger_id>'}`;
        const curl = origin
            ? buildWebhookCurl({
                origin,
                flowId,
                triggerId,
                secretToken: asString(c.secret_token),
                secretHeader,
            })
            : '';
        const secretHint = this.t('trigger_editor_modal.hint_secret_token', {
            header: secretHeader,
        });
        const headerEnumConfig = {
            values: [
                ...WEBHOOK_SECRET_HEADER_PRESETS.map((name) => ({ value: name, label: name })),
                {
                    value: WEBHOOK_SECRET_HEADER_CUSTOM,
                    label: this.t('trigger_editor_modal.secret_header_custom'),
                },
            ],
        };
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.section_webhook')}</div>
                <p class="config-intro">${this.t('trigger_editor_modal.webhook_intro')}</p>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_webhook_url')}</label>
                    <div class="webhook-endpoint-row">
                        <platform-field
                            type="string"
                            mode="view"
                            .value=${endpointUrl}
                        ></platform-field>
                        <platform-button
                            variant="ghost"
                            density="compact"
                            @click=${() => this._copyText(
                                endpointUrl,
                                'flows:trigger_editor_modal.toast_webhook_url_copied',
                                'flows:trigger_editor_modal.toast_webhook_url_copy_failed',
                            )}
                        >
                            ${this.t('trigger_editor_modal.copy_webhook_url')}
                        </platform-button>
                    </div>
                    <span class="hint">${this.t('trigger_editor_modal.hint_webhook_url')}</span>
                </div>
                ${curl ? html`
                    <div class="field">
                        <label>${this.t('trigger_editor_modal.field_ready_curl')}</label>
                        <p class="hint">${this.t('trigger_editor_modal.hint_ready_curl')}</p>
                        <pre class="curl-box">${curl}</pre>
                        <div class="dx-toolbar">
                            <platform-button
                                variant="primary"
                                density="compact"
                                @click=${() => this._copyText(
                                    curl,
                                    'flows:trigger_editor_modal.toast_curl_copied',
                                    'flows:trigger_editor_modal.toast_curl_copy_failed',
                                )}
                            >
                                ${this.t('trigger_editor_modal.copy_curl')}
                            </platform-button>
                        </div>
                    </div>
                ` : nothing}
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_secret_token')}</label>
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${asString(c.secret_token)}
                        placeholder=${this.t('trigger_editor_modal.field_secret_token_placeholder')}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-trigger-editor-modal: secret_token expects string detail.value');
                            }
                            this._setConfig('secret_token', v);
                        }}
                    ></platform-field>
                    <span class="hint">${secretHint}</span>
                </div>
                <div class="field">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('trigger_editor_modal.field_secret_header')}
                        .hint=${this.t('trigger_editor_modal.hint_secret_header')}
                        .value=${headerSelectValue}
                        .config=${headerEnumConfig}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-trigger-editor-modal: secret_header enum expects string');
                            }
                            if (v === WEBHOOK_SECRET_HEADER_CUSTOM) {
                                if (!headerIsCustom) {
                                    this._setConfig('secret_header', 'X-Custom-Secret');
                                }
                                return;
                            }
                            this._setConfig('secret_header', v);
                        }}
                    ></platform-field>
                </div>
                ${headerIsCustom ? html`
                    <div class="field">
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('trigger_editor_modal.field_secret_header_custom')}
                            .value=${secretHeader}
                            placeholder=${this.t('trigger_editor_modal.field_secret_header_custom_placeholder')}
                            @change=${(e) => {
                                const v = e.detail.value;
                                if (typeof v !== 'string') {
                                    throw new TypeError('flows-trigger-editor-modal: custom secret_header expects string');
                                }
                                this._setConfig('secret_header', v.trim() || DEFAULT_WEBHOOK_SECRET_HEADER);
                            }}
                        ></platform-field>
                    </div>
                ` : nothing}
                <div class="field">
                    <platform-field
                        type="array"
                        mode="edit"
                        .label=${this.t('trigger_editor_modal.field_allowed_ips')}
                        .hint=${this.t('trigger_editor_modal.hint_allowed_ips')}
                        .value=${allowedIps}
                        .config=${{ preserve_case: true }}
                        placeholder=${this.t('trigger_editor_modal.field_allowed_ips_placeholder')}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (!Array.isArray(v)) {
                                throw new TypeError('flows-trigger-editor-modal: allowed_ips expects array detail.value');
                            }
                            this._setConfig(
                                'allowed_ips',
                                v.filter((item) => typeof item === 'string' && item.trim().length > 0),
                            );
                        }}
                    ></platform-field>
                </div>
            </div>
        `;
    }

    _renderEmailConfig() {
        const mail = this._mailSelect.value;
        const bindings = Array.isArray(mail.bindings) ? mail.bindings : [];
        const connection = mail.connection;
        const c = this._config;
        const selectedId = typeof c.mailbox_binding_id === 'string' ? c.mailbox_binding_id : '';
        const subjectContains = typeof c.subject_contains === 'string' ? c.subject_contains : '';
        const allowedSendersList = Array.isArray(c.allowed_senders)
            ? c.allowed_senders.filter((item) => typeof item === 'string')
            : [];
        const allowedSenders = allowedSendersList.join(', ');
        const activePresetId = this._resolveActiveEmailFilterPresetId(
            allowedSendersList,
            subjectContains,
        );

        if (bindings.length === 0) {
            const noConnection = connection === null;
            return html`
                <div class="config-section">
                    <div class="config-section-title">${this.t('trigger_editor_modal.section_email')}</div>
                    <div class="email-cta">
                        <p class="email-cta-text">
                            ${noConnection
                                ? this.t('trigger_editor_modal.email_cta_no_connection')
                                : this.t('trigger_editor_modal.email_cta_no_mailbox')}
                        </p>
                        <platform-button variant="primary" @click=${() => this._openMailSettings()}>
                            ${noConnection
                                ? this.t('trigger_editor_modal.email_cta_connect')
                                : this.t('trigger_editor_modal.email_cta_setup_mailbox')}
                        </platform-button>
                    </div>
                </div>
            `;
        }

        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.section_email')}</div>
                <div class="email-stack">
                    <p class="email-filter-hint">${this.t('trigger_editor_modal.hint_mailbox')}</p>
                    <div class="email-mailbox-list" role="listbox" aria-label=${this.t('trigger_editor_modal.field_mailbox')}>
                        ${bindings.map((binding) => {
                            const bindingId = binding.mailbox_binding_id;
                            if (typeof bindingId !== 'string' || bindingId.length === 0) {
                                throw new TypeError('flows-trigger-editor-modal: mailbox_binding_id missing');
                            }
                            const isActive = bindingId === selectedId;
                            return html`
                                <article
                                    role="option"
                                    tabindex="0"
                                    class="email-chip ${isActive ? 'active' : ''}"
                                    aria-selected=${isActive ? 'true' : 'false'}
                                    @click=${() => this._selectMailboxBinding(bindingId)}
                                    @keydown=${(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            this._selectMailboxBinding(bindingId);
                                        }
                                    }}
                                >
                                    ${binding.email_address}
                                    ${binding.is_default
                                        ? html`<span class="email-chip-meta">${this.t('trigger_editor_modal.mailbox_default_badge')}</span>`
                                        : nothing}
                                </article>
                            `;
                        })}
                    </div>
                    <platform-button variant="ghost" @click=${() => this._openMailSettings()}>
                        ${this.t('trigger_editor_modal.email_open_settings')}
                    </platform-button>
                    <div class="config-section-title">${this.t('trigger_editor_modal.section_email_filter')}</div>
                    <p class="email-filter-hint">${this.t('trigger_editor_modal.hint_email_filter_presets')}</p>
                    <div class="email-preset-list" role="listbox" aria-label=${this.t('trigger_editor_modal.section_email_filter')}>
                        ${EMAIL_FILTER_PRESETS.map((preset) => {
                            const isActive = preset.id === activePresetId;
                            return html`
                                <article
                                    role="option"
                                    tabindex="0"
                                    class="email-chip ${isActive ? 'active' : ''}"
                                    aria-selected=${isActive ? 'true' : 'false'}
                                    @click=${() => this._applyEmailFilterPreset(preset.id)}
                                    @keydown=${(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            this._applyEmailFilterPreset(preset.id);
                                        }
                                    }}
                                >
                                    ${this.t(`trigger_editor_modal.${preset.labelKey}`)}
                                </article>
                            `;
                        })}
                    </div>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('trigger_editor_modal.field_allowed_senders')}
                        .placeholder=${this.t('trigger_editor_modal.field_allowed_senders_placeholder')}
                        .value=${allowedSenders}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-trigger-editor-modal: allowed_senders expects string');
                            }
                            this._setConfigList('allowed_senders', v, 'string');
                        }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('trigger_editor_modal.field_subject_contains')}
                        .placeholder=${this.t('trigger_editor_modal.field_subject_contains_placeholder')}
                        .value=${subjectContains}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-trigger-editor-modal: subject_contains expects string');
                            }
                            this._setConfig('subject_contains', v);
                        }}
                    ></platform-field>
                </div>
            </div>
        `;
    }

    _ensureMailLoaded() {
        this.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null);
        this.dispatch(MAIL_EVENTS.CONNECTION_LOAD_REQUESTED, null);
    }

    _openMailSettings() {
        this.openModal('platform.mail', { openSettings: true });
    }

    _normalizeEmailConfig(config) {
        const src = isPlainObject(config) ? config : {};
        const mailboxBindingId = typeof src.mailbox_binding_id === 'string'
            ? src.mailbox_binding_id
            : '';
        const allowedSenders = Array.isArray(src.allowed_senders)
            ? src.allowed_senders.filter((item) => typeof item === 'string')
            : [];
        const subjectContains = typeof src.subject_contains === 'string'
            ? src.subject_contains
            : '';
        return {
            mailbox_binding_id: mailboxBindingId,
            allowed_senders: allowedSenders,
            subject_contains: subjectContains,
        };
    }

    _maybeAutofillMailboxBinding() {
        const mail = this._mailSelect.value;
        const bindings = Array.isArray(mail.bindings) ? mail.bindings : [];
        if (bindings.length === 0) return;
        const current = this._config.mailbox_binding_id;
        if (typeof current === 'string' && current.length > 0) {
            if (bindings.some((b) => b.mailbox_binding_id === current)) {
                return;
            }
        }
        const preferred = bindings.find((b) => b.is_default === true);
        const next = preferred || bindings[0];
        if (!next || typeof next.mailbox_binding_id !== 'string') {
            return;
        }
        this._config = {
            ...this._normalizeEmailConfig(this._config),
            mailbox_binding_id: next.mailbox_binding_id,
        };
    }

    _selectMailboxBinding(mailboxBindingId) {
        if (typeof mailboxBindingId !== 'string' || mailboxBindingId.length === 0) {
            throw new TypeError('flows-trigger-editor-modal: mailbox_binding_id required');
        }
        this._config = {
            ...this._normalizeEmailConfig(this._config),
            mailbox_binding_id: mailboxBindingId,
        };
        this.isDirty = true;
    }

    /**
     * @param {readonly string[]} allowedSenders
     * @param {string} subjectContains
     * @returns {string | null}
     */
    _resolveActiveEmailFilterPresetId(allowedSenders, subjectContains) {
        const subject = subjectContains.trim();
        const sendersKey = [...allowedSenders].map((s) => s.trim()).filter((s) => s.length > 0).sort().join(',');
        for (const preset of EMAIL_FILTER_PRESETS) {
            const presetSubject = preset.subjectValueKey === null
                ? ''
                : this.t(`trigger_editor_modal.${preset.subjectValueKey}`).trim();
            const presetSendersKey = [...preset.allowed_senders].map((s) => s.trim()).filter((s) => s.length > 0).sort().join(',');
            if (sendersKey === presetSendersKey && subject === presetSubject) {
                return preset.id;
            }
        }
        return null;
    }

    _applyEmailFilterPreset(presetId) {
        const preset = EMAIL_FILTER_PRESETS.find((item) => item.id === presetId);
        if (!preset) {
            throw new Error(`flows-trigger-editor-modal: unknown email filter preset ${presetId}`);
        }
        const subjectContains = preset.subjectValueKey === null
            ? ''
            : this.t(`trigger_editor_modal.${preset.subjectValueKey}`);
        this._config = {
            ...this._normalizeEmailConfig(this._config),
            allowed_senders: [...preset.allowed_senders],
            subject_contains: subjectContains,
        };
        this.isDirty = true;
    }

    _maybeApplyEmailMappingDefaults() {
        if (this._type !== 'email') {
            return;
        }
        if (this._outputMapping.some((row) => asString(row.state).trim().length > 0)) {
            return;
        }
        this._applyAllMappingExamples();
    }

    _ensurePlatformEventsCatalogLoaded() {
        if (this._catalogLoadStarted) return;
        this._catalogLoadStarted = true;
        this._catalogLoadError = '';
        void this._catalogOp.run({}).then((r) => {
            if (r === null) {
                this._catalogLoadStarted = false;
                const err = this._catalogOp.error;
                this._catalogLoadError = typeof err === 'string' && err.length > 0
                    ? err
                    : this.t('trigger_editor_modal.error_event_catalog_load');
                this._catalogItems = [];
                this._rebuildCatalogEnumConfig('');
                return;
            }
            if (!Array.isArray(r.items)) {
                this._catalogLoadStarted = false;
                throw new TypeError('flows-trigger-editor-modal: catalog response.items must be an array');
            }
            this._catalogItems = r.items.map((raw) => this._normalizeCatalogItem(raw));
            this._catalogLoadError = '';
            const selectedType = asString(this._config.event_type);
            this._rebuildCatalogEnumConfig(selectedType);
        });
    }

    /**
     * Стабильный `.config` для platform-field-enum: новый object только при
     * реальной смене набора event_type (не на каждый render модалки).
     * @param {string} selectedType
     */
    _rebuildCatalogEnumConfig(selectedType) {
        const items = Array.isArray(this._catalogItems) ? this._catalogItems : [];
        const values = items.map((item) => ({
            value: item.event_type,
            label: item.description
                ? `${item.event_type} — ${item.description}`
                : item.event_type,
        }));
        if (selectedType.length > 0 && !values.some((v) => v.value === selectedType)) {
            values.unshift({ value: selectedType, label: selectedType });
        }
        this._catalogEnumConfig = Object.freeze({ values: Object.freeze(values) });
    }

    /**
     * @param {unknown} raw
     */
    _normalizeCatalogItem(raw) {
        if (!isPlainObject(raw)) {
            throw new TypeError('flows-trigger-editor-modal: catalog item must be object');
        }
        const eventType = raw.event_type;
        if (typeof eventType !== 'string' || !eventType.trim()) {
            throw new TypeError('flows-trigger-editor-modal: catalog item.event_type required');
        }
        const description = typeof raw.description === 'string' ? raw.description : '';
        const filterFieldsRaw = Array.isArray(raw.filter_fields) ? raw.filter_fields : [];
        const filterFields = filterFieldsRaw.map((field) => this._normalizeFilterField(field));
        return {
            event_type: eventType,
            description,
            filter_fields: filterFields,
        };
    }

    /**
     * @param {unknown} raw
     */
    _normalizeFilterField(raw) {
        if (!isPlainObject(raw)) {
            throw new TypeError('flows-trigger-editor-modal: filter_fields item must be object');
        }
        const path = raw.path;
        const label = raw.label;
        const valueKind = raw.value_kind;
        const opsRaw = raw.ops;
        if (typeof path !== 'string' || !path.trim()) {
            throw new TypeError('flows-trigger-editor-modal: filter_fields.path required');
        }
        if (typeof label !== 'string' || !label.trim()) {
            throw new TypeError('flows-trigger-editor-modal: filter_fields.label required');
        }
        if (
            valueKind !== 'string'
            && valueKind !== 'integer'
            && valueKind !== 'number'
            && valueKind !== 'boolean'
            && valueKind !== 'enum'
        ) {
            throw new TypeError(`flows-trigger-editor-modal: unknown value_kind ${String(valueKind)}`);
        }
        if (!Array.isArray(opsRaw) || opsRaw.length === 0) {
            throw new TypeError('flows-trigger-editor-modal: filter_fields.ops required');
        }
        const ops = opsRaw.map((op) => {
            if (op !== 'eq' && op !== 'ne' && op !== 'contains') {
                throw new TypeError(`flows-trigger-editor-modal: unknown filter op ${String(op)}`);
            }
            return op;
        });
        let enumValues = null;
        if (valueKind === 'enum') {
            if (!Array.isArray(raw.enum_values) || raw.enum_values.length === 0) {
                throw new TypeError('flows-trigger-editor-modal: enum filter_fields.enum_values required');
            }
            enumValues = raw.enum_values.map((v) => {
                if (typeof v !== 'string') {
                    throw new TypeError('flows-trigger-editor-modal: enum_values must be strings');
                }
                return v;
            });
        }
        return {
            path,
            label,
            description: typeof raw.description === 'string' ? raw.description : '',
            value_kind: valueKind,
            enum_values: enumValues,
            ops,
        };
    }

    _selectedCatalogEntry() {
        const selectedType = asString(this._config.event_type);
        const items = Array.isArray(this._catalogItems) ? this._catalogItems : [];
        return items.find((item) => item.event_type === selectedType) ?? null;
    }

    _platformEventFilters() {
        const raw = this._config.filters;
        if (!Array.isArray(raw)) return [];
        return raw.filter((f) => isPlainObject(f));
    }

    _setPlatformEventFilters(filters) {
        this._setConfig('filters', filters);
    }

    /**
     * @param {{ value_kind: string, enum_values: string[] | null }} field
     * @param {unknown} current
     */
    _defaultFilterValue(field, current) {
        if (field.value_kind === 'boolean') {
            return typeof current === 'boolean' ? current : false;
        }
        if (field.value_kind === 'integer' || field.value_kind === 'number') {
            return typeof current === 'number' ? current : 0;
        }
        if (field.value_kind === 'enum') {
            const values = field.enum_values;
            if (values === null || values.length === 0) {
                throw new TypeError('flows-trigger-editor-modal: enum field without values');
            }
            if (typeof current === 'string' && values.includes(current)) {
                return current;
            }
            return values[0];
        }
        return typeof current === 'string' ? current : '';
    }

    _renderPlatformEventConfig() {
        this._ensurePlatformEventsCatalogLoaded();
        const c = this._config;
        const selectedType = asString(c.event_type);
        const selectedEntry = this._selectedCatalogEntry();
        const filterFields = selectedEntry !== null ? selectedEntry.filter_fields : [];
        const filters = this._platformEventFilters();
        const canAddFilters = selectedType.length > 0 && filterFields.length > 0;
        const pathEnumValues = filterFields.map((field) => ({
            value: field.path,
            label: `${field.path} — ${field.label}`,
        }));
        const catalogBusy = this._catalogOp.busy;
        const catalogEmpty = !catalogBusy
            && this._catalogLoadError.length === 0
            && this._catalogItems.length === 0
            && this._catalogLoadStarted;

        return html`
            <div class="config-section">
                <div class="config-section-title">${this.t('trigger_editor_modal.section_platform_event')}</div>
                <div class="field">
                    <label>${this.t('trigger_editor_modal.field_event_type')}</label>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .value=${selectedType}
                        .config=${this._catalogEnumConfig}
                        .placeholder=${catalogBusy
                            ? this.t('trigger_editor_modal.event_catalog_loading')
                            : ''}
                        .hint=${this.t('trigger_editor_modal.hint_event_type')}
                        ?disabled=${catalogBusy}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-trigger-editor-modal: event_type expects string detail.value');
                            }
                            this._config = {
                                ...this._config,
                                event_type: v,
                                filters: [],
                            };
                            this._rebuildCatalogEnumConfig(v);
                        }}
                    ></platform-field>
                    ${this._catalogLoadError.length > 0
                        ? html`<span class="hint" style="color: var(--error);">${this._catalogLoadError}</span>`
                        : catalogEmpty
                            ? html`<span class="hint">${this.t('trigger_editor_modal.error_event_catalog_empty')}</span>`
                            : nothing}
                </div>
                <div class="mapping-add-row">
                    <span style="font-weight: var(--font-medium); color: var(--text-secondary);">
                        ${this.t('trigger_editor_modal.event_filters_label')}
                    </span>
                    <platform-button
                        variant="ghost"
                        density="compact"
                        ?disabled=${!canAddFilters}
                        @click=${() => {
                            if (!canAddFilters) return;
                            const first = filterFields[0];
                            this._setPlatformEventFilters([
                                ...filters,
                                {
                                    path: first.path,
                                    op: first.ops[0],
                                    value: this._defaultFilterValue(first, ''),
                                },
                            ]);
                        }}
                    >
                        + ${this.t('trigger_editor_modal.event_filters_add')}
                    </platform-button>
                </div>
                ${selectedType.length > 0 && filterFields.length === 0
                    ? html`<div class="mapping-empty">${this.t('trigger_editor_modal.event_filters_no_fields')}</div>`
                    : nothing}
                ${filters.length === 0 && canAddFilters
                    ? html`<div class="mapping-empty">${this.t('trigger_editor_modal.event_filters_empty')}</div>`
                    : nothing}
                ${filters.map((f, idx) => this._renderPlatformEventFilterRow(f, idx, filters, filterFields, pathEnumValues))}
                <span class="hint">${this.t('trigger_editor_modal.hint_event_filters')}</span>
            </div>
        `;
    }

    /**
     * @param {Record<string, unknown>} filterRow
     * @param {number} idx
     * @param {Record<string, unknown>[]} filters
     * @param {ReturnType<FlowsTriggerEditorModal['_normalizeFilterField']>[]} filterFields
     * @param {{ value: string, label: string }[]} pathEnumValues
     */
    _renderPlatformEventFilterRow(filterRow, idx, filters, filterFields, pathEnumValues) {
        const path = asString(filterRow.path);
        const field = filterFields.find((item) => item.path === path) ?? filterFields[0] ?? null;
        if (field === null) {
            return nothing;
        }
        const op = asString(filterRow.op) || field.ops[0];
        const opEnumConfig = {
            values: field.ops.map((opId) => {
                const meta = EVENT_FILTER_OPS.find((item) => item.id === opId);
                if (meta === undefined) {
                    throw new TypeError(`flows-trigger-editor-modal: missing i18n for op ${opId}`);
                }
                return {
                    value: opId,
                    label: this.t(`trigger_editor_modal.${meta.labelKey}`),
                };
            }),
        };
        const value = this._defaultFilterValue(field, filterRow.value);
        return html`
            <div class="event-filter-row">
                <platform-field
                    type="enum"
                    mode="edit"
                    .value=${field.path}
                    .config=${{ values: pathEnumValues }}
                    .hint=${field.description}
                    @change=${(e) => {
                        const v = e.detail.value;
                        if (typeof v !== 'string') {
                            throw new TypeError('flows-trigger-editor-modal: filter path expects string detail.value');
                        }
                        const nextField = filterFields.find((item) => item.path === v);
                        if (nextField === undefined) {
                            throw new TypeError(`flows-trigger-editor-modal: unknown filter path ${v}`);
                        }
                        this._setPlatformEventFilters(
                            filters.map((row, i) => (i === idx
                                ? {
                                    path: nextField.path,
                                    op: nextField.ops[0],
                                    value: this._defaultFilterValue(nextField, ''),
                                }
                                : row)),
                        );
                    }}
                ></platform-field>
                <platform-field
                    type="enum"
                    mode="edit"
                    .value=${op}
                    .config=${opEnumConfig}
                    @change=${(e) => {
                        const v = e.detail.value;
                        if (typeof v !== 'string') {
                            throw new TypeError('flows-trigger-editor-modal: filter op expects string detail.value');
                        }
                        this._setPlatformEventFilters(
                            filters.map((row, i) => (i === idx ? { ...row, op: v } : row)),
                        );
                    }}
                ></platform-field>
                ${this._renderFilterValueField(field, value, (nextValue) => {
                    this._setPlatformEventFilters(
                        filters.map((row, i) => (i === idx ? { ...row, value: nextValue } : row)),
                    );
                })}
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    danger
                    title=${this.t('trigger_editor_modal.mapping_remove_title')}
                    @click=${() => {
                        this._setPlatformEventFilters(filters.filter((_, i) => i !== idx));
                    }}
                >
                    <platform-icon name="trash" size="16"></platform-icon>
                </platform-button>
            </div>
        `;
    }

    /**
     * @param {ReturnType<FlowsTriggerEditorModal['_normalizeFilterField']>} field
     * @param {unknown} value
     * @param {(v: unknown) => void} onChange
     */
    _renderFilterValueField(field, value, onChange) {
        if (field.value_kind === 'enum') {
            const values = field.enum_values;
            if (values === null) {
                throw new TypeError('flows-trigger-editor-modal: enum value field without enum_values');
            }
            return html`
                <platform-field
                    type="enum"
                    mode="edit"
                    .value=${typeof value === 'string' ? value : values[0]}
                    .config=${{ values: values.map((v) => ({ value: v, label: v })) }}
                    @change=${(e) => {
                        const v = e.detail.value;
                        if (typeof v !== 'string') {
                            throw new TypeError('flows-trigger-editor-modal: enum filter value expects string');
                        }
                        onChange(v);
                    }}
                ></platform-field>
            `;
        }
        if (field.value_kind === 'boolean') {
            return html`
                <platform-field
                    type="boolean"
                    mode="edit"
                    .value=${typeof value === 'boolean' ? value : false}
                    @change=${(e) => {
                        const v = e.detail.value;
                        if (typeof v !== 'boolean') {
                            throw new TypeError('flows-trigger-editor-modal: boolean filter value expects boolean');
                        }
                        onChange(v);
                    }}
                ></platform-field>
            `;
        }
        if (field.value_kind === 'integer' || field.value_kind === 'number') {
            return html`
                <platform-field
                    type=${field.value_kind === 'integer' ? 'integer' : 'number'}
                    mode="edit"
                    .value=${typeof value === 'number' ? value : 0}
                    @change=${(e) => {
                        const v = e.detail.value;
                        if (typeof v !== 'number') {
                            throw new TypeError('flows-trigger-editor-modal: number filter value expects number');
                        }
                        onChange(v);
                    }}
                ></platform-field>
            `;
        }
        return html`
            <platform-field
                type="string"
                mode="edit"
                .value=${typeof value === 'string' ? value : ''}
                placeholder=${this.t('trigger_editor_modal.event_filter_value_placeholder')}
                @change=${(e) => {
                    const v = e.detail.value;
                    if (typeof v !== 'string') {
                        throw new TypeError('flows-trigger-editor-modal: string filter value expects string');
                    }
                    onChange(v);
                }}
            ></platform-field>
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
                    <platform-button variant="ghost" density="compact" @click=${this._addMapping}>
                        + ${this.t('trigger_editor_modal.mapping_add')}
                    </platform-button>
                </div>

                ${this._outputMapping.length === 0
                    ? html`<div class="mapping-empty">${this.t('trigger_editor_modal.mapping_empty')}</div>`
                    : this._outputMapping.map((m, idx) => html`
                        <div class="mapping-row">
                            <platform-field
                                type="string"
                                mode="edit"
                                .value=${m.state}
                                placeholder=${this.t('trigger_editor_modal.mapping_placeholder_state')}
                                @change=${(e) => {
                                    const v = e.detail.value;
                                    if (typeof v !== 'string') {
                                        throw new TypeError('flows-trigger-editor-modal: mapping state expects string detail.value');
                                    }
                                    this._updateMapping(idx, 'state', v);
                                }}
                            ></platform-field>
                            <span class="mapping-arrow">→</span>
                            <platform-field
                                type="string"
                                mode="edit"
                                .value=${m.payload}
                                placeholder=${this.t('trigger_editor_modal.mapping_placeholder_payload')}
                                @change=${(e) => {
                                    const v = e.detail.value;
                                    if (typeof v !== 'string') {
                                        throw new TypeError('flows-trigger-editor-modal: mapping payload expects string detail.value');
                                    }
                                    this._updateMapping(idx, 'payload', v);
                                }}
                            ></platform-field>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="dense"
                                danger
                                title=${this.t('trigger_editor_modal.mapping_remove_title')}
                                @click=${() => this._removeMapping(idx)}
                            >
                                <platform-icon name="trash" size="16"></platform-icon>
                            </platform-button>
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
                ${this._renderSamplePayloadPanel()}
            </div>
        `;
    }

    _renderSamplePayloadPanel() {
        if (!this._type || !TRIGGER_SAMPLE_PAYLOADS[this._type]) {
            return nothing;
        }
        const sample = TRIGGER_SAMPLE_PAYLOADS[this._type];
        const sampleJson = formatJsonPretty(sample);
        const docsUrl = TRIGGER_SAMPLE_DOCS[this._type] || '';
        const docsKey = this._type === 'telegram'
            ? 'sample_docs_link'
            : this._type === 'webhook'
                ? 'sample_docs_link_webhook'
                : this._type === 'platform_event'
                    ? 'sample_docs_link_platform_event'
                    : 'sample_docs_link';
        const canTest = Boolean(this.trigger)
            && typeof this.flowId === 'string'
            && this.flowId.length > 0
            && asString(this._triggerId).length > 0;
        return html`
            <div class="field sample-payload-block">
                <label>${this.t('trigger_editor_modal.sample_payload_title')}</label>
                <p class="hint">${this.t('trigger_editor_modal.sample_payload_hint')}</p>
                ${this._renderHowToFire()}
                <pre class="sample-json">${sampleJson}</pre>
                <div class="dx-toolbar">
                    <platform-button
                        variant="ghost"
                        density="compact"
                        @click=${() => this._copyText(
                            sampleJson,
                            'flows:trigger_editor_modal.toast_sample_copied',
                            'flows:trigger_editor_modal.toast_sample_copy_failed',
                        )}
                    >
                        ${this.t('trigger_editor_modal.copy_sample')}
                    </platform-button>
                    <platform-button
                        variant="ghost"
                        density="compact"
                        ?disabled=${!canTest}
                        title=${canTest
                            ? this.t('trigger_editor_modal.run_sample_test')
                            : this.t('trigger_editor_modal.run_sample_test_disabled')}
                        @click=${() => this._onRunSampleTest()}
                    >
                        ${this.t('trigger_editor_modal.run_sample_test')}
                    </platform-button>
                </div>
                ${!canTest
                    ? html`<p class="hint">${this.t('trigger_editor_modal.run_sample_test_disabled')}</p>`
                    : nothing}
                ${this._mappingTestResultText
                    ? html`
                        <label>${this.t('trigger_editor_modal.sample_test_result')}</label>
                        <pre class="sample-json">${this._mappingTestResultText}</pre>
                    `
                    : nothing}
                ${docsUrl
                    ? html`<p class="sample-docs">
                        <a href=${docsUrl} target="_blank" rel="noopener noreferrer">
                            ${this.t(`trigger_editor_modal.${docsKey}`)}
                        </a>
                    </p>`
                    : nothing}
            </div>
        `;
    }

    _renderHowToFire() {
        if (this._type === 'email') {
            return html`<p class="hint">${this.t('trigger_editor_modal.howto_email')}</p>`;
        }
        if (this._type === 'platform_event') {
            return html`<p class="hint">${this.t('trigger_editor_modal.howto_platform_event')}</p>`;
        }
        if (this._type === 'cron') {
            return html`<p class="hint">${this.t('trigger_editor_modal.howto_cron')}</p>`;
        }
        return nothing;
    }

    async _onRunSampleTest() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            throw new Error('flows-trigger-editor-modal: flowId required for sample test');
        }
        const triggerId = asString(this._triggerId);
        if (triggerId.length === 0 || !this.trigger) {
            this._mappingTestResultText = '';
            this.toast('flows:trigger_editor_modal.run_sample_test_disabled', { type: 'error' });
            this.requestUpdate();
            return;
        }
        if (!this._type || !TRIGGER_SAMPLE_PAYLOADS[this._type]) {
            throw new Error('flows-trigger-editor-modal: sample payload missing for type');
        }
        const body = TRIGGER_SAMPLE_PAYLOADS[this._type];
        if (body === null || typeof body !== 'object' || Array.isArray(body)) {
            throw new Error('flows-trigger-editor-modal: sample payload must be a JSON object');
        }
        await this._testOp.run({
            flow_id: this.flowId,
            trigger_id: triggerId,
            payload: body,
        });
        const lr = this._testOp.lastResult;
        this._mappingTestResultText = lr === null || lr === undefined
            ? (this._testOp.error || this.t('trigger_editor_modal.verify_error_network'))
            : formatJsonPretty(lr);
        this.requestUpdate();
    }

    _renderMappingExamples() {
        const examples = this._type ? MAPPING_EXAMPLES[this._type] : null;
        if (!examples || examples.length === 0) {
            return html`<p class="config-intro">${this.t('trigger_editor_modal.examples_select_type')}</p>`;
        }
        return html`
            <p class="examples-click-hint">${this.t('trigger_editor_modal.examples_click_hint')}</p>
            <div class="dx-toolbar">
                <platform-button
                    variant="primary"
                    density="compact"
                    @click=${() => this._applyAllMappingExamples()}
                >
                    ${this.t('trigger_editor_modal.apply_all_examples')}
                </platform-button>
            </div>
            <div class="examples-list">
                ${examples.map((ex) => html`
                    <article
                        role="button"
                        tabindex="0"
                        class="examples-row"
                        title=${this.t('trigger_editor_modal.examples_click_title')}
                        @click=${() => this._addMappingFromExample(ex)}
                        @keydown=${(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                this._addMappingFromExample(ex);
                            }
                        }}
                    >
                        <code>${ex.state} → ${ex.payload}</code>
                        <span class="desc">— ${this.t(`trigger_editor_modal.${ex.descKey}`)}</span>
                    </article>
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
            && (this._type === 'email' || this._type === 'webhook');
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
                <platform-button variant="ghost" density="compact" @click=${() => { this._outputTelegramExpanded = true; this.isDirty = true; }}>
                    ${this.t('trigger_editor_modal.output_telegram_customize')}
                </platform-button>
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
            ${this._type === 'webhook'
                ? html`
                    <platform-button
                        variant="ghost"
                        density="compact"
                        @click=${() => this._applyWebhookCallbackPreset()}
                    >
                        ${this.t('trigger_editor_modal.output_webhook_callback_preset')}
                    </platform-button>
                `
                : nothing}
            ${this._outputActions.map((action, idx) => this._renderOutputAction(action, idx))}

            <platform-button variant="ghost" density="compact" @click=${this._addOutputAction}>
                <platform-icon name="plus" size="16"></platform-icon>
                ${this.t('trigger_editor_modal.output_add')}
            </platform-button>
        `;
    }

    _renderOutputAction(action, idx) {
        const channelOptions = outputChannelTypesForTrigger(this._type);
        const allowedIds = new Set(channelOptions.map((c) => c.id));
        const showLegacyChannel = !allowedIds.has(action.channel);
        const mappingEntries = Object.entries(action.mapping);
        const channelEnumValues = [];
        if (showLegacyChannel) {
            channelEnumValues.push({
                value: action.channel,
                label: `${action.channel} (${this.t('trigger_editor_modal.output_channel_legacy')})`,
            });
        }
        for (const ch of channelOptions) {
            channelEnumValues.push({
                value: ch.id,
                label: this.t(`trigger_editor_modal.${ch.labelKey}`),
            });
        }
        const channelEnumConfig = { values: channelEnumValues };
        const actionEnumConfig = {
            values: OUTPUT_ACTIONS.map((a) => ({
                value: a.id,
                label: this.t(`trigger_editor_modal.${a.labelKey}`),
            })),
        };
        return html`
            <div class="output-action-item">
                <div class="output-action-content">
                    <div class="output-action-header">
                        <platform-field
                            type="enum"
                            mode="edit"
                            .value=${action.channel}
                            .config=${channelEnumConfig}
                            @change=${(e) => {
                                const v = e.detail.value;
                                if (typeof v !== 'string') {
                                    throw new TypeError('flows-trigger-editor-modal: output channel expects string detail.value');
                                }
                                this._updateOutputAction(idx, 'channel', v);
                            }}
                        ></platform-field>
                        <platform-field
                            type="enum"
                            mode="edit"
                            .value=${action.action}
                            .config=${actionEnumConfig}
                            @change=${(e) => {
                                const v = e.detail.value;
                                if (typeof v !== 'string') {
                                    throw new TypeError('flows-trigger-editor-modal: output action expects string detail.value');
                                }
                                this._updateOutputAction(idx, 'action', v);
                            }}
                        ></platform-field>
                    </div>

                    <div class="field">
                        <label>${this.t('trigger_editor_modal.output_mapping_label')}</label>
                        ${mappingEntries.length === 0
                            ? html`<div class="mapping-empty">${this.t('trigger_editor_modal.mapping_empty')}</div>`
                            : mappingEntries.map(([key, value]) => html`
                                <div class="mapping-row">
                                    <platform-field
                                        type="string"
                                        mode="edit"
                                        .value=${key}
                                        placeholder=${this.t('trigger_editor_modal.output_mapping_param_placeholder')}
                                        @change=${(e) => {
                                            const v = e.detail.value;
                                            if (typeof v !== 'string') {
                                                throw new TypeError('flows-trigger-editor-modal: output mapping key expects string detail.value');
                                            }
                                            this._renameOutputMappingKey(idx, key, v);
                                        }}
                                    ></platform-field>
                                    <span class="mapping-arrow">→</span>
                                    <platform-field
                                        type="string"
                                        mode="edit"
                                        .value=${value}
                                        placeholder=${this.t('trigger_editor_modal.output_mapping_value_placeholder')}
                                        @change=${(e) => {
                                            const v = e.detail.value;
                                            if (typeof v !== 'string') {
                                                throw new TypeError('flows-trigger-editor-modal: output mapping value expects string detail.value');
                                            }
                                            this._setOutputMappingValue(idx, key, v);
                                        }}
                                    ></platform-field>
                                    <platform-button
                                        variant="ghost"
                                        icon-only
                                        density="dense"
                                        danger
                                        title=${this.t('trigger_editor_modal.mapping_remove_title')}
                                        @click=${() => this._removeOutputMappingKey(idx, key)}
                                    >
                                        <platform-icon name="trash" size="16"></platform-icon>
                                    </platform-button>
                                </div>
                            `)}
                        <platform-button variant="ghost" density="compact" @click=${() => this._addOutputMappingKey(idx)}>
                            + ${this.t('trigger_editor_modal.output_mapping_add')}
                        </platform-button>
                    </div>

                    <div class="field">
                        <label>${this.t('trigger_editor_modal.output_condition_label')}</label>
                        <platform-field
                            type="string"
                            mode="edit"
                            .value=${action.condition}
                            placeholder=${this.t('trigger_editor_modal.output_condition_placeholder')}
                            @change=${(e) => {
                                const v = e.detail.value;
                                if (typeof v !== 'string') {
                                    throw new TypeError('flows-trigger-editor-modal: output condition expects string detail.value');
                                }
                                this._updateOutputAction(idx, 'condition', v);
                            }}
                        ></platform-field>
                        <span class="hint">${this.t('trigger_editor_modal.output_condition_hint')}</span>
                    </div>
                </div>
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    danger
                    title=${this.t('trigger_editor_modal.output_action_remove_title')}
                    @click=${() => this._removeOutputAction(idx)}
                >
                    <platform-icon name="trash" size="16"></platform-icon>
                </platform-button>
            </div>
        `;
    }

    renderFooter() {
        const busy = this._createOp.busy || this._updateOp.busy;
        const saveLabel = this.trigger
            ? this.t('trigger_editor_modal.action_save')
            : this.t('trigger_editor_modal.action_create');
        return html`
            <platform-button ?disabled=${busy} @click=${() => this.close()}>${this.t('common.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${busy} @click=${() => this._performSave()}>
                ${busy ? this.t('editor_header.saving') : saveLabel}
            </platform-button>
        `;
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
        if (typeId === 'cron' || typeId === 'platform_event') {
            this._postFlowOutputEnabled = false;
            if (this._activeTab === 'output') {
                this._activeTab = 'config';
            }
        } else if (this._postFlowOutputEnabled && typeId === 'telegram' && this._outputActions.length === 0) {
            if (this._triggerId.trim().length > 0) {
                this._outputActions = [defaultTelegramOutputAction(this._triggerId)];
            }
        }
        if (typeId === 'email') {
            this._config = this._normalizeEmailConfig(this._config);
            this._ensureMailLoaded();
            this._maybeAutofillMailboxBinding();
            this._maybeApplyEmailMappingDefaults();
        }
        if (typeId === 'webhook') {
            this._config = this._normalizeWebhookConfig(this._config);
        }
        this.isDirty = true;
    }

    _normalizeWebhookConfig(config) {
        const next = isPlainObject(config) ? { ...config } : {};
        const header = asString(next.secret_header).trim();
        next.secret_header = header.length > 0 ? header : DEFAULT_WEBHOOK_SECRET_HEADER;
        if (!Array.isArray(next.allowed_ips)) {
            next.allowed_ips = [];
        } else {
            next.allowed_ips = next.allowed_ips.filter((item) => typeof item === 'string');
        }
        if (typeof next.secret_token !== 'string') {
            next.secret_token = asString(next.secret_token);
        }
        return next;
    }

    _copyText(text, successKey, errorKey) {
        this.copyToClipboard(String(text), {
            success_i18n_key: successKey,
            error_i18n_key: errorKey,
        });
    }

    _applyAllMappingExamples() {
        const examples = this._type ? MAPPING_EXAMPLES[this._type] : null;
        if (!examples || examples.length === 0) {
            return;
        }
        const byState = new Map(
            this._outputMapping
                .filter((m) => asString(m.state).trim().length > 0)
                .map((m) => [asString(m.state).trim(), m]),
        );
        for (const ex of examples) {
            byState.set(ex.state, { state: ex.state, payload: ex.payload });
        }
        this._outputMapping = [...byState.values()];
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

    _addMappingFromExample(ex) {
        if (!isPlainObject(ex)) {
            throw new TypeError('flows-trigger-editor-modal: mapping example must be an object');
        }
        const state = asString(ex.state);
        const payload = asString(ex.payload);
        if (!state || !payload) {
            throw new TypeError('flows-trigger-editor-modal: mapping example requires state and payload');
        }
        const emptyIdx = this._outputMapping.findIndex(
            (m) => asString(m.state).trim().length === 0 && asString(m.payload).trim().length === 0,
        );
        if (emptyIdx >= 0) {
            this._outputMapping = this._outputMapping.map((m, i) => (
                i === emptyIdx ? { state, payload } : m
            ));
        } else {
            this._outputMapping = [...this._outputMapping, { state, payload }];
        }
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
                : this._type === 'webhook' && defaultChannel === 'webhook'
                    ? defaultWebhookCallbackOutputAction('')
                    : { channel: defaultChannel, action: 'send_message', mapping: {}, config: {}, condition: '' };
        this._outputActions = [...this._outputActions, next];
        this._outputTelegramExpanded = true;
        this.isDirty = true;
    }

    _applyWebhookCallbackPreset() {
        this._postFlowOutputEnabled = true;
        this._outputActions = [defaultWebhookCallbackOutputAction('https://example.com/callback')];
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
        if (this._type === 'email') {
            const mailboxId = this._config.mailbox_binding_id;
            if (typeof mailboxId !== 'string' || mailboxId.trim().length === 0) {
                return { config: this.t('trigger_editor_modal.error_mailbox_required') };
            }
        }
        if (this._type === 'platform_event') {
            const eventType = this._config.event_type;
            if (typeof eventType !== 'string' || eventType.trim().length === 0) {
                return { config: this.t('trigger_editor_modal.error_event_type_required') };
            }
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
            config: this._type === 'email'
                ? this._normalizeEmailConfig(this._config)
                : (this._type === 'webhook' ? this._normalizeWebhookConfig(this._config) : this._config),
            output_mapping: outputMapping,
            output_actions: outputActions,
            post_flow_output_enabled: postFlow,
            branch_id: this._branchId.trim(),
        };

        if (this.trigger) {
            await this._updateOp.run({
                flow_id: this.flowId,
                trigger_id: this._triggerId.trim(),
                name: body.name,
                enabled: body.enabled,
                config: body.config,
                output_mapping: body.output_mapping,
                output_actions: body.output_actions,
                post_flow_output_enabled: body.post_flow_output_enabled,
                branch_id: body.branch_id,
            });
        } else {
            await this._createOp.run({ flow_id: this.flowId, ...body });
        }
        await this._listOp.run({ flow_id: this.flowId });
        this.closeAfterSave();
    }
}

customElements.define('flows-trigger-editor-modal', FlowsTriggerEditorModal);
registerModalKind(FlowsTriggerEditorModal.modalKind, 'flows-trigger-editor-modal');
