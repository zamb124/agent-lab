/**
 * ChannelNodeEditor - редактор для Channel типа ноды
 * Отправка сообщений в Telegram, Email, WhatsApp, Webhook
 */
import { html, css } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/json-field-editor.js';
import '../editors/variable-input.js';

const CHANNEL_TYPES = [
    { id: 'telegram', name: 'Telegram', icon: 'send', color: '#0088cc' },
    { id: 'email', name: 'Email', icon: 'mail', color: '#ea4335' },
    { id: 'whatsapp', name: 'WhatsApp', icon: 'message-circle', color: '#25d366' },
    { id: 'sms', name: 'SMS', icon: 'phone', color: '#6b7280' },
    { id: 'webhook', name: 'Webhook', icon: 'globe', color: '#8b5cf6' },
];

const CHANNEL_ACTIONS = {
    telegram: [
        { id: 'send_message', name: 'Отправить сообщение' },
        { id: 'send_photo', name: 'Отправить фото' },
        { id: 'send_document', name: 'Отправить документ' },
    ],
    email: [
        { id: 'send_email', name: 'Отправить email' },
    ],
    whatsapp: [
        { id: 'send_message', name: 'Отправить сообщение' },
    ],
    sms: [
        { id: 'send_sms', name: 'Отправить SMS' },
    ],
    webhook: [
        { id: 'post', name: 'POST запрос' },
    ],
};

export class ChannelNodeEditor extends BaseNodeEditor {
    static properties = {
        ...BaseNodeEditor.properties,
        selectedChannel: { type: String },
    };

    static styles = [
        BaseNodeEditor.styles,
        css`
            .channel-selector {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            
            .channel-option {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .channel-option:hover {
                border-color: var(--border-medium);
                background: var(--glass-tint-subtle);
            }
            
            .channel-option.active {
                border-color: var(--accent);
                background: var(--accent-bg);
            }
            
            .channel-icon {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
            }
            
            .channel-label {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            
            .config-section {
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                margin-top: var(--space-3);
            }
            
            .config-section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
        `
    ];

