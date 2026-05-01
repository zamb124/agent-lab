/**
 * flows-channel-node-editor — редактор channel-ноды.
 *
 * Поля точно по `ChannelNodeConfig` + `ChannelType` enum
 * (apps/flows/src/models/channel_config.py, enums.py):
 *   - channel: 'telegram' | 'email' | 'whatsapp' | 'sms' | 'webhook'
 *   - action: str (default 'send_message')
 *   - channel_config: per-channel конфиг
 *
 * Per-channel подформы:
 *   - telegram: bot_token, parse_mode (HTML | MarkdownV2 | null)
 *   - email: smtp_host, smtp_port, from_email, password
 *   - webhook: url, method, headers (JSON)
 *   - whatsapp/sms: provider-specific JSON
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-variable-input.js';
import '../editors/flows-json-field-editor.js';
import { asString } from '../../_helpers/flows-resolvers.js';

const CHANNELS = Object.freeze(['telegram', 'email', 'whatsapp', 'sms', 'webhook']);
const PARSE_MODES = Object.freeze(['', 'HTML', 'MarkdownV2']);
const HTTP_METHODS = Object.freeze(['POST', 'GET', 'PUT', 'PATCH', 'DELETE']);

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
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input, select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            details {
                margin-top: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
            .grid {
                display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2);
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
        this.expanded = false;
        this.embedded = false;
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onChannel(e) {
        const v = e.target.value;
        if (!CHANNELS.includes(v)) return;
        this._emitPatch({ channel: v, channel_config: {} });
    }

    _onAction(e) {
        this._emitPatch({ action: e.target.value });
    }

    _onChannelConfig(field, value) {
        const current = this.nodeConfig?.channel_config && typeof this.nodeConfig.channel_config === 'object'
            ? this.nodeConfig.channel_config
            : {};
        const next = { ...current, [field]: value };
        this._emitPatch({ channel_config: next });
    }

    _onChannelConfigJson(parsed) {
        this._emitPatch({ channel_config: parsed && typeof parsed === 'object' ? parsed : {} });
    }

    _renderTelegram(cfg) {
        return html`
            <div class="field">
                <label>${this.t('channel_node_editor.telegram_bot_token')}</label>
                <flows-variable-input
                    .value=${typeof cfg.bot_token === 'string' ? cfg.bot_token : ''}
                    .flowVariables=${this.flowVariables}
                    @change=${(e) => this._onChannelConfig('bot_token', asString(e.detail?.value))}
                ></flows-variable-input>
            </div>
            <div class="field">
                <label>${this.t('channel_node_editor.telegram_parse_mode')}</label>
                <select
                    .value=${typeof cfg.parse_mode === 'string' ? cfg.parse_mode : ''}
                    @change=${(e) => this._onChannelConfig('parse_mode', e.target.value.length > 0 ? e.target.value : null)}
                >
                    ${PARSE_MODES.map((m) => html`<option value=${m}>${m === '' ? '—' : m}</option>`)}
                </select>
            </div>
        `;
    }

    _renderEmail(cfg) {
        return html`
            <div class="grid">
                <div class="field">
                    <label>${this.t('channel_node_editor.email_smtp_host')}</label>
                    <input type="text" .value=${asString(cfg.smtp_host)}
                        @input=${(e) => this._onChannelConfig('smtp_host', e.target.value)} />
                </div>
                <div class="field">
                    <label>${this.t('channel_node_editor.email_smtp_port')}</label>
                    <input type="number" .value=${cfg.smtp_port == null ? '' : String(cfg.smtp_port)}
                        @input=${(e) => this._onChannelConfig('smtp_port', e.target.value === '' ? null : parseInt(e.target.value, 10))} />
                </div>
                <div class="field">
                    <label>${this.t('channel_node_editor.email_from')}</label>
                    <input type="email" .value=${asString(cfg.from_email)}
                        @input=${(e) => this._onChannelConfig('from_email', e.target.value)} />
                </div>
                <div class="field">
                    <label>${this.t('channel_node_editor.email_password')}</label>
                    <flows-variable-input
                        .value=${typeof cfg.password === 'string' ? cfg.password : ''}
                        .flowVariables=${this.flowVariables}
                        @change=${(e) => this._onChannelConfig('password', asString(e.detail?.value))}
                    ></flows-variable-input>
                </div>
            </div>
        `;
    }

    _renderWebhook(cfg) {
        const headers = cfg.headers && typeof cfg.headers === 'object'
            ? JSON.stringify(cfg.headers, null, 2) : '{}';
        return html`
            <div class="field">
                <label>${this.t('channel_node_editor.webhook_url')}</label>
                <input type="url" .value=${asString(cfg.url)}
                    @input=${(e) => this._onChannelConfig('url', e.target.value)} />
            </div>
            <div class="field">
                <label>${this.t('channel_node_editor.webhook_method')}</label>
                <select .value=${typeof cfg.method === 'string' && cfg.method.length > 0 ? cfg.method : 'POST'}
                    @change=${(e) => this._onChannelConfig('method', e.target.value)}>
                    ${HTTP_METHODS.map((m) => html`<option value=${m}>${m}</option>`)}
                </select>
            </div>
            <div class="field">
                <label>${this.t('channel_node_editor.webhook_headers')}</label>
                <flows-json-field-editor
                    .value=${headers}
                    @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._onChannelConfig('headers', e.detail.parsed); }}
                ></flows-json-field-editor>
            </div>
        `;
    }

    _renderProviderJson(cfg) {
        return html`
            <div class="field">
                <label>${this.t('channel_node_editor.provider_json')}</label>
                <flows-json-field-editor
                    .value=${JSON.stringify(cfg, null, 2)}
                    @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._onChannelConfigJson(e.detail.parsed); }}
                ></flows-json-field-editor>
            </div>
        `;
    }

    _renderChannelBody(channel, cfg) {
        if (channel === 'telegram') return this._renderTelegram(cfg);
        if (channel === 'email') return this._renderEmail(cfg);
        if (channel === 'webhook') return this._renderWebhook(cfg);
        return this._renderProviderJson(cfg);
    }

    render() {
        const channel = CHANNELS.includes(this.nodeConfig?.channel) ? this.nodeConfig.channel : 'telegram';
        const action = typeof this.nodeConfig?.action === 'string' ? this.nodeConfig.action : 'send_message';
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
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    <div class="grid">
                        <div class="field">
                            <label>${this.t('channel_node_editor.channel')}</label>
                            <select .value=${channel} @change=${this._onChannel}>
                                ${CHANNELS.map((c) => html`<option value=${c} ?selected=${c === channel}>${c}</option>`)}
                            </select>
                        </div>
                        <div class="field">
                            <label>${this.t('channel_node_editor.action')}</label>
                            <input type="text" .value=${action} @input=${this._onAction} />
                        </div>
                    </div>
                    <details open>
                        <summary>${this.t('channel_node_editor.channel_config')}</summary>
                        ${this._renderChannelBody(channel, cfg)}
                    </details>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-channel-node-editor', FlowsChannelNodeEditor);
