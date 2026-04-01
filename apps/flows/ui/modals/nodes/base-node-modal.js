/**
 * BaseNodeModal - базовый класс для модалок редактирования нод
 * Наследуется от PlatformFormModal (DRY)
 * Убраны все дублирующиеся стили - используются shared
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';

const nodeModalStyles = css`
    :host {
        --modal-max-width: 1200px;
    }
    
    .state-settings-section {
        padding: var(--space-3);
        background: var(--glass-tint-subtle);
        border-radius: var(--radius-md);
        margin-top: var(--space-3);
    }
    
    .state-settings-section h4 {
        margin: 0 0 var(--space-3);
        font-size: var(--text-sm);
        font-weight: var(--font-medium);
        color: var(--text-secondary);
    }
    
    .checkbox-row {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        margin-bottom: var(--space-2);
    }
    
    .checkbox-row input[type="checkbox"] {
        width: 16px;
        height: 16px;
        cursor: pointer;
    }
    
    .checkbox-row label {
        font-size: var(--text-sm);
        color: var(--text-primary);
        cursor: pointer;
    }
    
    .message-field-row {
        margin-top: var(--space-2);
        padding-left: var(--space-5);
    }
`;

export class BaseNodeModal extends PlatformFormModal {
    static styles = [PlatformFormModal.styles, nodeModalStyles];

    static properties = {
        ...PlatformFormModal.properties,
        nodeId: { type: String, attribute: 'node-id' },
        nodeConfig: { type: Object },
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
        flowVariables: { type: Object },
        previewExecutionState: { type: Object },
        localConfig: { type: Object },
        saveToMessages: { type: Boolean },
        messageField: { type: String },
        outputKey: { type: String },
    };

    constructor() {
        super();
        this.size = 'xl';
        this.nodeId = '';
        this.nodeConfig = {};
        this.flowId = '';
        this.skillId = '';
        this.flowVariables = {};
        this.previewExecutionState = null;
        this.localConfig = {};
        this.saveToMessages = false;
        this.messageField = '';
        this.outputKey = '';
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.nodeConfig) {
            this.localConfig = JSON.parse(JSON.stringify(this.nodeConfig));
            this._loadStateSettings(this.nodeConfig);
        }
    }

    getModalTitle() {
        return this.i18n.t('node_modal.common.title_edit_default');
    }

    showModal() {
        this.title = this.getModalTitle();
        super.showModal();
        if (this.nodeConfig) {
            this.localConfig = JSON.parse(JSON.stringify(this.nodeConfig));
            this._loadStateSettings(this.nodeConfig);
        }
        this.isDirty = false;
    }
    
    _loadStateSettings(config) {
        this.outputKey = config.output_key || '';
        this.saveToMessages = config.save_to_messages || false;
        this.messageField = config.message_field || '';
    }
    
    _onOutputKeyChange(e) {
        this.outputKey = e.target.value;
        this.isDirty = true;
    }
    
    _onSaveToMessagesChange(e) {
        this.saveToMessages = e.target.checked;
        if (!this.saveToMessages) {
            this.messageField = '';
        }
        this.isDirty = true;
    }
    
    _onMessageFieldChange(e) {
        this.messageField = e.target.value;
        this.isDirty = true;
    }
    
    _buildDefaultState() {
        if (this.previewExecutionState && typeof this.previewExecutionState === 'object') {
            return structuredClone(this.previewExecutionState);
        }
        return { content: '', messages: [], variables: {} };
    }

    _applyStateSettings(config) {
        if (this.outputKey) {
            config.output_key = this.outputKey;
        }
        if (this.saveToMessages) {
            config.save_to_messages = true;
            if (this.messageField) {
                config.message_field = this.messageField;
            }
        }
        return config;
    }

    _updateConfig(field, value) {
        this.localConfig[field] = value;
        this.isDirty = true;
        this.localConfig = { ...this.localConfig };
    }

    validateForm() {
        return {};
    }

    async handleSubmit(data) {
        this.emit('node-save', {
            nodeId: this.nodeId,
            config: this.localConfig,
        });
        this.isDirty = false;
        this.close();
    }

    renderHeader() {
        return this.title;
    }

    renderSidebar() {
        return html`
            <div class="form-group">
                <label class="form-label">${this.i18n.t('node_modal.common.sidebar_node_id')}</label>
                <input 
                    type="text" 
                    class="form-input readonly" 
                    .value=${this.nodeId}
                    readonly
                />
            </div>
        `;
    }
    
    renderStateSettings() {
        return html`
            <div class="state-settings-section">
                <h4>${this.i18n.t('node_modal.common.state_section_title')}</h4>
                
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('node_modal.common.output_key_label')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${this.outputKey}
                        @input=${this._onOutputKeyChange}
                        placeholder="${this.nodeId || 'node_id'}"
                    />
                    <span class="form-hint">${this.i18n.t('node_modal.common.output_key_hint')}</span>
                </div>
                
                <div class="checkbox-row">
                    <input 
                        type="checkbox" 
                        id="save-to-messages"
                        .checked=${this.saveToMessages}
                        @change=${this._onSaveToMessagesChange}
                    />
                    <label for="save-to-messages">${this.i18n.t('node_modal.common.save_to_messages_label')}</label>
                </div>
                
                ${this.saveToMessages ? html`
                    <div class="message-field-row">
                        <div class="form-group">
                            <label class="form-label">${this.i18n.t('node_modal.common.message_field_label')}</label>
                            <input 
                                type="text" 
                                class="form-input"
                                .value=${this.messageField}
                                @input=${this._onMessageFieldChange}
                                placeholder=${this.i18n.t('node_modal.common.message_field_placeholder')}
                            />
                            <span class="form-hint">${this.i18n.t('node_modal.common.message_field_hint')}</span>
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    renderMainContent() {
        return html`<p>${this.i18n.t('node_modal.common.override_subclass')}</p>`;
    }

    renderBody() {
        return html`
            <div class="form-layout">
                <div class="form-sidebar">
                    ${this.renderSidebar()}
                </div>
                <div class="form-main">
                    ${this.renderMainContent()}
                </div>
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
                ${this.i18n.t('inline_tool_modal.save')}
            </platform-button>
        `;
    }
}

customElements.define('base-node-modal', BaseNodeModal);
