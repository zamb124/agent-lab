/**
 * flows-channel-node-editor — редактор channel-ноды.
 *
 * Поля по `ChannelNodeConfig` + `ChannelType`:
 *   - channel: 'telegram' | 'email' | 'sms' | 'webhook'
 *   - action: enum по каналу
 *   - channel_config: per-channel конфиг
 *   - Сообщение: facade над input_mapping (recipient / subject / text|caption)
 *     через platform-variable-input + platform-markdown-editor (enableVariables)
 *
 * Email (platform mail | SMTP):
 *   - channel_config.delivery = mailbox|smtp
 *   - Кому/Тема/Тело — input_mapping.recipient|subject|text
 *
 * SMS (HTTP-супербаза, канон External API):
 *   - пресеты → url/method/headers/body_template
 *   - в JSON: @state: / @var:; {key} из input_mapping
 *   - Method — platform-segmented-control как у external_api
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-picker-card.js';
import '@platform/lib/components/platform-segmented-control.js';
import './flows-base-node-editor.js';
import '@platform/lib/components/platform-variable-input.js';
import '@platform/lib/components/platform-markdown-editor.js';
import '@platform/lib/components/platform-json-editor.js';
import '../editors/flows-http-headers-editor.js';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { buildPromptVariableContext } from '../../_helpers/prompt-variable-catalog.js';
import {
    buildExecutionStatePreview,
    collectStatePathsFromDataflow,
} from '@platform/lib/variables/variable-refs.js';
import {
    getSmsPreset,
    listSmsPresets,
    smsConfigMatchesPresetSkeleton,
} from '../../_helpers/flows-sms-presets.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { MAIL_EVENTS } from '@platform/lib/events/reducers/mail.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';

const CHANNELS = Object.freeze(['telegram', 'email', 'sms', 'webhook']);
const PARSE_MODES = Object.freeze(['', 'HTML', 'MarkdownV2']);
const HTTP_METHODS = Object.freeze(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);
/** @type {Readonly<Record<string, string>>} */
const HTTP_METHOD_TONES = Object.freeze({
    GET: 'success',
    POST: 'accent-secondary',
    PUT: 'warning',
    PATCH: 'accent-tertiary',
    DELETE: 'error',
});

/** Базовые actions Telegram / generic. */
const BASE_ACTIONS = Object.freeze(['send_message', 'send_photo', 'send_document']);
/** Email / SMS: только send_message. */
const EMAIL_ACTIONS = Object.freeze(['send_message']);
const SMS_ACTIONS = Object.freeze(['send_message']);
/** Webhook: base + send_payload / send_notification. */
const WEBHOOK_ACTIONS = Object.freeze([
    ...BASE_ACTIONS,
    'send_payload',
    'send_notification',
]);

/**
 * @param {string} channel
 * @returns {readonly string[]}
 */
function actionsForChannel(channel) {
    if (channel === 'webhook') {
        return WEBHOOK_ACTIONS;
    }
    if (channel === 'email') {
        return EMAIL_ACTIONS;
    }
    if (channel === 'sms') {
        return SMS_ACTIONS;
    }
    return BASE_ACTIONS;
}

/**
 * @param {string} channel
 * @param {string} action
 * @returns {string}
 */
function resolveAction(channel, action) {
    const allowed = actionsForChannel(channel);
    if (allowed.includes(action)) {
        return action;
    }
    return 'send_message';
}

