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
`;

export class BaseNodeModal extends PlatformFormModal {
    static styles = [PlatformFormModal.styles, nodeModalStyles];

    static properties = {
        ...PlatformFormModal.properties,
        nodeId: { type: String, attribute: 'node-id' },
        nodeConfig: { type: Object },
        agentId: { type: String, attribute: 'agent-id' },
        skillId: { type: String, attribute: 'skill-id' },
        agentVariables: { type: Object },
        localConfig: { type: Object },
    };

    constructor() {
        super();
        this.size = 'xl';
        this.nodeId = '';
        this.nodeConfig = {};
        this.agentId = '';
        this.skillId = '';
        this.agentVariables = {};
        this.localConfig = {};
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.nodeConfig) {
            this.localConfig = JSON.parse(JSON.stringify(this.nodeConfig));
        }
    }

    getModalTitle() {
        return 'Edit Node';
    }

    showModal() {
        this.title = this.getModalTitle();
        super.showModal();
        if (this.nodeConfig) {
            this.localConfig = JSON.parse(JSON.stringify(this.nodeConfig));
        }
        this.isDirty = false;
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
                <label class="form-label">Node ID</label>
                <input 
                    type="text" 
                    class="form-input readonly" 
                    .value=${this.nodeId}
                    readonly
                />
            </div>
        `;
    }

    renderMainContent() {
        return html`<p>Override renderMainContent() in subclass</p>`;
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
                Отмена
            </platform-button>
            <platform-button 
                variant="primary" 
                ?loading=${this.loading}
                @click=${this._onSubmit}
            >
                Сохранить
            </platform-button>
        `;
    }
}

customElements.define('base-node-modal', BaseNodeModal);
