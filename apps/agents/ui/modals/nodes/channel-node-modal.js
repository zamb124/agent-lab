/**
 * ChannelNodeModal - модалка создания/редактирования Channel Node
 * Отправка сообщений в Telegram, Email, WhatsApp, Webhook
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';
import '../../components/editors/json-field-editor.js';

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

export class ChannelNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
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

    static properties = {
        ...BaseNodeModal.properties,
        selectedChannel: { type: String },
    };

    constructor() {
        super();
        this.selectedChannel = '';
    }

    getNodeType() {
        return 'channel';
    }

    getModalTitle() {
        return 'Channel Node';
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);
        this.selectedChannel = config.channel || 'telegram';
    }

    _onChannelSelect(channelId) {
        this.selectedChannel = channelId;
        this.isDirty = true;
    }

    _buildConfig() {
        const nodeId = this.shadowRoot.querySelector('[name="node_id"]')?.value?.trim();
        const name = this.shadowRoot.querySelector('[name="name"]')?.value?.trim() || '';
        const action = this.shadowRoot.querySelector('[name="action"]')?.value || 'send_message';
        
        if (!nodeId) {
            throw new Error('Node ID обязателен');
        }
        
        if (!this.selectedChannel) {
            throw new Error('Выберите канал');
        }
        
        const config = {
            type: 'channel',
            channel: this.selectedChannel,
            action,
            channel_config: {},
        };
        
        if (name) config.name = name;
        
        // Channel config
        if (this.selectedChannel === 'telegram') {
            const botToken = this.shadowRoot.querySelector('[name="bot_token"]')?.value?.trim();
            const parseMode = this.shadowRoot.querySelector('[name="parse_mode"]')?.value || 'HTML';
            
            if (botToken) config.channel_config.bot_token = botToken;
            config.channel_config.parse_mode = parseMode;
        }
        
        if (this.selectedChannel === 'webhook') {
            const url = this.shadowRoot.querySelector('[name="webhook_url"]')?.value?.trim();
            if (url) config.channel_config.url = url;
            
            const headersEditor = this.shadowRoot.querySelector('json-field-editor[name="headers"]');
            if (headersEditor?.getValue()?.trim()) {
                if (!headersEditor.isValid()) {
                    throw new Error('Неверный формат Headers JSON');
                }
                const headers = headersEditor.getParsedValue();
                if (Object.keys(headers).length > 0) {
                    config.channel_config.headers = headers;
                }
            }
        }
        
        if (this.selectedChannel === 'email') {
            const smtpHost = this.shadowRoot.querySelector('[name="smtp_host"]')?.value?.trim();
            const fromEmail = this.shadowRoot.querySelector('[name="from_email"]')?.value?.trim();
            
            if (smtpHost) config.channel_config.smtp_host = smtpHost;
            if (fromEmail) config.channel_config.from_email = fromEmail;
        }
        
        // Input mapping
        const inputMappingEditor = this.shadowRoot.querySelector('state-mapping-editor');
        const inputMapping = inputMappingEditor?.getValue() || {};
        if (Object.keys(inputMapping).length > 0) {
            config.input_mapping = inputMapping;
        }
        
        return this._applyStateSettings(config);
    }

    _renderChannelConfig() {
        const config = this.nodeConfig;
        
        if (this.selectedChannel === 'telegram') {
            return html`
                <div class="config-section">
                    <div class="config-section-title">Telegram</div>
                    <div class="form-group">
                        <label class="form-label">Bot Token</label>
                        <input 
                            type="text" 
                            name="bot_token"
                            class="form-input"
                            .value=${config.channel_config?.bot_token || ''}
                            placeholder="@var:telegram_bot_token"
                        />
                        <span class="form-hint">Используйте @var:имя для ссылки на переменную</span>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Parse Mode</label>
                        <select name="parse_mode" class="form-select">
                            <option value="HTML" ?selected=${config.channel_config?.parse_mode === 'HTML'}>HTML</option>
                            <option value="Markdown" ?selected=${config.channel_config?.parse_mode === 'Markdown'}>Markdown</option>
                            <option value="MarkdownV2" ?selected=${config.channel_config?.parse_mode === 'MarkdownV2'}>MarkdownV2</option>
                        </select>
                    </div>
                </div>
            `;
        }
        
        if (this.selectedChannel === 'webhook') {
            return html`
                <div class="config-section">
                    <div class="config-section-title">Webhook</div>
                    <div class="form-group">
                        <label class="form-label">URL</label>
                        <input 
                            type="text" 
                            name="webhook_url"
                            class="form-input"
                            .value=${config.channel_config?.url || ''}
                            placeholder="https://api.example.com/webhook"
                        />
                    </div>
                    <div class="form-group">
                        <label class="form-label">Headers (JSON)</label>
                        <json-field-editor
                            name="headers"
                            .value=${config.channel_config?.headers ? JSON.stringify(config.channel_config.headers, null, 2) : '{}'}
                            min-height="60"
                        ></json-field-editor>
                    </div>
                </div>
            `;
        }
        
        if (this.selectedChannel === 'email') {
            return html`
                <div class="config-section">
                    <div class="config-section-title">Email</div>
                    <div class="form-group">
                        <label class="form-label">SMTP Host</label>
                        <input 
                            type="text" 
                            name="smtp_host"
                            class="form-input"
                            .value=${config.channel_config?.smtp_host || ''}
                            placeholder="smtp.gmail.com"
                        />
                    </div>
                    <div class="form-group">
                        <label class="form-label">From Email</label>
                        <input 
                            type="text" 
                            name="from_email"
                            class="form-input"
                            .value=${config.channel_config?.from_email || ''}
                            placeholder="bot@example.com"
                        />
                    </div>
                </div>
            `;
        }
        
        return '';
    }

    renderBody() {
        const config = this.nodeConfig;
        const actions = CHANNEL_ACTIONS[this.selectedChannel] || [];
        
        return html`
            <div class="form-layout">
                <div class="form-sidebar">
                    <div class="form-group">
                        <label class="form-label">Node ID *</label>
                        <input 
                            type="text" 
                            name="node_id"
                            class="form-input ${this.isEdit ? 'readonly' : ''}"
                            .value=${this.nodeId || ''}
                            ?readonly=${this.isEdit}
                            placeholder="send_telegram"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Имя</label>
                        <input 
                            type="text" 
                            name="name"
                            class="form-input"
                            .value=${config.name || ''}
                            placeholder="Send to Channel"
                        />
                    </div>
                    
                    ${this.renderStateSettings()}
                </div>
                
                <div class="form-main">
                    <div class="form-group">
                        <label class="form-label">Канал</label>
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
                            <label class="form-label">Действие</label>
                            <select name="action" class="form-select">
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
                    
                    <div class="form-group">
                        <state-mapping-editor
                            mode="input"
                            .mappings=${config.input_mapping || {}}
                            .stateVariables=${Object.keys(this._buildDefaultState())}
                        ></state-mapping-editor>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('channel-node-modal', ChannelNodeModal);
