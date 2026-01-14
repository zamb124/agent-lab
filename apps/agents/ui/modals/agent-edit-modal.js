/**
 * AgentEditModal - fullscreen модалка-контейнер для редактора агента
 * Использует Light DOM для совместимости с Drawflow
 * Наследуется от PlatformLightModal (DRY)
 */
import { html } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';

export class AgentEditModal extends PlatformLightModal {
    static properties = {
        ...PlatformLightModal.properties,
        agentId: { type: String, attribute: 'agent-id' },
        skillId: { type: String, attribute: 'skill-id' },
    };

    constructor() {
        super();
        this.agentId = '';
        this.skillId = '';
    }

    connectedCallback() {
        super.connectedCallback();
        this.setAttribute('extends-platform-light-modal', '');
    }

    _onEditorClose() {
        this.close();
    }

    _onAgentSaved(e) {
        this.emit('agent-saved', e.detail);
    }

    render() {
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container">
                <agent-editor-page
                    agent-id=${this.agentId}
                    skill-id=${this.skillId || ''}
                    @editor-close=${this._onEditorClose}
                    @agent-saved=${this._onAgentSaved}
                ></agent-editor-page>
            </div>
        `;
    }
}

customElements.define('agent-edit-modal', AgentEditModal);