export class FlowsChannelNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        embedded: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .field { display: flex; flex-direction: column; gap: var(--space-2); margin-bottom: var(--space-2); }
            details {
                margin-top: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
            .grid {
                display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2);
            }
            /* Явный stack: у <details> non-summary дети схлопываются в anonymous box — gap между pills теряется. */
            .channel-stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                min-width: 0;
            }
            .channel-stack > * {
                margin: 0;
            }
            .email-cta {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            .email-cta-text {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .email-mail-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
            }
            .section-title {
                margin: 0;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            .message-body-editor {
                display: block;
                min-width: 0;
            }
            .message-body-editor platform-markdown-editor {
                display: block;
                min-height: 160px;
            }
            .sms-presets {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                gap: var(--space-3);
            }
            .sms-presets platform-picker-card {
                min-width: 0;
                --platform-picker-card-padding: var(--space-3);
            }
            .sms-provider-icon {
                width: 28px;
                height: 28px;
                object-fit: contain;
                display: block;
            }
            .method-toggle {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }
            .method-toggle platform-segmented-control {
                width: 100%;
            }
            .field-hint {
                margin: 0;
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'channel';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
        this._mailSelect = this.select((s) => s.mail);
        this.useEvent(MAIL_EVENTS.BINDINGS_LOADED, () => {
            this._maybeAutofillMailboxBinding();
            this.requestUpdate();
        });
        this.useEvent(MAIL_EVENTS.CONNECTION_LOADED, () => this.requestUpdate());
        this.useEvent(MAIL_EVENTS.BINDING_CREATED, () => {
            this._maybeAutofillMailboxBinding();
            this.requestUpdate();
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadMailState();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('nodeConfig')) {
            const channel = this.nodeConfig?.channel;
            if (channel === 'email') {
                this._maybeAutofillMailboxBinding();
            }
        }
    }

    _loadMailState() {
        this.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null);
        this.dispatch(MAIL_EVENTS.CONNECTION_LOAD_REQUESTED, null);
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _inputMapping() {
        const raw = this.nodeConfig?.input_mapping;
        return isPlainObject(raw) ? { ...raw } : {};
    }

    _onInputMappingField(field, value) {
        if (typeof field !== 'string' || field.length === 0) {
            throw new Error('flows-channel-node-editor: input_mapping field required');
        }
        if (typeof value !== 'string') {
            throw new Error(`flows-channel-node-editor: input_mapping.${field} must be string`);
        }
        const next = this._inputMapping();
        next[field] = value;
        this._emitPatch({ input_mapping: next });
    }

    _onChannel(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: channel change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: channel detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-channel-node-editor: channel string required');
        }
        if (!CHANNELS.includes(v)) {
            return;
        }
        const currentAction = typeof this.nodeConfig?.action === 'string'
            ? this.nodeConfig.action
            : 'send_message';
        const nextAction = resolveAction(v, currentAction);
        const patch = { channel: v, channel_config: {} };
        if (nextAction !== currentAction) {
            patch.action = nextAction;
        }
        if (v === 'email') {
            const mapping = this._inputMapping();
            let mappingChanged = false;
            if (!Object.prototype.hasOwnProperty.call(mapping, 'subject')) {
                mapping.subject = '';
                mappingChanged = true;
            }
            if (mappingChanged) {
                patch.input_mapping = mapping;
            }
            const mail = this._mailSelect.value;
            const bindings = Array.isArray(mail?.bindings) ? mail.bindings : [];
            if (bindings.length > 0) {
                const preferred = bindings.find((b) => b.is_default === true) || bindings[0];
                patch.channel_config = {
                    delivery: 'mailbox',
                    mailbox_binding_id: preferred.mailbox_binding_id,
                };
            } else {
                patch.channel_config = {
                    delivery: 'smtp',
                    smtp_port: 587,
                    smtp_use_tls: true,
                };
            }
            this._emitPatch(patch);
            this._loadMailState();
            return;
        }
        if (v === 'sms') {
            patch.channel_config = { ...getSmsPreset('custom').channel_config };
            if (nextAction !== 'send_message') {
                patch.action = 'send_message';
            }
        }
        this._emitPatch(patch);
    }

    _onAction(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: action change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: action detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-channel-node-editor: action string required');
        }
        const channel = CHANNELS.includes(this.nodeConfig?.channel)
            ? this.nodeConfig.channel
            : 'telegram';
        if (!actionsForChannel(channel).includes(v)) {
            return;
        }
        this._emitPatch({ action: v });
    }

    _actionEnumValues(channel) {
        return actionsForChannel(channel).map((actionId) => ({
            value: actionId,
            label: this.t(`channel_node_editor.action_${actionId}`),
        }));
    }

    _onChannelConfig(field, value) {
        const current = this.nodeConfig?.channel_config && typeof this.nodeConfig.channel_config === 'object'
            ? this.nodeConfig.channel_config
            : {};
        const next = { ...current, [field]: value };
        this._emitPatch({ channel_config: next });
    }

    _onChannelConfigParseMode(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: parse_mode change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: parse_mode detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-channel-node-editor: parse_mode string required');
        }
        this._onChannelConfig('parse_mode', v.length > 0 ? v : null);
    }

    _onChannelConfigWebhookMethod(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: webhook method change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: webhook method detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-channel-node-editor: webhook method string required');
        }
        this._onChannelConfig('method', v);
    }

    _onSmsMethod(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: sms method change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: sms method detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string' || !HTTP_METHODS.includes(v)) {
            throw new Error(`flows-channel-node-editor: unsupported SMS HTTP method "${String(v)}"`);
        }
        this._onChannelConfig('method', v);
    }

    _onChannelConfigWebhookUrl(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: webhook url change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: webhook url detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-channel-node-editor: webhook url string required');
        }
        this._onChannelConfig('url', v);
    }

    _onSmsBodyTemplateChange(e) {
        if (!e.detail || !('parsed' in e.detail)) {
            return;
        }
        const parsed = e.detail.parsed;
        if (!isPlainObject(parsed)) {
            throw new Error('flows-channel-node-editor: sms body_template must be a JSON object');
        }
        this._onChannelConfig('body_template', JSON.stringify(parsed, null, 2));
    }

    async _onApplySmsPreset(presetId) {
        if (typeof presetId !== 'string' || presetId.length === 0) {
            throw new Error('flows-channel-node-editor: sms preset_id required');
        }
        const preset = getSmsPreset(presetId);
        const current = this.nodeConfig?.channel_config && typeof this.nodeConfig.channel_config === 'object'
            ? this.nodeConfig.channel_config
            : {};
        const currentPresetId = typeof current.preset_id === 'string' ? current.preset_id : '';
        if (Object.keys(current).length > 0) {
            let matchesCurrentSkeleton = false;
            if (currentPresetId.length > 0) {
                try {
                    matchesCurrentSkeleton = smsConfigMatchesPresetSkeleton(
                        current,
                        getSmsPreset(currentPresetId).channel_config,
                    );
                } catch {
                    matchesCurrentSkeleton = false;
                }
            }
            if (!matchesCurrentSkeleton && currentPresetId !== presetId) {
                const confirmed = await platformConfirm(this.t('channel_node_editor.sms_preset_confirm'));
                if (!confirmed) {
                    return;
                }
            }
        }
        this._emitPatch({ channel_config: { ...preset.channel_config } });
    }

    _onMailboxBindingChange(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: mailbox_binding_id change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: mailbox_binding_id detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-channel-node-editor: mailbox_binding_id string required');
        }
        this._emitPatch({
            channel_config: {
                delivery: 'mailbox',
                mailbox_binding_id: v,
            },
        });
    }

    _onDeliveryChange(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: delivery change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: delivery detail.value');
        }
        const v = d.value;
        if (v !== 'mailbox' && v !== 'smtp') {
            throw new Error('flows-channel-node-editor: delivery must be mailbox|smtp');
        }
        if (v === 'mailbox') {
            const mail = this._mailSelect.value;
            const bindings = Array.isArray(mail?.bindings) ? mail.bindings : [];
            const preferred = bindings.find((b) => b.is_default === true) || bindings[0];
            const next = { delivery: 'mailbox' };
            if (preferred && typeof preferred.mailbox_binding_id === 'string') {
                next.mailbox_binding_id = preferred.mailbox_binding_id;
            }
            this._emitPatch({ channel_config: next });
            return;
        }
        this._emitPatch({
            channel_config: {
                delivery: 'smtp',
                smtp_port: 587,
                smtp_use_tls: true,
            },
        });
    }

    _onSmtpUseTlsChange(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: smtp_use_tls change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: smtp_use_tls detail.value');
        }
        const v = d.value;
        if (v !== 'true' && v !== 'false') {
            throw new Error('flows-channel-node-editor: smtp_use_tls must be true|false string');
        }
        const current = isPlainObject(this.nodeConfig?.channel_config)
            ? { ...this.nodeConfig.channel_config }
            : { delivery: 'smtp' };
        current.delivery = 'smtp';
        current.smtp_use_tls = v === 'true';
        delete current.mailbox_binding_id;
        this._emitPatch({ channel_config: current });
    }

    _onSmtpField(field, value) {
        if (typeof field !== 'string' || field.length === 0) {
            throw new Error('flows-channel-node-editor: smtp field required');
        }
        const current = isPlainObject(this.nodeConfig?.channel_config)
            ? { ...this.nodeConfig.channel_config }
            : {};
        current.delivery = 'smtp';
        delete current.mailbox_binding_id;
        if (field === 'smtp_port') {
            if (typeof value !== 'string' && typeof value !== 'number') {
                throw new Error('flows-channel-node-editor: smtp_port type');
            }
            const asNum = typeof value === 'number' ? value : Number(String(value).trim());
            if (!Number.isInteger(asNum) || asNum <= 0 || asNum > 65535) {
                throw new Error('flows-channel-node-editor: smtp_port invalid');
            }
            current.smtp_port = asNum;
        } else {
            if (typeof value !== 'string') {
                throw new Error(`flows-channel-node-editor: ${field} must be string`);
            }
            current[field] = value;
        }
        this._emitPatch({ channel_config: current });
    }

    /**
     * @param {Record<string, unknown>} cfg
     * @returns {'mailbox'|'smtp'}
     */
    _resolveDelivery(cfg) {
        if (cfg.delivery === 'smtp') {
            return 'smtp';
        }
        if (cfg.delivery === 'mailbox') {
            return 'mailbox';
        }
        if (typeof cfg.smtp_host === 'string' && cfg.smtp_host.length > 0) {
            return 'smtp';
        }
        return 'mailbox';
    }

    _maybeAutofillMailboxBinding() {
        if (this.nodeConfig?.channel !== 'email') {
            return;
        }
        const cfg = isPlainObject(this.nodeConfig?.channel_config)
            ? this.nodeConfig.channel_config
            : {};
        const delivery = this._resolveDelivery(cfg);
        if (delivery !== 'mailbox') {
            return;
        }
        const mail = this._mailSelect.value;
        const bindings = Array.isArray(mail?.bindings) ? mail.bindings : [];
        if (bindings.length === 0) {
            if (cfg.delivery !== 'mailbox' && cfg.delivery !== 'smtp') {
                this._emitPatch({
                    channel_config: {
                        delivery: 'smtp',
                        smtp_port: 587,
                        smtp_use_tls: true,
                    },
                });
            }
            return;
        }
        const patch = { delivery: 'mailbox' };
        const current = typeof cfg.mailbox_binding_id === 'string' ? cfg.mailbox_binding_id : '';
        if (current.length > 0 && bindings.some((b) => b.mailbox_binding_id === current)) {
            if (cfg.delivery !== 'mailbox') {
                this._emitPatch({
                    channel_config: {
                        delivery: 'mailbox',
                        mailbox_binding_id: current,
                    },
                });
            }
            return;
        }
        const preferred = bindings.find((b) => b.is_default === true);
        const next = preferred || bindings[0];
        if (!next || typeof next.mailbox_binding_id !== 'string') {
            return;
        }
        patch.mailbox_binding_id = next.mailbox_binding_id;
        this._emitPatch({ channel_config: patch });
    }

    _openMailSettings() {
        this.openModal('platform.mail', { openSettings: true });
    }

    _variableContext() {
        return buildPromptVariableContext({
            flowVariables: this.flowVariables,
            nodeLocalVariables: this.nodeConfig?.local_variables,
            dataflowNode: this.dataflowNode,
            previewExecutionState: this.previewExecutionState,
        });
    }

    _onMessageBodyChange(field, e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-channel-node-editor: message body change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-channel-node-editor: message body detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-channel-node-editor: message body string required');
        }
        this._onInputMappingField(field, v);
    }

    /**
     * Facade над input_mapping: Кому + (Тема) + тело/caption в markdown-editor.
     * @param {{ includeSubject?: boolean, bodyField?: 'text'|'caption', recipientPlaceholderKey?: string }} opts
     */
    _renderMessageSection(opts = {}) {
        const includeSubject = opts.includeSubject === true;
        const bodyField = opts.bodyField === 'caption' ? 'caption' : 'text';
        const recipientPlaceholderKey = typeof opts.recipientPlaceholderKey === 'string'
            ? opts.recipientPlaceholderKey
            : 'channel_node_editor.message_to_placeholder';
        const mapping = this._inputMapping();
        const recipient = typeof mapping.recipient === 'string' ? mapping.recipient : '';
        const subject = typeof mapping.subject === 'string' ? mapping.subject : '';
        const body = typeof mapping[bodyField] === 'string' ? mapping[bodyField] : '';
        const variableContext = this._variableContext();
        const statePreview = buildExecutionStatePreview(this.previewExecutionState);
        const statePaths = collectStatePathsFromDataflow(this.dataflowNode);
        const bodyLabel = bodyField === 'caption'
            ? this.t('channel_node_editor.message_caption')
            : this.t('channel_node_editor.message_body');
        return html`
            <p class="section-title">${this.t('channel_node_editor.message_section')}</p>
            <platform-variable-input
                data-field="recipient"
                .label=${this.t('channel_node_editor.message_to')}
                .placeholder=${this.t(recipientPlaceholderKey)}
                .value=${recipient}
                .previewValues=${variableContext.values}
                .variableCatalog=${variableContext.catalog}
                .statePreview=${statePreview}
                .statePaths=${statePaths}
                @change=${(e) => this._onInputMappingField('recipient', asString(e.detail?.value))}
            ></platform-variable-input>
            ${includeSubject
                ? html`
                    <platform-variable-input
                        data-field="subject"
                        .label=${this.t('channel_node_editor.message_subject')}
                        .placeholder=${this.t('channel_node_editor.message_subject_placeholder')}
                        .value=${subject}
                        .previewValues=${variableContext.values}
                        .variableCatalog=${variableContext.catalog}
                        .statePreview=${statePreview}
                        .statePaths=${statePaths}
                        @change=${(e) => this._onInputMappingField('subject', asString(e.detail?.value))}
                    ></platform-variable-input>
                `
                : null}
            <div class="message-body-editor">
                <platform-markdown-editor
                    compact
                    data-field=${bodyField}
                    .value=${body}
                    .enableVariables=${true}
                    .variables=${variableContext.values}
                    .variableCatalog=${variableContext.catalog}
                    .statePreview=${statePreview}
                    .statePaths=${statePaths}
                    .label=${bodyLabel}
                    .hint=${this.t('channel_node_editor.message_body_hint')}
                    .minHeight=${160}
                    @change=${(e) => this._onMessageBodyChange(bodyField, e)}
                ></platform-markdown-editor>
            </div>
        `;
    }

    _renderEmailMessageFields() {
        return this._renderMessageSection({
            includeSubject: true,
            bodyField: 'text',
            recipientPlaceholderKey: 'channel_node_editor.message_to_placeholder',
        });
    }

    _renderChannelMessageByAction(channel) {
        const action = resolveAction(
            channel,
            typeof this.nodeConfig?.action === 'string' ? this.nodeConfig.action : 'send_message',
        );
        if (action === 'send_photo' || action === 'send_document') {
            return this._renderMessageSection({
                includeSubject: false,
                bodyField: 'caption',
                recipientPlaceholderKey: channel === 'telegram'
                    ? 'channel_node_editor.telegram_recipient_placeholder'
                    : 'channel_node_editor.message_to_placeholder',
            });
        }
        if (action === 'send_message' || action === 'send_notification') {
            return this._renderMessageSection({
                includeSubject: false,
                bodyField: 'text',
                recipientPlaceholderKey: channel === 'telegram'
                    ? 'channel_node_editor.telegram_recipient_placeholder'
                    : 'channel_node_editor.message_to_placeholder',
            });
        }
        return null;
    }

    _renderEmailMailboxSection(cfg, bindings, connection) {
        const selectedId = typeof cfg.mailbox_binding_id === 'string' ? cfg.mailbox_binding_id : '';
        const noConnection = connection === null || connection === undefined;
        if (bindings.length === 0) {
            return html`
                <div class="email-cta">
                    <p class="email-cta-text">
                        ${noConnection
                            ? this.t('channel_node_editor.email_cta_no_connection')
                            : this.t('channel_node_editor.email_cta_no_mailbox')}
                    </p>
                    <div class="email-mail-actions">
                        <platform-button variant="primary" @click=${() => this._openMailSettings()}>
                            ${noConnection
                                ? this.t('channel_node_editor.email_cta_connect')
                                : this.t('channel_node_editor.email_cta_setup_mailbox')}
                        </platform-button>
                    </div>
                </div>
            `;
        }
        const mailboxEnumConfig = {
            values: bindings.map((binding) => ({
                value: binding.mailbox_binding_id,
                label: binding.is_default
                    ? `${binding.email_address} (${this.t('channel_node_editor.mailbox_default_badge')})`
                    : binding.email_address,
            })),
        };
        return html`
            <platform-field
                mode="edit"
                type="enum"
                data-field="mailbox_binding_id"
                .label=${this.t('channel_node_editor.email_mailbox')}
                .hint=${this.t('channel_node_editor.email_mailbox_hint')}
                .value=${selectedId}
                .config=${mailboxEnumConfig}
                @change=${this._onMailboxBindingChange}
            ></platform-field>
            <div class="email-mail-actions">
                <platform-button variant="ghost" density="compact" @click=${() => this._openMailSettings()}>
                    ${this.t('channel_node_editor.email_open_settings')}
                </platform-button>
            </div>
        `;
    }

    _renderEmailSmtpSection(cfg) {
        const useTls = cfg.smtp_use_tls === false ? 'false' : 'true';
        return html`
            <platform-variable-input
                data-field="smtp_host"
                .label=${this.t('channel_node_editor.smtp_host')}
                .placeholder=${this.t('channel_node_editor.smtp_host_placeholder')}
                .value=${typeof cfg.smtp_host === 'string' ? cfg.smtp_host : ''}
                @change=${(e) => this._onSmtpField('smtp_host', asString(e.detail?.value))}
            ></platform-variable-input>
            <platform-field
                mode="edit"
                type="integer"
                data-field="smtp_port"
                .label=${this.t('channel_node_editor.smtp_port')}
                .value=${typeof cfg.smtp_port === 'number' ? cfg.smtp_port : 587}
                @change=${(e) => {
                    const raw = e.detail?.value;
                    this._onSmtpField('smtp_port', raw == null ? '587' : String(raw));
                }}
            ></platform-field>
            <platform-variable-input
                data-field="from_email"
                .label=${this.t('channel_node_editor.smtp_from')}
                .placeholder=${this.t('channel_node_editor.smtp_from_placeholder')}
                .value=${typeof cfg.from_email === 'string' ? cfg.from_email : ''}
                @change=${(e) => this._onSmtpField('from_email', asString(e.detail?.value))}
            ></platform-variable-input>
            <platform-variable-input
                data-field="smtp_user"
                .label=${this.t('channel_node_editor.smtp_user')}
                .placeholder=${this.t('channel_node_editor.smtp_user_placeholder')}
                .value=${typeof cfg.smtp_user === 'string' ? cfg.smtp_user : ''}
                @change=${(e) => this._onSmtpField('smtp_user', asString(e.detail?.value))}
            ></platform-variable-input>
            <platform-variable-input
                data-field="password"
                .label=${this.t('channel_node_editor.smtp_password')}
                .placeholder=${this.t('channel_node_editor.smtp_password_placeholder')}
                .value=${typeof cfg.password === 'string' ? cfg.password : ''}
                @change=${(e) => this._onSmtpField('password', asString(e.detail?.value))}
            ></platform-variable-input>
            <platform-field
                mode="edit"
                type="enum"
                data-field="smtp_use_tls"
                .label=${this.t('channel_node_editor.smtp_use_tls')}
                .value=${useTls}
                .config=${{
                    values: [
                        { value: 'true', label: this.t('channel_node_editor.smtp_tls_yes') },
                        { value: 'false', label: this.t('channel_node_editor.smtp_tls_no') },
                    ],
                }}
                @change=${this._onSmtpUseTlsChange}
            ></platform-field>
        `;
    }

    _renderEmail(cfg) {
        const mail = this._mailSelect.value;
        const bindings = Array.isArray(mail?.bindings) ? mail.bindings : [];
        const connection = mail?.connection;
        const delivery = this._resolveDelivery(cfg);

        return html`
            <div class="channel-stack">
                <platform-field
                    mode="edit"
                    type="enum"
                    data-field="delivery"
                    .label=${this.t('channel_node_editor.delivery')}
                    .hint=${this.t('channel_node_editor.delivery_hint')}
                    .value=${delivery}
                    .config=${{
                        values: [
                            {
                                value: 'mailbox',
                                label: this.t('channel_node_editor.delivery_mailbox'),
                            },
                            {
                                value: 'smtp',
                                label: this.t('channel_node_editor.delivery_smtp'),
                            },
                        ],
                    }}
                    @change=${this._onDeliveryChange}
                ></platform-field>
                ${delivery === 'mailbox'
                    ? this._renderEmailMailboxSection(cfg, bindings, connection)
                    : this._renderEmailSmtpSection(cfg)}
                ${this._renderEmailMessageFields()}
            </div>
        `;
    }

    _renderTelegram(cfg) {
        return html`
            <div class="channel-stack">
                <platform-variable-input
                    .label=${this.t('channel_node_editor.telegram_bot_token')}
                    .value=${typeof cfg.bot_token === 'string' ? cfg.bot_token : ''}
                    @change=${(e) => this._onChannelConfig('bot_token', asString(e.detail?.value))}
                ></platform-variable-input>
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('channel_node_editor.telegram_parse_mode')}
                    .value=${typeof cfg.parse_mode === 'string' ? cfg.parse_mode : ''}
                    .config=${{
                        values: PARSE_MODES.map((m) => ({
                            value: m,
                            label: m === '' ? '—' : m,
                        })),
                    }}
                    @change=${this._onChannelConfigParseMode}
                ></platform-field>
                ${this._renderChannelMessageByAction('telegram')}
            </div>
        `;
    }

    _renderWebhook(cfg) {
        const headers =
            cfg.headers && typeof cfg.headers === 'object' && !Array.isArray(cfg.headers)
                ? cfg.headers
                : {};
        return html`
            <div class="channel-stack">
                <platform-field
                    mode="edit"
                    type="string"
                    input-type="url"
                    .label=${this.t('channel_node_editor.webhook_url')}
                    .value=${asString(cfg.url)}
                    @change=${this._onChannelConfigWebhookUrl}
                ></platform-field>
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('channel_node_editor.webhook_method')}
                    .value=${typeof cfg.method === 'string' && cfg.method.length > 0 ? cfg.method : 'POST'}
                    .config=${{
                        values: HTTP_METHODS.map((m) => ({ value: m, label: m })),
                    }}
                    @change=${this._onChannelConfigWebhookMethod}
                ></platform-field>
                <div class="field">
                    <p class="section-title">${this.t('channel_node_editor.webhook_headers')}</p>
                    <flows-http-headers-editor
                        .value=${headers}
                        @change=${(e) => {
                            const d = e.detail;
                            if (d === null || typeof d !== 'object' || !('value' in d)) {
                                throw new Error('flows-channel-node-editor: webhook headers detail.value');
                            }
                            this._onChannelConfig('headers', d.value);
                        }}
                    ></flows-http-headers-editor>
                </div>
                ${this._renderChannelMessageByAction('webhook')}
            </div>
        `;
    }

    _renderSms(cfg) {
        const selectedPresetId = typeof cfg.preset_id === 'string' ? cfg.preset_id : '';
        const headers =
            cfg.headers && typeof cfg.headers === 'object' && !Array.isArray(cfg.headers)
                ? cfg.headers
                : {};
        const bodyTemplate = typeof cfg.body_template === 'string' && cfg.body_template.length > 0
            ? cfg.body_template
            : '{}';
        const method = HTTP_METHODS.includes(cfg.method) ? cfg.method : 'POST';
        const timeout = typeof cfg.timeout === 'number' ? cfg.timeout : 30;
        const methodItems = HTTP_METHODS.map((m) => ({
            value: m,
            label: m,
            tone: HTTP_METHOD_TONES[m],
        }));
        return html`
            <div class="channel-stack">
                <p class="section-title">${this.t('channel_node_editor.sms_presets')}</p>
                <div class="sms-presets">
                    ${listSmsPresets().map((preset) => html`
                        <platform-picker-card
                            .title=${this.t(preset.labelKey)}
                            .subtitle=${this.t(preset.subtitleKey)}
                            .value=${preset.preset_id}
                            ?selected=${selectedPresetId === preset.preset_id}
                            @select=${(e) => {
                                const presetId = e.detail?.value;
                                if (typeof presetId !== 'string') {
                                    throw new TypeError('flows-channel-node-editor: sms preset value must be string');
                                }
                                this._onApplySmsPreset(presetId);
                            }}
                        >
                            <img
                                slot="icon"
                                class="sms-provider-icon"
                                src=${preset.iconSrc}
                                alt=""
                                aria-hidden="true"
                            />
                        </platform-picker-card>
                    `)}
                </div>
                <p class="section-title">${this.t('channel_node_editor.sms_http_section')}</p>
                <div class="method-toggle">
                    <span class="section-title">${this.t('channel_node_editor.sms_method')}</span>
                    <platform-segmented-control
                        full-width
                        density="dense"
                        .value=${method}
                        .items=${methodItems}
                        aria-label=${this.t('channel_node_editor.sms_method')}
                        @change=${this._onSmsMethod}
                    ></platform-segmented-control>
                </div>
                <platform-field
                    mode="edit"
                    type="string"
                    input-type="url"
                    data-field="url"
                    .label=${this.t('channel_node_editor.sms_url')}
                    .hint=${this.t('channel_node_editor.sms_url_hint')}
                    .value=${asString(cfg.url)}
                    @change=${this._onChannelConfigWebhookUrl}
                ></platform-field>
                <platform-field
                    mode="edit"
                    type="number"
                    data-field="timeout"
                    .label=${this.t('channel_node_editor.sms_timeout')}
                    .value=${timeout}
                    @change=${(e) => {
                        const raw = e.detail?.value;
                        const parsed = typeof raw === 'number' ? raw : Number(raw);
                        if (!Number.isFinite(parsed) || parsed <= 0) {
                            throw new Error('flows-channel-node-editor: sms timeout must be a positive number');
                        }
                        this._onChannelConfig('timeout', parsed);
                    }}
                ></platform-field>
                ${method === 'GET'
                    ? nothing
                    : html`
                        <div class="field">
                            <p class="section-title">${this.t('channel_node_editor.sms_body_template')}</p>
                            <p class="field-hint">${this.t('channel_node_editor.sms_body_template_hint')}</p>
                            <platform-json-editor
                                validate-json
                                show-toolbar="false"
                                .readonly=${false}
                                .value=${bodyTemplate}
                                @change=${this._onSmsBodyTemplateChange}
                            ></platform-json-editor>
                        </div>
                    `}
                <div class="field">
                    <p class="section-title">${this.t('channel_node_editor.sms_headers')}</p>
                    <flows-http-headers-editor
                        .value=${headers}
                        @change=${(e) => {
                            const d = e.detail;
                            if (d === null || typeof d !== 'object' || !('value' in d)) {
                                throw new Error('flows-channel-node-editor: sms headers detail.value');
                            }
                            this._onChannelConfig('headers', d.value);
                        }}
                    ></flows-http-headers-editor>
                </div>
            </div>
        `;
    }

    _renderChannelBody(channel, cfg) {
        if (channel === 'telegram') return this._renderTelegram(cfg);
        if (channel === 'email') return this._renderEmail(cfg);
        if (channel === 'webhook') return this._renderWebhook(cfg);
        if (channel === 'sms') return this._renderSms(cfg);
        throw new Error(`flows-channel-node-editor: unsupported channel ${channel}`);
    }

    render() {
        const channel = CHANNELS.includes(this.nodeConfig?.channel) ? this.nodeConfig.channel : 'telegram';
        const action = resolveAction(
            channel,
            typeof this.nodeConfig?.action === 'string' ? this.nodeConfig.action : 'send_message',
        );
        const cfg = this.nodeConfig?.channel_config && typeof this.nodeConfig.channel_config === 'object'
            ? this.nodeConfig.channel_config : {};
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'channel'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    <div class="grid">
                        <platform-field
                            mode="edit"
                            type="enum"
                            data-field="channel"
                            .label=${this.t('channel_node_editor.channel')}
                            .value=${channel}
                            .config=${{ values: CHANNELS.map((c) => ({ value: c, label: c })) }}
                            @change=${this._onChannel}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="enum"
                            data-field="action"
                            .label=${this.t('channel_node_editor.action')}
                            .value=${action}
                            .config=${{ values: this._actionEnumValues(channel) }}
                            @change=${this._onAction}
                        ></platform-field>
                    </div>
                    <details class="glass-subtle" open>
                        <summary>${this.t('channel_node_editor.channel_config')}</summary>
                        ${this._renderChannelBody(channel, cfg)}
                    </details>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-channel-node-editor', FlowsChannelNodeEditor);
