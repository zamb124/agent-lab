/**
 * TriggerEditorModal - модалка создания/редактирования триггера
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import '../components/editors/json-field-editor.js';
import '../components/editors/state-mapping-editor.js';
import '../components/editors/variable-input.js';

const TRIGGER_TYPE_IDS = [
    { id: 'telegram', icon: 'send', color: '#0088cc' },
    { id: 'cron', icon: 'clock', color: '#f59e0b' },
    { id: 'webhook', icon: 'globe', color: '#8b5cf6' },
    { id: 'email', icon: 'mail', color: '#ea4335' },
    { id: 'redis', icon: 'database', color: '#dc382d' },
];

const CHANNEL_IDS = ['telegram', 'email', 'webhook'];

export class TriggerEditorModal extends PlatformFormModal {
    static styles = [
        PlatformFormModal.styles,
        css`
            :host {
                --modal-max-width: 900px;
            }
            
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
                transition: all var(--duration-fast) var(--easing-default);
                text-align: center;
            }
            
            .trigger-type-option:hover {
                border-color: var(--border-medium);
                background: var(--glass-tint-subtle);
            }
            
            .trigger-type-option.active {
                border-color: var(--accent);
                background: var(--accent-bg);
            }
            
            .trigger-type-icon {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
            }
            
            .trigger-type-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            
            .trigger-type-desc {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
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
            
            .output-actions-section {
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
            
            .output-action-content {
                flex: 1;
            }
            
            .output-action-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            
            .output-action-remove {
                background: none;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: var(--space-1);
            }
            
            .output-action-remove:hover {
                color: var(--error);
            }
            
            .add-action-btn {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-subtle);
                border: 1px dashed var(--border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                width: 100%;
                justify-content: center;
            }
            
            .add-action-btn:hover {
                background: var(--glass-tint-medium);
                border-color: var(--border-medium);
            }
            
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
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .tab:hover {
                color: var(--text-primary);
            }
            
            .tab.active {
                color: var(--accent);
                border-bottom-color: var(--accent);
            }
        `
    ];

    static properties = {
        ...PlatformFormModal.properties,
        flowId: { type: String },
        triggerId: { type: String },
        triggerConfig: { type: Object },
        selectedType: { type: String },
        activeTab: { type: String },
        outputActions: { type: Array },
        flowVariables: { type: Array },
    };

    constructor() {
        super();
        this.size = 'lg';
        this.flowId = '';
        this.triggerId = '';
        this.triggerConfig = {};
        this.flowVariables = [];
        this.selectedType = '';
        this.activeTab = 'config';
        this.outputActions = [];
    }

    getModalTitle() {
        return this.triggerId
            ? this.i18n.t('trigger_editor.title_edit')
            : this.i18n.t('trigger_editor.title_create');
    }

    showModal(triggerId = '', config = {}) {
        this.triggerId = triggerId;
        this.triggerConfig = { ...config };
        this.selectedType = config.type || '';
        this.outputActions = config.output_actions || [];
        this.activeTab = 'config';
        this.isDirty = false;
        this.title = this.getModalTitle();
        super.showModal();
    }

    _onTypeSelect(typeId) {
        this.selectedType = typeId;
        this.isDirty = true;
    }

    _onConfigChange(field, value) {
        // Обновляем config внутри triggerConfig
        this.triggerConfig = {
            ...this.triggerConfig,
            config: {
                ...(this.triggerConfig.config || {}),
                [field]: value,
            },
        };
        this.isDirty = true;
    }

    _setActiveTab(tab) {
        this.activeTab = tab;
    }

    _addOutputAction() {
        this.outputActions = [
            ...this.outputActions,
            {
                channel: 'telegram',
                action: 'send_message',
                mapping: {},
                config: {},
                condition: '',
            }
        ];
        this.isDirty = true;
    }

    _removeOutputAction(index) {
        this.outputActions = this.outputActions.filter((_, i) => i !== index);
        this.isDirty = true;
    }

    _updateOutputAction(index, field, value) {
        this.outputActions = this.outputActions.map((action, i) => {
            if (i === index) {
                return { ...action, [field]: value };
            }
            return action;
        });
        this.isDirty = true;
    }

    _renderTelegramConfig() {
        const config = this.triggerConfig.config || {};
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.i18n.t('trigger_editor.telegram.section')}</div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.telegram.bot_token')}</label>
                    <variable-input
                        name="config.bot_token"
                        .value=${config.bot_token || ''}
                        .variables=${this.flowVariables}
                        placeholder="@var:telegram_bot_token"
                        @change=${(e) => this._onConfigChange('bot_token', e.target.value)}
                    ></variable-input>
                    <span class="form-hint">${this.i18n.t('trigger_editor.telegram.bot_token_hint')}</span>
                </div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.telegram.allowed_users')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        name="config.allowed_users"
                        .value=${(config.allowed_users || []).join(', ')}
                        placeholder="123456789, 987654321"
                    />
                    <span class="form-hint">${this.i18n.t('trigger_editor.telegram.allowed_users_hint')}</span>
                </div>
            </div>
        `;
    }

    _renderCronConfig() {
        const config = this.triggerConfig.config || {};
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.i18n.t('trigger_editor.cron.section')}</div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.cron.cron')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        name="config.cron"
                        .value=${config.cron || ''}
                        placeholder="0 9 * * *"
                    />
                    <span class="form-hint">${this.i18n.t('trigger_editor.cron.cron_hint')}</span>
                </div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.cron.timezone')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        name="config.timezone"
                        .value=${config.timezone || 'UTC'}
                        placeholder="UTC"
                    />
                </div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.cron.initial_content')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        name="config.initial_content"
                        .value=${config.initial_content || ''}
                        placeholder="Scheduled task started"
                    />
                </div>
            </div>
        `;
    }

    _renderWebhookConfig() {
        const config = this.triggerConfig.config || {};
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.i18n.t('trigger_editor.webhook.section')}</div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.webhook.secret')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        name="config.secret_token"
                        .value=${config.secret_token || ''}
                        placeholder="your_secret_token"
                    />
                    <span class="form-hint">${this.i18n.t('trigger_editor.webhook.secret_hint')}</span>
                </div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.webhook.allowed_ips')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        name="config.allowed_ips"
                        .value=${(config.allowed_ips || []).join(', ')}
                        placeholder="192.168.1.1, 10.0.0.0/8"
                    />
                    <span class="form-hint">${this.i18n.t('trigger_editor.webhook.allowed_ips_hint')}</span>
                </div>
            </div>
        `;
    }

    _renderEmailConfig() {
        const config = this.triggerConfig.config || {};
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.i18n.t('trigger_editor.email.section')}</div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.email.provider')}</label>
                    <select class="form-input form-select" name="config.provider">
                        <option value="imap" ?selected=${config.provider === 'imap'}>IMAP</option>
                        <option value="mailgun" ?selected=${config.provider === 'mailgun'}>Mailgun</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.email.imap_host')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        name="config.imap_host"
                        .value=${config.imap_host || ''}
                        placeholder="imap.gmail.com"
                    />
                </div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.email.imap_user')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        name="config.imap_user"
                        .value=${config.imap_user || ''}
                        placeholder="bot@example.com"
                    />
                </div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.email.imap_password')}</label>
                    <input 
                        type="password" 
                        class="form-input"
                        name="config.imap_password"
                        .value=${config.imap_password || ''}
                        placeholder="@var:email_password"
                    />
                </div>
            </div>
        `;
    }

    _renderRedisConfig() {
        const config = this.triggerConfig.config || {};
        return html`
            <div class="config-section">
                <div class="config-section-title">${this.i18n.t('trigger_editor.redis.section')}</div>
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('trigger_editor.redis.channel')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        name="config.channel"
                        .value=${config.channel || ''}
                        placeholder="events:my_flow"
                    />
                </div>
                <div class="form-group">
                    <label class="form-label">
                        <input 
                            type="checkbox" 
                            name="config.pattern"
                            ?checked=${config.pattern}
                        />
                        ${this.i18n.t('trigger_editor.redis.pattern_subscribe')}
                    </label>
                    <span class="form-hint">${this.i18n.t('trigger_editor.redis.pattern_hint')}</span>
                </div>
            </div>
        `;
    }

    _renderTypeConfig() {
        switch (this.selectedType) {
            case 'telegram': return this._renderTelegramConfig();
            case 'cron': return this._renderCronConfig();
            case 'webhook': return this._renderWebhookConfig();
            case 'email': return this._renderEmailConfig();
            case 'redis': return this._renderRedisConfig();
            default: return '';
        }
    }

    _renderOutputAction(action, index) {
        return html`
            <div class="output-action-item">
                <div class="output-action-content">
                    <div class="output-action-header">
                        <select 
                            class="form-input form-select"
                            style="width: 140px;"
                            .value=${action.channel}
                            @change=${(e) => this._updateOutputAction(index, 'channel', e.target.value)}
                        >
                            ${CHANNEL_IDS.map((cid) => html`
                                <option value=${cid} ?selected=${cid === action.channel}>
                                    ${this.i18n.t(`trigger_editor.channels.${cid}`)}
                                </option>
                            `)}
                        </select>
                        <select 
                            class="form-input form-select"
                            style="width: 160px;"
                            .value=${action.action}
                            @change=${(e) => this._updateOutputAction(index, 'action', e.target.value)}
                        >
                            <option value="send_message">${this.i18n.t('node_modal.channel.actions.send_message')}</option>
                            <option value="send_photo">${this.i18n.t('node_modal.channel.actions.send_photo')}</option>
                            <option value="send_document">${this.i18n.t('node_modal.channel.actions.send_document')}</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('trigger_editor.output_action.mapping_json')}</label>
                        <json-field-editor
                            .value=${JSON.stringify(action.mapping || {}, null, 2)}
                            @change=${(e) => {
                                if (e.target.isValid()) {
                                    this._updateOutputAction(index, 'mapping', e.target.getParsedValue());
                                }
                            }}
                            min-height="60"
                            placeholder='{"recipient": "@state:variables.chat_id", "text": "@state:response"}'
                        ></json-field-editor>
                    </div>
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('trigger_editor.output_action.condition')}</label>
                        <input 
                            type="text" 
                            class="form-input"
                            .value=${action.condition || ''}
                            @change=${(e) => this._updateOutputAction(index, 'condition', e.target.value)}
                            placeholder="@state:should_reply == true"
                        />
                    </div>
                </div>
                <button 
                    class="output-action-remove"
                    @click=${() => this._removeOutputAction(index)}
                    title=${this.i18n.t('trigger_editor.output_action.remove_title')}
                >
                    <platform-icon name="x" size="16"></platform-icon>
                </button>
            </div>
        `;
    }

    _buildConfig() {
        const form = this.shadowRoot.querySelector('form');
        const formData = new FormData(form);
        
        const triggerId = formData.get('trigger_id')?.trim() || this.triggerId;
        const name = formData.get('name')?.trim() || '';
        
        if (!triggerId) {
            throw new Error(this.i18n.t('trigger_editor.err_trigger_id'));
        }
        
        if (!this.selectedType) {
            throw new Error(this.i18n.t('trigger_editor.err_type'));
        }
        
        // Начинаем с сохраненных значений из triggerConfig.config (для variable-input и др.)
        const config = { ...(this.triggerConfig.config || {}) };
        
        // Дополняем/перезаписываем значениями из FormData
        for (const [key, value] of formData.entries()) {
            if (key.startsWith('config.')) {
                const configKey = key.replace('config.', '');
                if (configKey === 'allowed_users' || configKey === 'allowed_ips') {
                    config[configKey] = value ? value.split(',').map(s => s.trim()).filter(Boolean) : [];
                } else if (configKey === 'pattern') {
                    config[configKey] = value === 'on';
                } else {
                    config[configKey] = value;
                }
            }
        }
        
        const mappingEditor = this.shadowRoot.querySelector('state-mapping-editor');
        const outputMapping = mappingEditor?.getValue() || {};
        
        return {
            trigger_id: triggerId,
            name: name || triggerId,
            type: this.selectedType,
            enabled: this.triggerConfig.enabled !== false,
            config,
            output_mapping: outputMapping,
            output_actions: this.outputActions,
        };
    }

    async handleSubmit() {
        try {
            const config = this._buildConfig();
            
            this.emit('trigger-save', {
                triggerId: config.trigger_id,
                config,
            });
            
            this.isDirty = false;
            this.close();
        } catch (error) {
            this.error(error.message);
        }
    }

    renderBody() {
        const config = this.triggerConfig;
        const isEdit = !!this.triggerId;
        
        return html`
            <form @submit=${(e) => { e.preventDefault(); this._onSubmit(); }}>
                <div class="tabs">
                    <button 
                        type="button"
                        class="tab ${this.activeTab === 'config' ? 'active' : ''}"
                        @click=${() => this._setActiveTab('config')}
                    >
                        ${this.i18n.t('trigger_editor.tabs_config')}
                    </button>
                    <button 
                        type="button"
                        class="tab ${this.activeTab === 'mapping' ? 'active' : ''}"
                        @click=${() => this._setActiveTab('mapping')}
                    >
                        ${this.i18n.t('trigger_editor.tabs_mapping')}
                    </button>
                    <button 
                        type="button"
                        class="tab ${this.activeTab === 'output' ? 'active' : ''}"
                        @click=${() => this._setActiveTab('output')}
                    >
                        ${this.i18n.t('trigger_editor.tabs_output')}
                    </button>
                </div>
                
                ${this.activeTab === 'config' ? html`
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('trigger_editor.field_trigger_id')}</label>
                        <input 
                            type="text" 
                            class="form-input ${isEdit ? 'readonly' : ''}"
                            name="trigger_id"
                            .value=${this.triggerId}
                            ?readonly=${isEdit}
                            placeholder="my_telegram_trigger"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('trigger_editor.field_name')}</label>
                        <input 
                            type="text" 
                            class="form-input"
                            name="name"
                            .value=${config.name || ''}
                            placeholder="Main Telegram Bot"
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('trigger_editor.field_trigger_type')}</label>
                        <div class="trigger-type-selector">
                            ${TRIGGER_TYPE_IDS.map((type) => html`
                                <div 
                                    class="trigger-type-option ${this.selectedType === type.id ? 'active' : ''}"
                                    @click=${() => this._onTypeSelect(type.id)}
                                >
                                    <div class="trigger-type-icon" style="background: ${type.color}20; color: ${type.color};">
                                        <platform-icon name="${type.icon}" size="24"></platform-icon>
                                    </div>
                                    <div class="trigger-type-name">${this.i18n.t(`trigger_editor.types.${type.id}.name`)}</div>
                                    <div class="trigger-type-desc">${this.i18n.t(`trigger_editor.types.${type.id}.description`)}</div>
                                </div>
                            `)}
                        </div>
                    </div>
                    
                    ${this._renderTypeConfig()}
                ` : ''}
                
                ${this.activeTab === 'mapping' ? html`
                    <div class="config-section">
                        <div class="config-section-title">${this.i18n.t('trigger_editor.mapping_output_title')}</div>
                        <p style="font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--space-3);">
                            ${this.i18n.t('trigger_editor.mapping_hint')}
                        </p>
                        <state-mapping-editor
                            mode="input"
                            .mappings=${config.output_mapping || config.input_mapping || {}}
                            placeholder-left="variables.chat_id"
                            placeholder-right="message.chat.id"
                        ></state-mapping-editor>
                    </div>
                    
                    <div class="config-section">
                        <div class="config-section-title">${this.i18n.t('trigger_editor.mapping_examples_title', { type: this.selectedType || '—' })}</div>
                        ${this._renderMappingExamples()}
                    </div>
                ` : ''}
                
                ${this.activeTab === 'output' ? html`
                    <div class="output-actions-section">
                        <div class="config-section-title">${this.i18n.t('trigger_editor.output_title')}</div>
                        <p style="font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--space-3);">
                            ${this.i18n.t('trigger_editor.output_hint')}
                        </p>
                        
                        ${this.outputActions.map((action, index) => 
                            this._renderOutputAction(action, index)
                        )}
                        
                        <button 
                            type="button"
                            class="add-action-btn"
                            @click=${this._addOutputAction}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                            ${this.i18n.t('trigger_editor.add_action')}
                        </button>
                    </div>
                ` : ''}
            </form>
        `;
    }

    _renderMappingExamples() {
        const ROWS = {
            telegram: [
                { path: 'message.text', key: 'message_text' },
                { path: 'message.chat.id', key: 'message_chat_id' },
                { path: 'message.from.id', key: 'message_from_id' },
                { path: 'message.from.username', key: 'message_from_username' },
            ],
            webhook: [
                { path: 'body.data', key: 'body_data' },
                { path: 'headers.X-Custom', key: 'headers_x_custom' },
                { path: 'query.param', key: 'query_param' },
            ],
            cron: [{ path: 'scheduled_time', key: 'scheduled_time' }],
            email: [
                { path: 'from', key: 'from' },
                { path: 'subject', key: 'subject' },
                { path: 'body', key: 'body' },
            ],
            redis: [
                { path: 'channel', key: 'channel' },
                { path: 'data', key: 'data' },
            ],
        };
        const rows = ROWS[this.selectedType] || [];
        if (rows.length === 0) {
            return html`<p style="color: var(--text-tertiary);">${this.i18n.t('trigger_editor.mapping_select_type')}</p>`;
        }
        const st = this.selectedType;
        return html`
            <div style="font-size: var(--text-sm); font-family: var(--font-mono);">
                ${rows.map((row) => html`
                    <div style="padding: var(--space-1) 0; display: flex; gap: var(--space-3);">
                        <code style="color: var(--accent);">${row.path}</code>
                        <span style="color: var(--text-tertiary);">— ${this.i18n.t(`trigger_editor.ex.${st}.${row.key}`)}</span>
                    </div>
                `)}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="secondary" @click=${this.close}>
                ${this.i18n.t('editor.cancel')}
            </platform-button>
            <platform-button 
                variant="primary" 
                ?loading=${this.loading}
                @click=${this._onSubmit}
            >
                ${this.triggerId ? this.i18n.t('inline_tool_modal.save') : this.i18n.t('inline_tool_modal.create')}
            </platform-button>
        `;
    }
}

customElements.define('trigger-editor-modal', TriggerEditorModal);