    constructor() {
        super();
        this._nodeType = 'channel';
        this.selectedChannel = '';
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.nodeConfig?.channel) {
            this.selectedChannel = this.nodeConfig.channel;
        }
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('nodeConfig') && this.nodeConfig?.channel) {
            this.selectedChannel = this.nodeConfig.channel;
        }
    }

    _onChannelSelect(channelId) {
        this.selectedChannel = channelId;
        this._onInputChange('channel', channelId);
        
        const actions = CHANNEL_ACTIONS[channelId] || [];
        if (actions.length > 0) {
            this._onInputChange('action', actions[0].id);
        }
    }

    _updateChannelConfig(field, value) {
        const channelConfig = { ...(this.nodeConfig.channel_config || {}), [field]: value };
        this._onInputChange('channel_config', channelConfig);
    }

    _renderChannelConfig() {
        const channel = this.selectedChannel;
        const config = this.nodeConfig;
        
        if (channel === 'telegram') {
            return html`
                <div class="config-section">
                    <div class="config-section-title">Telegram</div>
                    <div class="form-group">
                        <div class="form-label">
                            <span class="form-label-text">Bot Token</span>
                        </div>
                        <variable-input
                            .value=${config.channel_config?.bot_token || ''}
                            .variables=${this.flowVariables || {}}
                            placeholder="@var:telegram_bot_token"
                            @change=${(e) => this._updateChannelConfig('bot_token', e.detail.value)}
                        ></variable-input>
                        <span class="form-hint">Используйте @var:имя для ссылки на переменную</span>
                    </div>
                    <div class="form-group">
                        <div class="form-label">
                            <span class="form-label-text">Parse Mode</span>
                        </div>
                        <select 
                            class="form-input form-select"
                            .value=${config.channel_config?.parse_mode || 'HTML'}
                            @change=${(e) => this._updateChannelConfig('parse_mode', e.target.value)}
                        >
                            <option value="HTML">HTML</option>
                            <option value="Markdown">Markdown</option>
                            <option value="MarkdownV2">MarkdownV2</option>
                        </select>
                    </div>
                </div>
            `;
        }
        
        if (channel === 'email') {
            return html`
                <div class="config-section">
                    <div class="config-section-title">Email</div>
                    <div class="form-group">
                        <div class="form-label">
                            <span class="form-label-text">SMTP Host</span>
                        </div>
                        <input 
                            type="text" 
                            class="form-input"
                            .value=${config.channel_config?.smtp_host || ''}
                            @change=${(e) => this._updateChannelConfig('smtp_host', e.target.value)}
                            placeholder="smtp.gmail.com"
                        />
                    </div>
                    <div class="form-group">
                        <div class="form-label">
                            <span class="form-label-text">From Email</span>
                        </div>
                        <input 
                            type="text" 
                            class="form-input"
                            .value=${config.channel_config?.from_email || ''}
                            @change=${(e) => this._updateChannelConfig('from_email', e.target.value)}
                            placeholder="bot@example.com"
                        />
                    </div>
                </div>
            `;
        }
        
        if (channel === 'webhook') {
            return html`
                <div class="config-section">
                    <div class="config-section-title">Webhook</div>
                    <div class="form-group">
                        <div class="form-label">
                            <span class="form-label-text">URL</span>
                        </div>
                        <input 
                            type="text" 
                            class="form-input"
                            .value=${config.channel_config?.url || ''}
                            @change=${(e) => this._updateChannelConfig('url', e.target.value)}
                            placeholder="https://api.example.com/webhook"
                        />
                    </div>
                    <div class="form-group">
                        <div class="form-label">
                            <span class="form-label-text">Headers (JSON)</span>
                        </div>
                        <json-field-editor
                            .value=${config.channel_config?.headers ? JSON.stringify(config.channel_config.headers, null, 2) : '{}'}
                            @change=${(e) => {
                                if (e.target.isValid()) {
                                    this._updateChannelConfig('headers', e.target.getParsedValue());
                                }
                            }}
                            min-height="60"
                        ></json-field-editor>
                    </div>
                </div>
            `;
        }
        
        return '';
    }

    renderFields() {
        const config = this.nodeConfig;
        const showCommonFields = !this.expanded;
        const actions = CHANNEL_ACTIONS[this.selectedChannel] || [];
        
        return html`
            ${showCommonFields ? html`
                ${this.renderNodeIdField()}
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Имя</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.name || ''}
                        @change=${(e) => this._onInputChange('name', e.target.value)}
                        placeholder="Send to Telegram"
                    />
                </div>
            ` : ''}
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">Канал</span>
                </div>
                <div class="channel-selector">
                    ${CHANNEL_TYPES.map(ch => html`
                        <div 
                            class="channel-option ${this.selectedChannel === ch.id ? 'active' : ''}"
                            @click=${() => this._onChannelSelect(ch.id)}
                        >
                            <div class="channel-icon" style="background: ${ch.color}20; color: ${ch.color};">
                                <platform-icon name="${ch.icon}" size="20"></platform-icon>
                            </div>
                            <span class="channel-label">${ch.name}</span>
                        </div>
                    `)}
                </div>
            </div>
            
            ${this.selectedChannel && actions.length > 0 ? html`
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Действие</span>
                    </div>
                    <select 
                        class="form-input form-select"
                        .value=${config.action || actions[0]?.id || ''}
                        @change=${(e) => this._onInputChange('action', e.target.value)}
                    >
                        ${actions.map(action => html`
                            <option 
                                value=${action.id}
                                ?selected=${action.id === config.action}
                            >
                                ${action.name}
                            </option>
                        `)}
                    </select>
                </div>
            ` : ''}
            
            ${this._renderChannelConfig()}
            
            ${this.renderMappingSection()}
            
            ${this._renderTestPanel()}
        `;
    }
}

customElements.define('channel-node-editor', ChannelNodeEditor);
